"""Google Calendar service.

Pulls upcoming events for a calendar, exposes filter helpers for the next-hour
view, and computes the today/week completion percentages used by ProgressWidget.

The Google API client is synchronous; callers must wrap `fetch_events` in
`asyncio.to_thread` so the Textual event loop never blocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from dateutil import parser as dtparser

from .. import paths

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

DONE_PREFIX = "✓ "
CANCELLED_PREFIX = "✗ "
EXT_DONE_KEY = "personalizer_done"
EXT_CANCELLED_KEY = "personalizer_cancelled"


@dataclass(frozen=True)
class Event:
    summary: str
    start: datetime
    end: datetime
    id: str = ""
    done: bool = False
    cancelled: bool = False

    @property
    def is_all_day(self) -> bool:
        return self.start.hour == 0 and self.end - self.start >= timedelta(hours=23)

    def is_active(self, now: datetime) -> bool:
        return self.start <= now < self.end

    def is_done(self, now: datetime) -> bool:
        return self.done or self.end <= now

    def state(self, now: datetime) -> str:
        """One of: cancelled, done, active, upcoming. Drives row colour."""
        if self.cancelled:
            return "cancelled"
        if self.done or self.end <= now:
            return "done"
        if self.start <= now:
            return "active"
        return "upcoming"


class CalendarUnavailable(Exception):
    """Raised when credentials are missing or refresh fails."""


def _build_service():
    """Build a Google Calendar API client. Imports happen lazily so the rest of
    the app (and tests) can run without google-* installed if needed."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not paths.GOOGLE_TOKEN.exists():
        raise CalendarUnavailable(
            "No token.json found. Run `personalizer-setup` to authorize."
        )

    creds = Credentials.from_authorized_user_file(str(paths.GOOGLE_TOKEN), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                paths.GOOGLE_TOKEN.write_text(creds.to_json(), encoding="utf-8")
            except Exception as e:
                raise CalendarUnavailable(
                    f"Token refresh failed: {e}. Re-run `personalizer-setup`."
                ) from e
        else:
            raise CalendarUnavailable("Invalid credentials. Re-run `personalizer-setup`.")

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_event(raw: dict[str, Any]) -> Event | None:
    summary = raw.get("summary", "(no title)")
    start_raw = raw.get("start", {})
    end_raw = raw.get("end", {})
    start_str = start_raw.get("dateTime") or start_raw.get("date")
    end_str = end_raw.get("dateTime") or end_raw.get("date")
    if not start_str or not end_str:
        return None
    try:
        start = dtparser.isoparse(start_str)
        end = dtparser.isoparse(end_str)
    except (ValueError, TypeError):
        return None
    if start.tzinfo is None:
        start = start.astimezone()
    if end.tzinfo is None:
        end = end.astimezone()
    ext_private = raw.get("extendedProperties", {}).get("private", {}) or {}
    done = ext_private.get(EXT_DONE_KEY) == "1"
    cancelled = ext_private.get(EXT_CANCELLED_KEY) == "1"
    # Strip our visual prefixes so the displayed title stays clean.
    if summary.startswith(DONE_PREFIX):
        summary = summary[len(DONE_PREFIX):]
    elif summary.startswith(CANCELLED_PREFIX):
        summary = summary[len(CANCELLED_PREFIX):]
    return Event(
        summary=summary,
        start=start,
        end=end,
        id=raw.get("id", ""),
        done=done,
        cancelled=cancelled,
    )


def fetch_events(calendar_id: str = "primary", lookahead_hours: int = 24) -> list[Event]:
    """Fetch events from now to now + lookahead_hours. Synchronous — wrap in to_thread."""
    service = _build_service()
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(hours=lookahead_hours)
    # Look back to start-of-week so progress math has a complete week to count.
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    response = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=week_start.isoformat(),
            timeMax=horizon.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
    )
    parsed = [_parse_event(e) for e in response.get("items", [])]
    return [e for e in parsed if e is not None]


def filter_next_hour(
    events: list[Event], now: datetime, lookahead_minutes: int = 60, limit: int = 5
) -> list[Event]:
    """Return up to `limit` events that overlap the next `lookahead_minutes`."""
    horizon = now + timedelta(minutes=lookahead_minutes)
    upcoming = [e for e in events if e.end > now and e.start <= horizon and not e.is_all_day]
    upcoming.sort(key=lambda e: e.start)
    return upcoming[:limit]


def progress_today(events: list[Event], now: datetime) -> int:
    """Percentage (0-100) of today's timed events that have ended.

    Cancelled events drop out of the denominator entirely; manually-done
    events count toward the numerator regardless of clock time.
    """
    today = now.astimezone().date()
    todays = [
        e
        for e in events
        if e.start.astimezone().date() == today
        and not e.is_all_day
        and not e.cancelled
    ]
    if not todays:
        return 0
    done = sum(1 for e in todays if e.is_done(now))
    return round(100 * done / len(todays))


def progress_week(events: list[Event], now: datetime) -> int:
    """Percentage (0-100) of this ISO week's timed events that have ended."""
    local_now = now.astimezone()
    monday = local_now.date() - timedelta(days=local_now.weekday())
    sunday = monday + timedelta(days=6)
    weeks = [
        e
        for e in events
        if monday <= e.start.astimezone().date() <= sunday
        and not e.is_all_day
        and not e.cancelled
    ]
    if not weeks:
        return 0
    done = sum(1 for e in weeks if e.is_done(now))
    return round(100 * done / len(weeks))


# ---- write operations ---------------------------------------------------


def _patch_event(
    calendar_id: str,
    event_id: str,
    *,
    set_done: bool = False,
    set_cancelled: bool = False,
) -> None:
    """Apply a personalizer flag to a Google Calendar event.

    Sets the matching extendedProperties.private key AND prefixes the summary
    with ✓ / ✗ so the marker shows up in the Google Calendar UI as well.
    Idempotent: safe to call twice on the same event.
    """
    service = _build_service()
    current = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    summary = current.get("summary", "")
    # Strip any existing personalizer prefix so we don't double up.
    if summary.startswith(DONE_PREFIX):
        summary = summary[len(DONE_PREFIX):]
    elif summary.startswith(CANCELLED_PREFIX):
        summary = summary[len(CANCELLED_PREFIX):]

    private: dict[str, str] = {}
    if set_done:
        private[EXT_DONE_KEY] = "1"
        private[EXT_CANCELLED_KEY] = ""  # clear opposing flag
        summary = DONE_PREFIX + summary
    elif set_cancelled:
        private[EXT_CANCELLED_KEY] = "1"
        private[EXT_DONE_KEY] = ""
        summary = CANCELLED_PREFIX + summary

    body = {
        "summary": summary,
        "extendedProperties": {"private": private},
    }
    service.events().patch(
        calendarId=calendar_id, eventId=event_id, body=body
    ).execute()


def mark_done(calendar_id: str, event_id: str) -> None:
    """Mark a calendar event as personalizer-done. Synchronous — wrap in to_thread."""
    _patch_event(calendar_id, event_id, set_done=True)


def mark_cancelled(calendar_id: str, event_id: str) -> None:
    """Mark a calendar event as personalizer-cancelled. Synchronous — wrap in to_thread."""
    _patch_event(calendar_id, event_id, set_cancelled=True)

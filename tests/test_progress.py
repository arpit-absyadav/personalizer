"""Tests for today/week progress math in the gcal service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from personalizer.services.gcal import Event, progress_today, progress_week


def _evt(start: datetime, duration_minutes: int = 30, summary: str = "x") -> Event:
    return Event(summary=summary, start=start, end=start + timedelta(minutes=duration_minutes))


def test_progress_today_no_events_is_zero() -> None:
    now = datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc)
    assert progress_today([], now) == 0


def test_progress_today_all_done() -> None:
    now = datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc)
    events = [
        _evt(datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)),
        _evt(datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc)),
    ]
    assert progress_today(events, now) == 100


def test_progress_today_half_done() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        _evt(datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)),  # done
        _evt(datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc)),  # done
        _evt(datetime(2026, 4, 10, 13, 0, tzinfo=timezone.utc)),  # not yet
        _evt(datetime(2026, 4, 10, 15, 0, tzinfo=timezone.utc)),  # not yet
    ]
    assert progress_today(events, now) == 50


def test_progress_today_ignores_other_days() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        _evt(datetime(2026, 4, 9, 9, 0, tzinfo=timezone.utc)),  # yesterday
        _evt(datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)),  # today, done
        _evt(datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc)),  # tomorrow
    ]
    assert progress_today(events, now) == 100


def test_progress_week_includes_full_iso_week() -> None:
    # 2026-04-10 is a Friday → ISO week is Mon Apr 6 - Sun Apr 12.
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        _evt(datetime(2026, 4, 6, 9, 0, tzinfo=timezone.utc)),  # Mon, done
        _evt(datetime(2026, 4, 8, 9, 0, tzinfo=timezone.utc)),  # Wed, done
        _evt(datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)),  # Fri, done
        _evt(datetime(2026, 4, 11, 9, 0, tzinfo=timezone.utc)),  # Sat, not yet
    ]
    assert progress_week(events, now) == 75


def test_progress_week_excludes_other_weeks() -> None:
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    events = [
        _evt(datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc)),  # last week
        _evt(datetime(2026, 4, 13, 9, 0, tzinfo=timezone.utc)),  # next week
        _evt(datetime(2026, 4, 7, 9, 0, tzinfo=timezone.utc)),  # this week, done
    ]
    assert progress_week(events, now) == 100

"""Tests for the next-60-min event filter."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from personalizer.services.gcal import Event, filter_next_hour


def _evt(start: datetime, duration_minutes: int = 30, summary: str = "x") -> Event:
    return Event(summary=summary, start=start, end=start + timedelta(minutes=duration_minutes))


NOW = datetime(2026, 4, 10, 14, 0, tzinfo=timezone.utc)


def test_filter_includes_events_within_next_hour() -> None:
    events = [
        _evt(NOW + timedelta(minutes=10)),
        _evt(NOW + timedelta(minutes=30)),
        _evt(NOW + timedelta(minutes=55)),
    ]
    out = filter_next_hour(events, NOW)
    assert len(out) == 3


def test_filter_excludes_events_after_horizon() -> None:
    events = [
        _evt(NOW + timedelta(minutes=70)),  # past 60-min horizon
        _evt(NOW + timedelta(hours=3)),
    ]
    assert filter_next_hour(events, NOW) == []


def test_filter_includes_in_progress_event() -> None:
    events = [
        _evt(NOW - timedelta(minutes=10), duration_minutes=60),  # started, still running
    ]
    out = filter_next_hour(events, NOW)
    assert len(out) == 1
    assert out[0].is_active(NOW)


def test_filter_excludes_finished_event() -> None:
    events = [
        _evt(NOW - timedelta(hours=2), duration_minutes=30),  # ended long ago
    ]
    assert filter_next_hour(events, NOW) == []


def test_filter_respects_limit() -> None:
    events = [_evt(NOW + timedelta(minutes=i)) for i in range(1, 20)]
    out = filter_next_hour(events, NOW, limit=5)
    assert len(out) == 5


def test_filter_results_are_sorted() -> None:
    events = [
        _evt(NOW + timedelta(minutes=40)),
        _evt(NOW + timedelta(minutes=10)),
        _evt(NOW + timedelta(minutes=25)),
    ]
    out = filter_next_hour(events, NOW)
    assert [e.start for e in out] == sorted(e.start for e in out)


def test_filter_excludes_all_day_events() -> None:
    midnight = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    events = [
        Event(summary="all-day", start=midnight, end=midnight + timedelta(days=1)),
        _evt(NOW + timedelta(minutes=10)),
    ]
    out = filter_next_hour(events, NOW)
    assert len(out) == 1
    assert out[0].summary == "x"

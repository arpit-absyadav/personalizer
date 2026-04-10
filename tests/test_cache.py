"""Cache TTL and freshness tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from personalizer.services import cache


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "x.json"
    cache.write(p, {"hello": "world"})
    data = cache.read(p)
    assert data is not None
    assert data["hello"] == "world"
    assert "fetched_at" in data


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert cache.read(tmp_path / "nope.json") is None


def test_read_corrupt_returns_none(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert cache.read(p) is None


def test_is_fresh_within_ttl(tmp_path: Path) -> None:
    p = tmp_path / "fresh.json"
    cache.write(p, {"k": "v"})
    data = cache.read(p)
    assert cache.is_fresh(data, timedelta(hours=1))


def test_is_fresh_expired() -> None:
    old_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert not cache.is_fresh({"fetched_at": old_iso}, timedelta(hours=1))


def test_is_fresh_handles_missing_field() -> None:
    assert not cache.is_fresh({"k": "v"}, timedelta(hours=1))
    assert not cache.is_fresh(None, timedelta(hours=1))


def test_is_today_true_for_now(tmp_path: Path) -> None:
    p = tmp_path / "t.json"
    cache.write(p, {"word": "x"})
    data = cache.read(p)
    assert cache.is_today(data)


def test_is_today_false_for_yesterday() -> None:
    yesterday = (datetime.now().astimezone() - timedelta(days=1)).isoformat()
    assert not cache.is_today({"fetched_at": yesterday})

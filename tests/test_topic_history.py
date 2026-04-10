"""Tests for the 7-day topic history exclusion."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from personalizer.services import openai_topic


def _write_history(path: Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries), encoding="utf-8")


def test_load_recent_topics_empty_file(tmp_path: Path) -> None:
    assert openai_topic.load_recent_topics(tmp_path / "missing.json") == []


def test_load_recent_topics_returns_within_window(tmp_path: Path) -> None:
    p = tmp_path / "h.json"
    now = datetime.now(timezone.utc)
    _write_history(
        p,
        [
            {"topic": "Event Loop", "fetched_at": (now - timedelta(days=1)).isoformat()},
            {"topic": "B-Tree", "fetched_at": (now - timedelta(days=3)).isoformat()},
            {"topic": "Quicksort", "fetched_at": (now - timedelta(days=6)).isoformat()},
        ],
    )
    topics = openai_topic.load_recent_topics(p)
    assert set(topics) == {"Event Loop", "B-Tree", "Quicksort"}


def test_load_recent_topics_prunes_older_than_7_days(tmp_path: Path) -> None:
    p = tmp_path / "h.json"
    now = datetime.now(timezone.utc)
    _write_history(
        p,
        [
            {"topic": "Recent", "fetched_at": (now - timedelta(days=2)).isoformat()},
            {"topic": "Stale", "fetched_at": (now - timedelta(days=8)).isoformat()},
            {"topic": "Ancient", "fetched_at": (now - timedelta(days=30)).isoformat()},
        ],
    )
    topics = openai_topic.load_recent_topics(p)
    assert topics == ["Recent"]


def test_record_topic_appends_and_persists(tmp_path: Path) -> None:
    p = tmp_path / "h.json"
    openai_topic.record_topic("Event Loop", path=p)
    openai_topic.record_topic("B-Tree", path=p)
    topics = openai_topic.load_recent_topics(p)
    assert topics == ["Event Loop", "B-Tree"]


def test_record_topic_prunes_stale_on_write(tmp_path: Path) -> None:
    p = tmp_path / "h.json"
    now = datetime.now(timezone.utc)
    _write_history(
        p,
        [
            {"topic": "Stale", "fetched_at": (now - timedelta(days=10)).isoformat()},
            {"topic": "Fresh", "fetched_at": (now - timedelta(days=1)).isoformat()},
        ],
    )
    openai_topic.record_topic("New", path=p)
    topics = openai_topic.load_recent_topics(p)
    assert "Stale" not in topics
    assert "Fresh" in topics
    assert "New" in topics


def test_load_recent_topics_handles_corrupt_file(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert openai_topic.load_recent_topics(p) == []


def test_build_user_prompt_includes_avoid_list() -> None:
    prompt = openai_topic._build_user_prompt(["Event Loop", "B-Tree"])
    assert "Event Loop" in prompt
    assert "B-Tree" in prompt
    assert "Do NOT" in prompt


def test_build_user_prompt_no_avoid_when_empty() -> None:
    prompt = openai_topic._build_user_prompt([])
    assert "Do NOT" not in prompt

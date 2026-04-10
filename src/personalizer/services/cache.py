"""Tiny JSON cache with TTL helpers.

Used by topic and word services to avoid hitting external APIs every tick.
Each cached value is stored as a JSON object with a `fetched_at` ISO timestamp.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


def read(path: Path) -> dict[str, Any] | None:
    """Return the cached dict, or None if missing/corrupt."""
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def write(path: Path, payload: dict[str, Any]) -> None:
    """Write payload to disk, stamping with `fetched_at` (UTC ISO)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = {**payload, "fetched_at": _now().isoformat()}
    with path.open("w", encoding="utf-8") as f:
        json.dump(stamped, f, indent=2)


def is_fresh(payload: dict[str, Any] | None, ttl: timedelta) -> bool:
    """Return True if payload was fetched within the last `ttl`."""
    if not payload or "fetched_at" not in payload:
        return False
    try:
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (TypeError, ValueError):
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return _now() - fetched < ttl


def is_today(payload: dict[str, Any] | None) -> bool:
    """Return True if payload was fetched on the current local date."""
    if not payload or "fetched_at" not in payload:
        return False
    try:
        fetched = datetime.fromisoformat(payload["fetched_at"])
    except (TypeError, ValueError):
        return False
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return fetched.astimezone().date() == datetime.now().astimezone().date()

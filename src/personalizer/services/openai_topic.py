"""Hourly learning topic via OpenAI.

Calls Chat Completions with a JSON-mode prompt that returns
{topic, explanation}. Caches the response to avoid re-fetching within the hour.

Also keeps a 7-day rolling history of recently shown topics, which is passed
back to the model as a "do not repeat" list so the user sees fresh material
across the week.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import paths
from . import cache

HISTORY_WINDOW = timedelta(days=7)

DEFAULT_EXPERIENCE = "senior software engineer with 8+ years of experience"
DEFAULT_AREAS: list[str] = [
    "system design",
    "data structures and algorithms",
    "backend engineering",
]


def _build_system_prompt(experience_level: str, topic_areas: list[str]) -> str:
    areas_text = "; ".join(topic_areas) if topic_areas else "software engineering"
    return (
        f"You are a concise tech educator writing for a {experience_level}. "
        f"Pick topics ONLY from these areas: {areas_text}. "
        "Skip beginner material — assume the reader already knows fundamentals "
        "and is looking for depth, edge cases, trade-offs, or advanced patterns. "
        "Return JSON with three fields:\n"
        '  "topic" — a short concept name (1-4 words).\n'
        '  "explanation" — about 300 characters in 2-4 sentences, covering what it is, '
        "why it matters, and one practical insight or trade-off.\n"
        '  "vocab" — an array of EXACTLY 2 objects {"word", "meaning"}, where each '
        "word is pulled VERBATIM from your explanation above (pick the two most "
        "noteworthy or jargony terms that a learner might not already know), and "
        '"meaning" is a plain-English definition of 8-15 words.\n'
        "Pick a fresh, varied concept each time. No preamble, no markdown."
    )


def _build_user_prompt(recent_topics: list[str]) -> str:
    base = (
        "Give me a random concept to learn about right now. "
        "Pick something interesting that a senior engineer would find valuable."
    )
    if not recent_topics:
        return base
    avoid_list = ", ".join(f'"{t}"' for t in recent_topics)
    return (
        f"{base} Do NOT pick any of these recently shown topics or close synonyms: "
        f"{avoid_list}."
    )


class TopicUnavailable(Exception):
    pass


# ---- history helpers ----------------------------------------------------


def _read_history_raw(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict)]


def _prune(entries: list[dict[str, str]], now: datetime) -> list[dict[str, str]]:
    cutoff = now - HISTORY_WINDOW
    keep: list[dict[str, str]] = []
    for entry in entries:
        ts = entry.get("fetched_at")
        if not isinstance(ts, str):
            continue
        try:
            fetched = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        if fetched >= cutoff:
            keep.append(entry)
    return keep


def load_recent_topics(path: Path = paths.CACHE_TOPIC_HISTORY) -> list[str]:
    """Return topic names shown in the last 7 days, oldest-first."""
    now = datetime.now(timezone.utc)
    pruned = _prune(_read_history_raw(path), now)
    return [str(e["topic"]) for e in pruned if "topic" in e]


def record_topic(topic: str, path: Path = paths.CACHE_TOPIC_HISTORY) -> None:
    """Append a topic to history and rewrite the file with stale entries pruned."""
    now = datetime.now(timezone.utc)
    entries = _prune(_read_history_raw(path), now)
    entries.append({"topic": topic, "fetched_at": now.isoformat()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


# ---- API call -----------------------------------------------------------


def _parse_vocab(raw: Any) -> list[dict[str, str]]:
    """Coerce model output into a list of {word, meaning} dicts (max 2)."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        meaning = str(item.get("meaning", "")).strip()
        if word and meaning:
            out.append({"word": word, "meaning": meaning})
        if len(out) == 2:
            break
    return out


async def fetch_topic(
    api_key: str,
    model: str = "gpt-4o-mini",
    recent_topics: list[str] | None = None,
    experience_level: str = DEFAULT_EXPERIENCE,
    topic_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Call OpenAI and return {'topic', 'explanation', 'vocab'}."""
    if not api_key:
        raise TopicUnavailable("OPENAI_API_KEY is not set.")

    # Lazy import so the rest of the app loads without `openai` installed.
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    system_prompt = _build_system_prompt(experience_level, topic_areas or DEFAULT_AREAS)
    user_prompt = _build_user_prompt(recent_topics or [])
    try:
        resp = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0.9,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        raise TopicUnavailable(f"OpenAI call failed: {e}") from e

    content = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise TopicUnavailable(f"OpenAI returned non-JSON: {e}") from e

    topic = str(data.get("topic", "")).strip()
    explanation = str(data.get("explanation", "")).strip()
    if not topic or not explanation:
        raise TopicUnavailable("OpenAI response missing topic/explanation.")
    return {
        "topic": topic,
        "explanation": explanation,
        "vocab": _parse_vocab(data.get("vocab")),
    }


async def get_topic(
    api_key: str,
    model: str = "gpt-4o-mini",
    force: bool = False,
    experience_level: str = DEFAULT_EXPERIENCE,
    topic_areas: list[str] | None = None,
) -> dict[str, Any]:
    """Return the cached topic if fresh (<1h), else fetch a new one.

    Passes the last 7 days of topic names to OpenAI as a do-not-repeat list,
    and records each successful fetch in the history file. On API failure,
    falls back to the stale cache if available.
    """
    cached = cache.read(paths.CACHE_TOPIC)
    if not force and cache.is_fresh(cached, timedelta(hours=1)):
        return cached  # type: ignore[return-value]

    recent = load_recent_topics()
    try:
        fresh = await fetch_topic(
            api_key,
            model,
            recent_topics=recent,
            experience_level=experience_level,
            topic_areas=topic_areas,
        )
    except TopicUnavailable:
        if cached:
            return cached
        raise

    cache.write(paths.CACHE_TOPIC, fresh)
    record_topic(fresh["topic"])
    return cache.read(paths.CACHE_TOPIC) or fresh

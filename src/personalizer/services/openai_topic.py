"""Hourly learning topic via OpenAI.

Calls Chat Completions with a JSON-mode prompt that returns
{topic, explanation}. Caches the response to avoid re-fetching within the hour.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from .. import paths
from . import cache

_SYSTEM_PROMPT = (
    "You are a concise tech educator. Return JSON with two fields: "
    '"topic" (a short concept name, 1-4 words) and "explanation" '
    "(exactly 2 short sentences, each at most 120 characters). "
    "No preamble, no markdown."
)

_USER_PROMPT = (
    "Give me a random computer-science or software-engineering concept "
    "to learn about right now. Pick something interesting and not too obscure."
)


class TopicUnavailable(Exception):
    pass


async def fetch_topic(api_key: str, model: str = "gpt-4o-mini") -> dict[str, str]:
    """Call OpenAI and return {'topic': ..., 'explanation': ...}."""
    if not api_key:
        raise TopicUnavailable("OPENAI_API_KEY is not set.")

    # Lazy import so the rest of the app loads without `openai` installed.
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    try:
        resp = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            temperature=0.9,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _USER_PROMPT},
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
    return {"topic": topic, "explanation": explanation}


async def get_topic(
    api_key: str, model: str = "gpt-4o-mini", force: bool = False
) -> dict[str, Any]:
    """Return the cached topic if fresh (<1h), else fetch a new one.

    On API failure, falls back to the stale cache if available.
    """
    cached = cache.read(paths.CACHE_TOPIC)
    if not force and cache.is_fresh(cached, timedelta(hours=1)):
        return cached  # type: ignore[return-value]

    try:
        fresh = await fetch_topic(api_key, model)
    except TopicUnavailable:
        if cached:
            return cached
        raise

    cache.write(paths.CACHE_TOPIC, fresh)
    return cache.read(paths.CACHE_TOPIC) or fresh

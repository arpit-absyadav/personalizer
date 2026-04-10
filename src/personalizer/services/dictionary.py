"""Daily word service.

Random word from random-word-api.vercel.app, definition from dictionaryapi.dev.
Both are free and unauthenticated. random-word-api often returns obscure or
non-English words; we retry up to 5 times before falling back to a bundled list
of common-but-interesting words.
"""

from __future__ import annotations

from typing import Any

import httpx

from .. import paths
from . import cache

RANDOM_WORD_URL = "https://random-word-api.vercel.app/api?words=1"
DEFINITION_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
MAX_RETRIES = 5
MAX_DEFINITION_LEN = 80

# Curated fallback words — guaranteed to resolve in dictionaryapi.dev.
FALLBACK_WORDS = [
    "ephemeral",
    "ubiquitous",
    "serendipity",
    "ineffable",
    "petrichor",
    "halcyon",
    "luminous",
    "quintessential",
    "ethereal",
    "esoteric",
    "magnanimous",
    "perspicacious",
    "sonorous",
    "mellifluous",
    "tenacious",
    "intrepid",
    "sublime",
    "vicarious",
    "elucidate",
    "recalcitrant",
]


class WordUnavailable(Exception):
    pass


async def _random_word(client: httpx.AsyncClient) -> str:
    resp = await client.get(RANDOM_WORD_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        raise WordUnavailable("random-word-api returned empty payload")
    return str(data[0]).strip().lower()


async def _definition(client: httpx.AsyncClient, word: str) -> str | None:
    resp = await client.get(DEFINITION_URL.format(word=word), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    try:
        meaning = data[0]["meanings"][0]["definitions"][0]["definition"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(meaning, str) or not meaning.strip():
        return None
    text = meaning.strip()
    if len(text) > MAX_DEFINITION_LEN:
        text = text[: MAX_DEFINITION_LEN - 1].rstrip() + "…"
    return text


async def fetch_word() -> dict[str, str]:
    """Try several random words; fall back to a bundled list. Returns {word, meaning}."""
    async with httpx.AsyncClient() as client:
        for _ in range(MAX_RETRIES):
            try:
                word = await _random_word(client)
            except (httpx.HTTPError, WordUnavailable):
                break  # random-word-api itself is down — go to fallback
            meaning = await _definition(client, word)
            if meaning:
                return {"word": word, "meaning": meaning}

        # Fallback list — try until one resolves.
        import random

        for word in random.sample(FALLBACK_WORDS, len(FALLBACK_WORDS)):
            try:
                meaning = await _definition(client, word)
            except httpx.HTTPError:
                continue
            if meaning:
                return {"word": word, "meaning": meaning}

    raise WordUnavailable("Could not fetch any word from APIs or fallback list.")


async def get_word(force: bool = False) -> dict[str, Any]:
    """Return cached word if fetched today, else fetch a new one.

    On API failure, falls back to the stale cache if available.
    """
    cached = cache.read(paths.CACHE_WORD)
    if not force and cache.is_today(cached):
        return cached  # type: ignore[return-value]

    try:
        fresh = await fetch_word()
    except WordUnavailable:
        if cached:
            return cached
        raise

    cache.write(paths.CACHE_WORD, fresh)
    return cache.read(paths.CACHE_WORD) or fresh

"""Daily word service.

Picks an intermediate-level (B2-C1 CEFR) English vocabulary word from a
curated list and fetches its definition from dictionaryapi.dev.

The list targets a learner who already speaks intermediate English and wants
to level up — words encountered in news articles, novels, and professional
writing, but not in casual day-to-day chat. Trivial words ("random", "weird",
"podcast") and obscure ones ("perspicacious", "sesquipedalian") are both
deliberately excluded.
"""

from __future__ import annotations

import random
from typing import Any

import httpx

from .. import paths
from . import cache

DEFINITION_URL = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
MAX_DEFINITION_LEN = 200

# Curated B2-C1 vocabulary for an intermediate-to-upper-intermediate learner.
# Every entry must resolve in dictionaryapi.dev.
INTERMEDIATE_WORDS = [
    "abate", "alleviate", "ambiguous", "ambivalent", "amend", "anomaly",
    "arbitrary", "articulate", "augment", "austere", "authentic", "benevolent",
    "brevity", "candid", "capricious", "censure", "coerce", "coherent",
    "compelling", "complacent", "comprehensive", "concede", "concur",
    "consensus", "conspicuous", "contemplate", "contend", "conundrum",
    "convoluted", "credible", "cynical", "debunk", "decisive", "deference",
    "deride", "deter", "didactic", "diligent", "disdain", "disparage",
    "dubious", "eclectic", "elusive", "eminent", "empathy", "endorse",
    "enigma", "ephemeral", "equivocal", "erudite", "evoke", "exacerbate",
    "exemplary", "facilitate", "fastidious", "fervent", "frugal", "futile",
    "hindrance", "immerse", "impede", "impeccable", "impetuous", "inadvertent",
    "incessant", "incisive", "indignant", "indispensable", "inevitable",
    "innocuous", "intrepid", "intricate", "intuitive", "juxtapose", "laconic",
    "lethargic", "lucid", "magnanimous", "meticulous", "mundane", "nebulous",
    "nonchalant", "notorious", "oblivious", "obscure", "ominous",
    "ostentatious", "paradigm", "paramount", "pertinent", "placate",
    "plausible", "poignant", "pragmatic", "prevalent", "profound", "prominent",
    "prudent", "quintessential", "rapport", "reconcile", "refute", "relinquish",
    "reproach", "resilient", "scrutinize", "serene", "skeptical", "somber",
    "sophisticated", "stoic", "succinct", "superfluous", "tactful", "tedious",
    "tenacious", "thorough", "transient", "trivial", "ubiquitous",
    "unprecedented", "vehement", "viable", "vigilant", "voracious", "wary",
    "zealous",
]


class WordUnavailable(Exception):
    pass


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


async def _definition(
    client: httpx.AsyncClient, word: str
) -> dict[str, str] | None:
    """Return {meaning, example} for `word`, or None if no usable entry exists.

    Walks every definition (across all parts of speech) so we can prefer one
    that has both a definition AND an example sentence. Falls back to the
    first definition-only entry if no example is available anywhere.
    """
    resp = await client.get(DEFINITION_URL.format(word=word), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or not data:
        return None

    fallback: dict[str, str] | None = None
    try:
        meanings = data[0].get("meanings", [])
    except (AttributeError, KeyError):
        return None

    for meaning_block in meanings:
        for defn in meaning_block.get("definitions", []):
            text = defn.get("definition")
            if not isinstance(text, str) or not text.strip():
                continue
            entry = {"meaning": _truncate(text, MAX_DEFINITION_LEN), "example": ""}
            example = defn.get("example")
            if isinstance(example, str) and example.strip():
                entry["example"] = _truncate(example, MAX_DEFINITION_LEN)
                return entry
            if fallback is None:
                fallback = entry

    return fallback


async def fetch_word() -> dict[str, str]:
    """Pick an intermediate word and fetch it. Returns {word, meaning, example}."""
    async with httpx.AsyncClient() as client:
        for word in random.sample(INTERMEDIATE_WORDS, len(INTERMEDIATE_WORDS)):
            try:
                entry = await _definition(client, word)
            except httpx.HTTPError:
                continue
            if entry:
                return {
                    "word": word,
                    "meaning": entry["meaning"],
                    "example": entry.get("example", ""),
                }
    raise WordUnavailable("Could not fetch a definition for any intermediate word.")


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

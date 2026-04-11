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


async def _example_via_openai(
    word: str, api_key: str, model: str = "gpt-4o-mini"
) -> str:
    """Ask OpenAI for one short example sentence. Returns '' on any failure.

    Used as a fallback when dictionaryapi.dev has no example for the word.
    Silent on errors — the caller treats an empty string as "no example".
    """
    if not api_key or not word:
        return ""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return ""

    client = AsyncOpenAI(api_key=api_key)
    prompt = (
        f'Write ONE simple natural English example sentence using the word "{word}". '
        "8 to 15 words. Demonstrate the word's meaning clearly in context. "
        "Reply with ONLY the sentence — no quotes, no preamble, no markdown."
    )
    try:
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.7,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:  # noqa: BLE001
        return ""

    text = (resp.choices[0].message.content or "").strip().strip('"').strip()
    if not text:
        return ""
    return _truncate(text, MAX_DEFINITION_LEN)


async def get_word(
    force: bool = False,
    openai_api_key: str = "",
    openai_model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    """Return cached word if fetched today, else fetch a new one.

    If the resulting entry has no example sentence and an OpenAI key is
    provided, generates one via OpenAI and persists it back to the cache so
    subsequent reads are instant. On dictionary API failure, falls back to
    the stale cache if available.
    """
    cached = cache.read(paths.CACHE_WORD)

    if not force and cache.is_today(cached) and cached:
        result: dict[str, Any] = cached
    else:
        try:
            fresh = await fetch_word()
        except WordUnavailable:
            if cached:
                result = cached
            else:
                raise
        else:
            cache.write(paths.CACHE_WORD, fresh)
            result = cache.read(paths.CACHE_WORD) or fresh

    # Backfill example sentence via OpenAI if dictionary didn't supply one.
    if not result.get("example") and openai_api_key and result.get("word"):
        example = await _example_via_openai(
            str(result["word"]), openai_api_key, openai_model
        )
        if example:
            result = {**result, "example": example}
            cache.write(paths.CACHE_WORD, result)

    return result

"""Filesystem paths used by Personalizer.

Resolves and creates the per-user state directory tree at ~/.personalizer/.
All paths are absolute Path objects.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path.home() / ".personalizer"

CONFIG_FILE = ROOT / "config.yaml"
ENV_FILE = ROOT / ".env"
LOG_FILE = ROOT / "personalizer.log"

GOOGLE_DIR = ROOT / "google"
GOOGLE_CREDENTIALS = GOOGLE_DIR / "credentials.json"
GOOGLE_TOKEN = GOOGLE_DIR / "token.json"

CACHE_DIR = ROOT / "cache"
CACHE_TOPIC = CACHE_DIR / "topic.json"
CACHE_TOPIC_HISTORY = CACHE_DIR / "topic_history.json"
CACHE_WORD = CACHE_DIR / "word.json"


def ensure_dirs() -> None:
    """Create the ~/.personalizer tree if missing. Idempotent."""
    ROOT.mkdir(parents=True, exist_ok=True)
    GOOGLE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

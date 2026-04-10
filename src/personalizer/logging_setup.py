"""Logging configuration — writes to ~/.personalizer/personalizer.log.

The Textual UI swallows widget errors into terse "(unavailable)" strings, so
the file log is the place to look for the real traceback when something fails.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from . import paths

LOGGER_NAME = "personalizer"
_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Attach a rotating file handler to the personalizer logger. Idempotent."""
    global _configured
    if _configured:
        return
    paths.ensure_dirs()
    handler = RotatingFileHandler(
        paths.LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True
    logger.info("logging initialised → %s", paths.LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the personalizer namespace."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")

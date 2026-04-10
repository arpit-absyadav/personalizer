"""Configuration loader.

Reads ~/.personalizer/config.yaml for user-editable settings and ~/.personalizer/.env
(plus shell env) for secrets like the OpenAI API key. Writes a default config.yaml
on first run so the user has something to edit.
"""

from __future__ import annotations

from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import paths


DEFAULT_TOPIC_AREAS = [
    "System design (HLD)",
    "Low-level design (LLD) and OOP patterns",
    "Data structures and algorithms",
    "Node.js and NestJS internals",
    "React and modern frontend architecture",
    "AI engineering (LLMs, RAG, agents, evals)",
    "Data engineering (pipelines, warehousing, streaming)",
    "Data analysis and analytics engineering",
    "DevOps (CI/CD, Kubernetes, observability)",
    "MLOps and AIOps",
    "Distributed systems and scalability",
    "Database internals and query optimization",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "reminders": [
        "Drink water",
        "Stretch",
        "20-20-20: look 20ft away for 20s",
        "Posture check",
        "Deep breath",
    ],
    "work_hours": {"start": "09:00", "end": "18:00"},
    "calendar": {"id": "primary", "lookahead_minutes": 60},
    "openai": {
        "model": "gpt-4o-mini",
        "experience_level": "senior software engineer with 8+ years of experience",
        "topic_areas": DEFAULT_TOPIC_AREAS,
    },
}


class WorkHours(BaseModel):
    start: str = "09:00"
    end: str = "18:00"


class CalendarConfig(BaseModel):
    id: str = "primary"
    lookahead_minutes: int = 60


class OpenAIConfig(BaseModel):
    model: str = "gpt-4o-mini"
    experience_level: str = "senior software engineer with 8+ years of experience"
    topic_areas: list[str] = Field(default_factory=lambda: list(DEFAULT_TOPIC_AREAS))


class AppConfig(BaseModel):
    reminders: list[str] = Field(default_factory=lambda: list(DEFAULT_CONFIG["reminders"]))
    work_hours: WorkHours = Field(default_factory=WorkHours)
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)


class Secrets(BaseSettings):
    """Secrets loaded from ~/.personalizer/.env or shell environment."""

    openai_api_key: str = ""

    model_config = SettingsConfigDict(
        env_file=str(paths.ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


def _write_default_config() -> None:
    paths.ensure_dirs()
    with paths.CONFIG_FILE.open("w", encoding="utf-8") as f:
        yaml.safe_dump(DEFAULT_CONFIG, f, sort_keys=False)


def load_config() -> AppConfig:
    """Load config.yaml, creating a default file if it doesn't exist."""
    paths.ensure_dirs()
    if not paths.CONFIG_FILE.exists():
        _write_default_config()
    with paths.CONFIG_FILE.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return AppConfig.model_validate(raw)


def load_secrets() -> Secrets:
    paths.ensure_dirs()
    return Secrets()

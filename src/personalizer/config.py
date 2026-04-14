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
    # -- AI / ML (deep) --
    "LLM internals (transformer architecture, attention heads, KV-cache, positional encoding, tokenization, BPE vs SentencePiece)",
    "Context windows and memory (sliding window, memory augmentation, retrieval-augmented generation, summarisation chains, long-context strategies)",
    "Hallucination (causes, detection, grounding techniques, factuality scoring, chain-of-verification)",
    "Prompt engineering (system/user/assistant roles, few-shot, chain-of-thought, ReAct, tree-of-thought, self-consistency)",
    "AI agents and agentic flows (tool use, function calling, planning loops, reflection, multi-agent orchestration, human-in-the-loop)",
    "RAG pipelines (chunking strategies, embedding models, vector stores, hybrid search, re-ranking, query rewriting)",
    "Fine-tuning and alignment (LoRA, QLoRA, RLHF, DPO, instruction tuning, catastrophic forgetting)",
    "Evaluation and evals (BLEU, ROUGE, LLM-as-judge, human evals, A/B testing prompts, red-teaming)",
    "ML fundamentals (gradient descent, backprop, regularisation, bias-variance, overfitting, cross-validation)",
    "Deep learning architectures (CNNs, RNNs, LSTMs, GANs, diffusion models, vision transformers)",
    "MLOps (experiment tracking, model registry, feature stores, model serving, drift detection, A/B deployment)",
    # -- Data Engineering --
    "Data engineering (batch vs streaming, ELT/ETL, data lakehouse, Spark internals, Kafka, Flink, dbt)",
    "Data modelling and warehousing (star schema, slowly changing dimensions, data vault, partitioning, materialised views)",
    "Data quality and observability (data contracts, great expectations, schema evolution, lineage, freshness SLAs)",
    "Data analysis and analytics engineering",
    # -- Infrastructure --
    "DevOps (CI/CD, Kubernetes, observability)",
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

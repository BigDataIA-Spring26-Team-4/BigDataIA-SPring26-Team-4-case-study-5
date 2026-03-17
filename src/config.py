"""
CS4 RAG & Search configuration.

Reads LLM provider settings from environment variables.
Completely separate from CS3's app/config.py to keep clean separation.

All model names and provider settings are configurable via env vars —
no hardcoded model names anywhere. Supports any LiteLLM-compatible provider:
  - OpenAI:    CS4_PRIMARY_MODEL=gpt-4o
  - Anthropic: CS4_PRIMARY_MODEL=claude-sonnet-4-20250514
  - Ollama:    CS4_PRIMARY_MODEL=ollama/llama3
  - Together:  CS4_PRIMARY_MODEL=together_ai/meta-llama/Llama-3-70b
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ModelConfig:
    """Configuration for a single model assignment."""
    primary: str
    fallbacks: List[str]
    temperature: float
    max_tokens: int


@dataclass
class CS4Settings:
    """
    CS4 configuration loaded entirely from environment variables.

    Env var reference:
      CS4_PRIMARY_MODEL          — Default model for most tasks
      CS4_FALLBACK_MODEL         — Fallback if primary fails
      CS4_EXTRACTION_MODEL       — Model for evidence extraction
      CS4_JUSTIFICATION_MODEL    — Model for justification generation
      CS4_CHAT_MODEL             — Model for chat / lightweight tasks
      CS4_DAILY_BUDGET_USD       — Daily spend limit (default 50)
      CS4_CHROMA_PERSIST_DIR     — ChromaDB data directory
      CS4_EMBEDDING_MODEL        — Sentence-transformers model name
      CS4_BM25_WEIGHT            — Sparse retrieval weight (default 0.4)
      CS4_DENSE_WEIGHT           — Dense retrieval weight (default 0.6)
      CS4_RRF_K                  — RRF fusion constant (default 60)
      CS4_CS3_API_URL            — Base URL for CS1/CS2/CS3 API
    """

    # ── LLM Provider Settings ───────────────────────────────────
    primary_model: str = ""
    fallback_model: str = ""
    extraction_model: str = ""
    justification_model: str = ""
    chat_model: str = ""
    daily_budget_usd: float = 50.0

    # ── Retrieval Settings ──────────────────────────────────────
    chroma_persist_dir: str = "./chroma_data"
    embedding_model: str = "all-MiniLM-L6-v2"
    bm25_weight: float = 0.4
    dense_weight: float = 0.6
    rrf_k: int = 60

    # ── Integration Settings ────────────────────────────────────
    cs3_api_url: str = "http://localhost:8000"

    def __post_init__(self):
        """Load values from environment, falling back to defaults."""
        default_model = os.getenv("CS4_PRIMARY_MODEL", "")
        default_fallback = os.getenv("CS4_FALLBACK_MODEL", "")

        self.primary_model = default_model
        self.fallback_model = default_fallback
        self.extraction_model = os.getenv("CS4_EXTRACTION_MODEL", default_model)
        self.justification_model = os.getenv("CS4_JUSTIFICATION_MODEL", default_model)
        self.chat_model = os.getenv("CS4_CHAT_MODEL", default_model)
        self.daily_budget_usd = float(os.getenv("CS4_DAILY_BUDGET_USD", "50.0"))

        self.chroma_persist_dir = os.getenv("CS4_CHROMA_PERSIST_DIR", "./chroma_data")
        self.embedding_model = os.getenv("CS4_EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.bm25_weight = float(os.getenv("CS4_BM25_WEIGHT", "0.4"))
        self.dense_weight = float(os.getenv("CS4_DENSE_WEIGHT", "0.6"))
        self.rrf_k = int(os.getenv("CS4_RRF_K", "60"))

        self.cs3_api_url = os.getenv("CS4_CS3_API_URL", "http://localhost:8000")

    def get_model_config(self, task_type: str) -> ModelConfig:
        """
        Get model configuration for a given task type.

        Reads task-specific model from env, falls back to primary/fallback.
        Returns ModelConfig with temperature and max_tokens tuned per task.
        """
        task_configs = {
            "evidence_extraction": ModelConfig(
                primary=self.extraction_model,
                fallbacks=[self.fallback_model] if self.fallback_model else [],
                temperature=0.3,
                max_tokens=4000,
            ),
            "justification_generation": ModelConfig(
                primary=self.justification_model,
                fallbacks=[self.fallback_model] if self.fallback_model else [],
                temperature=0.2,
                max_tokens=2000,
            ),
            "chat_response": ModelConfig(
                primary=self.chat_model,
                fallbacks=[self.fallback_model] if self.fallback_model else [],
                temperature=0.7,
                max_tokens=1000,
            ),
            "hyde_generation": ModelConfig(
                primary=self.chat_model,
                fallbacks=[self.fallback_model] if self.fallback_model else [],
                temperature=0.7,
                max_tokens=500,
            ),
        }

        config = task_configs.get(task_type)
        if config is None:
            config = ModelConfig(
                primary=self.primary_model,
                fallbacks=[self.fallback_model] if self.fallback_model else [],
                temperature=0.5,
                max_tokens=2000,
            )

        return config

    @property
    def is_llm_configured(self) -> bool:
        """Check if at least one LLM provider is configured."""
        return bool(self.primary_model)

    @property
    def provider_summary(self) -> Dict[str, str]:
        """Summary of configured providers for health checks."""
        return {
            "primary": self.primary_model or "(not set)",
            "fallback": self.fallback_model or "(not set)",
            "extraction": self.extraction_model or "(not set)",
            "justification": self.justification_model or "(not set)",
            "chat": self.chat_model or "(not set)",
            "embedding": self.embedding_model,
        }


def get_cs4_settings() -> CS4Settings:
    """Factory function — creates settings from current environment."""
    return CS4Settings()

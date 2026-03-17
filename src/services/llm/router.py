"""
Multi-model routing with LiteLLM and streaming support.

Task 7.1: Multi-Provider LLM Router.
Single-provider dependency creates risk. LiteLLM provides a unified API
to 100+ providers with automatic fallbacks and cost tracking.

All model names come from CS4Settings (environment variables).
Supports: OpenAI, Anthropic, Ollama, Together, Groq, and any
LiteLLM-compatible provider — swap with a single env var change.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncIterator, Dict, List

import structlog

from src.config import CS4Settings, get_cs4_settings

logger = structlog.get_logger()


# ============================================================================
# Task Types
# ============================================================================


class TaskType(str, Enum):
    """LLM task types — each maps to a model config via CS4Settings."""
    EVIDENCE_EXTRACTION = "evidence_extraction"
    JUSTIFICATION_GENERATION = "justification_generation"
    CHAT_RESPONSE = "chat_response"
    HYDE_GENERATION = "hyde_generation"


# ============================================================================
# Daily Budget Tracker
# ============================================================================


class DailyBudget:
    """
    Track daily LLM spend to prevent runaway costs.

    Resets at midnight automatically. Limit configurable via
    CS4_DAILY_BUDGET_USD env var (default $50).
    """

    def __init__(self, limit_usd: float = 50.0):
        self._date = date.today()
        self._spent = Decimal("0")
        self._limit = Decimal(str(limit_usd))

    def _maybe_reset(self):
        """Reset counter if day has changed."""
        today = date.today()
        if self._date != today:
            self._date = today
            self._spent = Decimal("0")

    def can_spend(self, amount: float) -> bool:
        """Check if we can afford this request."""
        self._maybe_reset()
        return self._spent + Decimal(str(amount)) <= self._limit

    def record_spend(self, amount: float):
        """Record a completed spend."""
        self._maybe_reset()
        self._spent += Decimal(str(amount))

    @property
    def remaining(self) -> float:
        """Remaining budget for today."""
        self._maybe_reset()
        return float(self._limit - self._spent)

    @property
    def spent_today(self) -> float:
        """Amount spent today."""
        self._maybe_reset()
        return float(self._spent)


# ============================================================================
# Model Router
# ============================================================================


class ModelRouter:
    """
    Route LLM requests with fallbacks and cost tracking.

    Usage:
        router = ModelRouter()
        response = await router.complete(
            task=TaskType.JUSTIFICATION_GENERATION,
            messages=[{"role": "user", "content": "..."}],
        )

    All model names are resolved from environment variables at runtime.
    If no LLM is configured, raises a clear error.
    """

    def __init__(self, settings: CS4Settings = None):
        self._settings = settings or get_cs4_settings()
        self._budget = DailyBudget(limit_usd=self._settings.daily_budget_usd)

    @property
    def is_configured(self) -> bool:
        """Whether at least one LLM provider is configured."""
        return self._settings.is_llm_configured

    async def complete(
        self,
        task: TaskType,
        messages: List[Dict[str, str]],
        stream: bool = False,
        **kwargs,
    ) -> Any:
        """
        Route a completion request with automatic fallbacks.

        Tries the primary model first, then each fallback in order.
        Tracks cost against the daily budget.

        Args:
            task: Task type (determines model selection, temperature, etc.)
            messages: Chat messages in OpenAI format
            stream: If True, returns an async iterator of string chunks
            **kwargs: Additional args passed to litellm.acompletion

        Returns:
            LiteLLM response object (or async iterator if stream=True)

        Raises:
            RuntimeError: If no LLM is configured or all models fail
        """
        if not self.is_configured:
            raise RuntimeError(
                "No LLM provider configured. Set CS4_PRIMARY_MODEL env var. "
                "Examples: 'gpt-4o', 'claude-sonnet-4-20250514', 'ollama/llama3'"
            )

        config = self._settings.get_model_config(task.value)
        models_to_try = [config.primary] + config.fallbacks
        # Filter out empty strings
        models_to_try = [m for m in models_to_try if m]

        if not models_to_try:
            raise RuntimeError(
                f"No model configured for task '{task.value}'. "
                f"Set CS4_PRIMARY_MODEL or task-specific env var."
            )

        last_error = None
        for model in models_to_try:
            try:
                if stream:
                    return self._stream_complete(model, messages, config, **kwargs)

                response = await self._single_complete(
                    model, messages, config, **kwargs
                )
                logger.info(
                    "llm_complete",
                    model=model,
                    task=task.value,
                    budget_remaining=self._budget.remaining,
                )
                return response

            except Exception as e:
                last_error = e
                logger.warning(
                    "model_failed",
                    model=model,
                    task=task.value,
                    error=str(e),
                )

        raise RuntimeError(
            f"All models failed for task '{task.value}'. "
            f"Tried: {models_to_try}. Last error: {last_error}"
        )

    async def _single_complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        config: Any,
        **kwargs,
    ) -> Any:
        """Execute a single (non-streaming) completion."""
        import litellm
        from litellm import acompletion

        # Estimate cost for budget check (rough: $0.01 per request)
        estimated_cost = 0.01
        if not self._budget.can_spend(estimated_cost):
            raise RuntimeError(
                f"Daily budget exhausted. "
                f"Spent: ${self._budget.spent_today:.2f}, "
                f"Limit: ${self._settings.daily_budget_usd:.2f}"
            )

        response = await acompletion(
            model=model,
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            **kwargs,
        )

        # Track actual cost if available
        actual_cost = getattr(response, "_hidden_params", {}).get(
            "response_cost", estimated_cost
        )
        self._budget.record_spend(float(actual_cost) if actual_cost else estimated_cost)

        return response

    async def _stream_complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        config: Any,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Execute a streaming completion, yielding text chunks."""
        from litellm import acompletion

        response = await acompletion(
            model=model,
            messages=messages,
            stream=True,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            **kwargs,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def get_status(self) -> Dict[str, Any]:
        """Return router health/status for API endpoints."""
        return {
            "configured": self.is_configured,
            "providers": self._settings.provider_summary,
            "budget": {
                "spent_today": self._budget.spent_today,
                "remaining": self._budget.remaining,
                "limit": self._settings.daily_budget_usd,
            },
        }

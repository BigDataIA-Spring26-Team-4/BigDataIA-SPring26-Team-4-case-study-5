"""
CS5 Configuration — service URLs for CS1-CS4 backends.
"""

import sys
import logging

from pydantic_settings import BaseSettings
from pathlib import Path
import structlog


# ── CRITICAL: Redirect ALL logging to stderr ────────────────────
# MCP stdio transport uses stdout for JSON-RPC only.
# Any stdout writes (from structlog, print, etc.) corrupt the protocol.
# This MUST run before any logger.info() calls anywhere.

logging.basicConfig(
    format="%(message)s",
    stream=sys.stderr,
    level=logging.INFO,
)

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    cache_logger_on_first_use=True,
)


class Settings(BaseSettings):
    # CS1, CS2, CS3 all run on the same FastAPI app (port 8000)
    CS1_URL: str = "http://localhost:8000"
    CS2_URL: str = "http://localhost:8000"
    CS3_URL: str = "http://localhost:8000"
    # CS4 justification/search also on the same app (port 8000)
    CS4_URL: str = "http://localhost:8000"

    # MCP server URL (for agent tool calls — Lab 10)
    MCP_SERVER_URL: str = "http://localhost:3000"

    # OpenAI / Anthropic keys (for LangGraph agents in Lab 10)
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    model_config = {
        "env_file": str(Path(__file__).parent / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

"""
CS2 Client — Evidence collection from CS2 APIs.

Wraps CS2 FastAPI endpoints (port 8000).
Provides the CS5-expected signature: get_evidence(company_id, dimension, limit).
NO mock data — errors propagate if CS2 is down.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger()


# ── Enums & Dataclasses ────────────────────────────────────────


class SourceType(str, Enum):
    SEC_10K_ITEM_1 = "sec_10k_item_1"
    SEC_10K_ITEM_1A = "sec_10k_item_1a"
    SEC_10K_ITEM_7 = "sec_10k_item_7"
    JOB_POSTING_INDEED = "job_posting_indeed"
    PATENT_USPTO = "patent_uspto"
    GLASSDOOR_REVIEW = "glassdoor_review"
    BOARD_PROXY_DEF14A = "board_proxy_def14a"
    NEWS_ARTICLE = "news_article"
    PRESS_RELEASE = "press_release"


@dataclass
class Evidence:
    """Single evidence item from CS2."""
    evidence_id: str
    company_id: str
    source_type: SourceType
    signal_category: str
    content: str
    confidence: float


# Dimension → signal categories mapping (for CS5 filtering)
_DIMENSION_TO_CATEGORIES = {
    "data_infrastructure": ["digital_presence", "innovation_activity"],
    "ai_governance": ["governance_signals"],
    "technology_stack": ["digital_presence", "innovation_activity"],
    "talent": ["technology_hiring"],
    "leadership": ["leadership_signals"],
    "use_case_portfolio": ["innovation_activity"],
    "culture": ["culture_signals"],
}


class CS2Client:
    """Client for CS2 Evidence Collection APIs (port 8000)."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)

    async def get_evidence(
        self,
        company_id: str,
        dimension: str = "all",
        limit: int = 10,
    ) -> List[Evidence]:
        """
        Fetch evidence for a company, optionally filtered by dimension.

        CS5 wrapper signature per gap analysis.
        Internally resolves ticker → UUID, then fetches docs + signals.
        """
        ticker = company_id.upper()

        # Step 1: Resolve ticker → Snowflake UUID
        uuid = await self._resolve_ticker(ticker)
        if not uuid:
            raise ValueError(f"Could not resolve ticker '{ticker}' to company_id")

        evidence_list: List[Evidence] = []

        # Step 2: Fetch document chunks (SEC filings)
        doc_evidence = await self._fetch_document_evidence(ticker, uuid)
        evidence_list.extend(doc_evidence)

        # Step 3: Fetch signal evidence (jobs, patents, glassdoor, etc.)
        signal_evidence = await self._fetch_signal_evidence(ticker, uuid)
        evidence_list.extend(signal_evidence)

        # Step 4: Filter by dimension if not "all"
        if dimension != "all" and dimension in _DIMENSION_TO_CATEGORIES:
            allowed_cats = set(_DIMENSION_TO_CATEGORIES[dimension])
            evidence_list = [
                e for e in evidence_list if e.signal_category in allowed_cats
            ]

        # Step 5: Apply limit
        return evidence_list[:limit]

    async def close(self):
        await self._client.aclose()

    # ── Internal: Ticker Resolution ─────────────────────────────

    async def _resolve_ticker(self, ticker: str) -> Optional[str]:
        """Resolve ticker → Snowflake UUID via CS1 company endpoint."""
        response = await self._client.get(
            f"/api/v1/companies/by-ticker/{ticker}"
        )
        response.raise_for_status()
        data = response.json()
        return data.get("company_id") or data.get("id")

    # ── Internal: Document Evidence ─────────────────────────────

    async def _fetch_document_evidence(
        self, ticker: str, uuid: str
    ) -> List[Evidence]:
        """Fetch SEC filing chunks as evidence items."""
        evidence: List[Evidence] = []

        response = await self._client.get(
            "/api/v1/documents",
            params={"company_id": uuid, "limit": 50},
        )
        response.raise_for_status()
        documents = response.json()

        for doc in documents:
            doc_id = doc["id"]

            # Fetch chunks for this document
            try:
                chunk_resp = await self._client.get(
                    f"/api/v1/documents/{doc_id}/chunks"
                )
                chunk_resp.raise_for_status()
                chunks = chunk_resp.json()
            except httpx.HTTPError:
                continue

            for i, chunk in enumerate(chunks):
                content = chunk.get("content", "")
                if len(content.strip()) < 50:
                    continue

                section = (chunk.get("section") or "").lower().strip()
                source_type = self._section_to_source(section)
                signal_cat = self._source_to_category(source_type)

                evidence.append(Evidence(
                    evidence_id=chunk.get("id", f"{doc_id}_{i}"),
                    company_id=ticker,
                    source_type=source_type,
                    signal_category=signal_cat,
                    content=content,
                    confidence=0.85,
                ))

        return evidence

    # ── Internal: Signal Evidence ───────────────────────────────

    async def _fetch_signal_evidence(
        self, ticker: str, uuid: str
    ) -> List[Evidence]:
        """Fetch external signals (jobs, patents, glassdoor, etc.)."""
        evidence: List[Evidence] = []

        response = await self._client.get(
            "/api/v1/signals",
            params={"company_id": uuid, "limit": 200},
        )
        response.raise_for_status()
        signals = response.json()

        for i, sig in enumerate(signals):
            source = sig.get("source", "")
            category = sig.get("category", "leadership_signals")
            raw_value = sig.get("raw_value", "")
            metadata = sig.get("metadata", {}) or {}

            # Build content from raw_value + metadata
            parts = [raw_value] if raw_value else []
            for key, val in metadata.items():
                if isinstance(val, (str, int, float)) and val:
                    parts.append(f"{key}: {val}")
            content = " | ".join(parts)

            if len(content.strip()) < 10:
                continue

            source_type = self._signal_source_to_type(source)

            evidence.append(Evidence(
                evidence_id=sig.get("id", f"sig_{ticker}_{i}"),
                company_id=ticker,
                source_type=source_type,
                signal_category=category,
                content=content,
                confidence=float(sig.get("confidence", 0.7)),
            ))

        return evidence

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _section_to_source(section: str) -> SourceType:
        mapping = {
            "item_1": SourceType.SEC_10K_ITEM_1,
            "item_1a": SourceType.SEC_10K_ITEM_1A,
            "item_7": SourceType.SEC_10K_ITEM_7,
        }
        return mapping.get(section, SourceType.SEC_10K_ITEM_7)

    @staticmethod
    def _source_to_category(source_type: SourceType) -> str:
        mapping = {
            SourceType.SEC_10K_ITEM_1: "digital_presence",
            SourceType.SEC_10K_ITEM_1A: "governance_signals",
            SourceType.SEC_10K_ITEM_7: "leadership_signals",
            SourceType.JOB_POSTING_INDEED: "technology_hiring",
            SourceType.PATENT_USPTO: "innovation_activity",
            SourceType.GLASSDOOR_REVIEW: "culture_signals",
            SourceType.BOARD_PROXY_DEF14A: "governance_signals",
            SourceType.NEWS_ARTICLE: "leadership_signals",
        }
        return mapping.get(source_type, "leadership_signals")

    @staticmethod
    def _signal_source_to_type(source: str) -> SourceType:
        mapping = {
            "indeed": SourceType.JOB_POSTING_INDEED,
            "glassdoor": SourceType.GLASSDOOR_REVIEW,
            "patentsview": SourceType.PATENT_USPTO,
            "company_website": SourceType.BOARD_PROXY_DEF14A,
            "news_press_releases": SourceType.NEWS_ARTICLE,
        }
        return mapping.get(source, SourceType.PRESS_RELEASE)

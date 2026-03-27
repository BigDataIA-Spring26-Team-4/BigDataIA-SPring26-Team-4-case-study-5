"""
CS3 Client — Scoring engine from CS3 APIs.

Wraps CS3 FastAPI endpoints (port 8000).
Returns typed CompanyAssessment matching CS5 PDF Section 1.2.
NO mock data — errors propagate if CS3 is down.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple

import httpx
import structlog

logger = structlog.get_logger()


# ── Enums & Dataclasses (per CS5 PDF Section 1.2) ──────────────


class Dimension(str, Enum):
    DATA_INFRASTRUCTURE = "data_infrastructure"
    AI_GOVERNANCE = "ai_governance"
    TECHNOLOGY_STACK = "technology_stack"
    TALENT = "talent"
    LEADERSHIP = "leadership"
    USE_CASE_PORTFOLIO = "use_case_portfolio"
    CULTURE = "culture"


@dataclass
class DimensionScore:
    """Score for a single dimension."""
    dimension: Dimension
    score: float
    level: int
    evidence_count: int


@dataclass
class CompanyAssessment:
    """Full company assessment from CS3 — matches PDF Section 1.2."""
    company_id: str
    org_air_score: float
    vr_score: float
    hr_score: float
    synergy_score: float
    dimension_scores: Dict[Dimension, DimensionScore]
    confidence_interval: Tuple[float, float]
    evidence_count: int


def _score_to_level(score: float) -> int:
    """Convert numeric score to L1-L5."""
    if score >= 80:
        return 5
    elif score >= 60:
        return 4
    elif score >= 40:
        return 3
    elif score >= 20:
        return 2
    return 1


class CS3Client:
    """Client for CS3 Scoring Engine APIs (port 8000)."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=60.0)

    async def get_assessment(self, company_id: str) -> CompanyAssessment:
        """
        Fetch complete assessment for a company.

        Calls: POST /api/v1/pipeline/score {"ticker": "<TICKER>"}
        Returns typed CompanyAssessment with all fields CS5 needs.
        """
        ticker = company_id.upper()

        response = await self._client.post(
            "/api/v1/pipeline/score",
            json={"ticker": ticker},
        )
        response.raise_for_status()
        data = response.json()

        return self._parse_assessment(ticker, data)

    async def close(self):
        await self._client.aclose()

    # ── Parsing ─────────────────────────────────────────────────

    def _parse_assessment(self, ticker: str, data: dict) -> CompanyAssessment:
        """Parse CS3 pipeline/score response into CompanyAssessment."""
        raw_dims = data.get("dimension_scores", {})
        evidence_count = data.get("evidence_count", 0)
        dim_count = max(len(raw_dims), 1)

        dimension_scores: Dict[Dimension, DimensionScore] = {}
        for dim_key, score_val in raw_dims.items():
            try:
                dim = Dimension(dim_key)
            except ValueError:
                continue

            score = float(score_val)
            dimension_scores[dim] = DimensionScore(
                dimension=dim,
                score=score,
                level=_score_to_level(score),
                evidence_count=evidence_count // dim_count,
            )

        return CompanyAssessment(
            company_id=ticker,
            org_air_score=float(data.get("final_score", 0)),
            vr_score=float(data.get("vr_score", 0)),
            hr_score=float(data.get("hr_score", 0)),
            synergy_score=float(data.get("synergy_score", 0)),
            dimension_scores=dimension_scores,
            confidence_interval=(
                float(data.get("ci_lower", 0)),
                float(data.get("ci_upper", 0)),
            ),
            evidence_count=evidence_count,
        )

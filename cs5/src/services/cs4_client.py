"""
CS4 Client — RAG search & justifications from CS4 API.

Wraps CS4 FastAPI endpoints (port 8000 — same app as CS1/CS2/CS3).
NO mock data — errors propagate if the API is down.

Actual endpoints (from app/routers/justification.py & search.py):
  GET /api/v1/justification/{company_id}/{dimension}
  GET /api/v1/ic-prep/{company_id}
  GET /api/v1/search?q=...&company_id=...&dimension=...&top_k=...
"""

from dataclasses import dataclass
from typing import List, Optional

import httpx
import structlog

logger = structlog.get_logger()


# ── Dataclasses ─────────────────────────────────────────────────


@dataclass
class CitedEvidence:
    """Single piece of cited evidence from CS4 RAG."""
    evidence_id: str
    content: str
    source_type: str
    source_url: Optional[str]
    confidence: float
    matched_keywords: List[str]
    relevance_score: float


@dataclass
class ScoreJustification:
    """Score justification from CS4 RAG — used by MCP tools & agents."""
    company_id: str
    dimension: str
    score: float
    level: int
    level_name: str
    confidence_interval: List[float]
    rubric_criteria: str
    rubric_keywords: List[str]
    supporting_evidence: List[CitedEvidence]
    gaps_identified: List[str]
    generated_summary: str
    evidence_strength: str


@dataclass
class ICPrepPackage:
    """IC meeting preparation package from CS4."""
    company_id: str
    company_name: str
    org_air_score: float
    vr_score: float
    hr_score: float
    executive_summary: str
    key_strengths: List[str]
    key_gaps: List[str]
    risk_factors: List[str]
    recommendation: str
    dimension_justifications: dict
    total_evidence_count: int
    avg_evidence_strength: str


class CS4Client:
    """
    Client for CS4 RAG API.

    In our project, CS4 runs on the SAME FastAPI app as CS1/CS2/CS3
    (all on port 8000). The PDF mentions port 8003 but our Docker
    compose runs a single 'api' service.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def generate_justification(
        self, company_id: str, dimension: str
    ) -> ScoreJustification:
        """
        Generate evidence-backed justification for a dimension.

        Calls: GET /api/v1/justification/{company_id}/{dimension}
        (from app/routers/justification.py)
        """
        ticker = company_id.upper()
        # Handle Dimension enum or string
        dim_value = dimension.value if hasattr(dimension, "value") else dimension

        response = await self._client.get(
            f"/api/v1/justification/{ticker}/{dim_value}"
        )
        response.raise_for_status()
        data = response.json()

        return ScoreJustification(
            company_id=data.get("company_id", ticker),
            dimension=data.get("dimension", dim_value),
            score=float(data.get("score", 0)),
            level=int(data.get("level", 1)),
            level_name=data.get("level_name", "Unknown"),
            confidence_interval=data.get("confidence_interval", [0, 0]),
            rubric_criteria=data.get("rubric_criteria", ""),
            rubric_keywords=data.get("rubric_keywords", []),
            supporting_evidence=[
                CitedEvidence(
                    evidence_id=e.get("evidence_id", ""),
                    content=e.get("content", ""),
                    source_type=e.get("source_type", ""),
                    source_url=e.get("source_url"),
                    confidence=float(e.get("confidence", 0)),
                    matched_keywords=e.get("matched_keywords", []),
                    relevance_score=float(e.get("relevance_score", 0)),
                )
                for e in data.get("supporting_evidence", [])
            ],
            gaps_identified=data.get("gaps_identified", []),
            generated_summary=data.get("generated_summary", ""),
            evidence_strength=data.get("evidence_strength", "unknown"),
        )

    async def search_evidence(
        self,
        query: str,
        company_id: Optional[str] = None,
        dimension: Optional[str] = None,
        top_k: int = 10,
    ) -> List[dict]:
        """
        Search evidence via CS4 hybrid search.

        Calls: GET /api/v1/search?q=...&company_id=...&dimension=...&top_k=...
        (from app/routers/search.py — note: param is 'q' not 'query',
         and 'company_id' not 'company')
        """
        params: dict = {"q": query, "top_k": top_k}
        if company_id:
            params["company_id"] = company_id.upper()
        if dimension:
            dim_value = dimension.value if hasattr(dimension, "value") else dimension
            params["dimension"] = dim_value

        response = await self._client.get("/api/v1/search", params=params)
        response.raise_for_status()
        return response.json().get("results", [])

    async def prepare_ic_meeting(self, company_id: str) -> ICPrepPackage:
        """
        Prepare IC meeting package.

        Calls: GET /api/v1/ic-prep/{company_id}
        (from app/routers/justification.py)
        """
        ticker = company_id.upper()
        response = await self._client.get(f"/api/v1/ic-prep/{ticker}")
        response.raise_for_status()
        data = response.json()

        return ICPrepPackage(
            company_id=data.get("company_id", ticker),
            company_name=data.get("company_name", ticker),
            org_air_score=float(data.get("org_air_score", 0)),
            vr_score=float(data.get("vr_score", 0)),
            hr_score=float(data.get("hr_score", 0)),
            executive_summary=data.get("executive_summary", ""),
            key_strengths=data.get("key_strengths", []),
            key_gaps=data.get("key_gaps", []),
            risk_factors=data.get("risk_factors", []),
            recommendation=data.get("recommendation", ""),
            dimension_justifications=data.get("dimension_justifications", {}),
            total_evidence_count=int(data.get("total_evidence_count", 0)),
            avg_evidence_strength=data.get("avg_evidence_strength", "unknown"),
        )

    async def close(self):
        await self._client.aclose()

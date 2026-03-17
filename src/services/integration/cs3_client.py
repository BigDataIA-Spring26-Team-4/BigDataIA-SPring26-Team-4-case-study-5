"""
CS3 Scoring Engine API client.

Task 7.0c: Connect to CS3 Scoring Engine.
CS3 provides the scores and rubrics needed for justification:
  - Dimension scores: The actual 0-100 scores to justify
  - Rubric criteria: What each score level means
  - Rubric keywords: Terms to search for in evidence

Wraps the existing FastAPI pipeline/scoring/rubric endpoints.
Falls back to local results/*.json when the API is unavailable.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import httpx
import structlog

logger = structlog.get_logger()


# ============================================================================
# Enums (per CS4 PDF Section 4)
# ============================================================================


class Dimension(str, Enum):
    """The 7 V^R dimensions from CS3."""
    DATA_INFRASTRUCTURE = "data_infrastructure"
    AI_GOVERNANCE = "ai_governance"
    TECHNOLOGY_STACK = "technology_stack"
    TALENT = "talent"
    LEADERSHIP = "leadership"
    USE_CASE_PORTFOLIO = "use_case_portfolio"
    CULTURE = "culture"


class ScoreLevel(int, Enum):
    """Score levels with ranges."""
    LEVEL_5 = 5   # 80-100: Excellent
    LEVEL_4 = 4   # 60-79:  Good
    LEVEL_3 = 3   # 40-59:  Adequate
    LEVEL_2 = 2   # 20-39:  Developing
    LEVEL_1 = 1   # 0-19:   Nascent

    @property
    def name_label(self) -> str:
        labels = {5: "Excellent", 4: "Good", 3: "Adequate",
                  2: "Developing", 1: "Nascent"}
        return labels[self.value]

    @property
    def score_range(self) -> Tuple[int, int]:
        ranges = {5: (80, 100), 4: (60, 79), 3: (40, 59),
                  2: (20, 39), 1: (0, 19)}
        return ranges[self.value]


def score_to_level(score: float) -> ScoreLevel:
    """Convert a numeric score to its ScoreLevel."""
    if score >= 80:
        return ScoreLevel.LEVEL_5
    elif score >= 60:
        return ScoreLevel.LEVEL_4
    elif score >= 40:
        return ScoreLevel.LEVEL_3
    elif score >= 20:
        return ScoreLevel.LEVEL_2
    return ScoreLevel.LEVEL_1


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class DimensionScore:
    """Single dimension score from CS3."""
    dimension: Dimension
    score: float
    level: ScoreLevel
    confidence_interval: Tuple[float, float]   # (lower, upper)
    evidence_count: int
    last_updated: str


@dataclass
class RubricCriteria:
    """Rubric criteria for a dimension level."""
    dimension: Dimension
    level: ScoreLevel
    criteria_text: str
    keywords: List[str]
    quantitative_thresholds: Dict[str, float]


@dataclass
class CompanyAssessment:
    """Full company assessment from CS3."""
    company_id: str
    assessment_date: str

    # Composite scores
    vr_score: float
    hr_score: float
    synergy_score: float
    org_air_score: float

    # Confidence interval
    confidence_interval: Tuple[float, float]

    # Component scores
    dimension_scores: Dict[Dimension, DimensionScore]

    # Risk adjustments
    talent_concentration: float
    position_factor: float


# ============================================================================
# CS3 Client
# ============================================================================


class CS3Client:
    """
    Client for CS3 Scoring Engine API.

    Fetches scores from the pipeline/score endpoint and rubric data
    from the rubrics endpoint added in Phase 0.
    Falls back to results/*.json files when the API is unavailable.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    # ── Assessment Methods ──────────────────────────────────────

    async def get_assessment(self, company_id: str) -> CompanyAssessment:
        """
        Fetch complete assessment for a company.

        Tries API first (GET /api/v1/pipeline/evidence-summary/{ticker}),
        then falls back to local results/{ticker}.json.
        """
        ticker = company_id.upper()

        try:
            response = await self.client.get(
                f"{self.base_url}/api/v1/pipeline/evidence-summary/{ticker}"
            )
            response.raise_for_status()
            summary = response.json()

            # Also try to load the full scoring result
            result = self._load_local_result(ticker)
            if result:
                return self._parse_result_json(ticker, result)

            # If no local result, build from summary
            return self._parse_summary(ticker, summary)

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs3_api_unavailable", ticker=ticker, error=str(e))
            result = self._load_local_result(ticker)
            if result:
                return self._parse_result_json(ticker, result)
            raise ValueError(f"No scoring data available for '{ticker}'")

    async def get_dimension_score(
        self, company_id: str, dimension: Dimension
    ) -> DimensionScore:
        """Fetch single dimension score."""
        assessment = await self.get_assessment(company_id)
        if dimension not in assessment.dimension_scores:
            raise ValueError(
                f"Dimension '{dimension.value}' not found for '{company_id}'"
            )
        return assessment.dimension_scores[dimension]

    # ── Rubric Methods ──────────────────────────────────────────

    async def get_rubric(
        self,
        dimension: Dimension,
        level: Optional[ScoreLevel] = None,
    ) -> List[RubricCriteria]:
        """
        Fetch rubric criteria for a dimension.

        Calls: GET /api/v1/rubrics/{dimension}?level=...
        """
        try:
            params = {}
            if level:
                params["level"] = level.value

            response = await self.client.get(
                f"{self.base_url}/api/v1/rubrics/{dimension.value}",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            return [
                RubricCriteria(
                    dimension=dimension,
                    level=ScoreLevel(r["level"]),
                    criteria_text=f"Level {r['level']} ({r['level_name']}): "
                                  f"Requires {r['min_keyword_matches']}+ keyword matches "
                                  f"from: {', '.join(r['keywords'][:5])}",
                    keywords=r["keywords"],
                    quantitative_thresholds={
                        "min_keyword_matches": r.get("min_keyword_matches", 1),
                        "quantitative_threshold": r.get("quantitative_threshold", 0.0),
                    },
                )
                for r in data
            ]

        except (httpx.HTTPError, httpx.ConnectError) as e:
            logger.warning("cs3_rubric_fetch_failed", dimension=dimension.value, error=str(e))
            return self._load_local_rubric(dimension, level)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    # ── Parsing Helpers ─────────────────────────────────────────

    def _parse_result_json(self, ticker: str, data: dict) -> CompanyAssessment:
        """Parse a results/*.json file into CompanyAssessment."""
        dim_scores = {}
        raw_dims = data.get("dimension_scores", {})
        evidence_count = data.get("evidence_count", 0)

        for dim_key, score_val in raw_dims.items():
            try:
                dim = Dimension(dim_key)
            except ValueError:
                continue

            score = float(score_val)
            level = score_to_level(score)

            dim_scores[dim] = DimensionScore(
                dimension=dim,
                score=score,
                level=level,
                confidence_interval=(
                    float(data.get("ci_lower", score - 5)),
                    float(data.get("ci_upper", score + 5)),
                ),
                evidence_count=evidence_count // max(len(raw_dims), 1),
                last_updated=data.get("assessment_date", ""),
            )

        return CompanyAssessment(
            company_id=ticker,
            assessment_date=data.get("assessment_date", ""),
            vr_score=float(data.get("vr_score", 0)),
            hr_score=float(data.get("hr_score", 0)),
            synergy_score=float(data.get("synergy_score", 0)),
            org_air_score=float(data.get("final_score", 0)),
            confidence_interval=(
                float(data.get("ci_lower", 0)),
                float(data.get("ci_upper", 0)),
            ),
            dimension_scores=dim_scores,
            talent_concentration=float(data.get("talent_concentration", 0)),
            position_factor=float(data.get("position_factor", 0)),
        )

    def _parse_summary(self, ticker: str, summary: dict) -> CompanyAssessment:
        """Parse evidence-summary API response into CompanyAssessment."""
        # The summary endpoint doesn't have full scoring data,
        # so we build a minimal assessment
        dim_scores = {}
        summary_data = summary.get("summary", {})

        # Map signal summary scores to approximate dimension scores
        if summary_data:
            approx_dims = {
                Dimension.TALENT: float(summary_data.get("technology_hiring_score", 50)),
                Dimension.TECHNOLOGY_STACK: float(summary_data.get("digital_presence_score", 50)),
                Dimension.USE_CASE_PORTFOLIO: float(summary_data.get("innovation_activity_score", 50)),
                Dimension.LEADERSHIP: float(summary_data.get("leadership_signals_score", 50)),
            }
            for dim, score in approx_dims.items():
                level = score_to_level(score)
                dim_scores[dim] = DimensionScore(
                    dimension=dim,
                    score=score,
                    level=level,
                    confidence_interval=(max(0, score - 10), min(100, score + 10)),
                    evidence_count=summary.get("signal_count", 0),
                    last_updated="",
                )

        return CompanyAssessment(
            company_id=ticker,
            assessment_date="",
            vr_score=0,
            hr_score=0,
            synergy_score=0,
            org_air_score=float(summary_data.get("composite_score", 0)) if summary_data else 0,
            confidence_interval=(0, 0),
            dimension_scores=dim_scores,
            talent_concentration=0,
            position_factor=0,
        )

    # ── Local Fallback ──────────────────────────────────────────

    @staticmethod
    def _load_local_result(ticker: str) -> Optional[dict]:
        """Load scoring result from local results/{ticker}.json."""
        path = Path("results") / f"{ticker.lower()}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    def _load_local_rubric(
        self,
        dimension: Dimension,
        level: Optional[ScoreLevel] = None,
    ) -> List[RubricCriteria]:
        """
        Fallback: load rubric from the CS3 scoring module directly.

        This imports from app.scoring.rubric_scorer to avoid
        requiring the API to be running.
        """
        try:
            from app.scoring.rubric_scorer import (
                DIMENSION_RUBRICS,
                ScoreLevel as CS3Level,
            )

            rubric = DIMENSION_RUBRICS.get(dimension.value, {})
            results = []

            level_map = {
                CS3Level.LEVEL_5: ScoreLevel.LEVEL_5,
                CS3Level.LEVEL_4: ScoreLevel.LEVEL_4,
                CS3Level.LEVEL_3: ScoreLevel.LEVEL_3,
                CS3Level.LEVEL_2: ScoreLevel.LEVEL_2,
                CS3Level.LEVEL_1: ScoreLevel.LEVEL_1,
            }

            for cs3_level, criteria in rubric.items():
                cs4_level = level_map.get(cs3_level)
                if cs4_level is None:
                    continue
                if level is not None and cs4_level != level:
                    continue

                results.append(RubricCriteria(
                    dimension=dimension,
                    level=cs4_level,
                    criteria_text=f"Level {cs4_level.value} ({cs4_level.name_label}): "
                                  f"Requires {criteria.min_keyword_matches}+ keyword matches",
                    keywords=criteria.keywords,
                    quantitative_thresholds={
                        "min_keyword_matches": criteria.min_keyword_matches,
                        "quantitative_threshold": criteria.quantitative_threshold,
                    },
                ))

            return sorted(results, key=lambda r: r.level.value, reverse=True)

        except ImportError:
            logger.warning("cs3_rubric_import_failed", dimension=dimension.value)
            return []

"""
Rubric-Based Scorer.

CS3 Task 5.0b: Converts raw evidence into rubric-aligned scores
using the 5-level PE Org-AI-R rubrics for each of the 7 dimensions.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List


class ScoreLevel(Enum):
    LEVEL_5 = (80, 100, "Excellent")
    LEVEL_4 = (60, 79, "Good")
    LEVEL_3 = (40, 59, "Adequate")
    LEVEL_2 = (20, 39, "Developing")
    LEVEL_1 = (0, 19, "Nascent")

    @property
    def min_score(self) -> int:
        return self.value[0]

    @property
    def max_score(self) -> int:
        return self.value[1]


@dataclass
class RubricCriteria:
    level: ScoreLevel
    keywords: List[str]
    min_keyword_matches: int
    quantitative_threshold: float


@dataclass
class RubricResult:
    dimension: str
    level: ScoreLevel
    score: Decimal
    matched_keywords: List[str]
    keyword_match_count: int
    confidence: Decimal
    rationale: str


DIMENSION_RUBRICS: Dict[str, Dict[ScoreLevel, RubricCriteria]] = {
    "data_infrastructure": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["snowflake", "databricks", "lakehouse", "real-time",
                       "data quality", "api-first", "data mesh", "streaming"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["azure", "aws", "warehouse", "etl", "data catalog",
                       "hybrid cloud", "data lake", "cloud migration"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["migration", "hybrid", "modernizing", "cloud adoption",
                       "data warehouse", "batch processing"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["legacy", "silos", "on-premise", "fragmented",
                       "mainframe", "manual processes"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["mainframe", "spreadsheets", "manual", "no infrastructure",
                       "paper-based"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "ai_governance": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["caio", "cdo", "board committee", "model risk",
                       "responsible ai", "ai ethics", "governance framework"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["vp data", "ai policy", "risk framework", "compliance",
                       "data governance", "model validation"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["director", "guidelines", "it governance", "data privacy",
                       "security framework"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["informal", "no policy", "ad-hoc", "basic compliance"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["none", "no oversight", "unmanaged", "no governance"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "technology_stack": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["sagemaker", "mlops", "feature store", "model registry",
                       "vertex ai", "automated pipeline", "ci/cd for ml"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["mlflow", "kubeflow", "databricks ml", "experiment tracking",
                       "model serving", "containerized"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["jupyter", "notebooks", "manual deploy", "python",
                       "scikit-learn", "basic ml"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["excel", "tableau only", "no ml", "basic bi",
                       "spreadsheet analytics"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["manual", "no tools", "no analytics", "manual reporting"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "talent": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["ml platform", "ai research", "large team", ">20 specialists",
                       "ai leadership", "principal ml", "staff ml"],
            min_keyword_matches=3,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["data science team", "ml engineers", "10-20",
                       "active hiring", "retention", "ai team"],
            min_keyword_matches=2,
            quantitative_threshold=0.25,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["data scientist", "growing team", "3-10",
                       "hiring data", "analytics team"],
            min_keyword_matches=2,
            quantitative_threshold=0.15,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["junior", "contractor", "turnover", "one data scientist",
                       "outsourced"],
            min_keyword_matches=1,
            quantitative_threshold=0.05,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["no data scientist", "vendor only", "no ai talent",
                       "no technical staff"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "leadership": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["ceo ai", "board committee", "ai strategy",
                       "multi-year plan", "ai investment", "digital transformation"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["cto ai", "strategic priority", "executive sponsor",
                       "technology roadmap", "innovation agenda"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["vp sponsor", "department initiative", "pilot program",
                       "innovation lab"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["it led", "limited awareness", "no executive sponsor",
                       "cost center"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["no sponsor", "not discussed", "no ai awareness"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "use_case_portfolio": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["production ai", "3x roi", "ai product", "5+ use cases",
                       "revenue generating", "scaled ai"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["production", "measured roi", "scaling", "2-4 use cases",
                       "deployed model"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["pilot", "early production", "poc to production",
                       "initial deployment"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["poc", "proof of concept", "experimentation",
                       "no production"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["exploring", "no use cases", "no ai projects"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
    "culture": {
        ScoreLevel.LEVEL_5: RubricCriteria(
            level=ScoreLevel.LEVEL_5,
            keywords=["innovative", "data-driven", "fail-fast",
                       "experimentation", "growth mindset", "continuous learning"],
            min_keyword_matches=3,
            quantitative_threshold=0.80,
        ),
        ScoreLevel.LEVEL_4: RubricCriteria(
            level=ScoreLevel.LEVEL_4,
            keywords=["experimental", "learning culture", "agile",
                       "data literacy", "adaptive"],
            min_keyword_matches=2,
            quantitative_threshold=0.60,
        ),
        ScoreLevel.LEVEL_3: RubricCriteria(
            level=ScoreLevel.LEVEL_3,
            keywords=["open to change", "some resistance", "mixed adoption",
                       "evolving culture"],
            min_keyword_matches=2,
            quantitative_threshold=0.40,
        ),
        ScoreLevel.LEVEL_2: RubricCriteria(
            level=ScoreLevel.LEVEL_2,
            keywords=["bureaucratic", "resistant", "slow", "hierarchical",
                       "risk-averse"],
            min_keyword_matches=1,
            quantitative_threshold=0.20,
        ),
        ScoreLevel.LEVEL_1: RubricCriteria(
            level=ScoreLevel.LEVEL_1,
            keywords=["hostile", "siloed", "no data culture", "change averse"],
            min_keyword_matches=1,
            quantitative_threshold=0.0,
        ),
    },
}


class RubricScorer:
    """Score evidence against PE Org-AI-R rubrics."""

    def __init__(self):
        self.rubrics = DIMENSION_RUBRICS

    def score_dimension(
        self,
        dimension: str,
        evidence_text: str,
        quantitative_metrics: Dict[str, float],
    ) -> RubricResult:
        text = evidence_text.lower()
        rubric = self.rubrics.get(dimension, {})

        # Check from highest level down
        for level in [ScoreLevel.LEVEL_5, ScoreLevel.LEVEL_4, ScoreLevel.LEVEL_3,
                      ScoreLevel.LEVEL_2, ScoreLevel.LEVEL_1]:
            criteria = rubric.get(level)
            if not criteria:
                continue

            matches = [kw for kw in criteria.keywords if kw in text]

            # Check quantitative threshold
            quant_key = next(iter(quantitative_metrics), None)
            quant_val = quantitative_metrics.get(quant_key, 0) if quant_key else 0
            quant_met = quant_val >= criteria.quantitative_threshold

            if len(matches) >= criteria.min_keyword_matches or (quant_met and matches):
                # Interpolate within the level range
                match_ratio = min(len(matches) / max(len(criteria.keywords), 1), 1.0)
                range_size = level.max_score - level.min_score
                score = level.min_score + match_ratio * range_size

                confidence = min(
                    Decimal("0.5") + Decimal(str(len(matches))) * Decimal("0.1"),
                    Decimal("0.95"),
                )

                return RubricResult(
                    dimension=dimension,
                    level=level,
                    score=Decimal(str(round(score, 2))),
                    matched_keywords=matches,
                    keyword_match_count=len(matches),
                    confidence=confidence,
                    rationale=f"Matched {len(matches)} keywords at {level.value[2]} level",
                )

        # No level matched — default to LEVEL_2 midpoint
        return RubricResult(
            dimension=dimension,
            level=ScoreLevel.LEVEL_2,
            score=Decimal("30"),
            matched_keywords=[],
            keyword_match_count=0,
            confidence=Decimal("0.3"),
            rationale="No rubric keywords matched, defaulting to Developing level",
        )

    def score_all_dimensions(
        self,
        evidence_by_dimension: Dict[str, str],
        metrics_by_dimension: Dict[str, Dict[str, float]],
    ) -> Dict[str, RubricResult]:
        results = {}
        for dim in DIMENSION_RUBRICS:
            text = evidence_by_dimension.get(dim, "")
            metrics = metrics_by_dimension.get(dim, {})
            results[dim] = self.score_dimension(dim, text, metrics)
        return results

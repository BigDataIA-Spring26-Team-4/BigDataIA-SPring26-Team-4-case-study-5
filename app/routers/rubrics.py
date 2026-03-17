"""
Rubrics API router for PE Org-AI-R Platform.

CS4 Integration: Exposes rubric criteria (keywords, thresholds, score levels)
so the CS4 RAG layer can fetch rubric data for score justification generation.
"""

import structlog
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel

from app.scoring.rubric_scorer import DIMENSION_RUBRICS, ScoreLevel

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/rubrics", tags=["rubrics"])


# ============================================================================
# Response Models
# ============================================================================

class RubricCriteriaResponse(BaseModel):
    """Single rubric criteria for a dimension at a specific level."""
    level: int
    level_name: str
    score_range: list[int]
    keywords: list[str]
    min_keyword_matches: int
    quantitative_threshold: float


class DimensionRubricResponse(BaseModel):
    """All rubric levels for a dimension."""
    dimension: str
    criteria: list[RubricCriteriaResponse]


# ============================================================================
# Helpers
# ============================================================================

VALID_DIMENSIONS = list(DIMENSION_RUBRICS.keys())

LEVEL_NAMES = {
    5: "Excellent",
    4: "Good",
    3: "Adequate",
    2: "Developing",
    1: "Nascent",
}

LEVEL_RANGES = {
    5: [80, 100],
    4: [60, 79],
    3: [40, 59],
    2: [20, 39],
    1: [0, 19],
}


def _score_level_to_int(level: ScoreLevel) -> int:
    """Extract integer level from ScoreLevel enum."""
    return {
        ScoreLevel.LEVEL_5: 5,
        ScoreLevel.LEVEL_4: 4,
        ScoreLevel.LEVEL_3: 3,
        ScoreLevel.LEVEL_2: 2,
        ScoreLevel.LEVEL_1: 1,
    }[level]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=list[str])
def list_dimensions():
    """List all dimensions that have rubric definitions."""
    return VALID_DIMENSIONS


@router.get("/{dimension}", response_model=list[RubricCriteriaResponse])
def get_rubric(
    dimension: str,
    level: Optional[int] = Query(
        None, ge=1, le=5,
        description="Filter by level (1-5). Returns all levels if omitted."
    ),
):
    """
    Fetch rubric criteria for a dimension.

    Returns keywords, thresholds, and score ranges for each level.
    Used by CS4's justification generator to match evidence against rubrics.
    """
    if dimension not in DIMENSION_RUBRICS:
        raise HTTPException(
            status_code=404,
            detail=f"Dimension '{dimension}' not found. Valid: {VALID_DIMENSIONS}",
        )

    rubric = DIMENSION_RUBRICS[dimension]
    results = []

    for score_level, criteria in rubric.items():
        lvl = _score_level_to_int(score_level)

        # If a specific level was requested, skip others
        if level is not None and lvl != level:
            continue

        results.append(RubricCriteriaResponse(
            level=lvl,
            level_name=LEVEL_NAMES[lvl],
            score_range=LEVEL_RANGES[lvl],
            keywords=criteria.keywords,
            min_keyword_matches=criteria.min_keyword_matches,
            quantitative_threshold=criteria.quantitative_threshold,
        ))

    if level is not None and not results:
        raise HTTPException(
            status_code=404,
            detail=f"No rubric found for dimension='{dimension}' at level={level}",
        )

    # Return sorted by level descending (Level 5 first)
    return sorted(results, key=lambda r: r.level, reverse=True)

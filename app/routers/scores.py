"""
Dimension Scores API router for PE Org-AI-R Platform.

This router handles the individual score update endpoint that's separate
from the assessments router per PDF Table 2.
"""

import structlog
from fastapi import APIRouter, Depends
from uuid import UUID
from sqlalchemy.orm import Session

from app.models.dimension import DimensionScoreUpdate, DimensionScoreResponse
from app.services import snowflake
from app.services.snowflake import get_db
from app.services.redis_cache import invalidate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/scores", tags=["dimension-scores"])

CACHE_PREFIX = "assessments:"  # Invalidate assessment cache when scores change


@router.put("/{score_id}", response_model=DimensionScoreResponse)
def update_score(
    score_id: UUID,
    score: DimensionScoreUpdate,
    db: Session = Depends(get_db)
):
    """
    Update a single dimension score.
    
    Endpoint: PUT /api/v1/scores/{id}
    Per PDF Table 2: "Update a dimension score"
    """
    log.info("updating_score", score_id=str(score_id))
    result = snowflake.update_score(db, str(score_id), score)
    invalidate(CACHE_PREFIX)
    log.info("score_updated", score_id=str(score_id))
    return result

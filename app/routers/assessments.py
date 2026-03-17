"""
Assessments API router for PE Org-AI-R Platform.

Implements all assessment endpoints with PDF-compliant pagination.
"""

import structlog
from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.models.assessment import AssessmentCreate, AssessmentUpdate, AssessmentResponse
from app.models.dimension import DimensionScoreCreate, DimensionScoreUpdate, DimensionScoreResponse
from app.models.common import PaginatedResponse, paginate
from app.services import snowflake
from app.services.snowflake import get_db
from app.services.redis_cache import cached, invalidate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/assessments", tags=["assessments"])

CACHE_PREFIX = "assessments:"


@router.post("", response_model=AssessmentResponse, status_code=201)
def create_assessment(assessment: AssessmentCreate, db: Session = Depends(get_db)):
    """Create a new assessment."""
    log.info(
        "creating_assessment",
        company_id=str(assessment.company_id),
        type=assessment.assessment_type.value
    )
    result = snowflake.create_assessment(db, assessment)
    invalidate(CACHE_PREFIX)
    log.info("assessment_created", assessment_id=result.id)
    return result


@router.get("", response_model=PaginatedResponse[AssessmentResponse])
def list_assessments(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    company_id: Optional[str] = Query(None, description="Filter by company ID"),
    db: Session = Depends(get_db)
):
    """
    List assessments with pagination and filtering.
    
    Returns paginated response per PDF Section 4.3.
    """
    # Convert page/page_size to skip/limit
    skip = (page - 1) * page_size
    limit = page_size
    
    log.info("listing_assessments", page=page, page_size=page_size, company_id=company_id)
    
    # Get items and total count
    items = snowflake.list_assessments(db, skip=skip, limit=limit, company_id=company_id)
    total = snowflake.count_assessments(db, company_id=company_id)
    
    # Return paginated response
    return paginate(items, total, skip, limit)


@router.get("/{assessment_id}", response_model=AssessmentResponse)
@cached(prefix=CACHE_PREFIX, ttl=120)  # 2 minutes per PDF Table 3
def get_assessment(assessment_id: UUID, db: Session = Depends(get_db)):
    """Get an assessment by ID (cached for 2 minutes per PDF Table 3)."""
    log.info("getting_assessment", assessment_id=str(assessment_id))
    return snowflake.get_assessment(db, str(assessment_id))


@router.patch("/{assessment_id}", response_model=AssessmentResponse)
def update_assessment(
    assessment_id: UUID,
    assessment: AssessmentUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an assessment (including status transitions).
    
    PDF Section 4.1: PATCH /api/v1/assessments/{id}/status
    Implemented as PATCH /api/v1/assessments/{id} with optional status field.
    """
    log.info("updating_assessment", assessment_id=str(assessment_id))
    result = snowflake.update_assessment(db, str(assessment_id), assessment)
    invalidate(CACHE_PREFIX)
    log.info("assessment_updated", assessment_id=str(assessment_id))
    return result


# ============================================================================
# Dimension Scores Endpoints
# ============================================================================

@router.post("/{assessment_id}/scores", response_model=list[DimensionScoreResponse], status_code=201)
def add_scores(
    assessment_id: UUID,
    scores: list[DimensionScoreCreate],
    db: Session = Depends(get_db)
):
    """Add dimension scores to an assessment."""
    log.info("adding_scores", assessment_id=str(assessment_id), count=len(scores))
    result = snowflake.add_scores(db, str(assessment_id), scores)
    invalidate(CACHE_PREFIX)
    log.info("scores_added", assessment_id=str(assessment_id), count=len(scores))
    return result


@router.get("/{assessment_id}/scores", response_model=list[DimensionScoreResponse])
@cached(prefix=CACHE_PREFIX)
def get_scores(assessment_id: UUID, db: Session = Depends(get_db)):
    """Get all dimension scores for an assessment."""
    log.info("getting_scores", assessment_id=str(assessment_id))
    return snowflake.get_scores(db, str(assessment_id))


# Note: Individual score update endpoint moved to app/routers/scores.py
# to match PDF Table 2 endpoint: PUT /api/v1/scores/{id}

"""
Industries API router for PE Org-AI-R Platform.

Provides full CRUD endpoints for industry reference data with caching.
Per PDF Section 8.1: "Redis caching implemented for companies and industries"
"""

import structlog
from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.models.company import IndustryCreate, IndustryResponse
from app.models.common import PaginatedResponse, paginate
from app.services import snowflake
from app.services.snowflake import get_db
from app.services.redis_cache import cached, invalidate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/industries", tags=["industries"])

# Industry list cached for 1 hour (PDF Table 3)
CACHE_PREFIX = "industries:"


@router.post("", response_model=IndustryResponse, status_code=201)
def create_industry(industry: IndustryCreate, db: Session = Depends(get_db)):
    """Create a new industry."""
    log.info("creating_industry", name=industry.name)
    result = snowflake.create_industry(db, industry)
    invalidate(CACHE_PREFIX)  # Invalidate all industry cache
    log.info("industry_created", industry_id=result.id)
    return result


@router.get("", response_model=PaginatedResponse[IndustryResponse])
def list_industries(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db)
):
    """
    List all industries with pagination.
    
    Cached for 1 hour per PDF Section 6.1 Table 3:
    "Industry list - 1 hour - Static reference data"
    """
    # Convert page/page_size to skip/limit
    skip = (page - 1) * page_size
    limit = page_size
    
    log.info("listing_industries", page=page, page_size=page_size)
    
    # For industries, we don't expect many, so we can cache the full list
    # and paginate in-memory for simplicity
    all_industries = snowflake.list_industries(db)
    total = len(all_industries)
    
    # Paginate in-memory
    items = all_industries[skip:skip + limit]
    
    return paginate(items, total, skip, limit)


@router.get("/{industry_id}", response_model=IndustryResponse)
@cached(prefix=CACHE_PREFIX, ttl=3600)  # 1 hour per PDF Table 3
def get_industry(industry_id: UUID, db: Session = Depends(get_db)):
    """Get industry by ID (cached for 1 hour per PDF Table 3)."""
    log.info("getting_industry", industry_id=str(industry_id))
    return snowflake.get_industry(db, str(industry_id))


@router.put("/{industry_id}", response_model=IndustryResponse)
def update_industry(
    industry_id: UUID,
    industry: IndustryCreate,
    db: Session = Depends(get_db)
):
    """Update an industry."""
    log.info("updating_industry", industry_id=str(industry_id))
    
    # Get existing industry
    existing = snowflake.get_industry(db, str(industry_id))
    
    # Update fields
    existing.name = industry.name
    existing.sector = industry.sector
    existing.h_r_base = float(industry.h_r_base)
    
    db.commit()
    db.refresh(existing)
    
    invalidate(CACHE_PREFIX)  # Invalidate all industry cache
    log.info("industry_updated", industry_id=str(industry_id))
    return existing


@router.delete("/{industry_id}", status_code=204)
def delete_industry(industry_id: UUID, db: Session = Depends(get_db)):
    """Delete an industry."""
    log.info("deleting_industry", industry_id=str(industry_id))
    
    industry = snowflake.get_industry(db, str(industry_id))
    db.delete(industry)
    db.commit()
    
    invalidate(CACHE_PREFIX)  # Invalidate all industry cache
    log.info("industry_deleted", industry_id=str(industry_id))
    return None

"""
Companies API router for PE Org-AI-R Platform.

Implements all company endpoints with PDF-compliant pagination.
"""

import structlog
from fastapi import APIRouter, Depends, Query
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import Session

from app.models.company import CompanyCreate, CompanyUpdate, CompanyResponse
from app.models.common import PaginatedResponse, paginate
from app.services import snowflake
from app.services.snowflake import get_db
from app.services.redis_cache import cached, invalidate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/companies", tags=["companies"])

CACHE_PREFIX = "companies:"


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(company: CompanyCreate, db: Session = Depends(get_db)):
    """Create a new company."""
    log.info("creating_company", name=company.name)
    result = snowflake.create_company(db, company)
    invalidate(CACHE_PREFIX)
    log.info("company_created", company_id=result.id)
    return result


@router.get("", response_model=PaginatedResponse[CompanyResponse])
def list_companies(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    industry_id: Optional[str] = Query(None, description="Filter by industry ID"),
    db: Session = Depends(get_db)
):
    """
    List companies with pagination.
    
    Returns paginated response per PDF Section 4.3:
    {
        "items": [...],
        "total": 100,
        "page": 1,
        "page_size": 20,
        "total_pages": 5
    }
    """
    # Convert page/page_size to skip/limit
    skip = (page - 1) * page_size
    limit = page_size
    
    log.info("listing_companies", page=page, page_size=page_size, industry_id=industry_id)
    
    # Get items and total count
    items = snowflake.list_companies(db, skip=skip, limit=limit, industry_id=industry_id)
    total = snowflake.count_companies(db, industry_id=industry_id)
    
    # Return paginated response
    return paginate(items, total, skip, limit)


@router.get("/by-ticker/{ticker}")
@cached(prefix=CACHE_PREFIX, ttl=300)
def get_company_by_ticker(ticker: str, db: Session = Depends(get_db)):
    """
    Get a company by ticker symbol.

    CS4 Integration: CS1 client needs ticker-based lookup for company metadata.
    Returns company data with sector from industry join.
    """
    log.info("getting_company_by_ticker", ticker=ticker)
    company = snowflake.get_company_by_ticker_with_industry(db, ticker.upper())
    if not company:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Company with ticker '{ticker}' not found")
    return company


@router.get("/{company_id}", response_model=CompanyResponse)
@cached(prefix=CACHE_PREFIX, ttl=300)  # 5 minutes per PDF Table 3
def get_company(company_id: UUID, db: Session = Depends(get_db)):
    """Get a company by ID (cached for 5 minutes per PDF Table 3)."""
    log.info("getting_company", company_id=str(company_id))
    return snowflake.get_company(db, str(company_id))


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    company: CompanyUpdate,
    db: Session = Depends(get_db)
):
    """Update a company."""
    log.info("updating_company", company_id=str(company_id))
    result = snowflake.update_company(db, str(company_id), company)
    invalidate(CACHE_PREFIX)
    log.info("company_updated", company_id=str(company_id))
    return result


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: UUID, db: Session = Depends(get_db)):
    """Soft delete a company."""
    log.info("deleting_company", company_id=str(company_id))
    snowflake.delete_company(db, str(company_id))
    invalidate(CACHE_PREFIX)
    log.info("company_deleted", company_id=str(company_id))
    return None

"""
Common/shared Pydantic models for PE Org-AI-R Platform.

Includes pagination models as specified in PDF Section 4.3.
"""

from pydantic import BaseModel, Field
from typing import Generic, TypeVar, List
import math

T = TypeVar('T')


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Paginated response model as specified in PDF Section 4.3.
    
    Example:
        {
            "items": [...],
            "total": 100,
            "page": 1,
            "page_size": 20,
            "total_pages": 5
        }
    """
    items: List[T] = Field(..., description="List of items for this page")
    total: int = Field(..., description="Total number of items across all pages")
    page: int = Field(..., ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    
    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int
    ) -> "PaginatedResponse[T]":
        """
        Create paginated response with calculated total_pages.
        
        Args:
            items: List of items for current page
            total: Total count of items
            page: Current page number (1-indexed)
            page_size: Items per page
            
        Returns:
            PaginatedResponse with calculated total_pages
        """
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    model_config = {"arbitrary_types_allowed": True}


def paginate(
    items: List[T],
    total: int,
    skip: int,
    limit: int
) -> PaginatedResponse[T]:
    """
    Helper function to convert skip/limit to page-based pagination.
    
    Args:
        items: Items for current page
        total: Total count
        skip: Number of items skipped
        limit: Page size
        
    Returns:
        PaginatedResponse
        
    Example:
        >>> items = get_companies(skip=20, limit=10)
        >>> total = count_companies()
        >>> paginate(items, total, skip=20, limit=10)
        PaginatedResponse(items=..., page=3, page_size=10, total_pages=15)
    """
    # Calculate page number from skip/limit
    page = (skip // limit) + 1
    
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        page_size=limit
    )

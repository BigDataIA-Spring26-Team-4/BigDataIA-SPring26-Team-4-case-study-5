"""
Company Pydantic models for PE Org-AI-R Platform.

This module defines the data validation models for Company entities,
following the exact specifications from the case study requirements.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class CompanyBase(BaseModel):
    """
    Base model for Company with common fields.
    
    Requirements from Case Study:
    - Name: required, 1-255 characters
    - Ticker: optional, uppercase, 1-10 characters
    - Industry reference: UUID foreign key
    - Position factor: -1.0 to 1.0, default 0.0
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Company name"
    )
    ticker: Optional[str] = Field(
        None,
        max_length=10,
        description="Stock ticker symbol (optional, uppercase, 1-10 chars)"
    )
    industry_id: UUID = Field(
        ...,
        description="Foreign key reference to industry"
    )
    position_factor: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Position factor between -1.0 and 1.0"
    )
    
    @field_validator('ticker')
    @classmethod
    def uppercase_ticker(cls, v: Optional[str]) -> Optional[str]:
        """
        Convert ticker to uppercase.
        
        Args:
            v: Ticker symbol value
            
        Returns:
            Uppercase ticker or None
            
        Example:
            >>> CompanyBase(name="Test", ticker="aapl", industry_id=uuid4(), position_factor=0.0)
            # ticker becomes "AAPL"
        """
        return v.upper() if v else None


class CompanyCreate(CompanyBase):
    """
    Model for creating a new company.
    Inherits all validation from CompanyBase.
    """
    pass


class CompanyUpdate(BaseModel):
    """
    Model for updating an existing company.
    All fields are optional to support partial updates.
    """
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Company name"
    )
    ticker: Optional[str] = Field(
        None,
        max_length=10,
        description="Stock ticker symbol"
    )
    industry_id: Optional[UUID] = Field(
        None,
        description="Industry reference"
    )
    position_factor: Optional[float] = Field(
        None,
        ge=-1.0,
        le=1.0,
        description="Position factor"
    )
    
    @field_validator('ticker')
    @classmethod
    def uppercase_ticker(cls, v: Optional[str]) -> Optional[str]:
        """Convert ticker to uppercase."""
        return v.upper() if v else None


class CompanyResponse(CompanyBase):
    """
    Model for company responses from the API.
    Includes system-generated fields (id, timestamps).
    """
    id: UUID = Field(..., description="Unique company identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    model_config = {"from_attributes": True}


# ============================================================================
# Industry Model (Reference Data)
# ============================================================================

class IndustryBase(BaseModel):
    """Base model for Industry reference data."""
    name: str = Field(..., min_length=1, max_length=255, description="Industry name")
    sector: str = Field(..., min_length=1, max_length=100, description="Sector classification")
    h_r_base: float = Field(..., ge=0, le=100, description="Historical readiness baseline (0-100)")


class IndustryCreate(IndustryBase):
    """Model for creating a new industry."""
    pass


class IndustryResponse(IndustryBase):
    """Model for industry responses from the API."""
    id: UUID = Field(..., description="Unique industry identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {"from_attributes": True}

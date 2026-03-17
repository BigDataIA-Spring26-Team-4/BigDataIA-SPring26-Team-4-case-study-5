"""
Dimension Score Pydantic models for PE Org-AI-R Platform.

This module defines data validation models for dimension scoring,
implementing the 7-dimension AI-Readiness framework.

Requirements from Case Study PDF (Section 3.2.4 & Table 1):
- Seven dimensions of AI-Readiness
- Default weights per dimension
- Score validation (0-100)
- Confidence levels
- Evidence tracking
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum


# ============================================================================
# Dimension Enumeration (Exact from PDF Section 3.2.1 & Table 1)
# ============================================================================

class Dimension(str, Enum):
    """
    Seven dimensions of AI-Readiness as defined in the PE Org-AI-R Framework.
    
    Case Study Table 1: The Seven Dimensions of AI-Readiness
    Each dimension measures a specific aspect of organizational AI capability.
    """
    DATA_INFRASTRUCTURE = "data_infrastructure"      # D1: Weight 0.25
    AI_GOVERNANCE = "ai_governance"                  # D2: Weight 0.20
    TECHNOLOGY_STACK = "technology_stack"            # D3: Weight 0.15
    TALENT_SKILLS = "talent_skills"                  # D4: Weight 0.15
    LEADERSHIP_VISION = "leadership_vision"          # D5: Weight 0.10
    USE_CASE_PORTFOLIO = "use_case_portfolio"        # D6: Weight 0.10
    CULTURE_CHANGE = "culture_change"                # D7: Weight 0.05


# ============================================================================
# Default Weights (Exact from PDF Section 3.2.4 & Table 1)
# ============================================================================

DIMENSION_WEIGHTS: dict[Dimension, float] = {
    Dimension.DATA_INFRASTRUCTURE: 0.25,   # Highest priority
    Dimension.AI_GOVERNANCE: 0.20,
    Dimension.TECHNOLOGY_STACK: 0.15,
    Dimension.TALENT_SKILLS: 0.15,
    Dimension.LEADERSHIP_VISION: 0.10,
    Dimension.USE_CASE_PORTFOLIO: 0.10,
    Dimension.CULTURE_CHANGE: 0.05,       # Lowest priority
}

# Verify weights sum to 1.0
assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 0.001, "Dimension weights must sum to 1.0"


# ============================================================================
# Dimension Metadata
# ============================================================================

DIMENSION_DESCRIPTIONS: dict[Dimension, str] = {
    Dimension.DATA_INFRASTRUCTURE: "Quality, accessibility, and governance of data assets",
    Dimension.AI_GOVERNANCE: "Policies, ethics frameworks, compliance readiness",
    Dimension.TECHNOLOGY_STACK: "Cloud infrastructure, ML tooling, API architecture",
    Dimension.TALENT_SKILLS: "AI/ML talent density, retention, training programs",
    Dimension.LEADERSHIP_VISION: "Executive commitment, AI strategy, investment appetite",
    Dimension.USE_CASE_PORTFOLIO: "AI projects in production, pipeline, ROI tracking",
    Dimension.CULTURE_CHANGE: "Innovation culture, change readiness, adoption rates",
}


# ============================================================================
# Pydantic Models
# ============================================================================

class DimensionScoreBase(BaseModel):
    """
    Base model for Dimension Score with common fields.
    
    Requirements from Case Study Section 3.2.4:
    - Assessment foreign key reference
    - Dimension type (enum)
    - Score (0-100, required)
    - Weight (0-1, dimension-specific default)
    - Confidence level (0-1)
    - Evidence count (how many pieces of evidence support this score)
    """
    assessment_id: UUID = Field(
        ...,
        description="Foreign key reference to assessment"
    )
    dimension: Dimension = Field(
        ...,
        description="Dimension being scored"
    )
    score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Score for this dimension (0-100)"
    )
    weight: Optional[float] = Field(
        default=None,
        ge=0,
        le=1,
        description="Weight of this dimension (0-1, auto-set from DIMENSION_WEIGHTS if None)"
    )
    confidence: float = Field(
        default=0.8,
        ge=0,
        le=1,
        description="Confidence level in this score (0-1)"
    )
    evidence_count: int = Field(
        default=0,
        ge=0,
        description="Number of evidence pieces supporting this score"
    )
    
    @model_validator(mode='after')
    def set_default_weight(self) -> 'DimensionScoreBase':
        """
        Auto-set weight from DIMENSION_WEIGHTS if not provided.
        
        From PDF Section 3.2.4:
        "Weight (0-1, dimension-specific default)" - each dimension
        has a predefined weight that is used if not explicitly set.
        """
        if self.weight is None:
            self.weight = DIMENSION_WEIGHTS.get(self.dimension, 0.1)
        return self


class DimensionScoreCreate(DimensionScoreBase):
    """
    Model for creating a new dimension score.
    Inherits all validation from DimensionScoreBase.
    """
    pass


class DimensionScoreUpdate(BaseModel):
    """
    Model for updating an existing dimension score.
    All fields are optional to support partial updates.
    """
    score: Optional[float] = Field(None, ge=0, le=100)
    weight: Optional[float] = Field(None, ge=0, le=1)
    confidence: Optional[float] = Field(None, ge=0, le=1)
    evidence_count: Optional[int] = Field(None, ge=0)


class DimensionScoreResponse(DimensionScoreBase):
    """
    Model for dimension score responses from the API.
    Includes system-generated fields (id, timestamps).
    """
    id: UUID = Field(..., description="Unique dimension score identifier")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    model_config = {"from_attributes": True}


# ============================================================================
# Helper Functions
# ============================================================================

def get_dimension_weight(dimension: Dimension) -> float:
    """
    Get the default weight for a dimension.
    
    Args:
        dimension: The dimension to get weight for
        
    Returns:
        float: Default weight for this dimension
        
    Example:
        >>> get_dimension_weight(Dimension.DATA_INFRASTRUCTURE)
        0.25
    """
    return DIMENSION_WEIGHTS.get(dimension, 0.1)


def get_dimension_description(dimension: Dimension) -> str:
    """
    Get the description for a dimension.
    
    Args:
        dimension: The dimension to get description for
        
    Returns:
        str: Description of what this dimension measures
        
    Example:
        >>> get_dimension_description(Dimension.DATA_INFRASTRUCTURE)
        'Quality, accessibility, and governance of data assets'
    """
    return DIMENSION_DESCRIPTIONS.get(
        dimension,
        "AI-Readiness dimension"
    )


def validate_dimension_scores_complete(scores: list[DimensionScoreBase]) -> bool:
    """
    Validate that all 7 dimensions are present in a score set.
    
    Args:
        scores: List of dimension scores
        
    Returns:
        bool: True if all 7 dimensions are present
        
    Example:
        >>> scores = [DimensionScoreBase(dimension=d, ...) for d in Dimension]
        >>> validate_dimension_scores_complete(scores)
        True
    """
    scored_dimensions = {score.dimension for score in scores}
    all_dimensions = set(Dimension)
    return scored_dimensions == all_dimensions


def get_missing_dimensions(scores: list[DimensionScoreBase]) -> list[Dimension]:
    """
    Get list of dimensions that are missing from a score set.
    
    Args:
        scores: List of dimension scores
        
    Returns:
        List of dimensions not present in scores
        
    Example:
        >>> scores = [DimensionScoreBase(dimension=Dimension.DATA_INFRASTRUCTURE, ...)]
        >>> missing = get_missing_dimensions(scores)
        >>> len(missing)
        6
    """
    scored_dimensions = {score.dimension for score in scores}
    all_dimensions = set(Dimension)
    return list(all_dimensions - scored_dimensions)

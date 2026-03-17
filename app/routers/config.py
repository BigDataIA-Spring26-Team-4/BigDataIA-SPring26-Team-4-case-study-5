"""
Configuration API router for PE Org-AI-R Platform.

Provides endpoints for configuration data like dimension weights.
"""

import structlog
from fastapi import APIRouter
from pydantic import BaseModel

from app.models.dimension import DIMENSION_WEIGHTS, Dimension
from app.services.redis_cache import cached

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/config", tags=["configuration"])


class DimensionWeightsResponse(BaseModel):
    """Response model for dimension weights."""
    weights: dict[str, float]
    total: float
    
    model_config = {"json_schema_extra": {
        "example": {
            "weights": {
                "data_infrastructure": 0.25,
                "ai_governance": 0.20,
                "technology_stack": 0.15,
                "talent_skills": 0.15,
                "leadership_vision": 0.10,
                "use_case_portfolio": 0.10,
                "culture_change": 0.05
            },
            "total": 1.0
        }
    }}


@router.get("/dimension-weights", response_model=DimensionWeightsResponse)
@cached(prefix="config:dimension-weights:", ttl=86400)  # 24 hours per PDF Table 3
def get_dimension_weights():
    """
    Get dimension weights configuration.
    
    Cached for 24 hours per PDF Section 6.1 Table 3:
    "Dimension weights - 24 hours - Configuration, rarely changes"
    
    Returns the 7 dimension weights from the PE Org-AI-R framework.
    """
    log.info("getting_dimension_weights")
    
    # Convert enum keys to string values for JSON response
    weights = {dim.value: weight for dim, weight in DIMENSION_WEIGHTS.items()}
    total = sum(weights.values())
    
    return DimensionWeightsResponse(
        weights=weights,
        total=total
    )

"""
Assessment Pydantic models for PE Org-AI-R Platform.

This module defines data validation models for Assessment entities,
including state machine validation for status transitions.

Requirements from Case Study PDF (Section 3.2.3):
- Assessment types: SCREENING, DUE_DILIGENCE, QUARTERLY, EXIT_PREP
- Status with state machine: DRAFT, IN_PROGRESS, SUBMITTED, APPROVED, SUPERSEDED
- Optional VR score (0-100, calculated later)
- Confidence interval (lower, upper bounds)
- Assessor information
"""

from pydantic import BaseModel, Field, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum


# ============================================================================
# Enumerations (Exact from PDF)
# ============================================================================

class AssessmentType(str, Enum):
    """
    Type of AI-readiness assessment.
    
    Case Study Section 3.2.1:
    - SCREENING: Quick external assessment
    - DUE_DILIGENCE: Deep dive with internal access
    - QUARTERLY: Regular portfolio monitoring
    - EXIT_PREP: Pre-exit assessment
    """
    SCREENING = "screening"
    DUE_DILIGENCE = "due_diligence"
    QUARTERLY = "quarterly"
    EXIT_PREP = "exit_prep"


class AssessmentStatus(str, Enum):
    """
    Current status of an assessment.
    
    Case Study Section 3.2.1:
    - DRAFT: Initial state
    - IN_PROGRESS: Work in progress
    - SUBMITTED: Completed and submitted
    - APPROVED: Reviewed and approved
    - SUPERSEDED: Replaced by newer assessment
    """
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


# ============================================================================
# Status State Machine (Valid Transitions)
# ============================================================================

VALID_STATUS_TRANSITIONS: dict[AssessmentStatus, list[AssessmentStatus]] = {
    AssessmentStatus.DRAFT: [
        AssessmentStatus.IN_PROGRESS,
        AssessmentStatus.SUPERSEDED
    ],
    AssessmentStatus.IN_PROGRESS: [
        AssessmentStatus.SUBMITTED,
        AssessmentStatus.DRAFT,
        AssessmentStatus.SUPERSEDED
    ],
    AssessmentStatus.SUBMITTED: [
        AssessmentStatus.APPROVED,
        AssessmentStatus.IN_PROGRESS,
        AssessmentStatus.SUPERSEDED
    ],
    AssessmentStatus.APPROVED: [
        AssessmentStatus.SUPERSEDED
    ],
    AssessmentStatus.SUPERSEDED: []  # Terminal state
}


# ============================================================================
# Pydantic Models
# ============================================================================

class AssessmentBase(BaseModel):
    """
    Base model for Assessment with common fields.
    
    Requirements from Case Study Section 3.2.3:
    - Company foreign key reference
    - Assessment type (enum)
    - Assessment date
    - Status with state machine validation
    - Optional VR score (0-100)
    - Confidence interval (lower, upper bounds)
    - Assessor information (primary and secondary)
    """
    company_id: UUID = Field(
        ...,
        description="Foreign key reference to company"
    )
    assessment_type: AssessmentType = Field(
        ...,
        description="Type of assessment"
    )
    assessment_date: datetime = Field(
        default_factory=lambda: datetime.now(),
        description="Date of assessment"
    )
    primary_assessor: Optional[str] = Field(
        None,
        max_length=255,
        description="Primary assessor name"
    )
    secondary_assessor: Optional[str] = Field(
        None,
        max_length=255,
        description="Secondary assessor name (optional)"
    )


class AssessmentCreate(AssessmentBase):
    """
    Model for creating a new assessment.
    Inherits all validation from AssessmentBase.
    """
    pass


class AssessmentUpdate(BaseModel):
    """
    Model for updating an existing assessment.
    All fields are optional to support partial updates.
    """
    assessment_type: Optional[AssessmentType] = None
    assessment_date: Optional[datetime] = None
    status: Optional[AssessmentStatus] = None
    v_r_score: Optional[float] = Field(None, ge=0, le=100)
    confidence_lower: Optional[float] = Field(None, ge=0, le=100)
    confidence_upper: Optional[float] = Field(None, ge=0, le=100)
    primary_assessor: Optional[str] = Field(None, max_length=255)
    secondary_assessor: Optional[str] = Field(None, max_length=255)


class AssessmentResponse(AssessmentBase):
    """
    Model for assessment responses from the API.
    Includes system-generated fields and optional calculated fields.
    
    Requirements from PDF Section 3.2.3:
    - UUID primary key
    - Status (defaults to DRAFT)
    - Optional VR score (0-100)
    - Confidence interval with validation
    """
    id: UUID = Field(..., description="Unique assessment identifier")
    status: AssessmentStatus = Field(
        default=AssessmentStatus.DRAFT,
        description="Current status"
    )
    v_r_score: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Value-Readiness score (calculated in Case Study 3)"
    )
    confidence_lower: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Lower bound of confidence interval"
    )
    confidence_upper: Optional[float] = Field(
        None,
        ge=0,
        le=100,
        description="Upper bound of confidence interval"
    )
    created_at: datetime = Field(..., description="Creation timestamp")
    
    @model_validator(mode='after')
    def validate_confidence_interval(self) -> 'AssessmentResponse':
        """
        Validate that confidence_upper >= confidence_lower.
        
        From PDF Section 3.2.3:
        "Confidence interval (lower, upper bounds)" must be logically consistent.
        
        Raises:
            ValueError: If upper bound < lower bound
        """
        if (self.confidence_upper is not None and
            self.confidence_lower is not None and
            self.confidence_upper < self.confidence_lower):
            raise ValueError(
                f"confidence_upper ({self.confidence_upper}) must be >= "
                f"confidence_lower ({self.confidence_lower})"
            )
        return self
    
    model_config = {"from_attributes": True}


# ============================================================================
# Status Transition Validation
# ============================================================================

def validate_status_transition(
    current_status: AssessmentStatus,
    new_status: AssessmentStatus
) -> bool:
    """
    Validate if a status transition is allowed.
    
    Args:
        current_status: Current assessment status
        new_status: Requested new status
        
    Returns:
        bool: True if transition is valid, False otherwise
        
    Example:
        >>> validate_status_transition(AssessmentStatus.DRAFT, AssessmentStatus.IN_PROGRESS)
        True
        >>> validate_status_transition(AssessmentStatus.APPROVED, AssessmentStatus.DRAFT)
        False
    """
    allowed_transitions = VALID_STATUS_TRANSITIONS.get(current_status, [])
    return new_status in allowed_transitions


def get_allowed_transitions(current_status: AssessmentStatus) -> list[AssessmentStatus]:
    """
    Get list of allowed status transitions from current status.
    
    Args:
        current_status: Current assessment status
        
    Returns:
        List of allowed next statuses
        
    Example:
        >>> get_allowed_transitions(AssessmentStatus.DRAFT)
        [<AssessmentStatus.IN_PROGRESS: 'in_progress'>, <AssessmentStatus.SUPERSEDED: 'superseded'>]
    """
    return VALID_STATUS_TRANSITIONS.get(current_status, [])

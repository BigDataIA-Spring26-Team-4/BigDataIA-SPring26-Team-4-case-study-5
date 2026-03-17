"""
Signal models for external evidence collection.

Case Study 2: Defines data structures for external signals
(job postings, tech stack, patents, leadership) that indicate
actual AI investment vs. just rhetoric.
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class SignalCategory(str, Enum):
    """Signal category types."""

    TECHNOLOGY_HIRING = "technology_hiring"
    INNOVATION_ACTIVITY = "innovation_activity"
    DIGITAL_PRESENCE = "digital_presence"
    LEADERSHIP_SIGNALS = "leadership_signals"


class SignalSource(str, Enum):
    """Signal data sources."""

    LINKEDIN = "linkedin"
    INDEED = "indeed"
    GLASSDOOR = "glassdoor"
    USPTO = "uspto"
    BUILTWITH = "builtwith"
    PRESS_RELEASE = "press_release"
    COMPANY_WEBSITE = "company_website"


class ExternalSignal(BaseModel):
    """A single external signal observation."""

    id: UUID = Field(default_factory=uuid4)
    company_id: UUID
    category: SignalCategory
    source: SignalSource
    signal_date: datetime
    raw_value: str  # Original observation
    normalized_score: float = Field(ge=0, le=100)
    confidence: float = Field(default=0.8, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# Default signal weights (CS2 composite scoring)
DEFAULT_SIGNAL_WEIGHTS = {
    "technology_hiring": 0.30,
    "innovation_activity": 0.25,
    "digital_presence": 0.25,
    "leadership_signals": 0.20,
}


class SignalWeights(BaseModel):
    """Configurable signal weights for composite score calculation."""

    technology_hiring: float = Field(default=0.30, ge=0, le=1)
    innovation_activity: float = Field(default=0.25, ge=0, le=1)
    digital_presence: float = Field(default=0.25, ge=0, le=1)
    leadership_signals: float = Field(default=0.20, ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights_sum(self) -> "SignalWeights":
        """Weights must sum to 1.0."""
        total = (
            self.technology_hiring
            + self.innovation_activity
            + self.digital_presence
            + self.leadership_signals
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Signal weights must sum to 1.0, got {total:.4f}"
            )
        return self


class CompanySignalSummary(BaseModel):
    """Aggregated signals for a company."""

    company_id: UUID
    ticker: str
    technology_hiring_score: float = Field(ge=0, le=100)
    innovation_activity_score: float = Field(ge=0, le=100)
    digital_presence_score: float = Field(ge=0, le=100)
    leadership_signals_score: float = Field(ge=0, le=100)
    composite_score: float = Field(ge=0, le=100)
    signal_count: int
    last_updated: datetime
    weights: SignalWeights = Field(default_factory=SignalWeights)

    @model_validator(mode="after")
    def calculate_composite(self) -> "CompanySignalSummary":
        """Calculate weighted composite score using configurable weights."""
        w = self.weights
        self.composite_score = (
            w.technology_hiring * self.technology_hiring_score
            + w.innovation_activity * self.innovation_activity_score
            + w.digital_presence * self.digital_presence_score
            + w.leadership_signals * self.leadership_signals_score
        )
        return self

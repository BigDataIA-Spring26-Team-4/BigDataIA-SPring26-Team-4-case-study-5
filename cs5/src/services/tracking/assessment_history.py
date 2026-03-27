"""
Task 9.4: Assessment History Tracking (6 pts).

Tracks assessment score history over time for trend analysis.
Uses CS3 for current scores, in-memory cache for history.

Classes:
  - AssessmentSnapshot: Point-in-time score record
  - AssessmentTrend: Trend metrics (deltas, direction)
  - AssessmentHistoryService: record, retrieve, analyze trends
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
import structlog

from services.cs3_client import CS3Client, CompanyAssessment

logger = structlog.get_logger()


@dataclass
class AssessmentSnapshot:
    """Single point-in-time assessment record."""
    company_id: str
    timestamp: datetime
    org_air: Decimal
    vr_score: Decimal
    hr_score: Decimal
    synergy_score: Decimal
    dimension_scores: Dict[str, Decimal]
    confidence_interval: tuple
    evidence_count: int
    assessor_id: str
    assessment_type: str  # "screening", "limited", "full"


@dataclass
class AssessmentTrend:
    """Trend analysis for a company over time."""
    company_id: str
    current_org_air: float
    entry_org_air: float
    delta_since_entry: float
    delta_30d: Optional[float]
    delta_90d: Optional[float]
    trend_direction: str  # "improving", "stable", "declining"
    snapshot_count: int


class AssessmentHistoryService:
    """
    Tracks assessment history using CS3 for current scores.

    Stores snapshots in-memory (with optional Snowflake persistence).
    Provides trend analysis for portfolio monitoring.
    """

    def __init__(self, cs3_client: CS3Client):
        self.cs3 = cs3_client
        self._cache: Dict[str, List[AssessmentSnapshot]] = {}

    async def record_assessment(
        self,
        company_id: str,
        assessor_id: str,
        assessment_type: str = "full",
    ) -> AssessmentSnapshot:
        """
        Record current assessment as a snapshot.

        Flow:
          1. Call CS3 get_assessment() for current scores (real data)
          2. Create snapshot with timestamp
          3. Store in history cache
          4. Return snapshot
        """
        # Get current assessment from CS3 (NO mock data)
        assessment = await self.cs3.get_assessment(company_id)

        snapshot = AssessmentSnapshot(
            company_id=company_id.upper(),
            timestamp=datetime.utcnow(),
            org_air=Decimal(str(assessment.org_air_score)),
            vr_score=Decimal(str(assessment.vr_score)),
            hr_score=Decimal(str(assessment.hr_score)),
            synergy_score=Decimal(str(assessment.synergy_score)),
            dimension_scores={
                d.value: Decimal(str(s.score))
                for d, s in assessment.dimension_scores.items()
            },
            confidence_interval=assessment.confidence_interval,
            evidence_count=assessment.evidence_count,
            assessor_id=assessor_id,
            assessment_type=assessment_type,
        )

        # Store in cache
        if company_id.upper() not in self._cache:
            self._cache[company_id.upper()] = []
        self._cache[company_id.upper()].append(snapshot)

        # Persist to Snowflake (production)
        await self._store_snapshot(snapshot)

        logger.info(
            "assessment_recorded",
            company_id=company_id,
            org_air=float(snapshot.org_air),
            assessor=assessor_id,
        )

        return snapshot

    async def _store_snapshot(self, snapshot: AssessmentSnapshot) -> None:
        """Store snapshot in Snowflake via CS1 (production path)."""
        # In production: INSERT INTO assessment_history ...
        # For now: in-memory only (cache handles it)
        pass

    async def get_history(
        self,
        company_id: str,
        days: int = 365,
    ) -> List[AssessmentSnapshot]:
        """Retrieve assessment history for a company."""
        ticker = company_id.upper()

        if ticker in self._cache:
            cutoff = datetime.utcnow() - timedelta(days=days)
            return [
                s for s in self._cache[ticker]
                if s.timestamp >= cutoff
            ]

        # In production: query Snowflake
        # SELECT * FROM assessment_history
        # WHERE company_id = ? AND timestamp >= ?
        return []

    async def calculate_trend(self, company_id: str) -> AssessmentTrend:
        """
        Calculate trend metrics from history.

        Returns direction (improving/stable/declining) based on
        entry vs current scores, plus 30d and 90d deltas.
        """
        ticker = company_id.upper()
        history = await self.get_history(ticker, days=365)

        if not history:
            # No history — get current assessment and return flat trend
            current = await self.cs3.get_assessment(ticker)
            return AssessmentTrend(
                company_id=ticker,
                current_org_air=current.org_air_score,
                entry_org_air=current.org_air_score,
                delta_since_entry=0.0,
                delta_30d=None,
                delta_90d=None,
                trend_direction="stable",
                snapshot_count=0,
            )

        # Sort chronologically
        history.sort(key=lambda s: s.timestamp)

        current = float(history[-1].org_air)
        entry = float(history[0].org_air)

        # Calculate time-based deltas
        now = datetime.utcnow()
        delta_30d = None
        delta_90d = None

        for snapshot in reversed(history):
            age_days = (now - snapshot.timestamp).days
            if age_days >= 30 and delta_30d is None:
                delta_30d = current - float(snapshot.org_air)
            if age_days >= 90 and delta_90d is None:
                delta_90d = current - float(snapshot.org_air)
                break

        # Determine trend direction
        delta = current - entry
        if delta > 5:
            direction = "improving"
        elif delta < -5:
            direction = "declining"
        else:
            direction = "stable"

        return AssessmentTrend(
            company_id=ticker,
            current_org_air=current,
            entry_org_air=entry,
            delta_since_entry=round(delta, 1),
            delta_30d=round(delta_30d, 1) if delta_30d is not None else None,
            delta_90d=round(delta_90d, 1) if delta_90d is not None else None,
            trend_direction=direction,
            snapshot_count=len(history),
        )


def create_history_service(cs3: CS3Client) -> AssessmentHistoryService:
    """Factory function for creating history service."""
    return AssessmentHistoryService(cs3)

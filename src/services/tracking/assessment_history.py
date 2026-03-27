from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class AssessmentSnapshot:
    company_id: str
    timestamp: str
    org_air_score: float
    vr_score: float
    hr_score: float
    synergy_score: float
    dimension_scores: dict
    confidence_interval: list
    evidence_count: int
    assessment_type: str = "full"


@dataclass
class AssessmentTrend:
    company_id: str
    latest_score: float
    previous_score: Optional[float]
    delta: float
    direction: str
    assessment_count: int


class AssessmentHistoryService:
    def __init__(self):
        self._store: Dict[str, List[AssessmentSnapshot]] = {}

    def record_assessment(
        self,
        company_id: str,
        scoring_result: dict,
        assessment_type: str = "full",
        evidence_count: int = 0,
    ) -> AssessmentSnapshot:
        snapshot = AssessmentSnapshot(
            company_id=company_id,
            timestamp=datetime.utcnow().isoformat(),
            org_air_score=float(scoring_result.get("org_air_score", 0.0)),
            vr_score=float(scoring_result.get("vr_score", 0.0)),
            hr_score=float(scoring_result.get("hr_score", 0.0)),
            synergy_score=float(scoring_result.get("synergy_score", 0.0)),
            dimension_scores=scoring_result.get("dimension_scores", {}),
            confidence_interval=scoring_result.get("confidence_interval", []),
            evidence_count=int(evidence_count),
            assessment_type=assessment_type,
        )

        if company_id not in self._store:
            self._store[company_id] = []

        self._store[company_id].append(snapshot)
        return snapshot

    def get_history(self, company_id: str) -> List[dict]:
        history = self._store.get(company_id, [])
        return [asdict(item) for item in history]

    def get_latest(self, company_id: str) -> Optional[dict]:
        history = self._store.get(company_id, [])
        if not history:
            return None
        return asdict(history[-1])

    def calculate_trend(self, company_id: str) -> dict:
        history = self._store.get(company_id, [])

        if not history:
            trend = AssessmentTrend(
                company_id=company_id,
                latest_score=0.0,
                previous_score=None,
                delta=0.0,
                direction="no_data",
                assessment_count=0,
            )
            return asdict(trend)

        latest = history[-1]
        previous = history[-2] if len(history) > 1 else None

        latest_score = latest.org_air_score
        previous_score = previous.org_air_score if previous else None
        delta = latest_score - previous_score if previous_score is not None else 0.0

        if previous_score is None:
            direction = "new"
        elif delta > 0:
            direction = "up"
        elif delta < 0:
            direction = "down"
        else:
            direction = "flat"

        trend = AssessmentTrend(
            company_id=company_id,
            latest_score=latest_score,
            previous_score=previous_score,
            delta=delta,
            direction=direction,
            assessment_count=len(history),
        )
        return asdict(trend)


assessment_history_service = AssessmentHistoryService()
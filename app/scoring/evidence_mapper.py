"""
Evidence-to-Dimension Mapper.

CS3 Task 5.0a: Maps CS2 signals (4 categories) + CS3 sources
(Glassdoor, Board, SEC sections) to the 7 VR dimensions with
contribution weights from the mapping matrix.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Dict, List


class Dimension(str, Enum):
    DATA_INFRASTRUCTURE = "data_infrastructure"
    AI_GOVERNANCE = "ai_governance"
    TECHNOLOGY_STACK = "technology_stack"
    TALENT = "talent"
    LEADERSHIP = "leadership"
    USE_CASE_PORTFOLIO = "use_case_portfolio"
    CULTURE = "culture"


class SignalSource(str, Enum):
    TECHNOLOGY_HIRING = "technology_hiring"
    INNOVATION_ACTIVITY = "innovation_activity"
    DIGITAL_PRESENCE = "digital_presence"
    LEADERSHIP_SIGNALS = "leadership_signals"
    SEC_ITEM_1 = "sec_item_1"
    SEC_ITEM_1A = "sec_item_1a"
    SEC_ITEM_7 = "sec_item_7"
    GLASSDOOR_REVIEWS = "glassdoor_reviews"
    BOARD_COMPOSITION = "board_composition"
    NEWS_PRESS_RELEASES = "news_press_releases"


@dataclass
class DimensionMapping:
    source: SignalSource
    primary_dimension: Dimension
    primary_weight: Decimal
    secondary_mappings: Dict[Dimension, Decimal] = field(default_factory=dict)
    reliability: Decimal = Decimal("0.8")


@dataclass
class EvidenceScore:
    source: SignalSource
    raw_score: Decimal
    confidence: Decimal
    evidence_count: int
    metadata: Dict = field(default_factory=dict)


@dataclass
class DimensionScore:
    dimension: Dimension
    score: Decimal
    contributing_sources: List[SignalSource]
    total_weight: Decimal
    confidence: Decimal


SIGNAL_TO_DIMENSION_MAP: Dict[SignalSource, DimensionMapping] = {
    SignalSource.TECHNOLOGY_HIRING: DimensionMapping(
        source=SignalSource.TECHNOLOGY_HIRING,
        primary_dimension=Dimension.TALENT,
        primary_weight=Decimal("0.70"),
        secondary_mappings={
            Dimension.TECHNOLOGY_STACK: Decimal("0.20"),
            Dimension.CULTURE: Decimal("0.10"),
        },
        reliability=Decimal("0.85"),
    ),
    SignalSource.INNOVATION_ACTIVITY: DimensionMapping(
        source=SignalSource.INNOVATION_ACTIVITY,
        primary_dimension=Dimension.TECHNOLOGY_STACK,
        primary_weight=Decimal("0.50"),
        secondary_mappings={
            Dimension.USE_CASE_PORTFOLIO: Decimal("0.30"),
            Dimension.DATA_INFRASTRUCTURE: Decimal("0.20"),
        },
        reliability=Decimal("0.80"),
    ),
    SignalSource.DIGITAL_PRESENCE: DimensionMapping(
        source=SignalSource.DIGITAL_PRESENCE,
        primary_dimension=Dimension.DATA_INFRASTRUCTURE,
        primary_weight=Decimal("0.60"),
        secondary_mappings={
            Dimension.TECHNOLOGY_STACK: Decimal("0.40"),
        },
        reliability=Decimal("0.85"),
    ),
    SignalSource.LEADERSHIP_SIGNALS: DimensionMapping(
        source=SignalSource.LEADERSHIP_SIGNALS,
        primary_dimension=Dimension.LEADERSHIP,
        primary_weight=Decimal("0.60"),
        secondary_mappings={
            Dimension.AI_GOVERNANCE: Decimal("0.25"),
            Dimension.CULTURE: Decimal("0.15"),
        },
        reliability=Decimal("0.75"),
    ),
    SignalSource.SEC_ITEM_1: DimensionMapping(
        source=SignalSource.SEC_ITEM_1,
        primary_dimension=Dimension.USE_CASE_PORTFOLIO,
        primary_weight=Decimal("0.70"),
        secondary_mappings={
            Dimension.TECHNOLOGY_STACK: Decimal("0.30"),
        },
        reliability=Decimal("0.70"),
    ),
    SignalSource.SEC_ITEM_1A: DimensionMapping(
        source=SignalSource.SEC_ITEM_1A,
        primary_dimension=Dimension.AI_GOVERNANCE,
        primary_weight=Decimal("0.80"),
        secondary_mappings={
            Dimension.DATA_INFRASTRUCTURE: Decimal("0.20"),
        },
        reliability=Decimal("0.75"),
    ),
    SignalSource.SEC_ITEM_7: DimensionMapping(
        source=SignalSource.SEC_ITEM_7,
        primary_dimension=Dimension.LEADERSHIP,
        primary_weight=Decimal("0.50"),
        secondary_mappings={
            Dimension.USE_CASE_PORTFOLIO: Decimal("0.30"),
            Dimension.DATA_INFRASTRUCTURE: Decimal("0.20"),
        },
        reliability=Decimal("0.70"),
    ),
    SignalSource.GLASSDOOR_REVIEWS: DimensionMapping(
        source=SignalSource.GLASSDOOR_REVIEWS,
        primary_dimension=Dimension.CULTURE,
        primary_weight=Decimal("0.80"),
        secondary_mappings={
            Dimension.TALENT: Decimal("0.10"),
            Dimension.LEADERSHIP: Decimal("0.10"),
        },
        reliability=Decimal("0.65"),
    ),
    SignalSource.BOARD_COMPOSITION: DimensionMapping(
        source=SignalSource.BOARD_COMPOSITION,
        primary_dimension=Dimension.AI_GOVERNANCE,
        primary_weight=Decimal("0.70"),
        secondary_mappings={
            Dimension.LEADERSHIP: Decimal("0.30"),
        },
        reliability=Decimal("0.80"),
    ),
    # CS3 Extension: News & press releases reflect deliberate public
    # AI positioning — strong signal for leadership and use cases.
    SignalSource.NEWS_PRESS_RELEASES: DimensionMapping(
        source=SignalSource.NEWS_PRESS_RELEASES,
        primary_dimension=Dimension.LEADERSHIP,
        primary_weight=Decimal("0.50"),
        secondary_mappings={
            Dimension.USE_CASE_PORTFOLIO: Decimal("0.30"),
            Dimension.CULTURE: Decimal("0.20"),
        },
        reliability=Decimal("0.85"),
    ),
}


class EvidenceMapper:
    """Maps CS2 evidence to 7 VR dimensions."""

    def __init__(self):
        self.mappings = SIGNAL_TO_DIMENSION_MAP

    def map_evidence_to_dimensions(
        self,
        evidence_scores: List[EvidenceScore],
    ) -> Dict[Dimension, DimensionScore]:
        dim_sums: Dict[Dimension, Decimal] = {d: Decimal("0") for d in Dimension}
        dim_weights: Dict[Dimension, Decimal] = {d: Decimal("0") for d in Dimension}
        dim_sources: Dict[Dimension, List[SignalSource]] = {d: [] for d in Dimension}

        for ev in evidence_scores:
            mapping = self.mappings.get(ev.source)
            if not mapping:
                continue

            effective_weight = ev.confidence * mapping.reliability

            # primary
            dim = mapping.primary_dimension
            w = mapping.primary_weight * effective_weight
            dim_sums[dim] += ev.raw_score * w
            dim_weights[dim] += w
            if ev.source not in dim_sources[dim]:
                dim_sources[dim].append(ev.source)

            # secondary
            for dim, sec_w in mapping.secondary_mappings.items():
                w = sec_w * effective_weight
                dim_sums[dim] += ev.raw_score * w
                dim_weights[dim] += w
                if ev.source not in dim_sources[dim]:
                    dim_sources[dim].append(ev.source)

        results: Dict[Dimension, DimensionScore] = {}
        for d in Dimension:
            if dim_weights[d] > Decimal("0"):
                score = dim_sums[d] / dim_weights[d]
                score = max(Decimal("0"), min(Decimal("100"), score))
                conf = min(Decimal("0.5") + dim_weights[d], Decimal("0.95"))
            else:
                score = Decimal("50")
                conf = Decimal("0.3")

            results[d] = DimensionScore(
                dimension=d,
                score=score.quantize(Decimal("0.01")),
                contributing_sources=dim_sources[d],
                total_weight=dim_weights[d].quantize(Decimal("0.0001")),
                confidence=conf.quantize(Decimal("0.01")),
            )

        return results

    def get_coverage_report(
        self,
        evidence_scores: List[EvidenceScore],
    ) -> Dict[Dimension, Dict]:
        dim_scores = self.map_evidence_to_dimensions(evidence_scores)
        report = {}
        for d in Dimension:
            ds = dim_scores[d]
            report[d] = {
                "has_evidence": len(ds.contributing_sources) > 0,
                "source_count": len(ds.contributing_sources),
                "total_weight": float(ds.total_weight),
                "confidence": float(ds.confidence),
            }
        return report

"""
Map CS2 signals to CS3 dimensions for indexing.

Task 8.0a: Evidence-to-Dimension Mapper.
CS2 produces signal categories (technology_hiring, innovation_activity).
CS3 scoring requires dimension scores (talent, data_infrastructure).
This mapper bridges the gap using CS3's signal-to-dimension mapping matrix.

The weights define how strongly each signal category contributes to
each dimension. For example, technology_hiring contributes 70% to
talent, 20% to technology_stack, and 10% to culture.
"""

from typing import Dict

from src.services.integration.cs2_client import SignalCategory, SourceType
from src.services.integration.cs3_client import Dimension


# ============================================================================
# Signal-to-Dimension Mapping Matrix (from CS4 PDF Task 8.0a)
# ============================================================================

SIGNAL_TO_DIMENSION_MAP: Dict[SignalCategory, Dict[Dimension, float]] = {
    SignalCategory.TECHNOLOGY_HIRING: {
        Dimension.TALENT: 0.70,
        Dimension.TECHNOLOGY_STACK: 0.20,
        Dimension.CULTURE: 0.10,
    },
    SignalCategory.INNOVATION_ACTIVITY: {
        Dimension.TECHNOLOGY_STACK: 0.50,
        Dimension.USE_CASE_PORTFOLIO: 0.30,
        Dimension.DATA_INFRASTRUCTURE: 0.20,
    },
    SignalCategory.DIGITAL_PRESENCE: {
        Dimension.DATA_INFRASTRUCTURE: 0.60,
        Dimension.TECHNOLOGY_STACK: 0.40,
    },
    SignalCategory.LEADERSHIP_SIGNALS: {
        Dimension.LEADERSHIP: 0.60,
        Dimension.AI_GOVERNANCE: 0.25,
        Dimension.CULTURE: 0.15,
    },
    SignalCategory.CULTURE_SIGNALS: {
        Dimension.CULTURE: 0.80,
        Dimension.TALENT: 0.10,
        Dimension.LEADERSHIP: 0.10,
    },
    SignalCategory.GOVERNANCE_SIGNALS: {
        Dimension.AI_GOVERNANCE: 0.70,
        Dimension.LEADERSHIP: 0.30,
    },
}


# ============================================================================
# Source Type → Signal Category (for SEC filings & other typed sources)
# ============================================================================

SOURCE_TO_SIGNAL: Dict[str, SignalCategory] = {
    "sec_10k_item_1": SignalCategory.DIGITAL_PRESENCE,
    "sec_10k_item_1a": SignalCategory.GOVERNANCE_SIGNALS,
    "sec_10k_item_7": SignalCategory.LEADERSHIP_SIGNALS,
    "job_posting_linkedin": SignalCategory.TECHNOLOGY_HIRING,
    "job_posting_indeed": SignalCategory.TECHNOLOGY_HIRING,
    "patent_uspto": SignalCategory.INNOVATION_ACTIVITY,
    "glassdoor_review": SignalCategory.CULTURE_SIGNALS,
    "board_proxy_def14a": SignalCategory.GOVERNANCE_SIGNALS,
    "press_release": SignalCategory.LEADERSHIP_SIGNALS,
    "news_article": SignalCategory.LEADERSHIP_SIGNALS,
    "analyst_interview": SignalCategory.LEADERSHIP_SIGNALS,
    "dd_data_room": SignalCategory.DIGITAL_PRESENCE,
}


# ============================================================================
# Dimension Mapper
# ============================================================================


class DimensionMapper:
    """Map CS2 evidence to CS3 dimensions."""

    def get_dimension_weights(
        self, signal_category: SignalCategory
    ) -> Dict[Dimension, float]:
        """
        Get dimension weights for a signal category.

        Returns a dict mapping each relevant Dimension to its weight.
        If the signal category is unknown, defaults to data_infrastructure=1.0.
        """
        return SIGNAL_TO_DIMENSION_MAP.get(signal_category, {
            Dimension.DATA_INFRASTRUCTURE: 1.0
        })

    def get_primary_dimension(
        self, signal_category: SignalCategory
    ) -> Dimension:
        """
        Get primary dimension (highest weight) for a signal category.

        Example: TECHNOLOGY_HIRING → TALENT (weight 0.70)
        """
        weights = self.get_dimension_weights(signal_category)
        return max(weights.items(), key=lambda x: x[1])[0]

    def get_all_dimensions_for_evidence(
        self,
        signal_category: SignalCategory,
        min_weight: float = 0.1,
    ) -> Dict[Dimension, float]:
        """
        Get all dimensions with weight >= threshold.

        Useful for multi-label indexing where evidence contributes
        to multiple dimensions.
        """
        weights = self.get_dimension_weights(signal_category)
        return {d: w for d, w in weights.items() if w >= min_weight}

    def get_signal_for_source(self, source_type: SourceType) -> SignalCategory:
        """
        Get the signal category for a given source type.

        Uses the SOURCE_TO_SIGNAL mapping.
        """
        return SOURCE_TO_SIGNAL.get(
            source_type.value,
            SignalCategory.LEADERSHIP_SIGNALS,
        )

    def get_primary_dimension_for_source(
        self, source_type: SourceType
    ) -> Dimension:
        """
        Get primary dimension for a source type (convenience method).

        Chains: SourceType → SignalCategory → Primary Dimension
        Example: SEC_10K_ITEM_1 → DIGITAL_PRESENCE → DATA_INFRASTRUCTURE
        """
        signal = self.get_signal_for_source(source_type)
        return self.get_primary_dimension(signal)

"""
Tests for CS4 Phase 1: Integration Layer.

Tests:
  - Dimension Mapper (Task 8.0a) — pure logic, no mocks needed
  - CS1 Client local fallback (Task 7.0a)
  - CS3 Client local fallback (Task 7.0c)
  - CS2 Evidence enums (Task 7.0b)
  - Rubrics API endpoint (Phase 0)
"""

import json
import asyncio
from pathlib import Path

import pytest


# ============================================================================
# Task 8.0a: Dimension Mapper Tests
# ============================================================================


class TestDimensionMapper:
    """Test the signal-to-dimension mapping (Task 8.0a, 5 pts)."""

    def test_all_signal_categories_mapped(self):
        """Every SignalCategory has a mapping in SIGNAL_TO_DIMENSION_MAP."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.retrieval.dimension_mapper import SIGNAL_TO_DIMENSION_MAP

        for cat in SignalCategory:
            assert cat in SIGNAL_TO_DIMENSION_MAP, f"{cat.value} missing from mapping"

    def test_weights_sum_to_one(self):
        """Each signal category's dimension weights must sum to 1.0."""
        from src.services.retrieval.dimension_mapper import SIGNAL_TO_DIMENSION_MAP

        for cat, weights in SIGNAL_TO_DIMENSION_MAP.items():
            total = sum(weights.values())
            assert abs(total - 1.0) < 0.001, (
                f"{cat.value} weights sum to {total}, expected 1.0"
            )

    def test_primary_dimension_technology_hiring(self):
        """TECHNOLOGY_HIRING should primarily map to TALENT."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()
        primary = mapper.get_primary_dimension(SignalCategory.TECHNOLOGY_HIRING)
        assert primary == Dimension.TALENT

    def test_primary_dimension_innovation(self):
        """INNOVATION_ACTIVITY should primarily map to TECHNOLOGY_STACK."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()
        primary = mapper.get_primary_dimension(SignalCategory.INNOVATION_ACTIVITY)
        assert primary == Dimension.TECHNOLOGY_STACK

    def test_primary_dimension_digital_presence(self):
        """DIGITAL_PRESENCE should primarily map to DATA_INFRASTRUCTURE."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()
        primary = mapper.get_primary_dimension(SignalCategory.DIGITAL_PRESENCE)
        assert primary == Dimension.DATA_INFRASTRUCTURE

    def test_primary_dimension_culture(self):
        """CULTURE_SIGNALS should primarily map to CULTURE."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()
        primary = mapper.get_primary_dimension(SignalCategory.CULTURE_SIGNALS)
        assert primary == Dimension.CULTURE

    def test_primary_dimension_governance(self):
        """GOVERNANCE_SIGNALS should primarily map to AI_GOVERNANCE."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()
        primary = mapper.get_primary_dimension(SignalCategory.GOVERNANCE_SIGNALS)
        assert primary == Dimension.AI_GOVERNANCE

    def test_min_weight_filter(self):
        """get_all_dimensions_for_evidence respects min_weight threshold."""
        from src.services.integration.cs2_client import SignalCategory
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()

        # TECHNOLOGY_HIRING: talent=0.70, tech_stack=0.20, culture=0.10
        dims_all = mapper.get_all_dimensions_for_evidence(
            SignalCategory.TECHNOLOGY_HIRING, min_weight=0.1
        )
        assert len(dims_all) == 3  # All three pass 0.1 threshold

        dims_filtered = mapper.get_all_dimensions_for_evidence(
            SignalCategory.TECHNOLOGY_HIRING, min_weight=0.25
        )
        assert len(dims_filtered) == 1  # Only talent (0.70) passes 0.25

    def test_source_to_signal_mapping(self):
        """SOURCE_TO_SIGNAL covers all SourceType values."""
        from src.services.integration.cs2_client import SourceType
        from src.services.retrieval.dimension_mapper import SOURCE_TO_SIGNAL

        for st in SourceType:
            assert st.value in SOURCE_TO_SIGNAL, (
                f"SourceType.{st.name} ({st.value}) missing from SOURCE_TO_SIGNAL"
            )

    def test_source_to_primary_dimension(self):
        """End-to-end: SourceType → SignalCategory → Primary Dimension."""
        from src.services.integration.cs2_client import SourceType
        from src.services.integration.cs3_client import Dimension
        from src.services.retrieval.dimension_mapper import DimensionMapper

        mapper = DimensionMapper()

        # SEC 10-K Item 1 → digital_presence → data_infrastructure
        dim = mapper.get_primary_dimension_for_source(SourceType.SEC_10K_ITEM_1)
        assert dim == Dimension.DATA_INFRASTRUCTURE

        # Job posting → technology_hiring → talent
        dim = mapper.get_primary_dimension_for_source(SourceType.JOB_POSTING_LINKEDIN)
        assert dim == Dimension.TALENT

        # Patent → innovation_activity → technology_stack
        dim = mapper.get_primary_dimension_for_source(SourceType.PATENT_USPTO)
        assert dim == Dimension.TECHNOLOGY_STACK

        # Glassdoor → culture_signals → culture
        dim = mapper.get_primary_dimension_for_source(SourceType.GLASSDOOR_REVIEW)
        assert dim == Dimension.CULTURE


# ============================================================================
# Task 7.0a: CS1 Client Tests (local fallback)
# ============================================================================


class TestCS1ClientLocal:
    """Test CS1 Client's local fallback mode (Task 7.0a, 5 pts)."""

    def test_load_nvda_from_local(self):
        """Load NVIDIA company data from results/nvda.json."""
        from src.services.integration.cs1_client import CS1Client, Sector

        client = CS1Client(base_url="http://localhost:99999")  # Intentionally bad URL
        company = client._load_from_local("NVDA")

        assert company.ticker == "NVDA"
        assert company.name == "NVIDIA"
        assert company.sector == Sector.TECHNOLOGY
        assert 0.0 <= company.market_cap_percentile <= 1.0
        assert -1.0 <= company.position_factor <= 1.0

    def test_load_jpm_from_local(self):
        """Load JPMorgan from results/jpm.json."""
        from src.services.integration.cs1_client import CS1Client, Sector

        client = CS1Client()
        company = client._load_from_local("JPM")

        assert company.ticker == "JPM"
        assert company.sector == Sector.FINANCIAL_SERVICES

    def test_load_wmt_from_local(self):
        """Load Walmart from results/wmt.json."""
        from src.services.integration.cs1_client import CS1Client, Sector

        client = CS1Client()
        company = client._load_from_local("WMT")

        assert company.ticker == "WMT"
        assert company.sector == Sector.RETAIL

    def test_load_all_portfolio_companies(self):
        """All 5 portfolio companies load from local fallback."""
        from src.services.integration.cs1_client import CS1Client

        client = CS1Client()
        companies = client._load_all_local()

        tickers = {c.ticker for c in companies}
        assert tickers == {"NVDA", "JPM", "WMT", "GE", "DG"}

    def test_sector_filter_local(self):
        """Sector filter works on local fallback data."""
        from src.services.integration.cs1_client import CS1Client, Sector

        client = CS1Client()
        retail = client._load_all_local(sector=Sector.RETAIL)

        assert all(c.sector == Sector.RETAIL for c in retail)
        assert len(retail) >= 1  # At least WMT

    def test_invalid_ticker_raises(self):
        """Loading a non-existent ticker raises ValueError."""
        from src.services.integration.cs1_client import CS1Client

        client = CS1Client()
        with pytest.raises(ValueError, match="No data available"):
            client._load_from_local("FAKE_TICKER_XYZ")


# ============================================================================
# Task 7.0c: CS3 Client Tests (local fallback)
# ============================================================================


class TestCS3ClientLocal:
    """Test CS3 Client's local fallback mode (Task 7.0c, 7 pts)."""

    def test_load_nvda_assessment(self):
        """Parse NVIDIA scoring result from results/nvda.json."""
        from src.services.integration.cs3_client import CS3Client, Dimension

        client = CS3Client()
        data = client._load_local_result("NVDA")
        assert data is not None

        assessment = client._parse_result_json("NVDA", data)

        assert assessment.company_id == "NVDA"
        assert assessment.org_air_score > 0
        assert assessment.vr_score > 0
        assert assessment.hr_score > 0
        assert Dimension.DATA_INFRASTRUCTURE in assessment.dimension_scores
        assert Dimension.TALENT in assessment.dimension_scores
        assert len(assessment.dimension_scores) == 7

    def test_dimension_score_levels(self):
        """Dimension scores map to correct ScoreLevels."""
        from src.services.integration.cs3_client import (
            CS3Client, Dimension, ScoreLevel,
        )

        client = CS3Client()
        data = client._load_local_result("NVDA")
        assessment = client._parse_result_json("NVDA", data)

        di_score = assessment.dimension_scores[Dimension.DATA_INFRASTRUCTURE]
        # NVDA data_infrastructure is 93.69 → should be Level 5
        assert di_score.level == ScoreLevel.LEVEL_5
        assert di_score.score >= 80

    def test_score_to_level_mapping(self):
        """score_to_level correctly maps score ranges."""
        from src.services.integration.cs3_client import score_to_level, ScoreLevel

        assert score_to_level(95) == ScoreLevel.LEVEL_5
        assert score_to_level(80) == ScoreLevel.LEVEL_5
        assert score_to_level(79) == ScoreLevel.LEVEL_4
        assert score_to_level(60) == ScoreLevel.LEVEL_4
        assert score_to_level(59) == ScoreLevel.LEVEL_3
        assert score_to_level(40) == ScoreLevel.LEVEL_3
        assert score_to_level(39) == ScoreLevel.LEVEL_2
        assert score_to_level(20) == ScoreLevel.LEVEL_2
        assert score_to_level(19) == ScoreLevel.LEVEL_1
        assert score_to_level(0) == ScoreLevel.LEVEL_1

    def test_all_five_companies_have_results(self):
        """All 5 portfolio companies have local result files."""
        from src.services.integration.cs3_client import CS3Client

        client = CS3Client()
        for ticker in ["NVDA", "JPM", "WMT", "GE", "DG"]:
            data = client._load_local_result(ticker)
            assert data is not None, f"Missing results/{ticker.lower()}.json"
            assert "final_score" in data
            assert "dimension_scores" in data

    def test_confidence_interval_present(self):
        """Assessment has valid confidence interval."""
        from src.services.integration.cs3_client import CS3Client

        client = CS3Client()
        data = client._load_local_result("NVDA")
        assessment = client._parse_result_json("NVDA", data)

        ci_lower, ci_upper = assessment.confidence_interval
        assert ci_lower <= assessment.org_air_score <= ci_upper

    def test_rubric_local_fallback(self):
        """Rubric local fallback loads from app.scoring.rubric_scorer."""
        from src.services.integration.cs3_client import (
            CS3Client, Dimension, ScoreLevel,
        )

        client = CS3Client()
        rubrics = client._load_local_rubric(Dimension.DATA_INFRASTRUCTURE)

        assert len(rubrics) == 5  # 5 levels
        assert rubrics[0].level == ScoreLevel.LEVEL_5  # Sorted descending

        # Check that keywords exist
        level5 = rubrics[0]
        assert len(level5.keywords) > 0
        assert any("snowflake" in kw or "databricks" in kw for kw in level5.keywords)

    def test_rubric_level_filter(self):
        """Rubric level filter returns only the specified level."""
        from src.services.integration.cs3_client import (
            CS3Client, Dimension, ScoreLevel,
        )

        client = CS3Client()
        rubrics = client._load_local_rubric(
            Dimension.DATA_INFRASTRUCTURE,
            level=ScoreLevel.LEVEL_4,
        )

        assert len(rubrics) == 1
        assert rubrics[0].level == ScoreLevel.LEVEL_4


# ============================================================================
# Task 7.0b: CS2 Evidence Enum Tests
# ============================================================================


class TestCS2EvidenceEnums:
    """Test CS2 Evidence enums and mappings (Task 7.0b, 8 pts)."""

    def test_source_types_complete(self):
        """All 12 SourceType values are defined."""
        from src.services.integration.cs2_client import SourceType

        assert len(SourceType) >= 12

    def test_signal_categories_complete(self):
        """All 6 SignalCategory values are defined."""
        from src.services.integration.cs2_client import SignalCategory

        assert len(SignalCategory) == 6

    def test_source_to_signal_static_method(self):
        """CS2Client._source_to_signal maps all source types."""
        from src.services.integration.cs2_client import CS2Client, SourceType, SignalCategory

        for st in SourceType:
            result = CS2Client._source_to_signal(st)
            assert isinstance(result, SignalCategory)

    def test_cs2_evidence_dataclass(self):
        """CS2Evidence can be constructed with required fields."""
        from src.services.integration.cs2_client import (
            CS2Evidence, SourceType, SignalCategory,
        )
        from datetime import datetime

        evidence = CS2Evidence(
            evidence_id="test_001",
            company_id="NVDA",
            source_type=SourceType.SEC_10K_ITEM_1,
            signal_category=SignalCategory.DIGITAL_PRESENCE,
            content="NVIDIA maintains world-class data infrastructure...",
            extracted_at=datetime.now(),
            confidence=0.9,
        )

        assert evidence.evidence_id == "test_001"
        assert evidence.indexed_in_cs4 is False
        assert evidence.fiscal_year is None


# ============================================================================
# Phase 0: Rubrics API Tests
# ============================================================================


class TestRubricsAPI:
    """Test the rubrics API endpoint added in Phase 0."""

    def test_rubric_dimensions_list(self):
        """DIMENSION_RUBRICS has all 7 dimensions."""
        from app.scoring.rubric_scorer import DIMENSION_RUBRICS

        expected = {
            "data_infrastructure", "ai_governance", "technology_stack",
            "talent", "leadership", "use_case_portfolio", "culture",
        }
        assert set(DIMENSION_RUBRICS.keys()) == expected

    def test_each_dimension_has_5_levels(self):
        """Each dimension has rubrics for all 5 score levels."""
        from app.scoring.rubric_scorer import DIMENSION_RUBRICS, ScoreLevel

        for dim, rubric in DIMENSION_RUBRICS.items():
            assert len(rubric) == 5, f"{dim} has {len(rubric)} levels, expected 5"
            levels = {level for level in rubric.keys()}
            expected_levels = {
                ScoreLevel.LEVEL_5, ScoreLevel.LEVEL_4, ScoreLevel.LEVEL_3,
                ScoreLevel.LEVEL_2, ScoreLevel.LEVEL_1,
            }
            assert levels == expected_levels, f"{dim} missing levels"

    def test_rubric_criteria_have_keywords(self):
        """Every rubric criteria has at least 1 keyword."""
        from app.scoring.rubric_scorer import DIMENSION_RUBRICS

        for dim, rubric in DIMENSION_RUBRICS.items():
            for level, criteria in rubric.items():
                assert len(criteria.keywords) >= 1, (
                    f"{dim} {level} has no keywords"
                )

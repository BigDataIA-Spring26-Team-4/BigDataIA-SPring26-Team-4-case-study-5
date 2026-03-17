"""
Tests for the complete scoring engine.

Includes property-based tests with Hypothesis (500 examples as required).
"""

import pytest
from decimal import Decimal
from hypothesis import given, settings as h_settings, strategies as st

from app.scoring.evidence_mapper import (
    EvidenceMapper, EvidenceScore, SignalSource, Dimension,
)
from app.scoring.rubric_scorer import RubricScorer, ScoreLevel
from app.scoring.talent_concentration import TalentConcentrationCalculator, JobAnalysis
from app.scoring.vr_calculator import VRCalculator
from app.scoring.position_factor import PositionFactorCalculator
from app.scoring.hr_calculator import HRCalculator
from app.scoring.confidence import ConfidenceCalculator
from app.scoring.synergy_calculator import SynergyCalculator
from app.scoring.org_air_calculator import OrgAIRCalculator
from app.scoring.integration_service import ScoringIntegrationService


# ── Evidence Mapper ──────────────────────────────────────────────────

class TestEvidenceMapper:
    def setup_method(self):
        self.mapper = EvidenceMapper()

    def test_all_dimensions_returned(self):
        result = self.mapper.map_evidence_to_dimensions([])
        assert len(result) == 7
        assert set(result.keys()) == set(Dimension)

    def test_missing_evidence_defaults_to_50(self):
        result = self.mapper.map_evidence_to_dimensions([])
        for d, ds in result.items():
            assert ds.score == Decimal("50")
            assert ds.confidence == Decimal("0.30")

    def test_single_signal_maps_correctly(self):
        ev = EvidenceScore(
            source=SignalSource.TECHNOLOGY_HIRING,
            raw_score=Decimal("80"), confidence=Decimal("0.9"), evidence_count=5,
        )
        result = self.mapper.map_evidence_to_dimensions([ev])
        assert result[Dimension.TALENT].score > Decimal("50")
        assert SignalSource.TECHNOLOGY_HIRING in result[Dimension.TALENT].contributing_sources

    def test_multiple_signals(self):
        signals = [
            EvidenceScore(SignalSource.TECHNOLOGY_HIRING, Decimal("90"), Decimal("0.9"), 10),
            EvidenceScore(SignalSource.DIGITAL_PRESENCE, Decimal("85"), Decimal("0.8"), 5),
            EvidenceScore(SignalSource.BOARD_COMPOSITION, Decimal("70"), Decimal("0.8"), 3),
        ]
        result = self.mapper.map_evidence_to_dimensions(signals)
        for d in Dimension:
            assert Decimal("0") <= result[d].score <= Decimal("100")

    def test_coverage_report(self):
        ev = EvidenceScore(SignalSource.TECHNOLOGY_HIRING, Decimal("80"), Decimal("0.9"), 5)
        report = self.mapper.get_coverage_report([ev])
        assert report[Dimension.TALENT]["has_evidence"] is True
        assert report[Dimension.TALENT]["source_count"] >= 1

    def test_more_evidence_higher_confidence(self):
        one = [EvidenceScore(SignalSource.TECHNOLOGY_HIRING, Decimal("70"), Decimal("0.8"), 5)]
        two = one + [EvidenceScore(SignalSource.DIGITAL_PRESENCE, Decimal("60"), Decimal("0.8"), 3)]
        r1 = self.mapper.map_evidence_to_dimensions(one)
        r2 = self.mapper.map_evidence_to_dimensions(two)
        # data_infrastructure gets signal from digital_presence
        assert r2[Dimension.DATA_INFRASTRUCTURE].confidence >= r1[Dimension.DATA_INFRASTRUCTURE].confidence

    @given(score=st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False))
    @h_settings(max_examples=500)
    def test_property_scores_bounded(self, score):
        ev = EvidenceScore(SignalSource.TECHNOLOGY_HIRING, score, Decimal("0.8"), 1)
        result = self.mapper.map_evidence_to_dimensions([ev])
        for d in Dimension:
            assert Decimal("0") <= result[d].score <= Decimal("100")

    @given(score=st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False))
    @h_settings(max_examples=500)
    def test_property_all_seven_returned(self, score):
        ev = EvidenceScore(SignalSource.DIGITAL_PRESENCE, score, Decimal("0.8"), 1)
        result = self.mapper.map_evidence_to_dimensions([ev])
        assert len(result) == 7


# ── Rubric Scorer ────────────────────────────────────────────────────

class TestRubricScorer:
    def setup_method(self):
        self.scorer = RubricScorer()

    def test_high_talent_keywords(self):
        text = "Large AI research team with ML platform, principal ml engineers, staff ml"
        result = self.scorer.score_dimension("talent", text, {"ai_job_ratio": 0.5})
        assert result.level == ScoreLevel.LEVEL_5
        assert result.score >= Decimal("80")

    def test_no_keywords_defaults(self):
        result = self.scorer.score_dimension("talent", "random text", {})
        assert result.score == Decimal("30")
        assert result.level == ScoreLevel.LEVEL_2

    def test_all_dimensions_scored(self):
        evidence = {d: "some generic text" for d in [
            "data_infrastructure", "ai_governance", "technology_stack",
            "talent", "leadership", "use_case_portfolio", "culture"
        ]}
        metrics = {d: {} for d in evidence}
        results = self.scorer.score_all_dimensions(evidence, metrics)
        assert len(results) == 7

    def test_culture_keywords(self):
        text = "innovative data-driven fail-fast experimentation growth mindset"
        result = self.scorer.score_dimension("culture", text, {})
        assert result.level in (ScoreLevel.LEVEL_5, ScoreLevel.LEVEL_4)

    def test_data_infra_level_4(self):
        text = "hybrid cloud with azure and aws data warehouse using etl pipelines"
        result = self.scorer.score_dimension("data_infrastructure", text, {})
        assert result.level in (ScoreLevel.LEVEL_4, ScoreLevel.LEVEL_3)

    def test_governance_level_5(self):
        text = "CAIO reports to CEO, board committee for AI, comprehensive model risk management"
        result = self.scorer.score_dimension("ai_governance", text, {})
        assert result.level == ScoreLevel.LEVEL_5


# ── Talent Concentration ─────────────────────────────────────────────

class TestTalentConcentration:
    def setup_method(self):
        self.calc = TalentConcentrationCalculator()

    def test_distributed_team(self):
        analysis = JobAnalysis(
            total_ai_jobs=25, senior_ai_jobs=3, mid_ai_jobs=12,
            entry_ai_jobs=10, unique_skills={"python", "pytorch", "tensorflow",
            "spark", "kubernetes", "docker", "aws", "sagemaker", "mlflow",
            "huggingface", "langchain", "openai", "azure", "gcp", "scikit-learn"},
        )
        tc = self.calc.calculate_tc(analysis)
        assert tc < Decimal("0.25")

    def test_concentrated_team(self):
        analysis = JobAnalysis(
            total_ai_jobs=2, senior_ai_jobs=2, mid_ai_jobs=0,
            entry_ai_jobs=0, unique_skills={"python"},
        )
        tc = self.calc.calculate_tc(analysis, glassdoor_individual_mentions=5, glassdoor_review_count=10)
        assert tc > Decimal("0.5")

    def test_no_jobs_defaults(self):
        analysis = JobAnalysis(0, 0, 0, 0, set())
        tc = self.calc.calculate_tc(analysis)
        assert Decimal("0") <= tc <= Decimal("1")

    def test_all_senior_high_tc(self):
        analysis = JobAnalysis(5, 5, 0, 0, {"python"})
        tc = self.calc.calculate_tc(analysis)
        assert tc > Decimal("0.4")

    def test_all_entry_low_tc(self):
        analysis = JobAnalysis(20, 0, 0, 20, {"python", "pytorch", "tensorflow",
            "spark", "kubernetes", "docker", "aws", "sagemaker", "mlflow", "openai"})
        tc = self.calc.calculate_tc(analysis)
        assert tc < Decimal("0.3")

    def test_analyze_job_postings(self):
        postings = [
            {"title": "Principal ML Engineer", "description": "python pytorch kubernetes", "is_ai_related": True},
            {"title": "Junior Data Scientist", "description": "python scikit-learn", "is_ai_related": True},
            {"title": "Sales Manager", "description": "sales crm", "is_ai_related": False},
        ]
        analysis = self.calc.analyze_job_postings(postings)
        assert analysis.total_ai_jobs == 2
        assert analysis.senior_ai_jobs == 1
        assert "python" in analysis.unique_skills

    @given(total=st.integers(min_value=0, max_value=100),
           senior=st.integers(min_value=0, max_value=50))
    @h_settings(max_examples=500)
    def test_property_tc_bounded(self, total, senior):
        senior = min(senior, total)
        analysis = JobAnalysis(total, senior, 0, 0, set())
        tc = self.calc.calculate_tc(analysis)
        assert Decimal("0") <= tc <= Decimal("1")


# ── VR Calculator ────────────────────────────────────────────────────

class TestVRCalculator:
    def setup_method(self):
        self.calc = VRCalculator()
        self.dims = [
            "data_infrastructure", "ai_governance", "technology_stack",
            "talent", "leadership", "use_case_portfolio", "culture"
        ]

    def test_uniform_scores(self):
        scores = {d: 70.0 for d in self.dims}
        result = self.calc.calculate(scores, talent_concentration=0.2)
        assert Decimal("60") <= result.vr_score <= Decimal("75")

    def test_high_scores_high_vr(self):
        scores = {d: 90.0 for d in self.dims}
        result = self.calc.calculate(scores, talent_concentration=0.1)
        assert result.vr_score > Decimal("80")

    def test_higher_scores_increase_vr(self):
        low = {d: 40.0 for d in self.dims}
        high = {d: 80.0 for d in self.dims}
        r_low = self.calc.calculate(low, talent_concentration=0.2)
        r_high = self.calc.calculate(high, talent_concentration=0.2)
        assert r_high.vr_score > r_low.vr_score

    def test_talent_concentration_penalty(self):
        scores = {d: 70.0 for d in self.dims}
        low_tc = self.calc.calculate(scores, talent_concentration=0.1)
        high_tc = self.calc.calculate(scores, talent_concentration=0.8)
        assert low_tc.vr_score > high_tc.vr_score

    def test_deterministic(self):
        scores = {"data_infrastructure": 65, "ai_governance": 70,
                   "technology_stack": 55, "talent": 80,
                   "leadership": 60, "use_case_portfolio": 50, "culture": 45}
        r1 = self.calc.calculate(scores, talent_concentration=0.3)
        r2 = self.calc.calculate(scores, talent_concentration=0.3)
        assert r1.vr_score == r2.vr_score

    def test_uniform_no_cv_penalty(self):
        scores = {d: 60.0 for d in self.dims}
        result = self.calc.calculate(scores, talent_concentration=0.2)
        assert result.cv_penalty >= Decimal("0.99")

    @given(score=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
    @h_settings(max_examples=500)
    def test_property_vr_bounded(self, score):
        scores = {d: score for d in self.dims}
        result = self.calc.calculate(scores)
        assert Decimal("0") <= result.vr_score <= Decimal("100")


# ── Position Factor ──────────────────────────────────────────────────

class TestPositionFactor:
    def setup_method(self):
        self.calc = PositionFactorCalculator()

    def test_leader(self):
        pf = self.calc.calculate_position_factor(90.0, "technology", 0.95)
        assert pf > Decimal("0")

    def test_laggard(self):
        pf = self.calc.calculate_position_factor(20.0, "technology", 0.1)
        assert pf < Decimal("0")

    def test_average(self):
        pf = self.calc.calculate_position_factor(65.0, "technology", 0.5)
        assert abs(pf) < Decimal("0.1")

    @given(vr=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
           mcap=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
    @h_settings(max_examples=500)
    def test_property_bounded(self, vr, mcap):
        pf = self.calc.calculate_position_factor(vr, "retail", mcap)
        assert Decimal("-1") <= pf <= Decimal("1")


# ── HR Calculator ────────────────────────────────────────────────────

class TestHRCalculator:
    def setup_method(self):
        self.calc = HRCalculator()

    def test_positive_pf_increases_hr(self):
        r1 = self.calc.calculate("technology", 0.0)
        r2 = self.calc.calculate("technology", 0.5)
        assert r2.hr_score > r1.hr_score

    def test_negative_pf_decreases_hr(self):
        r1 = self.calc.calculate("retail", 0.0)
        r2 = self.calc.calculate("retail", -0.5)
        assert r2.hr_score < r1.hr_score

    def test_delta_is_015(self):
        r = self.calc.calculate("technology", 1.0)
        # HR = 85 * (1 + 0.15 * 1.0) = 85 * 1.15 = 97.75
        assert r.hr_score == Decimal("97.75")


# ── Confidence ───────────────────────────────────────────────────────

class TestConfidence:
    def setup_method(self):
        self.calc = ConfidenceCalculator()

    def test_more_evidence_tighter_ci(self):
        r1 = self.calc.calculate(Decimal("60"), evidence_count=3)
        r2 = self.calc.calculate(Decimal("60"), evidence_count=30)
        ci_width_1 = r1.ci_upper - r1.ci_lower
        ci_width_2 = r2.ci_upper - r2.ci_lower
        assert ci_width_2 < ci_width_1

    def test_ci_contains_score(self):
        r = self.calc.calculate(Decimal("75"), evidence_count=10)
        assert r.ci_lower <= Decimal("75") <= r.ci_upper

    def test_spearman_brown_formula(self):
        r = self.calc.calculate(Decimal("50"), evidence_count=1)
        assert r.reliability == Decimal("0.7000")
        r10 = self.calc.calculate(Decimal("50"), evidence_count=10)
        assert r10.reliability > r.reliability


# ── Synergy ──────────────────────────────────────────────────────────

class TestSynergy:
    def setup_method(self):
        self.calc = SynergyCalculator()

    def test_basic(self):
        r = self.calc.calculate(Decimal("70"), Decimal("80"), alignment=0.9)
        assert r.synergy_score > Decimal("0")
        assert r.synergy_score <= Decimal("100")

    def test_zero_alignment(self):
        r = self.calc.calculate(Decimal("70"), Decimal("80"), alignment=0.0)
        assert r.synergy_score == Decimal("0.00")

    def test_timing_factor_bounds(self):
        r1 = self.calc.calculate(Decimal("70"), Decimal("80"), timing_factor=0.5)
        assert r1.timing_factor == Decimal("0.8")
        r2 = self.calc.calculate(Decimal("70"), Decimal("80"), timing_factor=1.5)
        assert r2.timing_factor == Decimal("1.2")


# ── Org-AI-R ─────────────────────────────────────────────────────────

class TestOrgAIR:
    def setup_method(self):
        self.calc = OrgAIRCalculator()

    def test_basic(self):
        r = self.calc.calculate(Decimal("70"), Decimal("80"), Decimal("50"))
        assert Decimal("0") <= r.final_score <= Decimal("100")

    def test_contributions_sum(self):
        r = self.calc.calculate(Decimal("70"), Decimal("80"), Decimal("50"))
        total = r.vr_contribution + r.hr_contribution + r.synergy_contribution
        assert abs(total - r.final_score) < Decimal("1")

    def test_alpha_060_beta_012(self):
        # Org-AI-R = 0.88 * (0.60*70 + 0.40*80) + 0.12 * 50
        # = 0.88 * (42 + 32) + 6 = 0.88 * 74 + 6 = 65.12 + 6 = 71.12
        r = self.calc.calculate(Decimal("70"), Decimal("80"), Decimal("50"))
        assert abs(r.final_score - Decimal("71.12")) < Decimal("0.1")

    @given(vr=st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False),
           hr=st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False),
           syn=st.decimals(min_value=0, max_value=100, places=2, allow_nan=False, allow_infinity=False))
    @h_settings(max_examples=500)
    def test_property_bounded(self, vr, hr, syn):
        r = self.calc.calculate(vr, hr, syn)
        assert Decimal("0") <= r.final_score <= Decimal("100")


# ── Integration Service (unit tests with mock data) ──────────────────

class TestIntegrationService:
    def setup_method(self):
        self.service = ScoringIntegrationService()

    def test_score_company_nvda_like(self):
        result = self.service.score_company(
            ticker="NVDA",
            cs2_signals={
                "technology_hiring_score": 88.0,
                "innovation_activity_score": 100.0,
                "digital_presence_score": 100.0,
                "leadership_signals_score": 58.0,
            },
            glassdoor_score=28.0,
            board_score=50.0,
            evidence_count=40,
            sec_scores={"item_1": 73.0, "item_1a": 55.0, "item_7": 71.0},
        )
        assert 60 <= result["final_score"] <= 95
        assert result["ticker"] == "NVDA"
        assert result["sector"] == "technology"
        assert len(result["dimension_scores"]) == 7

    def test_score_company_dg_like(self):
        result = self.service.score_company(
            ticker="DG",
            cs2_signals={
                "technology_hiring_score": 10.0,
                "innovation_activity_score": 0.0,
                "digital_presence_score": 22.0,
                "leadership_signals_score": 32.0,
            },
            glassdoor_score=38.0,
            board_score=20.0,
            evidence_count=30,
        )
        assert 30 <= result["final_score"] <= 60
        assert result["final_score"] < 60

    def test_ranking_order(self):
        nvda = self.service.score_company("NVDA",
            {"technology_hiring_score": 88, "innovation_activity_score": 100,
             "digital_presence_score": 100, "leadership_signals_score": 58},
            28.0, 50.0, 40, {"item_1": 73, "item_1a": 55, "item_7": 71})
        dg = self.service.score_company("DG",
            {"technology_hiring_score": 10, "innovation_activity_score": 0,
             "digital_presence_score": 22, "leadership_signals_score": 32},
            38.0, 20.0, 30)
        assert nvda["final_score"] > dg["final_score"]

    def test_all_dimension_scores_present(self):
        result = self.service.score_company("GE",
            {"technology_hiring_score": 50, "innovation_activity_score": 30,
             "digital_presence_score": 55, "leadership_signals_score": 40},
            27.0, 45.0, 30)
        dims = result["dimension_scores"]
        expected = ["data_infrastructure", "ai_governance", "technology_stack",
                    "talent", "leadership", "use_case_portfolio", "culture"]
        for d in expected:
            assert d in dims
            assert 0 <= dims[d] <= 100

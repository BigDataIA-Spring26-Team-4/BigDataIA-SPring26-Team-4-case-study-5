"""
Tests to verify MCP tools call CS1-CS4 (NO hardcoded data).

Per PDF Section 17: TAs verify by:
  1. Checking MCP tools call CS1-CS4 clients
  2. Running pytest with CS services stopped (should error)
  3. Reviewing code for hardcoded return values

Run:  cd cs5 && python -m pytest tests/ -v
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from decimal import Decimal


# ════════════════════════════════════════════════════════════════
# Fixtures: Mock CS3 Assessment
# ════════════════════════════════════════════════════════════════


def _make_mock_assessment(org_air=72.5, vr=68.0, hr=75.0, synergy=4.2):
    """Create a mock CompanyAssessment matching our dataclass shape."""
    from services.cs3_client import CompanyAssessment, DimensionScore, Dimension

    dim_scores = {}
    base_scores = {
        Dimension.DATA_INFRASTRUCTURE: 70.0,
        Dimension.AI_GOVERNANCE: 55.0,
        Dimension.TECHNOLOGY_STACK: 80.0,
        Dimension.TALENT: 75.0,
        Dimension.LEADERSHIP: 65.0,
        Dimension.USE_CASE_PORTFOLIO: 60.0,
        Dimension.CULTURE: 58.0,
    }
    for dim, score in base_scores.items():
        dim_scores[dim] = DimensionScore(
            dimension=dim, score=score, level=4 if score >= 60 else 3,
            evidence_count=5,
        )

    return CompanyAssessment(
        company_id="NVDA",
        org_air_score=org_air,
        vr_score=vr,
        hr_score=hr,
        synergy_score=synergy,
        dimension_scores=dim_scores,
        confidence_interval=(68.0, 77.0),
        evidence_count=35,
    )


def _make_mock_evidence_list(count=3):
    """Create mock CS2 Evidence items."""
    from services.cs2_client import Evidence, SourceType

    return [
        Evidence(
            evidence_id=f"ev_{i}",
            company_id="NVDA",
            source_type=SourceType.SEC_10K_ITEM_7,
            signal_category="leadership_signals",
            content=f"Test evidence content {i}",
            confidence=0.85,
        )
        for i in range(count)
    ]


# ════════════════════════════════════════════════════════════════
# Test 1: calculate_org_air_score calls CS3
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_calculate_org_air_calls_cs3():
    """Verify calculate_org_air_score calls cs3_client.get_assessment()."""
    mock_assessment = _make_mock_assessment(org_air=72.5)

    with patch("mcp_server.server.cs3_client") as mock_cs3:
        mock_cs3.get_assessment = AsyncMock(return_value=mock_assessment)

        from mcp_server.server import calculate_org_air_score
        result = await calculate_org_air_score(company_id="NVDA")

        # CRITICAL: Verify CS3 was actually called
        mock_cs3.get_assessment.assert_called_once_with("NVDA")

        # Verify result contains real data from the mock
        data = json.loads(result)
        assert data["org_air"] == 72.5
        assert data["vr_score"] == 68.0


# ════════════════════════════════════════════════════════════════
# Test 2: get_company_evidence calls CS2
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_get_company_evidence_calls_cs2():
    """Verify get_company_evidence calls cs2_client.get_evidence()."""
    mock_evidence = _make_mock_evidence_list(count=3)

    with patch("mcp_server.server.cs2_client") as mock_cs2:
        mock_cs2.get_evidence = AsyncMock(return_value=mock_evidence)

        from mcp_server.server import get_company_evidence
        result = await get_company_evidence(
            company_id="NVDA", dimension="all", limit=10
        )

        # Verify CS2 was called with correct params
        mock_cs2.get_evidence.assert_called_once_with(
            company_id="NVDA", dimension="all", limit=10,
        )

        data = json.loads(result)
        assert len(data) == 3


# ════════════════════════════════════════════════════════════════
# Test 3: generate_justification calls CS4
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_justification_calls_cs4():
    """Verify generate_justification calls cs4_client."""
    from services.cs4_client import ScoreJustification, CitedEvidence

    mock_just = ScoreJustification(
        company_id="NVDA", dimension="talent", score=75.0,
        level=4, level_name="Good",
        confidence_interval=[70.0, 80.0],
        rubric_criteria="Level 4 criteria",
        rubric_keywords=["hiring", "ML"],
        supporting_evidence=[
            CitedEvidence(
                evidence_id="e1", content="AI hiring evidence",
                source_type="job_posting_indeed", source_url=None,
                confidence=0.85, matched_keywords=["ML"], relevance_score=0.9,
            )
        ],
        gaps_identified=["Need more senior ML engineers"],
        generated_summary="NVDA has strong AI talent pipeline",
        evidence_strength="strong",
    )

    with patch("mcp_server.server.cs4_client") as mock_cs4:
        mock_cs4.generate_justification = AsyncMock(return_value=mock_just)

        from mcp_server.server import generate_justification
        result = await generate_justification(
            company_id="NVDA", dimension="talent"
        )

        mock_cs4.generate_justification.assert_called_once_with("NVDA", "talent")

        data = json.loads(result)
        assert data["score"] == 75.0
        assert data["level"] == 4


# ════════════════════════════════════════════════════════════════
# Test 4: No hardcoded data — tools error when CS is down
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_hardcoded_data_cs3_down():
    """Tools must error when CS3 is unreachable, NOT return fake data."""
    with patch("mcp_server.server.cs3_client") as mock_cs3:
        mock_cs3.get_assessment = AsyncMock(
            side_effect=ConnectionError("CS3 not running")
        )

        from mcp_server.server import calculate_org_air_score

        with pytest.raises(ConnectionError):
            await calculate_org_air_score(company_id="NVDA")


@pytest.mark.asyncio
async def test_no_hardcoded_data_cs2_down():
    """Tools must error when CS2 is unreachable, NOT return fake data."""
    with patch("mcp_server.server.cs2_client") as mock_cs2:
        mock_cs2.get_evidence = AsyncMock(
            side_effect=ConnectionError("CS2 not running")
        )

        from mcp_server.server import get_company_evidence

        with pytest.raises(ConnectionError):
            await get_company_evidence(company_id="NVDA")


@pytest.mark.asyncio
async def test_no_hardcoded_data_cs4_down():
    """Tools must error when CS4 is unreachable, NOT return fake data."""
    with patch("mcp_server.server.cs4_client") as mock_cs4:
        mock_cs4.generate_justification = AsyncMock(
            side_effect=ConnectionError("CS4 not running")
        )

        from mcp_server.server import generate_justification

        with pytest.raises(ConnectionError):
            await generate_justification(
                company_id="NVDA", dimension="talent"
            )


# ════════════════════════════════════════════════════════════════
# Test 5: HITL triggers for out-of-range scores
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_hitl_triggered_high_score():
    """Scores above 85 must trigger HITL approval."""
    from agents.specialists import ScoringAgent
    from agents.state import DueDiligenceState
    from datetime import datetime

    agent = ScoringAgent()
    mock_state: DueDiligenceState = {
        "company_id": "NVDA",
        "assessment_type": "full",
        "requested_by": "test",
        "messages": [],
        "sec_analysis": None, "talent_analysis": None,
        "scoring_result": None, "evidence_justifications": None,
        "value_creation_plan": None, "next_agent": None,
        "requires_approval": False, "approval_reason": None,
        "approval_status": None, "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    # Mock the MCP tool call to return a high score
    high_score_result = json.dumps({"org_air": 92.0, "vr_score": 90.0, "hr_score": 88.0})

    with patch("agents.specialists.get_org_air_score") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value=high_score_result)

        result = await agent.calculate(mock_state)

        assert result["requires_approval"] is True
        assert "outside normal range" in result["approval_reason"]


@pytest.mark.asyncio
async def test_hitl_triggered_low_score():
    """Scores below 40 must trigger HITL approval."""
    from agents.specialists import ScoringAgent
    from agents.state import DueDiligenceState
    from datetime import datetime

    agent = ScoringAgent()
    mock_state: DueDiligenceState = {
        "company_id": "DG",
        "assessment_type": "full",
        "requested_by": "test",
        "messages": [],
        "sec_analysis": None, "talent_analysis": None,
        "scoring_result": None, "evidence_justifications": None,
        "value_creation_plan": None, "next_agent": None,
        "requires_approval": False, "approval_reason": None,
        "approval_status": None, "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    low_score_result = json.dumps({"org_air": 35.0, "vr_score": 30.0, "hr_score": 40.0})

    with patch("agents.specialists.get_org_air_score") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value=low_score_result)

        result = await agent.calculate(mock_state)

        assert result["requires_approval"] is True
        assert "outside normal range" in result["approval_reason"]


@pytest.mark.asyncio
async def test_hitl_not_triggered_normal_score():
    """Scores within [40, 85] should NOT trigger HITL."""
    from agents.specialists import ScoringAgent
    from agents.state import DueDiligenceState
    from datetime import datetime

    agent = ScoringAgent()
    mock_state: DueDiligenceState = {
        "company_id": "JPM",
        "assessment_type": "full",
        "requested_by": "test",
        "messages": [],
        "sec_analysis": None, "talent_analysis": None,
        "scoring_result": None, "evidence_justifications": None,
        "value_creation_plan": None, "next_agent": None,
        "requires_approval": False, "approval_reason": None,
        "approval_status": None, "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    normal_score_result = json.dumps({"org_air": 65.0, "vr_score": 62.0, "hr_score": 70.0})

    with patch("agents.specialists.get_org_air_score") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value=normal_score_result)

        result = await agent.calculate(mock_state)

        assert result["requires_approval"] is False
        assert result["approval_reason"] is None


# ════════════════════════════════════════════════════════════════
# Test 6: EBITDA calculator
# ════════════════════════════════════════════════════════════════


def test_ebitda_projection_basic():
    """EBITDA calculator produces valid scenarios."""
    from services.value_creation.ebitda import ebitda_calculator

    projection = ebitda_calculator.project(
        company_id="NVDA",
        entry_score=50.0,
        exit_score=75.0,
        h_r_score=70.0,
    )

    assert projection.delta_air == 25.0
    assert projection.conservative_pct < projection.base_pct
    assert projection.base_pct < projection.optimistic_pct
    assert isinstance(projection.requires_approval, bool)


def test_ebitda_hitl_trigger():
    """EBITDA > 5% must flag requires_approval."""
    from services.value_creation.ebitda import ebitda_calculator

    # Large delta should produce > 5% EBITDA
    projection = ebitda_calculator.project(
        company_id="TEST",
        entry_score=20.0,
        exit_score=90.0,
        h_r_score=90.0,
    )

    # With 70 points of improvement and high H^R, should exceed 5%
    assert projection.delta_air == 70.0
    assert projection.risk_adjusted_pct > 5.0
    assert projection.requires_approval is True


# ════════════════════════════════════════════════════════════════
# Test 7: Fund-AI-R calculator
# ════════════════════════════════════════════════════════════════


def test_fund_air_calculation():
    """Fund-AI-R calculator produces valid metrics."""
    from services.analytics.fund_air import fund_air_calculator
    from services.integration.portfolio_data_service import PortfolioCompanyView

    companies = [
        PortfolioCompanyView(
            company_id="NVDA", ticker="NVDA", name="NVIDIA",
            sector="technology", org_air=80.0, vr_score=78.0,
            hr_score=82.0, synergy_score=5.0,
            dimension_scores={}, confidence_interval=(75, 85),
            entry_org_air=45.0, delta_since_entry=35.0, evidence_count=30,
        ),
        PortfolioCompanyView(
            company_id="DG", ticker="DG", name="Dollar General",
            sector="retail", org_air=45.0, vr_score=40.0,
            hr_score=50.0, synergy_score=2.0,
            dimension_scores={}, confidence_interval=(40, 50),
            entry_org_air=45.0, delta_since_entry=0.0, evidence_count=15,
        ),
    ]

    ev_map = {"NVDA": 500.0, "DG": 100.0}

    metrics = fund_air_calculator.calculate_fund_metrics(
        fund_id="test_fund", companies=companies, enterprise_values=ev_map,
    )

    # EV-weighted: (500*80 + 100*45) / 600 = 74166.67/600 ≈ 74.2
    assert 73.0 <= metrics.fund_air <= 75.0
    assert metrics.company_count == 2
    assert metrics.ai_leaders_count == 1   # NVDA >= 70
    assert metrics.ai_laggards_count == 1  # DG < 50
    assert 0 < metrics.sector_hhi <= 1.0


def test_fund_air_empty_portfolio():
    """Fund-AI-R must raise on empty portfolio."""
    from services.analytics.fund_air import fund_air_calculator

    with pytest.raises(ValueError, match="empty portfolio"):
        fund_air_calculator.calculate_fund_metrics(
            fund_id="empty", companies=[], enterprise_values={},
        )


# ════════════════════════════════════════════════════════════════
# Test 8: Gap analyzer
# ════════════════════════════════════════════════════════════════


def test_gap_analysis_identifies_gaps():
    """Gap analyzer identifies dimensions below target."""
    from services.value_creation.gap_analysis import gap_analyzer

    current_scores = {
        "data_infrastructure": 70.0,
        "ai_governance": 40.0,   # big gap
        "technology_stack": 80.0,
        "talent": 55.0,          # gap
        "leadership": 65.0,
        "use_case_portfolio": 45.0,  # gap
        "culture": 50.0,         # gap
    }

    result = gap_analyzer.analyze(
        company_id="TEST",
        current_scores=current_scores,
        target_org_air=75.0,
        sector="technology",
    )

    assert result["company_id"] == "TEST"
    assert result["target_org_air"] == 75.0
    assert result["overall_gap"] > 0
    assert len(result["priority_dimensions"]) == 3
    assert len(result["initiatives"]) > 0
    # ai_governance has biggest gap, should be priority
    assert "ai_governance" in result["priority_dimensions"]


# ════════════════════════════════════════════════════════════════
# Test 9: Supervisor routing logic
# ════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_supervisor_routes_to_sec_first():
    """Supervisor should route to sec_analyst when nothing is done."""
    from agents.supervisor import supervisor_node
    from datetime import datetime

    state = {
        "company_id": "NVDA", "assessment_type": "full",
        "requested_by": "test", "messages": [],
        "sec_analysis": None, "talent_analysis": None,
        "scoring_result": None, "evidence_justifications": None,
        "value_creation_plan": None, "next_agent": None,
        "requires_approval": False, "approval_reason": None,
        "approval_status": None, "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    result = await supervisor_node(state)
    assert result["next_agent"] == "sec_analyst"


@pytest.mark.asyncio
async def test_supervisor_routes_to_hitl_when_pending():
    """Supervisor routes to HITL when approval is pending."""
    from agents.supervisor import supervisor_node
    from datetime import datetime

    state = {
        "company_id": "NVDA", "assessment_type": "full",
        "requested_by": "test", "messages": [],
        "sec_analysis": {"done": True}, "talent_analysis": None,
        "scoring_result": {"org_air": 92.0}, "evidence_justifications": None,
        "value_creation_plan": None, "next_agent": None,
        "requires_approval": True,
        "approval_reason": "Score 92.0 outside [40, 85]",
        "approval_status": "pending",
        "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    result = await supervisor_node(state)
    assert result["next_agent"] == "hitl_approval"


@pytest.mark.asyncio
async def test_supervisor_routes_to_complete():
    """Supervisor routes to complete when all outputs are filled."""
    from agents.supervisor import supervisor_node
    from datetime import datetime

    state = {
        "company_id": "NVDA", "assessment_type": "full",
        "requested_by": "test", "messages": [],
        "sec_analysis": {"done": True},
        "talent_analysis": None,
        "scoring_result": {"org_air": 72.0},
        "evidence_justifications": {"done": True},
        "value_creation_plan": {"done": True},
        "next_agent": None,
        "requires_approval": False, "approval_reason": None,
        "approval_status": None, "approved_by": None,
        "started_at": datetime.utcnow(), "completed_at": None,
        "total_tokens": 0, "error": None,
    }

    result = await supervisor_node(state)
    assert result["next_agent"] == "complete"

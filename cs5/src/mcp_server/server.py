"""
PE Org-AI-R MCP Server — Tasks 9.2 + 9.3.

Exposes CS1-CS4 APIs as MCP tools for universal agent interoperability.
Uses FastMCP (built into the mcp SDK).

6 Tools:
  1. calculate_org_air_score  → CS3 scoring engine
  2. get_company_evidence     → CS2 evidence collection
  3. generate_justification   → CS4 RAG justifications
  4. project_ebitda_impact    → EBITDA calculator (v2.0 params)
  5. run_gap_analysis         → Gap analyzer (100-day plan)
  6. get_portfolio_summary    → CS1 portfolio + CS3 scores

2 Resources:
  - orgair://parameters/v2.0  → Scoring parameters
  - orgair://sectors           → Sector baselines

2 Prompts:
  - due_diligence_assessment  → Full DD workflow template
  - ic_meeting_prep           → IC package generation template

ALL tools call real CS1-CS4 services. NO mock data.
"""

import sys
import json
from pathlib import Path

# Ensure src/ is importable (works for both direct run and python -m)
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from mcp.server.fastmcp import FastMCP
import structlog

from config import settings
from services.cs1_client import CS1Client
from services.cs2_client import CS2Client
from services.cs3_client import CS3Client
from services.cs4_client import CS4Client
from services.value_creation.ebitda import ebitda_calculator
from services.value_creation.gap_analysis import gap_analyzer
from services.integration.portfolio_data_service import portfolio_data_service

logger = structlog.get_logger()

# ── Initialize MCP server ───────────────────────────────────────

mcp = FastMCP("pe-orgair-server")

# Module-level clients (v4 FIX: init at module level, not inside tools)
cs1_client = CS1Client(base_url=settings.CS1_URL)
cs2_client = CS2Client(base_url=settings.CS2_URL)
cs3_client = CS3Client(base_url=settings.CS3_URL)
cs4_client = CS4Client(base_url=settings.CS4_URL)


# ════════════════════════════════════════════════════════════════
# TOOLS — Executable functions (Task 9.2: 12 pts)
# ════════════════════════════════════════════════════════════════


@mcp.tool()
async def calculate_org_air_score(company_id: str) -> str:
    """Calculate Org-AI-R score for a company using CS3 scoring engine.

    Returns: Final score, V^R, H^R, synergy, confidence interval, dimension breakdown.

    Args:
        company_id: Company ticker (e.g., 'NVDA', 'JPM', 'WMT', 'GE', 'DG')
    """
    logger.info("mcp_tool_call", tool="calculate_org_air_score", company_id=company_id)

    assessment = await cs3_client.get_assessment(company_id)

    return json.dumps({
        "company_id": company_id.upper(),
        "org_air": assessment.org_air_score,
        "vr_score": assessment.vr_score,
        "hr_score": assessment.hr_score,
        "synergy_score": assessment.synergy_score,
        "confidence_interval": list(assessment.confidence_interval),
        "evidence_count": assessment.evidence_count,
        "dimension_scores": {
            d.value: {"score": s.score, "level": s.level, "evidence_count": s.evidence_count}
            for d, s in assessment.dimension_scores.items()
        },
    }, indent=2)


@mcp.tool()
async def get_company_evidence(
    company_id: str,
    dimension: str = "all",
    limit: int = 10,
) -> str:
    """Retrieve AI-readiness evidence for a company using CS2 evidence collection.

    Returns: Evidence items with source type, content, confidence.

    Args:
        company_id: Company ticker (e.g., 'NVDA')
        dimension: One of: data_infrastructure, ai_governance, technology_stack, talent, leadership, use_case_portfolio, culture, all
        limit: Maximum number of evidence items to return (default 10)
    """
    logger.info("mcp_tool_call", tool="get_company_evidence", company_id=company_id, dimension=dimension)

    evidence = await cs2_client.get_evidence(
        company_id=company_id,
        dimension=dimension,
        limit=limit,
    )

    return json.dumps([
        {
            "evidence_id": e.evidence_id,
            "source_type": e.source_type.value if hasattr(e.source_type, "value") else str(e.source_type),
            "signal_category": e.signal_category,
            "content": e.content[:500],
            "confidence": e.confidence,
        }
        for e in evidence
    ], indent=2)


@mcp.tool()
async def generate_justification(company_id: str, dimension: str) -> str:
    """Generate evidence-backed justification for a dimension using CS4 RAG.

    Returns: Score, level, rubric match, supporting evidence with citations, gaps.

    Args:
        company_id: Company ticker (e.g., 'NVDA')
        dimension: One of: data_infrastructure, ai_governance, technology_stack, talent, leadership, use_case_portfolio, culture
    """
    logger.info("mcp_tool_call", tool="generate_justification", company_id=company_id, dimension=dimension)

    justification = await cs4_client.generate_justification(company_id, dimension)

    return json.dumps({
        "company_id": justification.company_id,
        "dimension": justification.dimension,
        "score": justification.score,
        "level": justification.level,
        "level_name": justification.level_name,
        "evidence_strength": justification.evidence_strength,
        "rubric_criteria": justification.rubric_criteria,
        "supporting_evidence": [
            {
                "source_type": e.source_type,
                "content": e.content[:300],
                "confidence": e.confidence,
            }
            for e in justification.supporting_evidence[:5]
        ],
        "gaps_identified": justification.gaps_identified,
        "generated_summary": justification.generated_summary[:500],
    }, indent=2)


@mcp.tool()
async def project_ebitda_impact(
    company_id: str,
    entry_score: float,
    target_score: float,
    h_r_score: float,
) -> str:
    """Project EBITDA impact from AI improvements using v2.0 model.

    Returns: Conservative, base, optimistic scenarios with risk adjustment.

    Args:
        company_id: Company ticker (e.g., 'NVDA')
        entry_score: Org-AI-R at portfolio entry (0-100)
        target_score: Target Org-AI-R score (0-100)
        h_r_score: Current H^R (systematic readiness) score (0-100)
    """
    logger.info("mcp_tool_call", tool="project_ebitda_impact", company_id=company_id)

    projection = ebitda_calculator.project(
        company_id=company_id,
        entry_score=entry_score,
        exit_score=target_score,
        h_r_score=h_r_score,
    )

    return json.dumps({
        "company_id": projection.company_id,
        "delta_air": projection.delta_air,
        "scenarios": {
            "conservative": f"{projection.conservative_pct:.2f}%",
            "base": f"{projection.base_pct:.2f}%",
            "optimistic": f"{projection.optimistic_pct:.2f}%",
        },
        "risk_adjusted": f"{projection.risk_adjusted_pct:.2f}%",
        "requires_approval": projection.requires_approval,
    }, indent=2)


@mcp.tool()
async def run_gap_analysis(
    company_id: str,
    target_org_air: float = 75.0,
) -> str:
    """Analyze gaps and generate 100-day improvement plan.

    Returns: Gap by dimension, priority ranking, initiatives, investment estimate.

    Args:
        company_id: Company ticker (e.g., 'NVDA')
        target_org_air: Target Org-AI-R score (default 75.0)
    """
    logger.info("mcp_tool_call", tool="run_gap_analysis", company_id=company_id)

    # Get current scores from CS3 (real data, no mocks)
    assessment = await cs3_client.get_assessment(company_id)
    current_scores = {
        d.value: s.score for d, s in assessment.dimension_scores.items()
    }

    # Get company sector from CS1 for benchmark lookup
    try:
        company = await cs1_client.get_company(company_id)
        sector = company.sector.value
    except Exception:
        sector = "technology"

    analysis = gap_analyzer.analyze(
        company_id=company_id,
        current_scores=current_scores,
        target_org_air=target_org_air,
        sector=sector,
    )

    return json.dumps(analysis, indent=2)


@mcp.tool()
async def get_portfolio_summary(fund_id: str = "growth_fund_v") -> str:
    """Get fund portfolio summary with Fund-AI-R metric.

    Returns: Fund-AI-R, company breakdown, sector distribution.

    Args:
        fund_id: Fund identifier (default 'growth_fund_v')
    """
    logger.info("mcp_tool_call", tool="get_portfolio_summary", fund_id=fund_id)

    portfolio = await portfolio_data_service.get_portfolio_view(fund_id)

    fund_air = sum(c.org_air for c in portfolio) / len(portfolio) if portfolio else 0

    return json.dumps({
        "fund_id": fund_id,
        "fund_air": round(fund_air, 1),
        "company_count": len(portfolio),
        "companies": [
            {
                "ticker": c.ticker,
                "name": c.name,
                "sector": c.sector,
                "org_air": c.org_air,
                "vr_score": c.vr_score,
                "hr_score": c.hr_score,
                "delta_since_entry": c.delta_since_entry,
                "evidence_count": c.evidence_count,
            }
            for c in portfolio
        ],
    }, indent=2)


# ════════════════════════════════════════════════════════════════
# RESOURCES — Addressable data (Task 9.3: 8 pts)
# ════════════════════════════════════════════════════════════════


@mcp.resource("orgair://parameters/v2.0")
def get_scoring_parameters() -> str:
    """Org-AI-R v2.0 Scoring Parameters — alpha, beta, gamma values."""
    return json.dumps({
        "version": "2.0",
        "description": "Org-AI-R scoring model parameters",
        "alpha": 0.60,
        "beta": 0.12,
        "gamma_0": 0.0025,
        "gamma_1": 0.05,
        "gamma_2": 0.025,
        "gamma_3": 0.01,
        "vr_dimensions": [
            "data_infrastructure", "ai_governance", "technology_stack",
            "talent", "leadership", "use_case_portfolio", "culture",
        ],
        "hr_factors": [
            "sector_benchmark", "peer_comparison", "market_readiness",
        ],
        "hitl_thresholds": {
            "score_low": 40,
            "score_high": 85,
            "ebitda_pct": 5.0,
        },
    }, indent=2)


@mcp.resource("orgair://sectors")
def get_sector_definitions() -> str:
    """Sector definitions — baselines and weights for quartile calculation."""
    return json.dumps({
        "technology": {
            "h_r_base": 85,
            "weight_talent": 0.18,
            "quartiles": {"q1": 75, "q2": 65, "q3": 55, "q4": 45},
        },
        "healthcare": {
            "h_r_base": 75,
            "weight_governance": 0.18,
            "quartiles": {"q1": 70, "q2": 58, "q3": 48, "q4": 38},
        },
        "financial_services": {
            "h_r_base": 80,
            "weight_governance": 0.16,
            "quartiles": {"q1": 72, "q2": 60, "q3": 50, "q4": 40},
        },
        "manufacturing": {
            "h_r_base": 65,
            "weight_infrastructure": 0.16,
            "quartiles": {"q1": 68, "q2": 55, "q3": 45, "q4": 35},
        },
        "retail": {
            "h_r_base": 60,
            "weight_use_cases": 0.16,
            "quartiles": {"q1": 65, "q2": 52, "q3": 42, "q4": 32},
        },
        "energy": {
            "h_r_base": 55,
            "weight_infrastructure": 0.18,
            "quartiles": {"q1": 60, "q2": 48, "q3": 38, "q4": 28},
        },
    }, indent=2)


# ════════════════════════════════════════════════════════════════
# PROMPTS — Reusable templates (Task 9.3 continued)
# ════════════════════════════════════════════════════════════════


@mcp.prompt()
def due_diligence_assessment(company_id: str) -> str:
    """Complete due diligence assessment workflow for a company."""
    return f"""Perform a comprehensive due diligence assessment for {company_id.upper()}.

Follow these steps in order:

1. **Score Calculation**: Use calculate_org_air_score to get the current Org-AI-R score breakdown
2. **Evidence Review**: For any dimension scoring below 60, use get_company_evidence to review the underlying evidence
3. **Justification**: Use generate_justification for the 3 lowest-scoring dimensions to understand why
4. **Gap Analysis**: Use run_gap_analysis with target_org_air=75 to identify improvement priorities
5. **EBITDA Projection**: Use project_ebitda_impact with the current scores to estimate value creation potential

Present findings as:
- Executive Summary (2-3 sentences)
- Score Breakdown (table format)
- Key Strengths (top 3 dimensions)
- Critical Gaps (bottom 3 dimensions with justifications)
- 100-Day Improvement Plan (from gap analysis)
- EBITDA Impact Assessment (3 scenarios)
- HITL Flags (any scores outside [40, 85] or EBITDA > 5%)
"""


@mcp.prompt()
def ic_meeting_prep(company_id: str) -> str:
    """Prepare Investment Committee meeting package for a company."""
    return f"""Prepare an Investment Committee meeting package for {company_id.upper()}.

Follow these steps:

1. Use calculate_org_air_score to get complete scoring
2. Use generate_justification for ALL 7 dimensions
3. Use run_gap_analysis with target_org_air=80 (IC-level target)
4. Use project_ebitda_impact for value creation projections
5. Use get_portfolio_summary to show portfolio-level context

Package format:
- **Company Overview**: Name, sector, current Org-AI-R
- **Score Card**: All 7 dimensions with levels (L1-L5)
- **Evidence Summary**: Key evidence per dimension
- **Risk Assessment**: HITL flags, confidence intervals
- **Value Creation Thesis**: Gap analysis + EBITDA projections
- **Portfolio Impact**: How this company affects Fund-AI-R
- **Recommendation**: Hold / Accelerate / Watch with rationale
"""


# ════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════


if __name__ == "__main__":
    mcp.run()

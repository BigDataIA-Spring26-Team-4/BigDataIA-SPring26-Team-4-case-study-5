import json
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from app.services.integration.cs2_client import CS2Client
from app.services.integration.cs3_client import CS3Client
from app.services.integration.cs4_client import CS4Client
from src.services.integration.portfolio_data_service import PortfolioDataService
from src.mcp.resources import ORG_AIR_PARAMETERS, SECTOR_BASELINES
from src.mcp.prompts import (
    DUE_DILIGENCE_ASSESSMENT_PROMPT,
    IC_MEETING_PREP_PROMPT,
)

mcp = FastMCP("pe-orgair-server")

# Module-level clients per PDF guidance
cs2_client = CS2Client()
cs3_client = CS3Client()
cs4_client = CS4Client()
portfolio_data_service = PortfolioDataService()


def _serialize_dimension_scores(dimension_scores: Dict[str, Any]) -> Dict[str, Any]:
    serialized = {}

    for key, value in dimension_scores.items():
        clean_key = getattr(key, "value", str(key))

        if hasattr(value, "score"):
            serialized[clean_key] = {
                "score": getattr(value, "score", None),
                "level": int(getattr(value, "level", 0).value)
                if hasattr(getattr(value, "level", None), "value")
                else str(getattr(value, "level", "")),
                "confidence_interval": list(getattr(value, "confidence_interval", []))
                if getattr(value, "confidence_interval", None)
                else [],
                "evidence_count": getattr(value, "evidence_count", 0),
                "last_updated": getattr(value, "last_updated", ""),
            }
        else:
            serialized[clean_key] = value

    return serialized


@mcp.tool()
async def calculate_org_air_score(company_id: str) -> dict:
    assessment = await cs3_client.get_assessment(company_id)

    return {
        "company_id": company_id,
        "org_air_score": assessment.org_air_score,
        "vr_score": assessment.vr_score,
        "hr_score": assessment.hr_score,
        "synergy_score": assessment.synergy_score,
        "dimension_scores": assessment.dimension_scores,
        "confidence_interval": assessment.confidence_interval
    }


@mcp.tool()
async def get_company_evidence(company_id: str, dimension: str = "all", limit: int = 10) -> list:
    evidence = await cs2_client.get_evidence_for_cs5(
        company_id=company_id,
        dimension=dimension,
        limit=limit,
    )

    results = []
    for item in evidence:
        results.append(
            {
                "evidence_id": getattr(item, "evidence_id", ""),
                "company_id": getattr(item, "company_id", company_id),
                "source_type": str(getattr(item, "source_type", "")),
                "signal_category": str(getattr(item, "signal_category", "")),
                "content": getattr(item, "content", ""),
                "confidence": getattr(item, "confidence", 0.0),
                "fiscal_year": getattr(item, "fiscal_year", None),
                "source_url": getattr(item, "source_url", None),
                "page_number": getattr(item, "page_number", None),
            }
        )
    return results


@mcp.tool()
async def generate_justification_impl(company_id: str, dimension: str) -> dict:
    evidence = await cs2_client.get_evidence_for_cs5(
        company_id=company_id,
        dimension="all",
        limit=50,
    )

    return cs4_client.generate_justification_with_evidence(
        company_id=company_id,
        dimension=dimension,
        evidence=evidence,
    )

@mcp.tool()
async def generate_justification(company_id: str, dimension: str) -> dict:
    return await generate_justification_impl(company_id, dimension)
@mcp.tool()
def project_ebitda_impact(company_id: str, base_ebitda: float, improvement_pct: float) -> dict:
    projected_impact = base_ebitda * (improvement_pct / 100.0)
    projected_total = base_ebitda + projected_impact

    return {
        "company_id": company_id,
        "base_ebitda": base_ebitda,
        "improvement_pct": improvement_pct,
        "projected_impact": projected_impact,
        "projected_total_ebitda": projected_total,
    }


@mcp.tool()
def run_gap_analysis(company_id: str, current_score: float) -> dict:
    gaps = []
    initiatives = []

    if current_score < 50:
        gaps.append("Overall Org-AI-R score is in the lagging range")
        initiatives.append("Prioritize foundational AI governance and operating model setup")
        initiatives.append("Establish data platform and enterprise AI roadmap")
    elif current_score < 60:
        gaps.append("Overall Org-AI-R score is below target threshold")
        initiatives.append("Improve AI governance and operating cadence")
        initiatives.append("Strengthen data infrastructure and platform readiness")
    elif current_score < 75:
        gaps.append("Overall Org-AI-R score is moderate with room for improvement")
        initiatives.append("Expand AI talent and value realization programs")
        initiatives.append("Scale priority use cases with stronger executive sponsorship")
    else:
        initiatives.append("Maintain leadership and optimize cross-functional AI scale-up")
        initiatives.append("Focus on monetization, repeatability, and portfolio-wide best practices")

    return {
        "company_id": company_id,
        "current_score": current_score,
        "gaps": gaps,
        "initiatives": initiatives,
    }


@mcp.tool()
async def get_portfolio_summary(fund_id: str = "default") -> list:
    portfolio = await portfolio_data_service.get_portfolio_view(fund_id)

    return [
        {
            "ticker": row.ticker,
            "name": row.name,
            "sector": str(row.sector).replace("Sector.", ""),
            "org_air": row.org_air,
            "vr": row.vr,
            "hr": row.hr,
            "synergy": row.synergy,
            "dimensions": _serialize_dimension_scores(row.dimensions),
            "confidence_interval": list(row.confidence_interval)
            if row.confidence_interval
            else [],
            "delta": row.delta,
            "evidence_count": row.evidence_count,
        }
        for row in portfolio
    ]


@mcp.resource("orgair://parameters/v2.0")
def orgair_parameters() -> str:
    return json.dumps(ORG_AIR_PARAMETERS, indent=2)


@mcp.resource("orgair://sectors")
def orgair_sectors() -> str:
    return json.dumps(SECTOR_BASELINES, indent=2)


@mcp.prompt()
def due_diligence_assessment() -> str:
    return DUE_DILIGENCE_ASSESSMENT_PROMPT


@mcp.prompt()
def ic_meeting_prep() -> str:
    return IC_MEETING_PREP_PROMPT


if __name__ == "__main__":
    mcp.run()
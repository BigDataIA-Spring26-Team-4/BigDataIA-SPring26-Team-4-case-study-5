import sys
from pathlib import Path

# Ensure the src directory is on the path so sibling packages (services, etc.) are importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.fastmcp import FastMCP

from services.integration.portfolio_data_service import portfolio_data_service
from services.cs1_client import CS1Client
from services.cs2_client import CS2Client
from services.cs3_client import CS3Client
from services.cs4_client import CS4Client

mcp = FastMCP("pe-orgair-server")


@mcp.tool()
async def calculate_org_air_score(ticker: str) -> dict:
    """Calculate the Org-AIR score for a company based on its ticker symbol."""
    assessment = await portfolio_data_service.cs3.get_assessment(ticker)
    return {"org_air_score": assessment["final_score"]}


@mcp.tool()
async def get_company_evidence(company_id: str) -> dict:
    """Retrieve evidence for a specific company by its company ID."""
    evidence = await portfolio_data_service.cs3.get_assessment(company_id)
    return {"evidence": evidence["evidence_list"]}


@mcp.tool()
async def generate_justification(company_id: str, dimension: str) -> dict:
    """Generate a justification for a dimension of a company's Org-AIR score based on its ID.

    Args:
        company_id: The company identifier.
        dimension: One of: data_infrastructure, ai_governance, technology_stack, talent_skills, leadership_vision, use_case_portfolio, culture_change.
    """
    assessment = await portfolio_data_service.cs4.get_dimension_justification(company_id, dimension)
    return {"justification": assessment["justification"]}


@mcp.tool()
async def get_portfolio_view() -> dict:
    """Get a comprehensive view of the portfolio with ESG scores, dimension breakdowns, and confidence intervals."""
    views = await portfolio_data_service.get_portfolio_view()
    return {"portfolio_view": [view.__dict__ for view in views]}


if __name__ == "__main__":
    mcp.run()
"""
Task 10.2: Specialist Agents (12 pts).

4 specialist agents that use MCP tools to access CS1-CS4:
  1. SECAnalysisAgent     — SEC filing evidence via get_company_evidence
  2. ScoringAgent         — Org-AI-R scoring via calculate_org_air_score + HITL check
  3. EvidenceAgent        — CS4 justifications for 3 key dimensions
  4. ValueCreationAgent   — Gap analysis + EBITDA projection

Agents call MCP tools via MCPToolCaller (HTTP to MCP server).
They NEVER call CS clients directly.
"""

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from typing import Dict, Any
from datetime import datetime
import json

import httpx
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool
import structlog

from agents.state import DueDiligenceState
from config import settings

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════
# MCP Tool Caller — HTTP client for MCP server
# ════════════════════════════════════════════════════════════════


class MCPToolCaller:
    """
    HTTP client wrapper for calling MCP server tools.

    In production: POSTs to the MCP server's HTTP transport.
    The MCP server must be running (e.g., on port 3000).
    """

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=60.0)

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Call an MCP tool via HTTP.

        Posts to {base_url}/tools/{tool_name} with JSON arguments.
        Returns the tool result as a string.
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/tools/{tool_name}",
                json=arguments,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", json.dumps(result))
        except httpx.ConnectError:
            logger.warning(
                "mcp_server_unavailable",
                tool=tool_name,
                url=self.base_url,
            )
            raise ConnectionError(
                f"MCP server not reachable at {self.base_url}. "
                f"Start it with: python -m mcp_server.server"
            )
        except Exception as e:
            logger.error("mcp_tool_call_failed", tool=tool_name, error=str(e))
            raise


# Module-level MCP client
mcp_client = MCPToolCaller(base_url=settings.MCP_SERVER_URL)


# ════════════════════════════════════════════════════════════════
# LangChain Tool Wrappers (wrap MCP calls as LangChain tools)
# ════════════════════════════════════════════════════════════════


@tool
async def get_org_air_score(company_id: str) -> str:
    """Get Org-AI-R score for a company via MCP server."""
    return await mcp_client.call_tool(
        "calculate_org_air_score", {"company_id": company_id}
    )


@tool
async def get_evidence(company_id: str, dimension: str = "all") -> str:
    """Get evidence for a company via MCP server."""
    return await mcp_client.call_tool(
        "get_company_evidence",
        {"company_id": company_id, "dimension": dimension},
    )


@tool
async def get_justification(company_id: str, dimension: str) -> str:
    """Get CS4 justification for a dimension via MCP server."""
    return await mcp_client.call_tool(
        "generate_justification",
        {"company_id": company_id, "dimension": dimension},
    )


@tool
async def get_gap_analysis(company_id: str, target: float = 75.0) -> str:
    """Run gap analysis via MCP server."""
    return await mcp_client.call_tool(
        "run_gap_analysis",
        {"company_id": company_id, "target_org_air": target},
    )


@tool
async def get_ebitda_projection(
    company_id: str,
    entry_score: float,
    target_score: float,
    h_r_score: float,
) -> str:
    """Project EBITDA impact via MCP server."""
    return await mcp_client.call_tool(
        "project_ebitda_impact",
        {
            "company_id": company_id,
            "entry_score": entry_score,
            "target_score": target_score,
            "h_r_score": h_r_score,
        },
    )


# ════════════════════════════════════════════════════════════════
# Specialist Agent #1: SEC Analysis
# ════════════════════════════════════════════════════════════════


class SECAnalysisAgent:
    """Agent specialized in SEC filing analysis."""

    def __init__(self):
        self._llm = None
        self.tools = [get_evidence]

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        return self._llm

    async def analyze(self, state: DueDiligenceState) -> Dict[str, Any]:
        """
        Analyze SEC filing evidence for a company.

        Calls get_company_evidence MCP tool for all dimensions,
        returns structured findings.
        """
        company_id = state["company_id"]
        logger.info("sec_agent_start", company_id=company_id)

        # Get evidence via MCP tool (calls CS2 under the hood)
        evidence_result = await get_evidence.ainvoke(
            {"company_id": company_id, "dimension": "all"}
        )

        # Parse the result
        try:
            findings = json.loads(evidence_result) if evidence_result else []
        except (json.JSONDecodeError, TypeError):
            findings = []

        return {
            "sec_analysis": {
                "company_id": company_id,
                "findings": findings,
                "dimensions_covered": [
                    "data_infrastructure",
                    "ai_governance",
                    "technology_stack",
                ],
                "evidence_count": len(findings),
            },
            "messages": [{
                "role": "assistant",
                "content": f"SEC analysis complete for {company_id}: "
                           f"found {len(findings)} evidence items",
                "agent_name": "sec_analyst",
                "timestamp": datetime.utcnow(),
            }],
        }


# ════════════════════════════════════════════════════════════════
# Specialist Agent #2: Scoring
# ════════════════════════════════════════════════════════════════


class ScoringAgent:
    """Agent for calculating and explaining Org-AI-R scores."""

    def __init__(self):
        self._llm = None
        self.tools = [get_org_air_score, get_justification]

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatAnthropic(
                model="claude-sonnet-4-20250514", temperature=0.2
            )
        return self._llm

    async def calculate(self, state: DueDiligenceState) -> Dict[str, Any]:
        """
        Calculate Org-AI-R score and check HITL requirements.

        HITL triggers if score is outside [40, 85].
        """
        company_id = state["company_id"]
        logger.info("scoring_agent_start", company_id=company_id)

        # Get score via MCP tool (calls CS3 under the hood)
        score_result = await get_org_air_score.ainvoke(
            {"company_id": company_id}
        )
        score_data = json.loads(score_result)

        # Check HITL requirement
        org_air = score_data.get("org_air", 0)
        requires_approval = org_air > 85 or org_air < 40
        approval_reason = None
        if requires_approval:
            approval_reason = (
                f"Score {org_air:.1f} outside normal range [40, 85]"
            )

        return {
            "scoring_result": score_data,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "approval_status": "pending" if requires_approval else None,
            "messages": [{
                "role": "assistant",
                "content": (
                    f"Scoring complete: Org-AI-R = {org_air:.1f}"
                    + (" [REQUIRES APPROVAL]" if requires_approval else "")
                ),
                "agent_name": "scorer",
                "timestamp": datetime.utcnow(),
            }],
        }


# ════════════════════════════════════════════════════════════════
# Specialist Agent #3: Evidence Justification
# ════════════════════════════════════════════════════════════════


class EvidenceAgent:
    """Agent for evidence retrieval and justification."""

    def __init__(self):
        self._llm = None
        self.tools = [get_justification]

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        return self._llm

    async def justify(self, state: DueDiligenceState) -> Dict[str, Any]:
        """
        Generate justifications for 3 key dimensions via CS4 RAG.

        Targets: data_infrastructure, talent, use_case_portfolio
        (the dimensions most impactful for PE value creation).
        """
        company_id = state["company_id"]
        logger.info("evidence_agent_start", company_id=company_id)

        target_dims = ["data_infrastructure", "talent", "use_case_portfolio"]
        justifications = {}

        for dim in target_dims:
            try:
                result = await get_justification.ainvoke(
                    {"company_id": company_id, "dimension": dim}
                )
                justifications[dim] = json.loads(result)
            except Exception as e:
                logger.warning(
                    "justification_failed",
                    company_id=company_id,
                    dimension=dim,
                    error=str(e),
                )
                justifications[dim] = {"error": str(e)}

        return {
            "evidence_justifications": {
                "company_id": company_id,
                "justifications": justifications,
                "dimensions_justified": len(justifications),
            },
            "messages": [{
                "role": "assistant",
                "content": (
                    f"Generated justifications for "
                    f"{len(justifications)} dimensions"
                ),
                "agent_name": "evidence_agent",
                "timestamp": datetime.utcnow(),
            }],
        }


# ════════════════════════════════════════════════════════════════
# Specialist Agent #4: Value Creation
# ════════════════════════════════════════════════════════════════


class ValueCreationAgent:
    """Agent for EBITDA projections and value creation planning."""

    def __init__(self):
        self._llm = None
        self.tools = [get_gap_analysis, get_ebitda_projection]

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        return self._llm

    async def plan(self, state: DueDiligenceState) -> Dict[str, Any]:
        """
        Create value creation plan with gap analysis and EBITDA projection.

        HITL triggers if projected EBITDA impact > 5%.
        """
        company_id = state["company_id"]
        logger.info("value_creation_agent_start", company_id=company_id)

        # Run gap analysis via MCP tool
        gap_result = await get_gap_analysis.ainvoke(
            {"company_id": company_id, "target": 80.0}
        )
        gap_data = json.loads(gap_result)

        # Check HITL for large EBITDA projections
        projected_impact = gap_data.get("projected_ebitda_pct", 0.0)
        requires_approval = (
            projected_impact > 5.0
            or state.get("requires_approval", False)
        )
        approval_reason = state.get("approval_reason")
        if projected_impact > 5.0 and not approval_reason:
            approval_reason = f"EBITDA projection {projected_impact:.1f}% > 5%"

        return {
            "value_creation_plan": {
                "company_id": company_id,
                "gap_analysis": gap_data,
                "projected_ebitda_pct": projected_impact,
            },
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "messages": [{
                "role": "assistant",
                "content": (
                    f"Value creation plan complete. "
                    f"Projected EBITDA impact: {projected_impact:.1f}%"
                ),
                "agent_name": "value_creator",
                "timestamp": datetime.utcnow(),
            }],
        }


# ════════════════════════════════════════════════════════════════
# Module-level instances (per PDF v4 FIX)
# ════════════════════════════════════════════════════════════════

sec_agent = SECAnalysisAgent()
scoring_agent = ScoringAgent()
evidence_agent = EvidenceAgent()
value_agent = ValueCreationAgent()

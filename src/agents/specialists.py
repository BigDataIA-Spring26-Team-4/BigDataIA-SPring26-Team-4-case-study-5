from datetime import datetime
from typing import Any, Dict

from src.agents.tools import MCPToolCaller
from src.agents.state import DueDiligenceState


def _msg(agent_name: str, content: str) -> Dict[str, str]:
    return {
        "role": "assistant",
        "content": content,
        "agent_name": agent_name,
        "timestamp": datetime.utcnow().isoformat(),
    }


class SECAnalysisAgent:
    def __init__(self, tools: MCPToolCaller | None = None):
        self.tools = tools or MCPToolCaller()

    def run(self, state: DueDiligenceState) -> DueDiligenceState:
        company_id = state["company_id"]
        evidence = self.tools.get_evidence(company_id=company_id, dimension="all", limit=10)

        return {
            "sec_analysis": {
                "company_id": company_id,
                "evidence_count": len(evidence),
                "evidence_preview": evidence[:3],
            },
            "messages": [_msg("SECAnalysisAgent", f"Collected {len(evidence)} evidence items for {company_id}.")],
            "next_agent": "scorer",
        }


class ScoringAgent:
    def __init__(self, tools: MCPToolCaller | None = None):
        self.tools = tools or MCPToolCaller()

    def run(self, state: DueDiligenceState) -> DueDiligenceState:
        company_id = state["company_id"]
        scoring = self.tools.get_org_air_score(company_id=company_id)
        score = scoring.get("org_air_score", 0.0)

        requires_approval = score < 40 or score > 85
        approval_reason = ""
        if requires_approval:
            approval_reason = f"Score {score} outside HITL range [40, 85]."

        return {
            "scoring_result": scoring,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "messages": [_msg("ScoringAgent", f"Calculated Org-AI-R score {score} for {company_id}.")],
            "next_agent": "hitl" if requires_approval else "evidence",
        }


class EvidenceAgent:
    def __init__(self, tools: MCPToolCaller | None = None):
        self.tools = tools or MCPToolCaller()

    def run(self, state: DueDiligenceState) -> DueDiligenceState:
        company_id = state["company_id"]
        dims = ["data_infrastructure", "ai_governance", "technology_stack"]

        justifications: Dict[str, Any] = {}
        for dim in dims:
            try:
                justifications[dim] = self.tools.get_justification(company_id=company_id, dimension=dim)
            except Exception as e:
                justifications[dim] = {"dimension": dim, "error": str(e)}

        return {
            "evidence_justifications": justifications,
            "messages": [_msg("EvidenceAgent", f"Generated justifications for {len(dims)} dimensions for {company_id}.")],
            "next_agent": "value_creator",
        }


class ValueCreationAgent:
    def __init__(self, tools: MCPToolCaller | None = None):
        self.tools = tools or MCPToolCaller()

    def run(self, state: DueDiligenceState) -> DueDiligenceState:
        company_id = state["company_id"]
        scoring = state.get("scoring_result", {})
        current_score = float(scoring.get("org_air_score", 0.0))

        gap_analysis = self.tools.get_gap_analysis(company_id=company_id, current_score=current_score)

        requires_approval = state.get("requires_approval", False)
        approval_reason = state.get("approval_reason", "")

        return {
            "value_creation_plan": gap_analysis,
            "requires_approval": requires_approval,
            "approval_reason": approval_reason,
            "messages": [_msg("ValueCreationAgent", f"Created value plan for {company_id}.")],
            "next_agent": "complete",
        }
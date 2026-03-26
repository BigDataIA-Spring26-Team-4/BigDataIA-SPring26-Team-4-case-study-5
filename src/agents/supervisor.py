from datetime import datetime
from typing import Dict

from src.agents.state import DueDiligenceState
from src.agents.specialists import (
    SECAnalysisAgent,
    ScoringAgent,
    EvidenceAgent,
    ValueCreationAgent,
)


def supervisor_node(state: DueDiligenceState) -> Dict:
    if "sec_analysis" not in state:
        return {"next_agent": "sec_analyst"}

    if "scoring_result" not in state:
        return {"next_agent": "scorer"}

    if state.get("requires_approval") and state.get("approval_status") != "approved":
        return {"next_agent": "hitl"}

    if "evidence_justifications" not in state:
        return {"next_agent": "evidence"}

    if "value_creation_plan" not in state:
        return {"next_agent": "value_creator"}

    return {"next_agent": "complete"}


def sec_analyst_node(state: DueDiligenceState) -> Dict:
    return SECAnalysisAgent().run(state)


def scorer_node(state: DueDiligenceState) -> Dict:
    return ScoringAgent().run(state)


def evidence_node(state: DueDiligenceState) -> Dict:
    return EvidenceAgent().run(state)


def value_creator_node(state: DueDiligenceState) -> Dict:
    return ValueCreationAgent().run(state)


def hitl_approval_node(state: DueDiligenceState) -> Dict:
    return {
        "approval_status": "approved",
        "approved_by": "auto_approval_for_exercise",
        "messages": [{
            "role": "assistant",
            "content": f"Auto-approved HITL review. Reason: {state.get('approval_reason', '')}",
            "agent_name": "HITLApprovalNode",
            "timestamp": datetime.utcnow().isoformat(),
        }],
    }


def complete_node(state: DueDiligenceState) -> Dict:
    return {
        "completed_at": datetime.utcnow().isoformat(),
        "messages": [{
            "role": "assistant",
            "content": f"Due diligence workflow completed for {state['company_id']}.",
            "agent_name": "CompleteNode",
            "timestamp": datetime.utcnow().isoformat(),
        }],
    }
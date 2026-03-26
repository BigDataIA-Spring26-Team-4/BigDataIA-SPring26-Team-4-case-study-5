from typing import Annotated, Any, Dict, List, Optional, TypedDict
import operator


class AgentMessage(TypedDict):
    role: str
    content: str
    agent_name: str
    timestamp: str


class DueDiligenceState(TypedDict, total=False):
    company_id: str
    assessment_type: str
    requested_by: str

    messages: Annotated[List[AgentMessage], operator.add]

    sec_analysis: Dict[str, Any]
    scoring_result: Dict[str, Any]
    evidence_justifications: Dict[str, Any]
    value_creation_plan: Dict[str, Any]
    portfolio_summary: List[Dict[str, Any]]

    next_agent: str
    requires_approval: bool
    approval_reason: str
    approval_status: str
    approved_by: str

    started_at: str
    completed_at: str
    total_tokens: int
    error: Optional[str]
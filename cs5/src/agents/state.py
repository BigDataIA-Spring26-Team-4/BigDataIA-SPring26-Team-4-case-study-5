"""
Task 10.1: LangGraph State Definitions (8 pts).

Defines the state schema for the due diligence workflow.
Uses TypedDict with Annotated for append-only message accumulation.
"""

from typing import TypedDict, Annotated, List, Dict, Any, Optional, Literal
from datetime import datetime
import operator


class AgentMessage(TypedDict):
    """Single message in the agent conversation."""
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    agent_name: Optional[str]
    timestamp: datetime


class DueDiligenceState(TypedDict):
    """
    State for the due diligence workflow.

    Fields are grouped by purpose:
      - Input: what the workflow is about
      - Messages: append-only conversation log
      - Agent outputs: results from each specialist
      - Workflow control: routing and HITL
      - Metadata: timing and token tracking
    """

    # ── Input ───────────────────────────────────────────────────
    company_id: str
    assessment_type: Literal["screening", "limited", "full"]
    requested_by: str

    # ── Messages (append-only via operator.add reducer) ─────────
    messages: Annotated[List[AgentMessage], operator.add]

    # ── Agent outputs ───────────────────────────────────────────
    sec_analysis: Optional[Dict[str, Any]]
    talent_analysis: Optional[Dict[str, Any]]
    scoring_result: Optional[Dict[str, Any]]
    evidence_justifications: Optional[Dict[str, Any]]
    value_creation_plan: Optional[Dict[str, Any]]

    # ── Workflow control ────────────────────────────────────────
    next_agent: Optional[str]
    requires_approval: bool
    approval_reason: Optional[str]
    approval_status: Optional[Literal["pending", "approved", "rejected"]]
    approved_by: Optional[str]

    # ── Metadata ────────────────────────────────────────────────
    started_at: datetime
    completed_at: Optional[datetime]
    total_tokens: int
    error: Optional[str]

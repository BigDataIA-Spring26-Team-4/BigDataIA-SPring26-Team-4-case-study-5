"""
Task 10.3: Supervisor with HITL (10 pts).

LangGraph StateGraph implementing the supervisor-worker pattern:
  - Supervisor routes to the next agent based on workflow state
  - 4 specialist agent nodes
  - HITL approval gate for scores outside [40, 85] or EBITDA > 5%
  - MemorySaver checkpointer for conversation persistence

Graph flow:
  supervisor → (sec_analyst | scorer | evidence_agent | value_creator | hitl_approval | complete)
  all agents → supervisor
  hitl_approval → supervisor
  complete → END
"""

import sys
from pathlib import Path

_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from typing import Dict, Any
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import structlog

from agents.state import DueDiligenceState
from agents.specialists import sec_agent, scoring_agent, evidence_agent, value_agent

logger = structlog.get_logger()


# ════════════════════════════════════════════════════════════════
# Node functions
# ════════════════════════════════════════════════════════════════


async def supervisor_node(state: DueDiligenceState) -> Dict[str, Any]:
    """
    Supervisor decides which agent to run next.

    Routing logic:
      1. If HITL approval is pending → route to hitl_approval
      2. If SEC analysis missing → route to sec_analyst
      3. If scoring missing → route to scorer
      4. If evidence justifications missing → route to evidence_agent
      5. If value creation missing (and not screening) → route to value_creator
      6. Otherwise → complete
    """
    # Check HITL first
    if (
        state.get("requires_approval")
        and state.get("approval_status") == "pending"
    ):
        return {"next_agent": "hitl_approval"}

    # Route based on what's missing
    if not state.get("sec_analysis"):
        return {"next_agent": "sec_analyst"}
    elif not state.get("scoring_result"):
        return {"next_agent": "scorer"}
    elif not state.get("evidence_justifications"):
        return {"next_agent": "evidence_agent"}
    elif (
        not state.get("value_creation_plan")
        and state["assessment_type"] != "screening"
    ):
        return {"next_agent": "value_creator"}
    else:
        return {"next_agent": "complete"}


async def sec_analyst_node(state: DueDiligenceState) -> Dict[str, Any]:
    """Run SEC analysis specialist."""
    return await sec_agent.analyze(state)


async def scorer_node(state: DueDiligenceState) -> Dict[str, Any]:
    """Run scoring specialist."""
    return await scoring_agent.calculate(state)


async def evidence_node(state: DueDiligenceState) -> Dict[str, Any]:
    """Run evidence justification specialist."""
    return await evidence_agent.justify(state)


async def value_creator_node(state: DueDiligenceState) -> Dict[str, Any]:
    """Run value creation specialist."""
    return await value_agent.plan(state)


async def hitl_approval_node(state: DueDiligenceState) -> Dict[str, Any]:
    """
    Human-in-the-loop approval gate.

    HITL triggers:
      - Org-AI-R score outside [40, 85]
      - EBITDA projection > 5%

    In production: sends Slack/email notification, waits for response.
    For exercise: auto-approves after logging the warning.
    """
    logger.warning(
        "hitl_approval_required",
        company_id=state["company_id"],
        reason=state.get("approval_reason"),
    )

    # Auto-approve for exercise (production would block here)
    return {
        "approval_status": "approved",
        "approved_by": "exercise_auto_approve",
        "messages": [{
            "role": "system",
            "content": (
                f"HITL approval granted (auto): "
                f"{state.get('approval_reason', 'No reason specified')}"
            ),
            "agent_name": "hitl",
            "timestamp": datetime.utcnow(),
        }],
    }


async def complete_node(state: DueDiligenceState) -> Dict[str, Any]:
    """Mark the workflow as complete."""
    return {
        "completed_at": datetime.utcnow(),
        "messages": [{
            "role": "assistant",
            "content": (
                f"Due diligence complete for {state['company_id']}. "
                f"Assessment type: {state['assessment_type']}."
            ),
            "agent_name": "supervisor",
            "timestamp": datetime.utcnow(),
        }],
    }


# ════════════════════════════════════════════════════════════════
# Graph construction
# ════════════════════════════════════════════════════════════════


def _route_from_supervisor(state: DueDiligenceState) -> str:
    """Conditional edge: read next_agent from state."""
    return state["next_agent"]


def create_due_diligence_graph():
    """
    Build the LangGraph StateGraph for due diligence.

    Structure:
      - Entry → supervisor
      - supervisor → conditional routing to agents / hitl / complete
      - All agents → back to supervisor
      - hitl_approval → back to supervisor
      - complete → END
      - MemorySaver checkpointer for persistence
    """
    workflow = StateGraph(DueDiligenceState)

    # ── Add nodes ───────────────────────────────────────────────
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("sec_analyst", sec_analyst_node)
    workflow.add_node("scorer", scorer_node)
    workflow.add_node("evidence_agent", evidence_node)
    workflow.add_node("value_creator", value_creator_node)
    workflow.add_node("hitl_approval", hitl_approval_node)
    workflow.add_node("complete", complete_node)

    # ── Conditional edges from supervisor ───────────────────────
    workflow.add_conditional_edges(
        "supervisor",
        _route_from_supervisor,
        {
            "sec_analyst": "sec_analyst",
            "scorer": "scorer",
            "evidence_agent": "evidence_agent",
            "value_creator": "value_creator",
            "hitl_approval": "hitl_approval",
            "complete": "complete",
        },
    )

    # ── All agents loop back to supervisor ──────────────────────
    for agent_node in [
        "sec_analyst", "scorer", "evidence_agent", "value_creator"
    ]:
        workflow.add_edge(agent_node, "supervisor")

    # ── HITL loops back to supervisor ───────────────────────────
    workflow.add_edge("hitl_approval", "supervisor")

    # ── Complete → END ──────────────────────────────────────────
    workflow.add_edge("complete", END)

    # ── Entry point ─────────────────────────────────────────────
    workflow.set_entry_point("supervisor")

    # ── Compile with MemorySaver checkpointer ───────────────────
    return workflow.compile(checkpointer=MemorySaver())


# Module-level compiled graph (ready to invoke)
dd_graph = create_due_diligence_graph()

from datetime import datetime
from typing import Literal

from langgraph.graph import END, StateGraph

from src.agents.state import DueDiligenceState
from src.agents.supervisor import (
    supervisor_node,
    sec_analyst_node,
    scorer_node,
    evidence_node,
    value_creator_node,
    hitl_approval_node,
    complete_node,
)


def route_from_supervisor(state: DueDiligenceState) -> Literal[
    "sec_analyst",
    "scorer",
    "hitl",
    "evidence",
    "value_creator",
    "complete",
]:
    return supervisor_node(state)["next_agent"]


def create_due_diligence_graph():
    workflow = StateGraph(DueDiligenceState)

    # Nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("sec_analyst", sec_analyst_node)
    workflow.add_node("scorer", scorer_node)
    workflow.add_node("hitl", hitl_approval_node)
    workflow.add_node("evidence", evidence_node)
    workflow.add_node("value_creator", value_creator_node)
    workflow.add_node("complete", complete_node)

    # Entry
    workflow.set_entry_point("supervisor")

    # Supervisor conditional routing
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "sec_analyst": "sec_analyst",
            "scorer": "scorer",
            "hitl": "hitl",
            "evidence": "evidence",
            "value_creator": "value_creator",
            "complete": "complete",
        },
    )

    # All workers go back to supervisor
    workflow.add_edge("sec_analyst", "supervisor")
    workflow.add_edge("scorer", "supervisor")
    workflow.add_edge("hitl", "supervisor")
    workflow.add_edge("evidence", "supervisor")
    workflow.add_edge("value_creator", "supervisor")

    # Complete ends workflow
    workflow.add_edge("complete", END)

    return workflow.compile()


class DueDiligenceGraphRunner:
    def __init__(self):
        self.graph = create_due_diligence_graph()

    def run(
        self,
        company_id: str,
        assessment_type: str = "full",
        requested_by: str = "user",
    ) -> DueDiligenceState:
        initial_state: DueDiligenceState = {
            "company_id": company_id,
            "assessment_type": assessment_type,
            "requested_by": requested_by,
            "messages": [],
            "started_at": datetime.utcnow().isoformat(),
            "requires_approval": False,
            "approval_status": "",
            "approval_reason": "",
            "approved_by": "",
            "error": None,
        }

        final_state = self.graph.invoke(initial_state)
        return final_state
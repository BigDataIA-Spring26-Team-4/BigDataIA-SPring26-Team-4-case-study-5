"""
Task 10.4: Agentic Due Diligence Workflow (10 pts).

End-to-end exercise that runs the complete multi-agent DD process.
Initializes state, invokes the LangGraph supervisor graph,
and prints results.

Usage:
    cd cs5/src
    python -m exercises.agentic_due_diligence

Requires:
    - CS1-CS4 services running (Docker: docker compose up)
    - MCP server running (python -m mcp_server.server)
    - OPENAI_API_KEY and/or ANTHROPIC_API_KEY in .env
"""

import sys
from pathlib import Path

# Ensure cs5/src is importable
_src_dir = str(Path(__file__).resolve().parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import asyncio
from datetime import datetime

from agents.supervisor import dd_graph
from agents.state import DueDiligenceState


async def run_due_diligence(
    company_id: str,
    assessment_type: str = "full",
    requested_by: str = "analyst",
) -> DueDiligenceState:
    """
    Run the complete agentic due diligence workflow.

    Initializes the DueDiligenceState with all required fields,
    invokes the LangGraph supervisor graph, and returns final state.

    Args:
        company_id: Company ticker (e.g., 'NVDA')
        assessment_type: 'screening', 'limited', or 'full'
        requested_by: Analyst identifier

    Returns:
        Final DueDiligenceState with all agent outputs populated.
    """
    # Initialize state with all required fields
    initial_state: DueDiligenceState = {
        # Input
        "company_id": company_id.upper(),
        "assessment_type": assessment_type,
        "requested_by": requested_by,
        # Messages (empty — will be populated by agents)
        "messages": [],
        # Agent outputs (None — will be filled as agents run)
        "sec_analysis": None,
        "talent_analysis": None,
        "scoring_result": None,
        "evidence_justifications": None,
        "value_creation_plan": None,
        # Workflow control
        "next_agent": None,
        "requires_approval": False,
        "approval_reason": None,
        "approval_status": None,
        "approved_by": None,
        # Metadata
        "started_at": datetime.utcnow(),
        "completed_at": None,
        "total_tokens": 0,
        "error": None,
    }

    # Thread ID includes company + timestamp for checkpointing
    thread_id = f"dd-{company_id.upper()}-{datetime.now().isoformat()}"
    config = {"configurable": {"thread_id": thread_id}}

    # Invoke the graph
    result = await dd_graph.ainvoke(initial_state, config)

    return result


def _print_results(result: DueDiligenceState) -> None:
    """Pretty-print the DD workflow results."""
    print()
    print("=" * 60)
    print(f"  Company: {result['company_id']}")
    print(f"  Assessment Type: {result['assessment_type']}")
    print("=" * 60)

    # Scoring
    scoring = result.get("scoring_result")
    if scoring:
        print(f"\n  Org-AI-R Score: {scoring.get('org_air', 'N/A')}")
        print(f"  V^R Score:      {scoring.get('vr_score', 'N/A')}")
        print(f"  H^R Score:      {scoring.get('hr_score', 'N/A')}")
        print(f"  Synergy:        {scoring.get('synergy_score', 'N/A')}")
        ci = scoring.get("confidence_interval", [0, 0])
        print(f"  CI:             [{ci[0]:.1f}, {ci[1]:.1f}]")

        # Dimension breakdown
        dims = scoring.get("dimension_scores", {})
        if dims:
            print("\n  Dimension Scores:")
            for dim, info in dims.items():
                if isinstance(info, dict):
                    score = info.get("score", 0)
                    level = info.get("level", "?")
                else:
                    score = info
                    level = "?"
                dim_label = dim.replace("_", " ").title()
                print(f"    {dim_label:<25} {score:>6.1f}  (L{level})")

    # HITL
    print(f"\n  HITL Required:  {result.get('requires_approval', False)}")
    if result.get("approval_reason"):
        print(f"  HITL Reason:    {result['approval_reason']}")
    print(f"  HITL Status:    {result.get('approval_status', 'N/A')}")

    # SEC Analysis
    sec = result.get("sec_analysis")
    if sec:
        print(f"\n  SEC Evidence Items: {sec.get('evidence_count', 0)}")

    # Evidence Justifications
    ej = result.get("evidence_justifications")
    if ej:
        print(f"  Dimensions Justified: {ej.get('dimensions_justified', 0)}")

    # Value Creation
    vc = result.get("value_creation_plan")
    if vc:
        gap = vc.get("gap_analysis", {})
        print(f"  Overall Gap:    {gap.get('overall_gap', 'N/A')}")
        print(f"  EBITDA Impact:  {vc.get('projected_ebitda_pct', 'N/A')}%")

    # Timeline
    print(f"\n  Started:   {result.get('started_at', 'N/A')}")
    print(f"  Completed: {result.get('completed_at', 'N/A')}")

    # Agent message log
    messages = result.get("messages", [])
    if messages:
        print(f"\n  Agent Messages ({len(messages)}):")
        for msg in messages:
            agent = msg.get("agent_name", "unknown")
            content = msg.get("content", "")
            print(f"    [{agent}] {content}")

    print()
    print("  All data came from CS1-CS4 via MCP tools.")
    print("=" * 60)


async def main():
    """Run the full DD exercise for NVDA."""
    print("=" * 60)
    print("  PE Org-AI-R: Agentic Due Diligence")
    print("  Running full assessment for NVDA...")
    print("=" * 60)

    try:
        result = await run_due_diligence("NVDA", "full")
        _print_results(result)
    except ConnectionError as e:
        print(f"\n  ERROR: {e}")
        print("  Make sure the MCP server is running.")
    except Exception as e:
        print(f"\n  ERROR: {e}")
        print("  Make sure CS1-CS4 services are running (docker compose up).")


if __name__ == "__main__":
    asyncio.run(main())

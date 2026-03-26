from datetime import datetime
import json

from src.agents.graph import DueDiligenceGraphRunner


def run_due_diligence(company_id: str, assessment_type: str = "full"):
    runner = DueDiligenceGraphRunner()
    return runner.run(
        company_id=company_id,
        assessment_type=assessment_type,
        requested_by="cs5_exercise",
    )


if __name__ == "__main__":
    company_id = "NVDA"
    assessment_type = "full"

    state = run_due_diligence(company_id, assessment_type)

    print("\n=== AGENTIC DUE DILIGENCE RESULT ===")
    print(f"Company: {company_id}")
    print(f"Assessment Type: {assessment_type}")
    print(f"Completed At: {state.get('completed_at')}")

    print("\n=== ORG-AI-R SUMMARY ===")
    scoring = state.get("scoring_result", {})
    print(json.dumps(scoring, indent=2, default=str))

    print("\n=== VALUE CREATION PLAN ===")
    print(json.dumps(state.get("value_creation_plan", {}), indent=2, default=str))

    print("\n=== JUSTIFICATIONS ===")
    print(json.dumps(state.get("evidence_justifications", {}), indent=2, default=str))

    print("\n=== MESSAGE TRACE ===")
    for msg in state.get("messages", []):
        print(f"[{msg['agent_name']}] {msg['content']}")
from src.agents.graph import DueDiligenceGraphRunner

runner = DueDiligenceGraphRunner()
state = runner.run(company_id="NVDA", assessment_type="full", requested_by="Tapan")

print("=== FINAL STATE KEYS ===")
print(sorted(state.keys()))

print("\n=== SCORING RESULT ===")
print(state.get("scoring_result"))

print("\n=== VALUE CREATION PLAN ===")
print(state.get("value_creation_plan"))

print("\n=== APPROVAL ===")
print({
    "requires_approval": state.get("requires_approval"),
    "approval_reason": state.get("approval_reason"),
    "approval_status": state.get("approval_status"),
    "approved_by": state.get("approved_by"),
})

print("\n=== MESSAGES ===")
for msg in state.get("messages", []):
    print(f"[{msg['agent_name']}] {msg['content']}")
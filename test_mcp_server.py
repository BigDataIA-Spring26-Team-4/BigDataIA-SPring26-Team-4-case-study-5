from src.mcp.server import (
    calculate_org_air_score,
    get_company_evidence,
    generate_justification,
    project_ebitda_impact,
    run_gap_analysis,
    get_portfolio_summary,
    orgair_parameters,
    orgair_sectors,
    due_diligence_assessment,
    ic_meeting_prep,
)

print("=== SCORE ===")
print(calculate_org_air_score("NVDA"))

print("\n=== EVIDENCE ===")
print(get_company_evidence("NVDA", "all", 3))

print("\n=== JUSTIFICATION ===")
print(generate_justification("NVDA", "data_infrastructure"))

print("\n=== EBITDA ===")
print(project_ebitda_impact("NVDA", 1000.0, 5.0))

print("\n=== GAP ANALYSIS ===")
print(run_gap_analysis("NVDA", 78.91))

print("\n=== PORTFOLIO SUMMARY ===")
print(get_portfolio_summary("default")[:2])

print("\n=== RESOURCE: PARAMETERS ===")
print(orgair_parameters())

print("\n=== RESOURCE: SECTORS ===")
print(orgair_sectors())

print("\n=== PROMPT: DD ===")
print(due_diligence_assessment())

print("\n=== PROMPT: IC ===")
print(ic_meeting_prep())
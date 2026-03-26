from src.mcp.server import MCPServer

server = MCPServer()

print("=== Portfolio Summary ===")
print(server.call_tool("get_portfolio_summary"))

print("\n=== Org-AI-R Score ===")
print(server.call_tool("calculate_org_air_score", company_id="NVDA"))

print("\n=== Justification ===")
print(server.call_tool("generate_justification", company_id="NVDA", dimension="data_infrastructure"))

print("\n=== Gap Analysis ===")
print(server.call_tool("run_gap_analysis", company_id="NVDA", current_score=78.91))

print("\n=== EBITDA Impact ===")
print(server.call_tool("project_ebitda_impact", company_id="NVDA", base_ebitda=1000.0, improvement_pct=5.0))
from src.services.integration.portfolio_data_service import PortfolioDataService

print("Starting PortfolioDataService test...")

service = PortfolioDataService()
data = service.get_portfolio_view()

print("Type:", type(data))
print("Count:", len(data) if isinstance(data, list) else data)

for i, row in enumerate(data[:3]):
    print(f"\n--- Company {i + 1} ---")
    print("Ticker:", row.ticker)
    print("Name:", row.name)
    print("Sector:", row.sector)
    print("Org-AI-R:", row.org_air)
    print("VR:", row.vr)
    print("HR:", row.hr)
    print("Synergy:", row.synergy)
    print("Delta:", row.delta)
    print("Evidence Count:", row.evidence_count)
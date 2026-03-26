from app.services.integration.cs2_client import CS2Client

client = CS2Client()
result = client.get_evidence_for_cs5("NVDA", "talent", 5)

print(type(result))
print(len(result) if isinstance(result, list) else result)
print(result[:1] if isinstance(result, list) and result else result)
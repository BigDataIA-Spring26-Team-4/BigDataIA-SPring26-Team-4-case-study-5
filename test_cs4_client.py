from app.services.integration.cs4_client import CS4Client

client = CS4Client()

result = client.generate_justification("NVDA", "data_infrastructure")

print(result)
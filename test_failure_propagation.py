import asyncio
import traceback

from src.mcp.server import calculate_org_air_score, get_company_evidence
from app.services.integration.cs3_client import CS3Client
from app.services.integration.cs2_client import CS2Client


async def test_cs3_failure():
    print("=== FAILURE TEST: CS3 DOWN ===")
    bad_cs3 = CS3Client(base_url="http://localhost:8999")

    try:
        await bad_cs3.get_assessment("NVDA")
        print("[UNEXPECTED] CS3 failure test passed when it should fail")
    except Exception as e:
        print("[EXPECTED FAILURE] CS3 is unavailable")
        print(type(e).__name__, str(e))


async def test_cs2_failure():
    print("\n=== FAILURE TEST: CS2 DOWN ===")
    bad_cs2 = CS2Client(base_url="http://localhost:8999")

    try:
        await bad_cs2.get_evidence_for_cs5("NVDA")
        print("[UNEXPECTED] CS2 failure test passed when it should fail")
    except Exception as e:
        print("[EXPECTED FAILURE] CS2 is unavailable")
        print(type(e).__name__, str(e))


async def test_mcp_failure_style():
    print("\n=== FAILURE TEST: MCP STYLE CHECK ===")
    try:
        result = await calculate_org_air_score("BAD_TICKER_XYZ")
        print("[MCP RESPONSE]")
        print(result)
    except Exception as e:
        print("[EXPECTED MCP FAILURE OR PROPAGATED ERROR]")
        print(type(e).__name__, str(e))
        traceback.print_exc()


async def test_mcp_evidence_failure_style():
    print("\n=== FAILURE TEST: MCP EVIDENCE STYLE CHECK ===")
    try:
        result = await get_company_evidence("BAD_TICKER_XYZ")
        print("[MCP RESPONSE]")
        print(result)
    except Exception as e:
        print("[EXPECTED MCP FAILURE OR PROPAGATED ERROR]")
        print(type(e).__name__, str(e))
        traceback.print_exc()


async def main():
    await test_cs3_failure()
    await test_cs2_failure()
    await test_mcp_failure_style()
    await test_mcp_evidence_failure_style()


if __name__ == "__main__":
    asyncio.run(main())
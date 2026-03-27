import asyncio
import traceback

from src.mcp.server import (
    calculate_org_air_score,
    get_company_evidence,
    generate_justification_impl,
    get_portfolio_summary,
)


async def main():
    print("=== MCP TOOL SUCCESS TESTS ===")

    try:
        score = await calculate_org_air_score("NVDA")
        print("\n[SCORE OK]")
        print(score)
    except Exception as e:
        print("\n[SCORE FAILED]")
        print(type(e).__name__, str(e))
        traceback.print_exc()

    try:
        evidence = await get_company_evidence("NVDA")
        print("\n[EVIDENCE OK]")
        print(f"Evidence count: {len(evidence)}")
        if evidence:
            print("First evidence item:")
            print(evidence[0])
    except Exception as e:
        print("\n[EVIDENCE FAILED]")
        print(type(e).__name__, str(e))
        traceback.print_exc()

    try:
        justification = await generate_justification_impl("NVDA", "data_infrastructure")
        print("\n[JUSTIFICATION OK]")
        print(justification)
    except Exception as e:
        print("\n[JUSTIFICATION FAILED]")
        print(type(e).__name__, str(e))
        traceback.print_exc()

    try:
        portfolio = await get_portfolio_summary("default")
        print("\n[PORTFOLIO OK]")
        print(f"Portfolio rows: {len(portfolio)}")
        if portfolio:
            print("First portfolio row:")
            print(portfolio[0])
    except Exception as e:
        print("\n[PORTFOLIO FAILED]")
        print(type(e).__name__, str(e))
        traceback.print_exc()


import asyncio

if __name__ == "__main__":
    asyncio.run(main())
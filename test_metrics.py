import asyncio
from src.services.observability.metrics import (
    track_mcp_tool,
    track_agent,
    track_cs_client,
    record_hitl_approval,
    metrics_registry,
)


@track_mcp_tool
async def fake_mcp_tool():
    await asyncio.sleep(0.1)
    return {"ok": True}


@track_agent
async def fake_agent():
    await asyncio.sleep(0.05)
    return "done"


@track_cs_client
async def fake_cs_call():
    await asyncio.sleep(0.08)
    return {"status": "ok"}


async def main():
    print(await fake_mcp_tool())
    print(await fake_agent())
    print(await fake_cs_call())
    record_hitl_approval()
    print(metrics_registry.snapshot())


if __name__ == "__main__":
    asyncio.run(main())
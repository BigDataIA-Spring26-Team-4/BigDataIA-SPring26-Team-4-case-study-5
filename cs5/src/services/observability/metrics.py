"""
Task 10.6: Prometheus Metrics (5 pts).

Defines counters, histograms, and decorators for observability
across the MCP server, LangGraph agents, and CS1-CS4 clients.

Metrics:
  Counters:
    - mcp_tool_calls_total         (tool_name, status)
    - agent_invocations_total      (agent_name, status)
    - hitl_approvals_total         (reason, decision)
    - cs_client_calls_total        (service, endpoint, status)

  Histograms:
    - mcp_tool_duration_seconds    (tool_name)
    - agent_duration_seconds       (agent_name)

Decorators:
    - @track_mcp_tool(tool_name)
    - @track_agent(agent_name)
    - @track_cs_client(service, endpoint)
"""

from prometheus_client import Counter, Histogram
from functools import wraps
import time


# ════════════════════════════════════════════════════════════════
# MCP SERVER METRICS
# ════════════════════════════════════════════════════════════════

MCP_TOOL_CALLS = Counter(
    "mcp_tool_calls_total",
    "Total MCP tool invocations",
    ["tool_name", "status"],
)

MCP_TOOL_DURATION = Histogram(
    "mcp_tool_duration_seconds",
    "MCP tool execution duration in seconds",
    ["tool_name"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# ════════════════════════════════════════════════════════════════
# LANGGRAPH AGENT METRICS
# ════════════════════════════════════════════════════════════════

AGENT_INVOCATIONS = Counter(
    "agent_invocations_total",
    "Total agent invocations",
    ["agent_name", "status"],
)

AGENT_DURATION = Histogram(
    "agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_name"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)


# ════════════════════════════════════════════════════════════════
# HITL METRICS
# ════════════════════════════════════════════════════════════════

HITL_APPROVALS = Counter(
    "hitl_approvals_total",
    "HITL approval requests and decisions",
    ["reason", "decision"],
)


# ════════════════════════════════════════════════════════════════
# CS1-CS4 INTEGRATION METRICS
# ════════════════════════════════════════════════════════════════

CS_CLIENT_CALLS = Counter(
    "cs_client_calls_total",
    "Calls to CS1-CS4 services",
    ["service", "endpoint", "status"],
)


# ════════════════════════════════════════════════════════════════
# DECORATORS
# ════════════════════════════════════════════════════════════════


def track_mcp_tool(tool_name: str):
    """
    Decorator to track MCP tool metrics.

    Records:
      - Call count (success/error)
      - Execution duration

    Usage:
        @track_mcp_tool("calculate_org_air_score")
        async def calculate_org_air_score(company_id: str) -> str:
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                MCP_TOOL_CALLS.labels(
                    tool_name=tool_name, status="success"
                ).inc()
                return result
            except Exception as e:
                MCP_TOOL_CALLS.labels(
                    tool_name=tool_name, status="error"
                ).inc()
                raise
            finally:
                elapsed = time.perf_counter() - start
                MCP_TOOL_DURATION.labels(
                    tool_name=tool_name
                ).observe(elapsed)
        return wrapper
    return decorator


def track_agent(agent_name: str):
    """
    Decorator to track LangGraph agent metrics.

    Records:
      - Invocation count (success/error)
      - Execution duration

    Usage:
        @track_agent("sec_analyst")
        async def analyze(self, state):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                AGENT_INVOCATIONS.labels(
                    agent_name=agent_name, status="success"
                ).inc()
                return result
            except Exception as e:
                AGENT_INVOCATIONS.labels(
                    agent_name=agent_name, status="error"
                ).inc()
                raise
            finally:
                elapsed = time.perf_counter() - start
                AGENT_DURATION.labels(
                    agent_name=agent_name
                ).observe(elapsed)
        return wrapper
    return decorator


def track_cs_client(service: str, endpoint: str):
    """
    Decorator to track CS1-CS4 client call metrics.

    Records:
      - Call count per service/endpoint (success/error)

    Usage:
        @track_cs_client("cs3", "get_assessment")
        async def get_assessment(self, company_id):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                CS_CLIENT_CALLS.labels(
                    service=service, endpoint=endpoint, status="success"
                ).inc()
                return result
            except Exception as e:
                CS_CLIENT_CALLS.labels(
                    service=service, endpoint=endpoint, status="error"
                ).inc()
                raise
        return wrapper
    return decorator

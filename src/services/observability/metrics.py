import time
from functools import wraps
from typing import Callable, Dict


class MetricsRegistry:
    def __init__(self):
        self.counters: Dict[str, int] = {
            "mcp_tool_calls_total": 0,
            "agent_invocations_total": 0,
            "hitl_approvals_total": 0,
            "cs_client_calls_total": 0,
        }
        self.durations: Dict[str, list] = {
            "mcp_tool_duration_seconds": [],
            "agent_duration_seconds": [],
            "cs_client_duration_seconds": [],
        }

    def inc(self, name: str, amount: int = 1):
        self.counters[name] = self.counters.get(name, 0) + amount

    def observe(self, name: str, value: float):
        if name not in self.durations:
            self.durations[name] = []
        self.durations[name].append(value)

    def snapshot(self) -> dict:
        return {
            "counters": self.counters,
            "durations": {
                key: {
                    "count": len(values),
                    "avg": round(sum(values) / len(values), 6) if values else 0.0,
                    "max": round(max(values), 6) if values else 0.0,
                }
                for key, values in self.durations.items()
            },
        }


metrics_registry = MetricsRegistry()


def track_mcp_tool(func: Callable):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("mcp_tool_calls_total")
            metrics_registry.observe("mcp_tool_duration_seconds", elapsed)

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("mcp_tool_calls_total")
            metrics_registry.observe("mcp_tool_duration_seconds", elapsed)

    return async_wrapper if _is_async(func) else sync_wrapper


def track_agent(func: Callable):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("agent_invocations_total")
            metrics_registry.observe("agent_duration_seconds", elapsed)

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("agent_invocations_total")
            metrics_registry.observe("agent_duration_seconds", elapsed)

    return async_wrapper if _is_async(func) else sync_wrapper


def track_cs_client(func: Callable):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return await func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("cs_client_calls_total")
            metrics_registry.observe("cs_client_duration_seconds", elapsed)

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            metrics_registry.inc("cs_client_calls_total")
            metrics_registry.observe("cs_client_duration_seconds", elapsed)

    return async_wrapper if _is_async(func) else sync_wrapper


def record_hitl_approval():
    metrics_registry.inc("hitl_approvals_total")


def _is_async(func: Callable) -> bool:
    import inspect
    return inspect.iscoroutinefunction(func)
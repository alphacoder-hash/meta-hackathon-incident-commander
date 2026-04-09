"""
services.py — Service definitions and dependency graph.

8 services: api_gateway, auth, database, cache, queue, payment, notification, cdn.
The dependency graph defines which services call which others.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Baseline service health values
# ---------------------------------------------------------------------------

@dataclass
class ServiceSpec:
    name: str
    base_latency_ms: float          # healthy baseline
    base_error_rate: float          # healthy baseline (0.0–1.0)
    base_cpu_pct: float
    base_memory_pct: float
    critical: bool = False          # is this a tier-1 service?
    last_deployed: str = "2026-03-28T10:00:00Z"

    # What happens when this service fails
    failure_latency_ms: float = 5000.0
    failure_error_rate: float = 0.95
    failure_cpu_pct: float = 95.0
    failure_memory_pct: float = 90.0


ALL_SERVICES: Dict[str, ServiceSpec] = {
    "api_gateway": ServiceSpec(
        name="api_gateway",
        base_latency_ms=45.0,
        base_error_rate=0.001,
        base_cpu_pct=30.0,
        base_memory_pct=40.0,
        critical=True,
        failure_latency_ms=8000.0,
        failure_error_rate=0.98,
    ),
    "auth": ServiceSpec(
        name="auth",
        base_latency_ms=80.0,
        base_error_rate=0.002,
        base_cpu_pct=25.0,
        base_memory_pct=35.0,
        critical=True,
        failure_latency_ms=6000.0,
        failure_error_rate=0.9,
    ),
    "database": ServiceSpec(
        name="database",
        base_latency_ms=12.0,
        base_error_rate=0.0005,
        base_cpu_pct=55.0,
        base_memory_pct=60.0,
        critical=True,
        failure_latency_ms=15000.0,
        failure_error_rate=0.99,
        failure_cpu_pct=99.0,
        failure_memory_pct=95.0,
    ),
    "cache": ServiceSpec(
        name="cache",
        base_latency_ms=2.0,
        base_error_rate=0.0001,
        base_cpu_pct=20.0,
        base_memory_pct=75.0,          # cache uses lots of memory normally
        critical=True,
        failure_latency_ms=3000.0,
        failure_error_rate=0.85,
        failure_cpu_pct=50.0,
        failure_memory_pct=99.5,        # OOM scenario
    ),
    "queue": ServiceSpec(
        name="queue",
        base_latency_ms=5.0,
        base_error_rate=0.001,
        base_cpu_pct=35.0,
        base_memory_pct=45.0,
        critical=False,
        failure_latency_ms=4000.0,
        failure_error_rate=0.7,
    ),
    "payment": ServiceSpec(
        name="payment",
        base_latency_ms=200.0,
        base_error_rate=0.005,
        base_cpu_pct=40.0,
        base_memory_pct=50.0,
        critical=True,
        failure_latency_ms=12000.0,
        failure_error_rate=0.95,
        failure_memory_pct=88.0,
    ),
    "notification": ServiceSpec(
        name="notification",
        base_latency_ms=150.0,
        base_error_rate=0.01,
        base_cpu_pct=20.0,
        base_memory_pct=30.0,
        critical=False,
        failure_latency_ms=5000.0,
        failure_error_rate=0.6,
    ),
    "cdn": ServiceSpec(
        name="cdn",
        base_latency_ms=30.0,
        base_error_rate=0.002,
        base_cpu_pct=15.0,
        base_memory_pct=25.0,
        critical=False,
        failure_latency_ms=2000.0,
        failure_error_rate=0.3,
    ),
}


# ---------------------------------------------------------------------------
# Dependency graph: service → list of services it depends on
# If a dependency fails, a service degrades proportionally.
# ---------------------------------------------------------------------------

DEPENDENCY_GRAPH: Dict[str, List[str]] = {
    "api_gateway":   ["auth", "cache", "cdn"],
    "auth":          ["database", "cache"],
    "database":      [],                        # no dependencies (leaf)
    "cache":         [],                        # no dependencies (leaf)
    "queue":         ["database"],
    "payment":       ["database", "cache", "queue"],
    "notification":  ["queue"],
    "cdn":           [],
}

# Reverse graph: service → services that depend on it (for cascade propagation)
REVERSE_GRAPH: Dict[str, List[str]] = {svc: [] for svc in ALL_SERVICES}
for svc, deps in DEPENDENCY_GRAPH.items():
    for dep in deps:
        REVERSE_GRAPH[dep].append(svc)


def get_cascade_order() -> List[str]:
    """Return services in topological order (process leaves first)."""
    visited: set = set()
    order: List[str] = []

    def dfs(node: str) -> None:
        if node in visited:
            return
        visited.add(node)
        for dep in DEPENDENCY_GRAPH[node]:
            dfs(dep)
        order.append(node)

    for svc in ALL_SERVICES:
        dfs(svc)
    return order


CASCADE_ORDER: List[str] = get_cascade_order()
SERVICE_NAMES: List[str] = list(ALL_SERVICES.keys())

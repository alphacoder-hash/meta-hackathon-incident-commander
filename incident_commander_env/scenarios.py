"""
scenarios.py — The 4 task scenarios for IncidentCommander.

Each scenario defines:
  - root_cause_id: ground truth cause the agent must discover
  - affected_services: which services start degraded
  - red_herring_alerts: misleading alerts the agent should ignore
  - max_steps: episode length
  - chaos: whether chaos injection is active
  - initial_fault: what exact fault is injected at t=0
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AlertTemplate:
    id: str
    severity: str          # "critical" | "warning" | "info"
    service: str
    message: str
    is_red_herring: bool = False


@dataclass
class Scenario:
    task_id: str
    root_cause_id: str
    affected_services: List[str]
    alert_templates: List[AlertTemplate]
    max_steps: int
    chaos: bool = False
    description: str = ""
    hints: List[str] = field(default_factory=list)


SCENARIOS: Dict[str, Scenario] = {
    # ------------------------------------------------------------------
    # Task 1 — Single Service Crash (Easy)
    # Root cause: cache OOM — cache has run out of memory and crashed.
    # ------------------------------------------------------------------
    "single_service_crash": Scenario(
        task_id="single_service_crash",
        root_cause_id="cache_oom",
        affected_services=["cache"],
        alert_templates=[
            AlertTemplate(
                id="alert_cache_down",
                severity="critical",
                service="cache",
                message="CRITICAL: cache service is returning connection refused on port 6379.",
            ),
            AlertTemplate(
                id="alert_cache_memory",
                severity="critical",
                service="cache",
                message="CRITICAL: cache memory utilization at 99.8%. OOM killer may have triggered.",
            ),
            AlertTemplate(
                id="alert_api_latency",
                severity="warning",
                service="api_gateway",
                message="WARNING: api_gateway P99 latency spiked to 4200ms. Possible upstream dependency issue.",
            ),
            # Red herring — CDN spike is unrelated
            AlertTemplate(
                id="alert_cdn_spike",
                severity="warning",
                service="cdn",
                message="WARNING: cdn cache-miss rate increased to 18%. Traffic spike detected.",
                is_red_herring=True,
            ),
        ],
        max_steps=10,
        description="A single service has crashed. Identify and fix it before customers notice.",
        hints=["Check the cache service logs", "Memory metrics may give clues"],
    ),

    # ------------------------------------------------------------------
    # Task 2 — Cascading Failure (Medium)
    # Root cause: database_overload — DB overloaded, cascading to cache,
    # auth, api_gateway.
    # ------------------------------------------------------------------
    "cascading_failure": Scenario(
        task_id="cascading_failure",
        root_cause_id="database_overload",
        affected_services=["database", "cache", "auth", "api_gateway"],
        alert_templates=[
            AlertTemplate(
                id="alert_db_cpu",
                severity="critical",
                service="database",
                message="CRITICAL: database CPU at 99%. Query queue depth: 4800. Connections exhausted.",
            ),
            AlertTemplate(
                id="alert_db_latency",
                severity="critical",
                service="database",
                message="CRITICAL: database query latency P95=45000ms. Slow query log filling up.",
            ),
            AlertTemplate(
                id="alert_auth_timeout",
                severity="critical",
                service="auth",
                message="CRITICAL: auth service timing out — cannot reach database. 503 errors on /verify.",
            ),
            AlertTemplate(
                id="alert_api_errors",
                severity="critical",
                service="api_gateway",
                message="CRITICAL: api_gateway returning 40% 503 errors. Auth dependency failing.",
            ),
            AlertTemplate(
                id="alert_cache_evict",
                severity="warning",
                service="cache",
                message="WARNING: cache eviction rate 3x normal. DB fallback causing cache stampede.",
            ),
            # Red herring — payment anomaly is from a separate AB test
            AlertTemplate(
                id="alert_payment_ab",
                severity="warning",
                service="payment",
                message="WARNING: payment success rate dropped 2%. Investigating AB test variant.",
                is_red_herring=True,
            ),
        ],
        max_steps=15,
        description="A cascading failure is spreading. Find the root cause before the whole system goes down.",
        hints=["Start with the service that has the most downstream dependents", "Check DB connection pools"],
    ),

    # ------------------------------------------------------------------
    # Task 3 — Bad Deployment (Medium-Hard)
    # Root cause: payment_bad_deploy — payment service deployed with a
    # bug that causes it to crash-loop.
    # ------------------------------------------------------------------
    "bad_deployment": Scenario(
        task_id="bad_deployment",
        root_cause_id="payment_bad_deploy",
        affected_services=["payment", "queue", "notification"],
        alert_templates=[
            AlertTemplate(
                id="alert_payment_crash",
                severity="critical",
                service="payment",
                message="CRITICAL: payment service crash-looping. Exit code 1. Deployment v2.4.1 detected.",
            ),
            AlertTemplate(
                id="alert_payment_errors",
                severity="critical",
                service="payment",
                message="CRITICAL: payment processing error rate 94%. Revenue impact: ~$12,000/min.",
            ),
            AlertTemplate(
                id="alert_queue_backup",
                severity="warning",
                service="queue",
                message="WARNING: queue depth at 24,000 messages. Consumer lag growing.",
            ),
            AlertTemplate(
                id="alert_notification_fail",
                severity="warning",
                service="notification",
                message="WARNING: notification service cannot dequeue. Order confirmation emails delayed.",
            ),
            # Red herring 1 — DB replica lag is normal maintenance
            AlertTemplate(
                id="alert_db_replica_lag",
                severity="warning",
                service="database",
                message="WARNING: database replica lag 800ms. Read replicas may be slightly stale.",
                is_red_herring=True,
            ),
            # Red herring 2 — CDN certificate renewal is scheduled
            AlertTemplate(
                id="alert_cdn_cert",
                severity="info",
                service="cdn",
                message="INFO: cdn TLS certificate renewal in progress. Brief 200ms latency increase expected.",
                is_red_herring=True,
            ),
        ],
        max_steps=15,
        description="A bad deployment is causing havoc. Rollback before revenue impact becomes critical.",
        hints=["Check recent deployments", "Compare error rates before/after deployment timestamp"],
    ),

    # ------------------------------------------------------------------
    # Task 4 — Silent Degradation (Hard) + Chaos
    # Root cause: payment_memory_leak — payment service has a slow
    # memory leak. Latency creeps up invisibly until it OOMs.
    # ------------------------------------------------------------------
    "silent_degradation": Scenario(
        task_id="silent_degradation",
        root_cause_id="payment_memory_leak",
        affected_services=["payment"],
        alert_templates=[
            AlertTemplate(
                id="alert_payment_latency",
                severity="warning",
                service="payment",
                message="WARNING: payment service P99 latency increased from 200ms to 850ms over last 2 hours.",
            ),
            AlertTemplate(
                id="alert_payment_memory_trend",
                severity="warning",
                service="payment",
                message="WARNING: payment memory utilization trending up: 52% → 61% → 73% (past 90 min).",
            ),
            # Red herring 1 — auth latency is from a new token validation feature
            AlertTemplate(
                id="alert_auth_latency",
                severity="info",
                service="auth",
                message="INFO: auth latency increased 40ms. New JWT validation feature deployed yesterday.",
                is_red_herring=True,
            ),
            # Red herring 2 — DB replication is fine, just log noise
            AlertTemplate(
                id="alert_db_connections",
                severity="warning",
                service="database",
                message="WARNING: database connection pool at 68%. Normal for this time of day.",
                is_red_herring=True,
            ),
            # Red herring 3 — CDN anomaly from marketing campaign
            AlertTemplate(
                id="alert_cdn_traffic",
                severity="info",
                service="cdn",
                message="INFO: cdn traffic 3x normal. Marketing campaign started at 09:00.",
                is_red_herring=True,
            ),
        ],
        max_steps=20,
        chaos=True,
        description="Something is slowly degrading the system. Find the leak before it causes a full outage.",
        hints=["Memory trends are more telling than instantaneous values", "Look for gradual increases"],
    ),
}

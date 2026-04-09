"""
log_generator.py — Generates realistic syslog/JSON log lines per service.

Logs are tailored to the active scenario: failing services emit error logs
with realistic stack traces; healthy services emit normal access logs.
"""
from __future__ import annotations

import random
from typing import List


# ---------------------------------------------------------------------------
# Realistic log templates per service × health state
# ---------------------------------------------------------------------------

_HEALTHY_LOGS = {
    "api_gateway": [
        'INFO  2026-03-28T{t}Z api_gateway [access] GET /api/v1/products 200 42ms',
        'INFO  2026-03-28T{t}Z api_gateway [access] POST /api/v1/orders 201 87ms',
        'INFO  2026-03-28T{t}Z api_gateway [router] Upstream auth latency P95=78ms — OK',
        'DEBUG 2026-03-28T{t}Z api_gateway [cache] Cache HIT rate 94.2%',
        'INFO  2026-03-28T{t}Z api_gateway [health] All upstreams healthy',
    ],
    "auth": [
        'INFO  2026-03-28T{t}Z auth [jwt] Token validated in 3.1ms uid=user_88421',
        'INFO  2026-03-28T{t}Z auth [session] Session created ttl=3600s',
        'DEBUG 2026-03-28T{t}Z auth [cache] Redis SETEX uid:88421 OK',
        'INFO  2026-03-28T{t}Z auth [db] SELECT users WHERE id=88421 → 1 row 2.1ms',
    ],
    "database": [
        'INFO  2026-03-28T{t}Z database [query] SELECT products LIMIT 20 → 20 rows 8ms',
        'INFO  2026-03-28T{t}Z database [pool] 42/200 connections active',
        'DEBUG 2026-03-28T{t}Z database [repl] Replica lag 12ms — within SLO',
        'INFO  2026-03-28T{t}Z database [vacuum] Auto-vacuum completed on orders table',
    ],
    "cache": [
        'INFO  2026-03-28T{t}Z cache [redis] GET user:session:88421 HIT 0.3ms',
        'INFO  2026-03-28T{t}Z cache [redis] SETEX product:list TTL=300 OK',
        'DEBUG 2026-03-28T{t}Z cache [memory] used_memory=2.4GB maxmemory=4GB (60%)',
        'INFO  2026-03-28T{t}Z cache [evict] evicted_keys=0 hit_rate=0.97',
    ],
    "queue": [
        'INFO  2026-03-28T{t}Z queue [consumer] Processed order.placed event lag=120ms',
        'DEBUG 2026-03-28T{t}Z queue [broker] Queue depth: 42 messages',
        'INFO  2026-03-28T{t}Z queue [producer] Published notification.send event OK',
    ],
    "payment": [
        'INFO  2026-03-28T{t}Z payment [stripe] charge_id=ch_abc123 status=succeeded 210ms',
        'INFO  2026-03-28T{t}Z payment [processor] Transaction TX_88421 completed in 198ms',
        'DEBUG 2026-03-28T{t}Z payment [health] DB pool 18/50 active, cache OK',
    ],
    "notification": [
        'INFO  2026-03-28T{t}Z notification [email] Sent order_confirmation to user@example.com OK',
        'INFO  2026-03-28T{t}Z notification [sms] SMS dispatched to +1-555-0188 OK',
        'DEBUG 2026-03-28T{t}Z notification [queue] Consumer lag 0ms',
    ],
    "cdn": [
        'INFO  2026-03-28T{t}Z cdn [cache] Cache HIT /static/app.js cf-ray=abc123',
        'INFO  2026-03-28T{t}Z cdn [edge] PoP SIN latency 24ms',
        'DEBUG 2026-03-28T{t}Z cdn [origin] Fetched /api/assets/logo.png 200 31ms',
    ],
}

_FAILURE_LOGS = {
    "cache_oom": [
        'WARN  2026-03-28T{t}Z cache [memory] used_memory=3.98GB maxmemory=4GB (99.5%) — near OOM',
        'ERROR 2026-03-28T{t}Z cache [oom] OOM killer triggered: killing redis-server (pid 1847)',
        'ERROR 2026-03-28T{t}Z cache [redis] FATAL: Cannot allocate memory — server aborting',
        'ERROR 2026-03-28T{t}Z api_gateway [upstream] cache upstream unreachable: connection refused :6379',
        'ERROR 2026-03-28T{t}Z auth [cache] Redis connection failed: ECONNREFUSED 127.0.0.1:6379',
        'WARN  2026-03-28T{t}Z cache [evict] eviction_policy=allkeys-lru evicted_keys=142000 in last 60s',
        'ERROR 2026-03-28T{t}Z cache [replication] Replica sync aborted — master OOM restarting',
        'WARN  2026-03-28T{t}Z api_gateway [fallback] Cache miss fallback to DB for all requests — expect latency spike',
    ],
    "database_overload": [
        'ERROR 2026-03-28T{t}Z database [pool] Connection pool exhausted: 200/200 connections active',
        'ERROR 2026-03-28T{t}Z database [query] FATAL: remaining connection slots reserved for replication',
        'WARN  2026-03-28T{t}Z database [slow] Slow query log: SELECT * FROM orders took 42000ms',
        'ERROR 2026-03-28T{t}Z database [cpu] CPU 99.8% — query planner unable to schedule new queries',
        'ERROR 2026-03-28T{t}Z auth [db] Timeout connecting to database after 30s: dial tcp :5432 timeout',
        'ERROR 2026-03-28T{t}Z auth [handler] 503 Service Unavailable: database unreachable',
        'ERROR 2026-03-28T{t}Z api_gateway [upstream] auth returned 503: upstream database overloaded',
        'WARN  2026-03-28T{t}Z cache [stampede] Cache stampede detected — 8200 concurrent DB fallback requests',
    ],
    "payment_bad_deploy": [
        'ERROR 2026-03-28T{t}Z payment [startup] Panic: runtime error: invalid memory address — deployment v2.4.1',
        'ERROR 2026-03-28T{t}Z payment [startup] goroutine 1 [running]: main.initPaymentGateway() +0x4f2',
        'WARN  2026-03-28T{t}Z payment [k8s] CrashLoopBackOff: restarted 8 times in 3 minutes',
        'ERROR 2026-03-28T{t}Z payment [config] PAYMENT_GATEWAY_SECRET missing from environment — abort()',
        'WARN  2026-03-28T{t}Z queue [consumer] payment consumer lag growing: 24000 messages unprocessed',
        'ERROR 2026-03-28T{t}Z payment [charge] charge_id=ch_def456 FAILED: service unavailable',
        'WARN  2026-03-28T{t}Z notification [queue] Cannot dequeue — payment events pending: queue depth 24k',
        'INFO  2026-03-28T{t}Z payment [deploy] Deployed payment-service:v2.4.1 at 2026-03-28T09:47:00Z (prev: v2.3.9)',
    ],
    "payment_memory_leak": [
        'DEBUG 2026-03-28T{t}Z payment [memory] Heap: 1.2GB (step 1) — baseline',
        'WARN  2026-03-28T{t}Z payment [memory] Heap: 1.8GB (step 5) — 50% increase, leak suspected',
        'WARN  2026-03-28T{t}Z payment [memory] Heap: 2.4GB (step 10) — 100% increase from baseline',
        'WARN  2026-03-28T{t}Z payment [latency] P99 latency 850ms — GC pressure from growing heap',
        'WARN  2026-03-28T{t}Z payment [gc] GC pause 420ms — heap fragmentation increasing',
        'DEBUG 2026-03-28T{t}Z payment [profile] goroutine leak: 8400 goroutines alive (normal: 200)',
        'WARN  2026-03-28T{t}Z payment [memory] memory_rss=3.1GB — approaching container limit (4GB)',
    ],
}

_CHAOS_LOGS = [
    'WARN  2026-03-28T{t}Z chaos-monkey [inject] Random latency injected into cdn (+500ms)',
    'WARN  2026-03-28T{t}Z chaos-monkey [inject] Dropped 5% of packets at notification ingress',
    'INFO  2026-03-28T{t}Z chaos-controller [status] Chaos mode ACTIVE — resilience testing in progress',
    'WARN  2026-03-28T{t}Z chaos-monkey [inject] CPU stress on queue service for 30s',
]

_RED_HERRING_LOGS = [
    'INFO  2026-03-28T{t}Z cdn [traffic] Marketing campaign traffic spike: 3x normal volume',
    'INFO  2026-03-28T{t}Z database [replica] Replica lag 800ms during maintenance window — expected',
    'INFO  2026-03-28T{t}Z cdn [cert] TLS certificate auto-renewal triggered — 200ms blip expected',
    'WARN  2026-03-28T{t}Z auth [feature] New JWT validation adding ~40ms — feature flag: jwt_v2_enabled',
    'INFO  2026-03-28T{t}Z payment [ab-test] AB test variant B active for 10% of payment traffic',
]


def _ts(step: int) -> str:
    """Fake timestamp based on step number."""
    hour = 10 + (step // 60)
    minute = step % 60
    return f"{hour:02d}:{minute:02d}:{step % 60:02d}"


def generate_logs(
    root_cause_id: str,
    step: int,
    healthy_services: List[str],
    failing_services: List[str],
    chaos_active: bool = False,
    rng: random.Random = None,
) -> List[str]:
    """
    Generate ~20 log lines for the current step.
    Mix of healthy, failure, and (optionally) chaos/red-herring logs.
    """
    if rng is None:
        rng = random.Random(step)

    logs: List[str] = []
    t = _ts(step)

    # Healthy service logs (2–3 per healthy service, capped at 8 total)
    for svc in rng.sample(healthy_services, min(4, len(healthy_services))):
        templates = _HEALTHY_LOGS.get(svc, [])
        if templates:
            chosen = rng.sample(templates, min(2, len(templates)))
            logs.extend(line.format(t=t) for line in chosen)

    # Failure logs (always present for the root cause)
    failure_templates = _FAILURE_LOGS.get(root_cause_id, [])
    if failure_templates:
        # Show more failure logs as step count increases
        n = min(3 + step // 3, len(failure_templates))
        chosen = rng.sample(failure_templates, n)
        logs.extend(line.format(t=t) for line in chosen)

    # Red herring logs (1–2, random)
    n_red = rng.randint(0, 2)
    sampled_rh = rng.sample(_RED_HERRING_LOGS, min(n_red, len(_RED_HERRING_LOGS)))
    logs.extend(line.format(t=t) for line in sampled_rh)

    # Chaos logs
    if chaos_active and rng.random() < 0.5:
        logs.append(rng.choice(_CHAOS_LOGS).format(t=t))

    rng.shuffle(logs)
    return logs[:20]   # cap at 20 lines

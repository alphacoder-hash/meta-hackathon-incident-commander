"""
server/graders.py — Pure-Python grader logic and scenario definitions.

This module has ZERO external dependencies (no openenv, no FastAPI).
This makes it instantly importable for local testing and pytest suites
without triggering the openenv framework's network bootstrapping.

Pattern matches the winning finalist repo:
  - Scenarios stored as dicts with keyword lists (not hardcoded inside graders)
  - grade_easy / grade_medium / grade_hard all accept (response, scenario) signature
  - Medium grader hard-caps at 0.45 unless red herring is explicitly flagged
  - Hard grader applies exclusivity penalty for keywords dumped in first third
"""

from typing import List


# ── Easy Scenarios ────────────────────────────────────────────────────────────
# Each scenario: one clearly failing service, symptoms obvious from logs.
# Agent must name the service + root cause. No red herrings (easy tier).

EASY_SCENARIOS: List[dict] = [
    {
        "id": "easy_cache_oom",
        "incident_report": """
🚨 INCIDENT REPORT — 02:47 UTC
Severity: P2 | Duration: 8 minutes and ongoing

Error logs:
  [ERROR] cache: Connection refused on port 6379
  [ERROR] cache: OOM killer triggered — process killed (RSS 3.9 GB / limit 4.0 GB)
  [WARN]  api_gateway: P99 latency spiked to 4,200ms — upstream cache unavailable
  [INFO]  auth: Operating normally
  [INFO]  database: Operating normally

User reports: "App is slow", "Getting timeouts", "Pages not loading"

Question: Which service is failing and what is the root cause?
""",
        "keywords": [
            "cache", "oom", "out of memory", "memory", "cache_oom",
            "redis", "connection refused", "clear_cache", "clear cache",
        ],
        "required_count": 2,
    },
    {
        "id": "easy_db_pool",
        "incident_report": """
🚨 INCIDENT REPORT — 09:15 UTC
Severity: P2 | Duration: 12 minutes and ongoing

Error logs:
  [ERROR] database: Connection pool exhausted (max_connections=100, active=100)
  [ERROR] database: Query timeout after 30s — queue depth 4,800
  [WARN]  auth: Cannot reach database — returning 503 on /verify
  [ERROR] payment: Upstream database unavailable — 847 failed transactions
  [INFO]  cdn: Operating normally
  [INFO]  notification: Operating normally

User reports: "Cannot checkout", "Payment keeps failing", "Getting 503 errors"

Question: Which service is failing and what is the root cause?
""",
        "keywords": [
            "database", "db", "connection", "pool", "exhausted",
            "database_overload", "overload", "timeout", "failover",
        ],
        "required_count": 2,
    },
    {
        "id": "easy_payment_crash",
        "incident_report": """
🚨 INCIDENT REPORT — 16:32 UTC
Severity: P2 | Duration: 5 minutes and ongoing

Error logs:
  [ERROR] payment: Crash-loop detected — exit code 1, restart count 8
  [ERROR] payment: NullPointerException at startup in PaymentProcessor.init()
  [ERROR] payment: Deployment v2.4.1 rolled out at 16:27 UTC
  [WARN]  queue: Consumer lag growing — 24,000 messages unprocessed
  [INFO]  auth: Operating normally
  [INFO]  api_gateway: Operating normally

User reports: "Payment not working", "Order stuck at checkout", "Transaction failed"

Question: Which service is failing and what is the root cause?
""",
        "keywords": [
            "payment", "crash", "crash-loop", "deploy", "deployment",
            "rollback", "payment_bad_deploy", "v2.4.1", "null pointer",
        ],
        "required_count": 2,
    },
]


# ── Medium Scenarios ──────────────────────────────────────────────────────────
# Three signals: one root cause (Signal B or C), one symptom (Signal A),
# one explicit RED HERRING. Agent must identify root cause AND flag red herring.

MEDIUM_SCENARIOS: List[dict] = [
    {
        "id": "medium_gpu",
        "incident_report": """
🚨 INCIDENT REPORT — 14:23 UTC
Severity: P1 | Duration: 8 minutes and ongoing

Signal A — Application logs:
  [ERROR] RecommendationService: Response time 8,400ms (threshold: 500ms)
  [ERROR] RecommendationService: Timeout calling ML model endpoint
  [WARN]  RecommendationService: Falling back to cached recommendations

Signal B — Infrastructure logs:
  [WARN]  MLModelServer: GPU memory utilization 97%
  [ERROR] MLModelServer: OOM killed worker process (3 times in 10 min)
  [INFO]  MLModelServer: Auto-restarting workers

Signal C — Network logs (RED HERRING):
  [WARN]  LoadBalancer: Elevated latency on eu-west-2 (120ms vs 40ms baseline)
  [INFO]  LoadBalancer: All health checks passing
  [INFO]  NetworkMonitor: No packet loss detected

Question: What is the ROOT CAUSE? Which signal is the root cause and which are symptoms/red herrings?
""",
        "root_cause_keywords": [
            "gpu", "memory", "oom", "ml model", "mlmodel", "out of memory",
            "infrastructure", "signal b", "worker",
        ],
        "red_herring_keywords": [
            "network", "loadbalancer", "load balancer", "latency", "signal c",
            "eu-west", "packet",
        ],
        "symptom_keywords": [
            "recommendationservice", "recommendation", "timeout", "signal a",
        ],
    },
    {
        "id": "medium_cache_cluster",
        "incident_report": """
🚨 INCIDENT REPORT — 11:05 UTC
Severity: P1 | Duration: 15 minutes and ongoing

Signal A — Infrastructure logs (RED HERRING):
  [WARN]  CDNProvider: Cache hit ratio dropped from 94% to 71%
  [INFO]  CDNProvider: No errors reported, serving traffic normally
  [INFO]  CDNProvider: All edge nodes healthy

Signal B — Application logs:
  [ERROR] api_gateway: Response time 12,000ms (threshold: 200ms)
  [ERROR] api_gateway: cache connection refused — falling back to database
  [ERROR] api_gateway: 40% of requests returning 503

Signal C — Infrastructure logs:
  [ERROR] cache: Primary node unreachable — port 6379 refused
  [ERROR] cache: Failover initiated — replica promotion failed
  [ERROR] cache: Cluster in degraded state — OOM on primary

Question: What is the ROOT CAUSE? Which signal is the root cause and which are symptoms/red herrings?
""",
        "root_cause_keywords": [
            "cache", "redis", "cluster", "signal c", "primary node",
            "failover", "oom", "promotion failed",
        ],
        "red_herring_keywords": [
            "cdn", "signal a", "cache hit", "edge", "cdnprovider",
        ],
        "symptom_keywords": [
            "api_gateway", "apigateway", "signal b", "response time", "503",
        ],
    },
    {
        "id": "medium_cert_expiry",
        "incident_report": """
🚨 INCIDENT REPORT — 00:01 UTC
Severity: P1 | Duration: 3 minutes and ongoing

Signal A — Application logs:
  [ERROR] api_gateway: SSL handshake failed for all HTTPS requests
  [ERROR] api_gateway: Certificate validation error — chain broken
  [ERROR] api_gateway: 100% of requests failing

Signal B — Infrastructure logs (RED HERRING):
  [WARN]  AutoScaler: Adding 3 new instances due to error rate spike
  [INFO]  AutoScaler: New instances healthy and serving traffic
  [INFO]  LoadBalancer: Traffic distributed across 7 instances

Signal C — Security logs:
  [ERROR] CertificateManager: TLS certificate expired at 00:00:00 UTC
  [ERROR] CertificateManager: Auto-renewal failed — DNS validation error
  [WARN]  CertificateManager: Certificate was due for renewal 7 days ago

Question: What is the ROOT CAUSE? Which signal is the root cause and which are symptoms/red herrings?
""",
        "root_cause_keywords": [
            "certificate", "cert", "tls", "ssl", "expired", "signal c",
            "certificatemanager", "renewal", "dns validation",
        ],
        "red_herring_keywords": [
            "autoscaler", "scaling", "signal b", "instances", "loadbalancer",
        ],
        "symptom_keywords": [
            "apigateway", "api_gateway", "signal a", "handshake", "https",
        ],
    },
]


# ── Hard Scenarios ────────────────────────────────────────────────────────────
# Complex cascading failures. Agent must produce a PRIORITIZED action plan:
# FIRST action addresses root cause, SECOND addresses symptoms, THIRD monitors.
# Scored on positional correctness of keywords across response thirds.

HARD_SCENARIOS: List[dict] = [
    {
        "id": "hard_auth_secret",
        "incident_report": """
🚨 INCIDENT REPORT — 03:15 UTC
Severity: P0 — Full outage | Duration: 23 minutes and escalating

Service map: api_gateway → auth → database
             api_gateway → payment → database, cache, queue
             api_gateway → notification → queue

Logs:
  [ERROR] api_gateway: 89% requests returning 502
  [ERROR] auth: JWT validation failing — secret key mismatch
  [ERROR] auth: CONFIG_VERSION=v2 but tokens signed with v1 key
  [WARN]  payment: Cannot validate user sessions — auth failing
  [ERROR] payment: All transactions failing auth check
  [ERROR] queue: Backing up — 4,200 messages unprocessed
  [WARN]  notification: Cannot dequeue — payment upstream failing

Recent deploys:
  03:01 UTC — auth v2.1.0 (JWT_SECRET rotated in config)
  02:45 UTC — database v1.8.2 (index optimization — unrelated)

Question: Write a PRIORITIZED action plan — FIRST, SECOND, THIRD steps to restore service and WHY.
""",
        "first_keywords": [
            "auth", "jwt", "secret", "rollback", "revert", "config",
            "key", "auth v2", "jwt_secret",
        ],
        "second_keywords": [
            "payment", "queue", "restart", "payment", "clear",
            "cache", "transaction",
        ],
        "third_keywords": [
            "notification", "monitor", "alert", "watch", "verify",
            "check", "metrics",
        ],
    },
    {
        "id": "hard_db_cascade",
        "incident_report": """
🚨 INCIDENT REPORT — 18:44 UTC
Severity: P0 — Full outage | Duration: 31 minutes and escalating

Service map: api_gateway → auth → database
             api_gateway → payment → database, cache, queue
             payment → queue → database

Logs:
  [ERROR] api_gateway: 94% of requests failing — auth and payment both down
  [ERROR] database: CPU at 99% — query queue depth 4,200 — connections exhausted
  [ERROR] auth: Cannot reach database — returning 503 on /verify
  [ERROR] payment: Cannot reach database — all transactions failing
  [ERROR] cache: Eviction storm — 80% miss rate — stampeding to database
  [ERROR] queue: Consumer lag 47 seconds — dependent on database
  [WARN]  notification: Delayed — queue backing up

Recent deploys:
  18:30 UTC — payment v3.1 (new DB query patterns — 3x more connections)
  18:15 UTC — cache v2.8 (TTL reduced from 1hr to 5min — causing stampede)

Question: Write a PRIORITIZED action plan — FIRST, SECOND, THIRD steps to restore service and WHY.
""",
        "first_keywords": [
            "database", "db", "failover", "failover_db", "scale_up", "scale up",
            "replica", "database_overload", "cpu", "connection",
        ],
        "second_keywords": [
            "cache", "payment", "rollback", "revert", "ttl",
            "eviction", "cache stampede",
        ],
        "third_keywords": [
            "notification", "queue", "monitor", "auth", "verify",
            "restart", "check", "metrics",
        ],
    },
    {
        "id": "hard_memory_leak",
        "incident_report": """
🚨 INCIDENT REPORT — 22:05 UTC
Severity: P0 — Degrading | Duration: 45 minutes and worsening

Service map: api_gateway → payment → database, cache
             api_gateway → auth → database

Chaos injection ACTIVE on non-critical services.

Logs:
  [WARN]  payment: Memory utilization trending up — 52% → 61% → 73% → 88% (past 2hr)
  [WARN]  payment: P99 latency increased from 200ms to 1,400ms
  [ERROR] payment: Goroutine leak detected — 12,000 goroutines (normal: 200)
  [INFO]  auth: Latency +40ms — new JWT validation feature deployed yesterday (expected)
  [WARN]  database: Connection pool at 68% — normal for this time of day
  [INFO]  cdn: Traffic 3x normal — marketing campaign started at 09:00

Chaos events: Intermittent latency spikes on cdn and notification (ignore — chaos injected)

Question: Write a PRIORITIZED action plan — FIRST, SECOND, THIRD steps to restore service and WHY.
""",
        "first_keywords": [
            "payment", "memory", "leak", "payment_memory_leak", "goroutine",
            "heap", "memory_pct", "diagnose", "restart payment",
        ],
        "second_keywords": [
            "restart", "restart_service", "flush", "heap", "clear",
            "scale", "rollback", "monitor memory",
        ],
        "third_keywords": [
            "monitor", "alert", "watch", "metrics", "check_metrics",
            "canary", "verify", "chaos", "auth", "database",
        ],
    },
]


# ── Graders ───────────────────────────────────────────────────────────────────

def safe_reward(raw: float) -> float:
    """Clamp the reward strictly between 0.01 and 0.99 to pass OpenEnv validation."""
    return round(min(max(float(raw), 0.01), 0.99), 2)


def grade_easy(response: str, scenario: dict) -> float:
    """
    Easy task — single failing service, obvious from logs.
    Agent must name the service and root cause.

    Scoring:
      - 0.5 + partial bonus for keyword hits >= required_count
      - +0.10 bonus if agent explicitly states root cause
      - Cap: 0.95
    """
    r = response.lower()
    keywords = scenario["keywords"]
    required = scenario["required_count"]

    # Count keyword hits, filter out negations like "not cache" / "not a cache issue"
    hits = sum(
        1 for kw in keywords
        if kw in r and f"not {kw}" not in r and f"not a {kw}" not in r
    )

    if hits >= required:
        # Scale: required+0 → 0.50, each extra → +0.10, max +0.40
        score = 0.50 + min(0.40, (hits - required) * 0.10 + 0.30)
    elif hits == 1:
        score = 0.30
    else:
        score = 0.05

    # Bonus for explicit root cause statement
    root_cause_terms = [
        "root cause", "cause is", "failing because", "due to",
        "caused by", "reason is", "the issue is",
    ]
    if any(term in r for term in root_cause_terms):
        score = min(1.0, score + 0.10)

    return safe_reward(min(score, 0.95))


def grade_medium(response: str, scenario: dict) -> float:
    """
    Medium task — multi-signal incident with one explicit RED HERRING.
    Agent must: (1) identify root cause, (2) explicitly flag the red herring,
    (3) identify symptom services.

    Key rule (matches winning repo): If the agent does NOT explicitly flag the red
    herring with strict dismissal language, score is hard-capped at 0.45.

    Scoring:
      - Root cause identification: up to 0.35
      - Red herring explicit flag: 0.30 (REQUIRED for score > 0.45)
      - Symptom identification: 0.15
      - Correct signal letter named: 0.10 bonus
      - Cap: 0.80
    """
    r = response.lower()
    score = 0.0

    # Determine target signal letter for this scenario
    signal_map = {
        "medium_gpu": "signal b",
        "medium_cache_cluster": "signal c",
        "medium_cert_expiry": "signal c",
    }
    target_signal = signal_map.get(scenario["id"], "")

    # ── Root cause identification (35%) ──────────────────────────────────────
    root_hits = sum(1 for kw in scenario["root_cause_keywords"] if kw in r)
    causal_terms = [
        "because", "due to", "since", "causes", "resulting",
        "as a result", "leads to", "indicates", "root cause",
    ]
    has_explanation = any(term in r for term in causal_terms)

    if root_hits >= 2 and has_explanation:
        score += 0.35
    elif root_hits >= 1 and has_explanation:
        score += 0.15
    elif root_hits >= 1:
        score += 0.05

    # ── Red herring explicit flag (30%) — STRICT ──────────────────────────────
    # Agent MUST use explicit dismissal language AND name the red herring.
    # "not the cause" is intentionally excluded — too easy to accidentally include.
    strict_dismissal_terms = [
        "red herring", "false alarm", "misleading", "symptom only",
        "coincidental", "irrelevant", "not related", "unrelated",
        "distraction", "noise",
    ]
    dismissal_hits = sum(1 for term in strict_dismissal_terms if term in r)
    rh_name_hits = sum(1 for kw in scenario["red_herring_keywords"] if kw in r)

    # BOTH conditions must be satisfied
    red_herring_identified = dismissal_hits >= 1 and rh_name_hits >= 1
    if red_herring_identified:
        score += 0.30

    # ── Symptom identification (15%) ──────────────────────────────────────────
    symptom_hits = sum(1 for kw in scenario["symptom_keywords"] if kw in r)
    if symptom_hits >= 1:
        score += 0.15

    # ── Correct signal letter bonus (10%) ────────────────────────────────────
    if target_signal and target_signal in r:
        score += 0.10

    # ── HARD CAP — the key differentiator ────────────────────────────────────
    # Models that correctly ID the root cause but miss the red herring are capped.
    # This forces models to explicitly reason about distractors.
    if not red_herring_identified:
        score = min(score, 0.45)

    return safe_reward(min(score, 0.80))


def grade_hard(response: str, scenario: dict) -> float:
    """
    Hard task — cascading P0 outage. Agent must write a PRIORITIZED action plan.
    Scored on positional correctness across response thirds.

    Key features (matches winning repo):
      - Exclusivity penalty: -0.15 per case where second/third keywords appear in FIRST THIRD
        (prevents LLMs from dumping all keywords upfront to game scoring)
      - Wrong-service penalty: -0.20 if wrong service is first priority
      - Prioritization bonus: +0.10 for explicit step language
      - Cap: 0.75
    """
    r = response.lower()
    lines = [line for line in r.split("\n") if line.strip()]
    score = 0.0

    if not lines:
        return safe_reward(0.01)

    # Split into thirds (positional scoring)
    third = max(1, len(lines) // 3)
    first_part = " ".join(lines[:third])
    mid_part = " ".join(lines[third: 2 * third])
    last_part = " ".join(lines[2 * third:])

    # ── Wrong-service penalty ─────────────────────────────────────────────────
    wrong_service_penalty = 0.0
    wrong_map = {
        "hard_auth_secret": ["queue", "notification", "database"],
        "hard_db_cascade": ["notification", "auth", "cdn"],
        "hard_memory_leak": ["auth", "database", "cdn", "cache"],
    }
    wrong_first = wrong_map.get(scenario["id"], [])
    if any(kw in first_part for kw in wrong_first) and \
       not any(kw in first_part for kw in scenario["first_keywords"]):
        wrong_service_penalty = 0.20

    # ── Positional scoring ────────────────────────────────────────────────────
    first_in_position = any(kw in first_part for kw in scenario["first_keywords"])
    second_in_position = any(kw in mid_part for kw in scenario["second_keywords"])
    third_in_position = any(kw in last_part for kw in scenario["third_keywords"])

    if first_in_position:
        score += 0.40
    if second_in_position:
        score += 0.30
    if third_in_position:
        score += 0.20

    # ── Exclusivity penalty ────────────────────────────────────────────────────
    # Penalise LLMs that dump SECOND and THIRD tier keywords right in the first third.
    exclusivity_penalty = 0.0
    if any(kw in first_part for kw in scenario["second_keywords"]):
        exclusivity_penalty += 0.15
    if any(kw in first_part for kw in scenario["third_keywords"]):
        exclusivity_penalty += 0.15

    # ── Prioritization language bonus (10%) ───────────────────────────────────
    priority_terms = [
        "first", "second", "third", "step 1", "step 2", "step 3",
        "priority", "immediately", "then", "finally", "next",
    ]
    if sum(1 for t in priority_terms if t in r) >= 3:
        score += 0.10

    # ── Apply penalties ───────────────────────────────────────────────────────
    score -= wrong_service_penalty
    score -= exclusivity_penalty

    # Cap if root cause not addressed first
    if not first_in_position:
        score = min(score, 0.40)

    # Require structured response (>=5 lines) for score > 0.5
    if len(lines) < 5:
        score = min(score, 0.30)

    return safe_reward(min(score, 0.75))

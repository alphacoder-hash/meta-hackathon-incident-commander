"""
inference.py — IncidentCommander agent loop using OpenAI client.

Mandatory environment variables:
  API_BASE_URL   default: https://router.huggingface.co/v1
  HF_TOKEN       your Hugging Face token (used as API key)
  MODEL_NAME     model to use, e.g. "meta-llama/Llama-3.3-70B-Instruct"

Run:
  python inference.py
"""
from __future__ import annotations

import json
import os
import re
import textwrap
from typing import List

from openai import OpenAI

from incident_commander_env import ActionType, IncidentAction, IncidentCommanderEnv

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = os.getenv("HF_TOKEN") or os.getenv("OPENAI_API_KEY") or os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")

VALID_ACTIONS = [a.value for a in ActionType]
SERVICES = [
    "api_gateway", "auth", "database", "cache",
    "queue", "payment", "notification", "cdn",
]
ROOT_CAUSES = [
    "cache_oom", "database_overload",
    "payment_bad_deploy", "payment_memory_leak",
]
TASKS = [
    "single_service_crash",
    "cascading_failure",
    "bad_deployment",
    "silent_degradation",
]

ACTION_PATTERN = re.compile(r'\{[^{}]*\}', re.DOTALL)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert Site Reliability Engineer (SRE) managing a live production incident
    in an 8-service microservices system. Your goal is to identify the root cause and
    restore all affected services as quickly as possible.

    === SERVICES ===
    api_gateway, auth, database, cache, queue, payment, notification, cdn

    === DEPENDENCY GRAPH ===
    api_gateway → auth, cache, cdn
    auth → database, cache
    payment → database, cache, queue
    queue → database
    notification → queue

    === AVAILABLE ACTIONS ===
    CHECK_LOGS        – Inspect logs of a target_service
    CHECK_METRICS     – Check CPU, memory, latency, error_rate of a target_service
    TRACE_REQUEST     – Trace a request through a target_service
    RESTART_SERVICE   – Restart a target_service (clears OOM, not bad deploys)
    SCALE_UP          – Scale up a target_service (helps with overload)
    ROLLBACK          – Rollback a target_service to previous version (fixes bad deploys)
    FAILOVER_DB       – Failover database to read replica (fixes DB overload)
    CLEAR_CACHE       – Flush the cache completely (fixes cache OOM)
    DIAGNOSE          – Declare root_cause_id (one of the root causes below)
    ESCALATE          – Escalate to senior team (last resort, heavy penalty)

    === ROOT CAUSES ===
    cache_oom           – Cache ran out of memory
    database_overload   – Database overwhelmed with connections / CPU
    payment_bad_deploy  – Payment service bad deployment (crash-looping)
    payment_memory_leak – Payment service slow memory leak (silent degradation)

    === STRATEGY ===
    1. Start by checking logs/metrics of services with CRITICAL alerts.
    2. Follow the dependency graph: if a downstream service is failing, find the root.
    3. Once you identify the root cause, DIAGNOSE first, then apply the correct fix.
    4. Only ESCALATE if you are truly stuck — it costs −2.0 reward.
    5. Avoid restarting healthy services (−1.0 unnecessary restart penalty).

    === OUTPUT FORMAT ===
    Reply with ONLY a valid JSON object (no markdown, no explanation):
    {"action_type": "...", "target_service": "...", "root_cause_id": "..."}

    Omit "target_service" if not needed. Omit "root_cause_id" unless action is DIAGNOSE.
""").strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_action(response_text: str) -> dict:
    match = ACTION_PATTERN.search(response_text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            # Validate action_type
            if parsed.get("action_type") in VALID_ACTIONS:
                return parsed
        except json.JSONDecodeError:
            pass
    return {"action_type": "CHECK_METRICS", "target_service": "api_gateway"}


def format_observation(step: int, observation, history: List[str]) -> str:
    obs = observation.model_dump()
    # Format service statuses as a compact table
    status_lines = []
    for svc in obs.get("service_statuses", []):
        health = "✅" if svc["healthy"] else "❌"
        status_lines.append(
            f"  {health} {svc['name']:15s} latency={svc['latency_ms']:.0f}ms "
            f"err={svc['error_rate']:.2%} cpu={svc['cpu_pct']:.0f}% mem={svc['memory_pct']:.0f}%"
        )

    alert_lines = [
        f"  [{a['severity'].upper()}] {a['service']}: {a['message'][:80]}"
        for a in obs.get("alerts", [])
    ]

    log_lines = obs.get("logs", [])[:6]

    timeline = obs.get("timeline", [])[-5:]

    return textwrap.dedent(f"""
        === STEP {step} / {obs['max_steps']} | Incident: {obs['incident_id']} ===
        Resolved services: {obs.get('resolved_services', [])}
        Running reward: {obs.get('total_reward', 0):.2f}

        --- ALERTS ---
        {chr(10).join(alert_lines) or "  (none)"}

        --- SERVICE STATUS ---
        {chr(10).join(status_lines)}

        --- RECENT LOGS (last 6) ---
        {chr(10).join(log_lines) or "  (none)"}

        --- INCIDENT TIMELINE ---
        {chr(10).join(timeline) or "  (none)"}

        --- YOUR RECENT ACTIONS ---
        {chr(10).join(history[-4:]) or "  (none)"}

        What is your next action?
    """).strip()


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_task(client: OpenAI, env: IncidentCommanderEnv, task_id: str) -> float:
    print(f"\n{'='*65}")
    print(f"  TASK: {task_id}")
    print(f"{'='*65}")

    history: List[str] = []
    result = env.reset(task_id=task_id, seed=42)
    observation = result.observation
    done = False
    step = 0
    episode_score = 0.0

    print(f"  Incident ID : {result.incident_id}")
    print(f"  Max steps   : {observation.max_steps}")

    while not done:
        step += 1
        user_prompt = format_observation(step, observation, history)

        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=200,
                stream=False,
            )
            response_text = completion.choices[0].message.content or ""
        except Exception as exc:
            print(f"  ⚠️  Model error ({exc}) — using CHECK_METRICS fallback.")
            response_text = '{"action_type": "CHECK_METRICS", "target_service": "api_gateway"}'

        action_dict = parse_action(response_text)
        try:
            action = IncidentAction(**action_dict)
        except Exception:
            action = IncidentAction(action_type=ActionType.CHECK_METRICS, target_service="api_gateway")

        target_str = action.target_service or ""
        cause_str = f" cause={action.root_cause_id}" if action.root_cause_id else ""
        print(f"  Step {step:02d}: {action.action_type.value} {target_str}{cause_str}", end="")

        step_result = env.step(action)
        observation = step_result.observation
        reward = step_result.reward
        done = step_result.done

        print(f" → reward {reward:+.2f} {'✅ DONE' if done else ''}")
        history.append(
            f"Step {step}: {action.action_type.value} {target_str}{cause_str} → {reward:+.2f}"
        )

    episode_score = env.grade()
    state = env.state()
    print(f"\n  Final Score      : {episode_score:.4f}")
    print(f"  Correct Diagnosis: {'Yes' if state.correct_diagnosis else 'No'}")
    print(f"  Services Restored: {len(state.resolved_services)}/{len(state.affected_services)}")
    print(f"  Steps Used       : {state.step}/{state.max_steps}")
    return episode_score


def main() -> None:
    if not API_KEY:
        print("⚠️  WARNING: HF_TOKEN / API_KEY not set. Requests will likely fail.")

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY or "dummy")
    env = IncidentCommanderEnv()

    scores = {}
    for task_id in TASKS:
        try:
            scores[task_id] = run_task(client, env, task_id)
        except Exception as exc:
            print(f"  ❌ Task {task_id} failed: {exc}")
            scores[task_id] = 0.0

    print(f"\n{'='*65}")
    print("  FINAL RESULTS")
    print(f"{'='*65}")
    for task_id, score in scores.items():
        bar = "█" * int(score * 20)
        print(f"  {task_id:30s} {score:.4f}  |{bar:<20}|")
    overall = sum(scores.values()) / len(scores)
    print(f"\n  Overall Average  : {overall:.4f}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()

"""
inference.py — IncidentCommander baseline agent using OpenAI client.

Mandatory environment variables:
  API_BASE_URL   LLM API endpoint (default: https://router.huggingface.co/v1)
  MODEL_NAME     Model identifier  (default: meta-llama/Llama-3.3-70B-Instruct)
  HF_TOKEN       Hugging Face / API key

Mandatory stdout log format (one line each):
  [START] task=<task_id> seed=<seed>
  [STEP]  step=<n> action=<ACTION_TYPE> target=<service|None> reward=<float> done=<bool>
  [END]   task=<task_id> score=<float> steps=<n>

Run:
  python inference.py [--env-url URL]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
from typing import Dict, List

from openai import OpenAI

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE_URL: str = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY: str = (
    os.getenv("HF_TOKEN")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("API_KEY")
    or ""
)
MODEL_NAME: str = os.getenv("MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")

# The 3 required tasks (easy → medium → hard) + optional 4th
TASKS: List[str] = [
    "single_service_crash",   # easy
    "cascading_failure",      # medium
    "bad_deployment",         # medium-hard
    "silent_degradation",     # hard
]

VALID_ACTIONS: List[str] = [
    "CHECK_LOGS", "CHECK_METRICS", "TRACE_REQUEST",
    "RESTART_SERVICE", "SCALE_UP", "ROLLBACK",
    "FAILOVER_DB", "CLEAR_CACHE", "DIAGNOSE", "ESCALATE",
]

ACTION_PATTERN = re.compile(r'\{[^{}]*\}', re.DOTALL)

SEED = 42

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = textwrap.dedent("""
    You are an expert Site Reliability Engineer (SRE) managing a live production incident
    in an 8-service microservices system. Your goal is to identify the root cause and
    restore all affected services as quickly as possible.

    === SERVICES ===
    api_gateway, auth, database, cache, queue, payment, notification, cdn

    === DEPENDENCY GRAPH ===
    api_gateway → auth, cache, cdn
    auth        → database, cache
    payment     → database, cache, queue
    queue       → database
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
    ESCALATE          – Escalate to senior team (last resort — heavy penalty)

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
# Environment wrappers (local or remote)
# ---------------------------------------------------------------------------

class LocalEnvWrapper:
    """Wraps the local IncidentCommanderEnv to return plain dicts."""

    def __init__(self):
        # Import here so the script also works when used against a remote env
        from incident_commander_env import IncidentCommanderEnv
        self._env = IncidentCommanderEnv()

    def reset(self, task_id: str, seed: int) -> Dict:
        result = self._env.reset(task_id=task_id, seed=seed)
        return result.model_dump()

    def step(self, action_dict: Dict) -> Dict:
        from incident_commander_env import IncidentAction
        action = IncidentAction(**action_dict)
        result = self._env.step(action)
        return result.model_dump()

    def state(self) -> Dict:
        return self._env.state().model_dump()

    def grade(self) -> Dict:
        s = self._env.state()
        score = self._env.grade()
        return {"score": score, "task_id": s.task_id, "step": s.step}


class RemoteEnvWrapper:
    """Wraps the HTTP client to return plain dicts — same interface as LocalEnvWrapper."""

    def __init__(self, base_url: str):
        import requests
        self._url = base_url.rstrip("/")
        self._session = requests.Session()

    def reset(self, task_id: str, seed: int) -> Dict:
        r = self._session.post(f"{self._url}/reset", json={"task_id": task_id, "seed": seed})
        r.raise_for_status()
        return r.json()

    def step(self, action_dict: Dict) -> Dict:
        r = self._session.post(f"{self._url}/step", json=action_dict)
        r.raise_for_status()
        return r.json()

    def state(self) -> Dict:
        r = self._session.get(f"{self._url}/state")
        r.raise_for_status()
        return r.json()

    def grade(self) -> Dict:
        r = self._session.get(f"{self._url}/grade")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_action(response_text: str) -> Dict:
    """Extract the first valid JSON action from the model response."""
    match = ACTION_PATTERN.search(response_text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if parsed.get("action_type") in VALID_ACTIONS:
                return parsed
        except json.JSONDecodeError:
            pass
    # Fallback: safe investigatory action
    return {"action_type": "CHECK_METRICS", "target_service": "api_gateway"}


def format_observation(step_n: int, obs: Dict, history: List[str]) -> str:
    """Format environment observation into a concise prompt for the LLM."""
    status_lines = []
    for svc in obs.get("service_statuses", []):
        health = "OK " if svc["healthy"] else "ERR"
        status_lines.append(
            f"  [{health}] {svc['name']:15s} "
            f"lat={svc['latency_ms']:.0f}ms err={svc['error_rate']:.1%} "
            f"cpu={svc['cpu_pct']:.0f}% mem={svc['memory_pct']:.0f}%"
        )

    alert_lines = [
        f"  [{a['severity'].upper()}] {a['service']}: {a['message'][:80]}"
        for a in obs.get("alerts", [])
    ]

    log_lines = obs.get("logs", [])[:6]
    timeline = obs.get("timeline", [])[-5:]

    return textwrap.dedent(f"""
        === STEP {step_n}/{obs['max_steps']} | Incident: {obs['incident_id']} ===
        Resolved: {obs.get('resolved_services', [])} | Running reward: {obs.get('total_reward', 0):.2f}

        --- ALERTS ---
        {chr(10).join(alert_lines) or '  (none)'}

        --- SERVICE STATUS ---
        {chr(10).join(status_lines)}

        --- RECENT LOGS (last 6) ---
        {chr(10).join(log_lines) or '  (none)'}

        --- INCIDENT TIMELINE ---
        {chr(10).join(timeline) or '  (none)'}

        --- YOUR RECENT ACTIONS ---
        {chr(10).join(history[-4:]) or '  (none)'}

        What is your next action?
    """).strip()


# ---------------------------------------------------------------------------
# Main agent loop — per task
# ---------------------------------------------------------------------------

def run_task(client: OpenAI, env, task_id: str, seed: int = SEED) -> float:
    """
    Run one full episode and return the final score.

    Emits mandatory structured log lines:
      [START] task=<task_id> seed=<seed>
      [STEP]  step=<n> action=<type> target=<svc|None> reward=<r> done=<bool>
      [END]   task=<task_id> score=<score> steps=<n>
    """
    # ---- [START] ----
    print(f"[START] task={task_id} seed={seed}", flush=True)

    history: List[str] = []
    reset_res = env.reset(task_id=task_id, seed=seed)

    # Observation lives under "observation" key in ResetResult dict
    observation = reset_res.get("observation", reset_res)

    done = False
    step_n = 0

    while not done:
        step_n += 1
        user_prompt = format_observation(step_n, observation, history)

        try:
            completion = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=200,
                stream=False,
            )
            response_text = completion.choices[0].message.content or ""
        except Exception as exc:
            # Graceful degradation: log and use fallback action
            print(f"  [WARN] LLM error: {exc} — using fallback action", file=sys.stderr, flush=True)
            response_text = '{"action_type": "CHECK_METRICS", "target_service": "api_gateway"}'

        action_dict = parse_action(response_text)
        action_type  = action_dict.get("action_type", "CHECK_METRICS")
        target       = action_dict.get("target_service", None)

        step_result  = env.step(action_dict)
        observation  = step_result["observation"]
        reward       = step_result["reward"]
        done         = step_result["done"]

        # ---- [STEP] ----
        print(
            f"[STEP] step={step_n} action={action_type} target={target} "
            f"reward={reward:.4f} done={done}",
            flush=True,
        )

        history.append(f"Step {step_n}: {action_type} → {reward:+.2f}")

    grade_res = env.grade()
    score = grade_res["score"]
    steps_used = grade_res.get("step", step_n)

    # ---- [END] ----
    print(f"[END] task={task_id} score={score:.4f} steps={steps_used}", flush=True)

    return score


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="IncidentCommander baseline inference script")
    parser.add_argument(
        "--env-url",
        type=str,
        default=None,
        help="URL of a running remote environment (e.g. HF Space). Omit for local mode.",
    )
    args = parser.parse_args()

    if not API_KEY:
        print(
            "[WARN] HF_TOKEN / OPENAI_API_KEY not set — LLM calls will likely fail.",
            file=sys.stderr,
            flush=True,
        )

    openai_client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY or "dummy")

    if args.env_url:
        print(f"[INFO] Connecting to remote environment: {args.env_url}", flush=True)
        env = RemoteEnvWrapper(args.env_url)
    else:
        print("[INFO] Using local environment.", flush=True)
        env = LocalEnvWrapper()

    scores: Dict[str, float] = {}

    for task_id in TASKS:
        try:
            scores[task_id] = run_task(openai_client, env, task_id, seed=SEED)
        except Exception as exc:
            import traceback
            print(f"[ERROR] Task {task_id} failed: {exc}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            # Emit [END] with score=0 so evaluation can parse it
            print(f"[END] task={task_id} score=0.0000 steps=0", flush=True)
            scores[task_id] = 0.0

    # Summary
    print("\n" + "=" * 65, flush=True)
    print("FINAL BASELINE SCORES", flush=True)
    print("=" * 65, flush=True)
    for task_id, score in scores.items():
        bar = "#" * int(score * 20)
        print(f"  {task_id:30s} {score:.4f}  |{bar:<20}|", flush=True)
    overall = sum(scores.values()) / max(1, len(scores))
    print(f"\n  Overall Average : {overall:.4f}", flush=True)
    print("=" * 65 + "\n", flush=True)


if __name__ == "__main__":
    main()

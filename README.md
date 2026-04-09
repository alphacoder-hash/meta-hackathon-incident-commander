---
title: IncidentCommander
emoji: 🚨
colorFrom: blue
colorTo: red
sdk: docker
pinned: false
app_port: 7860
base_path: /ui
tags:
  - openenv
  - devops
  - sre
  - incident-response
  - evaluation
  - reinforcement-learning
---

# IncidentCommander 🚨

> A production-grade **OpenEnv** environment where AI agents act as Site Reliability Engineers (SREs), diagnosing and resolving live infrastructure incidents across an 8-service microservices architecture.

[![OpenEnv](https://img.shields.io/badge/OpenEnv-v1-blue)](https://github.com/meta-pytorch/openenv)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-50%20passing-success)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🎯 What Is This?

**IncidentCommander** simulates the real-world task of incident response — a core function in every engineering organization. On-call SREs spend hours each week triaging production alerts, reading system logs, tracing cascading failures, and applying targeted fixes to restore service health.

This environment captures all of that complexity:
- **Dynamic alerts** with realistic stack traces, metrics anomalies, and red herrings
- **Cascading failures** that propagate through a dependency graph
- **Multiple remediation paths** (some correct, some harmful)
- **Meaningful partial rewards** — the agent is rewarded for each correct step, not just the final resolution
- **Chaos injection** in the hardest scenario to test resilience under uncertainty

This is designed to **train and evaluate LLM agents on reasoning-under-pressure** — a skill that generalizes directly to real operations roles.

---

## 🏗️ System Architecture

```
api_gateway ──→ auth ──→ database (leaf)
            ├──→ cache   (leaf)
            └──→ cdn     (leaf)

payment ────→ database
        ├──→ cache
        └──→ queue ──→ database

notification ──→ queue
```

**8 services**: `api_gateway`, `auth`, `database`, `cache`, `queue`, `payment`, `notification`, `cdn`

The simulator propagates failures through this graph in topological order each step. A leaf service failure cascades upward to all dependents, with degradation proportional to the fraction of failed dependencies.

---

## 🎮 Task Scenarios

| # | Task ID | Difficulty | Root Cause | Max Steps |
|---|---------|-----------|------------|-----------|
| 1 | `single_service_crash` | 🟢 Easy | `cache_oom` — Cache OOM crash | 10 |
| 2 | `cascading_failure` | 🟡 Medium | `database_overload` — DB overload cascading | 15 |
| 3 | `bad_deployment` | 🟠 Medium-Hard | `payment_bad_deploy` — Crash-looping deployment | 15 |
| 4 | `silent_degradation` | 🔴 Hard + Chaos | `payment_memory_leak` — Slow memory leak | 20 |

### Task 1: Single Service Crash (Easy)
The Redis cache has run out of memory (OOM) and crashed. The `api_gateway` and `auth` services are reporting elevated latency. One red-herring alert about CDN cache misses is present. A competent agent should `CHECK_LOGS cache` → `DIAGNOSE cache_oom` → `CLEAR_CACHE` in 3 steps.

### Task 2: Cascading Failure (Medium)
The database is CPU-saturated. The failure cascades to `cache`, `auth`, and `api_gateway`. Alerts span 5 services. The agent must trace back to the database as the root and use `FAILOVER_DB` to restore service. Red herring: a payment AB-test anomaly.

### Task 3: Bad Deployment (Medium-Hard)
`payment` v2.4.1 introduced a null pointer panic at startup. The service is crash-looping (8 restarts in 3 min). `queue` is backing up, `notification` is delayed. `RESTART_SERVICE payment` won't help — only `ROLLBACK payment` works. Two red herrings: DB replica lag and CDN cert renewal.

### Task 4: Silent Degradation (Hard)
`payment` has a slow goroutine memory leak. No immediate crash — latency creeps up over 10+ steps as heap grows from 52% → 73% → 99%. Chaos monkey injects random latency spikes on non-critical services. Three red-herring alerts distract from the real pattern. The agent must `DIAGNOSE payment_memory_leak` (based on memory trend, not a crash) and `RESTART_SERVICE payment` to flush the heap temporarily.

---

## 🛠️ Action Space

The agent submits a JSON action each step:

```json
{"action_type": "DIAGNOSE", "target_service": "cache", "root_cause_id": "cache_oom"}
```

| Action | Parameters | Effect |
|--------|-----------|--------|
| `CHECK_LOGS` | `target_service` | Inspect logs of a service; +0.5 if failing service, −0.2 if healthy |
| `CHECK_METRICS` | `target_service` | View CPU/mem/latency/error metrics; same reward shape as CHECK_LOGS |
| `TRACE_REQUEST` | `target_service` | Trace a request through a service for error patterns |
| `RESTART_SERVICE` | `target_service` | Restart a service; fixes OOM, not bad deploys. −1.0 if healthy |
| `SCALE_UP` | `target_service` | Add capacity; partially alleviates database overload |
| `ROLLBACK` | `target_service` | Rollback to previous deployment; only fixes `payment_bad_deploy` |
| `FAILOVER_DB` | — | Switch to DB replica; fixes `database_overload` only |
| `CLEAR_CACHE` | — | Flush cache; fixes `cache_oom` only |
| `DIAGNOSE` | `root_cause_id` | Declare root cause; +3.0 if correct, −1.5 if wrong, −0.5 if red-herring |
| `ESCALATE` | — | Pass to senior team; ends episode with −2.0 penalty |

---

## 👁️ Observation Space

Each step returns an `IncidentObservation`:

| Field | Type | Description |
|-------|------|-------------|
| `incident_id` | `str` | Unique episode identifier (`INC-XXXX`) |
| `task_id` | `str` | Active scenario name |
| `step` | `int` | Current step number |
| `max_steps` | `int` | Episode budget |
| `alerts` | `List[Alert]` | Active monitoring alerts (some are red herrings) |
| `service_statuses` | `List[ServiceStatus]` | Per-service metrics: `healthy`, `latency_ms`, `error_rate`, `cpu_pct`, `memory_pct`, `restarts` |
| `logs` | `List[str]` | Up to 20 recent log lines (realistic syslog format) |
| `timeline` | `List[str]` | Last 10 agent actions and their outcomes |
| `resolved_services` | `List[str]` | Services restored during this episode |
| `total_reward` | `float` | Cumulative reward so far |

---

## 🏆 Grading / Reward

### Per-Step Reward Signals
| Signal | Value |
|--------|-------|
| Correct diagnosis (first time) | +3.0 |
| Service restored to healthy | +2.0 |
| All services resolved (bonus) | +5.0 |
| Chaos event survived | +2.0 |
| Useful investigation (failing service) | +0.5 |
| Partial fix action worked | +0.5 |
| Wasted investigation (healthy service) | −0.2 |
| Wrong diagnosis | −1.5 |
| Red herring diagnosis | −0.5 |
| Unnecessary restart (healthy service) | −1.0 |
| Escalate | −2.0 |
| Customer impact (per failing service/step) | −0.3 |
| Step cost | −0.1 |

### Final Episode Score (0.0 – 1.0)
```
score = 0.30 × diagnosis_correct
      + 0.30 × (services_restored / services_affected)
      + 0.20 × (1 - steps_used / max_steps)
      + 0.15 × avg_service_uptime
      + 0.05 × (1 - red_herring_penalty)
```

---

## 📊 Baseline Scores

Baseline agent: `meta-llama/Llama-3.3-70B-Instruct` via HuggingFace Inference Router

| Task | Difficulty | Score |
|------|-----------|-------|
| `single_service_crash` | Easy | ~0.65–0.75 |
| `cascading_failure` | Medium | ~0.45–0.55 |
| `bad_deployment` | Medium-Hard | ~0.40–0.55 |
| `silent_degradation` | Hard | ~0.15–0.35 |
| **Overall Average** | — | **~0.40–0.55** |

Run the baseline yourself:
```bash
python inference.py
```

---

## 🚀 Quick Start

### Local (Python)
```bash
git clone https://huggingface.co/spaces/<your-space>/IncidentCommander
cd IncidentCommander

pip install -r requirements.txt

# Run the server
uvicorn server.app:app --host 0.0.0.0 --port 7860
# Open http://localhost:7860/ui for the interactive dashboard
```

### Local (Docker)
```bash
docker build -t incident-commander .
docker run -p 7860:7860 \
  -e HF_TOKEN=<your-token> \
  -e MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct \
  -e API_BASE_URL=https://router.huggingface.co/v1 \
  incident-commander
```

### Run the Baseline Inference Script
```bash
export HF_TOKEN=hf_xxx
export MODEL_NAME=meta-llama/Llama-3.3-70B-Instruct
export API_BASE_URL=https://router.huggingface.co/v1

# Local environment
python inference.py

# Against a deployed HF Space
python inference.py --env-url https://<your-space>.hf.space
```

### Python Client API
```python
from incident_commander_env import IncidentCommanderEnv, IncidentAction, ActionType

env = IncidentCommanderEnv()

# Start an episode
result = env.reset(task_id="cascading_failure", seed=42)
obs = result.observation

print(f"Incident: {obs.incident_id}")
print(f"Alerts: {[a.message for a in obs.alerts]}")

# Take actions
done = False
while not done:
    # Your agent logic here
    action = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="database")
    step_result = env.step(action)
    obs = step_result.observation
    done = step_result.done

# Get final grade
score = env.grade()
print(f"Final score: {score:.4f}")  # 0.0 – 1.0
```

### HTTP API (against running server)
```bash
# Reset
curl -X POST http://localhost:7860/reset \
  -H 'Content-Type: application/json' \
  -d '{"task_id": "single_service_crash", "seed": 42}'

# Step
curl -X POST http://localhost:7860/step \
  -H 'Content-Type: application/json' \
  -d '{"action_type": "CHECK_LOGS", "target_service": "cache"}'

# Grade
curl http://localhost:7860/grade

# State (ground truth)
curl http://localhost:7860/state
```

---

## 🧪 Running Tests
```bash
pip install -r requirements.txt
python -m pytest tests/ -v
# Expected: 50 passed
```

---

## 🌳 Project Structure
```
incident-commander/
├── environment.py          # Core IncidentCommanderEnv class
├── models.py               # Pydantic types: Action, Observation, State, Reward
├── scenarios.py            # 4 task scenarios with alert templates
├── simulator.py            # Tick-based infrastructure state machine
├── services.py             # Service specs and dependency graph
├── grader.py               # Deterministic grader (0.0–1.0) + reward signals
├── log_generator.py        # Realistic log line generation per scenario
├── inference.py            # Baseline LLM agent loop (mandatory log format)
├── client.py               # HTTP client wrapper for remote environments
├── openenv.yaml            # OpenEnv manifest
├── Dockerfile              # Self-contained Docker build
├── requirements.txt        # Python dependencies
├── server/
│   ├── app.py              # Standalone FastAPI server (all endpoints)
│   └── gradio_ui.py        # Interactive Gradio dashboard at /ui
├── incident_commander_env/
│   └── __init__.py         # Python package export
└── tests/
    ├── test_environment.py  # 18 environment lifecycle tests
    ├── test_grader.py       # 11 grader and reward signal tests
    ├── test_models.py       # 11 Pydantic model tests
    └── test_server.py       # 9 FastAPI endpoint tests
```

---

## 📜 License
MIT

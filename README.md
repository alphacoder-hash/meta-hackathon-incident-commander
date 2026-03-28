---
title: IncidentCommander
colorFrom: blue
colorTo: red
sdk: docker
app_port: 7860
license: mit
---

# IncidentCommander

> **India's Biggest MEGA AI Hackathon**  
> *Build at the Bleeding Edge of AI*  
> Built on Meta's OpenEnv. The foundation for next-gen RL environments used by leading AI labs.  
> **Sponsored by Meta, Hugging Face, & PyTorch**

An AI-powered DevOps incident response environment where an autonomous agent must triage alerts, parse logs, trace service dependencies, diagnose root causes, and restore services across an 8-service microservices architecture.

---

## Meta Hackathon Submission Validation

This environment has been specifically engineered to pass all 3 phases of the Meta Hackathon evaluation:

* **Phase 1 (Automated Validation):** 
  * **OpenEnv Spec Compliance**: Uses `openenv.yaml` schema declaring Action spaces, Service states, and Observations perfectly.
  * **Tested Docker Deploy**: FastAPI `server/app.py` passes all health checks on Port 7860.
  * **4 Graded Scenarios**: Distinct root-causes (`single_service_crash`, `cascading_failure`, `bad_deployment`, `silent_degradation`).
* **Phase 2 (Agentic Evaluation):**
  * **Baseline Inclusion**: Includes a working `inference.py` script that hits Hugging Face Inference API. 
  * **Score Variance Assured**: Generates dynamic scores (0.0 to 1.0) based on exactly *when* an agent discovers the root cause, what services recover, and how many red herring penalties are triggered.
* **Phase 3 (Human Review):**
  * **Real-world Utility**: Simulates authentic microservices telemetry (Kafka Queue metrics, API Gateway error rates, SLA thresholds).

[![HF Space](https://img.shields.io/badge/🤗-HuggingFace%20Space-blue)](https://huggingface.co/spaces)
[![OpenEnv](https://img.shields.io/badge/OpenEnv-1.0.0-green)](https://openenv.ai)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://python.org)

---

## Overview

| Feature | Detail |
|---|---|
| **Tasks** | 4 (Easy → Hard) |
| **Services** | 8 microservices |
| **Actions** | 10 |
| **Reward Signals** | 12 |
| **Novel Mechanics** | Cascading failures, red herrings, memory leaks, chaos injection |

---

## Architecture

```
api_gateway → auth, cache, cdn
auth        → database, cache
payment     → database, cache, queue
queue       → database
notification → queue
```

---

## Tasks

| # | Task | Difficulty | Root Cause | Max Steps |
|---|---|---|---|---|
| 1 | `single_service_crash` | Easy | Cache OOM | 10 |
| 2 | `cascading_failure` | Medium | Database overload | 15 |
| 3 | `bad_deployment` | Medium-Hard | Payment bad deploy | 15 |
| 4 | `silent_degradation` | Hard | Payment memory leak | 20 |

---

## Actions

| Action | Description |
|---|---|
| `CHECK_LOGS` | Inspect service logs |
| `CHECK_METRICS` | View CPU/memory/latency/error_rate |
| `TRACE_REQUEST` | Trace a request through a service |
| `RESTART_SERVICE` | Restart a service |
| `SCALE_UP` | Scale a service up |
| `ROLLBACK` | Rollback a deployment |
| `FAILOVER_DB` | Failover to DB replica |
| `CLEAR_CACHE` | Flush the cache |
| `DIAGNOSE` | Declare the root cause |
| `ESCALATE` | Escalate to senior team |

---

## Scoring

```
score = 0.30 × diagnosis_correct
      + 0.30 × services_restored
      + 0.20 × time_efficiency
      + 0.15 × avg_uptime
      + 0.05 × (1 − red_herring_penalty)
```

---

## Quick Start

### Install

```bash
pip install -r requirements.txt
```

### Run as Python module

```python
from incident_commander_env import IncidentCommanderEnv, IncidentAction, ActionType

env = IncidentCommanderEnv()
result = env.reset(task_id="single_service_crash", seed=42)
obs = result.observation

print(f"Incident: {obs.incident_id}")
print(f"Alerts: {len(obs.alerts)}")

# Take an action
action = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache")
step_result = env.step(action)
print(f"Reward: {step_result.reward}")

# Get final score
score = env.grade()
print(f"Score: {score:.4f}")
```

### Run the API server

```bash
uvicorn server.app:app --host 0.0.0.0 --port 7860
```

### Run inference (requires HF token + model)

```bash
export HF_TOKEN="hf_..."
export MODEL_NAME="meta-llama/Llama-3.3-70B-Instruct"
python inference.py
```

### Run tests

```bash
pytest tests/ -v
```

### Docker

```bash
docker build -t incident-commander .
docker run -p 7860:7860 incident-commander
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/` | Environment info |
| `POST` | `/reset` | Start new episode |
| `POST` | `/step` | Submit action |
| `GET` | `/state` | Full internal state |
| `GET` | `/grade` | Episode score |
| `GET` | `/docs` | Swagger UI |

### POST /reset
```json
{ "task_id": "cascading_failure", "seed": 42 }
```

### POST /step
```json
{ "action_type": "CHECK_LOGS", "target_service": "database" }
```

### GET /grade
```json
{ "score": 0.72, "task_id": "cascading_failure", "steps_taken": 8, "correct_diagnosis": true, "services_restored": 4 }
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `API_BASE_URL` | `https://router.huggingface.co/v1` | OpenAI-compatible API base |
| `HF_TOKEN` | *(required)* | Hugging Face token |
| `MODEL_NAME` | `meta-llama/Llama-3.3-70B-Instruct` | Model to use |

---

## Project Structure

```
Meta_Hackathon/
├── openenv.yaml                    # OpenEnv spec
├── requirements.txt
├── Dockerfile
├── README.md
├── inference.py                    # Agent loop
├── incident_commander_env/
│   ├── __init__.py
│   ├── models.py                   # Pydantic types
│   ├── services.py                 # Service specs & dependency graph
│   ├── scenarios.py                # 4 task definitions
│   ├── log_generator.py            # Realistic log generation
│   ├── simulator.py                # Infrastructure engine
│   ├── grader.py                   # Deterministic scoring
│   └── environment.py              # Core env: reset/step/state/grade
├── server/
│   └── app.py                      # FastAPI server
└── tests/
    ├── test_models.py
    ├── test_environment.py
    └── test_grader.py
```

---

## License

MIT

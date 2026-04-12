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
---

# IncidentCommander 🚨

**IncidentCommander** is a production-grade **OpenEnv** environment designed to evaluate AI agents in the role of a Site Reliability Engineer (SRE). Agents must triage complex production incidents across an 8-service microservices architecture by analyzing live incident reports and providing prioritized remediation plans.

---

## 🎯 The Challenge

In this environment, "episodes" consist of high-fidelity incident scenarios. The agent receives a comprehensive **Incident Report** containing:
- **Service Statuses**: Latency, error rates, and health metrics for the 8-service graph.
- **Active Alerts**: Real-time signals including critical outages and misleading "red herring" monitors.
- **Log Snippets**: Recent logs from affected services (and red herrings) to aid root-cause identification.

The agent succeeds by providing a **free-text analysis** that correctly identifies the root cause, dismisses false signals, and outlines a prioritized recovery plan.

---

## 🎮 Scenarios (Tasks)

| Difficulty | Task ID | Description |
| :--- | :--- | :--- |
| 🟢 **Easy** | `single_service_crash` | Identify a single failing service from clear error logs. |
| 🟡 **Medium** | `cascading_failure` | Identify a root cause while navigating misleading "red herring" signals. |
| 🟠 **Medium-Hard** | `bad_deployment` | Diagnose a crash-looping deployment and recommend a rollback. |
| 🔴 **Hard** | `silent_degradation` | Diagnose a slow memory leak under chaos injection conditions. |

---

## 🏗️ Architecture

The environment simulates an 8-service dependency graph:
`api_gateway ──→ auth ──→ database`, `payment ──→ cache`, etc. 

Failures propagate topographically, requiring agents to reason about causal chains to find the true source of the "Outage".

---

## 🚀 Quick Start

### 1. Run the Dashboard (Interactive)
The environment includes a premium SRE Dashboard for manual triage and testing.
```bash
# Using Python
pip install -r requirements.txt
uvicorn server.app:app --host 0.0.0.0 --port 7860

# Navigate to http://localhost:7860/ui
```

### 2. Docker Deployment
```bash
docker build -t incident-commander .
docker run -p 7860:7860 incident-commander
```

### 3. API Usage (OpenEnv Client)
```python
import httpx

# Reset the environment
resp = httpx.post("http://localhost:7860/reset", json={"task_id": "cascading_failure"})
obs = resp.json()["observation"]
print(obs["incident_report"])

# Submit analysis
action = {"response": "The database is overloaded due to a slow query in the auth service. RECOMMENDATION: Scale up database."}
resp = httpx.post("http://localhost:7860/step", json=action)
print(f"Score: {resp.json()['reward']}")
```

---

## 🌳 Project Structure
```
incident-commander/
├── openenv.yaml        # OpenEnv manifest
├── models.py           # Core Pydantic types (Action/Observation)
├── Dockerfile          # Multi-stage build for HF Spaces
├── server/
│   ├── app.py          # FastAPI server with Gradio UI mount
│   ├── environment.py  # OpenEnv environment implementation
│   ├── graders.py      # Tiered keyword-based grading logic
│   └── gradio_ui.py    # Premium SRE Dashboard
└── requirements.txt    # Python dependencies
```

---

## 📜 License
MIT

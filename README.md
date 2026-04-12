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

**IncidentCommander** is a production-grade **OpenEnv** environment designed to evaluate AI agents in the role of a Site Reliability Engineer (SRE). Agents must triage complex production incidents across an 8-service microservices architecture by analyzing live incident reports and providing prioritized remediation plans. [![License: MIT](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🔗 Live Demonstration

- **Interactive Dashboard**: [https://vaibhav0714-incidentcommander.hf.space/](https://vaibhav0714-incidentcommander.hf.space/)
- **Hugging Face Space**: [https://huggingface.co/spaces/vaibhav0714/IncidentCommander](https://huggingface.co/spaces/vaibhav0714/IncidentCommander)
- **GitHub Repository**: [https://github.com/alphacoder-hash/meta-hackathon-incident-commander](https://github.com/alphacoder-hash/meta-hackathon-incident-commander)

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

### Local (Python)
```bash
git clone https://github.com/alphacoder-hash/meta-hackathon-incident-commander.git
cd incident-commander

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
  -e MODEL_NAME=Qwen/Qwen2.5-72B-Instruct \
  -e API_BASE_URL=https://router.huggingface.co/v1 \
  incident-commander
```

### Run the Baseline Inference Script
```bash
export HF_TOKEN=hf_xxx
export MODEL_NAME=Qwen/Qwen2.5-72B-Instruct
export API_BASE_URL=https://router.huggingface.co/v1

# Local environment
python inference.py

# Against a deployed HF Space
python inference.py --env-url https://vaibhav0714-incidentcommander.hf.space
```

### API Usage (OpenEnv Client)
```python
import httpx

# Reset the environment
resp = httpx.post("https://vaibhav0714-incidentcommander.hf.space/reset", json={"task_id": "cascading_failure"})
obs = resp.json()["observation"]
print(obs["incident_report"])

# Submit analysis
action = {"response": "The database is overloaded. RECOMMENDATION: Scale up database."}
resp = httpx.post("https://vaibhav0714-incidentcommander.hf.space/step", json=action)
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

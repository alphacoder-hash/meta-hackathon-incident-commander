"""
server/app.py — Standalone FastAPI server for IncidentCommander OpenEnv.

Endpoints:
  GET  /           → redirect to /ui
  GET  /health     → {"status": "ok"}
  GET  /info       → environment metadata
  POST /reset      → ResetResult
  POST /step       → StepResult
  GET  /state      → IncidentState
  GET  /grade      → {"score": float, "task_id": str, "step": int}
  GET  /ui         → Gradio interactive dashboard
"""
import sys
import os

# Ensure root directory is on sys.path
_server_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_server_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import Optional
import gradio as gr

from models import IncidentAction, IncidentObservation, ResetResult, StepResult, IncidentState
from environment import IncidentCommanderEnv
from server.gradio_ui import build_ui


# ---------------------------------------------------------------------------
# Persistent environment state
# ---------------------------------------------------------------------------

_env = IncidentCommanderEnv()
_last_task_id: str = "single_service_crash"


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    task_id: str = "single_service_crash"
    seed: int = 42
    episode_id: Optional[str] = None


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IncidentCommander OpenEnv",
    description=(
        "A DevOps SRE incident response environment where AI agents triage "
        "production alerts and restore service health across a microservices graph."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/ui")


@app.get("/health")
def health():
    """Health check — returns 200 when the server is up."""
    return {"status": "ok", "environment": "incident_commander", "version": "1.0.0"}


@app.get("/info")
def info():
    """Return environment metadata (tasks, actions, observation fields)."""
    return {
        "name": "IncidentCommander",
        "version": "1.0.0",
        "description": (
            "DevOps SRE incident response: triage alerts, trace cascading failures, "
            "restore services across an 8-node microservices graph."
        ),
        "tasks": [
            {"id": "single_service_crash", "difficulty": "easy",        "max_steps": 10},
            {"id": "cascading_failure",    "difficulty": "medium",      "max_steps": 15},
            {"id": "bad_deployment",       "difficulty": "medium-hard", "max_steps": 15},
            {"id": "silent_degradation",   "difficulty": "hard",        "max_steps": 20},
        ],
        "actions": [
            "CHECK_LOGS", "CHECK_METRICS", "TRACE_REQUEST",
            "RESTART_SERVICE", "SCALE_UP", "ROLLBACK",
            "FAILOVER_DB", "CLEAR_CACHE", "DIAGNOSE", "ESCALATE",
        ],
        "services": [
            "api_gateway", "auth", "database", "cache",
            "queue", "payment", "notification", "cdn",
        ],
        "root_causes": [
            "cache_oom", "database_overload",
            "payment_bad_deploy", "payment_memory_leak",
        ],
        "ui": "/ui",
        "docs": "/docs",
    }


@app.post("/reset", response_model=ResetResult)
def reset(req: ResetRequest = ResetRequest()):
    """
    Start a new episode.

    Returns a `ResetResult` containing the initial `IncidentObservation`.
    """
    global _last_task_id
    try:
        result = _env.reset(task_id=req.task_id, seed=req.seed, episode_id=req.episode_id)
        _last_task_id = req.task_id
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/step", response_model=StepResult)
def step(action: IncidentAction):
    """
    Submit an action and advance the environment one step.

    Returns `StepResult` with the new `IncidentObservation`, per-step `reward`, and `done` flag.
    """
    try:
        return _env.step(action)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/state", response_model=IncidentState)
def state():
    """
    Return the full internal ground-truth state (not exposed to the agent).

    Reveals `root_cause_id`, `affected_services`, diagnosis status, etc.
    """
    try:
        return _env.state()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/grade")
def grade():
    """Return the final episode score (0.0–1.0) plus metadata."""
    try:
        score = _env.grade()
        s = _env.state()
        return {
            "score": score,
            "task_id": s.task_id,
            "step": s.step,
            "max_steps": s.max_steps,
            "correct_diagnosis": s.correct_diagnosis,
            "resolved_services": s.resolved_services,
            "affected_services": s.affected_services,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Mount Gradio UI at /ui
# ---------------------------------------------------------------------------

demo = build_ui(api_url="http://localhost:7860")
app = gr.mount_gradio_app(app, demo, path="/ui")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == '__main__':
    main()

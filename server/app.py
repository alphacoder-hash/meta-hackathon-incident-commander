"""
server/app.py — FastAPI wrapper for IncidentCommander.

Exposes the environment as a REST API for Hugging Face Spaces deployment.
Runs on port 7860.

Endpoints:
  GET  /health           → 200 OK (HF health check)
  POST /reset            → ResetResult
  POST /step             → StepResult
  GET  /state            → IncidentState
  GET  /grade            → {"score": float}
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from incident_commander_env import (
    IncidentCommanderEnv,
    IncidentAction,
    IncidentState,
    ResetResult,
    StepResult,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IncidentCommander",
    description=(
        "A DevOps incident response OpenEnv environment. "
        "An AI agent triages alerts, diagnoses root causes, and restores services."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global environment instance (single-threaded, one episode at a time)
_env = IncidentCommanderEnv()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    task_id: str = "single_service_crash"
    seed: int = 42


class GradeResponse(BaseModel):
    score: float
    task_id: str
    steps_taken: int
    correct_diagnosis: bool
    services_restored: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Hugging Face health check endpoint."""
    return {"status": "ok", "environment": "incident_commander", "version": "1.0.0"}


@app.get("/")
def root() -> dict:
    """Root endpoint with environment info."""
    return {
        "name": "IncidentCommander",
        "description": "DevOps incident response OpenEnv environment",
        "tasks": ["single_service_crash", "cascading_failure", "bad_deployment", "silent_degradation"],
        "actions": [
            "CHECK_LOGS", "CHECK_METRICS", "TRACE_REQUEST", "RESTART_SERVICE",
            "SCALE_UP", "ROLLBACK", "FAILOVER_DB", "CLEAR_CACHE", "DIAGNOSE", "ESCALATE",
        ],
        "docs": "/docs",
    }


@app.post("/reset", response_model=ResetResult)
def reset(request: ResetRequest) -> ResetResult:
    """Start a new episode. Returns the initial observation."""
    valid_tasks = ["single_service_crash", "cascading_failure", "bad_deployment", "silent_degradation"]
    if request.task_id not in valid_tasks:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task_id '{request.task_id}'. Must be one of: {valid_tasks}",
        )
    return _env.reset(task_id=request.task_id, seed=request.seed)


@app.post("/step", response_model=StepResult)
def step(action: IncidentAction) -> StepResult:
    """Submit an action and get the next observation, reward, and done flag."""
    try:
        return _env.step(action)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/state", response_model=IncidentState)
def state() -> IncidentState:
    """Get the full internal state (ground truth, for evaluation)."""
    return _env.state()


@app.get("/grade", response_model=GradeResponse)
def grade() -> GradeResponse:
    """Get the final episode score (0.0–1.0)."""
    s = _env.state()
    score = _env.grade()
    return GradeResponse(
        score=score,
        task_id=s.task_id,
        steps_taken=s.step,
        correct_diagnosis=s.correct_diagnosis,
        services_restored=len(s.resolved_services),
    )

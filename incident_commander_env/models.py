"""
models.py — Pydantic data models for IncidentCommander.
All public types are re-exported from __init__.py.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Action space
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    CHECK_LOGS       = "CHECK_LOGS"
    CHECK_METRICS    = "CHECK_METRICS"
    TRACE_REQUEST    = "TRACE_REQUEST"
    RESTART_SERVICE  = "RESTART_SERVICE"
    SCALE_UP         = "SCALE_UP"
    ROLLBACK         = "ROLLBACK"
    FAILOVER_DB      = "FAILOVER_DB"
    CLEAR_CACHE      = "CLEAR_CACHE"
    DIAGNOSE         = "DIAGNOSE"
    ESCALATE         = "ESCALATE"


class IncidentAction(BaseModel):
    """Action submitted by the agent each step."""
    action_type: ActionType
    target_service: Optional[str] = None   # e.g. "database", "cache"
    root_cause_id: Optional[str] = None    # used with DIAGNOSE action

    model_config = {"extra": "ignore"}


# ---------------------------------------------------------------------------
# Observation (what the agent sees)
# ---------------------------------------------------------------------------

class Alert(BaseModel):
    id: str
    severity: str                          # "critical" | "warning" | "info"
    service: str
    message: str
    timestamp: str
    is_red_herring: bool = False           # hidden from agent; used by grader


class ServiceStatus(BaseModel):
    name: str
    healthy: bool
    latency_ms: float
    error_rate: float                      # 0.0–1.0
    cpu_pct: float                         # 0–100
    memory_pct: float                      # 0–100
    restarts: int = 0
    last_deployed: Optional[str] = None


class IncidentObservation(BaseModel):
    """Everything the agent can see at each step."""
    incident_id: str
    task_id: str
    step: int
    max_steps: int
    alerts: List[Alert]
    service_statuses: List[ServiceStatus]
    logs: List[str]                        # recent log lines (last 20)
    timeline: List[str] = Field(default_factory=list)   # action history
    resolved_services: List[str] = Field(default_factory=list)
    total_reward: float = 0.0


# ---------------------------------------------------------------------------
# Internal state (full ground truth, not seen by agent)
# ---------------------------------------------------------------------------

class IncidentState(BaseModel):
    """Full internal state snapshot returned by env.state()."""
    incident_id: str
    task_id: str
    root_cause_id: str
    step: int
    max_steps: int
    done: bool
    correct_diagnosis: bool
    affected_services: List[str]
    resolved_services: List[str]
    red_herring_ids: List[str]
    red_herring_traps_triggered: int
    unnecessary_restarts: int
    service_uptime_history: Dict[str, List[bool]]   # service → per-step uptime
    total_reward: float
    chaos_active: bool
    info: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Environment return types
# ---------------------------------------------------------------------------

class ResetResult(BaseModel):
    """Returned by env.reset()."""
    observation: IncidentObservation
    task_id: str
    incident_id: str


class StepResult(BaseModel):
    """Returned by env.step()."""
    observation: IncidentObservation
    reward: float
    done: bool
    info: Dict[str, Any] = Field(default_factory=dict)

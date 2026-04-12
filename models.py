"""
models.py — Pydantic data models for IncidentCommander.

Provides two layers:
  1. OpenEnv-compatible Action/Observation (IncidentCommanderAction /
     IncidentCommanderObservation) — used with create_app() and EnvClient.
  2. Original rich internal models (IncidentAction, IncidentObservation, etc.)
     — used by the core IncidentCommanderEnv simulation logic.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# OpenEnv-compatible Action / Observation
# (these inherit from openenv base classes so create_app() can use them)
# ---------------------------------------------------------------------------

try:
    from openenv.core.env_server.types import Action, Observation

    class IncidentCommanderAction(Action):
        """Action submitted by the agent each step (openenv-compatible)."""

        # Primary field: free-text incident analysis (used by graders directly)
        response: str = Field(
            default="",
            description=(
                "Agent's free-text analysis of the incident. "
                "Identify the failing service, root cause, and recommended actions."
            ),
        )
        # Legacy structured fields (kept for backward compat with simulation tests)
        action_type: str = Field(
            default="CHECK_METRICS",
            description=(
                "One of: CHECK_LOGS, CHECK_METRICS, TRACE_REQUEST, "
                "RESTART_SERVICE, SCALE_UP, ROLLBACK, FAILOVER_DB, "
                "CLEAR_CACHE, DIAGNOSE, ESCALATE"
            ),
        )
        target_service: Optional[str] = Field(
            default=None,
            description="Service to target (e.g. 'cache', 'database', 'payment')",
        )
        root_cause_id: Optional[str] = Field(
            default=None,
            description="Root cause to declare (use with DIAGNOSE action)",
        )

    class IncidentCommanderObservation(Observation):
        """What the agent sees each step (openenv-compatible)."""

        incident_report: str = Field(
            default="",
            description="Full incident report with alerts, service statuses, and logs",
        )
        task_id: str = Field(
            default="",
            description="Current task identifier",
        )
        step_number: int = Field(default=0, description="Current step in the episode")
        max_steps: int = Field(default=3, description="Maximum allowed steps")
        resolved_services: List[str] = Field(
            default_factory=list,
            description="Services that have been restored so far",
        )
        total_reward: float = Field(
            default=0.0, description="Cumulative reward so far"
        )
        feedback: str = Field(
            default="", description="Feedback from previous action"
        )
        done: bool = Field(default=False, description="Whether the episode is complete")
        reward: float = Field(default=0.0, description="Reward for this step")

except ImportError:
    # Fallback if openenv is not installed (e.g. during local dev without openenv)
    class IncidentCommanderAction(BaseModel):  # type: ignore[no-redef]
        response: str = ""
        action_type: str = "CHECK_METRICS"
        target_service: Optional[str] = None
        root_cause_id: Optional[str] = None

    class IncidentCommanderObservation(BaseModel):  # type: ignore[no-redef]
        incident_report: str = ""
        task_id: str = ""
        step_number: int = 0
        max_steps: int = 3
        resolved_services: List[str] = Field(default_factory=list)
        total_reward: float = 0.0
        feedback: str = ""
        done: bool = False
        reward: float = 0.0

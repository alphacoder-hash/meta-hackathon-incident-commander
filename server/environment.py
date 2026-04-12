"""
server/environment.py — OpenEnv-compliant wrapper for IncidentCommanderEnv.

Matches the winning finalist pattern:
  - _pick_scenarios() picks 1 random scenario per tier on each reset()
  - step() passes scenario dict into the tier-appropriate grader
  - Task selection from TASK_NAME env var OR options={"task_name": ...} kwarg
  - SUPPORTS_CONCURRENT_SESSIONS = True
"""

import os
import sys
import random
from uuid import uuid4
from typing import Optional

# Ensure root is on sys.path for local imports
_server_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_server_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

# Import openenv-compatible models
try:
    from ..models import IncidentCommanderAction, IncidentCommanderObservation
except ImportError:
    from models import IncidentCommanderAction, IncidentCommanderObservation

# Import graders and scenario pools (zero external deps — fast import for tests)
try:
    from .graders import (
        EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS,
        grade_easy, grade_medium, grade_hard,
    )
except ImportError:
    from graders import (
        EASY_SCENARIOS, MEDIUM_SCENARIOS, HARD_SCENARIOS,
        grade_easy, grade_medium, grade_hard,
    )


# Task order matches OpenEnv difficulty ladder
TASK_ORDER = ["easy", "medium", "hard"]

# Grader function lookup (maps task tier → grader)
GRADER_MAP = {
    "easy": grade_easy,
    "medium": grade_medium,
    "hard": grade_hard,
}

# Scenario pool lookup (maps task tier → list of scenario dicts)
SCENARIO_POOL = {
    "easy": EASY_SCENARIOS,
    "medium": MEDIUM_SCENARIOS,
    "hard": HARD_SCENARIOS,
}


class IncidentCommanderEnvironment(Environment):
    """
    OpenEnv-compliant IncidentCommander environment.

    The agent receives live production incident observations (structured reports
    with alerts, service statuses, logs, and red herrings) and must diagnose
    root causes and restore services.

    Tasks:
      - easy   (3 rotating scenarios): Single-service failure, clear logs
      - medium (3 rotating scenarios): Multi-signal with 1 red herring
      - hard   (3 rotating scenarios): Cascading P0, prioritized action plan required
    """

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        self._state = State(episode_id=str(uuid4()), step_count=0)
        self._total_reward: float = 0.0
        self._current_task: str = "easy"
        self._is_single_task: bool = False
        self._current_task_index: int = 0
        self._scenarios: dict = {}
        self._pick_scenarios()

        # Respect TASK_NAME env var at construction time
        target_task = os.getenv("TASK_NAME")
        if target_task in TASK_ORDER:
            self._current_task = target_task
            self._current_task_index = TASK_ORDER.index(target_task)
            self._is_single_task = True

    # -------------------------------------------------------------------------
    # Scenario rotation
    # -------------------------------------------------------------------------

    def _pick_scenarios(self) -> None:
        """Pick one random scenario per difficulty tier for this episode."""
        self._scenarios = {
            tier: random.choice(pool)
            for tier, pool in SCENARIO_POOL.items()
        }

    # -------------------------------------------------------------------------
    # OpenEnv interface
    # -------------------------------------------------------------------------

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs,
    ) -> "IncidentCommanderObservation":
        """
        Start a new episode.

        Task selection priority (highest wins):
          1. TASK_NAME env variable
          2. options={"task_name": "..."} kwarg (OpenEnv standard)
          3. task_name=... or task_id=... direct kwarg
          4. Default: "easy"
        """
        self._state = State(episode_id=episode_id or str(uuid4()), step_count=0)
        self._total_reward = 0.0

        # Pick new scenarios for this episode
        if seed is not None:
            random.seed(seed)
        self._pick_scenarios()

        # ── Task resolution (match winning repo pattern exactly) ──────────────
        target_task = os.getenv("TASK_NAME")

        # OpenEnv standard: options dict
        options = kwargs.get("options", {})
        if isinstance(options, dict):
            target_task = options.get("task_name", options.get("task_id", target_task))

        # Direct kwargs
        if "task_name" in kwargs:
            target_task = kwargs["task_name"]
        elif "task_id" in kwargs:
            target_task = kwargs["task_id"]

        # Handle edge case where seed is accidentally a dict
        elif seed is not None and isinstance(seed, dict):
            target_task = seed.get("task_name", seed.get("task_id", target_task))

        # Handle improperly destructured kwargs from testing scripts
        elif kwargs and isinstance(list(kwargs.values())[0], dict):
            inner = list(kwargs.values())[0]
            if "task_name" in inner or "task_id" in inner:
                target_task = inner.get("task_name", inner.get("task_id"))

        if target_task in TASK_ORDER:
            self._current_task = target_task
            self._current_task_index = TASK_ORDER.index(target_task)
            self._is_single_task = True
        else:
            self._current_task = TASK_ORDER[0]
            self._current_task_index = 0
            self._is_single_task = False

        scenario = self._scenarios[self._current_task]

        return IncidentCommanderObservation(
            incident_report=scenario["incident_report"],
            task_id=self._current_task,
            step_number=0,
            max_steps=3,
            resolved_services=[],
            total_reward=0.0,
            feedback="Welcome. Analyze the incident report and respond with your findings.",
            done=False,
            reward=0.0,
        )

    def step(self, action: "IncidentCommanderAction") -> "IncidentCommanderObservation":
        """
        Grade the agent's response and advance to the next task (or end episode).
        Each task is a single step: reset → step → done (or → next task).
        """
        if self._current_task_index >= len(TASK_ORDER):
            return IncidentCommanderObservation(
                incident_report="All incidents resolved.",
                task_id="complete",
                step_number=self._state.step_count,
                max_steps=3,
                resolved_services=[],
                total_reward=self._total_reward,
                feedback="Episode is already done. Please reset the environment.",
                done=True,
                reward=0.0,
            )

        self._state.step_count += 1

        current_task = TASK_ORDER[self._current_task_index]
        scenario = self._scenarios[current_task]
        grader = GRADER_MAP[current_task]

        # Extract free-text response from action
        response_text = _extract_response(action)

        # Grade with the scenario dict — matches winning pattern
        reward = grader(response_text, scenario)
        self._total_reward += reward

        # Advance: single-task mode → done immediately; multi-task → next tier
        if self._is_single_task:
            done = True
        else:
            self._current_task_index += 1
            done = self._current_task_index >= len(TASK_ORDER)

        if not done:
            next_task = TASK_ORDER[self._current_task_index]
            next_scenario = self._scenarios[next_task]
            return IncidentCommanderObservation(
                incident_report=next_scenario["incident_report"],
                task_id=next_task,
                step_number=self._state.step_count,
                max_steps=3,
                resolved_services=[],
                total_reward=self._total_reward,
                feedback=f"Task scored: {reward:.2f}. Moving to next incident.",
                done=False,
                reward=reward,
            )
        else:
            return IncidentCommanderObservation(
                incident_report="All incidents resolved.",
                task_id="complete",
                step_number=self._state.step_count,
                max_steps=3,
                resolved_services=[],
                total_reward=self._total_reward,
                feedback=(
                    f"Final task scored: {reward:.2f}. "
                    f"All tasks complete. Total: {self._total_reward:.2f}/3.00"
                ),
                done=True,
                reward=reward,
            )

    @property
    def state(self) -> State:
        return self._state

    def close(self) -> None:
        """
        Required by the openenv framework — called during introspection/cleanup.
        No persistent resources to release; intentionally a no-op.
        """
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_response(action: "IncidentCommanderAction") -> str:
    """
    Extract a free-text response string from the action.

    The openenv action can be submitted as free text (response field)
    or as a structured JSON action (action_type + optional fields).
    This helper handles both and returns a string for grading.
    """
    # Primary: dedicated response field (preferred, matches grader input)
    if hasattr(action, "response") and action.response:
        return str(action.response)

    # Secondary: reconstruct a readable string from structured action fields
    parts = []
    if hasattr(action, "action_type") and action.action_type:
        parts.append(f"action_type: {action.action_type}")
    if hasattr(action, "target_service") and action.target_service:
        parts.append(f"target_service: {action.target_service}")
    if hasattr(action, "root_cause_id") and action.root_cause_id:
        parts.append(f"root_cause_id: {action.root_cause_id}")

    return " ".join(parts) if parts else ""

"""
environment.py — Core IncidentCommanderEnv.

Implements:
  env.reset(task_id, seed) → ResetResult
  env.step(action)         → StepResult
  env.state()              → IncidentState
  env.grade()              → float (0.0–1.0)
"""
from grader import RewardSignals, grade as compute_grade
from log_generator import generate_logs
from models import (
    ActionType,
    Alert,
    IncidentAction,
    IncidentObservation,
    IncidentState,
    ResetResult,
    StepResult,
)
from scenarios import SCENARIOS, Scenario
from simulator import InfrastructureSimulator
import random
import uuid
from typing import Dict, List, Optional, Any


class IncidentCommanderEnv:
    """
    OpenEnv-compatible incident response environment.

    Usage:
        env = IncidentCommanderEnv()
        result = env.reset(task_id="cascading_failure", seed=42)
        obs = result.observation

        while not done:
            action = agent.act(obs)
            result = env.step(action)
            obs, reward, done = result.observation, result.reward, result.done

        score = env.grade()  # 0.0–1.0
    """

    def __init__(self) -> None:
        self._sim = InfrastructureSimulator()
        self._scenario: Optional[Scenario] = None
        self._incident_id: str = ""
        self._step: int = 0
        self._done: bool = False
        self._total_reward: float = 0.0
        self._rng: random.Random = random.Random(42)

        # Diagnosis tracking
        self._correct_diagnosis: bool = False
        self._red_herring_ids: List[str] = []
        self._red_herring_traps: int = 0
        self._unnecessary_restarts: int = 0
        self._resolved_services: List[str] = []

        # Timeline (shown to agent)
        self._timeline: List[str] = []
        self._episode_id: str = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # reset()
    # ------------------------------------------------------------------

    def reset(self, task_id: str = "single_service_crash", seed: int = 42, episode_id: Optional[str] = None) -> ResetResult:
        if task_id not in SCENARIOS:
            raise ValueError(f"Unknown task_id '{task_id}'. Available: {list(SCENARIOS.keys())}")

        self._scenario = SCENARIOS[task_id]
        self._incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
        self._step = 0
        self._done = False
        self._total_reward = 0.0
        self._rng = random.Random(seed)
        self._correct_diagnosis = False
        self._unnecessary_restarts = 0
        self._resolved_services = []
        self._timeline = []
        self._red_herring_traps = 0

        # Collect red herring alert IDs
        self._red_herring_ids = [
            a.id for a in self._scenario.alert_templates if a.is_red_herring
        ]

        # Boot the infrastructure simulator
        self._sim = InfrastructureSimulator(seed=seed)
        self._sim.reset(
            root_cause_id=self._scenario.root_cause_id,
            affected_services=list(self._scenario.affected_services),
            chaos=self._scenario.chaos,
        )

        self._episode_id = episode_id or f"INC-{uuid.uuid4().hex[:8].upper()}"

        obs = self._build_observation()
        return ResetResult(
            observation=obs,
            task_id=task_id,
            incident_id=self._incident_id,
        )

    # ------------------------------------------------------------------
    # step()
    # ------------------------------------------------------------------

    def step(self, action: IncidentAction) -> StepResult:
        if self._done:
            raise RuntimeError("Episode is done. Call reset() to start a new episode.")
        if self._scenario is None:
            raise RuntimeError("Call reset() before step().")

        self._step += 1
        reward = 0.0
        info: Dict = {}

        # Per-step base costs
        reward += RewardSignals.STEP_COST

        # Customer impact: −0.3 per step for each failing service
        failing = self._sim.get_failing_services()
        reward += RewardSignals.CUSTOMER_IMPACT * len(failing)

        # Dispatch action
        reward += self._dispatch_action(action, info)

        # Propagate simulator one tick
        chaos_event = self._scenario.chaos and self._rng.random() < 0.3
        self._sim.tick(chaos_event=chaos_event)

        # Check chaos bonus
        if chaos_event and self._sim.is_resolved():
            reward += RewardSignals.CHAOS_HANDLED
            info["chaos_bonus"] = True

        # Track which services got restored this step
        now_healthy = set(self._sim.get_healthy_services())
        was_affected = set(self._scenario.affected_services)
        newly_resolved = [
            svc for svc in was_affected
            if svc in now_healthy and svc not in self._resolved_services
        ]
        for svc in newly_resolved:
            self._resolved_services.append(svc)
            reward += RewardSignals.SERVICE_RESTORED
            self._timeline.append(f"Step {self._step}: ✅ {svc} restored")

        # All services restored bonus
        if self._sim.is_resolved() and len(newly_resolved) > 0:
            reward += RewardSignals.ALL_RESOLVED
            info["all_resolved"] = True

        reward = RewardSignals.clamp(reward)
        self._total_reward += reward

        # Episode done: all resolved OR max_steps reached OR action forced done (ESCALATE)
        self._done = self._done or self._sim.is_resolved() or self._step >= self._scenario.max_steps

        return StepResult(
            observation=self._build_observation(),
            reward=reward,
            done=self._done,
            info=info,
        )

    # ------------------------------------------------------------------
    # Action dispatch
    # ------------------------------------------------------------------

    def _dispatch_action(self, action: IncidentAction, info: Dict) -> float:
        reward = 0.0
        atype = action.action_type
        target = action.target_service
        cause = action.root_cause_id

        failing_svcs = set(self._sim.get_failing_services())

        if atype == ActionType.CHECK_LOGS:
            if target and target in failing_svcs:
                reward += RewardSignals.USEFUL_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🔍 CHECK_LOGS {target} — anomalies found")
            else:
                reward += RewardSignals.WASTED_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🔍 CHECK_LOGS {target or 'all'} — nothing notable")

        elif atype == ActionType.CHECK_METRICS:
            if target and target in failing_svcs:
                reward += RewardSignals.USEFUL_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 📊 CHECK_METRICS {target} — degraded metrics detected")
            else:
                reward += RewardSignals.WASTED_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 📊 CHECK_METRICS {target or 'all'} — metrics normal")

        elif atype == ActionType.TRACE_REQUEST:
            if target and target in failing_svcs:
                reward += RewardSignals.USEFUL_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🔗 TRACE_REQUEST through {target} — errors in trace")
            else:
                reward += RewardSignals.WASTED_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🔗 TRACE_REQUEST through {target or '?'} — trace clean")

        elif atype == ActionType.DIAGNOSE:
            if cause == self._scenario.root_cause_id:
                if not self._correct_diagnosis:
                    reward += RewardSignals.CORRECT_DIAGNOSIS
                    self._correct_diagnosis = True
                    info["diagnosis"] = "correct"
                    self._timeline.append(f"Step {self._step}: 🎯 DIAGNOSE → {cause} ✅ CORRECT")
                else:
                    # Already diagnosed; small penalty for redundancy
                    reward += RewardSignals.WASTED_INVESTIGATION
            else:
                if cause:
                    # Check if this target is a red herring
                    _rh_causes = {
                        a.service for a in self._scenario.alert_templates
                        if a.is_red_herring
                    }
                    if cause in _rh_causes:
                        self._red_herring_traps += 1
                        reward += RewardSignals.RED_HERRING_TRAP
                        self._timeline.append(f"Step {self._step}: ❌ DIAGNOSE → {cause} (red herring!)")
                    else:
                        reward += RewardSignals.WRONG_DIAGNOSIS
                        self._timeline.append(f"Step {self._step}: ❌ DIAGNOSE → {cause} WRONG")
                info["diagnosis"] = "incorrect"

        elif atype == ActionType.RESTART_SERVICE:
            if target:
                was_down = self._sim.restart_service(target)
                if not was_down:
                    reward += RewardSignals.UNNECESSARY_RESTART
                    self._unnecessary_restarts += 1
                    self._timeline.append(f"Step {self._step}: ⚠️ RESTART_SERVICE {target} — was healthy!")
                else:
                    reward += RewardSignals.PARTIAL_FIX
                    self._timeline.append(f"Step {self._step}: 🔄 RESTART_SERVICE {target}")

        elif atype == ActionType.CLEAR_CACHE:
            fixed = self._sim.clear_cache()
            if fixed:
                reward += RewardSignals.PARTIAL_FIX
                self._timeline.append(f"Step {self._step}: 🗑️ CLEAR_CACHE — flushed successfully")
            else:
                reward += RewardSignals.WASTED_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🗑️ CLEAR_CACHE — no effect (not root cause)")

        elif atype == ActionType.ROLLBACK:
            if target:
                fixed = self._sim.rollback_service(target)
                if fixed:
                    reward += RewardSignals.PARTIAL_FIX
                    self._timeline.append(f"Step {self._step}: ↩️ ROLLBACK {target} — reverted to previous version")
                else:
                    reward += RewardSignals.WASTED_INVESTIGATION
                    self._timeline.append(f"Step {self._step}: ↩️ ROLLBACK {target} — no effect")

        elif atype == ActionType.FAILOVER_DB:
            fixed = self._sim.failover_db()
            if fixed:
                reward += RewardSignals.PARTIAL_FIX
                self._timeline.append(f"Step {self._step}: 🔀 FAILOVER_DB — switched to replica")
            else:
                reward += RewardSignals.WASTED_INVESTIGATION
                self._timeline.append(f"Step {self._step}: 🔀 FAILOVER_DB — no effect")

        elif atype == ActionType.SCALE_UP:
            if target:
                fixed = self._sim.scale_up(target)
                if fixed:
                    reward += RewardSignals.PARTIAL_FIX
                    self._timeline.append(f"Step {self._step}: ⬆️ SCALE_UP {target} — capacity increased")
                else:
                    reward += RewardSignals.WASTED_INVESTIGATION
                    self._timeline.append(f"Step {self._step}: ⬆️ SCALE_UP {target} — no effect")

        elif atype == ActionType.ESCALATE:
            reward += RewardSignals.ESCALATE
            self._done = True
            self._timeline.append(f"Step {self._step}: 🚨 ESCALATE — incident escalated to senior team")

        return reward

    def state(self) -> IncidentState:
        """Return full ground-truth state (not seen by the agent)."""
        return IncidentState(
            incident_id=self._incident_id,
            task_id=self._scenario.task_id if self._scenario else "",
            root_cause_id=self._scenario.root_cause_id if self._scenario else "",
            step=self._step,
            max_steps=self._scenario.max_steps if self._scenario else 0,
            done=self._done,
            correct_diagnosis=self._correct_diagnosis,
            affected_services=list(self._scenario.affected_services) if self._scenario else [],
            resolved_services=list(self._resolved_services),
            red_herring_ids=list(self._red_herring_ids),
            red_herring_traps_triggered=self._red_herring_traps,
            unnecessary_restarts=self._unnecessary_restarts,
            service_uptime_history=dict(self._sim.uptime_history),
            total_reward=round(self._total_reward, 4),
            chaos_active=self._scenario.chaos if self._scenario else False,
        )

    def grade(self) -> float:
        return compute_grade(self.state())

    # ------------------------------------------------------------------
    # Internal — build observation for agent
    # ------------------------------------------------------------------

    def _build_observation(self) -> IncidentObservation:
        assert self._scenario is not None

        # Build alerts (hide is_red_herring from agent)
        alerts = [
            Alert(
                id=a.id,
                severity=a.severity,
                service=a.service,
                message=a.message,
                timestamp=f"2026-03-28T10:{self._step:02d}:00Z",
                is_red_herring=False,   # agents never see this
            )
            for a in self._scenario.alert_templates
        ]

        failing = self._sim.get_failing_services()
        healthy = self._sim.get_healthy_services()

        logs = generate_logs(
            root_cause_id=self._scenario.root_cause_id,
            step=self._step,
            healthy_services=healthy,
            failing_services=failing,
            chaos_active=self._scenario.chaos,
            rng=self._rng,
        )

        return IncidentObservation(
            incident_id=self._incident_id,
            task_id=self._scenario.task_id,
            step=self._step,
            max_steps=self._scenario.max_steps,
            alerts=alerts,
            service_statuses=self._sim.get_statuses(),
            logs=logs,
            timeline=list(self._timeline[-10:]),   # last 10 events
            resolved_services=list(self._resolved_services),
            total_reward=round(self._total_reward, 4),
        )

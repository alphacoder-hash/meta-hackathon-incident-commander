"""
grader.py — Deterministic grader for IncidentCommander episodes.

Final score formula (0.0–1.0):
  score = 0.30 × diagnosis
        + 0.30 × services_restored
        + 0.20 × time_efficiency
        + 0.15 × avg_uptime
        + 0.05 × (1 − red_herring_penalty)
"""
from __future__ import annotations

from typing import Dict, List

from .models import IncidentState


# ---------------------------------------------------------------------------
# Grade from a completed IncidentState
# ---------------------------------------------------------------------------

def grade(state: IncidentState) -> float:
    """
    Compute final episode score in [0.0, 1.0].

    Components:
    - diagnosis (0.30): Did the agent correctly identify the root cause?
    - services_restored (0.30): Fraction of affected services that are now healthy.
    - time_efficiency (0.20): Used fewer steps → higher score.
    - avg_uptime (0.15): Average per-step uptime across all services.
    - red_herring_penalty (0.05): Penalised for chasing red herrings.
    """
    # 1. Diagnosis score
    diagnosis = 1.0 if state.correct_diagnosis else 0.0

    # 2. Services restored score
    n_affected = max(1, len(state.affected_services))
    n_restored = len(state.resolved_services)
    services_restored = min(1.0, n_restored / n_affected)

    # 3. Time efficiency
    #    Linear: using all steps → 0.0; using 1 step → 1.0
    steps_used = max(1, state.step)
    max_steps = max(1, state.max_steps)
    time_efficiency = max(0.0, 1.0 - (steps_used / max_steps))

    # 4. Average uptime across all services and all steps
    all_uptime_vals: List[float] = []
    for svc_history in state.service_uptime_history.values():
        if svc_history:
            svc_avg = sum(1.0 if up else 0.0 for up in svc_history) / len(svc_history)
            all_uptime_vals.append(svc_avg)
    avg_uptime = sum(all_uptime_vals) / len(all_uptime_vals) if all_uptime_vals else 0.0

    # 5. Red herring penalty
    #    Each red herring trap triggered costs 0.2 (up to max 1.0 penalty)
    red_herring_penalty = min(1.0, state.red_herring_traps_triggered * 0.2)

    # Weighted sum
    raw = (
        0.30 * diagnosis
        + 0.30 * services_restored
        + 0.20 * time_efficiency
        + 0.15 * avg_uptime
        + 0.05 * (1.0 - red_herring_penalty)
    )

    return round(min(1.0, max(0.0, raw)), 4)


# ---------------------------------------------------------------------------
# Per-step reward signals (called from environment.py)
# ---------------------------------------------------------------------------

class RewardSignals:
    SERVICE_RESTORED       = +2.0   # A failing service returned to healthy
    CORRECT_DIAGNOSIS      = +3.0   # Agent correctly identified root cause
    USEFUL_INVESTIGATION   = +0.5   # Checked logs/metrics of a failing service
    WASTED_INVESTIGATION   = -0.2   # Checked healthy service logs/metrics
    RED_HERRING_TRAP       = -0.5   # Acted on a known red-herring alert
    UNNECESSARY_RESTART    = -1.0   # Restarted a healthy service
    WRONG_DIAGNOSIS        = -1.5   # Diagnosed with wrong root_cause_id
    CUSTOMER_IMPACT        = -0.3   # Per-step penalty while services are down
    STEP_COST              = -0.1   # Constant per-step cost
    ALL_RESOLVED           = +5.0   # Bonus: all services restored
    CHAOS_HANDLED          = +2.0   # Agent stabilised despite chaos injection
    ESCALATE               = -2.0   # Escalated instead of solving
    PARTIAL_FIX            = +0.5   # Action partially improved a metric

    @classmethod
    def clamp(cls, reward: float) -> float:
        return round(max(-10.0, min(10.0, reward)), 4)

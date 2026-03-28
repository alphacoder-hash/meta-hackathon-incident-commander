"""
test_grader.py — Unit tests for the deterministic grader.
"""
import pytest

from incident_commander_env.grader import grade, RewardSignals
from incident_commander_env.models import IncidentState


def make_state(**overrides) -> IncidentState:
    """Helper: create a default IncidentState with optional overrides."""
    defaults = dict(
        incident_id="INC-TEST",
        task_id="single_service_crash",
        root_cause_id="cache_oom",
        step=5,
        max_steps=10,
        done=True,
        correct_diagnosis=False,
        affected_services=["cache"],
        resolved_services=[],
        red_herring_ids=["alert_cdn_spike"],
        red_herring_traps_triggered=0,
        unnecessary_restarts=0,
        service_uptime_history={
            "api_gateway": [True] * 5,
            "auth": [True] * 5,
            "database": [True] * 5,
            "cache": [False, False, False, False, False],
            "queue": [True] * 5,
            "payment": [True] * 5,
            "notification": [True] * 5,
            "cdn": [True] * 5,
        },
        total_reward=0.0,
        chaos_active=False,
    )
    defaults.update(overrides)
    return IncidentState(**defaults)


class TestGrade:
    def test_grade_returns_float(self):
        state = make_state()
        score = grade(state)
        assert isinstance(score, float)

    def test_grade_in_range(self):
        for _ in range(10):
            state = make_state()
            score = grade(state)
            assert 0.0 <= score <= 1.0

    def test_perfect_score(self):
        """All components maxed out → score near 1.0."""
        state = make_state(
            correct_diagnosis=True,
            resolved_services=["cache"],
            step=1,          # fastest possible
            max_steps=10,
            red_herring_traps_triggered=0,
            service_uptime_history={
                svc: [True] * 1
                for svc in ["api_gateway", "auth", "database", "cache",
                             "queue", "payment", "notification", "cdn"]
            },
        )
        score = grade(state)
        assert score >= 0.7, f"Near-perfect play should score >= 0.7, got {score}"

    def test_worst_score(self):
        """All components at minimum → score near 0."""
        state = make_state(
            correct_diagnosis=False,
            resolved_services=[],
            step=10,         # all steps used
            max_steps=10,
            red_herring_traps_triggered=5,
            service_uptime_history={
                svc: [False] * 10
                for svc in ["api_gateway", "auth", "database", "cache",
                             "queue", "payment", "notification", "cdn"]
            },
        )
        score = grade(state)
        assert score < 0.3, f"Worst play should score < 0.3, got {score}"

    def test_correct_diagnosis_increases_score(self):
        base = make_state(correct_diagnosis=False)
        diag = make_state(correct_diagnosis=True)
        assert grade(diag) > grade(base)

    def test_services_restored_increases_score(self):
        no_fix = make_state(resolved_services=[])
        fixed = make_state(resolved_services=["cache"])
        assert grade(fixed) > grade(no_fix)

    def test_time_efficiency(self):
        slow = make_state(step=10, max_steps=10)
        fast = make_state(step=2, max_steps=10)
        assert grade(fast) > grade(slow)

    def test_red_herring_penalty_reduces_score(self):
        clean = make_state(red_herring_traps_triggered=0)
        trapped = make_state(red_herring_traps_triggered=3)
        assert grade(clean) > grade(trapped)

    def test_grader_is_deterministic(self):
        state = make_state(correct_diagnosis=True, resolved_services=["cache"])
        assert grade(state) == grade(state)


class TestRewardSignals:
    def test_clamp_within_range(self):
        assert RewardSignals.clamp(1000.0) == 10.0
        assert RewardSignals.clamp(-1000.0) == -10.0
        assert RewardSignals.clamp(5.0) == 5.0

    def test_positive_rewards_are_positive(self):
        assert RewardSignals.SERVICE_RESTORED > 0
        assert RewardSignals.CORRECT_DIAGNOSIS > 0
        assert RewardSignals.ALL_RESOLVED > 0
        assert RewardSignals.USEFUL_INVESTIGATION > 0

    def test_negative_rewards_are_negative(self):
        assert RewardSignals.WRONG_DIAGNOSIS < 0
        assert RewardSignals.UNNECESSARY_RESTART < 0
        assert RewardSignals.ESCALATE < 0
        assert RewardSignals.STEP_COST < 0
        assert RewardSignals.CUSTOMER_IMPACT < 0

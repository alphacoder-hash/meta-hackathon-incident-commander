"""
test_environment.py — Integration tests for the full episode lifecycle.
"""
import pytest

from incident_commander_env import (
    ActionType,
    IncidentAction,
    IncidentCommanderEnv,
    IncidentObservation,
    ResetResult,
    StepResult,
)


TASKS = [
    "single_service_crash",
    "cascading_failure",
    "bad_deployment",
    "silent_degradation",
]


class TestReset:
    def test_reset_returns_reset_result(self):
        env = IncidentCommanderEnv()
        result = env.reset(task_id="single_service_crash", seed=42)
        assert isinstance(result, ResetResult)

    def test_reset_observation_structure(self):
        env = IncidentCommanderEnv()
        result = env.reset(task_id="single_service_crash", seed=42)
        obs = result.observation
        assert isinstance(obs, IncidentObservation)
        assert obs.step == 0
        assert obs.max_steps == 10
        assert len(obs.alerts) > 0
        assert len(obs.service_statuses) == 8   # all 8 services

    def test_reset_all_tasks(self):
        env = IncidentCommanderEnv()
        for task_id in TASKS:
            result = env.reset(task_id=task_id, seed=42)
            assert result.task_id == task_id
            assert result.incident_id.startswith("INC-")

    def test_reset_invalid_task_raises(self):
        env = IncidentCommanderEnv()
        with pytest.raises(ValueError, match="Unknown task_id"):
            env.reset(task_id="nonexistent_task")

    def test_reset_reproducible_with_same_seed(self):
        env = IncidentCommanderEnv()
        r1 = env.reset(task_id="cascading_failure", seed=123)
        r2 = env.reset(task_id="cascading_failure", seed=123)
        assert r1.observation.task_id == r2.observation.task_id


class TestStep:
    def test_step_returns_step_result(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        action = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache")
        result = env.step(action)
        assert isinstance(result, StepResult)

    def test_step_increments_step_counter(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        for i in range(3):
            action = IncidentAction(action_type=ActionType.CHECK_METRICS, target_service="cache")
            result = env.step(action)
            assert result.observation.step == i + 1

    def test_step_reward_is_float(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="cascading_failure", seed=42)
        result = env.step(IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="database"))
        assert isinstance(result.reward, float)

    def test_step_done_within_max_steps(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        done = False
        steps = 0
        while not done and steps < 20:
            result = env.step(IncidentAction(action_type=ActionType.CHECK_METRICS, target_service="cache"))
            done = result.done
            steps += 1
        # Should end within max_steps (10) + buffer
        assert steps <= 11

    def test_step_after_done_raises(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        # Force done via escalate (ESCALATE sets done=True immediately)
        result = env.step(IncidentAction(action_type=ActionType.ESCALATE))
        assert result.done is True, "ESCALATE must set done=True"
        # Next step should raise
        with pytest.raises(RuntimeError):
            env.step(IncidentAction(action_type=ActionType.CHECK_LOGS))

    def test_step_before_reset_raises(self):
        env = IncidentCommanderEnv()
        with pytest.raises(RuntimeError, match="Call reset"):
            env.step(IncidentAction(action_type=ActionType.CHECK_LOGS))

    def test_correct_diagnosis_gives_reward(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        result = env.step(IncidentAction(
            action_type=ActionType.DIAGNOSE,
            root_cause_id="cache_oom",
        ))
        # Correct diagnosis gives +3.0 reward (minus step costs)
        assert result.reward > 0, "Correct diagnosis should give net positive reward"
        assert result.info.get("diagnosis") == "correct"

    def test_wrong_diagnosis_penalises(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        result = env.step(IncidentAction(
            action_type=ActionType.DIAGNOSE,
            root_cause_id="database_overload",
        ))
        assert result.reward < 0, "Wrong diagnosis should give negative reward"

    def test_unnecessary_restart_penalises(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        # api_gateway is healthy initially in single_service_crash
        result = env.step(IncidentAction(
            action_type=ActionType.RESTART_SERVICE,
            target_service="notification",  # not affected
        ))
        # -1.0 (restart) -0.1 (step) -0.3 (customer impact × 1 failing service)
        assert result.reward <= -1.0


class TestEpisodeLifecycle:
    def test_full_episode_task1_optimal(self):
        """Optimal play for single_service_crash: check logs → diagnose → clear_cache."""
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)

        # Check logs (useful — cache is failing)
        env.step(IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache"))
        # Diagnose correctly BEFORE fixing (so done doesn't trigger early)
        env.step(IncidentAction(
            action_type=ActionType.DIAGNOSE,
            root_cause_id="cache_oom",
        ))
        # Clear cache (fixes cache_oom — this may end the episode)
        env.step(IncidentAction(action_type=ActionType.CLEAR_CACHE))
        score = env.grade()
        assert score > 0.4, f"Optimal play should score > 0.4, got {score}"

    def test_grade_returns_0_to_1(self):
        env = IncidentCommanderEnv()
        for task_id in TASKS:
            env.reset(task_id=task_id, seed=42)
            for _ in range(3):
                result = env.step(IncidentAction(action_type=ActionType.CHECK_METRICS, target_service="api_gateway"))
                if result.done:
                    break   # stop stepping if episode ended early
            score = env.grade()
            assert 0.0 <= score <= 1.0, f"Score out of range for {task_id}: {score}"

    def test_state_exposes_ground_truth(self):
        env = IncidentCommanderEnv()
        env.reset(task_id="cascading_failure", seed=42)
        state = env.state()
        assert state.root_cause_id == "database_overload"
        assert "database" in state.affected_services

    def test_grade_improves_with_correct_actions(self):
        """Grade with correct diagnosis should beat random play."""
        env = IncidentCommanderEnv()
        env.reset(task_id="single_service_crash", seed=42)
        env.step(IncidentAction(action_type=ActionType.DIAGNOSE, root_cause_id="cache_oom"))
        env.step(IncidentAction(action_type=ActionType.CLEAR_CACHE))
        good_score = env.grade()

        env.reset(task_id="single_service_crash", seed=42)
        env.step(IncidentAction(action_type=ActionType.ESCALATE))
        bad_score = env.grade()

        assert good_score > bad_score, "Correct play must outscore escalation"

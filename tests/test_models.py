"""
test_models.py — Unit tests for Pydantic models.
"""
import pytest
from pydantic import ValidationError

from incident_commander_env.models import (
    ActionType,
    IncidentAction,
    IncidentObservation,
    Alert,
    ServiceStatus,
    StepResult,
    ResetResult,
    IncidentState,
)


class TestActionType:
    def test_all_actions_exist(self):
        expected = {
            "CHECK_LOGS", "CHECK_METRICS", "TRACE_REQUEST", "RESTART_SERVICE",
            "SCALE_UP", "ROLLBACK", "FAILOVER_DB", "CLEAR_CACHE", "DIAGNOSE", "ESCALATE",
        }
        assert set(a.value for a in ActionType) == expected

    def test_action_count(self):
        assert len(ActionType) == 10


class TestIncidentAction:
    def test_basic_action(self):
        a = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache")
        assert a.action_type == ActionType.CHECK_LOGS
        assert a.target_service == "cache"

    def test_action_from_string(self):
        a = IncidentAction(action_type="DIAGNOSE", root_cause_id="cache_oom")
        assert a.action_type == ActionType.DIAGNOSE
        assert a.root_cause_id == "cache_oom"

    def test_optional_fields_default_none(self):
        a = IncidentAction(action_type=ActionType.ESCALATE)
        assert a.target_service is None
        assert a.root_cause_id is None

    def test_invalid_action_type_raises(self):
        with pytest.raises(ValidationError):
            IncidentAction(action_type="INVALID_ACTION")

    def test_extra_fields_ignored(self):
        a = IncidentAction(action_type="CHECK_LOGS", unknown_field="foo")
        assert not hasattr(a, "unknown_field")


class TestAlert:
    def test_alert_creation(self):
        alert = Alert(
            id="test_1",
            severity="critical",
            service="cache",
            message="Cache is down",
            timestamp="2026-03-28T10:00:00Z",
        )
        assert alert.is_red_herring is False
        assert alert.severity == "critical"


class TestServiceStatus:
    def test_service_status(self):
        s = ServiceStatus(
            name="database",
            healthy=True,
            latency_ms=12.0,
            error_rate=0.001,
            cpu_pct=55.0,
            memory_pct=60.0,
        )
        assert s.name == "database"
        assert s.restarts == 0


class TestResultModels:
    def test_step_result_defaults(self):
        obs = IncidentObservation(
            incident_id="INC-001",
            task_id="single_service_crash",
            step=1,
            max_steps=10,
            alerts=[],
            service_statuses=[],
            logs=[],
        )
        result = StepResult(observation=obs, reward=0.5, done=False)
        assert result.info == {}
        assert result.done is False

    def test_incident_state(self):
        state = IncidentState(
            incident_id="INC-001",
            task_id="cascading_failure",
            root_cause_id="database_overload",
            step=5,
            max_steps=15,
            done=False,
            correct_diagnosis=True,
            affected_services=["database", "auth"],
            resolved_services=["auth"],
            red_herring_ids=["alert_payment_ab"],
            red_herring_traps_triggered=0,
            unnecessary_restarts=0,
            service_uptime_history={"database": [False, False, True]},
            total_reward=2.5,
            chaos_active=False,
        )
        assert state.correct_diagnosis is True
        assert len(state.resolved_services) == 1

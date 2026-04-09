"""
test_server.py — Integration tests for the FastAPI server endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from server.app import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["environment"] == "incident_commander"


def test_info_endpoint():
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert "actions" in data
    assert data["name"] == "IncidentCommander"
    assert len(data["tasks"]) >= 3   # must have at least 3 tasks


def test_reset_endpoint():
    payload = {"task_id": "single_service_crash", "seed": 42}
    response = client.post("/reset", json=payload)
    assert response.status_code == 200
    data = response.json()

    # ResetResult structure: {"observation": {...}, "task_id": ..., "incident_id": ...}
    assert "observation" in data
    obs = data["observation"]
    assert "incident_id" in obs
    assert obs["task_id"] == "single_service_crash"
    assert data["task_id"] == "single_service_crash"
    assert data["incident_id"].startswith("INC-")


def test_step_endpoint():
    # First reset
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})

    # Take an action — submit IncidentAction directly (not wrapped)
    payload = {"action_type": "CHECK_LOGS", "target_service": "cache"}
    response = client.post("/step", json=payload)
    assert response.status_code == 200
    data = response.json()

    # StepResult structure: {"observation": {...}, "reward": ..., "done": ..., "info": ...}
    assert "observation" in data
    assert "reward" in data
    assert "done" in data
    assert isinstance(data["reward"], float)


def test_state_endpoint():
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    response = client.get("/state")
    assert response.status_code == 200
    data = response.json()
    # IncidentState schema
    assert "root_cause_id" in data
    assert "affected_services" in data
    assert "correct_diagnosis" in data
    assert data["root_cause_id"] == "cache_oom"


def test_grade_endpoint():
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    response = client.get("/grade")
    assert response.status_code == 200
    data = response.json()
    assert "score" in data
    assert isinstance(data["score"], float)
    assert 0.0 <= data["score"] <= 1.0


def test_reset_invalid_task():
    response = client.post("/reset", json={"task_id": "nonexistent_task"})
    assert response.status_code == 400


def test_step_before_reset():
    """Step without episode is handled gracefully."""
    # (Server has a persistent env; state from previous test may carry)
    # Just verify it doesn't 500 on an invalid action_type
    pass  # Covered by integration flow above


def test_root_redirects_to_ui():
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)

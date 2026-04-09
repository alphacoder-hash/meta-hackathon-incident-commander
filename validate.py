"""
validate.py — Pre-submission validation script for IncidentCommander OpenEnv.

Checks every item on the hackathon pre-submission checklist:
  1. openenv.yaml is valid YAML with required fields
  2. Typed models (Action, Observation, State) are importable & correct
  3. step() / reset() / state() work end-to-end
  4. 3+ tasks exist, each grader returns score in [0.0, 1.0]
  5. inference.py exists at root with correct env var support
  6. Dockerfile exists

Run:  python validate.py
Exit code 0 = all checks pass. Non-zero = at least one failure.
"""
from __future__ import annotations

import os
import sys
import importlib
import traceback

# Ensure root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

failures: list[str] = []


def check(name: str, fn):
    try:
        result = fn()
        msg = f" - {result}" if isinstance(result, str) else ""
        print(f"{PASS} {name}{msg}")
    except Exception as exc:
        print(f"{FAIL} {name}: {exc}")
        failures.append(f"{name}: {exc}")


# ---------------------------------------------------------------------------
# 1. openenv.yaml
# ---------------------------------------------------------------------------
print("\n=== 1. openenv.yaml ===")

def check_yaml_exists():
    assert os.path.exists("openenv.yaml"), "openenv.yaml not found at project root"
    return "found"

def check_yaml_valid():
    import yaml
    with open("openenv.yaml") as f:
        data = yaml.safe_load(f)
    required = ["spec_version", "name", "version", "description", "type", "runtime", "app", "port"]
    missing = [k for k in required if k not in data]
    assert not missing, f"Missing fields: {missing}"
    return f"name={data['name']} version={data['version']}"

def check_yaml_tasks():
    import yaml
    with open("openenv.yaml") as f:
        data = yaml.safe_load(f)
    tasks = data.get("tasks", [])
    assert len(tasks) >= 3, f"Need >= 3 tasks, found {len(tasks)}"
    for t in tasks:
        assert "id" in t, f"Task missing 'id': {t}"
        assert "difficulty" in t, f"Task missing 'difficulty': {t}"
    return f"{len(tasks)} tasks defined"

check("openenv.yaml exists", check_yaml_exists)
check("openenv.yaml valid YAML with required fields", check_yaml_valid)
check("openenv.yaml has 3+ tasks with difficulty", check_yaml_tasks)


# ---------------------------------------------------------------------------
# 2. Typed models
# ---------------------------------------------------------------------------
print("\n=== 2. Typed Pydantic Models ===")

def check_models_importable():
    from models import IncidentAction, IncidentObservation, IncidentState, ResetResult, StepResult, ActionType
    return "IncidentAction, IncidentObservation, IncidentState, ResetResult, StepResult"

def check_action_model():
    from models import IncidentAction, ActionType
    a = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache")
    assert a.action_type == ActionType.CHECK_LOGS
    assert a.target_service == "cache"
    return f"{len(ActionType)} action types"

def check_observation_model():
    from models import IncidentObservation
    obs = IncidentObservation(
        incident_id="INC-TEST", task_id="test", step=0, max_steps=10,
        alerts=[], service_statuses=[], logs=[]
    )
    assert obs.incident_id == "INC-TEST"
    return "fields: incident_id, alerts, service_statuses, logs, timeline"

def check_state_model():
    from models import IncidentState
    s = IncidentState(
        incident_id="INC-TEST", task_id="test", root_cause_id="cache_oom",
        step=0, max_steps=10, done=False, correct_diagnosis=False,
        affected_services=["cache"], resolved_services=[],
        red_herring_ids=[], red_herring_traps_triggered=0,
        unnecessary_restarts=0, service_uptime_history={},
        total_reward=0.0, chaos_active=False
    )
    return "root_cause_id, affected_services, correct_diagnosis"

check("models.py importable", check_models_importable)
check("IncidentAction model", check_action_model)
check("IncidentObservation model", check_observation_model)
check("IncidentState model", check_state_model)


# ---------------------------------------------------------------------------
# 3. Environment API: reset() / step() / state()
# ---------------------------------------------------------------------------
print("\n=== 3. Environment API ===")

def check_env_importable():
    from environment import IncidentCommanderEnv
    env = IncidentCommanderEnv()
    return "IncidentCommanderEnv instantiated"

def check_reset():
    from environment import IncidentCommanderEnv
    from models import ResetResult, IncidentObservation
    env = IncidentCommanderEnv()
    result = env.reset(task_id="single_service_crash", seed=42)
    assert isinstance(result, ResetResult), f"reset() must return ResetResult, got {type(result)}"
    assert isinstance(result.observation, IncidentObservation)
    assert result.task_id == "single_service_crash"
    assert result.incident_id.startswith("INC-")
    return f"incident_id={result.incident_id}, step={result.observation.step}"

def check_step():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType, StepResult
    env = IncidentCommanderEnv()
    env.reset(task_id="single_service_crash", seed=42)
    action = IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache")
    result = env.step(action)
    assert isinstance(result, StepResult)
    assert isinstance(result.reward, float)
    assert isinstance(result.done, bool)
    return f"reward={result.reward:.2f}, done={result.done}"

def check_state():
    from environment import IncidentCommanderEnv
    from models import IncidentState
    env = IncidentCommanderEnv()
    env.reset(task_id="cascading_failure", seed=42)
    s = env.state()
    assert isinstance(s, IncidentState)
    assert s.root_cause_id == "database_overload"
    assert "database" in s.affected_services
    return f"root_cause={s.root_cause_id}"

def check_step_before_reset_raises():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    try:
        env.step(IncidentAction(action_type=ActionType.CHECK_LOGS))
        raise AssertionError("Should have raised RuntimeError")
    except RuntimeError:
        pass
    return "raises RuntimeError as expected"

check("IncidentCommanderEnv importable", check_env_importable)
check("reset() returns ResetResult", check_reset)
check("step() returns StepResult with reward+done", check_step)
check("state() returns IncidentState with root_cause_id", check_state)
check("step() before reset() raises RuntimeError", check_step_before_reset_raises)


# ---------------------------------------------------------------------------
# 4. Tasks & Graders
# ---------------------------------------------------------------------------
print("\n=== 4. Tasks & Graders (3+ tasks, scores in [0.0, 1.0]) ===")

TASK_IDS = ["single_service_crash", "cascading_failure", "bad_deployment", "silent_degradation"]

def check_task(task_id: str):
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    env.reset(task_id=task_id, seed=42)
    # Take a few steps
    for _ in range(3):
        result = env.step(IncidentAction(action_type=ActionType.CHECK_METRICS, target_service="api_gateway"))
        if result.done:
            break
    score = env.grade()
    assert isinstance(score, float), f"grade() must return float, got {type(score)}"
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
    return f"score={score:.4f}"

for tid in TASK_IDS:
    check(f"Task '{tid}' grader -> [0.0, 1.0]", lambda t=tid: check_task(t))

def check_correct_diagnosis_rewarded():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    env.reset(task_id="single_service_crash", seed=42)
    env.step(IncidentAction(action_type=ActionType.DIAGNOSE, root_cause_id="cache_oom"))
    env.step(IncidentAction(action_type=ActionType.CLEAR_CACHE))
    good = env.grade()
    env.reset(task_id="single_service_crash", seed=42)
    env.step(IncidentAction(action_type=ActionType.ESCALATE))
    bad = env.grade()
    assert good > bad, f"Good play ({good:.4f}) must beat escalation ({bad:.4f})"
    return f"correct={good:.4f} > escalate={bad:.4f}"

check("Correct actions score higher than ESCALATE", check_correct_diagnosis_rewarded)


# ---------------------------------------------------------------------------
# 5. Reward function provides partial progress signal
# ---------------------------------------------------------------------------
print("\n=== 5. Reward Signals ===")

def check_useful_investigation_positive():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    env.reset(task_id="single_service_crash", seed=42)
    result = env.step(IncidentAction(action_type=ActionType.CHECK_LOGS, target_service="cache"))
    # cache is failing, so CHECK_LOGS cache = +0.5 (useful), minus step/impact costs
    assert result.reward > -1.0, f"Useful investigation gives too negative reward: {result.reward}"
    return f"CHECK_LOGS failing service -> reward={result.reward:.2f}"

def check_unnecessary_restart_penalized():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    env.reset(task_id="single_service_crash", seed=42)
    result = env.step(IncidentAction(action_type=ActionType.RESTART_SERVICE, target_service="notification"))
    assert result.reward < -0.5, f"Unnecessary restart should be penalized, got {result.reward}"
    return f"RESTART healthy service -> reward={result.reward:.2f}"

def check_correct_diagnosis_positive():
    from environment import IncidentCommanderEnv
    from models import IncidentAction, ActionType
    env = IncidentCommanderEnv()
    env.reset(task_id="single_service_crash", seed=42)
    result = env.step(IncidentAction(action_type=ActionType.DIAGNOSE, root_cause_id="cache_oom"))
    assert result.reward > 0, f"Correct diagnosis must be net positive, got {result.reward}"
    return f"DIAGNOSE correct -> reward={result.reward:.2f}"

check("Useful investigation gives > -1.0 reward", check_useful_investigation_positive)
check("Unnecessary restart penalized < -0.5", check_unnecessary_restart_penalized)
check("Correct diagnosis net positive reward", check_correct_diagnosis_positive)


# ---------------------------------------------------------------------------
# 6. inference.py checks
# ---------------------------------------------------------------------------
print("\n=== 6. inference.py ===")

def check_inference_exists():
    assert os.path.exists("inference.py"), "inference.py not found at project root"
    return "found at root"

def check_inference_env_vars():
    with open("inference.py") as f:
        src = f.read()
    assert "API_BASE_URL" in src, "API_BASE_URL not referenced"
    assert "MODEL_NAME" in src, "MODEL_NAME not referenced"
    assert "HF_TOKEN" in src or "OPENAI_API_KEY" in src, "No API key env var"
    return "API_BASE_URL, MODEL_NAME, HF_TOKEN/OPENAI_API_KEY all referenced"

def check_inference_log_format():
    with open("inference.py") as f:
        src = f.read()
    assert "[START]" in src, "[START] log format missing"
    assert "[STEP]" in src, "[STEP] log format missing"
    assert "[END]" in src, "[END] log format missing"
    return "[START], [STEP], [END] format present"

def check_inference_openai_client():
    with open("inference.py") as f:
        src = f.read()
    assert "from openai import OpenAI" in src or "import openai" in src, "OpenAI client not used"
    return "OpenAI client used"

check("inference.py exists at root", check_inference_exists)
check("inference.py reads API_BASE_URL, MODEL_NAME, HF_TOKEN", check_inference_env_vars)
check("inference.py emits [START]/[STEP]/[END] format", check_inference_log_format)
check("inference.py uses OpenAI client", check_inference_openai_client)


# ---------------------------------------------------------------------------
# 7. Dockerfile & server
# ---------------------------------------------------------------------------
print("\n=== 7. Dockerfile & Server ===")

def check_dockerfile():
    assert os.path.exists("Dockerfile"), "Dockerfile (capital D) not found"
    with open("Dockerfile") as f:
        content = f.read()
    assert "EXPOSE 7860" in content, "Dockerfile must EXPOSE 7860"
    assert "requirements.txt" in content, "Dockerfile must install requirements.txt"
    return "Dockerfile valid, exposes 7860"

def check_server_importable():
    from server.app import app
    return f"FastAPI app: {app.title}"

def check_server_health():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    return "GET /health -> 200 ok"

def check_server_reset():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    r = client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    assert r.status_code == 200
    data = r.json()
    assert "observation" in data
    assert "incident_id" in data
    return f"POST /reset -> 200, incident_id={data['incident_id']}"

def check_server_step():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    r = client.post("/step", json={"action_type": "CHECK_LOGS", "target_service": "cache"})
    assert r.status_code == 200
    data = r.json()
    assert "reward" in data and "done" in data
    return f"POST /step -> 200, reward={data['reward']}"

def check_server_state():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    r = client.get("/state")
    assert r.status_code == 200
    assert "root_cause_id" in r.json()
    return "GET /state -> 200, returns root_cause_id"

def check_server_grade():
    from fastapi.testclient import TestClient
    from server.app import app
    client = TestClient(app)
    client.post("/reset", json={"task_id": "single_service_crash", "seed": 42})
    r = client.get("/grade")
    assert r.status_code == 200
    score = r.json()["score"]
    assert 0.0 <= score <= 1.0
    return f"GET /grade -> 200, score={score:.4f}"

check("Dockerfile exists and exposes 7860", check_dockerfile)
check("server.app importable (FastAPI)", check_server_importable)
check("GET /health -> 200", check_server_health)
check("POST /reset -> ResetResult", check_server_reset)
check("POST /step -> StepResult", check_server_step)
check("GET /state -> IncidentState", check_server_state)
check("GET /grade -> score in [0.0, 1.0]", check_server_grade)


# ---------------------------------------------------------------------------
# 8. README
# ---------------------------------------------------------------------------
print("\n=== 8. README ===")

def check_readme():
    assert os.path.exists("README.md"), "README.md not found"
    with open("README.md", encoding="utf-8") as f:
        content = f.read()
    checks = {
        "HF Space frontmatter": "sdk: docker" in content,
        "Environment description": "IncidentCommander" in content,
        "Action space": "Action Space" in content or "action" in content.lower(),
        "Observation space": "Observation Space" in content or "observation" in content.lower(),
        "Task descriptions": "Task" in content and "Difficulty" in content,
        "Setup instructions": "Quick Start" in content or "pip install" in content,
        "Baseline scores": "Baseline" in content or "score" in content.lower(),
    }
    missing = [k for k, v in checks.items() if not v]
    assert not missing, f"README missing sections: {missing}"
    return f"{len(checks)} sections present"

check("README.md complete", check_readme)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
if failures:
    print(f"{len(failures)} FAILURE(S):")
    for f in failures:
        print(f"  - {f}")
    print("=" * 60)
    sys.exit(1)
else:
    print("ALL CHECKS PASSED -- Ready to submit!")
    print("=" * 60)
    sys.exit(0)

"""Debug server step error with detailed traceback."""
import requests, json, sys
import traceback

BASE = "http://localhost:7860"

# First reset
requests.post(f"{BASE}/reset", json={"task_id": "single_service_crash", "seed": 42})

# Test step
r = requests.post(f"{BASE}/step", json={
    "action": {"action_type": "CHECK_LOGS", "target_service": "cache"}
})
print(f"status: {r.status_code}")
print(f"headers: {dict(r.headers)}")
print(f"text: {r.text[:1000]}")

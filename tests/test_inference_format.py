"""
test_inference_format.py — Smoke test verifying [START]/[STEP]/[END] format.
Run: python test_inference_format.py
"""
import sys
import os
import io
import unittest
from unittest.mock import MagicMock, patch

# Add root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("API_BASE_URL", "https://router.huggingface.co/v1")
os.environ.setdefault("HF_TOKEN", "dummy_token_for_testing")
os.environ.setdefault("MODEL_NAME", "test-model")

call_count = [0]

def _mock_create(*args, **kwargs):
    """Return a deterministic optimal sequence of actions for task 1."""
    c = call_count[0]
    call_count[0] += 1
    actions = [
        '{"action_type": "CHECK_LOGS", "target_service": "cache"}',
        '{"action_type": "DIAGNOSE", "root_cause_id": "cache_oom"}',
        '{"action_type": "CLEAR_CACHE"}',
    ]
    content = actions[c % len(actions)]
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_log_format():
    """Verify [START], [STEP], and [END] lines appear in stdout."""
    captured = io.StringIO()

    with patch("openai.resources.chat.completions.Completions.create", side_effect=_mock_create):
        # Lazy import after env vars are set
        from inference import run_task, LocalEnvWrapper
        from openai import OpenAI

        client = OpenAI(base_url="https://dummy.example.com/v1", api_key="dummy")
        env = LocalEnvWrapper()

        # Redirect stdout to capture log lines
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            score = run_task(client, env, "single_service_crash", seed=42)
        finally:
            sys.stdout = old_stdout

    output = captured.getvalue()
    lines = output.strip().split("\n")

    print("=== Captured output ===")
    for line in lines:
        print(f"  {line}")

    # Assertions
    start_lines = [l for l in lines if l.startswith("[START]")]
    step_lines  = [l for l in lines if l.startswith("[STEP]")]
    end_lines   = [l for l in lines if l.startswith("[END]")]

    assert len(start_lines) == 1, f"Expected 1 [START] line, got {len(start_lines)}"
    assert len(step_lines) >= 1,  f"Expected >= 1 [STEP] lines, got {len(step_lines)}"
    assert len(end_lines) == 1,   f"Expected 1 [END] line, got {len(end_lines)}"

    # Validate [START] format
    assert "task=single_service_crash" in start_lines[0], f"Bad [START]: {start_lines[0]}"
    assert "seed=42" in start_lines[0], f"Bad [START]: {start_lines[0]}"

    # Validate [STEP] format
    for step_line in step_lines:
        assert "step=" in step_line, f"Bad [STEP]: {step_line}"
        assert "action=" in step_line, f"Bad [STEP]: {step_line}"
        assert "reward=" in step_line, f"Bad [STEP]: {step_line}"
        assert "done=" in step_line, f"Bad [STEP]: {step_line}"

    # Validate [END] format
    assert "task=single_service_crash" in end_lines[0], f"Bad [END]: {end_lines[0]}"
    assert "score=" in end_lines[0], f"Bad [END]: {end_lines[0]}"
    assert "steps=" in end_lines[0], f"Bad [END]: {end_lines[0]}"

    # Score in range
    assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    print("\n✅ All format assertions passed!")
    print(f"   Score: {score:.4f}")
    print(f"   [START] lines : {len(start_lines)}")
    print(f"   [STEP] lines  : {len(step_lines)}")
    print(f"   [END] lines   : {len(end_lines)}")


if __name__ == "__main__":
    test_log_format()

"""
client.py — OpenEnv-compatible client for IncidentCommander.

Uses openenv.core.EnvClient (WebSocket-based) matching the finalist pattern.
Falls back to a plain requests-based client if openenv is not installed.

Usage:
    from client import IncidentCommanderClient

    # OpenEnv client (recommended — WebSocket)
    with IncidentCommanderClient(base_url="https://your-space.hf.space").sync() as env:
        result = env.reset()
        print(result.observation.incident_report)
        # Use the new response-based action
        result = env.step(IncidentCommanderAction(response="The cache service is OOM. Fixed."))
        print(result.reward)
"""

from typing import Dict, Optional, Any

# ---------------------------------------------------------------------------
# OpenEnv-compatible client (WebSocket-based, matches finalist pattern)
# ---------------------------------------------------------------------------

try:
    from openenv.core import EnvClient
    from openenv.core.client_types import StepResult
    from openenv.core.env_server.types import State

    from models import IncidentCommanderAction, IncidentCommanderObservation

    class IncidentCommanderClient(
        EnvClient[IncidentCommanderAction, IncidentCommanderObservation, State]
    ):
        """
        OpenEnv WebSocket client for IncidentCommander.

        Connects via WebSocket to a running environment server.

        Example:
            >>> with IncidentCommanderClient(base_url="http://localhost:7860").sync() as env:
            ...     result = env.reset()
            ...     print(result.observation.incident_report)
        """

        def _step_payload(self, action: IncidentCommanderAction) -> Dict:
            """Convert action to JSON payload."""
            return {"response": action.response}

        def _parse_result(self, payload: Dict) -> StepResult[IncidentCommanderObservation]:
            """Parse server response into StepResult."""
            obs_data = payload.get("observation", {})
            observation = IncidentCommanderObservation(
                incident_report=obs_data.get("incident_report", ""),
                task_id=obs_data.get("task_id", ""),
                step_number=obs_data.get("step_number", 0),
                max_steps=obs_data.get("max_steps", 10),
                resolved_services=obs_data.get("resolved_services", []),
                total_reward=obs_data.get("total_reward", 0.0),
                feedback=obs_data.get("feedback", ""),
                done=payload.get("done", False),
                reward=payload.get("reward", 0.0),
            )
            return StepResult(
                observation=observation,
                reward=payload.get("reward", 0.0),
                done=payload.get("done", False),
            )

        def _parse_state(self, payload: Dict) -> State:
            """Parse server response into State."""
            return State(
                episode_id=payload.get("episode_id", ""),
                step_count=payload.get("step_count", 0),
            )

except ImportError:
    # ---------------------------------------------------------------------------
    # Fallback: plain requests-based client (when openenv is not installed)
    # ---------------------------------------------------------------------------
    import requests

    class IncidentCommanderClient:  # type: ignore[no-redef]
        """
        Plain HTTP client for IncidentCommander (fallback, no openenv required).

        Connects to a running FastAPI server (local or on HuggingFace).
        """

        def __init__(self, base_url: str = "http://localhost:7860"):
            self.base_url = base_url.rstrip("/")

        def health(self) -> Dict:
            """Check if the environment server is healthy."""
            return requests.get(f"{self.base_url}/health").json()

        def reset(self, task_id: str = "single_service_crash", seed: int = 42) -> Dict:
            """Start a new episode. Returns the initial observation."""
            payload = {"task_id": task_id, "seed": seed}
            resp = requests.post(f"{self.base_url}/reset", json=payload)
            resp.raise_for_status()
            return resp.json()

        def step(self, action: Dict[str, Any]) -> Dict:
            """Submit an action and get the next observation, reward, and done flag."""
            resp = requests.post(f"{self.base_url}/step", json=action)
            resp.raise_for_status()
            return resp.json()

        def state(self) -> Dict:
            """Get the full internal state (ground truth)."""
            return requests.get(f"{self.base_url}/state").json()

        def tasks(self) -> Dict:
            """List available tasks."""
            return requests.get(f"{self.base_url}/tasks").json()


if __name__ == "__main__":
    # Quick smoke-test
    import sys
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:7860"
    client = IncidentCommanderClient(base_url=base_url)
    print("Tasks:", client.tasks() if hasattr(client, "tasks") else "N/A")

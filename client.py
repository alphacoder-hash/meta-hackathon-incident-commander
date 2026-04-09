import requests
from typing import Dict, List, Optional, Any
from pydantic import BaseModel

class IncidentCommanderClient:
    """
    Python client for the IncidentCommander OpenEnv.
    Connects to a running FastAPI server (local or on HuggingFace).
    """

    def __init__(self, base_url: str = "http://localhost:7860"):
        self.base_url = base_url.rstrip("/")

    def health(self) -> Dict:
        """Check if the environment server is healthy."""
        return requests.get(f"{self.base_url}/health").json()

    def info(self) -> Dict:
        """Get environment metadata and task info."""
        return requests.get(f"{self.base_url}/info").json()

    def reset(self, task_id: str = "single_service_crash", seed: int = 42) -> Dict:
        """
        Start a new episode.
        Returns the initial observation.
        """
        payload = {"task_id": task_id, "seed": seed}
        resp = requests.post(f"{self.base_url}/reset", json=payload)
        resp.raise_for_status()
        return resp.json()

    def step(self, action: Dict[str, Any]) -> Dict:
        """
        Submit an action and get the next observation, reward, and done flag.
        Example action: {"action_type": "CHECK_LOGS", "target_service": "cache"}
        """
        resp = requests.post(f"{self.base_url}/step", json=action)
        resp.raise_for_status()
        return resp.json()

    def state(self) -> Dict:
        """Get the full internal state (ground truth)."""
        return requests.get(f"{self.base_url}/state").json()

    def grade(self) -> Dict:
        """Get the final episode score (0.0-1.0)."""
        return requests.get(f"{self.base_url}/grade").json()

if __name__ == "__main__":
    # Example usage
    client = IncidentCommanderClient()
    print("Health:", client.health())
    
    print("\nStarting episode...")
    obs = client.reset(task_id="single_service_crash")
    print(f"Incident ID: {obs['incident_id']}")
    
    print("\nTaking action: CHECK_LOGS cache")
    result = client.step({"action_type": "CHECK_LOGS", "target_service": "cache"})
    print(f"Reward: {result['reward']}")
    print(f"Done: {result['done']}")

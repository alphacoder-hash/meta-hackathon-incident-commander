"""
incident_commander_env — Public API.

Usage:
    from incident_commander_env import IncidentCommanderEnv, IncidentAction, ActionType
"""
import sys
import os

# The actual module files live at the project root (one level up from this package).
# Ensure the root is on sys.path so imports work regardless of how this package
# is invoked (e.g. `python -m incident_commander_env`, `from incident_commander_env import ...`).
_pkg_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.dirname(_pkg_dir)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

from environment import IncidentCommanderEnv  # noqa: E402
from models import (  # noqa: E402
    ActionType,
    Alert,
    IncidentAction,
    IncidentObservation,
    IncidentState,
    ResetResult,
    ServiceStatus,
    StepResult,
)

__all__ = [
    "IncidentCommanderEnv",
    "IncidentAction",
    "ActionType",
    "Alert",
    "IncidentObservation",
    "IncidentState",
    "ResetResult",
    "ServiceStatus",
    "StepResult",
]

__version__ = "1.0.0"

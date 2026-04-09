"""
simulator.py — Infrastructure tick engine for IncidentCommander.

The simulator maintains the health state of every service and propagates
failures through the dependency graph each step.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services import ALL_SERVICES, DEPENDENCY_GRAPH, REVERSE_GRAPH, CASCADE_ORDER, ServiceSpec
from models import ServiceStatus


# ---------------------------------------------------------------------------
# Runtime service state
# ---------------------------------------------------------------------------

@dataclass
class ServiceState:
    spec: ServiceSpec
    healthy: bool = True
    latency_ms: float = 0.0
    error_rate: float = 0.0
    cpu_pct: float = 0.0
    memory_pct: float = 0.0
    restarts: int = 0
    # Memory leak grows over steps
    memory_leak_per_step: float = 0.0

    def to_status(self) -> ServiceStatus:
        return ServiceStatus(
            name=self.spec.name,
            healthy=self.healthy,
            latency_ms=round(self.latency_ms, 1),
            error_rate=round(self.error_rate, 4),
            cpu_pct=round(self.cpu_pct, 1),
            memory_pct=round(self.memory_pct, 1),
            restarts=self.restarts,
            last_deployed=self.spec.last_deployed,
        )


class InfrastructureSimulator:
    """
    Simulates the infrastructure state across a whole episode.
    Call `reset()` to start a new scenario, then `tick()` each step.
    """

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self._states: Dict[str, ServiceState] = {}
        self._root_cause_id: str = ""
        self._affected: List[str] = []
        self._chaos: bool = False
        self._step: int = 0
        # Tracks per-step health of each service (True=healthy, False=down)
        self.uptime_history: Dict[str, List[bool]] = {}

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def reset(
        self,
        root_cause_id: str,
        affected_services: List[str],
        chaos: bool = False,
    ) -> None:
        self._root_cause_id = root_cause_id
        self._affected = affected_services
        self._chaos = chaos
        self._step = 0

        # Initialise all services to their healthy baseline
        self._states = {}
        for name, spec in ALL_SERVICES.items():
            s = ServiceState(spec=spec)
            s.latency_ms = spec.base_latency_ms
            s.error_rate = spec.base_error_rate
            s.cpu_pct = spec.base_cpu_pct
            s.memory_pct = spec.base_memory_pct
            self._states[name] = s

        # Inject the initial fault
        self._inject_fault(root_cause_id, affected_services)

        # Initialise uptime history
        self.uptime_history = {name: [] for name in ALL_SERVICES}
        self._record_uptime()

    def _inject_fault(self, root_cause_id: str, affected_services: List[str]) -> None:
        """Set the initial degraded state based on root cause."""
        if root_cause_id == "cache_oom":
            s = self._states["cache"]
            s.healthy = False
            s.memory_pct = 99.8
            s.latency_ms = self._states["cache"].spec.failure_latency_ms
            s.error_rate = self._states["cache"].spec.failure_error_rate
            s.cpu_pct = 50.0

        elif root_cause_id == "database_overload":
            db = self._states["database"]
            db.healthy = False
            db.cpu_pct = 99.0
            db.latency_ms = db.spec.failure_latency_ms
            db.error_rate = db.spec.failure_error_rate
            db.memory_pct = 85.0

        elif root_cause_id == "payment_bad_deploy":
            p = self._states["payment"]
            p.healthy = False
            p.latency_ms = p.spec.failure_latency_ms
            p.error_rate = 0.94
            p.cpu_pct = 5.0   # crash-looping, barely any CPU
            p.memory_pct = 10.0
            p.restarts = 8
            p.spec = ServiceSpec(
                name=p.spec.name,
                base_latency_ms=p.spec.base_latency_ms,
                base_error_rate=p.spec.base_error_rate,
                base_cpu_pct=p.spec.base_cpu_pct,
                base_memory_pct=p.spec.base_memory_pct,
                critical=p.spec.critical,
                last_deployed="2026-03-28T09:47:00Z",  # bad deployment time
                failure_latency_ms=p.spec.failure_latency_ms,
                failure_error_rate=p.spec.failure_error_rate,
            )

        elif root_cause_id == "payment_memory_leak":
            p = self._states["payment"]
            p.healthy = True   # starts healthy (silent degradation)
            p.latency_ms = 210.0   # slightly elevated
            p.error_rate = 0.01
            p.memory_leak_per_step = 2.5   # % per step

        # Propagate cascades for affected services
        self._propagate_cascades()

    # ------------------------------------------------------------------
    # Tick — called each step
    # ------------------------------------------------------------------

    def tick(self, chaos_event: bool = False) -> None:
        """Advance one step: propagate cascades, apply memory leak, chaos."""
        self._step += 1
        self._apply_memory_leak()
        self._propagate_cascades()

        if self._chaos and chaos_event:
            self._inject_chaos()

        # Add small jitter to all healthy services to feel realistic
        for name, s in self._states.items():
            if s.healthy:
                jitter = self.rng.uniform(-0.05, 0.05)
                s.latency_ms = max(1.0, s.latency_ms * (1 + jitter))

        self._record_uptime()

    def _apply_memory_leak(self) -> None:
        for name, s in self._states.items():
            if s.memory_leak_per_step > 0:
                s.memory_pct = min(99.9, s.memory_pct + s.memory_leak_per_step)
                # After memory pct crosses 90%, latency degrades
                if s.memory_pct > 90.0:
                    s.latency_ms = min(
                        s.spec.failure_latency_ms,
                        s.latency_ms * 1.15,
                    )
                    s.error_rate = min(0.5, s.error_rate * 1.1)
                # At 99%, service is effectively down
                if s.memory_pct >= 99.0:
                    s.healthy = False
                    s.error_rate = 0.95

    def _propagate_cascades(self) -> None:
        """Propagate degradation through the dependency graph."""
        for svc in CASCADE_ORDER:
            s = self._states[svc]
            degraded_deps = [
                dep for dep in DEPENDENCY_GRAPH[svc]
                if not self._states[dep].healthy
            ]
            if not degraded_deps:
                # If all deps are healthy, partially recover (up to baseline × 1.5)
                if s.healthy and s.latency_ms > s.spec.base_latency_ms * 1.5:
                    s.latency_ms = max(s.spec.base_latency_ms, s.latency_ms * 0.9)
                continue

            # Degrade based on fraction of failed dependencies
            dep_count = len(DEPENDENCY_GRAPH[svc])
            fail_fraction = len(degraded_deps) / dep_count if dep_count > 0 else 0

            if fail_fraction >= 0.5:
                s.healthy = False
                s.latency_ms = s.spec.failure_latency_ms
                s.error_rate = min(s.spec.failure_error_rate, 0.98)
                s.cpu_pct = min(s.cpu_pct + 10, s.spec.failure_cpu_pct)
            elif fail_fraction > 0:
                # Partial degradation
                s.latency_ms = min(
                    s.spec.failure_latency_ms,
                    s.latency_ms + (s.spec.failure_latency_ms - s.spec.base_latency_ms) * fail_fraction * 0.6,
                )
                s.error_rate = min(
                    0.8,
                    s.error_rate + fail_fraction * 0.4,
                )

    def _inject_chaos(self) -> None:
        """Randomly degrade a healthy non-critical service for one step."""
        candidates = [
            name for name, s in self._states.items()
            if s.healthy and not s.spec.critical
        ]
        if not candidates:
            return
        target = self.rng.choice(candidates)
        s = self._states[target]
        s.latency_ms = s.latency_ms * self.rng.uniform(1.5, 3.0)

    def _record_uptime(self) -> None:
        for name, s in self._states.items():
            self.uptime_history[name].append(s.healthy)

    # ------------------------------------------------------------------
    # Remediation actions (called by environment.py)
    # ------------------------------------------------------------------

    def restart_service(self, service: str) -> bool:
        """Restart a service. Returns True if it was actually failing."""
        s = self._states.get(service)
        if s is None:
            return False
        was_unhealthy = not s.healthy
        spec = ALL_SERVICES[service]

        # Don't fix the root cause via restart alone (must use correct action)
        if service in self._affected and self._root_cause_id in (
            "cache_oom",
        ):
            # After restart, clears the OOM — cache comes back up
            s.healthy = True
            s.memory_pct = spec.base_memory_pct
            s.latency_ms = spec.base_latency_ms
            s.error_rate = spec.base_error_rate
            s.cpu_pct = spec.base_cpu_pct
        elif service in self._affected and self._root_cause_id == "payment_bad_deploy":
            # Restart doesn't fix bad deploy — crash-loops again
            s.restarts += 1
        else:
            # Healthy restart heals secondary cascades
            s.healthy = True
            s.latency_ms = spec.base_latency_ms * 1.1
            s.error_rate = spec.base_error_rate
            s.cpu_pct = spec.base_cpu_pct * 1.05

        return was_unhealthy

    def rollback_service(self, service: str) -> bool:
        """Rollback a service deployment. Fixes bad_deploy root cause."""
        s = self._states.get(service)
        if s is None:
            return False
        if service in self._affected and self._root_cause_id == "payment_bad_deploy":
            spec = ALL_SERVICES[service]
            s.healthy = True
            s.latency_ms = spec.base_latency_ms
            s.error_rate = spec.base_error_rate
            s.cpu_pct = spec.base_cpu_pct
            s.memory_pct = spec.base_memory_pct
            s.restarts = 0
            self._affected = [a for a in self._affected if a != service]
            return True
        return False

    def clear_cache(self) -> bool:
        """Clear cache. Fixes cache_oom root cause."""
        if self._root_cause_id == "cache_oom":
            s = self._states["cache"]
            spec = ALL_SERVICES["cache"]
            s.healthy = True
            s.memory_pct = spec.base_memory_pct
            s.latency_ms = spec.base_latency_ms
            s.error_rate = spec.base_error_rate
            self._affected = [a for a in self._affected if a != "cache"]
            return True
        return False

    def scale_up(self, service: str) -> bool:
        """Scale up a service. Partially helps with db overload."""
        s = self._states.get(service)
        if s is None:
            return False
        if service == "database" and self._root_cause_id == "database_overload":
            s.cpu_pct = max(s.cpu_pct * 0.6, 60.0)
            s.latency_ms = max(s.spec.base_latency_ms * 2, s.latency_ms * 0.5)
            s.error_rate = max(0.1, s.error_rate * 0.4)
            if s.latency_ms <= s.spec.base_latency_ms * 3:
                s.healthy = True
                self._affected = [a for a in self._affected if a != service]
            return True
        return False

    def failover_db(self) -> bool:
        """Failover to DB replica. Fixes database_overload root cause."""
        if self._root_cause_id == "database_overload":
            s = self._states["database"]
            spec = ALL_SERVICES["database"]
            s.cpu_pct = spec.base_cpu_pct * 1.2
            s.latency_ms = spec.base_latency_ms * 1.5
            s.error_rate = spec.base_error_rate * 2
            s.healthy = True
            self._affected = [a for a in self._affected if a != "database"]
            return True
        return False

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_statuses(self) -> List[ServiceStatus]:
        return [s.to_status() for s in self._states.values()]

    def get_healthy_services(self) -> List[str]:
        return [n for n, s in self._states.items() if s.healthy]

    def get_failing_services(self) -> List[str]:
        return [n for n, s in self._states.items() if not s.healthy]

    def is_resolved(self) -> bool:
        """True if all originally affected services are healthy again."""
        return all(self._states[svc].healthy for svc in self._affected)

    @property
    def affected_services(self) -> List[str]:
        return list(self._affected)

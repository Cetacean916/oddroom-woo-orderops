from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ACTION_CONTRACT_VERSION = "1.0.0"

PrerequisiteState = Literal[
    "READY",
    "MISSING_PYTHON",
    "MISSING_RUNTIME",
    "RUNTIME_STOPPED",
    "MISSING_COMPOSE",
]
RuntimeState = Literal[
    "FIRST_RUN",
    "PORT_OCCUPIED",
    "STOPPED",
    "FAILED_HEALTH",
    "ALREADY_RUNNING",
    "RERUN_READY",
]


@dataclass(frozen=True)
class PrerequisiteFacts:
    python_ready: bool
    runtime_cli_present: bool
    runtime_daemon_ready: bool
    compose_ready: bool


@dataclass(frozen=True)
class RuntimeFacts:
    package_state_exists: bool
    requested_port_available: bool
    services_running: bool
    health_ready: bool
    start_requested: bool = False


def classify_prerequisites(facts: PrerequisiteFacts) -> PrerequisiteState:
    """Return the first actionable prerequisite state in deterministic order."""
    if not facts.python_ready:
        return "MISSING_PYTHON"
    if not facts.runtime_cli_present:
        return "MISSING_RUNTIME"
    if not facts.runtime_daemon_ready:
        return "RUNTIME_STOPPED"
    if not facts.compose_ready:
        return "MISSING_COMPOSE"
    return "READY"


def classify_runtime(facts: RuntimeFacts) -> RuntimeState:
    """Classify every required PKG-005 launcher branch without OS-specific behavior."""
    if not facts.package_state_exists:
        if not facts.requested_port_available:
            return "PORT_OCCUPIED"
        return "FIRST_RUN"
    if not facts.services_running:
        return "STOPPED"
    if not facts.health_ready:
        return "FAILED_HEALTH"
    if facts.start_requested:
        return "RERUN_READY"
    return "ALREADY_RUNNING"


def recovery_action(state: PrerequisiteState | RuntimeState) -> str:
    return {
        "READY": "START_OR_OPEN_HUB",
        "MISSING_PYTHON": "OPEN_OFFICIAL_PYTHON_INSTALLER",
        "MISSING_RUNTIME": "OPEN_SUPPORTED_RUNTIME_INSTALLER",
        "RUNTIME_STOPPED": "OPEN_RUNTIME_AND_RECHECK",
        "MISSING_COMPOSE": "OPEN_SUPPORTED_RUNTIME_INSTALLER",
        "FIRST_RUN": "START",
        "PORT_OCCUPIED": "SELECT_FREE_LOOPBACK_PORT",
        "STOPPED": "RESTART",
        "FAILED_HEALTH": "RECOVER_AND_EXPORT_DIAGNOSTICS",
        "ALREADY_RUNNING": "OPEN_READY_TARGETS",
        "RERUN_READY": "RECONNECT_EXISTING_RUNTIME",
    }[state]

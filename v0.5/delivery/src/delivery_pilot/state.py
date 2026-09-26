"""Tier A mission state, transitions, and compare-and-set persistence."""

from __future__ import annotations

import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, digest, load_strict
from .contracts import MISSION_TERMINAL_OUTCOMES


class CasMismatch(RuntimeError):
    pass


class TransitionError(ValueError):
    pass


PHASES = (
    "authorized", "build", "slice-check", "qa", "freeze", "candidate-readiness",
    "final-check", "pr-ready", "handback", "merge", "deploy", "canary", "recovery",
    "closeout", "retro", "cleanup", "archive-ready", "externally-archived", "complete",
)
STATUSES = (
    "running", "parked", "waiting_taste", "waiting_safety", "waiting_capacity",
    "ceiling", "errored", "cancelling", "intervention_required", "complete", "cancelled",
)
WAKE_PREFIX = {
    "parked": ("manual_resume", "external_event:"),
    "waiting_taste": ("answer:",),
    "waiting_safety": ("safety_disposition:", "operation_observed:"),
    "waiting_capacity": ("capacity_after:",),
    "ceiling": ("ceiling_extension:", "cancel:"),
    "errored": ("recovery_proof:", "cancel:"),
    "cancelling": ("operations_terminal",),
    "intervention_required": ("safety_disposition:",),
}
ALLOWED = {
    "authorized": {"build"},
    "build": {"slice-check", "qa", "build"},
    "slice-check": {"build", "qa", "slice-check"},
    "qa": {"build", "freeze", "qa"},
    "freeze": {"build", "candidate-readiness", "final-check"},
    "candidate-readiness": {"candidate-readiness", "build", "final-check"},
    "final-check": {"final-check", "build", "pr-ready"},
    "pr-ready": {"handback", "merge"},
    "handback": {"complete"},
    "merge": {"deploy", "closeout"},
    "deploy": {"canary", "closeout"},
    "canary": {"closeout", "recovery"},
    "recovery": {"closeout", "recovery"},
    "closeout": {"retro"},
    "retro": {"cleanup"},
    "cleanup": {"archive-ready"},
    "archive-ready": {"externally-archived"},
    "externally-archived": {"complete"},
    "complete": set(),
}

STATUS_PHASES = {
    "waiting_taste": {"build", "slice-check", "qa", "candidate-readiness", "final-check"},
    "waiting_capacity": {"slice-check", "candidate-readiness", "final-check"},
    "intervention_required": {"deploy", "canary", "recovery"},
}


def _valid_wake(status: str, guard: str | None) -> bool:
    if status in {"running", "complete", "cancelled"}:
        return guard is None
    return guard is not None and any(guard == prefix or guard.startswith(prefix) for prefix in WAKE_PREFIX[status])


def transition(
    value: dict[str, Any],
    phase: str,
    status: str = "running",
    wake_guard: str | None = None,
    terminal_outcome: str | None = None,
) -> dict[str, Any]:
    aggregate = value["aggregate"]
    current = aggregate["phase"]
    terminal_cancellation = (
        phase == "complete"
        and status == "cancelled"
        and terminal_outcome == "cancelled"
    )
    cancellation_ready = (
        current != "complete"
        and aggregate.get("status") == "cancelling"
        and aggregate.get("wake_guard") == "operations_terminal"
    )
    if phase not in PHASES or status not in STATUSES:
        raise TransitionError("unknown phase or status")
    if phase != current and phase not in ALLOWED.get(current, set()) and not (
        terminal_cancellation and cancellation_ready
    ):
        raise TransitionError(f"illegal transition {current} -> {phase}")
    if terminal_cancellation and not cancellation_ready:
        raise TransitionError(
            "terminal cancellation requires cancelling status with operations_terminal wake guard"
        )
    if status in {"complete", "cancelled"} and phase != "complete":
        raise TransitionError("terminal status requires complete phase")
    allowed_phases = STATUS_PHASES.get(status)
    if allowed_phases is not None and phase not in allowed_phases:
        raise TransitionError(f"{status} is not valid during {phase}")
    if status == "cancelled" and any(
        operation.get("status") not in {"observed_succeeded", "observed_failed", "cancelled"}
        for operation in value.get("operations", [])
    ):
        raise TransitionError("cancellation cannot complete with unresolved operations")
    if phase == "complete" and status not in {"complete", "cancelled"}:
        status = "complete"
    if phase == "complete":
        if terminal_outcome not in MISSION_TERMINAL_OUTCOMES:
            raise TransitionError("complete phase requires a recognized terminal outcome")
        if (status == "cancelled") != (terminal_outcome == "cancelled"):
            raise TransitionError("terminal status and outcome disagree")
    elif terminal_outcome is not None:
        raise TransitionError("terminal outcome requires complete phase")
    if not _valid_wake(status, wake_guard):
        raise TransitionError(f"invalid wake guard for {status}")
    result = deepcopy(value)
    result["aggregate"].update({
        "phase": phase,
        "status": status,
        "terminal_outcome": terminal_outcome,
        "wake_guard": wake_guard,
    })
    validate_mission_invariants(result)
    return result


def validate_mission_invariants(value: dict[str, Any]) -> None:
    slices = value.get("slices", {})
    mutable = [name for name, item in slices.items() if item.get("status") in {"building", "fixing"}]
    if len(mutable) > 1:
        raise TransitionError(f"multiple mutable slices: {mutable}")
    aggregate = value.get("aggregate", {})
    phase = aggregate.get("phase")
    status = aggregate.get("status")
    if phase not in PHASES or status not in STATUSES:
        raise TransitionError("unknown aggregate phase or status")
    if phase == "complete" and status not in {"complete", "cancelled"}:
        raise TransitionError("complete phase requires terminal status")
    if phase == "complete":
        outcome = aggregate.get("terminal_outcome")
        if outcome not in MISSION_TERMINAL_OUTCOMES:
            raise TransitionError("complete phase requires a recognized terminal outcome")
        if (status == "cancelled") != (outcome == "cancelled"):
            raise TransitionError("terminal status and outcome disagree")
    elif status in {"complete", "cancelled"} or aggregate.get("terminal_outcome") is not None:
        raise TransitionError("terminal outcome requires complete phase")


@dataclass(frozen=True)
class Snapshot:
    value: dict[str, Any]
    digest: str


class MissionStore:
    def __init__(self, path: Path):
        self.path = path

    def create(self, value: dict[str, Any]) -> Snapshot:
        if self.path.exists():
            raise CasMismatch("mission already exists")
        validate_mission_invariants(value)
        self._write(value)
        return Snapshot(value, digest(value))

    def read(self) -> Snapshot:
        value = load_strict(self.path.read_bytes())
        return Snapshot(value, digest(value))

    def write(self, expected_digest: str, value: dict[str, Any], updated_at: str) -> Snapshot:
        current = self.read()
        if current.digest != expected_digest:
            raise CasMismatch("mission digest moved")
        result = deepcopy(value)
        result["revision"] = current.value["revision"] + 1
        result["prior_digest"] = current.digest
        result["updated_at"] = updated_at
        validate_mission_invariants(result)
        self._write(result)
        return Snapshot(result, digest(result))

    def claim(self, expected_digest: str, workspace_id: str, session_id: str, updated_at: str) -> Snapshot:
        current = self.read()
        result = deepcopy(current.value)
        result["controller"] = {
            "generation": current.value["controller"]["generation"] + 1,
            "workspace_id": workspace_id,
            "session_id": session_id,
        }
        return self.write(expected_digest, result, updated_at)

    def _write(self, value: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix=self.path.name, dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(canonical_bytes(value) + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(raw_path, self.path)
        finally:
            if os.path.exists(raw_path):
                os.unlink(raw_path)

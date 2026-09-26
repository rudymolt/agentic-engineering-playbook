"""Versioned, coordinator-only admission for the interim watchdog.

This is deliberately a policy seam: it parses a title and durable checkpoint,
records no worker command, and returns only ``resume-coordinator`` or a
truthful refusal.  The coordinator owns reconciliation and worker dispatch.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol

from .canonical import digest
from .interim import InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, validate_record
from .interim_recovery import InterimRecoveryCoordinator, RecoveryAdapter, reserve_wake_intent, wake_operation_id

PREFIX = "UNATTENDED_INTERIM_V1"
MODE = "interim-coordinator"


def _fail(message: str) -> None:
    raise InterimError("interim watchdog " + message)


def parse_opt_in(title: object) -> dict[str, str] | None:
    """Parse the strict v1 title; leave legacy titles to their legacy parser."""
    if not isinstance(title, str):
        _fail("title must be text")
    if not title.startswith(PREFIX):
        return None
    parts = title.split()
    if len(parts) != 6 or parts[0] != PREFIX:
        _fail("v1 title has unknown or missing fields")
    result: dict[str, str] = {}
    for part in parts[1:]:
        if part.count("=") != 1:
            _fail("v1 title is malformed")
        name, value = part.split("=", 1)
        if name not in {"run", "mode", "checkpoint", "progress", "hard_limits"} or not value or name in result:
            _fail("v1 title has unknown or duplicate fields")
        result[name] = value
    if set(result) != {"run", "mode", "checkpoint", "progress", "hard_limits"}:
        _fail("v1 title has unknown or missing fields")
    return result


def wake_id(run_id: str, event_id: str) -> str:
    """Derive one logical wake from its immutable run and stable host event ID."""
    if not isinstance(event_id, str) or not event_id:
        _fail("event ID must be stable and non-empty")
    return "watch-" + digest({"run": run_id, "event": event_id, "protocol": 1})[7:23]


def _terminal(record: dict[str, Any]) -> bool:
    recovery = record.get("recovery", {})
    return (recovery.get("status") in {"stopping", "stopped", "uncertain"}
            or record["state"]["next_action"] == "review-ready"
            or record.get("repair", {}).get("status") in {"stuck", "handback"})


def _operation(record: dict[str, Any], operation_id: str) -> dict[str, Any] | None:
    return next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)


def _unresolved_wake(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return the durable predecessor that blocks a distinct wake admission."""
    return next((item for item in record["usage"]["operations"]
                 if item.get("phase") == "wake" and item.get("status") != "accounted"), None)


def admit(record: object, title: object, session_id: object, event_id: str,
          observation: object, now: datetime | None = None) -> dict[str, Any]:
    """Return one dispatch-free coordinator resumption decision.

    ``observation`` is a retained host fact with only the small facts this
    policy can safely use.  Pending effects are refused before a new wake is
    admitted; the existing recovery seam later reconciles exact operation IDs.
    """
    record = validate_record(record)
    opt_in = parse_opt_in(title)
    if opt_in is None:
        return {"action": "ignore", "reason": "legacy-or-no-interim-opt-in"}
    approval = record["approval"]
    expected = {"run": approval["run_id"], "mode": MODE,
                "checkpoint": approval["checkpoint"]["ref"],
                "progress": approval["progress_checkpoint_policy"],
                "hard_limits": "none" if approval["hard_limits"] == "none" else "selected"}
    if opt_in != expected:
        return {"action": "ignore", "reason": "interim-identity-mismatch"}
    if session_id != approval["coordinator"]["session_id"]:
        return {"action": "ignore", "reason": "not-approved-coordinator"}
    if _terminal(record):
        return {"action": "refuse", "reason": "terminal-or-stopping-run"}
    if not isinstance(observation, dict) or set(observation) != {"current_turn", "pending_messages", "pending_effects"}:
        _fail("host observation has unknown or missing fields")
    exact_wake_id = wake_id(approval["run_id"], event_id)
    exact_operation = _operation(record, wake_operation_id(record, exact_wake_id))
    # A durable exact wake is already admitted. It must remain observable even
    # after that reservation exhausts a chosen cap or its deadline passes.
    if exact_operation is not None:
        return {"action": "resume-coordinator", "wake_id": exact_wake_id,
                "session_id": approval["coordinator"]["session_id"], "dispatch_worker": False,
                "next": "coordinator-must-reconcile-durable-state"}
    if observation["current_turn"] != "interrupted":
        return {"action": "refuse", "reason": "current-turn-not-interrupted"}
    if observation["pending_messages"] is not False or observation["pending_effects"] is not False:
        return {"action": "refuse", "reason": "pending-message-or-effect"}
    predecessor = _unresolved_wake(record)
    if predecessor is not None:
        return {"action": "refuse", "reason": "prior-wake-reconciliation-required",
                "operation_id": predecessor["id"]}
    now = now or datetime.now(timezone.utc)
    limits = approval["hard_limits"]
    if limits != "none":
        if "deadline_at" in limits and now >= datetime.fromisoformat(limits["deadline_at"].replace("Z", "+00:00")):
            return {"action": "refuse", "reason": "selected-deadline-reached"}
        # Existing durable launches, including pending effects, consume slots.
        if len(record["usage"].get("launches", [])) >= limits.get("dispatch_max", 2**63 - 1):
            return {"action": "refuse", "reason": "selected-dispatch-cap-reached"}
    # The host event ID is the stable correlation for one delivery.  It chooses
    # no authority: admission remains bound to immutable run/coordinator policy.
    return {"action": "resume-coordinator", "wake_id": wake_id(approval["run_id"], event_id),
            "session_id": approval["coordinator"]["session_id"], "dispatch_worker": False,
            "next": "coordinator-must-reconcile-durable-state"}


def reserve_wake(record: object, title: object, session_id: object, event_id: str,
                 observation: object, now: datetime | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create one durable-intent projection before a host wake is sent.

    The caller persists this projection with the checkpoint store's compare and
    set.  A stale second writer therefore loses publication rather than spending
    a second selected slot.  Repeating the same event returns the original
    logical operation and never appends another charge.
    """
    record = validate_record(record)
    decision = admit(record, title, session_id, event_id, observation, now)
    if decision["action"] != "resume-coordinator":
        return record, decision
    operation_id = wake_operation_id(record, decision["wake_id"])
    existing = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
    if existing:
        decision["action"] = "reconcile-coordinator-wake"
        decision["operation_id"] = operation_id
        return record, decision
    reserve_wake_intent(record, decision["wake_id"], now or datetime.now(timezone.utc))
    decision["operation_id"] = operation_id
    return validate_record(record), decision


def reserve_and_persist(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                        title: object, session_id: object, event_id: str, observation: object,
                        now: datetime | None = None) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
    """Atomically publish a wake intent using the existing exact-ref CAS store."""
    projected, decision = reserve_wake(deepcopy(snapshot.value), title, session_id, event_id, observation, now)
    if decision["action"] == "resume-coordinator":
        return store.persist(snapshot, projected), decision
    return snapshot, decision


class WatchdogAdapter(Protocol):
    """The narrow host seam needed after watchdog reservation.

    ``send_wake`` and ``observe`` operate only on the exact durable coordinator
    wake.  They are never worker dispatch surfaces.
    """
    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]: ...
    def send_wake(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def observe(self, operation: dict[str, Any]) -> dict[str, Any]: ...


def resume_and_reconcile(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                         title: object, session_id: object, event_id: str, observation: object,
                         adapter: WatchdogAdapter, now: datetime | None = None) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
    """Persist a coordinator wake before the host call, then reconcile its receipt.

    A newly persisted intent is sent once through ``send_wake``. Timeouts and
    malformed receipts become durable ``reconcile-required`` state. A duplicate
    or reload calls ``observe`` for the same operation ID; it never sends,
    publishes a second intent, launch, or charge.
    """
    reserved, decision = reserve_and_persist(store, snapshot, title, session_id, event_id, observation, now)
    if decision["action"] not in {"resume-coordinator", "reconcile-coordinator-wake"}:
        return reserved, decision
    clock = (lambda: now) if now is not None else None
    coordinator = (InterimRecoveryCoordinator(store, clock=clock, monitor_internal=True)
                   if clock is not None else InterimRecoveryCoordinator(store, monitor_internal=True))
    if decision["action"] == "resume-coordinator":
        return coordinator.send_wake(reserved, decision["wake_id"], adapter), decision
    return coordinator.reconcile_wake(reserved, decision["wake_id"], adapter), decision


def prompt_config() -> dict[str, Any]:
    """Reviewed source configuration; deployment/readback remains an S7 action."""
    return {"version": 1, "title_prefix": PREFIX, "mode": MODE,
            "watchdog_action": "resume-coordinator-only", "worker_dispatch": False,
            "complete_only_for": "whole-run-review-ready", "activation": "documented-only"}

"""Durable deadline cancellation shared by asynchronous repair and stack workers."""
from __future__ import annotations

from copy import deepcopy

from .interim import validate_record
from .interim_coordinator import InterimDispatchError, _at, _deadline_reached, _handback, _receipt


def cancel_expired(store, snapshot, operation_id, adapter, now):
    record = validate_record(snapshot.value)
    operation = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)
    if not _deadline_reached(record, now) or operation["status"] not in {"intent", "reconcile-required"}:
        return snapshot
    observation = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
    if "cancellation_intent" in operation:
        # A lost cancel response is reconciled by whole-run recovery. It never
        # authorizes a repeat cancel effect on this worker-dispatch path.
        return snapshot
    operation["cancellation_intent"] = {"at": _at(now), "reason": "selected deadline reached"}
    operation.setdefault("receipt", {"observation": observation, "transport": "unknown", "worker_state": "unknown", "elapsed_seconds": 0})
    operation["cancellation"] = {"observation": observation, "state": "uncertain"}
    operation["status"] = "cancellation-uncertain"
    if operation["phase"] in {"diagnosis", "repair", "repair-verify"}:
        record["repair"]["status"] = "handback"
    snapshot = store.persist_lifecycle(snapshot, _handback(record, "selected deadline reached; cancellation intent recorded"))
    try:
        cancellation = _receipt(adapter.cancel(deepcopy(operation)), operation)
        if cancellation.get("state") not in {"cancelled", "queued", "uncertain"}:
            raise InterimDispatchError("cancellation state is malformed")
    except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
        cancellation = {"observation": observation, "state": "uncertain", "reason": type(exc).__name__}
    record = validate_record(snapshot.value)
    operation = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)
    operation["cancellation"] = deepcopy(cancellation)
    if cancellation["state"] == "cancelled":
        operation["status"] = "unfinished-cancelled"
    else:
        # Generic S2 portable semantics deliberately treats queued cancellation
        # as uncertain until a terminal observation arrives.
        operation["cancellation"]["state"] = "uncertain"
        operation["cancellation"]["host_state"] = cancellation["state"]
    return store.persist_lifecycle(snapshot, _handback(record, "selected deadline reached; worker cancellation " + cancellation["state"]))

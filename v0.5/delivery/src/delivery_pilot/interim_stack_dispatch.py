"""Accounted asynchronous Verify dispatch for the interim stack policy.

All host effects remain behind the injected worker adapter. Each re-entry polls
an existing UUID operation or reserves one new intent before sending it.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import digest
from .interim import validate_record
from .interim_coordinator import InterimDispatchError, _append, _at, _handback, _limit, _observed, _receipt, _task
from .interim_identity import operation_identities
from .interim_worker_limits import cancel_expired
from .interim_semantics import _expected_id, restack_bound_verify_task, validate_worker_result
from .interim_stack import StackPolicyError, _final_operation_id, _final_phase_evidence, _final_review_evidence, _review_task


FINAL_PHASES = {"stack-final-qa", "stack-final-ci", "stack-final-review"}


def _admission(record, now):
    if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
        return "whole-run recovery state refuses worker dispatch"
    return _limit(record, now)


def _intent(record, operation_id, phase, slice_id, task, now, **context):
    return {"id": operation_id, "phase": phase, "slice": slice_id, "task": deepcopy(task),
            **operation_identities(record["approval"]["run_id"], operation_id, phase),
            "status": "intent", "issued_at": _at(now), "elapsed_seconds": 0,
            "route": {key: record["approval"]["routes"]["verify"][key] for key in ("model", "effort")}, **deepcopy(context)}


def _final_runtime(record, operation, receipt):
    """New dispatched final workers carry the same bounded runtime proof as Verify."""
    runtime = receipt.get("runtime")
    route = record["approval"]["routes"]["verify"]
    tasks = operation["task"]["tasks"]
    if not isinstance(runtime, dict) or set(runtime) != {"model", "effort", "runner", "permissions"}:
        raise StackPolicyError("final worker lacks its complete approved runtime")
    if any(runtime.get(key) != route[key] for key in ("model", "effort")) or any({key: runtime[key] for key in ("runner", "permissions")} != task["runtimes"]["verify"] for task in tasks):
        raise StackPolicyError("final worker runtime differs from approved Verify route/tasks")
    limits = operation["task"]["limits"]
    if type(receipt.get("wall_time_seconds")) is not int or not 0 <= receipt["wall_time_seconds"] <= limits["wall_time_seconds"]:
        raise StackPolicyError("final worker wall time exceeds its bounded task")
    tools = receipt.get("tools")
    if not isinstance(tools, list) or not tools or len(tools) > limits["max_tools"] or any(not isinstance(item, str) or not item for item in tools):
        raise StackPolicyError("final worker tool evidence is missing or unbounded")


def validate_final_worker(record, operation, receipt):
    context = operation["final_context"]
    projected = deepcopy(record)
    projected["stack"]["slices"] = deepcopy(context)
    candidates = [{"slice_id": entry["id"], "candidate": entry["candidate"]} for entry in context]
    if operation["phase"] == "stack-final-review":
        _final_review_evidence(projected, context, candidates, receipt)
    else:
        _final_phase_evidence(projected, context, candidates, operation["phase"].removeprefix("stack-final-"), receipt)
    _final_runtime(record, operation, receipt)


def _terminal(record, operation, receipt):
    if receipt.get("transport") != "accepted" or receipt.get("terminal_turn") is not True or receipt.get("task_success") is not True:
        raise StackPolicyError("stack worker has no accepted structured terminal success")
    if operation["phase"] == "stack-verify":
        task = restack_bound_verify_task(record, operation, operation["task"])
        validate_worker_result(receipt, {**operation, "phase": "verify"}, "verify", record["approval"]["routes"]["verify"], task, operation["candidate"])
    else:
        validate_final_worker(record, operation, receipt)


def _advance(coordinator, snapshot, intent, adapter):
    record = validate_record(snapshot.value)
    if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
        raise StackPolicyError("whole-run recovery state refuses worker continuation")
    operation = next((item for item in record["usage"]["operations"] if item["id"] == intent["id"]), None)
    if operation is None:
        limit = _admission(record, coordinator.clock())
        if limit:
            return coordinator._persist(snapshot, _handback(record, limit))
        operation = intent
        _append(record, operation, launch=True)
        record["state"] = {"next_action": "reconcile-stack-worker", "candidate": deepcopy(operation.get("candidate")), "review": None, "handback": None}
        snapshot = coordinator._persist(snapshot, record)
        record = validate_record(snapshot.value)
        limits = record["approval"]["hard_limits"]
        if limits != "none" and "deadline_at" in limits and _limit(record, coordinator.clock()) == "selected deadline reached":
            return coordinator._persist(snapshot, _handback(record, "selected deadline reached before stack worker send"))
        method = adapter.send
    elif operation["status"] in {"intent", "reconcile-required"}:
        method = adapter.reconcile
    else:
        return snapshot
    try:
        receipt = _receipt(method(deepcopy(operation)), operation)
    except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
        snapshot = coordinator._persist(snapshot, _handback(record, "stack worker requires same-ID reconciliation: " + type(exc).__name__))
        return cancel_expired(coordinator.store, snapshot, operation["id"], adapter, coordinator.clock())
    record = validate_record(snapshot.value)
    current = next(item for item in record["usage"]["operations"] if item["id"] == operation["id"])
    current["receipt"] = deepcopy(receipt)
    current["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
    _observed(record, current["id"])
    if receipt.get("terminal_turn") is not True and (receipt.get("worker_state") in {"queued", "active", "unknown"} or receipt.get("transport") in {"timeout", "unknown"}):
        current["status"] = "reconcile-required"
        record["state"] = {"next_action": "reconcile-stack-worker", "candidate": deepcopy(operation.get("candidate")), "review": None, "handback": None}
    else:
        try:
            if type(current["elapsed_seconds"]) is not int or current["elapsed_seconds"] < 0:
                raise StackPolicyError("stack worker elapsed time is malformed")
            _terminal(record, current, receipt)
            current["status"] = "result"
        except (ValueError, KeyError, TypeError) as exc:
            current["status"] = "result-unusable"
            current["validation_error"] = type(exc).__name__ + ": " + str(exc)
            # Malformed provider time cannot poison otherwise retainable evidence.
            current["elapsed_seconds"] = receipt.get("elapsed_seconds", 0) if type(receipt.get("elapsed_seconds", 0)) is int and receipt.get("elapsed_seconds", 0) >= 0 else 0
            _handback(record, "stack worker result is unusable and will not be resent: " + current["validation_error"])
    snapshot = coordinator._persist(snapshot, record)
    return cancel_expired(coordinator.store, snapshot, operation["id"], adapter, coordinator.clock())


def verify_slice(coordinator, snapshot, slice_id, task, adapter):
    record = validate_record(snapshot.value)
    task = _task(task, slice_id)
    approved = next((item for item in record["approval"]["slices"] if item["id"] == slice_id), None)
    if approved is None or approved["mode"] != "AFK":
        raise StackPolicyError("stack Verify dispatch requires an approved AFK slice")
    if not any(item["slice_id"] == slice_id and item["id"] == task["id"] and item["digest"] == digest(task) for item in record["approval"]["tasks"]):
        raise StackPolicyError("stack Verify task is not bound by immutable approval")
    entry = next(item for item in record["stack"]["slices"] if item["id"] == slice_id)
    if entry["candidate"] is None or entry["verification_environment_digest"] is None:
        raise StackPolicyError("stack Verify needs a current observed candidate and environment")
    if entry["accepted"]:
        return snapshot
    candidate = entry["candidate"]
    if approved["dependencies"]:
        entries = {item["id"]: item for item in record["stack"]["slices"]}
        predecessors = [entries[name] for name in approved["dependencies"]]
        predecessor = predecessors[-1]
        target = predecessor["restack_base"] if predecessor["merged"] else predecessor["candidate"]["head"] if predecessor["candidate"] else None
        if not all(item["accepted"] for item in predecessors) or candidate["base"] != target:
            raise StackPolicyError("stack Verify requires accepted dependencies and a current restack base")
    operation_id = _expected_id(record, task, "stack-verify", {**candidate, "verification_environment_digest": entry["verification_environment_digest"]})
    operation = _intent(record, operation_id, "stack-verify", slice_id, task, coordinator.clock(), candidate=candidate, criteria=task["criteria"], verification_environment_digest=entry["verification_environment_digest"])
    if candidate["base"] != task["base"]:
        restack = next((item for item in reversed(record["stack"]["operations"]) if item["kind"] == "restack" and item["slice_id"] == slice_id and item["status"] == "result" and item["receipt"]["candidate"] == candidate), None)
        if restack is None:
            raise StackPolicyError("changed-base stack Verify requires its completed durable restack")
        operation["restack_operation_id"] = restack["id"]
    prior = next((item for item in record["usage"]["operations"] if item["phase"] == "stack-verify" and item["slice"] == slice_id and item["id"] != operation_id and item["status"] in {"intent", "reconcile-required"}), None)
    if prior is not None:
        # Settle older work before reserving a new revision. Its stale result is
        # retained, but is never projected onto the current candidate's review.
        return _advance(coordinator, snapshot, prior, adapter)
    # Validate the effective base before creating a host session.
    restack_bound_verify_task(record, operation, task)
    snapshot = _advance(coordinator, snapshot, operation, adapter)
    record = validate_record(snapshot.value)
    current = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
    if current is None or current["status"] not in {"result", "reconciled"}:
        return snapshot
    receipt = current["receipt"]
    environment = operation["verification_environment_digest"]
    review = {"candidate": deepcopy(candidate), "verdict": "pass", "fresh_context": True, "verify_operation_id": operation_id, "verification_environment_digest": environment, "binding_digest": digest({"candidate": candidate, "runtime": receipt["runtime"], "artifact_id": receipt["evidence"]["artifact"]["id"], "operation_id": operation_id, "verification_environment_digest": environment}), "findings": deepcopy(receipt.get("nonblocking_findings", []))}
    return coordinator.accept_review(snapshot, slice_id, review)


def final_review(coordinator, snapshot, adapter):
    record = validate_record(snapshot.value)
    entries = record["stack"]["slices"]
    if not all(entry["accepted"] and entry["pr"] and entry["pr"]["state"] in {"open", "merged"} for entry in entries):
        raise StackPolicyError("final worker dispatch requires accepted current review and PRs for every slice")
    if record["stack"]["final"] is not None:
        return snapshot
    candidates = [{"slice_id": entry["id"], "candidate": entry["candidate"]} for entry in entries]
    current_ids = {_final_operation_id(record, kind, candidates, bound_inputs=True) for kind in ("final-qa", "final-ci", "cross-slice-review")}
    prior = next((item for item in record["usage"]["operations"] if item["phase"] in FINAL_PHASES and item["id"] not in current_ids and item["status"] in {"intent", "reconcile-required"}), None)
    if prior is not None:
        return _advance(coordinator, snapshot, prior, adapter)
    tasks = [_review_task(record, entry)[0] for entry in entries]
    evidence = {}
    for kind in ("qa", "ci", "review"):
        phase = "stack-final-" + kind
        operation_id = _final_operation_id(record, "cross-slice-review" if kind == "review" else "final-" + kind, candidates, bound_inputs=True)
        task = _final_task(operation_id, tasks)
        operation = _intent(record, operation_id, phase, "stack", task, coordinator.clock(), candidates=candidates, final_context=entries)
        snapshot = _advance(coordinator, snapshot, operation, adapter)
        record = validate_record(snapshot.value)
        current = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
        if current is None or current["status"] not in {"result", "reconciled"}:
            return snapshot
        evidence[kind + "_operation_id"] = operation_id
    return coordinator.finalise(snapshot, evidence)


def _final_task(operation_id, tasks):
    return {"id": operation_id, "criteria": list(dict.fromkeys(criterion for item in tasks for criterion in item["criteria"])), "tasks": deepcopy(tasks), "limits": {"max_tools": sum(item["limits"]["max_tools"] for item in tasks), "wall_time_seconds": sum(item["limits"]["wall_time_seconds"] for item in tasks)}}


def validate_dispatch(record):
    """Validate new final intents and historical results from frozen review inputs."""
    from .interim_stack import _entry, _review_binding, _slice_map
    for operation in record["usage"]["operations"]:
        if operation["phase"] not in FINAL_PHASES or "final_context" not in operation:
            continue  # Legacy fixture evidence is still checked by finalise.
        context = operation["final_context"]
        if not isinstance(context, list) or [entry.get("id") for entry in context] != [entry["id"] for entry in record["stack"]["slices"]]:
            raise StackPolicyError("final worker intent lacks every approved slice")
        projected = deepcopy(record)
        projected["stack"]["slices"] = deepcopy(context)
        for entry in context:
            _entry(entry, _slice_map(record))
            if entry["accepted"] is not True:
                raise StackPolicyError("final worker intent lacks accepted input reviews")
            _review_binding(projected, entry, entry["review"])
        candidates = [{"slice_id": entry["id"], "candidate": entry["candidate"]} for entry in context]
        kind = "cross-slice-review" if operation["phase"] == "stack-final-review" else operation["phase"].removeprefix("stack-")
        expected_id = _final_operation_id(projected, kind, candidates, bound_inputs=True)
        identities = operation_identities(record["approval"]["run_id"], expected_id, operation["phase"])
        tasks = [_review_task(projected, entry)[0] for entry in context]
        if operation["id"] != expected_id or operation["slice"] != "stack" or operation.get("candidates") != candidates or operation.get("task") != _final_task(expected_id, tasks) or operation.get("route") != {key: record["approval"]["routes"]["verify"][key] for key in ("model", "effort")} or any(operation[key] != value for key, value in identities.items()):
            raise StackPolicyError("final worker intent differs from its immutable reviewed inputs")
        receipt = operation.get("receipt")
        if operation["status"] in {"result", "reconciled"}:
            _terminal(record, operation, receipt)
        elif operation["status"] == "intent" and receipt is not None:
            raise StackPolicyError("final worker intent must not carry a result")
        elif operation["status"] == "reconcile-required":
            if not isinstance(receipt, dict) or receipt.get("terminal_turn") is True or not (receipt.get("worker_state") in {"queued", "active", "unknown"} or receipt.get("transport") in {"timeout", "unknown"}):
                raise StackPolicyError("final worker pending receipt must remain incomplete")

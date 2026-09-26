"""Deterministic S2 fixture coordinator; it deliberately has no host worker client.

The adapter is a narrow modeled-send seam.  Checkpointing happens before every
call and after every receipt, so a caller can reconcile a stable operation id
without treating transport, idle, or a terminal turn as task success.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .canonical import digest
from .interim_identity import operation_identities
from .interim_semantics import SemanticError, validate_worker_result, validate_handoff, accepted_slice_candidate, validate_ordinary_verify_failure
from .interim import InterimCheckpointError, InterimCheckpointSnapshot, InterimError, InterimCheckpointStore, validate_record
from .interim_disposition import clear as clear_disposition, unresolved as unresolved_disposition, decision_reason


class InterimDispatchError(InterimError):
    """A bounded modeled operation cannot advance the S2 fixture."""


class ModeledAdapter(Protocol):
    def send(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def reconcile(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def cancel(self, operation: dict[str, Any]) -> dict[str, Any]: ...


def _bind_worker_hint(adapter: ModeledAdapter, snapshot: InterimCheckpointSnapshot,
                      operation: dict[str, Any], repository: object) -> None:
    """Give a capable host adapter the trusted, persisted operation identity."""
    if "monitoring" in snapshot.value and hasattr(adapter, "bind_worker_hint"):
        adapter.bind_worker_hint(snapshot.value, operation["id"], repository)


def _fail(message: str) -> None:
    raise InterimDispatchError(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _operation_id(record: dict[str, Any], task: dict[str, Any], phase: str, candidate: str | None = None) -> str:
    # Logical identity never derives from a transport receipt or retry attempt.
    return "op-" + digest({"run": record["approval"]["run_id"], "slice": task["slice_id"], "task": task["id"], "attempt": task["attempt"], "candidate": candidate or task["candidate_ref"], "phase": phase})[7:23]


def _at(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _append(record: dict[str, Any], item: dict[str, Any], launch: bool = False) -> None:
    record["usage"]["operations"].append(item)
    if launch:
        record["usage"]["launches"].append({"operation_id": item["id"], "phase": item["phase"], "issued_at": item["issued_at"]})
        record["usage"]["charges"].append({"operation_id": item["id"], "work_units": 1, "status": "pending", "charged_at": item["issued_at"]})


def _handback(record: dict[str, Any], reason: str, finding: dict[str, Any] | None = None) -> dict[str, Any]:
    current_slice = record["state"].get("slice_id")
    record["state"] = {"next_action": "handback", "candidate": record["state"].get("candidate"), "review": record["state"].get("review"), "handback": {"reason": reason, "finding": finding}}
    if current_slice is not None:
        record["state"]["slice_id"] = current_slice
    return record


def _await_worker(record: dict[str, Any], intent: dict[str, Any], phase: str) -> dict[str, Any]:
    if "monitoring" not in record:
        return _handback(record, f"{phase} is incomplete; reconcile the same durable operation ID")
    record["state"] = {"next_action": "await-worker", "slice_id": intent["slice"],
                       "operation_id": intent["id"], "candidate": record["state"].get("candidate"),
                       "review": record["state"].get("review"), "handback": None}
    return record


def _limit(record: dict[str, Any], now: datetime) -> str | None:
    limits = record["approval"]["hard_limits"]
    if limits == "none":
        return None
    if "deadline_at" in limits and now >= datetime.fromisoformat(limits["deadline_at"].replace("Z", "+00:00")):
        return "selected deadline reached"
    if len(record["usage"]["launches"]) >= limits.get("dispatch_max", 2**63 - 1):
        return "selected dispatch cap reached"
    return None


def _deadline_reached(record: dict[str, Any], now: datetime) -> bool:
    limits = record["approval"]["hard_limits"]
    return limits != "none" and "deadline_at" in limits and now >= datetime.fromisoformat(limits["deadline_at"].replace("Z", "+00:00"))


def _task(value: object, slice_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"id", "slice_id", "attempt", "candidate_ref", "base", "criteria", "runtimes", "commands", "limits"}:
        _fail("bounded task has unknown or missing fields")
    if value["slice_id"] != slice_id or not all(isinstance(value[key], str) and value[key] for key in ("id", "candidate_ref", "base")) or type(value["attempt"]) is not int or value["attempt"] < 1:
        _fail("bounded task identity is malformed")
    if len(value["base"]) != 40 or any(char not in "0123456789abcdef" for char in value["base"]):
        _fail("bounded task base must be an exact revision")
    if not isinstance(value["criteria"], list) or not value["criteria"] or len(value["criteria"]) != len(set(value["criteria"])) or any(not isinstance(item, str) or not item for item in value["criteria"]):
        _fail("bounded task criteria must be unique approved IDs")
    if not isinstance(value["runtimes"], dict) or set(value["runtimes"]) != {"build", "verify"}:
        _fail("bounded task runtime expectations are missing")
    for phase in ("build", "verify"):
        expected = value["runtimes"][phase]
        if not isinstance(expected, dict) or set(expected) != {"runner", "permissions"} or any(not isinstance(expected[key], str) or not expected[key] for key in expected):
            _fail("bounded task runtime expectations are malformed")
    if not isinstance(value["commands"], dict) or set(value["commands"]) != {"build", "verify", "qa", "ci"}:
        _fail("bounded task command identities are missing")
    for name, commands in value["commands"].items():
        if not isinstance(commands, list) or not commands or len(commands) != len(set(commands)) or any(not isinstance(command, str) or not command for command in commands):
            _fail(f"bounded task {name} commands are malformed")
    if not isinstance(value["limits"], dict) or set(value["limits"]) != {"max_artifacts", "max_tools", "wall_time_seconds"} or any(type(item) is not int or item < 1 for item in value["limits"].values()):
        _fail("bounded task evidence limits are malformed")
    return deepcopy(value)


def _ledger(record: dict[str, Any]) -> None:
    operations = record["usage"]["operations"]
    if any(not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] for item in operations):
        _fail("operation ledger is malformed")
    if len({item["id"] for item in operations}) != len(operations):
        _fail("operation ledger contains duplicate logical IDs")


def _receipt(value: object, intent: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("adapter observation is missing")
    expected = {key: intent[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
    if value.get("observation") != expected:
        _fail("adapter observation is not correlated to the durable intended operation")
    return value


def _observed(record: dict[str, Any], operation_id: str) -> None:
    for charge in record["usage"]["charges"]:
        if charge["operation_id"] == operation_id:
            charge["status"] = "observed"
            return
    _fail("operation has no linked conservative charge")


def _success(result: object, intent: dict[str, Any], phase: str, route: dict[str, Any], task: dict[str, Any], candidate: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        return validate_worker_result(result, intent, phase, route, task, candidate)
    except SemanticError as exc:
        raise InterimDispatchError(str(exc)) from exc


def _handoff(value: object, candidate: dict[str, str], intent: dict[str, Any], task: dict[str, Any], artifact_id: str, runtime: dict[str, Any]) -> dict[str, Any]:
    try:
        return deepcopy(validate_handoff(value, candidate, intent, task, artifact_id, runtime))
    except SemanticError as exc:
        raise InterimDispatchError(str(exc)) from exc


class InterimFixtureCoordinator:
    """Approved per-slice Build -> fresh Verify -> PR-ready adapter protocol."""

    def __init__(self, store: InterimCheckpointStore, clock: Callable[[], datetime] = _now):
        self.store, self.clock = store, clock

    def _persist(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any]) -> InterimCheckpointSnapshot:
        return self.store.persist_lifecycle(snapshot, record)

    def _admit_send(self, snapshot: InterimCheckpointSnapshot, operation_id: str) -> tuple[InterimCheckpointSnapshot, bool]:
        """CAS the final admission after binding; later Stop treats it as in flight.

        Binding is read-only but may be slow. Stop before this CAS wins; Stop
        after it cannot revoke an already admitted provider effect and instead
        reconciles that same ID. Git CAS and the provider call are not atomic.
        """
        if "monitoring" not in snapshot.value:
            return snapshot, True  # preserve the established standalone S2 fixture timing
        current = self.store.reload(snapshot.value)
        record = current.value
        if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"} or record.get("monitoring", {}).get("state") == "inactive":
            return current, False
        matching = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
        if len(matching) != 1 or matching[0]["status"] != "intent" or "send_admission" in matching[0]:
            return current, False
        limits = record["approval"]["hard_limits"]
        admission_at = self.clock()
        if _deadline_reached(record, admission_at):
            try:
                return self._persist(current, _handback(deepcopy(record), "selected deadline reached before worker send admission")), False
            except InterimCheckpointError as exc:
                if exc.code != "cas-lost":
                    raise
                return self.store.reload(snapshot.value), False
        if limits != "none" and len(record["usage"]["launches"]) > limits.get("dispatch_max", 2**63 - 1):
            return current, False
        projected = deepcopy(record)
        operation = next(item for item in projected["usage"]["operations"] if item["id"] == operation_id)
        operation["send_admission"] = {"operation_id": operation_id, "at": _at(admission_at)}
        try:
            admitted = self._persist(current, projected)
        except InterimCheckpointError as exc:
            if exc.code != "cas-lost":
                raise
            return self.store.reload(snapshot.value), False
        return admitted, True

    def _persist_receipt_or_handback(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], phase: str) -> InterimCheckpointSnapshot:
        """Never publish a semantically corrupt adapter receipt as a checkpoint."""
        try:
            return self._persist(snapshot, record)
        except InterimError as exc:
            prior = validate_record(snapshot.value)
            if "monitoring" in prior:
                incoming = record["usage"]["operations"][-1]
                if incoming.get("phase") in {"build", "verify"} and isinstance(incoming.get("receipt"), dict):
                    return self._retain_failed_result(snapshot, prior, incoming["id"], incoming["receipt"], type(exc).__name__)
            return self._persist(snapshot, _handback(prior, f"{phase} receipt is corrupt or unresolvable: {exc}"))

    def _retain_failed_result(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any],
                              operation_id: str, receipt: dict[str, Any], reason: str) -> InterimCheckpointSnapshot:
        """Retain one exact failure without turning a host observation into success."""
        operation = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)
        operation["receipt"] = deepcopy(receipt)
        operation["status"] = "result-unusable"
        operation["validation_error"] = reason
        operation["elapsed_seconds"] = receipt.get("elapsed_seconds", 0) if type(receipt.get("elapsed_seconds", 0)) is int and receipt.get("elapsed_seconds", 0) >= 0 else 0
        _observed(record, operation_id)
        record["state"] = {"next_action": "worker-failed", "slice_id": operation["slice"],
                           "operation_id": operation_id, "candidate": record["state"].get("candidate"),
                           "review": record["state"].get("review"), "handback": None}
        return self._persist(snapshot, record)

    def _unresolved_observation(self, snapshot: InterimCheckpointSnapshot, intent: dict[str, Any],
                                adapter: ModeledAdapter, error: Exception, *, read_cycle: bool = False) -> InterimCheckpointSnapshot:
        """Retain an exact uncertain send/read before any replacement is possible."""
        record = validate_record(snapshot.value)
        if "monitoring" not in record:
            return self._persist(snapshot, _handback(record, str(error)))
        current = next(item for item in record["usage"]["operations"] if item["id"] == intent["id"])
        if record["state"].get("next_action") != "await-worker" or record["state"].get("operation_id") != current["id"]:
            snapshot = self._persist(snapshot, _await_worker(record, current, current["phase"]))
            record = validate_record(snapshot.value)
        if read_cycle:
            category = getattr(error, "category", None) or ("uncertain-effect" if current["status"] == "intent" and current.get("receipt") is None else "transient-outage")
            if unresolved_disposition(record, category, current["id"], self.clock(), getattr(error, "retry_after", None)):
                return self._persist(snapshot, _handback(record, decision_reason(category)))
            snapshot = self._persist(snapshot, record)
        unknown = {"observation": {name: current[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                   "transport": "unknown", "worker_state": "unknown", "elapsed_seconds": 0}
        stopped = self._unfinished_deadline_handback(snapshot, validate_record(snapshot.value), current, unknown, adapter)
        return stopped or snapshot

    def reconcile_pending(self, snapshot: InterimCheckpointSnapshot, operation_id: str, adapter: ModeledAdapter) -> InterimCheckpointSnapshot:
        """Persist one same-ID observation; never re-send an ambiguous operation."""
        record = validate_record(snapshot.value)
        _ledger(record)
        matches = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
        if len(matches) != 1 or matches[0].get("status") not in {"intent", "reconcile-required"}:
            _fail("only one pending durable operation may be reconciled")
        intent = matches[0]
        try:
            receipt = _receipt(adapter.reconcile(deepcopy(intent)), intent)
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            return self._unresolved_observation(snapshot, intent, adapter, exc, read_cycle=True)
        if receipt.get("result_unusable") and receipt.get("terminal_turn") is True:
            clear_disposition(record)
            return self._retain_failed_result(snapshot, record, operation_id, receipt, "terminal host result is unusable")
        intent["receipt"] = deepcopy(receipt)
        # An accepted host message can still be queued or active.  Preserve it
        # as the same pending operation; only a terminal structured result can
        # enter the worker-result transition below.
        worker_error = receipt.get("worker_state") == "error"
        intent["status"] = "result-unusable" if worker_error else "reconciled" if receipt.get("terminal_turn") is True else "reconcile-required"
        if worker_error:
            clear_disposition(record)
            intent["validation_error"] = "exact worker session reported error"
            record["state"] = {"next_action": "worker-failed", "slice_id": intent["slice"],
                               "operation_id": intent["id"], "candidate": record["state"].get("candidate"),
                               "review": record["state"].get("review"), "handback": None}
        elif intent["status"] == "reconcile-required":
            _await_worker(record, intent, intent["phase"])
            if receipt.get("worker_state") not in {"queued", "active"}:
                if unresolved_disposition(record, "uncertain-effect", intent["id"], self.clock()):
                    return self._persist(snapshot, _handback(record, decision_reason("uncertain-effect")))
            else:
                clear_disposition(record)
        elif record["state"]["next_action"] == "await-worker":
            clear_disposition(record)
            record["state"] = {"next_action": intent["phase"], "slice_id": intent["slice"],
                               "candidate": record["state"].get("candidate"),
                               "review": record["state"].get("review"), "handback": None}
        intent["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
        _observed(record, operation_id)
        snapshot = self._persist_receipt_or_handback(snapshot, record, intent["phase"])
        durable = validate_record(snapshot.value)
        stopped = self._unfinished_deadline_handback(snapshot, durable, intent, receipt, adapter)
        return stopped or snapshot

    def _unfinished_deadline_handback(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], intent: dict[str, Any], receipt: dict[str, Any], adapter: ModeledAdapter) -> InterimCheckpointSnapshot | None:
        if receipt.get("terminal_turn") is True:
            return None
        now = self.clock()
        if not _deadline_reached(record, now):
            return None
        operation = next(item for item in record["usage"]["operations"] if item["id"] == intent["id"])
        if "cancellation_intent" in operation:
            return snapshot  # whole-run recovery reconciles a lost cancel response
        operation.setdefault("receipt", deepcopy(receipt))
        operation["cancellation_intent"] = {"at": _at(now), "reason": "selected deadline reached"}
        operation["cancellation"] = {"observation": {name: intent[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "uncertain"}
        operation["status"] = "cancellation-uncertain"
        snapshot = self._persist(snapshot, _handback(record, "selected deadline reached; cancellation intent recorded"))
        record = validate_record(snapshot.value)
        operation = next(item for item in record["usage"]["operations"] if item["id"] == intent["id"])
        try:
            cancellation = _receipt(adapter.cancel(deepcopy(operation)), intent)
            if cancellation.get("state") != "cancelled":
                _fail("cancellation observation is missing terminal cancellation state")
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            operation["cancellation"] = {"observation": {name: intent[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "uncertain", "reason": str(exc)}
            operation["status"] = "cancellation-uncertain"
            return self._persist(snapshot, _handback(record, f"selected deadline reached; cancellation uncertain: {exc}"))
        operation["cancellation"] = deepcopy(cancellation)
        operation["status"] = "unfinished-cancelled"
        return self._persist(snapshot, _handback(record, "selected deadline reached; cancellation observed for unfinished operation"))

    def run_frontier(self, snapshot: InterimCheckpointSnapshot, tasks: dict[str, Any], build: ModeledAdapter, verify: ModeledAdapter, coordinator: ModeledAdapter | None = None, *, one_step: bool = False) -> InterimCheckpointSnapshot:
        """Advance one approved ordinary dependency frontier, including polling.

        Candidate observations come from terminal Build receipts. The caller
        supplies immutable tasks, never derived bases or synthesized successes.
        """
        record = validate_record(snapshot.value)
        current = record["state"].get("slice_id")
        if current is not None and record["state"]["next_action"] in {"build", "verify", "handback", "await-worker"}:
            if current not in tasks:
                _fail("current slice lacks its approved bounded task")
            return self.run_one(snapshot, current, tasks[current], build, verify, coordinator, one_step=one_step)
        accepted = set()
        for approved in record["approval"]["slices"]:
            try:
                accepted_slice_candidate(record, approved["id"])
            except SemanticError:
                continue
            accepted.add(approved["id"])
        for approved in record["approval"]["slices"]:
            if approved["id"] in accepted or not set(approved["dependencies"]).issubset(accepted):
                continue
            if approved["mode"] != "AFK":
                return self._persist(snapshot, _handback(record, "approved HITL slice blocks ordinary dependency frontier"))
            if approved["id"] not in tasks:
                _fail("frontier slice lacks its approved bounded task")
            return self.run_one(snapshot, approved["id"], tasks[approved["id"]], build, verify, coordinator, one_step=one_step)
        if len(accepted) != len(record["approval"]["slices"]):
            return self._persist(snapshot, _handback(record, "ordinary dependency frontier has no accepted predecessor"))
        return snapshot

    def run_one(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object, build: ModeledAdapter, verify: ModeledAdapter, coordinator: ModeledAdapter | None = None, *, one_step: bool = False) -> InterimCheckpointSnapshot:
        try:
            record = validate_record(snapshot.value)
        except InterimError as exc:
            raise InterimDispatchError(f"corrupt checkpoint cannot be safely advanced; reload a trustworthy revision: {exc}") from exc
        task = _task(task, slice_id)
        approved_tasks = record["approval"].get("tasks", [])
        if not any(item["id"] == task["id"] and item["slice_id"] == slice_id and item["spec_revision"] == record["approval"]["tracker"]["spec_revision"] and item["digest"] == digest(task) for item in approved_tasks):
            _fail("bounded task is not bound by immutable approval")
        if "launches" not in record["usage"]:
            _fail("S2 requires an operation/accounting container before dispatch")
        _ledger(record)
        approved_slice = next((item for item in record["approval"]["slices"] if item["id"] == slice_id), None)
        if approved_slice is None or approved_slice["mode"] != "AFK":
            _fail("requested slice is outside approved AFK scope")
        try:
            for dependency in approved_slice["dependencies"]:
                accepted_slice_candidate(record, dependency)
        except SemanticError as exc:
            _fail(str(exc))
        if any(op["phase"] in {"build", "verify"} and op["slice"] != slice_id and op["status"] in {"intent", "reconcile-required", "cancellation-uncertain"} for op in record["usage"]["operations"]):
            _fail("another slice has an unfinished ordinary worker")
        coordinator = coordinator or build
        if not any(item.get("phase") == "coordinator" for item in record["usage"]["operations"]):
            coordinator_id = "op-" + digest({"run": record["approval"]["run_id"], "task": task["id"], "attempt": task["attempt"], "phase": "coordinator"})[7:23]
            coordinator_intent = {"id": coordinator_id, "slice": slice_id, "phase": "coordinator", "task": task, **operation_identities(record["approval"]["run_id"], coordinator_id, "coordinator", record["approval"]["coordinator"]["session_id"]), "status": "intent", "issued_at": _at(self.clock()), "elapsed_seconds": 0}
            _append(record, coordinator_intent, launch=True)
            snapshot = self._persist(snapshot, record)
            record = validate_record(snapshot.value)
            try:
                observation = _receipt(coordinator.observe_coordinator(deepcopy(coordinator_intent)), coordinator_intent)
                if observation.get("current_coordinator") != record["approval"]["coordinator"]["session_id"] or observation.get("state") != "active" or type(observation.get("elapsed_seconds")) is not int or observation["elapsed_seconds"] < 0:
                    _fail("current coordinator observation is missing, ambiguous, or differs from immutable approval")
            except InterimDispatchError as exc:
                return self._persist(snapshot, _handback(record, str(exc)))
            current = next(item for item in record["usage"]["operations"] if item["id"] == coordinator_id)
            current["receipt"] = deepcopy(observation)
            current["status"] = "active"
            current["elapsed_seconds"] = observation["elapsed_seconds"]
            _observed(record, coordinator_id)
            snapshot = self._persist(snapshot, record)
            record = validate_record(snapshot.value)
        else:
            coordinator_intent = next(item for item in record["usage"]["operations"] if item.get("phase") == "coordinator")
            try:
                observation = _receipt(coordinator.observe_coordinator(deepcopy(coordinator_intent)), coordinator_intent)
                if observation.get("current_coordinator") != record["approval"]["coordinator"]["session_id"] or observation.get("state") != "active" or type(observation.get("elapsed_seconds")) is not int or observation["elapsed_seconds"] < 0:
                    _fail("current coordinator observation is missing, ambiguous, or differs from immutable approval")
            except InterimDispatchError as exc:
                return self._persist(snapshot, _handback(record, str(exc)))
            coordinator_intent["receipt"] = deepcopy(observation)
            coordinator_intent["status"] = "active"
            coordinator_intent["elapsed_seconds"] = observation["elapsed_seconds"]
            _observed(record, coordinator_intent["id"])
            snapshot = self._persist(snapshot, record)
            record = validate_record(snapshot.value)
        existing = [item for item in record["usage"]["operations"] if item.get("slice") == slice_id and item.get("phase") == "build"]
        if len(existing) > 1:
            _fail("duplicate Build logical operation IDs require handback")
        if existing and existing[0].get("status") in {"intent", "reconcile-required"}:
            return self.reconcile_pending(snapshot, existing[0]["id"], build)
        if existing and existing[0].get("status") not in {"result", "reconciled"}:
            _fail("existing Build operation cannot be re-sent")
        limit = _limit(record, self.clock())
        if limit and not existing:
            return self._persist(snapshot, _handback(record, limit))
        if existing:
            intent, receipt = existing[0], existing[0].get("receipt")
            if not isinstance(receipt, dict):
                _fail("reconciled Build has no correlated receipt")
        else:
            build_id = _operation_id(record, task, "build")
            intent = {"id": build_id, "slice": slice_id, "phase": "build", "task": task, **operation_identities(record["approval"]["run_id"], build_id, "build"), "status": "intent", "issued_at": _at(self.clock()), "elapsed_seconds": 0}
            _append(record, intent, launch=True)
            record["state"] = {"next_action": "build", "slice_id": slice_id, "candidate": None, "review": None, "handback": None}
            snapshot = self._persist(snapshot, record)  # intent is durable before modeled send
            try:
                _bind_worker_hint(build, snapshot, intent, self.store.repository)
            except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
                return self._unresolved_observation(snapshot, intent, build, exc)
            snapshot, allowed = self._admit_send(snapshot, intent["id"])
            if not allowed:
                return snapshot
            try:
                receipt = _receipt(build.send(deepcopy(intent)), intent)
            except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
                return self._unresolved_observation(snapshot, intent, build, exc)
            record = validate_record(snapshot.value)
            if receipt.get("result_unusable") and receipt.get("terminal_turn") is True:
                return self._retain_failed_result(snapshot, record, intent["id"], receipt, "terminal host result is unusable")
            record["usage"]["operations"][-1]["receipt"] = deepcopy(receipt)
            record["usage"]["operations"][-1]["status"] = "reconcile-required" if receipt.get("transport") in ("timeout", "unknown") or receipt.get("worker_state") in {"queued", "active", "unknown"} else "result"
            record["usage"]["operations"][-1]["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
            _observed(record, intent["id"])
            snapshot = self._persist_receipt_or_handback(snapshot, record, "Build")  # correlated receipt is durable before transition
            if snapshot.value["state"]["next_action"] == "handback":
                return snapshot
            stopped = self._unfinished_deadline_handback(snapshot, record, intent, receipt, build)
            if stopped is not None:
                return stopped
            if receipt.get("transport") in ("timeout", "unknown") or receipt.get("worker_state") in {"queued", "active", "unknown"}:
                return self._persist(snapshot, _await_worker(record, intent, "Build"))
        try:
            built = _success(receipt, intent, "Build", record["approval"]["routes"]["build"], task)
        except InterimDispatchError as exc:
            record = validate_record(snapshot.value)
            if "monitoring" in record:
                return self._retain_failed_result(snapshot, record, intent["id"], receipt, type(exc).__name__)
            return self._persist(snapshot, _handback(record, str(exc)))
        record = validate_record(snapshot.value)
        record["state"] = {"next_action": "verify", "slice_id": slice_id, "candidate": deepcopy(built["candidate"]), "review": None, "handback": None}
        if one_step and not existing:
            return self._persist(snapshot, record)
        existing_verify = [item for item in record["usage"]["operations"] if item.get("slice") == slice_id and item.get("phase") == "verify"]
        if len(existing_verify) > 1:
            _fail("duplicate Verify logical operation IDs require handback")
        if existing_verify and existing_verify[0].get("status") in {"intent", "reconcile-required"}:
            return self.reconcile_pending(snapshot, existing_verify[0]["id"], verify)
        limit = _limit(record, self.clock())
        if limit and not existing_verify:
            return self._persist(snapshot, _handback(record, limit))
        if existing_verify and existing_verify[0].get("status") not in {"result", "reconciled"}:
            _fail("existing Verify operation cannot be re-sent")
        if existing_verify:
            intent, receipt = existing_verify[0], existing_verify[0].get("receipt")
            if not isinstance(receipt, dict):
                _fail("reconciled Verify has no correlated receipt")
        else:
            verify_id = _operation_id(record, task, "verify", built["candidate"]["head"])
            intent = {"id": verify_id, "slice": slice_id, "phase": "verify", "task": task, "candidate": deepcopy(built["candidate"]), "criteria": list(task["criteria"]), **operation_identities(record["approval"]["run_id"], verify_id, "verify"), "status": "intent", "issued_at": _at(self.clock()), "elapsed_seconds": 0}
            _append(record, intent, launch=True)
            # This is a generated durable intent, not an adapter receipt.  It
            # must be published before the host send even when the prior
            # checkpoint was an incomplete Build handback.
            snapshot = self._persist(snapshot, record)
            try:
                _bind_worker_hint(verify, snapshot, intent, self.store.repository)
            except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
                return self._unresolved_observation(snapshot, intent, verify, exc)
            snapshot, allowed = self._admit_send(snapshot, intent["id"])
            if not allowed:
                return snapshot
            try:
                receipt = _receipt(verify.send(deepcopy(intent)), intent)
            except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
                return self._unresolved_observation(snapshot, intent, verify, exc)
            record = validate_record(snapshot.value)
            if receipt.get("result_unusable") and receipt.get("terminal_turn") is True:
                return self._retain_failed_result(snapshot, record, intent["id"], receipt, "terminal host result is unusable")
            record["usage"]["operations"][-1]["receipt"] = deepcopy(receipt)
            record["usage"]["operations"][-1]["status"] = "reconcile-required" if receipt.get("transport") in ("timeout", "unknown") or receipt.get("worker_state") in {"queued", "active", "unknown"} else "result"
            record["usage"]["operations"][-1]["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
            _observed(record, intent["id"])
            snapshot = self._persist_receipt_or_handback(snapshot, record, "Verify")
            if snapshot.value["state"]["next_action"] == "handback":
                return snapshot
            stopped = self._unfinished_deadline_handback(snapshot, record, intent, receipt, verify)
            if stopped is not None:
                return stopped
            if receipt.get("transport") in ("timeout", "unknown") or receipt.get("worker_state") in {"queued", "active", "unknown"}:
                return self._persist(snapshot, _await_worker(record, intent, "Verify"))
        try:
            reviewed = _success(receipt, intent, "Verify", record["approval"]["routes"]["verify"], task, built["candidate"])
            handoff = _handoff(reviewed.get("handoff"), built["candidate"], intent, task, reviewed["evidence"]["artifact"]["id"], reviewed["runtime"])
        except InterimDispatchError as exc:
            record = validate_record(snapshot.value)
            if "monitoring" in record:
                try:
                    current = next(item for item in record["usage"]["operations"] if item["id"] == intent["id"])
                    validate_ordinary_verify_failure(record, current, task, receipt)
                except SemanticError:
                    return self._retain_failed_result(snapshot, record, intent["id"], receipt, type(exc).__name__)
                record["state"] = {"next_action": "verify-failed", "slice_id": slice_id,
                                   "operation_id": intent["id"], "candidate": deepcopy(built["candidate"]),
                                   "review": None, "handback": None}
                return self._persist(snapshot, record)
            return self._persist(snapshot, _handback(record, str(exc)))
        record = validate_record(snapshot.value)
        record["state"] = {"next_action": "pr-ready", "slice_id": slice_id, "candidate": deepcopy(built["candidate"]), "review": {"findings": deepcopy(reviewed.get("nonblocking_findings", [])), "verdict": "pass"}, "handback": {"outcome": "pr-ready", "merge": "unavailable", "evidence": handoff}}
        return self._persist(snapshot, record)

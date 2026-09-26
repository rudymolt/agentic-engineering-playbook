"""Deterministic S3 fixture coordinator for one diagnosed repair sequence.

The adapter protocol is intentionally modeled.  This module persists intent
before every send and records correlated results before choosing a policy
transition; it has no Conductor, GitHub, or live worker client.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .interim import InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, validate_record
from .interim_coordinator import InterimDispatchError, InterimFixtureCoordinator, _at, _bind_worker_hint, _handback, _ledger, _limit, _observed, _task
from .interim_repair import _worker, repair_operation_id
from .canonical import digest
from .interim_identity import operation_identities
from .interim_worker_limits import cancel_expired
from .interim_disposition import eligible as recovery_check_eligible, unresolved as unresolved_disposition, clear as clear_disposition, decision_reason
from .interim_routes import route_for_operation
from .interim_repair import _diagnosis


def repair_opening_authority(record: dict[str, Any], slice_id: str) -> str | None:
    """Return the canonical S3 opening refusal for an otherwise valid record."""
    prior = record.get("repair")
    if isinstance(prior, dict) and (prior["status"] != "completed" or prior["slice_id"] == slice_id):
        return "repair policy is already open for this slice"
    if set(record["forecasts"]["initial"]) != {"work_units", "verification_units", "likely_repair_units", "final_handback_units"}:
        return "S3 requires an approved forecast covering work, verification, likely repairs, and final handback"
    return None


class RepairAdapter(Protocol):
    def send(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def reconcile(self, operation: dict[str, Any]) -> dict[str, Any]: ...


class _RouteUnavailable(InterimDispatchError):
    category = "route-mismatch"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _observation(value: object, operation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("observation") != {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}:
        raise InterimDispatchError("repair adapter observation is not correlated to durable intent")
    return value


def _append(record: dict[str, Any], operation: dict[str, Any]) -> None:
    record["usage"]["operations"].append(operation)
    record["usage"]["launches"].append({"operation_id": operation["id"], "phase": operation["phase"], "issued_at": operation["issued_at"]})
    record["usage"]["charges"].append({"operation_id": operation["id"], "work_units": 1, "status": "pending", "charged_at": operation["issued_at"]})


class InterimRepairCoordinator:
    """S3 policy only: diagnose, one repair, and one fresh Verify per cycle."""

    def __init__(self, store: InterimCheckpointStore, clock: Callable[[], datetime] = _now):
        self.store, self.clock = store, clock

    def _persist(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any]) -> InterimCheckpointSnapshot:
        return self.store.persist_lifecycle(snapshot, record)

    def _admitted_send(self, record: dict[str, Any]) -> str | None:
        """Check an already-persisted current intent immediately before send."""
        if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
            return "whole-run recovery state refuses repair dispatch"
        limits = record["approval"]["hard_limits"]
        if limits == "none":
            return None
        if "deadline_at" in limits and _limit(record, self.clock()) == "selected deadline reached":
            return "selected deadline reached"
        if len(record["usage"]["launches"]) > limits.get("dispatch_max", 2**63 - 1):
            return "selected dispatch cap reached"
        return None

    @staticmethod
    def _forecast_floor(record: dict[str, Any]) -> dict[str, int]:
        operations = record["usage"]["operations"]
        return {
            "work_units": sum(item["phase"] in {"coordinator", "build", "diagnosis", "repair"} for item in operations),
            "verification_units": sum(item["phase"] in {"verify", "repair-verify"} for item in operations),
            "likely_repair_units": sum(item["phase"] == "repair" for item in operations),
            # A handback is an estimate, not a modeled worker launch.  Keep
            # capacity for it without pretending it has already been consumed.
            "final_handback_units": 0,
        }

    def _forecast_target(self, record: dict[str, Any], next_phase: str | None = None) -> dict[str, int]:
        target = self._forecast_floor(record)
        if next_phase in {"diagnosis", "repair"}:
            target["work_units"] += 1
        if next_phase in {"diagnosis", "repair"}:
            target["likely_repair_units"] += 1
            target["verification_units"] += 1
        elif next_phase == "repair-verify":
            target["verification_units"] += 1
        target["final_handback_units"] = 1
        return target

    def _reforecast_if_needed(self, record: dict[str, Any], operation_id: str, next_phase: str | None = None) -> None:
        active = record["forecasts"]["revised"][-1]["forecast"] if record["forecasts"]["revised"] else record["forecasts"]["initial"]
        target = self._forecast_target(record, next_phase)
        if set(active) != set(target):
            raise InterimDispatchError("S3 forecast must cover work, verification, likely repairs, and final handback")
        if any(target[name] > active[name] for name in target):
            record["forecasts"]["revised"].append({"at": _at(self.clock()), "reason": "worker-result evidence requires remaining repair, verification, and handback capacity", "forecast": {name: max(active[name], target[name]) for name in target}, "evidence": {"operation_id": operation_id, "reason": "current retained worker-result checkpoint"}})

    def _ensure_forecast_capacity(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], next_phase: str) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
        """Record a result-bound soft estimate before no-cap continuation.

        Forecasts never refuse useful work by themselves.  They do make an
        overrun explicit before the next productive modeled send, using the
        latest durable observation rather than a caller assertion.
        """
        if record["approval"]["hard_limits"] != "none":
            return snapshot, record
        active = record["forecasts"]["revised"][-1]["forecast"] if record["forecasts"]["revised"] else record["forecasts"]["initial"]
        target = self._forecast_target(record, next_phase)
        if not any(target[name] > active[name] for name in target):
            return snapshot, record
        latest = next((item["id"] for item in reversed(record["usage"]["operations"]) if isinstance(item.get("receipt"), dict)), None)
        if latest is None:
            raise InterimDispatchError("no-cap continuation needs a retained result for its forecast revision")
        self._reforecast_if_needed(record, latest, next_phase)
        snapshot = self._persist(snapshot, record)
        return snapshot, validate_record(snapshot.value)

    def _persist_unusable(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], operation_id: str, receipt: dict[str, Any], error: Exception, reason: str) -> InterimCheckpointSnapshot:
        """Keep a correlated observation even when it cannot advance policy."""
        current = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)
        current["receipt"] = deepcopy(receipt)
        current["status"] = "result-unusable"
        current["elapsed_seconds"] = receipt.get("elapsed_seconds", 0) if type(receipt.get("elapsed_seconds", 0)) is int and receipt.get("elapsed_seconds", 0) >= 0 else 0
        current["validation_error"] = type(error).__name__ + ": " + str(error)
        _observed(record, operation_id)
        self._reforecast_if_needed(record, operation_id)
        if "monitoring" in record:
            # Exact session error is a retained failed attempt. S4b.4 owns
            # effect reconciliation and any later repair dispatch.
            record["repair"]["status"] = "worker-failed"
            record["state"] = {"next_action": "worker-failed", "slice_id": current["slice"],
                               "operation_id": operation_id, "candidate": record["state"].get("candidate"),
                               "review": record["state"].get("review"), "handback": None}
            return self._persist(snapshot, record)
        return self._handback(snapshot, record, f"{reason}; correlated observed result requires reconciliation and will not be resent: {current['validation_error']}")

    def open(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object, finding: object, revisions: object, execution_evidence: object,
             *, origin_operation_id: str | None = None) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        task = _task(task, slice_id)
        authority_refusal = repair_opening_authority(record, slice_id)
        if authority_refusal:
            raise InterimDispatchError(authority_refusal)
        if "repair" in record:
            prior = record["repair"]
            record.setdefault("repair_history", []).append(deepcopy(prior))
        opening = {"finding": deepcopy(finding), "criteria": deepcopy(task["criteria"]), "revisions": deepcopy(revisions), "execution_evidence": deepcopy(execution_evidence)}
        if origin_operation_id is not None:
            opening["origin_operation_id"] = origin_operation_id
        record["repair"] = {
            "slice_id": slice_id,
            "opening": opening,
            "status": "diagnosis-required", "diagnoses": [], "cycles": [], "progress": [],
            "batch": {"diagnosis_id": None, "cycles": 0, "no_progress": 0, "credited_progress": []},
        }
        if "escalation_policy" in record["approval"]:
            record["repair"]["escalated_slots"] = []
        record["state"] = {"next_action": "diagnosis", "candidate": deepcopy(revisions), "review": None, "handback": None}
        return self._persist(snapshot, record)

    def open_failed_worker(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object) -> InterimCheckpointSnapshot:
        """Use exact host failure evidence as the repair opening, never worker success."""
        record = validate_record(snapshot.value)
        if record["state"]["next_action"] != "failure-reconciled" or record["state"].get("slice_id") != slice_id:
            raise InterimDispatchError("failed worker repair lacks durable reconciliation")
        failures = [item for item in record["usage"]["operations"] if item.get("slice") == slice_id and isinstance(item.get("failure_reconciliation"), dict)]
        if len(failures) != 1:
            raise InterimDispatchError("failed worker repair needs one reconciled predecessor")
        operation = failures[0]
        candidate = operation["failure_reconciliation"]["candidate"]
        task = _task(task, slice_id)
        if operation["phase"] == "verify" and operation["receipt"].get("verdict") == "fail":
            criterion = next(key for key, value in operation["receipt"]["criteria"].items() if value == "fail")
            check = next(item for item in operation["receipt"]["evidence"]["checks"] if item["criterion_id"] == criterion)
            evidence = [{"id": "failed-check-" + operation["id"], "command": check["command"],
                         "result": "pass", "artifact_id": check["artifact_id"]}]
            summary = "Approved Verify criterion failed"
        else:
            criterion = task["criteria"][0]
            evidence = [{"id": "host-failure-" + operation["id"], "command": "conductor session status", "result": "pass", "artifact_id": operation["id"]}]
            summary = "Exact worker stopped before an acceptable result"
        finding = {"id": "failed-worker-" + operation["id"], "criterion_id": criterion,
                   "summary": summary, "reversible": True,
                   "scope": "in-scope", "external_effect": False, "requirement_changed": False,
                   "capability": "available", "evidence": evidence}
        return self.open(snapshot, slice_id, task, finding, candidate, evidence, origin_operation_id=operation["id"])

    def _operation(self, record: dict[str, Any], task: dict[str, Any], phase: str, attempt: int, candidate: dict[str, str], purpose: str) -> dict[str, Any]:
        operation_id = repair_operation_id(record, task, phase, attempt, candidate, purpose)
        operation = {
            "id": operation_id, "slice": task["slice_id"], "phase": phase, "task": deepcopy(task),
            "purpose": purpose, "repair_attempt": attempt,
            "route": route_for_operation(record["approval"], {"phase": phase}),
            **operation_identities(record["approval"]["run_id"], operation_id, phase), "status": "intent",
            "issued_at": _at(self.clock()), "elapsed_seconds": 0,
        }
        if phase == "repair-verify":
            operation["candidate"] = deepcopy(candidate)
        return operation

    def _handback(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], reason: str) -> InterimCheckpointSnapshot:
        record["repair"]["status"] = "handback"
        return self._persist(snapshot, _handback(record, reason))

    def _no_progress(self, record: dict[str, Any], policy: dict[str, Any], cycle: dict[str, Any], reason: str, handback: bool = False) -> None:
        """Apply the bounded post-diagnosis stagnation window exactly once."""
        policy["cycles"].append(cycle)
        policy["batch"]["cycles"] += 1
        policy["batch"]["no_progress"] += 1
        if handback:
            policy["status"] = "handback"
            _handback(record, reason)
        elif (escalation := record["approval"].get("escalation_policy")) and sum(item["outcome"] != "pass" for item in policy["cycles"]) >= escalation["trigger"]:
            policy["status"] = "escalation-ready"
            record["state"] = {"next_action": "escalation", "candidate": deepcopy(record["state"].get("candidate", policy["opening"]["revisions"])), "review": None, "handback": None}
        elif policy["batch"]["no_progress"] >= 3:
            policy["status"] = "stuck"
            _handback(record, reason)
        else:
            policy["status"] = "repair-ready"
            record["state"] = {"next_action": "repair", "candidate": deepcopy(policy["opening"]["revisions"]), "review": None, "handback": None}

    def _waiting(self, snapshot, record, operation, receipt=None):
        current = next(item for item in record["usage"]["operations"] if item["id"] == operation["id"])
        if receipt is not None:
            current["receipt"] = deepcopy(receipt)
            current["status"] = "reconcile-required"
            current["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
            _observed(record, current["id"])
        record["repair"]["status"] = "waiting-" + operation["phase"]
        record["state"] = {"next_action": "await-worker" if "monitoring" in record else "reconcile-repair",
                           "candidate": deepcopy(operation.get("candidate", record["repair"]["opening"]["revisions"])),
                           "review": None, "handback": None}
        if "monitoring" in record:
            record["state"]["slice_id"] = operation["slice"]
            record["state"]["operation_id"] = operation["id"]
        return self._persist(snapshot, record)

    def _dispatch(self, snapshot, operation, adapter):
        record = validate_record(snapshot.value)
        _append(record, operation)
        if "escalated_slot" in operation:
            record["repair"]["escalated_slots"].append(operation["id"])
        # The phase is durable even if the process dies between publish and send.
        snapshot = self._waiting(snapshot, record, operation)
        record = validate_record(snapshot.value)
        try:
            origin_id = record["repair"]["opening"].get("origin_operation_id")
            if origin_id is not None and operation["phase"] in {"diagnosis", "repair"}:
                origin = next(item for item in record["usage"]["operations"] if item["id"] == origin_id)
                if not hasattr(adapter, "preflight_repair_candidate"):
                    raise InterimDispatchError("repair candidate fingerprint cannot be checked")
                adapter.preflight_repair_candidate(record, self.store.repository,
                                                   origin["failure_reconciliation"]["candidate_work"])
            if "escalated_slot" in operation:
                if not hasattr(adapter, "preflight_escalated"):
                    raise _RouteUnavailable("authoritative escalated host preflight is unavailable")
                identity = adapter.preflight_escalated(deepcopy(operation))
                if identity != {"session_id": operation["session_id"], **operation["route"]}:
                    raise _RouteUnavailable("authoritative escalated host route differs from durable approval")
                projected = validate_record(snapshot.value)
                current = next(item for item in projected["usage"]["operations"] if item["id"] == operation["id"])
                current["route_preflight"] = deepcopy(identity)
                snapshot = self._persist(snapshot, projected)
                record = validate_record(snapshot.value)
                operation = next(item for item in record["usage"]["operations"] if item["id"] == operation["id"])
            _bind_worker_hint(adapter, snapshot, operation, self.store.repository)
            if "monitoring" in record:
                snapshot, allowed = InterimFixtureCoordinator(self.store, clock=self.clock)._admit_send(snapshot, operation["id"])
                if not allowed:
                    return snapshot
            else:
                limit = self._admitted_send(record)
                if limit:
                    return self._handback(snapshot, record, limit)
            receipt = _observation(adapter.send(deepcopy(operation)), operation)
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            if "escalated_slot" in operation and "route_preflight" not in operation:
                return self._preflight_failure(snapshot, operation, exc)
            # The exact intent may have reached the provider. Poll it on re-entry;
            # an ambiguous transport is neither a failed cycle nor retry authority.
            record["state"]["handback"] = {"reason": "repair send requires same-ID reconciliation: " + type(exc).__name__, "finding": None}
            snapshot = self._persist(snapshot, record)
            return cancel_expired(self.store, snapshot, operation["id"], adapter, self.clock())
        snapshot = self._project(snapshot, operation["id"], receipt)
        return cancel_expired(self.store, snapshot, operation["id"], adapter, self.clock())

    def reconcile_pending(self, snapshot: InterimCheckpointSnapshot, operation_id: str, adapter: RepairAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if "monitoring" in record and not recovery_check_eligible(record, self.clock()):
            return snapshot
        if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
            raise InterimDispatchError("whole-run recovery state refuses repair continuation")
        operation = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
        if operation is None or operation["phase"] not in {"diagnosis", "repair", "repair-verify"}:
            raise InterimDispatchError("repair reconciliation requires an existing repair operation")
        if operation["status"] not in {"intent", "reconcile-required"}:
            return snapshot
        if record["repair"]["status"] != "waiting-" + operation["phase"]:
            raise InterimDispatchError("repair reconciliation differs from the durable pending phase")
        if "escalated_slot" in operation and operation["status"] == "intent" and "route_preflight" not in operation:
            if not hasattr(adapter, "confirm_escalated"):
                return self._preflight_failure(snapshot, operation, _RouteUnavailable("exact idle-session readback unavailable"))
            try:
                identity = adapter.confirm_escalated(deepcopy(operation))
                if identity != {"session_id": operation["session_id"], **operation["route"]}:
                    raise _RouteUnavailable("exact idle-session route differs")
            except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
                return self._preflight_failure(snapshot, operation, exc)
            projected = validate_record(snapshot.value)
            next_op = next(item for item in projected["usage"]["operations"] if item["id"] == operation["id"])
            next_op["route_preflight"] = deepcopy(identity)
            snapshot = self._persist(snapshot, projected)
            operation = next(item for item in snapshot.value["usage"]["operations"] if item["id"] == operation["id"])
        if "escalated_slot" in operation and operation["status"] == "intent" and "route_preflight" in operation and "send_admission" not in operation:
            return self._resume_prepared_escalation(snapshot, operation, adapter)
        try:
            receipt = _observation(adapter.reconcile(deepcopy(operation)), operation)
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            if "monitoring" in record:
                category = getattr(exc, "category", "transient-outage")
                if unresolved_disposition(record, category, operation_id, self.clock(), getattr(exc, "retry_after", None)):
                    return self._handback(snapshot, record, decision_reason(category))
            record["state"]["handback"] = {"reason": "repair observation remains unresolved: " + type(exc).__name__, "finding": None}
            snapshot = self._persist(snapshot, record)
            return cancel_expired(self.store, snapshot, operation_id, adapter, self.clock())
        if "monitoring" in record and receipt.get("worker_state") not in {"queued", "active"} and receipt.get("terminal_turn") is not True and receipt.get("worker_state") != "error":
            if unresolved_disposition(record, "uncertain-effect", operation_id, self.clock()):
                return self._handback(snapshot, record, decision_reason("uncertain-effect"))
            return self._waiting(snapshot, record, operation, receipt)
        if "monitoring" in record and receipt.get("worker_state") in {"queued", "active"}:
            clear_disposition(record)
            return self._waiting(snapshot, record, operation, receipt)
        snapshot = self._project(snapshot, operation_id, receipt)
        return cancel_expired(self.store, snapshot, operation_id, adapter, self.clock())

    def _preflight_failure(self, snapshot, operation, exc):
        record = validate_record(snapshot.value)
        category = getattr(exc, "category", None)
        if category == "route-mismatch":
            record["repair"]["status"] = "stuck"
            return self._persist(snapshot, _handback(record, "authoritative escalated fallback is unavailable or mismatched; choose an approved route or stop"))
        if "monitoring" in record:
            if unresolved_disposition(record, category if category in {"uncertain-effect", "transient-outage", "ambiguous-missing-session"} else "uncertain-effect", operation["id"], self.clock()):
                return self._handback(snapshot, record, decision_reason(category if category in {"uncertain-effect", "transient-outage", "ambiguous-missing-session"} else "uncertain-effect"))
            return self._persist(snapshot, record)
        return self._handback(snapshot, record, "escalated host preflight remains uncertain; reconcile the exact idle session")

    def _resume_prepared_escalation(self, snapshot, operation, adapter):
        """Finish a prepared idle session after a crash, preserving its exact UUID."""
        if not hasattr(adapter, "confirm_escalated"):
            return self._handback(snapshot, validate_record(snapshot.value), "prepared escalated session cannot be authoritatively confirmed")
        try:
            identity = adapter.confirm_escalated(deepcopy(operation))
            if identity != operation["route_preflight"]:
                raise InterimDispatchError("prepared escalated session route changed before admission")
            _bind_worker_hint(adapter, snapshot, operation, self.store.repository)
            snapshot, allowed = InterimFixtureCoordinator(self.store, clock=self.clock)._admit_send(snapshot, operation["id"])
            if not allowed:
                return snapshot
            receipt = _observation(adapter.send(deepcopy(operation)), operation)
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            record = validate_record(snapshot.value)
            if "send_admission" not in next(item for item in record["usage"]["operations"] if item["id"] == operation["id"]):
                return self._preflight_failure(snapshot, operation, exc)
            return snapshot  # admitted ambiguity is reconciled by exact ID on the next wake
        return self._project(snapshot, operation["id"], receipt)

    def _pending(self, record):
        phase = record["repair"]["status"].removeprefix("waiting-")
        return next(item for item in reversed(record["usage"]["operations"]) if item["phase"] == phase and item["slice"] == record["repair"]["slice_id"])

    def _cycle(self, record, operation):
        policy = record["repair"]
        diagnosis = next(item for item in policy["diagnoses"] if item["id"] == policy["batch"]["diagnosis_id"])
        repair_operation = operation if operation["phase"] == "repair" else next(
            item for item in reversed(record["usage"]["operations"])
            if item["phase"] == "repair" and item["slice"] == policy["slice_id"] and item["repair_attempt"] == operation["repair_attempt"]
            and (not operation.get("escalated_verify") or item["id"] == operation["escalated_verify"]))
        return {"id": f"cycle-{operation['repair_attempt']}", "attempt": operation["repair_attempt"], "diagnosis_id": diagnosis["id"], "experiment_id": diagnosis["next_experiment"]["id"], "repair_operation_id": repair_operation["id"], "verify_operation_id": operation["id"] if operation["phase"] == "repair-verify" else None, "outcome": "incomplete", "finding": deepcopy(policy["opening"]["finding"])}

    def _project(self, snapshot, operation_id, receipt):
        """Atomically retain a terminal result and its policy transition.

        Queued/active observations leave counters untouched. A replay sees either
        the pending operation or the entire projected transition, never a result
        whose diagnosis/cycle accounting still needs an in-memory continuation.
        """
        record = validate_record(snapshot.value)
        clear_disposition(record)
        operation = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)
        if receipt.get("result_unusable") and receipt.get("terminal_turn") is True:
            return self._persist_unusable(snapshot, record, operation_id, receipt,
                                          InterimDispatchError("terminal host result is unusable"),
                                          operation["phase"] + " result is unusable")
        if receipt.get("terminal_turn") is not True:
            if receipt.get("worker_state") in {"queued", "active", "unknown"} or receipt.get("transport") in {"timeout", "unknown"}:
                return self._waiting(snapshot, record, operation, receipt)
            return self._persist_unusable(snapshot, record, operation_id, receipt, InterimDispatchError("terminal host turn lacks a structured terminal result"), "repair result is unusable")
        operation["receipt"], operation["status"] = deepcopy(receipt), "result"
        operation["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
        _observed(record, operation_id)
        policy, phase = record["repair"], operation["phase"]
        try:
            if phase == "diagnosis":
                diagnosis = receipt.get("diagnosis")
                if not isinstance(diagnosis, dict) or diagnosis.get("id") != operation["purpose"] or diagnosis.get("operation_id") != operation_id:
                    raise InterimDispatchError("diagnosis result is missing its durable identity")
                policy["diagnoses"].append(deepcopy(diagnosis))
                self._reforecast_if_needed(record, operation_id, "repair")
                if diagnosis.get("actionable") is not True:
                    policy["status"] = "handback"
                    _handback(record, diagnosis.get("blocker", "no actionable in-scope repair approach"))
                else:
                    policy["status"] = "repair-ready"
                    policy["batch"] = {"diagnosis_id": diagnosis["id"], "cycles": 0, "no_progress": 0, "credited_progress": []}
                    record["state"] = {"next_action": "repair", "candidate": deepcopy(policy["opening"]["revisions"]), "review": None, "handback": None}
            elif phase == "repair":
                if "escalated_slot" in operation:
                    diagnosis = receipt.get("diagnosis")
                    prior = [next(iter(item["conclusion"].values())) for item in policy["diagnoses"]]
                    _diagnosis(record, operation["task"], policy, diagnosis, prior)
                    if diagnosis["id"] != operation["purpose"] or diagnosis["operation_id"] != operation_id:
                        raise InterimDispatchError("escalated diagnosis differs from reserved operation")
                    policy["diagnoses"].append(deepcopy(diagnosis))
                    policy["batch"] = {"diagnosis_id": diagnosis["id"], "cycles": 0, "no_progress": 0, "credited_progress": []}
                    if diagnosis["actionable"] is not True:
                        policy["status"] = "stuck"
                        _handback(record, diagnosis["blocker"])
                        return self._persist(snapshot, record)
                cycle = self._cycle(record, operation)
                self._reforecast_if_needed(record, operation_id, "repair-verify")
                if receipt.get("transport") != "accepted" or receipt.get("task_success") is not True:
                    if "escalated_slot" in operation:
                        self._close_escalated_without_candidate(record, policy, "escalated worker produced no verifiable candidate")
                    else:
                        self._no_progress(record, policy, cycle, "repair terminated without a verifiable candidate; fresh Verify was not fabricated")
                else:
                    candidate = _worker(record, operation, "build", receipt)["candidate"]
                    policy["status"] = "repair-verify-ready"
                    record["state"] = {"next_action": "repair-verify", "candidate": deepcopy(candidate), "review": None, "handback": None}
            else:
                candidate = operation["candidate"]
                _worker(record, operation, "verify", receipt, candidate)
                cycle = self._cycle(record, operation)
                cycle["outcome"] = receipt.get("verdict")
                self._reforecast_if_needed(record, operation_id, "repair")
                accepted = receipt.get("progress", [])
                if not isinstance(accepted, list):
                    accepted = []
                seen = {digest(item["evidence"]) for item in policy["progress"]}
                fresh = [item for item in accepted if isinstance(item, dict) and item.get("id") not in policy["batch"]["credited_progress"] and isinstance(item.get("evidence"), list) and digest(item["evidence"]) not in seen]
                policy["progress"].extend(deepcopy(fresh))
                new_ids = [item["id"] for item in fresh]
                policy["batch"]["credited_progress"].extend(new_ids)
                if cycle["outcome"] == "pass" or new_ids:
                    policy["cycles"].append(cycle)
                    policy["batch"]["cycles"] += 1
                    if cycle["outcome"] == "pass":
                        policy["status"] = "completed"
                        record["state"] = {"next_action": "repair-complete", "candidate": deepcopy(candidate), "review": {"findings": deepcopy(receipt.get("nonblocking_findings", [])), "verdict": "pass"}, "handback": None}
                    else:
                        escalation = record["approval"].get("escalation_policy")
                        triggered = escalation and sum(item["outcome"] != "pass" for item in policy["cycles"]) >= escalation["trigger"]
                        exhausted = triggered and len(policy["escalated_slots"]) >= escalation["cycles_per_slice"]
                        policy["status"] = "stuck" if exhausted else "escalation-ready" if triggered else "diagnosis-required"
                        if exhausted:
                            _handback(record, "escalated repair allowance exhausted; retain independently verified progress and choose a new approved plan")
                        else:
                            record["state"] = {"next_action": "escalation" if triggered else "diagnosis", "candidate": deepcopy(candidate), "review": None, "handback": None}
                else:
                    if "escalated_verify" in operation:
                        policy["cycles"].append(cycle)
                        self._close_escalated_without_candidate(record, policy, "fresh Verify failed without independent progress")
                    else:
                        self._no_progress(record, policy, cycle, "repair batch made no independently verified progress")
            return self._persist(snapshot, record)
        except (InterimError, ValueError, KeyError, TypeError) as exc:
            prior = validate_record(snapshot.value)
            if "escalated_slot" in operation:
                self._close_escalated_without_candidate(prior, prior["repair"], "escalated result unusable after its reserved slot")
            elif phase != "diagnosis":
                cycle = self._cycle(prior, operation)
                self._no_progress(prior, prior["repair"], cycle, "repair policy projection is unusable", handback=True)
            return self._persist_unusable(snapshot, prior, operation_id, receipt, exc, phase + " result is unusable")

    def _close_escalated_without_candidate(self, record, policy, reason):
        allowance = record["approval"]["escalation_policy"]["cycles_per_slice"]
        exhausted = len(policy["escalated_slots"]) >= allowance
        policy["status"] = "stuck" if exhausted else "escalation-ready"
        if exhausted:
            _handback(record, reason + "; escalated allowance exhausted")
        else:
            record["state"] = {"next_action": "escalation", "candidate": deepcopy(record["state"].get("candidate", policy["opening"]["revisions"])), "review": None, "handback": None}

    def escalate_once(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object,
                      adapter: RepairAdapter, verify_adapter: RepairAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        task = _task(task, slice_id)
        policy = record.get("repair")
        if not isinstance(policy, dict) or "escalation_policy" not in record["approval"] or policy["slice_id"] != slice_id:
            raise InterimDispatchError("escalated repair lacks immutable run approval")
        if policy["status"] in {"waiting-repair", "waiting-repair-verify"}:
            return self.repair_once(snapshot, slice_id, task, adapter, verify_adapter)
        if policy["status"] != "escalation-ready":
            raise InterimDispatchError("escalation is not ready")
        if (limit := _limit(record, self.clock())):
            return self._handback(snapshot, record, limit)
        allowance = record["approval"]["escalation_policy"]["cycles_per_slice"]
        if len(policy["escalated_slots"]) >= allowance:
            policy["status"] = "stuck"
            return self._persist(snapshot, _handback(record, "escalated allowance exhausted"))
        snapshot, record = self._ensure_forecast_capacity(snapshot, record, "repair")
        slot = len(record["repair"]["escalated_slots"]) + 1
        operation = self._operation(record, task, "repair", len(record["repair"]["cycles"]) + 1,
                                    record["repair"]["opening"]["revisions"], f"escalation-{slot}")
        operation["escalated_slot"] = slot
        operation["route"] = route_for_operation(record["approval"], operation)
        operation["escalation_reason"] = "cumulative ordinary repair failures reached approved trigger"
        operation["prior_hypotheses"] = [next(iter(item["conclusion"].values())) for item in record["repair"]["diagnoses"]]
        operation["repair_context"] = {"opening": deepcopy(record["repair"]["opening"]),
                                       "failed_cycles": deepcopy(record["repair"]["cycles"])}
        snapshot = self._dispatch(snapshot, operation, adapter)
        record = validate_record(snapshot.value)
        if record["repair"]["status"] == "repair-verify-ready":
            return self.repair_once(snapshot, slice_id, task, adapter, verify_adapter)
        return snapshot

    def diagnose(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object, adapter: RepairAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
            raise InterimDispatchError("whole-run recovery state refuses repair continuation")
        task = _task(task, slice_id)
        repair = record.get("repair")
        if isinstance(repair, dict) and repair.get("status") == "waiting-diagnosis":
            return self.reconcile_pending(snapshot, self._pending(record)["id"], adapter)
        if not isinstance(repair, dict) or repair.get("status") != "diagnosis-required":
            raise InterimDispatchError("repair policy does not require a fresh diagnosis")
        limit = _limit(record, self.clock())
        if limit:
            return self._handback(snapshot, record, limit)
        try:
            snapshot, record = self._ensure_forecast_capacity(snapshot, record, "diagnosis")
        except InterimDispatchError as exc:
            return self._handback(snapshot, record, str(exc))
        repair = record["repair"]
        prior_diagnosis_attempts = sum(item["phase"] == "diagnosis" and item["slice"] == slice_id for item in record["usage"]["operations"])
        operation = self._operation(record, task, "diagnosis", len(repair["cycles"]) + 1, repair["opening"]["revisions"], f"diagnosis-{prior_diagnosis_attempts + 1}")
        operation["prior_hypotheses"] = [next(iter(item["conclusion"].values())) for item in repair["diagnoses"]]
        operation["repair_context"] = deepcopy(repair["opening"])
        return self._dispatch(snapshot, operation, adapter)

    def repair_once(self, snapshot: InterimCheckpointSnapshot, slice_id: str, task: object, repair_adapter: RepairAdapter, verify_adapter: RepairAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
            raise InterimDispatchError("whole-run recovery state refuses repair continuation")
        task = _task(task, slice_id)
        policy = record.get("repair")
        if not isinstance(policy, dict):
            raise InterimDispatchError("repair policy is not ready for one eligible repair")
        if policy["status"] in {"waiting-repair", "waiting-repair-verify"}:
            adapter = verify_adapter if policy["status"] == "waiting-repair-verify" else repair_adapter
            snapshot = self.reconcile_pending(snapshot, self._pending(record)["id"], adapter)
            record = validate_record(snapshot.value)
            if record["repair"]["status"] != "repair-verify-ready":
                return snapshot
        elif policy["status"] == "repair-ready":
            limit = _limit(record, self.clock())
            if limit:
                return self._handback(snapshot, record, limit)
            if policy["batch"]["cycles"] >= 3:
                policy["status"] = "stuck"
                return self._persist(snapshot, _handback(record, "repair batch exhausted its three no-progress cycles"))
            snapshot, record = self._ensure_forecast_capacity(snapshot, record, "repair")
            policy = record["repair"]
            diagnosis = next(item for item in policy["diagnoses"] if item["id"] == policy["batch"]["diagnosis_id"])
            operation = self._operation(record, task, "repair", len(policy["cycles"]) + 1, policy["opening"]["revisions"], diagnosis["next_experiment"]["id"])
            operation["repair_context"] = {"opening": deepcopy(policy["opening"]), "diagnosis": deepcopy(diagnosis)}
            snapshot = self._dispatch(snapshot, operation, repair_adapter)
            record = validate_record(snapshot.value)
            if record["repair"]["status"] != "repair-verify-ready":
                return snapshot
        elif policy["status"] != "repair-verify-ready":
            raise InterimDispatchError("repair policy is not ready for one eligible repair")
        # A successful repair is durable before admitting the independent Verify.
        policy = record["repair"]
        repair_operation = next(item for item in reversed(record["usage"]["operations"]) if item["phase"] == "repair" and item["slice"] == policy["slice_id"])
        limit = _limit(record, self.clock())
        if limit:
            self._no_progress(record, policy, self._cycle(record, repair_operation), limit + "; repair result retained and fresh Verify was not admitted", handback=True)
            return self._persist(snapshot, record)
        prior_verifies = [item for item in record["usage"]["operations"] if item["phase"] == "repair-verify" and item["slice"] == slice_id
                          and item.get("repair_attempt") == repair_operation["repair_attempt"]]
        verify_attempt = len(prior_verifies) + 1
        if verify_attempt > 3:
            policy["status"] = "stuck"
            return self._persist(snapshot, _handback(record, "fresh Verify recovery exhausted three unsuccessful attempts for the same candidate"))
        purpose = repair_operation["purpose"] if verify_attempt == 1 else repair_operation["purpose"] + f"-verify-{verify_attempt}"
        operation = self._operation(record, task, "repair-verify", repair_operation["repair_attempt"], record["state"]["candidate"], purpose)
        operation["verify_attempt"] = verify_attempt
        if "escalated_slot" in repair_operation:
            operation["escalated_verify"] = repair_operation["id"]
            operation["route"] = route_for_operation(record["approval"], operation)
            operation["verify_context"] = {"build_operation_id": repair_operation["id"],
                                           "candidate": deepcopy(record["state"]["candidate"]),
                                           "criteria": list(task["criteria"]),
                                           "artifact_id": repair_operation["receipt"]["evidence"]["artifact"]["id"]}
        return self._dispatch(snapshot, operation, verify_adapter)

    def revise_forecast(self, snapshot: InterimCheckpointSnapshot, forecast: object, operation_id: str, reason: str) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if "repair" not in record or not any(item["id"] == operation_id and item.get("receipt") for item in record["usage"]["operations"]):
            raise InterimDispatchError("reforecast requires a retained worker-result checkpoint")
        latest = next((item["id"] for item in reversed(record["usage"]["operations"]) if isinstance(item.get("receipt"), dict)), None)
        floor = self._forecast_floor(record)
        next_phase = "repair" if record["repair"].get("status") == "repair-ready" else None
        required = self._forecast_target(record, next_phase)
        if operation_id != latest or not isinstance(forecast, dict) or set(forecast) != set(floor) or any(type(value) is not int or value < required[name] for name, value in forecast.items()) or not isinstance(reason, str) or not reason:
            raise InterimDispatchError("reforecast is malformed")
        record["forecasts"]["revised"].append({"at": _at(self.clock()), "reason": reason, "forecast": deepcopy(forecast), "evidence": {"operation_id": operation_id, "reason": "verified worker-result checkpoint"}})
        return self._persist(snapshot, record)

"""S4 deterministic recovery and cooperative stop policy (fixture adapters only)."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .canonical import CanonicalError, canonical_bytes, digest
from .interim_identity import operation_identities
from .interim import InterimCheckpointSnapshot, InterimCheckpointStore, validate_record
from .interim_coordinator import InterimDispatchError, _at, _handback, _limit, _observed


class RecoveryPolicyError(ValueError): pass
def _fail(message: str) -> None: raise RecoveryPolicyError(message)
def _now() -> datetime: return datetime.now(timezone.utc)

def _observation(operation: dict[str, Any], receipt: object) -> dict[str, Any]:
    expected = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
    if not isinstance(receipt, dict) or receipt.get("observation") != expected:
        _fail("recovery receipt is not correlated to the durable operation")
    return receipt

def _recovery(record: dict[str, Any]) -> dict[str, Any]:
    return record.setdefault("recovery", {"status": "running", "wakes": [], "observations": [], "stop": None, "resume": None})


def wake_operation_id(record: dict[str, Any], wake_id: str) -> str:
    """Derive the one durable operation for an immutable logical wake."""
    if not isinstance(wake_id, str) or not wake_id:
        _fail("wake ID must be stable and non-empty")
    return "op-" + digest({"run": record["approval"]["run_id"], "wake": wake_id, "phase": "wake"})[7:23]


def reserve_wake_intent(record: dict[str, Any], wake_id: str, now: datetime) -> dict[str, Any]:
    """Add one wake intent, launch, charge, and recovery identity before I/O."""
    recovery = _recovery(record)
    operation_id = wake_operation_id(record, wake_id)
    for operation in record["usage"]["operations"]:
        if operation["id"] == operation_id:
            if wake_id not in recovery["wakes"]:
                recovery["wakes"].append(wake_id)
            return operation
    operation = {"id": operation_id, "slice": record["approval"]["slices"][0]["id"], "phase": "wake", **operation_identities(record["approval"]["run_id"], operation_id, "wake", record["approval"]["coordinator"]["session_id"]), "status": "reconcile-required", "issued_at": _at(now), "elapsed_seconds": 0}
    record["usage"]["operations"].append(operation)
    record["usage"]["launches"].append({"operation_id": operation_id, "phase": "wake", "issued_at": operation["issued_at"]})
    record["usage"]["charges"].append({"operation_id": operation_id, "work_units": 1, "status": "pending", "charged_at": operation["issued_at"]})
    recovery["wakes"].append(wake_id)
    return operation

def _timestamp(value: object, label: str) -> None:
    if not isinstance(value, str) or "T" not in value or not value.endswith("Z"):
        _fail(label + " must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecoveryPolicyError(label + " must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(label + " must be a timezone-aware UTC timestamp")

def _nonterminal_operations(record: dict[str, Any]) -> set[str]:
    """Durable worker/coordinator work that cannot disappear during a stop."""
    return {
        item["id"] for item in record["usage"]["operations"]
        if item["phase"] != "wake" and item["status"] in {
            "intent", "active", "reconcile-required", "cancellation-uncertain",
        }
    }

def _stop_targets(record: dict[str, Any], recovery: dict[str, Any]) -> set[str]:
    workers = {item["id"] for item in record["usage"]["operations"] if item["phase"] != "wake"}
    # A later empty inventory does not erase durably observed nonterminal work.
    return (_nonterminal_operations(record)
            | {item["operation_id"] for item in recovery["stop"]["cancellations"]}
            | {item["operation_id"] for item in recovery["observations"] if item["operation_id"] in workers and item["state"] != "terminal"})

def _confirmed_stop(record: dict[str, Any], recovery: dict[str, Any]) -> bool:
    stop = recovery["stop"]
    if not isinstance(stop, dict) or stop.get("prefix_removed") is not True or stop.get("uncertainty") is not None:
        return False
    cancellations = {item["operation_id"]: item for item in stop["cancellations"]}
    observations = {item["operation_id"]: item for item in recovery["observations"]}
    required = _stop_targets(record, recovery)
    return all(operation_id in cancellations and cancellations[operation_id]["state"] == "cancelled" and operation_id in observations and observations[operation_id]["state"] == "terminal" for operation_id in set(cancellations) | required)

def validate_recovery(record: dict[str, Any]) -> None:
    value = record["recovery"]
    if not isinstance(value, dict) or set(value) != {"status", "wakes", "observations", "stop", "resume"} or value["status"] not in {"running", "stopping", "stopped", "resumed", "uncertain"}:
        _fail("recovery state has unknown or missing fields")
    if not isinstance(value["wakes"], list) or len(value["wakes"]) != len(set(value["wakes"])) or any(not isinstance(x, str) or not x for x in value["wakes"]): _fail("recovery wakes must be unique stable IDs")
    operations = {item["id"]: item for item in record["usage"]["operations"]}; seen: set[str] = set()
    if not isinstance(value["observations"], list): _fail("recovery observations are malformed")
    for item in value["observations"]:
        if not isinstance(item, dict) or set(item) != {"operation_id", "state", "observed_at", "receipt"} or item.get("operation_id") not in operations or item["operation_id"] in seen or item.get("state") not in {"active", "queued", "terminal", "unknown"}: _fail("recovery observation is malformed")
        _timestamp(item["observed_at"], "recovery observation observed_at")
        receipt = _observation(operations[item["operation_id"]], item["receipt"])
        if receipt.get("worker_state") != item["state"]: _fail("recovery observation wrapper disagrees with correlated receipt")
        seen.add(item["operation_id"])
    stop = value["stop"]
    if stop is not None:
        if not isinstance(stop, dict) or set(stop) != {"intent_at", "instruction", "prefix_removed", "cancellations", "uncertainty"} or not isinstance(stop.get("instruction"), str) or not stop["instruction"] or type(stop.get("prefix_removed")) is not bool or not isinstance(stop.get("cancellations"), list) or stop["uncertainty"] is not None and (not isinstance(stop["uncertainty"], str) or not stop["uncertainty"]): _fail("whole-run stop record is malformed")
        _timestamp(stop["intent_at"], "whole-run stop intent_at")
        cancelled: set[str] = set()
        for item in stop["cancellations"]:
            if not isinstance(item, dict) or set(item) != {"operation_id", "state", "receipt"} or item.get("operation_id") not in operations or item["operation_id"] in cancelled or item.get("state") not in {"cancelled", "uncertain", "queued"}: _fail("whole-run cancellation record is malformed")
            receipt = _observation(operations[item["operation_id"]], item["receipt"])
            if receipt.get("state") != item["state"]: _fail("whole-run cancellation wrapper disagrees with correlated receipt")
            cancelled.add(item["operation_id"])
    resume = value["resume"]
    if resume is not None:
        if not isinstance(resume, dict) or set(resume) != {"instruction", "resumed_at"} or not isinstance(resume.get("instruction"), str) or not resume["instruction"]: _fail("resume record is malformed")
        _timestamp(resume.get("resumed_at"), "resume resumed_at")
    if value["status"] == "stopped" and not _confirmed_stop(record, value): _fail("stopped recovery must have a confirmed whole-run stop")
    if value["status"] == "resumed" and resume is None: _fail("resumed recovery needs explicit human instruction")

@dataclass(frozen=True)
class _AdapterFailure:
    boundary: str
    operation_id: str | None
    kind: str
    detail: str

    def message(self) -> str:
        identity = " for " + self.operation_id if self.operation_id else ""
        return self.boundary + identity + " " + self.kind + ": " + self.detail


def _adapter_result(boundary: str, invoke: Callable[[], Any], validate: Callable[[Any], Any], operation: dict[str, Any] | None = None) -> Any:
    """External errors and invalid data are separate from policy/storage errors.

    Adapters normalize provider/decoder/auth/quota failures to InterimDispatchError
    (or an OSError transport subtype). Unexpected programmer errors propagate.
    Validation is pure and raises only RecoveryPolicyError for malformed facts.
    Never put projection, clocks or checkpoint publication inside either catch.
    """
    operation_id = operation["id"] if operation is not None else None
    try:
        raw = invoke()
    except (InterimDispatchError, OSError) as exc:
        # Do not persist unbounded provider text, credentials, or invalid Unicode.
        return _AdapterFailure(boundary, operation_id, "unavailable", type(exc).__name__)
    try:
        return validate(raw)
    except RecoveryPolicyError as exc:
        return _AdapterFailure(boundary, operation_id, "malformed", str(exc))


def _portable_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    try:
        canonical_bytes(receipt)
    except (CanonicalError, RecursionError):
        _fail("retained receipt is not canonically portable")
    return deepcopy(receipt)


def _worker_observation(operation: dict[str, Any], raw: object, consume_elapsed: bool = False) -> dict[str, Any]:
    receipt = _observation(operation, raw)
    receipt = deepcopy(receipt)
    if receipt.get("terminal_turn") is True:
        receipt.setdefault("worker_state", "terminal")
    state = receipt.get("worker_state")
    if not isinstance(state, str) or state not in {"active", "queued", "terminal", "unknown"}:
        _fail("worker_state must be active, queued, terminal, or unknown")
    if consume_elapsed:
        if receipt.get("transport") != "accepted":
            _fail("wake receipt must be explicitly accepted")
        elapsed = receipt.get("elapsed_seconds", 0)
        if type(elapsed) is not int or elapsed < 0:
            _fail("consumed elapsed_seconds must be a nonnegative integer")
    return _portable_receipt(receipt)


def _cancellation(operation: dict[str, Any], raw: object) -> dict[str, Any]:
    receipt = _observation(operation, raw)
    state = receipt.get("state")
    if not isinstance(state, str) or state not in {"cancelled", "queued", "uncertain"}:
        _fail("cancellation state must be cancelled, queued, or uncertain")
    return _portable_receipt(receipt)


def _coordinators(approval: dict[str, Any], raw: object) -> bool:
    if not isinstance(raw, list):
        _fail("coordinator enumeration must be a list")
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("session_id"), str) or not item["session_id"]:
            _fail("coordinator identity must be a nonempty session_id")
    return len(raw) == 1 and raw[0]["session_id"] == approval["coordinator"]["session_id"]


def _prefix_removed(prefix: str, raw: object) -> bool:
    if not isinstance(raw, dict) or raw.get("prefix") != prefix or raw.get("readback_removed") is not True:
        _fail("prefix removal needs exact prefix and confirmed readback")
    return True


def _owned_workers(record: dict[str, Any], raw: object) -> list[tuple[str, str, dict[str, Any]]]:
    if not isinstance(raw, list):
        _fail("owned-worker enumeration must be a list")
    operations = {x["id"]: x for x in record["usage"]["operations"] if x["phase"] != "wake"}
    result = []; seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"operation_id", "state", "receipt"}:
            _fail("owned-worker item must have operation_id, state, and receipt")
        operation_id = item["operation_id"]
        if not isinstance(operation_id, str) or operation_id in seen or operation_id not in operations:
            _fail("owned-worker identity is duplicate or not durably identified")
        state = item["state"]
        if not isinstance(state, str) or state not in {"active", "queued", "terminal", "unknown"}:
            _fail("owned-worker state must be active, queued, terminal, or unknown")
        receipt = _worker_observation(operations[operation_id], item["receipt"])
        if receipt["worker_state"] != state:
            _fail("owned-worker wrapper disagrees with correlated receipt")
        seen.add(operation_id); result.append((operation_id, state, receipt))
    return result


class RecoveryAdapter(Protocol):
    """Normalize external failures to InterimDispatchError or OSError.

    Return provider facts without interpreting them as policy or durable success.
    Other exceptions are programmer errors, not provider observations.
    """
    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]: ...
    def observe(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def remove_prefix(self, session_id: str, prefix: str) -> dict[str, Any]: ...
    def cancel(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def owned_workers(self, run_id: str) -> list[dict[str, Any]]: ...


class WakeSendAdapter(Protocol):
    """Narrow host seam for one already-reserved coordinator wake."""
    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]: ...
    def send_wake(self, operation: dict[str, Any]) -> dict[str, Any]: ...


class InterimRecoveryCoordinator:
    def __init__(self, store: InterimCheckpointStore, clock: Callable[[], datetime] = _now,
                 monitor_internal: bool = False):
        self.store, self.clock, self.monitor_internal = store, clock, monitor_internal

    def _persist(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any]) -> InterimCheckpointSnapshot:
        # The working projection is isolated from snapshot.value. Validate the
        # complete projection before publication; neither failure is provider data.
        projected = validate_record(record)
        canonical_bytes(projected)
        if self.monitor_internal:
            # Same-ID monitor writes stay internal except an unambiguous
            # terminal/human handback: that must still retire this run before
            # a later delivery performs its observe-only reconciliation.
            from .interim_monitor import _terminal
            return (self.store.persist_lifecycle(snapshot, projected) if _terminal(projected)
                    else self.store.persist(snapshot, projected))
        return self.store.persist_lifecycle(snapshot, projected)

    def _terminal(self, record: dict[str, Any]) -> bool:
        return record.get("recovery", {}).get("status") in {"stopped", "uncertain"} or record["state"]["next_action"] == "review-ready" or record.get("repair", {}).get("status") in {"stuck", "handback"}

    def _coordinator(self, record: dict[str, Any], adapter: RecoveryAdapter) -> bool | _AdapterFailure:
        approval = deepcopy(record["approval"])
        return _adapter_result("coordinators", lambda: adapter.coordinators(deepcopy(approval)), lambda raw: _coordinators(approval, raw))

    def _observe(self, operation: dict[str, Any], adapter: RecoveryAdapter) -> dict[str, Any] | _AdapterFailure:
        return _adapter_result("observe", lambda: adapter.observe(deepcopy(operation)), lambda raw: _worker_observation(operation, raw, operation["phase"] == "wake"), operation)

    def _owned(self, record: dict[str, Any], adapter: RecoveryAdapter) -> list[tuple[str, str, dict[str, Any]]] | _AdapterFailure:
        return _adapter_result("owned_workers", lambda: adapter.owned_workers(record["approval"]["run_id"]), lambda raw: _owned_workers(record, raw))

    def _remember(self, recovery: dict[str, Any], operation_id: str, state: str, receipt: dict[str, Any]) -> None:
        recovery["observations"] = [x for x in recovery["observations"] if x["operation_id"] != operation_id]
        recovery["observations"].append({"operation_id": operation_id, "state": state, "observed_at": _at(self.clock()), "receipt": deepcopy(receipt)})

    def _stop_handback(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], message: str) -> InterimCheckpointSnapshot:
        message = "stop " + message
        recovery = _recovery(record)
        recovery["stop"]["uncertainty"] = message
        recovery["status"] = "uncertain"
        if "monitoring" in record:
            # The exact cancellation remains a monitored obligation until a
            # bounded recheck resolves it or produces a safety decision.
            return self._persist(snapshot, record)
        return self._persist(snapshot, _handback(record, message))

    def _wake_intent(self, record: dict[str, Any], wake_id: str) -> dict[str, Any]:
        return reserve_wake_intent(record, wake_id, self.clock())

    def _settle_reserved_wake(self, snapshot: InterimCheckpointSnapshot, wake_id: str,
                               adapter: RecoveryAdapter, coordinator_checked: bool = False) -> InterimCheckpointSnapshot:
        """Observe one already-persisted wake; retries reconcile, never resend it."""
        record = validate_record(snapshot.value)
        operation_id = wake_operation_id(record, wake_id)
        operation = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
        if operation is None or operation.get("phase") != "wake":
            _fail("wake reconciliation lacks its durable operation")
        if operation["status"] == "accounted":
            return snapshot
        if not coordinator_checked:
            coordinated = self._coordinator(record, adapter)
            if isinstance(coordinated, _AdapterFailure):
                return self._automatic_failure(snapshot, record, wake_id, coordinated, operation)
            if not coordinated:
                _recovery(record)["status"] = "uncertain"
                return self._persist(snapshot, _handback(record, "coordinators missing, ambiguous, or different from immutable approval"))
        receipt = self._observe(operation, adapter)
        if isinstance(receipt, _AdapterFailure):
            return self._automatic_failure(snapshot, record, wake_id, receipt, operation)
        return self._record_wake_receipt(snapshot, record, wake_id, operation, receipt)

    def _record_wake_receipt(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any],
                             wake_id: str, operation: dict[str, Any], receipt: dict[str, Any]) -> InterimCheckpointSnapshot:
        """Settle one validated receipt without creating or dispatching anything."""
        recovery = _recovery(record)
        state = receipt["worker_state"]
        self._remember(recovery, operation["id"], state, receipt)
        if state == "unknown":
            return self._persist(snapshot, _handback(record, "observe for " + operation["id"] + " remains unknown; exact wake requires reconciliation"))
        operation["receipt"] = receipt; operation["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
        operation["status"] = "accounted"; _observed(record, operation["id"])
        if state != "terminal" and not (self.monitor_internal and state in {"queued", "active"}):
            _handback(record, "observe for " + operation["id"] + " remains " + state + "; exact wake requires reconciliation")
        return self._persist(snapshot, record)

    def reconcile_wake(self, snapshot: InterimCheckpointSnapshot, wake_id: str,
                       adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        """Reconcile the exact watchdog reservation without creating another wake."""
        record = validate_record(snapshot.value)
        recovery = _recovery(record)
        if recovery["status"] == "stopping" or self._terminal(record):
            return self._persist(snapshot, _handback(record, "late automatic wake refused for terminal, stopping, or uncertain run"))
        return self._settle_reserved_wake(snapshot, wake_id, adapter)

    def send_wake(self, snapshot: InterimCheckpointSnapshot, wake_id: str,
                  adapter: WakeSendAdapter) -> InterimCheckpointSnapshot:
        """Send one exact coordinator wake after its intent/charge was persisted."""
        record = validate_record(snapshot.value)
        recovery = _recovery(record)
        if recovery["status"] == "stopping" or self._terminal(record):
            return self._persist(snapshot, _handback(record, "late automatic wake refused for terminal, stopping, or uncertain run"))
        operation_id = wake_operation_id(record, wake_id)
        operation = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
        if operation is None or operation.get("phase") != "wake":
            _fail("wake send lacks its durable operation")
        if operation["status"] == "accounted":
            return snapshot
        coordinated = self._coordinator(record, adapter)
        if isinstance(coordinated, _AdapterFailure):
            return self._automatic_failure(snapshot, record, wake_id, coordinated, operation)
        if not coordinated:
            recovery["status"] = "uncertain"
            return self._persist(snapshot, _handback(record, "coordinators missing, ambiguous, or different from immutable approval"))
        receipt = _adapter_result("wake-send", lambda: adapter.send_wake(deepcopy(operation)),
                                  lambda raw: _worker_observation(operation, raw, True), operation)
        if isinstance(receipt, _AdapterFailure):
            return self._automatic_failure(snapshot, record, wake_id, receipt, operation)
        return self._record_wake_receipt(snapshot, record, wake_id, operation, receipt)

    def _automatic_failure(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any], wake_id: str, failure: _AdapterFailure, operation: dict[str, Any] | None = None) -> InterimCheckpointSnapshot:
        recovery = _recovery(record)
        if operation is None and not _limit(record, self.clock()):
            operation = self._wake_intent(record, wake_id)
        if operation is not None:
            receipt = {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "transport": "unknown", "worker_state": "unknown", "uncertainty": failure.message()}
            # Keep trustworthy usage/receipts. An unavailable observation cannot
            # replace earlier host facts with invented provider evidence.
            if operation["phase"] == "wake" and "receipt" not in operation:
                operation["receipt"] = deepcopy(receipt)
            if not any(x["operation_id"] == operation["id"] for x in recovery["observations"]):
                self._remember(recovery, operation["id"], "unknown", receipt)
        return self._persist(snapshot, _handback(record, "automatic recovery " + failure.message()))

    def wake(self, snapshot: InterimCheckpointSnapshot, wake_id: str, adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if not isinstance(wake_id, str) or not wake_id:
            raise InterimDispatchError("wake ID must be stable and non-empty")
        recovery = _recovery(record)
        if recovery["status"] == "stopping" or self._terminal(record):
            return self._persist(snapshot, _handback(record, "late automatic wake refused for terminal, stopping, or uncertain run"))
        if wake_id in recovery["wakes"]:
            return self._settle_reserved_wake(snapshot, wake_id, adapter)
        limit = _limit(record, self.clock())
        if limit:
            return self._persist(snapshot, _handback(record, "selected ceiling prevents automatic wake admission: " + limit))
        coordinated = self._coordinator(record, adapter)
        if isinstance(coordinated, _AdapterFailure):
            return self._automatic_failure(snapshot, record, wake_id, coordinated)
        if not coordinated:
            recovery["status"] = "uncertain"
            return self._persist(snapshot, _handback(record, "coordinators missing, ambiguous, or different from immutable approval"))
        operation = self._wake_intent(record, wake_id)
        snapshot = self._persist(snapshot, record)  # intent and charge before observation
        return self._settle_reserved_wake(snapshot, wake_id, adapter, coordinator_checked=True)

    def recover(self, approved_record: dict[str, Any], wake_id: str, adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        snapshot = self.store.reload(approved_record); record = validate_record(snapshot.value)
        if not isinstance(wake_id, str) or not wake_id:
            raise InterimDispatchError("wake ID must be stable and non-empty")
        if record.get("recovery", {}).get("status") == "stopping":
            return self._continue_stop(snapshot, adapter)
        if self._terminal(record):
            return self.wake(snapshot, wake_id, adapter)
        recovery = _recovery(record)
        coordinated = self._coordinator(record, adapter)
        if isinstance(coordinated, _AdapterFailure):
            return self._automatic_failure(snapshot, record, wake_id, coordinated)
        if not coordinated:
            recovery["status"] = "uncertain"
            return self._persist(snapshot, _handback(record, "coordinators missing, ambiguous, or different from immutable approval"))
        for operation in record["usage"]["operations"]:
            if operation["status"] not in {"intent", "reconcile-required", "active", "cancellation-uncertain"}:
                continue
            receipt = self._observe(operation, adapter)
            if isinstance(receipt, _AdapterFailure):
                return self._automatic_failure(snapshot, record, wake_id, receipt, operation)
            state = receipt["worker_state"]
            self._remember(recovery, operation["id"], state, receipt)
            if operation["phase"] == "wake" and state == "terminal":
                operation["receipt"] = receipt; operation["elapsed_seconds"] = receipt.get("elapsed_seconds", 0)
                operation["status"] = "accounted"; _observed(record, operation["id"])
            if state != "terminal":
                return self._persist(snapshot, _handback(record, "observe for " + operation["id"] + " remains " + state + "; exact operation requires reconciliation"))
        return self.wake(self._persist(snapshot, record), wake_id, adapter)

    def stop(self, snapshot: InterimCheckpointSnapshot, instruction: str, adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if not isinstance(instruction, str) or not instruction:
            raise InterimDispatchError("whole-run stop requires explicit human instruction")
        recovery = _recovery(record)
        if recovery["status"] == "stopped":
            return snapshot
        if recovery["status"] != "stopping":
            # An explicit retry reconciles the existing stop. A stop after a
            # successful resume is a new intent with new cancellation work.
            if recovery["status"] != "uncertain" or recovery["stop"] is None:
                recovery["stop"] = {"intent_at": _at(self.clock()), "instruction": instruction, "prefix_removed": False, "cancellations": [], "uncertainty": None}
            recovery["status"] = "stopping"
            snapshot = self._persist(snapshot, record)
        return self._continue_stop(snapshot, adapter)

    def _continue_stop(self, snapshot: InterimCheckpointSnapshot, adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); recovery = _recovery(record); stop = recovery["stop"]
        if recovery["status"] != "stopping" or not isinstance(stop, dict):
            raise InterimDispatchError("only a durable stopping checkpoint can continue stop reconciliation")
        if not stop["prefix_removed"]:
            approval = record["approval"]
            renamed = _adapter_result("remove_prefix", lambda: adapter.remove_prefix(approval["coordinator"]["session_id"], approval["whole_run_stop"]), lambda raw: _prefix_removed(approval["whole_run_stop"], raw))
            if isinstance(renamed, _AdapterFailure):
                return self._stop_handback(snapshot, record, renamed.message())
            stop["prefix_removed"] = True
            snapshot = self._persist(snapshot, record)
        operations = {x["id"]: x for x in record["usage"]["operations"] if x["phase"] != "wake"}
        targets = _stop_targets(record, recovery)
        for round_number in range(2):
            owned = self._owned(record, adapter)
            if isinstance(owned, _AdapterFailure):
                return self._stop_handback(snapshot, record, owned.message())
            for operation_id, state, receipt in owned:
                self._remember(recovery, operation_id, state, receipt); targets.add(operation_id)
            snapshot = self._persist(snapshot, record)
            cancellations = {x["operation_id"]: x for x in stop["cancellations"]}
            for operation_id in sorted(targets):
                if operation_id in cancellations and cancellations[operation_id]["state"] == "cancelled":
                    continue
                operation = operations[operation_id]
                receipt = _adapter_result("cancel", lambda: adapter.cancel(deepcopy(operation)), lambda raw: _cancellation(operation, raw), operation)
                if isinstance(receipt, _AdapterFailure):
                    message = receipt.message()
                    receipt = {"observation": {n: operation[n] for n in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "uncertain", "reason": message}
                else:
                    message = "cancel for " + operation_id + " remains " + receipt["state"]
                cancellation = {"operation_id": operation_id, "state": receipt["state"], "receipt": receipt}
                stop["cancellations"] = [x for x in stop["cancellations"] if x["operation_id"] != operation_id] + [cancellation]
                snapshot = self._persist(snapshot, record)
                if receipt["state"] != "cancelled":
                    return self._stop_handback(snapshot, record, message)
            for operation_id in sorted(targets):
                receipt = self._observe(operations[operation_id], adapter)
                if isinstance(receipt, _AdapterFailure):
                    return self._stop_handback(snapshot, record, receipt.message())
                state = receipt["worker_state"]
                self._remember(recovery, operation_id, state, receipt)
                if state != "terminal":
                    return self._stop_handback(snapshot, record, "observe for " + operation_id + " remains " + state)
                snapshot = self._persist(snapshot, record)
            after = self._owned(record, adapter)
            if isinstance(after, _AdapterFailure):
                return self._stop_handback(snapshot, record, after.message())
            retry = False
            for operation_id, state, receipt in after:
                self._remember(recovery, operation_id, state, receipt)
                if operation_id not in targets or state != "terminal":
                    retry = True
                targets.add(operation_id)
            snapshot = self._persist(snapshot, record)
            if retry:
                if round_number == 1:
                    states = ", ".join(sorted({state for _, state, _ in after}))
                    return self._stop_handback(snapshot, record, "owned_workers changed during race-closing reconciliation; observed states: " + states)
                continue
            break
        recovery["status"] = "stopped"; stop["uncertainty"] = None
        return self._persist(snapshot, _handback(record, "whole-run stop observed for known workers; cooperative effects remain non-guaranteed"))

    def resume(self, snapshot: InterimCheckpointSnapshot, instruction: str, adapter: RecoveryAdapter) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); recovery = record.get("recovery")
        if not isinstance(instruction, str) or not instruction:
            raise InterimDispatchError("resume requires explicit human instruction")
        if not isinstance(recovery, dict) or recovery.get("status") != "stopped":
            raise InterimDispatchError("only a confirmed interim whole-run stop may be resumed")
        if not _confirmed_stop(record, recovery):
            raise InterimDispatchError("every durable nonterminal operation must have confirmed cancellation and terminal observation before resume")
        if _limit(record, self.clock()):
            return self._persist(snapshot, _handback(record, "selected ceiling prevents resume"))
        coordinated = self._coordinator(record, adapter)
        if isinstance(coordinated, _AdapterFailure):
            return self._persist(snapshot, _handback(record, "resume refused: " + coordinated.message()))
        if not coordinated:
            return self._persist(snapshot, _handback(record, "resume refused: coordinators missing, ambiguous, or different from immutable approval"))
        operations = {x["id"]: x for x in record["usage"]["operations"]}
        cancellation_ids = {x["operation_id"] for x in recovery["stop"]["cancellations"]}
        owned = self._owned(record, adapter)
        if isinstance(owned, _AdapterFailure):
            return self._persist(snapshot, _handback(record, "resume refused: " + owned.message()))
        for operation_id, state, receipt in owned:
            if operation_id not in cancellation_ids or state != "terminal":
                return self._persist(snapshot, _handback(record, "resume refused: owned_workers for " + operation_id + " is " + state + (" and unmatched" if operation_id not in cancellation_ids else "")))
            self._remember(recovery, operation_id, state, receipt)
        for cancellation in recovery["stop"]["cancellations"]:
            operation = operations[cancellation["operation_id"]]
            receipt = self._observe(operation, adapter)
            if isinstance(receipt, _AdapterFailure):
                return self._persist(snapshot, _handback(record, "resume refused: " + receipt.message()))
            if receipt["worker_state"] != "terminal":
                return self._persist(snapshot, _handback(record, "resume refused: observe for " + operation["id"] + " remains " + receipt["worker_state"]))
            self._remember(recovery, operation["id"], "terminal", receipt)
        recovery["status"] = "resumed"; recovery["resume"] = {"instruction": instruction, "resumed_at": _at(self.clock())}
        record["state"] = {"next_action": "recovered", "candidate": record["state"].get("candidate"), "review": record["state"].get("review"), "handback": None}
        return self._persist(snapshot, record)

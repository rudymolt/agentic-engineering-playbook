"""Offline, coordinator-only monitoring for explicitly approved interim runs.

The monitor is deliberately a narrow policy seam.  It treats GitHub deliveries
as locators, reloads the exact durable checkpoint, and reuses the existing
watchdog reservation/reconciliation path.  It never discovers work, creates a
session, or selects a worker.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import time
from typing import Any, Callable, Protocol
from uuid import UUID

from .canonical import digest
from .interim import InterimCheckpointError, InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, validate_record
from .interim_recovery import _confirmed_stop, wake_operation_id
from .interim_disposition import ObservationFailure, IMMEDIATE, decision_reason, eligible as recovery_check_eligible, unresolved as unresolved_disposition, clear as clear_disposition, notice_stop
from .interim_coordinator import _handback
from .interim_watchdog import MODE, PREFIX, resume_and_reconcile, wake_id


class MonitoringPolicyError(ValueError):
    pass


def _fail(message: str) -> None:
    raise MonitoringPolicyError(message)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(name + " must be a non-empty string")
    return value


def _utc(value: object, name: str) -> str:
    value = _text(value, name)
    if "T" not in value or not value.endswith("Z"):
        _fail(name + " must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise MonitoringPolicyError(name + " must be a UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        _fail(name + " must be a UTC timestamp")
    return value


def _workspace(value: object) -> str:
    value = _text(value, "coordinator workspace ID")
    try:
        UUID(value)
    except ValueError as exc:
        raise MonitoringPolicyError("coordinator workspace ID must be a UUID") from exc
    return value


def _commit(value: object, name: str = "checkpoint parent commit") -> str:
    value = _text(value, name)
    if len(value) not in {40, 64} or any(char not in "0123456789abcdef" for char in value):
        _fail("checkpoint commit must be a lowercase Git object ID")
    return value


def _terminal(record: dict[str, Any]) -> str | None:
    recovery = record.get("recovery", {})
    if recovery.get("status") in {"stopping", "stopped"} or (recovery.get("status") == "uncertain" and recovery.get("stop") is None):
        return "whole-run-" + recovery["status"]
    if record["state"].get("next_action") in {"review-ready", "handback"}:
        return "terminal-or-human-handback"
    if record.get("repair", {}).get("status") in {"stuck", "handback"}:
        return "repair-human-blocked"
    return None


def _title(record: dict[str, Any]) -> str:
    approval = record["approval"]
    return " ".join((PREFIX, "run=" + approval["run_id"], "mode=" + MODE,
                     "checkpoint=" + approval["checkpoint"]["ref"],
                     "progress=" + approval["progress_checkpoint_policy"],
                     "hard_limits=" + ("none" if approval["hard_limits"] == "none" else "selected")))


def generation(record: dict[str, Any], checkpoint_parent_commit: str | None, epoch: int, reason: str) -> str:
    return "wake-" + digest({"run": record["approval"]["run_id"], "ref": record["approval"]["checkpoint"]["ref"], "checkpoint_parent": checkpoint_parent_commit,
                              "epoch": epoch, "reason": reason, "protocol": 1})[7:23]


def enroll(record: object, coordinator_workspace_id: object, checkpoint_parent_commit: object = None) -> dict[str, Any]:
    """Add monitoring at genesis, or while advancing exactly one known parent.

    Genesis uses ``None``: its resulting control commit must have no parent.
    Any later enrollment is forbidden; transitions carry the exact immutable
    parent commit supplied by the CAS snapshot they advance from.
    """
    record = validate_record(record)
    if "monitoring" in record:
        _fail("run is already enrolled")
    workspace = _workspace(coordinator_workspace_id)
    if checkpoint_parent_commit is not None:
        _commit(checkpoint_parent_commit)
    reason = _terminal(record)
    state = "inactive" if reason else "active"
    record["monitoring"] = {
        "version": 1, "state": state, "epoch": 1,
        "coordinator_workspace_id": workspace,
        "coordinator_session_id": record["approval"]["coordinator"]["session_id"],
        "control_ref": record["approval"]["checkpoint"]["ref"],
        "pending_wake": None if reason else {"generation": generation(record, checkpoint_parent_commit, 1, "enrollment"), "reason": "enrollment", "checkpoint_parent_commit": checkpoint_parent_commit},
        "last_reconciliation": None, "inactive_reason": reason,
    }
    return validate_record(record)


def retire(record: object, reason: object) -> dict[str, Any]:
    record = validate_record(record)
    monitoring = record.get("monitoring")
    if not isinstance(monitoring, dict):
        _fail("run is not enrolled")
    monitoring["state"] = "inactive"
    monitoring["inactive_reason"] = _text(reason, "retirement reason")
    monitoring["pending_wake"] = None
    why = monitoring["inactive_reason"]
    if (why != "recovery-stuck" and record["state"]["next_action"] != "review-ready"
            and not record.get("recovery_disposition", {}).get("notices")):
        handback_reason = record["state"].get("handback")
        selected_handback = (isinstance(handback_reason, dict) and isinstance(handback_reason.get("reason"), str)
                             and handback_reason["reason"].startswith("selected "))
        cause = ("selected-limit" if why == "selected-limit-exhausted" or selected_handback else
                 "whole-run-stop" if why.startswith("whole-run-") else
                 "repair-stuck" if why == "repair-human-blocked" else
                 "hitl-slice" if record["state"]["next_action"] == "hitl" else
                 "outside-authority")
        notice_stop(record, cause, why)
    return validate_record(record)


def resume(record: object, checkpoint_parent_commit: object, human_authority: object) -> dict[str, Any]:
    """Restore monitoring only from a durably reconciled human whole-run stop.

    ``human_authority`` is deliberately separate from host status.  A running
    or merely idle record cannot mint renewed monitoring authority.
    """
    record = validate_record(record)
    monitoring = record.get("monitoring")
    if not isinstance(monitoring, dict):
        _fail("run is not enrolled")
    recovery = record.get("recovery")
    if not isinstance(human_authority, str) or not human_authority:
        _fail("monitoring resume requires explicit human authority")
    if (not isinstance(recovery, dict) or recovery.get("status") != "resumed" or not _confirmed_stop(record, recovery)
            or not isinstance(recovery.get("resume"), dict) or recovery["resume"].get("instruction") != human_authority):
        _fail("monitoring resume requires explicit authority after reconciled whole-run stop")
    parent = _commit(checkpoint_parent_commit)
    monitoring["epoch"] += 1
    monitoring["state"] = "active"
    monitoring["inactive_reason"] = None
    monitoring["pending_wake"] = {"generation": generation(record, parent, monitoring["epoch"], "human-resume"), "reason": "human-resume", "checkpoint_parent_commit": parent}
    return validate_record(record)


def checkpoint_transition(record: object, reason: object, checkpoint_parent_commit: object) -> dict[str, Any]:
    """Persist the next logical wake before an external event hint is emitted."""
    record = validate_record(record)
    monitoring = record.get("monitoring")
    if not isinstance(monitoring, dict) or monitoring["state"] != "active":
        _fail("checkpoint transition requires active monitoring")
    if any(item.get("phase") == "wake" and item.get("status") != "accounted" for item in record["usage"]["operations"]):
        _fail("checkpoint transition requires prior wake reconciliation")
    transition_reason = _text(reason, "checkpoint transition reason")
    parent = _commit(checkpoint_parent_commit)
    monitoring["pending_wake"] = {"generation": generation(record, parent, monitoring["epoch"], transition_reason),
                                  "reason": transition_reason, "checkpoint_parent_commit": parent}
    return validate_record(record)


DispatchEmitter = Callable[[dict[str, str]], None]


def start_monitored_run(store: InterimCheckpointStore, approved_record: object,
                        coordinator_workspace_id: object) -> InterimCheckpointSnapshot:
    """The coordinator's approved start boundary: enroll then publish genesis."""
    return store.monitored(_workspace(coordinator_workspace_id)).create_and_publish(
        deepcopy(validate_record(approved_record)))


def persist_checkpoint_transition(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                                  reason: object, emit: DispatchEmitter | None = None) -> InterimCheckpointSnapshot:
    """Advance a monitored checkpoint and then best-effort notify GitHub.

    The notification is only a hint: a failed emitter is deliberately ignored
    after the exact-ref CAS has made backup discovery sufficient for recovery.
    """
    record = checkpoint_transition(deepcopy(snapshot.value), reason, snapshot.commit_sha)
    persisted = store.persist(snapshot, record)
    pending = persisted.value["monitoring"]["pending_wake"]
    if emit is not None and isinstance(pending, dict):
        try:
            emit(locator({"run_id": persisted.value["approval"]["run_id"],
                          "control_ref": persisted.value["monitoring"]["control_ref"],
                          "generation": pending["generation"]}))
        except (OSError, TimeoutError, ConnectionError):
            pass
    return persisted


def persist_retirement(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                       reason: object) -> InterimCheckpointSnapshot:
    """Retire only the snapshot's exact run/ref; unrelated runs are untouched."""
    return store.persist(snapshot, retire(deepcopy(snapshot.value), reason))


def validate_monitoring(record: dict[str, Any]) -> None:
    value = record.get("monitoring")
    required = {"version", "state", "epoch", "coordinator_workspace_id", "coordinator_session_id", "control_ref", "pending_wake", "last_reconciliation", "inactive_reason"}
    if not isinstance(value, dict) or set(value) != required or value.get("version") != 1:
        _fail("monitoring state has unknown or missing fields")
    if value["state"] not in {"active", "inactive", "human-blocked"} or type(value["epoch"]) is not int or value["epoch"] < 1:
        _fail("monitoring state or epoch is malformed")
    _workspace(value["coordinator_workspace_id"])
    if value["coordinator_session_id"] != record["approval"]["coordinator"]["session_id"]:
        _fail("monitoring coordinator differs from immutable approval")
    if value["control_ref"] != record["approval"]["checkpoint"]["ref"]:
        _fail("monitoring control ref differs from immutable approval")
    pending = value["pending_wake"]
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != {"generation", "reason", "checkpoint_parent_commit"}:
            _fail("pending wake is malformed")
        _text(pending["generation"], "pending wake generation")
        _text(pending["reason"], "pending wake reason")
        parent = pending["checkpoint_parent_commit"]
        if parent is not None:
            _commit(parent)
        elif not (pending["reason"] == "enrollment" and value["epoch"] == 1):
            _fail("only genesis enrollment may have no checkpoint parent")
        expected_generation = generation(record, parent, value["epoch"], pending["reason"])
        if pending["generation"] != expected_generation:
            _fail("pending wake generation does not bind immutable record identity")
        if value["state"] != "active":
            _fail("inactive monitoring cannot retain a pending wake")
    if value["state"] == "active" and pending is None:
        _fail("active monitoring requires a pending wake")
    if value["inactive_reason"] is not None:
        _text(value["inactive_reason"], "monitoring inactive reason")
    if value["state"] == "active" and value["inactive_reason"] is not None:
        _fail("active monitoring cannot have an inactive reason")
    last = value["last_reconciliation"]
    if last is not None:
        if not isinstance(last, dict) or set(last) != {"source", "generation", "at", "outcome"}:
            _fail("last reconciliation is malformed")
        if last["source"] not in {"event", "backup", "manual"} or last["outcome"] not in {"woken", "refused", "reconciled"}:
            _fail("last reconciliation has invalid source or outcome")
        _text(last["generation"], "last reconciliation generation")
        _utc(last["at"], "last reconciliation at")


class MonitorAdapter(Protocol):
    def monitoring_observation(self, record: dict[str, Any]) -> dict[str, Any]: ...
    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]: ...
    def send_wake(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def observe(self, operation: dict[str, Any]) -> dict[str, Any]: ...


def _monitor_observation(value: object, allow_exact_wake: bool = False) -> dict[str, Any]:
    fields = {"current_turn", "pending_messages", "pending_effects", "active_workers", "working_ambiguous"}
    if not isinstance(value, dict) or frozenset(value) not in {frozenset(fields), frozenset(fields | {"awaited_worker"})}:
        _fail("host monitoring observation has unknown or missing fields")
    blocked = ("pending_messages", "active_workers", "working_ambiguous")
    if (value["current_turn"] != "interrupted" or any(value[name] is not False for name in blocked)
            or (not allow_exact_wake and value["pending_effects"] is not False)):
        _fail("host monitoring observation is not eligible")
    return value


def locator(value: object) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"run_id", "control_ref", "generation"}:
        _fail("untrusted locator has unknown or missing fields")
    return {name: _text(value[name], "locator " + name) for name in value}


def _lineage_is_bound(snapshot: InterimCheckpointSnapshot, record: dict[str, Any]) -> bool:
    """Prove this record is the one CAS child authorised by its wake binding."""
    pending = record["monitoring"]["pending_wake"]
    if not isinstance(pending, dict):
        return False
    parent = pending["checkpoint_parent_commit"]
    if parent is None:
        # A newly enrolled control ref is deliberately a root record.  It can
        # never be replayed as a descendant or transplanted into another ref.
        return pending["reason"] == "enrollment" and snapshot.parent_commits == ()
    return len(snapshot.parent_commits) == 1 and snapshot.parent_commits[0] == parent


def _reconcile_once(store: InterimCheckpointStore, approved_record: object, untrusted_locator: object,
                    source: str, adapter: MonitorAdapter, now: datetime | None = None,
                    *, _retire_retry: bool = True,
                    deadline: float | None = None,
                    monotonic: Callable[[], float] = time.monotonic,
                    admission_clock: Callable[[], datetime] | None = None) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
    """Converge an event or backup locator on the existing watchdog wake path."""
    if source not in {"event", "backup", "manual"}:
        _fail("reconciliation source is invalid")
    approved = validate_record(approved_record)
    where = locator(untrusted_locator)
    snapshot = store.reload(approved)
    record = snapshot.value
    monitoring = record.get("monitoring")
    if not isinstance(monitoring, dict):
        return snapshot, {"action": "refuse", "reason": "unenrolled-run"}
    if where["run_id"] != record["approval"]["run_id"] or where["control_ref"] != monitoring["control_ref"]:
        return snapshot, {"action": "refuse", "reason": "locator-not-authorized"}
    at = now or datetime.now(timezone.utc)
    if not recovery_check_eligible(record, at):
        return snapshot, {"action": "refuse", "reason": "recovery-backup-cadence"}
    # A record that already contains this exact durable wake may only be
    # reconciled.  Its later receipt checkpoint naturally has a different
    # parent, but it cannot resend or create a second charge.
    exact_wake = wake_operation_id(record, wake_id(record["approval"]["run_id"], where["generation"]))
    exact_operations = [item for item in record["usage"]["operations"] if item.get("id") == exact_wake and item.get("phase") == "wake"]
    has_exact_wake = bool(exact_operations)
    # A settled prior wake must not rewrite the successor checkpoint's audit
    # marker: that would break its exact parent binding and strand new work.
    successor = monitoring.get("pending_wake")
    if has_exact_wake and monitoring["state"] == "active" and isinstance(successor, dict) and where["generation"] != successor["generation"]:
        if len(exact_operations) == 1 and exact_operations[0]["status"] == "accounted":
            return snapshot, {"action": "reconcile-coordinator-wake", "reason": "stale-settled-wake"}
        return snapshot, {"action": "refuse", "reason": "prior-wake-receipt-unsettled"}

    def retire_or_reevaluate(reason: str) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
        try:
            return store.persist(snapshot, retire(deepcopy(record), reason)), {"action": "refuse", "reason": reason}
        except InterimCheckpointError as exc:
            if exc.code != "cas-lost" or not _retire_retry:
                raise
            # A competing delivery moved this exact ref first: it may already
            # have retired the run or admitted its wake.  Re-evaluate once from
            # that checkpoint; nothing was sent, and a second loss is refused.
            # Any other checkpoint failure is surfaced, never re-evaluated.
            return _reconcile_once(store, approved, where, source, adapter, now, _retire_retry=False,
                                   deadline=deadline, monotonic=monotonic,
                                   admission_clock=admission_clock)

    recovery = record.get("recovery", {})
    if recovery.get("status") == "uncertain" and isinstance(recovery.get("stop"), dict):
        targets = [item for item in record["usage"]["operations"] if item.get("status") in {"intent", "active", "reconcile-required", "cancellation-uncertain"}]
        operation = targets[-1] if targets else None
        operation_id = operation["id"] if operation else monitoring["coordinator_session_id"]
        category, retry_after = "unconfirmed-cancellation", None
        if operation is not None:
            try:
                observed = adapter.observe(deepcopy(operation))
                expected = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
                if not isinstance(observed, dict) or observed.get("observation") != expected:
                    _fail("stop observation differs from exact operation")
            except MonitoringPolicyError:
                return snapshot, {"action": "refuse", "reason": "host-observation-unavailable-or-ineligible"}
            except (OSError, TimeoutError, ConnectionError) as exc:
                category = getattr(exc, "category", category)
                retry_after = getattr(exc, "retry_after", None)
        projected = deepcopy(record)
        stop = unresolved_disposition(projected, category, operation_id, at, retry_after)
        if stop:
            projected = retire(projected, "recovery-stuck")
        else:
            projected = checkpoint_transition(projected, "cancellation-backup-recheck", snapshot.commit_sha)
        return store.persist(snapshot, projected), {"action": "refuse", "reason": "recovery-stuck" if stop else "unconfirmed-cancellation"}

    terminal = _terminal(record)
    if terminal and not has_exact_wake:
        return retire_or_reevaluate(terminal)
    if not has_exact_wake and (monitoring["state"] != "active" or monitoring["pending_wake"] is None):
        return snapshot, {"action": "refuse", "reason": "monitoring-inactive"}
    if not has_exact_wake and not _lineage_is_bound(snapshot, record):
        return snapshot, {"action": "refuse", "reason": "checkpoint-parent-binding-mismatch"}
    if not has_exact_wake and where["generation"] != monitoring["pending_wake"]["generation"]:
        return snapshot, {"action": "refuse", "reason": "stale-or-unknown-generation"}
    limits = record["approval"]["hard_limits"]
    at = now or datetime.now(timezone.utc)
    exhausted = (
        limits != "none" and (
            ("deadline_at" in limits and at >= datetime.fromisoformat(limits["deadline_at"].replace("Z", "+00:00")))
            or len(record["usage"].get("launches", [])) >= limits.get("dispatch_max", 2**63 - 1)
        )
    )
    if not has_exact_wake and exhausted:
        # Retire through the same exact-ref CAS before contacting the host.  A
        # later backup therefore sees inactive state rather than repeatedly
        # rediscovering an already selected-limit-exhausted run.  An exact
        # durable wake is already admitted: it can only settle through observe,
        # never launch, send, or charge again, even when that admission used
        # the final selected slot or its deadline has since passed.
        return retire_or_reevaluate("selected-limit-exhausted")
    active_awaited_worker = False
    try:
        raw_observation = adapter.monitoring_observation(record)
        if record["state"]["next_action"] == "await-worker" and not has_exact_wake and isinstance(raw_observation, dict):
            awaited = next(item for item in record["usage"]["operations"] if item["id"] == record["state"]["operation_id"])
            worker = raw_observation.get("awaited_worker")
            identity = {name: awaited[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
            if isinstance(worker, dict) and worker == {**identity, "state": "queued"}:
                _monitor_observation(raw_observation, allow_exact_wake=has_exact_wake)
                if record.get("recovery_disposition", {}).get("active"):
                    projected = deepcopy(record)
                    clear_disposition(projected)
                    projected = checkpoint_transition(projected, "worker-still-queued", snapshot.commit_sha)
                    snapshot = store.persist(snapshot, projected)
                return snapshot, {"action": "refuse", "reason": "awaited-worker-still-running"}
        observation = _monitor_observation(raw_observation, allow_exact_wake=has_exact_wake)
        if record["state"]["next_action"] == "await-worker" and not has_exact_wake:
            awaited = next(item for item in record["usage"]["operations"] if item["id"] == record["state"]["operation_id"])
            worker = observation.get("awaited_worker")
            identity = {name: awaited[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
            if (not isinstance(worker, dict) or set(worker) != set(identity) | {"state"}
                    or any(worker[name] != identity[name] for name in identity)):
                _fail("awaited worker has no exact terminal observation")
            if worker["state"] == "active":
                active_awaited_worker = True
            elif worker["state"] == "unknown":
                raise ObservationFailure("uncertain-effect")
            elif worker["state"] not in {"terminal", "error"}:
                _fail("awaited worker has no exact terminal observation")
    except MonitoringPolicyError:
        return snapshot, {"action": "refuse", "reason": "host-observation-unavailable-or-ineligible"}
    except (OSError, TimeoutError, ConnectionError, InterimCheckpointError) as exc:
        projected = deepcopy(record)
        operation_id = projected["state"].get("operation_id", monitoring["coordinator_session_id"])
        category = getattr(exc, "category", "transient-outage")
        prior = projected.get("recovery_disposition", {}).get("active")
        if (category == "ambiguous-missing-session" and isinstance(prior, dict)
                and prior["operation_id"] == operation_id and prior["category"] == category
                and prior["count"] >= 1):
            category = "missing-session"
        stop = unresolved_disposition(projected, category, operation_id, at, getattr(exc, "retry_after", None))
        if stop:
            projected = _handback(projected, decision_reason(category))
            projected = retire(projected, "authority-decision" if category in IMMEDIATE else "recovery-stuck")
        else:
            projected = checkpoint_transition(projected, "recovery-backup-recheck", snapshot.commit_sha)
        try:
            return store.persist(snapshot, projected), {"action": "refuse", "reason": ("authority-decision" if category in IMMEDIATE else "recovery-stuck") if stop else "host-observation-unavailable-or-ineligible"}
        except InterimCheckpointError as exc:
            if exc.code != "cas-lost":
                raise
            return store.reload(approved), {"action": "refuse", "reason": "cas-lost-reload-required"}
    if deadline is not None and monotonic() >= deadline:
        return snapshot, {"action": "refuse", "reason": "event-recheck-time-exhausted"}
    # Host status and transcript reads can consume the selected deadline.
    # Re-sample the authoritative clock immediately before reserving a wake;
    # an explicitly injected test time remains fixed for compatibility.
    at = admission_clock() if admission_clock is not None else at
    if (not has_exact_wake and limits != "none" and "deadline_at" in limits
            and at >= datetime.fromisoformat(limits["deadline_at"].replace("Z", "+00:00"))):
        return retire_or_reevaluate("selected-limit-exhausted")
    if active_awaited_worker:
        if record.get("recovery_disposition", {}).get("active"):
            projected = deepcopy(record)
            clear_disposition(projected)
            projected = checkpoint_transition(projected, "worker-still-running", snapshot.commit_sha)
            snapshot = store.persist(snapshot, projected)
        return snapshot, {"action": "refuse", "reason": "awaited-worker-still-running"}
    try:
        current, decision = resume_and_reconcile(store, snapshot, _title(record), monitoring["coordinator_session_id"], where["generation"],
                                                  {name: observation[name] for name in ("current_turn", "pending_messages", "pending_effects")}, adapter, at)
    except InterimCheckpointError as exc:
        # A second independent delivery may lose the exact-ref CAS between its
        # reload and reservation. Reload once and reconcile that durable wake;
        # never retry a host send based on the losing projection.  Any other
        # checkpoint failure (for example a rejected push) is surfaced.
        if exc.code != "cas-lost":
            raise
        current = store.reload(approved)
        # The winner may still be recording its receipt.  Returning the durable
        # reconciliation frontier is safer than racing a second receipt write;
        # the next event/backup performs the normal observe-only reconciliation.
        return current, {"action": "reconcile-coordinator-wake", "reason": "cas-lost-reload-required"}
    # The durable wake reservation is authoritative.  This audit marker is
    # best-effort only after that CAS transaction and cannot create a wake.
    # A lifecycle retirement may have cleared the monitoring record while an
    # ambiguous POST is still owed an observe-only settlement.  Its receipt is
    # durable in usage; do not resurrect monitoring just to write an audit.
    if current.value["monitoring"]["state"] == "active":
        marked = deepcopy(current.value)
        marked["monitoring"]["last_reconciliation"] = {"source": source, "generation": where["generation"],
                                                           "at": (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z"),
                                                           "outcome": "woken" if decision["action"] == "resume-coordinator" else "reconciled" if decision["action"] == "reconcile-coordinator-wake" else "refused"}
        try:
            current = store.persist(current, marked)
        except InterimCheckpointError:
            # A competing deterministic check won the marker; its earlier wake
            # reservation remains intact and this delivery must not retry an effect.
            pass
    # A terminal observation of the exact awaited worker resolves a prior
    # host-read outage. A failed-worker wake does not resolve its candidate or
    # external effects; preserve that cumulative count until the coordinator
    # establishes fresh effect evidence.
    if record["state"]["next_action"] == "await-worker" and current.value.get("recovery_disposition", {}).get("active"):
        cleared = deepcopy(current.value)
        clear_disposition(cleared)
        try:
            current = store.persist(current, cleared)
        except InterimCheckpointError:
            pass  # the admitted wake remains authoritative
    return current, decision


def reconcile(store: InterimCheckpointStore, approved_record: object, untrusted_locator: object,
              source: str, adapter: MonitorAdapter, now: datetime | None = None,
              *, monotonic: Callable[[], float] = time.monotonic,
              sleep: Callable[[float], None] = time.sleep,
              wall_clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> tuple[InterimCheckpointSnapshot, dict[str, Any]]:
    """One admission, plus at most four event-only 20-second host re-reads.

    The elapsed budget includes checkpoint reloads and host observation.  A
    slow observation may finish after the deadline, but cannot admit a wake.
    Backup and manual reconciliation never sleep or poll.
    """
    start = monotonic()
    deadline = start + 120 if source == "event" else None
    if source == "event" and hasattr(adapter, "set_event_deadline"):
        adapter.set_event_deadline(deadline, monotonic)
    try:
        for rereads in range(5):
            if rereads and deadline is not None and monotonic() >= deadline:
                return result[0], {"action": "refuse", "reason": "event-recheck-time-exhausted"}
            result = _reconcile_once(store, approved_record, untrusted_locator, source, adapter,
                                     now if now is not None else wall_clock(),
                                     deadline=deadline, monotonic=monotonic,
                                     admission_clock=None if now is not None else wall_clock)
            if source != "event" or result[1].get("reason") != "awaited-worker-still-running" or rereads == 4:
                return result
            remaining = deadline - monotonic()
            if remaining <= 0:
                return result[0], {"action": "refuse", "reason": "event-recheck-time-exhausted"}
            sleep(min(20, remaining))
    finally:
        if source == "event" and hasattr(adapter, "set_event_deadline"):
            adapter.set_event_deadline(None, monotonic)
    raise AssertionError("bounded event re-check loop did not return")

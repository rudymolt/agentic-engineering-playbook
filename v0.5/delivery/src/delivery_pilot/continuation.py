"""Pure, dispatch-free reducer for a bounded unattended continuation record.

This is a serialization contract, not a protected dispatch boundary.  Its
``authentication`` fields are explicit validated-input requirements; they do
not claim that this local reducer authenticates an external operator.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .budget import ActiveTimeLedger, CeilingError
from .canonical import CanonicalError, canonical_bytes, digest, load_strict
from .operations import operation_id


class ContinuationError(ValueError):
    """A malformed, unbound, or unsafe continuation fact was refused."""


_DIGEST_PREFIX = "sha256:"
_STATUSES = {"active", "hitl", "stopping", "stopped", "stop_not_confirmed", "intervention_required", "blocked", "terminal", "expired", "ambiguous"}
_ACCOUNTING_CLOSURE_STATUSES = _STATUSES - {"terminal", "stopped"}
_OP_TERMINAL = {"discarded", "completed", "failed", "cancelled", "fenced"}
_SENDER_TERMINAL = {"terminal", "fenced"}


def _fail(message: str) -> None:
    raise ContinuationError(message)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{name} must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(f"{name} must be a non-negative integer")
    return value


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if len(value) != 71 or not value.startswith(_DIGEST_PREFIX) or any(char not in "0123456789abcdef" for char in value[7:]):
        _fail(f"{name} must be a sha256 digest")
    return value


def _unique_strings(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value) or len(set(value)) != len(value):
        _fail(f"{name} must be a non-empty unique string list")
    return list(value)


def validate_envelope(value: object) -> dict[str, Any]:
    """Validate immutable human authorization and all admission bindings."""
    envelope = _mapping(value, "envelope")
    required = {
        "schema_version", "human_authorization", "run_id", "feature", "maximum_action", "spec_digest", "slices_digest",
        "targets", "sender_ids", "approved_afk_slices", "build_route", "verify_route", "allowed_paths_digest", "deadline",
        "limits", "initial_epoch", "protected_boundary", "stop_channel",
    }
    if set(envelope) != required or type(envelope.get("schema_version")) is not int or envelope["schema_version"] != 1:
        _fail("envelope has unknown or missing fields")
    human = _mapping(envelope["human_authorization"], "human_authorization")
    if set(human) != {"source_event_id", "validated", "original_intent_id"} or human["validated"] is not True:
        _fail("human authorization must be explicitly validated")
    _text(human["source_event_id"], "human source event")
    _text(human["original_intent_id"], "original intent identity")
    for name in ("run_id", "feature", "maximum_action", "build_route", "verify_route", "protected_boundary", "stop_channel"):
        _text(envelope[name], name)
    if envelope["maximum_action"] != "review-ready":
        _fail("maximum action must be review-ready for this continuation seam")
    for name in ("spec_digest", "slices_digest", "allowed_paths_digest"):
        _digest(envelope[name], name)
    _unique_strings(envelope["targets"], "targets")
    _unique_strings(envelope["sender_ids"], "sender IDs")
    _unique_strings(envelope["approved_afk_slices"], "approved AFK slices")
    _integer(envelope["deadline"], "deadline")
    _integer(envelope["initial_epoch"], "initial epoch")
    limits = _mapping(envelope["limits"], "limits")
    limit_names = {"dispatch_max", "retry_max", "failure_max", "no_progress_max", "active_seconds_max", "verification_reserve_seconds"}
    if set(limits) != limit_names or any(not isinstance(limits[name], int) or isinstance(limits[name], bool) or limits[name] < 0 for name in limit_names):
        _fail("limits are malformed")
    if limits["active_seconds_max"] <= limits["verification_reserve_seconds"]:
        _fail("verification reserve consumes active-time limit")
    return deepcopy(envelope)


def initial_state(envelope: object) -> dict[str, Any]:
    envelope = validate_envelope(envelope)
    return {
        "schema_version": 1,
        "envelope": envelope,
        "authorization_digest": digest(envelope),
        "run_id": envelope["run_id"],
        "epoch": envelope["initial_epoch"],
        "status": "active",
        "admission_closed": False,
        "observed": False,
        "observation_count": 0,
        "senders": {sender: {"status": "idle"} for sender in envelope["sender_ids"]},
        "sender_evidence": {},
        "operations": {},
        "ledger": ActiveTimeLedger(envelope["limits"]["active_seconds_max"]).to_record(),
        "counters": {"dispatches": 0, "retries": 0, "failures": 0, "no_progress": 0},
        "frozen_senders": [],
        "frozen_operations": [],
        "current_turn_stop_requested": False,
        "results": [],
        "ceiling_report": None,
        "checkpoint": None,
        "optional_counters": {
            "tool_calls": {"value": None, "reason": "unavailable authoritative tool count"},
            "tokens": {"value": None, "reason": "unavailable authoritative token count"},
        },
        "recovery": {"controller_generation": 0, "operation_id": None},
        "outcomes": [],
        "stop_receipt": None,
        "native_cancellation": None,
        "transitions": [],
    }


def validate_state(value: object) -> dict[str, Any]:
    state = _mapping(value, "state")
    required = {"schema_version", "envelope", "authorization_digest", "run_id", "epoch", "status", "admission_closed", "observed", "observation_count", "senders", "sender_evidence", "operations", "ledger", "counters", "frozen_senders", "frozen_operations", "current_turn_stop_requested", "results", "ceiling_report", "checkpoint", "optional_counters", "recovery", "outcomes", "stop_receipt", "native_cancellation", "transitions"}
    if set(state) != required or type(state.get("schema_version")) is not int or state["schema_version"] != 1:
        _fail("state has unknown or missing fields")
    envelope = validate_envelope(state["envelope"])
    if state["authorization_digest"] != digest(envelope) or state["run_id"] != envelope["run_id"]:
        _fail("state is not bound to immutable authorization")
    if not isinstance(state["epoch"], int) or isinstance(state["epoch"], bool) or state["epoch"] < envelope["initial_epoch"] or state["status"] not in _STATUSES:
        _fail("state epoch or status is malformed")
    if not isinstance(state["admission_closed"], bool) or not isinstance(state["observed"], bool) or not isinstance(state["current_turn_stop_requested"], bool):
        _fail("state booleans are malformed")
    _integer(state["observation_count"], "observation count")
    senders, operations, counters = _mapping(state["senders"], "senders"), _mapping(state["operations"], "operations"), _mapping(state["counters"], "counters")
    if set(senders) != set(envelope["sender_ids"]):
        _fail("sender set is not bound to envelope")
    for sender in senders.values():
        if not isinstance(sender, dict) or set(sender) != {"status"} or sender["status"] not in {"idle", "mutable", "in_flight", "frozen", "terminal", "fenced"}:
            _fail("sender state is malformed")
    sender_evidence = _mapping(state["sender_evidence"], "sender evidence")
    if not set(sender_evidence) <= set(senders):
        _fail("sender evidence includes an unregistered sender")
    for evidence in sender_evidence.values():
        if not isinstance(evidence, dict) or set(evidence) != {"status", "evidence_digest"} or evidence["status"] not in _SENDER_TERMINAL:
            _fail("sender evidence is malformed")
        _digest(evidence["evidence_digest"], "sender evidence digest")
    if set(counters) != {"dispatches", "retries", "failures", "no_progress"}:
        _fail("counters are malformed")
    for name, number in counters.items():
        _integer(number, name)
    try:
        ledger = ActiveTimeLedger.from_record(state["ledger"])
    except CeilingError as exc:
        _fail(str(exc))
    if ledger.total_limit != envelope["limits"]["active_seconds_max"]:
        _fail("ledger limit contradicts immutable envelope")
    if (not isinstance(state["frozen_senders"], list) or not isinstance(state["frozen_operations"], list)
            or any(not isinstance(item, str) for item in state["frozen_senders"] + state["frozen_operations"])
            or len(set(state["frozen_senders"])) != len(state["frozen_senders"])
            or len(set(state["frozen_operations"])) != len(state["frozen_operations"])
            or not set(state["frozen_senders"]) <= set(senders)
            or not set(state["frozen_operations"]) <= set(operations)):
        _fail("frozen identifiers are malformed")
    if not isinstance(state["results"], list):
        _fail("results are malformed")
    result_history: dict[str, list[dict[str, Any]]] = {}
    for result in state["results"]:
        if not isinstance(result, dict) or set(result) != {"operation_id", "transport", "completion", "verification", "known_effects", "evidence_digest"}:
            _fail("four-part result evidence is malformed")
        if not isinstance(result["operation_id"], str) or result["operation_id"] not in operations:
            _fail("result operation is unbound")
        _digest(result["evidence_digest"], "result evidence digest")
        result_history.setdefault(result["operation_id"], []).append(result)
    for operation_id_value, history in result_history.items():
        if any(previous == current for previous, current in zip(history, history[1:])):
            _fail("result history repeats identical evidence")
        if any(not _result_progresses(previous, current) for previous, current in zip(history, history[1:])):
            _fail("result history contains contradictory terminal facts")
        operation = operations[operation_id_value]
        if any(operation[name] != history[-1][name] for name in ("transport", "completion", "verification", "known_effects")):
            _fail("current operation contradicts latest result evidence")
    report = state["ceiling_report"]
    if report is not None:
        if not isinstance(report, dict) or set(report) != {"activity", "progress", "ceiling", "next_action"} or any(not isinstance(item, str) or not item for item in report.values()):
            _fail("ceiling report is malformed")
    if state["status"] == "expired" and report is None:
        _fail("expired state lacks durable ceiling report")
    if ledger.total_seconds > ledger.total_limit and (report is None or state["status"] not in _ACCOUNTING_CLOSURE_STATUSES):
        _fail("ledger overrun lacks durable exhausted-state evidence")
    checkpoint = state["checkpoint"]
    if checkpoint is not None:
        if not isinstance(checkpoint, dict) or set(checkpoint) != {"checkpoint_id", "outcome", "operation_id", "evidence_digest"}:
            _fail("checkpoint is malformed")
        _text(checkpoint["checkpoint_id"], "checkpoint ID")
        if checkpoint["outcome"] not in {"complete", "verified", "incomplete", "blocked", "current_turn_cancelled"}:
            _fail("checkpoint outcome is malformed")
        _digest(checkpoint["evidence_digest"], "checkpoint evidence digest")
        if checkpoint["operation_id"] is not None and (not isinstance(checkpoint["operation_id"], str) or checkpoint["operation_id"] not in operations):
            _fail("checkpoint operation is unbound")
    optional_counters = _mapping(state["optional_counters"], "optional counters")
    if set(optional_counters) != {"tool_calls", "tokens"}:
        _fail("optional counter names are malformed")
    for counter in optional_counters.values():
        if not isinstance(counter, dict) or set(counter) != {"value", "reason"}:
            _fail("optional counter is malformed")
        value, reason = counter["value"], counter["reason"]
        if value is None:
            _text(reason, "optional counter reason")
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0 or reason is not None:
            _fail("optional counter value or reason is malformed")
    recovery = _mapping(state["recovery"], "recovery")
    if set(recovery) != {"controller_generation", "operation_id"}:
        _fail("recovery is malformed")
    _integer(recovery["controller_generation"], "controller generation")
    if recovery["operation_id"] is not None and (not isinstance(recovery["operation_id"], str) or recovery["operation_id"] not in operations):
        _fail("recovery operation is unbound")
    if not isinstance(state["outcomes"], list):
        _fail("outcomes are malformed")
    valid_outcomes = {"complete", "verified", "incomplete", "blocked", "current_turn_cancelled", "stopping", "stopped", "stop_not_confirmed", "intervention_required", "expired", "ambiguous"}
    for outcome in state["outcomes"]:
        if not isinstance(outcome, dict) or set(outcome) != {"outcome", "status", "evidence_digest"} or outcome["outcome"] not in valid_outcomes or outcome["status"] not in _STATUSES:
            _fail("outcome evidence is malformed")
        _digest(outcome["evidence_digest"], "outcome evidence digest")
        expected_statuses = {
            "complete": {"terminal"}, "verified": {"terminal"}, "incomplete": {"blocked"},
            "blocked": {"blocked"}, "current_turn_cancelled": {"active"},
            "intervention_required": {"intervention_required"}, "expired": {"expired"},
            "ambiguous": {"ambiguous"}, "stopping": {"stopping"},
            "stopped": {"stopped"}, "stop_not_confirmed": {"stop_not_confirmed"},
        }
        exhausted_outcome = outcome["status"] in {"expired", "blocked"} and report is not None
        if outcome["status"] not in expected_statuses[outcome["outcome"]] and not exhausted_outcome:
            _fail("outcome status contradicts its named outcome")
    for op_id, operation in operations.items():
        if not isinstance(op_id, str) or not isinstance(operation, dict):
            _fail("operation is malformed")
        if op_id != operation.get("operation_id"):
            _fail("operation key contradicts immutable operation identity")
        _validate_operation(operation, envelope, state["authorization_digest"])
        _validate_operation_disposition(state, operation, result_history.get(op_id, []))
        sender_status = senders[operation["sender_id"]]["status"]
        if operation["status"] == "admitted" and sender_status != "mutable":
            _fail("sender contradicts unresolved admitted operation")
        if operation["status"] == "in_flight" and not state["admission_closed"] and sender_status != "in_flight":
            _fail("sender contradicts unresolved in-flight operation")
        if operation["status"] == "ambiguous" and sender_status in _SENDER_TERMINAL:
            _fail("sender evidence contradicts unresolved operation")
    active_builders = [sender for sender, item in senders.items() if item["status"] in {"mutable", "in_flight"}]
    if len(active_builders) > 1:
        _fail("multiple mutable builders")
    for sender_id, evidence in sender_evidence.items():
        if senders[sender_id]["status"] != evidence["status"]:
            _fail("sender evidence contradicts sender status")
        if any(item["sender_id"] == sender_id and item["status"] in {"admitted", "in_flight", "ambiguous"} for item in operations.values()):
            _fail("sender evidence contradicts unresolved operation")
    initial_epoch = envelope["initial_epoch"]
    if state["status"] == "active" and (state["admission_closed"] or state["epoch"] != initial_epoch):
        _fail("active state cannot close admission or advance epoch")
    if state["status"] == "stop_not_confirmed" and (not state["admission_closed"] or state["epoch"] != initial_epoch):
        _fail("stop-not-confirmed state contradicts durable closure facts")
    if state["status"] in {"stopping", "stopped"} and (not state["admission_closed"] or state["epoch"] != initial_epoch + 1):
        _fail("stopping or stopped state contradicts epoch or admission closure")
    if state["epoch"] > initial_epoch + 1:
        _fail("epoch can advance only once for this bounded run")
    if not state["admission_closed"] and (state["frozen_senders"] or state["frozen_operations"]):
        _fail("unclosed admission cannot contain frozen facts")
    if state["admission_closed"] and state["status"] != "stop_not_confirmed":
        if set(state["frozen_senders"]) != set(senders) or set(state["frozen_operations"]) != set(operations):
            _fail("closed admission must retain complete frozen sets")
    for operation in operations.values():
        if operation["epoch"] < initial_epoch or operation["epoch"] > state["epoch"]:
            _fail("operation epoch contradicts run epoch")
        if state["admission_closed"] and state["status"] != "stop_not_confirmed" and operation["status"] == "admitted":
            _fail("closed admission cannot retain an unfrozen admitted operation")
    if state["status"] == "stopped":
        if ledger.open_intervals:
            _fail("stopped state requires closed active-time intervals")
        if set(sender_evidence) != set(senders) or any(item["status"] not in _SENDER_TERMINAL for item in senders.values()):
            _fail("stopped state lacks sender terminal or fencing evidence")
        if any(item["status"] not in _OP_TERMINAL or item["known_effects"] not in {"fenced", "succeeded", "failed", "not_run"} for item in operations.values()):
            _fail("stopped state lacks operation or known-effect fencing evidence")
        if not isinstance(state["native_cancellation"], dict) or state["native_cancellation"]["status"] not in {"cancelled", "fenced", "not_required"}:
            _fail("stopped state lacks native cancellation evidence")
    stop_receipt = state["stop_receipt"]
    if stop_receipt is not None:
        if not isinstance(stop_receipt, dict) or set(stop_receipt) != {"source_event_id", "channel", "persistence_confirmed", "evidence_digest"}:
            _fail("stop receipt is malformed")
        _text(stop_receipt["source_event_id"], "stop receipt source")
        if stop_receipt["channel"] != envelope["stop_channel"] or not isinstance(stop_receipt["persistence_confirmed"], bool):
            _fail("stop receipt is unbound")
        _digest(stop_receipt["evidence_digest"], "stop receipt evidence digest")
    if state["admission_closed"] and stop_receipt is None:
        _fail("closed admission lacks Stop receipt")
    native = state["native_cancellation"]
    if native is not None:
        if not isinstance(native, dict) or set(native) != {"status", "evidence_digest"} or native["status"] not in {"requested", "cancelled", "fenced", "not_required", "unknown"}:
            _fail("native cancellation fact is malformed")
        _digest(native["evidence_digest"], "native cancellation evidence digest")
    transitions = state["transitions"]
    if not isinstance(transitions, list):
        _fail("transitions are malformed")
    transition_status = "active"
    for transition in transitions:
        if not isinstance(transition, dict) or set(transition) != {"transition", "from_status", "to_status", "evidence_digest"}:
            _fail("transition evidence is malformed")
        _text(transition["transition"], "transition name")
        if transition["from_status"] not in _STATUSES or transition["to_status"] not in _STATUSES:
            _fail("transition status is malformed")
        _digest(transition["evidence_digest"], "transition evidence digest")
        if transition["from_status"] != transition_status:
            _fail("transition history is not contiguous")
        transition_status = transition["to_status"]
    if transitions and transition_status != state["status"]:
        _fail("transition history does not reach current status")
    if state["status"] != "active" and not transitions:
        _fail("non-active state lacks transition evidence")
    if stop_receipt is not None and not state["admission_closed"]:
        _fail("Stop receipt requires closed admission")
    if state["admission_closed"]:
        if stop_receipt is None:
            _fail("closed admission lacks Stop receipt")
        if not transitions:
            _fail("closed admission lacks Stop transition evidence")
        if stop_receipt["persistence_confirmed"]:
            if state["epoch"] != initial_epoch + 1 or state["status"] == "stop_not_confirmed":
                _fail("confirmed Stop receipt contradicts epoch or status")
            if not any(transition["transition"] == "stop_run" and transition["to_status"] == "stopping"
                       for transition in transitions):
                _fail("confirmed Stop receipt lacks stopping transition")
            if not any(transition["transition"] == "stop_run" and transition["to_status"] == "stopping"
                       and transition["evidence_digest"] == stop_receipt["evidence_digest"]
                       for transition in transitions):
                _fail("confirmed Stop receipt contradicts Stop transition evidence")
        elif state["epoch"] != initial_epoch or state["status"] != "stop_not_confirmed":
            _fail("unconfirmed Stop receipt contradicts epoch or status")
        elif not any(transition["transition"] == "stop_not_confirmed"
                     and transition["to_status"] == "stop_not_confirmed" for transition in transitions):
            _fail("unconfirmed Stop receipt lacks stop-not-confirmed transition")
        elif not any(transition["transition"] == "stop_not_confirmed"
                     and transition["to_status"] == "stop_not_confirmed"
                     and transition["evidence_digest"] == stop_receipt["evidence_digest"]
                     for transition in transitions):
            _fail("unconfirmed Stop receipt contradicts Stop transition evidence")
    success_outcomes = [outcome for outcome in state["outcomes"] if outcome["outcome"] in {"complete", "verified"}]
    for outcome in success_outcomes:
        if not _matching_success(state, outcome["outcome"]):
            _fail("saved success outcome lacks matching completion evidence")
        if not _terminal_quiescent(state):
            _fail("saved success outcome requires quiescent current operations and senders")
    if state["status"] == "terminal" and not _terminal_success_evidence(state):
        _fail("terminal outcome lacks matching completion evidence")
    return deepcopy(state)


def _validate_operation(operation: dict[str, Any], envelope: dict[str, Any], authorization_digest: str) -> None:
    required = {"operation_id", "receipt_id", "authorization_digest", "run_id", "epoch", "sender_id", "target", "payload_digest", "task", "slice", "candidate", "action", "attempt", "original_generation", "status", "transport", "completion", "verification", "known_effects"}
    if set(operation) != required or operation["authorization_digest"] != authorization_digest or operation["run_id"] != envelope["run_id"]:
        _fail("operation is unbound")
    for name in ("operation_id", "receipt_id", "sender_id", "target", "task", "slice", "candidate", "action"):
        _text(operation[name], name)
    _digest(operation["payload_digest"], "payload digest")
    if operation["sender_id"] not in envelope["sender_ids"] or operation["target"] not in envelope["targets"]:
        _fail("operation sender or target is unbound")
    if operation["slice"] not in envelope["approved_afk_slices"] or operation["action"] != envelope["maximum_action"]:
        _fail("operation exceeds immutable approved AFK scope or maximum action")
    for name in ("epoch", "attempt", "original_generation"):
        _integer(operation[name], name)
    if operation["attempt"] < 1 or operation["status"] not in {"admitted", "in_flight", "discarded", "completed", "failed", "cancelled", "fenced", "ambiguous"}:
        _fail("operation status is malformed")
    if operation["transport"] not in {"not_run", "accepted", "queued", "failed", "unknown"} or operation["completion"] not in {"pending", "succeeded", "failed", "unknown"} or operation["verification"] not in {"not_run", "pending", "succeeded", "failed", "unknown"} or operation["known_effects"] not in {"pending", "succeeded", "failed", "fenced", "unknown", "not_run"}:
        _fail("operation result facts are malformed")
    binding = {name: operation[name] for name in ("authorization_digest", "run_id", "epoch", "sender_id", "target", "payload_digest", "task", "slice", "candidate", "action", "attempt", "original_generation")}
    expected_receipt = "receipt-" + digest(binding).split(":", 1)[1][:24]
    expected_op = operation_id(operation["run_id"], "continuation", operation["target"], {**binding, "receipt_id": expected_receipt})
    if operation["receipt_id"] != expected_receipt or operation["operation_id"] != expected_op:
        _fail("operation identity is not bound to its immutable receipt")


def _stop_binds_operation(state: dict[str, Any], operation: dict[str, Any]) -> bool:
    """A terminal Stop disposition is meaningful only inside its frozen run."""
    receipt = state["stop_receipt"]
    return (state["admission_closed"]
            and isinstance(receipt, dict)
            and receipt.get("persistence_confirmed") is True
            and operation["operation_id"] in state["frozen_operations"]
            and operation["sender_id"] in state["frozen_senders"])


def _validate_operation_disposition(state: dict[str, Any], operation: dict[str, Any], history: list[dict[str, Any]]) -> None:
    """Keep operation status aligned with durable result and effect facts."""
    terminal_effects = {"succeeded", "failed", "fenced", "not_run"}
    result_matches = any(
        all(result[name] == operation[name]
            for name in ("transport", "completion", "verification", "known_effects"))
        for result in history
    )
    status = operation["status"]
    if operation["completion"] in {"succeeded", "failed"} and not result_matches:
        _fail("terminal operation lacks exact matching success or failure evidence")
    if any(operation[name] == "unknown" for name in ("transport", "completion", "verification", "known_effects")) and status != "ambiguous":
        _fail("non-ambiguous operation contains unknown result evidence")
    if status == "discarded":
        if (not _stop_binds_operation(state, operation)
                or history
                or operation["transport"] != "not_run"
                or operation["completion"] != "pending"
                or operation["verification"] != "not_run"
                or operation["known_effects"] != "not_run"):
            _fail("terminal operation discard lacks confirmed Stop unsent evidence")
    elif status in {"completed", "failed"}:
        expected_completion = "succeeded" if status == "completed" else "failed"
        if operation["completion"] != expected_completion or operation["known_effects"] not in terminal_effects or not result_matches:
            _fail("terminal operation status contradicts durable result evidence")
    elif status in {"cancelled", "fenced"}:
        if (not _stop_binds_operation(state, operation)
                or not result_matches
                or operation["completion"] != "pending"
                or operation["known_effects"] != "fenced"):
            _fail("terminal operation cancellation or fencing lacks Stop-bound operation evidence")
    elif status == "admitted" and operation["completion"] in {"succeeded", "failed"}:
        _fail("nonterminal admitted operation contradicts completed result evidence")


def _update_operation_disposition(state: dict[str, Any], operation: dict[str, Any]) -> None:
    """Derive a non-admitting disposition from one operation's current facts."""
    if (operation["transport"] == "unknown" or operation["completion"] == "unknown"
            or operation["verification"] == "unknown" or operation["known_effects"] == "unknown"):
        operation["status"] = "ambiguous"
        if state["admission_closed"]:
            state["status"] = "intervention_required"
        else:
            state["status"] = "ambiguous"
        return
    if (operation["completion"] in {"succeeded", "failed"}
            and operation["known_effects"] in {"succeeded", "failed", "fenced", "not_run"}):
        operation["status"] = "completed" if operation["completion"] == "succeeded" else "failed"
        state["senders"][operation["sender_id"]]["status"] = "terminal"
        return
    if (operation["completion"] == "pending" and operation["known_effects"] == "fenced"
            and _stop_binds_operation(state, operation)):
        operation["status"] = "fenced"
        return
    if (operation["transport"] in {"accepted", "queued"}
            or operation["completion"] in {"succeeded", "failed"}):
        operation["status"] = "in_flight"
        state["senders"][operation["sender_id"]]["status"] = "in_flight"


def _event(value: object) -> dict[str, Any]:
    event = _mapping(value, "event")
    _text(event.get("type"), "event type")
    return event


def _now(event: dict[str, Any]) -> int:
    return _integer(event.get("now"), "event now")


def _admission_allowed(state: dict[str, Any], now: int) -> None:
    envelope, limits = state["envelope"], state["envelope"]["limits"]
    if state["status"] != "active" or state["admission_closed"]:
        _fail("new admission is revoked or not active")
    _checkpoint_allows_progress(state)
    if not state["observed"]:
        _fail("observer-first reconciliation is required")
    if any(operation["status"] == "ambiguous" for operation in state["operations"].values()):
        _fail("ambiguous operation blocks admission")
    if now >= envelope["deadline"]:
        state["status"] = "expired"
        _fail("deadline expired")
    if state["counters"]["dispatches"] >= limits["dispatch_max"]:
        _fail("dispatch ceiling exhausted")
    counter_limits = {"retries": "retry_max", "failures": "failure_max", "no_progress": "no_progress_max"}
    if any(state["counters"][name] >= limits[limit] for name, limit in counter_limits.items()):
        _fail("failure, retry, or no-progress ceiling exhausted")
    ledger = ActiveTimeLedger.from_record(state["ledger"])
    if ledger.open_intervals:
        _fail("unknown charged interval blocks admission")
    if ledger.total_seconds + limits["verification_reserve_seconds"] >= limits["active_seconds_max"]:
        _fail("verification reserve protects remaining capacity")


def _dispatch_budget_allowed(state: dict[str, Any], now: int) -> None:
    """Receipts are immutable evidence, never an extension of current limits."""
    limits = state["envelope"]["limits"]
    _checkpoint_allows_progress(state)
    if now >= state["envelope"]["deadline"]:
        _fail("deadline expired before dispatch")
    if state["counters"]["dispatches"] >= limits["dispatch_max"]:
        _fail("dispatch ceiling exhausted before dispatch")
    counter_limits = {"retries": "retry_max", "failures": "failure_max", "no_progress": "no_progress_max"}
    if any(state["counters"][name] >= limits[limit] for name, limit in counter_limits.items()):
        _fail("failure, retry, or no-progress ceiling exhausted before dispatch")
    ledger = ActiveTimeLedger.from_record(state["ledger"])
    if ledger.open_intervals:
        _fail("unknown charged interval blocks dispatch")
    if ledger.total_seconds + limits["verification_reserve_seconds"] >= limits["active_seconds_max"]:
        _fail("verification reserve protects dispatch capacity")


def _checkpoint_allows_progress(state: dict[str, Any]) -> None:
    checkpoint = state["checkpoint"]
    if checkpoint is not None and checkpoint["outcome"] in {"blocked", "complete", "verified"}:
        _fail(f"checkpoint is {checkpoint['outcome']}")


def _authenticated_stop(state: dict[str, Any], event: dict[str, Any]) -> None:
    authentication = _mapping(event.get("authentication"), "stop authentication")
    if set(authentication) != {"validated", "source_event_id", "channel"} or authentication["validated"] is not True:
        _fail("Stop requires explicit validated authentication")
    _text(authentication["source_event_id"], "stop source event")
    if authentication["channel"] != state["envelope"]["stop_channel"]:
        _fail("Stop channel is unbound")


def _transition(state: dict[str, Any], name: str, before: str, evidence_digest: str) -> None:
    """Retain evidence only when a reducer fact changes the durable state."""
    if state["status"] != before:
        state["transitions"].append({
            "transition": name,
            "from_status": before,
            "to_status": state["status"],
            "evidence_digest": evidence_digest,
        })


def _fact_transition(state: dict[str, Any], name: str, evidence_digest: str) -> None:
    """Record a new durable fact even when its status does not change."""
    state["transitions"].append({
        "transition": name,
        "from_status": state["status"],
        "to_status": state["status"],
        "evidence_digest": evidence_digest,
    })


def _matching_success(state: dict[str, Any], outcome: str) -> bool:
    checkpoint = state["checkpoint"]
    if checkpoint is None or checkpoint["outcome"] != outcome or checkpoint["operation_id"] is None:
        return False
    operation = state["operations"].get(checkpoint["operation_id"])
    if operation is None or operation["completion"] != "succeeded" or operation["known_effects"] != "succeeded":
        return False
    if outcome == "verified" and operation["verification"] != "succeeded":
        return False
    return any(result["operation_id"] == checkpoint["operation_id"] and result["completion"] == "succeeded"
               and result["known_effects"] == "succeeded"
               and (outcome != "verified" or result["verification"] == "succeeded")
               for result in state["results"])


def _terminal_success_evidence(state: dict[str, Any]) -> bool:
    return bool(state["outcomes"] and state["outcomes"][-1]["outcome"] in {"complete", "verified"}
                and _matching_success(state, state["outcomes"][-1]["outcome"]))


def _terminal_quiescent(state: dict[str, Any]) -> bool:
    """Final handback cannot ignore currently mutable or unresolved work."""
    return (not ActiveTimeLedger.from_record(state["ledger"]).open_intervals
            and all(operation["status"] in _OP_TERMINAL
                and operation["known_effects"] in {"fenced", "succeeded", "failed", "not_run"}
                for operation in state["operations"].values())
            and all(sender["status"] not in {"mutable", "in_flight", "frozen"}
                    for sender in state["senders"].values()))


def _result_progresses(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    """Permit recorded progress, never a contradictory terminal regression."""
    terminal_values = {
        "transport": {"failed", "unknown"},
        "completion": {"succeeded", "failed", "unknown"},
        "verification": {"succeeded", "failed", "unknown"},
        "known_effects": {"succeeded", "failed", "fenced", "unknown", "not_run"},
    }
    return all(previous[name] not in terminal_values[name] or previous[name] == current[name]
               for name in terminal_values)


def _ceiling(state: dict[str, Any], now: int) -> tuple[str, str, str] | None:
    """Read current accounting without changing it; persistence is a ``ceiling`` fact."""
    limits = state["envelope"]["limits"]
    if now >= state["envelope"]["deadline"]:
        return ("deadline", "deadline expired", "expired")
    if state["counters"]["dispatches"] >= limits["dispatch_max"]:
        return ("dispatch", "dispatch ceiling exhausted", "blocked")
    for name, label, limit in (("retries", "retry", "retry_max"), ("failures", "failure", "failure_max"), ("no_progress", "no_progress", "no_progress_max")):
        if state["counters"][name] >= limits[limit]:
            return (label, f"{name} ceiling exhausted", "blocked")
    ledger = ActiveTimeLedger.from_record(state["ledger"])
    if ledger.total_seconds >= limits["active_seconds_max"]:
        return ("active_time", "active-time ceiling exhausted", "blocked")
    if ledger.total_seconds + limits["verification_reserve_seconds"] >= limits["active_seconds_max"]:
        return ("reserve", "verification reserve protects remaining capacity", "blocked")
    return None


def _record_ceiling(state: dict[str, Any], ceiling: tuple[str, str, str], evidence_digest: str) -> None:
    before = state["status"]
    label, reason, status = ceiling
    # Exhaustion closes active authority, but it must not erase a truthful
    # terminal/revocation disposition while that disposition collects closure facts.
    if state["status"] == "active":
        state["status"] = status
    state["ceiling_report"] = {
        "activity": "continuation accounting",
        "progress": "incomplete",
        "ceiling": reason,
        "next_action": "human authorization required",
    }
    _transition(state, f"ceiling:{label}", before, evidence_digest)


def _freeze(state: dict[str, Any]) -> None:
    state["frozen_senders"] = sorted(state["senders"])
    for sender_state in state["senders"].values():
        # Freezing is not terminal/fenced evidence.  That evidence must be a
        # distinct serialized fact before an operator can see ``stopped``.
        sender_state["status"] = "frozen"
    for op_id, operation in state["operations"].items():
        if operation["status"] == "admitted":
            # Admission alone is unsent, but an accepted or queued transport
            # fact is already durable in-flight evidence even if completion
            # has not arrived.  Preserve it for truthful Stop closure.
            if operation["transport"] in {"accepted", "queued"}:
                operation["status"] = "in_flight"
            else:
                operation["status"] = "discarded"
                operation["known_effects"] = "not_run"
        state["frozen_operations"].append(op_id)
    state["frozen_operations"] = sorted(set(state["frozen_operations"]))


def _reduce(value: object, event_value: object) -> dict[str, Any]:
    """Apply one serialized fact; no branch performs host or credential work."""
    state, event = validate_state(value), _event(event_value)
    kind, now = event["type"], _now(event)
    if state["status"] == "stopped" and kind != "observe":
        _fail("terminal stopped state cannot accept further facts")
    if kind == "observe":
        if set(event) - {"type", "now", "facts_complete", "operation_id", "transport", "completion", "verification", "known_effects", "evidence_digest"}:
            _fail("unknown observation fields")
        if state["status"] == "stopped":
            _fail("terminal stopped state cannot be downgraded by observation")
        if not isinstance(event.get("facts_complete"), bool):
            _fail("observation completeness is required")
        state["observation_count"] += 1
        state["observed"] = event["facts_complete"]
        op_id = event.get("operation_id")
        if op_id is None:
            return state
        if not isinstance(op_id, str) or op_id not in state["operations"]:
            _fail("observation operation is unknown")
        _digest(event.get("evidence_digest"), "observation evidence digest")
        before = state["status"]
        operation = state["operations"][op_id]
        transport = event.get("transport")
        if transport not in {"accepted", "queued", "failed", "unknown"}:
            _fail("transport observation is required")
        observation_values = {
            "completion": {"succeeded", "failed", "pending", "unknown"},
            "verification": {"succeeded", "failed", "pending", "unknown", "not_run"},
            "known_effects": {"succeeded", "failed", "pending", "unknown", "fenced", "not_run"},
        }
        for name, allowed in observation_values.items():
            if name in event and event[name] not in allowed:
                _fail(f"{name} observation is malformed")
            if name in event:
                if operation[name] in {"succeeded", "failed", "unknown"} and operation[name] != event[name]:
                    _fail(f"terminal observation contradicts {name}")
                operation[name] = event[name]
        operation["transport"] = transport
        if not event["facts_complete"]:
            operation["status"] = "ambiguous"
            state["status"] = "intervention_required" if state["admission_closed"] else "ambiguous"
        else:
            _update_operation_disposition(state, operation)
        if operation["completion"] in {"succeeded", "failed"} or operation["status"] == "fenced":
            result = {
                "operation_id": op_id,
                "transport": operation["transport"],
                "completion": operation["completion"],
                "verification": operation["verification"],
                "known_effects": operation["known_effects"],
                "evidence_digest": event["evidence_digest"],
            }
            latest = next((item for item in reversed(state["results"])
                           if item["operation_id"] == op_id), None)
            if latest != result:
                state["results"].append(result)
        _transition(state, "observation", before, event["evidence_digest"])
        return validate_state(state)
    if kind == "admit":
        required = {"type", "now", "sender_id", "target", "payload_digest", "task", "slice", "candidate", "action", "attempt", "original_generation"}
        if set(event) != required:
            _fail("admission has unknown or missing fields")
        _admission_allowed(state, now)
        for name in ("sender_id", "target", "task", "slice", "candidate", "action"):
            _text(event[name], name)
        _digest(event["payload_digest"], "payload digest")
        if event["sender_id"] not in state["senders"] or event["target"] not in state["envelope"]["targets"]:
            _fail("admission sender or target is unbound")
        if event["slice"] not in state["envelope"]["approved_afk_slices"]:
            _fail("admission slice is not an approved AFK slice")
        if event["action"] != state["envelope"]["maximum_action"]:
            _fail("admission exceeds maximum action")
        if state["senders"][event["sender_id"]]["status"] not in {"idle", "terminal"} or any(item["status"] in {"mutable", "in_flight"} for item in state["senders"].values()):
            _fail("prior mutable builder is not terminal or fenced")
        for name in ("attempt", "original_generation"):
            _integer(event[name], name)
        if event["attempt"] < 1:
            _fail("attempt must be positive")
        binding = {"authorization_digest": state["authorization_digest"], "run_id": state["run_id"], "epoch": state["epoch"], **{name: event[name] for name in ("sender_id", "target", "payload_digest", "task", "slice", "candidate", "action", "attempt", "original_generation")}}
        receipt_id = "receipt-" + digest(binding).split(":", 1)[1][:24]
        op_id = operation_id(state["run_id"], "continuation", event["target"], {**binding, "receipt_id": receipt_id})
        if op_id in state["operations"]:
            _fail("operation ID already admitted")
        state["operations"][op_id] = {"operation_id": op_id, "receipt_id": receipt_id, **binding, "status": "admitted", "transport": "not_run", "completion": "pending", "verification": "not_run", "known_effects": "pending"}
        state["senders"][event["sender_id"]]["status"] = "mutable"
        state["observed"] = False
        return state
    if kind == "dispatch_started":
        if set(event) != {"type", "now", "operation_id"} or not isinstance(event["operation_id"], str):
            _fail("dispatch fact is malformed")
        operation = state["operations"].get(event["operation_id"])
        if state["status"] != "active" or operation is None or operation["status"] != "admitted" or operation["epoch"] != state["epoch"]:
            _fail("dispatch lacks a current admitted receipt")
        _dispatch_budget_allowed(state, now)
        operation["status"] = "in_flight"
        state["senders"][operation["sender_id"]]["status"] = "in_flight"
        state["counters"]["dispatches"] += 1
        return state
    if kind == "account":
        if set(event) != {"type", "now", "retries", "failures", "no_progress", "evidence_digest"}:
            _fail("accounting fact is malformed")
        if state["status"] != "active":
            _fail("cannot account after stop")
        for name in ("retries", "failures", "no_progress"):
            state["counters"][name] += _integer(event[name], name)
        _digest(event["evidence_digest"], "accounting evidence digest")
        ceiling = _ceiling(state, now)
        if ceiling is not None:
            _record_ceiling(state, ceiling, event["evidence_digest"])
        return state
    if kind == "checkpoint":
        if set(event) != {"type", "now", "checkpoint_id", "outcome", "operation_id", "evidence_digest"} or state["status"] != "active":
            _fail("checkpoint fact is malformed or not active")
        ledger = ActiveTimeLedger.from_record(state["ledger"])
        if ledger.open_intervals:
            _fail("checkpoint requires all charged intervals to close")
        checkpoint = {name: event[name] for name in ("checkpoint_id", "outcome", "operation_id", "evidence_digest")}
        _text(checkpoint["checkpoint_id"], "checkpoint ID")
        if checkpoint["outcome"] not in {"complete", "verified", "incomplete", "blocked", "current_turn_cancelled"}:
            _fail("checkpoint outcome is malformed")
        _digest(checkpoint["evidence_digest"], "checkpoint evidence digest")
        if checkpoint["operation_id"] is not None and (not isinstance(checkpoint["operation_id"], str) or checkpoint["operation_id"] not in state["operations"]):
            _fail("checkpoint operation is unbound")
        if checkpoint["outcome"] in {"complete", "verified"}:
            prospective = {**state, "checkpoint": checkpoint}
            if not _matching_success(prospective, checkpoint["outcome"]):
                _fail("checkpoint lacks matching completed result")
            if not _terminal_quiescent(prospective):
                _fail("terminal checkpoint requires quiescent current operations and senders")
        ceiling = _ceiling(state, now)
        if ceiling is not None:
            _record_ceiling(state, ceiling, checkpoint["evidence_digest"])
        state["checkpoint"] = checkpoint
        return state
    if kind == "optional_counter":
        required = {"type", "now", "name", "value", "reason", "evidence_digest"}
        if set(event) != required or event["name"] not in {"tool_calls", "tokens"}:
            _fail("optional counter fact is malformed")
        _digest(event["evidence_digest"], "optional counter evidence digest")
        value, reason = event["value"], event["reason"]
        if value is None:
            _text(reason, "optional counter reason")
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0 or reason is not None:
            _fail("optional counter value or reason is malformed")
        previous = state["optional_counters"][event["name"]]["value"]
        if previous is not None and (value is None or value < previous):
            _fail("optional counter cannot decrease or become unknown")
        state["optional_counters"][event["name"]] = {"value": value, "reason": reason}
        return state
    if kind == "recover":
        if set(event) != {"type", "now", "operation_id", "controller_generation", "evidence_digest"}:
            _fail("recovery fact is malformed")
        if state["status"] != "active" or not state["observed"]:
            _fail("recovery requires an active observer-first state")
        _dispatch_budget_allowed(state, now)
        operation_id_value = event["operation_id"]
        if not isinstance(operation_id_value, str) or operation_id_value not in state["operations"]:
            _fail("recovery operation is unbound")
        operation = state["operations"][operation_id_value]
        if operation["status"] not in {"admitted", "in_flight", "ambiguous"}:
            _fail("recovery operation is already terminal")
        generation = _integer(event["controller_generation"], "controller generation")
        if generation <= state["recovery"]["controller_generation"]:
            _fail("recovery generation must advance")
        _digest(event["evidence_digest"], "recovery evidence digest")
        # This event intentionally has no admission path: its only identity is
        # the existing operation/receipt, regardless of controller generation.
        state["recovery"] = {"controller_generation": generation, "operation_id": operation_id_value}
        return state
    if kind == "outcome":
        if set(event) != {"type", "now", "outcome", "evidence_digest"}:
            _fail("outcome fact is malformed")
        outcome = event["outcome"]
        status_for_outcome = {
            "complete": "terminal", "verified": "terminal", "incomplete": "blocked", "blocked": "blocked",
            "current_turn_cancelled": state["status"], "intervention_required": "intervention_required",
            "expired": "expired", "ambiguous": "ambiguous",
        }
        if outcome not in status_for_outcome:
            _fail("outcome must use its dedicated Stop transition")
        _digest(event["evidence_digest"], "outcome evidence digest")
        if outcome in {"complete", "verified"} and not _matching_success(state, outcome):
            _fail("terminal outcome lacks matching completion evidence")
        if outcome in {"complete", "verified"} and not _terminal_quiescent(state):
            _fail("terminal outcome requires quiescent current operations and senders")
        before = state["status"]
        ceiling = _ceiling(state, now)
        if state["status"] not in {"active", "expired", "blocked"} or state["admission_closed"]:
            _fail("outcome cannot overwrite a revoked or terminal state")
        if ceiling is not None:
            _record_ceiling(state, ceiling, event["evidence_digest"])
        elif state["status"] != "active":
            _fail("outcome cannot overwrite exhausted state")
        elif outcome == "expired":
            _fail("expired outcome requires a true deadline ceiling")
        else:
            state["status"] = status_for_outcome[outcome]
        next_status = state["status"]
        state["outcomes"].append({"outcome": outcome, "status": next_status, "evidence_digest": event["evidence_digest"]})
        if ceiling is None:
            _transition(state, f"outcome:{outcome}", before, event["evidence_digest"])
        return state
    if kind == "result":
        required = {"type", "now", "operation_id", "transport", "completion", "verification", "known_effects", "evidence_digest"}
        if set(event) != required or not isinstance(event["operation_id"], str) or event["operation_id"] not in state["operations"]:
            _fail("result fact is malformed or unbound")
        if event["transport"] not in {"accepted", "queued", "failed", "unknown"} or event["completion"] not in {"succeeded", "failed", "pending", "unknown"} or event["verification"] not in {"succeeded", "failed", "pending", "unknown", "not_run"} or event["known_effects"] not in {"succeeded", "failed", "fenced", "pending", "unknown", "not_run"}:
            _fail("four-part result fact is malformed")
        _digest(event["evidence_digest"], "result evidence digest")
        if any(item["operation_id"] == event["operation_id"] for item in state["results"]):
            _fail("operation already has durable result evidence")
        result = {name: event[name] for name in ("operation_id", "transport", "completion", "verification", "known_effects", "evidence_digest")}
        state["results"].append(result)
        operation = state["operations"][event["operation_id"]]
        operation.update({name: event[name] for name in ("transport", "completion", "verification", "known_effects")})
        before = state["status"]
        _update_operation_disposition(state, operation)
        _transition(state, "result", before, event["evidence_digest"])
        if state["status"] in {"active", "stopping"}:
            ceiling = _ceiling(state, now)
            if ceiling is not None:
                _record_ceiling(state, ceiling, event["evidence_digest"])
        return state
    if kind == "stop_current_turn":
        if set(event) != {"type", "now"}:
            _fail("current-turn Stop fact is malformed")
        state["current_turn_stop_requested"] = True
        return state
    if kind == "stop_run":
        if set(event) - {"type", "now", "authentication", "persistence_confirmed", "evidence_digest"}:
            _fail("Stop fact has unknown fields")
        _authenticated_stop(state, event)
        _digest(event.get("evidence_digest"), "Stop evidence digest")
        confirmed = event.get("persistence_confirmed")
        if confirmed is not None and not isinstance(confirmed, bool):
            _fail("Stop persistence fact is malformed")
        if confirmed is not True:
            authentication = event["authentication"]
            receipt = {"source_event_id": authentication["source_event_id"], "channel": authentication["channel"], "persistence_confirmed": False, "evidence_digest": event["evidence_digest"]}
            if state["admission_closed"]:
                if state["status"] != "stop_not_confirmed":
                    _fail("admission is already closed with confirmed Stop evidence")
                if state["stop_receipt"] == receipt:
                    return state
                state["stop_receipt"] = receipt
                _fact_transition(state, "stop_not_confirmed", event["evidence_digest"])
                return state
            before = state["status"]
            state["status"] = "stop_not_confirmed"
            state["admission_closed"] = True
            state["stop_receipt"] = receipt
            _transition(state, "stop_not_confirmed", before, event["evidence_digest"])
            return state
        if state["admission_closed"] and state["status"] != "stop_not_confirmed":
            _fail("admission is already closed")
        before = state["status"]
        state["epoch"] += 1
        state["admission_closed"] = True
        state["status"] = "stopping"
        authentication = event["authentication"]
        state["stop_receipt"] = {"source_event_id": authentication["source_event_id"], "channel": authentication["channel"], "persistence_confirmed": True, "evidence_digest": event["evidence_digest"]}
        _freeze(state)
        _transition(state, "stop_run", before, event["evidence_digest"])
        return state
    if kind == "fence_sender":
        if set(event) != {"type", "now", "sender_id", "status", "evidence_digest"} or state["status"] != "stopping":
            _fail("sender fencing fact is malformed")
        sender_id = _text(event["sender_id"], "sender ID")
        if sender_id not in state["senders"] or event["status"] not in _SENDER_TERMINAL:
            _fail("sender fencing fact is unbound")
        if any(item["sender_id"] == sender_id and item["status"] in {"admitted", "in_flight", "ambiguous"} for item in state["operations"].values()):
            _fail("sender fencing contradicts unresolved operation")
        _digest(event["evidence_digest"], "sender evidence digest")
        state["senders"][sender_id]["status"] = event["status"]
        state["sender_evidence"][sender_id] = {"status": event["status"], "evidence_digest": event["evidence_digest"]}
        return state
    if kind in {"interval_start", "interval_stop"}:
        expected = {"type", "now", "interval_id"} | ({"phase"} if kind == "interval_start" else set()) | ({"evidence_digest"} if kind == "interval_stop" and "evidence_digest" in event else set())
        if set(event) != expected:
            _fail("interval fact is malformed")
        if kind == "interval_start":
            if state["status"] != "active":
                _fail("cannot start accounting after stop")
            if now >= state["envelope"]["deadline"]:
                _fail("deadline expired before accounting")
        elif state["status"] not in _ACCOUNTING_CLOSURE_STATUSES:
            _fail("cannot close accounting after terminal stop")
        ledger = ActiveTimeLedger.from_record(state["ledger"])
        ledger_before = ledger.to_record()
        interval_id = _text(event["interval_id"], "interval ID")
        if kind == "interval_stop" and interval_id not in ledger.open_intervals and interval_id not in ledger.charged_ids:
            _fail("unknown charged interval blocks accounting closure")
        if kind == "interval_stop" and interval_id in ledger.charged_ids and interval_id not in ledger.open_intervals:
            return state
        try:
            if kind == "interval_start":
                ledger.start(interval_id, _text(event["phase"], "phase"), now)
            else:
                ledger.stop(interval_id, now)
        except CeilingError as exc:
            if ledger.to_record() == ledger_before:
                _fail(str(exc))
            # ``stop`` charges before checking a genuine hard ceiling, so
            # retain that observed charge while refusing further authority.
            state["ledger"] = ledger.to_record()
            _digest(event.get("evidence_digest"), "active-time ceiling evidence digest")
            before = state["status"]
            if state["status"] == "active":
                state["status"] = "blocked"
            state["ceiling_report"] = {
                "activity": "active-time accounting",
                "progress": "incomplete",
                "ceiling": str(exc),
                "next_action": "human authorization required",
            }
            _transition(state, "ceiling:active_time", before, event["evidence_digest"])
            return state
        state["ledger"] = ledger.to_record()
        if state["status"] in _ACCOUNTING_CLOSURE_STATUSES:
            ceiling = _ceiling(state, now)
            if ceiling is not None:
                _digest(event.get("evidence_digest"), "ceiling evidence digest")
                _record_ceiling(state, ceiling, event["evidence_digest"])
        return state
    if kind == "native_cancellation":
        if set(event) != {"type", "now", "status", "evidence_digest"} or state["status"] != "stopping":
            _fail("native cancellation fact is malformed")
        if event["status"] not in {"requested", "cancelled", "fenced", "not_required", "unknown"}:
            _fail("native cancellation status is malformed")
        _digest(event["evidence_digest"], "native cancellation evidence digest")
        previous_native = state["native_cancellation"]
        if previous_native is not None and previous_native["status"] in {"cancelled", "fenced", "not_required"} and event["status"] != previous_native["status"]:
            _fail("native cancellation cannot regress terminal evidence")
        state["native_cancellation"] = {"status": event["status"], "evidence_digest": event["evidence_digest"]}
        if event["status"] == "cancelled":
            for operation in state["operations"].values():
                if operation["status"] == "fenced":
                    operation["status"] = "cancelled"
        if event["status"] == "unknown":
            before = state["status"]
            state["status"] = "intervention_required"
            _transition(state, "native_cancellation", before, event["evidence_digest"])
        return state
    if kind == "ceiling":
        if set(event) != {"type", "now", "ceiling", "evidence_digest"}:
            _fail("ceiling fact is malformed")
        _digest(event["evidence_digest"], "ceiling evidence digest")
        ceiling = _ceiling(state, now)
        if ceiling is None or event["ceiling"] != ceiling[0]:
            _fail("ceiling fact is not currently true")
        _record_ceiling(state, ceiling, event["evidence_digest"])
        return state
    if kind == "confirm_stopped":
        if set(event) != {"type", "now", "evidence_digest"} or state["status"] != "stopping":
            _fail("stopped confirmation requires stopping")
        _digest(event["evidence_digest"], "stopped confirmation evidence digest")
        if ActiveTimeLedger.from_record(state["ledger"]).open_intervals:
            _fail("all charged intervals must close before stopped confirmation")
        if set(state["sender_evidence"]) != set(state["senders"]):
            _fail("every sender requires terminal or fencing evidence")
        if any(item["status"] not in _OP_TERMINAL for item in state["operations"].values()) or any(item["status"] not in _SENDER_TERMINAL for item in state["senders"].values()):
            _fail("every sender and operation must be terminal or fenced")
        if any(item["known_effects"] not in {"fenced", "succeeded", "failed", "not_run"} for item in state["operations"].values()):
            _fail("known effects are not terminal or fenced")
        if state["native_cancellation"] is None or state["native_cancellation"]["status"] not in {"cancelled", "fenced", "not_required"}:
            _fail("native cancellation evidence is required")
        before = state["status"]
        state["status"] = "stopped"
        _transition(state, "confirm_stopped", before, event["evidence_digest"])
        return state
    _fail("unknown continuation event")


def reduce(value: object, event_value: object) -> dict[str, Any]:
    """Apply one fact and return only a state that passes durable validation."""
    return validate_state(_reduce(value, event_value))


def serialize_state(value: object) -> bytes:
    """Produce canonical JSON only after validating every required durable fact."""
    return canonical_bytes(validate_state(value))


def next_action(value: object, now: int) -> dict[str, str]:
    """Return one conservative reducer decision; it never selects a host target."""
    state = validate_state(value)
    now = _integer(now, "decision now")
    if state["status"] == "stopping":
        return {"action": "fence", "reason": "run is stopping"}
    if state["status"] != "active" or state["admission_closed"]:
        return {"action": "refuse", "reason": f"run is {state['status']}"}
    if now >= state["envelope"]["deadline"]:
        return {"action": "refuse", "reason": "deadline expired"}
    checkpoint = state["checkpoint"]
    if checkpoint is not None:
        if checkpoint["outcome"] in {"complete", "verified"}:
            return {"action": "handback", "reason": f"checkpoint is {checkpoint['outcome']}"}
        if checkpoint["outcome"] == "blocked":
            return {"action": "refuse", "reason": "checkpoint is blocked"}
        if checkpoint["outcome"] == "current_turn_cancelled":
            return {"action": "observe", "reason": "current turn cancellation needs reconciliation"}
    if any(item["status"] in {"in_flight", "ambiguous"} for item in state["operations"].values()):
        return {"action": "observe", "reason": "prior operation requires reconciliation"}
    if not state["observed"]:
        return {"action": "observe", "reason": "observer-first reconciliation is required"}
    try:
        _admission_allowed(state, now)
    except ContinuationError as exc:
        return {"action": "refuse", "reason": str(exc)}
    return {"action": "admit", "reason": "approved run remains active"}


def load_state(raw: bytes | str) -> dict[str, Any]:
    """Load canonical JSON and fail closed before any reducer action."""
    try:
        return validate_state(load_strict(raw))
    except (CanonicalError, CeilingError) as exc:
        raise ContinuationError(str(exc)) from exc

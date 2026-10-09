"""Portable S3 diagnosis, repair, progress, and forecast policy.

This is deliberately a small semantic layer over the interim checkpoint.  It
does not create host workers: the fixture coordinator owns durable intent and
the adapter boundary.  The policy makes a replayed checkpoint subject to the
same rules as a live repair transition.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import digest
from .interim_identity import operation_identities
from .interim_semantics import SemanticError, validate_worker_result
from .interim_routes import route_for_operation


class RepairPolicyError(ValueError):
    pass


def _fail(message: str) -> None:
    raise RepairPolicyError(message)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be a non-empty string")
    return value


def _candidate(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"head", "base"}:
        _fail(f"{label} must contain exact head/base")
    for name in ("head", "base"):
        revision = value[name]
        if not isinstance(revision, str) or len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision):
            _fail(f"{label} {name} is malformed")
    return value


def _task(record: dict[str, Any], slice_id: str) -> dict[str, Any]:
    approved = record["approval"].get("tasks", [])
    matches = [item for item in record["usage"]["operations"] if item.get("phase") == "build" and item.get("slice") == slice_id]
    if len(matches) != 1 or not isinstance(matches[0].get("task"), dict):
        _fail("repair sequence lacks one immutable Build task")
    task = matches[0]["task"]
    task_digest = digest(task)
    if not any(item["id"] == task.get("id") and item["slice_id"] == slice_id and item["digest"] == task_digest for item in approved):
        _fail("repair task is not bound by immutable approval")
    return task


def _operation_id(record: dict[str, Any], task: dict[str, Any], phase: str, repair_attempt: int, candidate: dict[str, str], purpose: str) -> str:
    return "op-" + digest({
        "run": record["approval"]["run_id"], "slice": task["slice_id"],
        "task": task["id"], "attempt": task["attempt"],
        "repair_attempt": repair_attempt, "candidate": candidate["head"],
        "purpose": purpose, "phase": phase,
    })[7:23]


def _observation(operation: dict[str, Any], receipt: object) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("observation") != {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}:
        _fail("repair operation receipt is not correlated to its durable identity")
    return receipt


def _evidence(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        _fail(f"{label} must contain locatable execution evidence")
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "command", "result", "artifact_id"}:
            _fail(f"{label} is malformed")
        for name in ("id", "command", "artifact_id"):
            _text(item[name], f"{label} {name}")
        if item["id"] in seen or item["result"] != "pass":
            _fail(f"{label} is duplicated or non-passing")
        seen.add(item["id"])
    return value


def _runtime(record: dict[str, Any], phase: str, value: object, operation: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"model", "effort", "runner", "permissions"}:
        _fail("repair runtime is malformed")
    route = route_for_operation(record["approval"], operation or {"phase": phase})
    if value.get("model") != route["model"] or value.get("effort") != route["effort"]:
        _fail("repair runtime differs from approved route")
    _text(value.get("runner"), "repair runtime runner")
    _text(value.get("permissions"), "repair runtime permissions")
    return value


def _finding(value: object, criteria: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"id", "criterion_id", "summary", "reversible", "scope", "external_effect", "requirement_changed", "capability", "evidence"}:
        _fail("blocking finding has unknown or missing fields")
    _text(value["id"], "blocking finding id")
    if value["criterion_id"] not in criteria:
        _fail("blocking finding is not tied to an approved criterion")
    _text(value["summary"], "blocking finding summary")
    if value["reversible"] is not True or value["scope"] != "in-scope" or value["external_effect"] is not False or value["requirement_changed"] is not False:
        _fail("blocking finding is not an eligible reversible in-scope repair")
    if value["capability"] != "available":
        _fail("required repair capability is unavailable")
    _evidence(value["evidence"], "blocking finding evidence")
    return value


def _diagnosis(record: dict[str, Any], task: dict[str, Any], repair: dict[str, Any], value: object, prior: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) not in ({"id", "operation_id", "criteria", "revisions", "execution_evidence", "prior_hypotheses", "conclusion", "next_experiment", "actionable"}, {"id", "operation_id", "criteria", "revisions", "execution_evidence", "prior_hypotheses", "conclusion", "next_experiment", "actionable", "blocker"}):
        _fail("diagnosis has unknown or missing fields")
    _text(value["id"], "diagnosis id")
    if value["criteria"] != task["criteria"]:
        _fail("diagnosis criteria differ from approved task")
    if value["revisions"] != repair["opening"]["revisions"]:
        _fail("diagnosis revisions differ from the failed candidate")
    _evidence(value["execution_evidence"], "diagnosis execution evidence")
    if value["prior_hypotheses"] != prior:
        _fail("diagnosis prior hypotheses differ from retained history")
    conclusion = value["conclusion"]
    if not isinstance(conclusion, dict) or set(conclusion) not in ({"cause"}, {"eliminated_hypothesis"}):
        _fail("diagnosis needs a reproducible cause or eliminated hypothesis")
    _text(next(iter(conclusion.values())), "diagnosis conclusion")
    experiment = value["next_experiment"]
    if not isinstance(experiment, dict) or set(experiment) != {"id", "approach", "finding_id"} or experiment["finding_id"] != repair["opening"]["finding"]["id"]:
        _fail("diagnosis needs a changed experiment for the blocking finding")
    _text(experiment["id"], "diagnosis experiment id")
    _text(experiment["approach"], "diagnosis experiment approach")
    if value["actionable"] is not True:
        _text(value.get("blocker"), "unactionable diagnosis blocker")
    elif "blocker" in value:
        _fail("actionable diagnosis must not carry an unavailable blocker")
    return value


def _worker(record: dict[str, Any], operation: dict[str, Any], phase: str, receipt: object, candidate: dict[str, str] | None = None) -> dict[str, Any]:
    """Apply the accepted S2 receipt contract to the S3 logical operation."""
    intent = deepcopy(operation)
    intent["phase"] = phase
    if phase == "verify":
        intent["candidate"] = deepcopy(candidate)
        intent["criteria"] = list(operation["task"]["criteria"])
    projected = receipt
    # A failing fresh Verify still needs the whole approved runtime/evidence
    # contract; only the independent verdict/criterion outcome differs.
    if phase == "verify" and isinstance(receipt, dict) and receipt.get("verdict") == "fail":
        criteria = receipt.get("criteria")
        if receipt.get("task_success") is not True or not isinstance(criteria, dict) or set(criteria) != set(operation["task"]["criteria"]) or any(value not in {"pass", "fail"} for value in criteria.values()) or "fail" not in criteria.values():
            _fail("fresh repair Verify failure must retain complete approved pass/fail criteria")
        projected = deepcopy(receipt)
        projected["criteria"] = {item: "pass" for item in operation["task"]["criteria"]}
        projected["verdict"] = "pass"
    try:
        validate_worker_result(projected, intent, phase.title(), route_for_operation(record["approval"], operation), operation["task"], candidate)
    except SemanticError as exc:
        _fail(str(exc))
    return receipt


def _progress(repair: dict[str, Any], cycle: dict[str, Any], value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"id", "cycle_id", "criterion_id", "finding_id", "before", "after", "verification_operation_id", "evidence"}:
        _fail("progress evidence has unknown or missing fields")
    _text(value["id"], "progress id")
    if value["cycle_id"] != cycle["id"] or value["criterion_id"] != repair["opening"]["finding"]["criterion_id"] or value["finding_id"] != repair["opening"]["finding"]["id"]:
        _fail("progress evidence is not bound to the approved blocker")
    _text(value["before"], "progress before observation")
    _text(value["after"], "progress after observation")
    if value["before"] == value["after"] or value["verification_operation_id"] != cycle["verify_operation_id"]:
        _fail("progress evidence is not independently verified before/after evidence")
    _evidence(value["evidence"], "progress execution evidence")
    return value


def validate_repair(record: dict[str, Any]) -> None:
    """Validate S3 policy state after generic ledger validation has succeeded."""
    if "repair" not in record:
        return
    repair = record["repair"]
    if not isinstance(repair, dict) or set(repair) not in ({"slice_id", "opening", "status", "diagnoses", "cycles", "progress", "batch"}, {"slice_id", "opening", "status", "diagnoses", "cycles", "progress", "batch", "escalated_slots"}):
        _fail("repair state has unknown or missing fields")
    escalation = record["approval"].get("escalation_policy")
    if ("escalated_slots" in repair) != (escalation is not None):
        _fail("repair escalation state differs from immutable approval")
    if escalation is None and any(("escalated_slot" in item or "escalated_verify" in item) and item.get("slice") == repair["slice_id"]
                                  for item in record["usage"]["operations"]):
        _fail("legacy repair has no escalated worker authority")
    if escalation is not None and (not isinstance(repair["escalated_slots"], list) or len(repair["escalated_slots"]) > escalation["cycles_per_slice"]):
        _fail("repair escalation slot allowance is malformed")
    task = _task(record, repair["slice_id"])
    opening = repair["opening"]
    allowed_openings = ({"finding", "criteria", "revisions", "execution_evidence"},
                        {"finding", "criteria", "revisions", "execution_evidence", "origin_operation_id"})
    if not isinstance(opening, dict) or set(opening) not in allowed_openings or opening["criteria"] != task["criteria"]:
        _fail("repair opening is malformed")
    if "origin_operation_id" in opening:
        origin = next((item for item in record["usage"]["operations"] if item["id"] == opening["origin_operation_id"]), None)
        if (origin is None or origin.get("slice") != repair["slice_id"] or origin.get("status") not in {"result-unusable", "result", "reconciled"}
                or origin.get("phase") not in {"build", "verify"} or not isinstance(origin.get("failure_reconciliation"), dict)
                or origin.get("status") in {"result", "reconciled"} and (origin.get("phase") != "verify" or origin.get("receipt", {}).get("verdict") != "fail")
                or origin["failure_reconciliation"]["candidate"] != opening["revisions"]):
            _fail("worker-failure repair opening lacks reconciled predecessor")
    _finding(opening["finding"], task["criteria"])
    _candidate(opening["revisions"], "repair opening revisions")
    _evidence(opening["execution_evidence"], "repair opening execution evidence")
    if repair["status"] not in {"diagnosis-required", "repair-ready", "repair-verify-ready", "waiting-diagnosis", "waiting-repair", "waiting-repair-verify", "worker-failed", "stuck", "completed", "handback", "escalation-ready"} or not isinstance(repair["diagnoses"], list) or not isinstance(repair["cycles"], list) or not isinstance(repair["progress"], list):
        _fail("repair policy containers are malformed")
    if repair["status"] == "worker-failed":
        state = record["state"]
        failed = [item for item in record["usage"]["operations"]
                  if item.get("slice") == repair["slice_id"]
                  and item.get("phase") in {"diagnosis", "repair", "repair-verify"}
                  and item.get("repair_attempt") == len(repair["cycles"]) + 1
                  and item.get("status") == "result-unusable"
                  and isinstance(item.get("receipt"), dict)]
        unreconciled = [item for item in failed if not isinstance(item.get("failure_reconciliation"), dict)]
        recovery = record.get("recovery", {})
        active_boundary = (state.get("next_action") == "worker-failed"
                           and state.get("slice_id") == repair["slice_id"]
                           and len(unreconciled) == 1 and state.get("operation_id") == unreconciled[0]["id"])
        reconciled_boundary = (state.get("next_action") == "failure-reconciled"
                               and state.get("slice_id") == repair["slice_id"]
                               and failed and isinstance(failed[-1].get("failure_reconciliation"), dict))
        stopped_boundary = (recovery.get("status") in {"stopping", "stopped", "uncertain", "resumed"}
                            and state.get("next_action") in {"handback", "recovered"}
                            and bool(failed))
        if "monitoring" not in record or not (active_boundary or reconciled_boundary or stopped_boundary):
            _fail("failed repair worker boundary lacks its exact error operation")
    # In-flight phases are portable policy, not a local continuation. Validate
    # the exact next attempt so a restart cannot poll or project another cycle.
    pending_phase = repair["status"].removeprefix("waiting-") if repair["status"].startswith("waiting-") else None
    if pending_phase or repair["status"] == "repair-verify-ready":
        phase = pending_phase or "repair"
        operations = [item for item in record["usage"]["operations"] if item["phase"] == phase and item.get("slice") == repair["slice_id"] and item.get("repair_attempt") == len(repair["cycles"]) + 1
                      and (item["status"] in {"intent", "reconcile-required"} if pending_phase else item.get("receipt", {}).get("task_success") is True)]
        if len(operations) != 1:
            _fail("resumable repair phase lacks one exact current operation")
        operation = operations[0]
        candidate = opening["revisions"]
        if phase == "diagnosis":
            prior_attempts = sum(item["phase"] == "diagnosis" and item.get("slice") == repair["slice_id"] and item["id"] != operation["id"] for item in record["usage"]["operations"])
            purpose = f"diagnosis-{prior_attempts + 1}"
        else:
            diagnosis = next((item for item in repair["diagnoses"] if item["id"] == repair["batch"]["diagnosis_id"]), None)
            if phase == "repair" and "escalated_slot" in operation:
                purpose = operation["purpose"]
                diagnosis = {"next_experiment": {"id": purpose}}
            if diagnosis is None:
                _fail("resumable repair phase lacks its accepted diagnosis")
            purpose = diagnosis["next_experiment"]["id"]
            if phase == "repair-verify":
                parent = next((item for item in reversed(record["usage"]["operations"]) if item["phase"] == "repair" and item.get("slice") == repair["slice_id"] and item.get("repair_attempt") == operation["repair_attempt"]
                               and (not operation.get("escalated_verify") or item["id"] == operation["escalated_verify"])), None)
                if parent is None or parent["status"] not in {"result", "reconciled"}:
                    _fail("pending repair Verify lacks its successful repair")
                candidate = _worker(record, parent, "build", parent.get("receipt"))["candidate"]
                if operation.get("candidate") != candidate:
                    _fail("pending repair Verify candidate differs from its repair")
                attempt = operation.get("verify_attempt", 1)
                if type(attempt) is not int or not 1 <= attempt <= 3:
                    _fail("fresh Verify retry is outside the bounded allowance")
                purpose = purpose if attempt == 1 else purpose + f"-verify-{attempt}"
        _validate_operation(record, task, repair, operation, purpose, len(repair["cycles"]) + 1, candidate)
        if pending_phase:
            if operation["status"] not in {"intent", "reconcile-required"}:
                _fail("waiting repair phase does not retain a pending operation")
            if operation["status"] == "intent" and operation.get("receipt") is not None:
                _fail("pending repair intent cannot contain a receipt")
            if operation["status"] == "reconcile-required":
                receipt = _observation(operation, operation.get("receipt"))
                if receipt.get("terminal_turn") is True or not (receipt.get("worker_state") in {"queued", "active", "unknown"} or receipt.get("transport") in {"timeout", "unknown"}):
                    _fail("waiting repair requires nonterminal transport evidence")
        elif operation["status"] not in {"result", "reconciled"} or record["state"].get("candidate") != _worker(record, operation, "build", operation.get("receipt"))["candidate"]:
            _fail("repair Verify admission lacks a durable successful candidate")
    diagnosis_ids: set[str] = set()
    prior_hypotheses: list[str] = []
    for diagnosis in repair["diagnoses"]:
        _diagnosis(record, task, repair, diagnosis, prior_hypotheses)
        if diagnosis["id"] in diagnosis_ids:
            _fail("diagnosis IDs must be unique")
        if any(previous["next_experiment"]["approach"] == diagnosis["next_experiment"]["approach"] for previous in repair["diagnoses"][:len(diagnosis_ids)]):
            _fail("fresh diagnosis must choose a changed repair approach")
        diagnosis_ids.add(diagnosis["id"])
        operation = next((item for item in record["usage"]["operations"] if item["id"] == diagnosis["operation_id"]), None)
        if not isinstance(operation, dict) or (operation.get("phase") != "diagnosis" and not (operation.get("phase") == "repair" and "escalated_slot" in operation)):
            _fail("diagnosis lacks its durable operation")
        _validate_operation(record, task, repair, operation, diagnosis["id"], operation.get("repair_attempt"), opening["revisions"])
        receipt = _observation(operation, operation.get("receipt"))
        if (receipt.get("diagnosis") != diagnosis or receipt.get("transport") != "accepted" or receipt.get("terminal_turn") is not True
                or receipt.get("task_success") is not True and "escalated_slot" not in operation):
            _fail("diagnosis receipt is incomplete or differs from durable diagnosis")
        _runtime(record, "diagnosis", receipt.get("runtime"), operation)
        prior_hypotheses.append(next(iter(diagnosis["conclusion"].values())))
    cycle_ids: set[str] = set()
    unsuccessful = 0
    for index, cycle in enumerate(repair["cycles"], start=1):
        if not isinstance(cycle, dict) or set(cycle) != {"id", "attempt", "diagnosis_id", "experiment_id", "repair_operation_id", "verify_operation_id", "outcome", "finding"}:
            _fail("repair cycle has unknown or missing fields")
        if cycle["id"] != f"cycle-{index}" or cycle["attempt"] != index or cycle["id"] in cycle_ids or cycle["diagnosis_id"] not in diagnosis_ids:
            _fail("repair cycles are not unique and ordered")
        cycle_ids.add(cycle["id"])
        _finding(cycle["finding"], task["criteria"])
        if cycle["finding"] != opening["finding"]:
            _fail("repair cycle changed its blocking finding")
        diagnosis = next(item for item in repair["diagnoses"] if item["id"] == cycle["diagnosis_id"])
        if cycle["experiment_id"] != diagnosis["next_experiment"]["id"]:
            _fail("repair cycle did not use its diagnosis experiment")
        repair_op = next((item for item in record["usage"]["operations"] if item["id"] == cycle["repair_operation_id"]), None)
        if not isinstance(repair_op, dict) or repair_op.get("phase") != "repair":
            _fail("repair cycle lacks its durable repair operation")
        _validate_operation(record, task, repair, repair_op, cycle["experiment_id"], cycle["attempt"], opening["revisions"])
        verify_op = next((item for item in record["usage"]["operations"] if cycle["verify_operation_id"] is not None and item["id"] == cycle["verify_operation_id"]), None)
        if cycle["outcome"] == "incomplete":
            unsuccessful += 1
            repair_receipt = repair_op.get("receipt")
            if repair_receipt is None:
                if cycle["verify_operation_id"] is not None or repair_op.get("status") != "intent":
                    _fail("unobserved incomplete repair must retain its durable intent")
                continue
            repair_receipt = _observation(repair_op, repair_receipt)
            if repair_op.get("status") == "result-unusable":
                _unusable(repair_op)
                if cycle["verify_operation_id"] is not None:
                    _fail("unusable repair cannot fabricate a fresh Verify")
                continue
            if repair_receipt.get("task_success") is True:
                candidate = _worker(record, repair_op, "build", repair_receipt)["candidate"]
                if cycle["verify_operation_id"] is None:
                    # A selected ceiling can refuse Verify admission before its
                    # intent exists; the successful repair remains truthful.
                    continue
                if not isinstance(verify_op, dict) or verify_op.get("phase") != "repair-verify":
                    _fail("successful repair incomplete cycle lacks its pending fresh Verify")
                retry = verify_op.get("verify_attempt", 1)
                if type(retry) is not int or not 1 <= retry <= 3:
                    _fail("fresh Verify retry is outside the bounded allowance")
                _validate_operation(record, task, repair, verify_op, cycle["experiment_id"] if retry == 1 else cycle["experiment_id"] + f"-verify-{retry}", cycle["attempt"], candidate)
                if verify_op.get("status") in {"intent", "reconcile-required"}:
                    if verify_op.get("receipt") is not None:
                        _fail("incomplete fresh Verify must retain only pending/reconciliation evidence")
                elif verify_op.get("status") == "result-unusable":
                    _unusable(verify_op)
                else:
                    _fail("incomplete fresh Verify must retain pending or unusable evidence")
            elif cycle["verify_operation_id"] is not None or verify_op is not None:
                _fail("failed repair cannot fabricate a fresh Verify")
            continue
        repair_receipt = _observation(repair_op, repair_op.get("receipt"))
        if not isinstance(cycle["verify_operation_id"], str) or not cycle["verify_operation_id"]:
            _fail("completed repair cycle lacks a fresh Verify operation ID")
        if repair_receipt.get("task_success") is not True or not isinstance(verify_op, dict) or verify_op.get("phase") != "repair-verify":
            _fail("completed repair cycle lacks successful repair and fresh Verify")
        candidate = _worker(record, repair_op, "build", repair_receipt)["candidate"]
        verify_attempt = verify_op.get("verify_attempt", 1)
        if type(verify_attempt) is not int or not 1 <= verify_attempt <= 3:
            _fail("fresh Verify retry is outside the bounded allowance")
        verify_purpose = cycle["experiment_id"] if verify_attempt == 1 else cycle["experiment_id"] + f"-verify-{verify_attempt}"
        _validate_operation(record, task, repair, verify_op, verify_purpose, cycle["attempt"], candidate)
        verify_receipt = _observation(verify_op, verify_op.get("receipt"))
        _worker(record, verify_op, "verify", verify_receipt, candidate)
        criteria = verify_receipt.get("criteria")
        if verify_receipt.get("verdict") not in {"pass", "fail"} or not isinstance(criteria, dict) or set(criteria) != set(task["criteria"]) or any(value not in {"pass", "fail"} for value in criteria.values()) or (verify_receipt["verdict"] == "pass" and any(value != "pass" for value in criteria.values())) or (verify_receipt["verdict"] == "fail" and "fail" not in criteria.values()):
            _fail("fresh repair Verify verdict/criteria is malformed")
        if cycle["outcome"] != verify_receipt["verdict"]:
            _fail("repair cycle outcome differs from fresh Verify")
        if cycle["outcome"] == "fail":
            unsuccessful += 1
    if unsuccessful != sum(cycle["outcome"] != "pass" for cycle in repair["cycles"]):
        _fail("repair cumulative failure history is malformed")
    progress_ids: set[str] = set()
    for value in repair["progress"]:
        cycle = next((item for item in repair["cycles"] if isinstance(value, dict) and item["id"] == value.get("cycle_id")), None)
        if cycle is None:
            _fail("progress evidence names an unknown cycle")
        _progress(repair, cycle, value)
        if value["id"] in progress_ids:
            _fail("progress evidence cannot be credited twice")
        progress_ids.add(value["id"])
    batch = repair["batch"]
    if not isinstance(batch, dict) or set(batch) != {"diagnosis_id", "cycles", "no_progress", "credited_progress"} or (batch["diagnosis_id"] is not None and batch["diagnosis_id"] not in diagnosis_ids) or type(batch["cycles"]) is not int or type(batch["no_progress"]) is not int or not isinstance(batch["credited_progress"], list):
        _fail("repair batch is malformed")
    if batch["cycles"] < 0 or batch["cycles"] > 3 or batch["no_progress"] < 0 or batch["no_progress"] > 3 or len(batch["credited_progress"]) != len(set(batch["credited_progress"])) or any(item not in progress_ids for item in batch["credited_progress"]):
        _fail("repair batch counters are malformed")
    if repair["status"] == "repair-ready" and batch["diagnosis_id"] is None:
        _fail("repair-ready state requires an accepted diagnosis")
    if repair["status"] == "completed" and (not repair["cycles"] or repair["cycles"][-1]["outcome"] != "pass"):
        _fail("repair completion requires passing fresh Verify")
    if repair["status"] == "stuck" and batch["no_progress"] != 3 and escalation is None:
        _fail("stuck repair requires three no-progress cycles")
    ordinary_unsuccessful = sum(cycle["outcome"] != "pass" and not any(op["id"] == cycle["repair_operation_id"] and "escalated_slot" in op for op in record["usage"]["operations"]) for cycle in repair["cycles"])
    if repair["status"] == "escalation-ready" and (escalation is None or ordinary_unsuccessful < escalation["trigger"]):
        _fail("escalation requires cumulative unsuccessful ordinary repairs and explicit approval")
    if escalation is not None:
        slots = repair["escalated_slots"]
        operation_order = {item["id"]: index for index, item in enumerate(record["usage"]["operations"])}
        if len(slots) != len(set(slots)):
            _fail("escalated slots must be unique")
        if slots:
            first_slot = operation_order[slots[0]] if slots[0] in operation_order else -1
            before = sum(cycle["outcome"] != "pass" and operation_order.get(cycle["repair_operation_id"], first_slot) < first_slot
                         and not any(op["id"] == cycle["repair_operation_id"] and "escalated_slot" in op for op in record["usage"]["operations"])
                         for cycle in repair["cycles"])
            if before < escalation["trigger"]:
                _fail("escalated slot precedes the cumulative ordinary repair trigger")
        for index, operation_id in enumerate(slots, start=1):
            operation = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), None)
            if (operation is None or operation.get("phase") != "repair" or operation.get("slice") != repair["slice_id"]
                    or operation.get("escalated_slot") != index or operation.get("route") != route_for_operation(record["approval"], operation)
                    or operation.get("escalation_reason") != "cumulative ordinary repair failures reached approved trigger"):
                _fail("escalated slot lacks one exact approved worker operation")
            if "route_preflight" in operation and operation["route_preflight"] != {"session_id": operation["session_id"], **operation["route"]}:
                _fail("escalated preflight differs from exact approved route")
            if (operation["status"] != "intent" or "receipt" in operation or "send_admission" in operation
                    or "cancellation" in operation or "failure_reconciliation" in operation) and "route_preflight" not in operation:
                _fail("escalated worker effect or receipt lacks authoritative preflight")
            if index > 1 and operation_order[operation_id] <= operation_order[slots[index - 2]]:
                _fail("escalated slots are out of durable order")
        if any(item.get("escalated_slot") and item["id"] not in slots for item in record["usage"]["operations"] if item.get("slice") == repair["slice_id"]):
            _fail("unreserved escalated worker operation")
        if slots and any(item["phase"] in {"diagnosis", "repair"} and "escalated_slot" not in item and item["slice"] == repair["slice_id"]
                         and operation_order[item["id"]] > operation_order[slots[0]] for item in record["usage"]["operations"]):
            _fail("ordinary repair or diagnosis resumed after escalation")
        retries: dict[str, list[dict[str, Any]]] = {}
        for operation in record["usage"]["operations"]:
            if operation.get("slice") != repair["slice_id"] or "escalated_verify" not in operation:
                continue
            parent_id = operation["escalated_verify"]
            parent = next((item for item in record["usage"]["operations"] if item["id"] == parent_id), None)
            if parent_id not in slots or parent is None or parent.get("status") not in {"result", "reconciled"}:
                _fail("fresh escalated Verify lacks one successful reserved implementation")
            candidate = _worker(record, parent, "build", parent.get("receipt"))["candidate"]
            if operation.get("verify_context") != {"build_operation_id": parent_id, "candidate": candidate,
                                                    "criteria": list(task["criteria"]),
                                                    "artifact_id": parent["receipt"]["evidence"]["artifact"]["id"]}:
                _fail("fresh escalated Verify lacks compact candidate evidence")
            attempts = retries.setdefault(parent_id, [])
            attempt = operation.get("verify_attempt")
            if type(attempt) is not int or attempt != len(attempts) + 1 or attempt > 3 or operation.get("candidate") != candidate:
                _fail("fresh escalated Verify retry or candidate is malformed")
            purpose = parent["purpose"] if attempt == 1 else parent["purpose"] + f"-verify-{attempt}"
            _validate_operation(record, task, repair, operation, purpose, parent["repair_attempt"], candidate)
            if attempts:
                previous = attempts[-1]
                if previous.get("status") != "result-unusable" or previous.get("failure_reconciliation", {}).get("candidate") != candidate:
                    _fail("fresh Verify retry lacks exact failed-verifier reconciliation")
            attempts.append(operation)
    if unsuccessful >= 3 and repair["status"] == "repair-ready" and len(repair["diagnoses"]) <= unsuccessful:
        _fail("three unsuccessful repair cycles require fresh diagnosis")
    operation_ids = {item["id"] for item in record["usage"]["operations"] if isinstance(item, dict) and isinstance(item.get("receipt"), dict)}
    for revision in record["forecasts"]["revised"]:
        if revision["evidence"]["operation_id"] not in operation_ids:
            _fail("revised forecast is not tied to a retained worker-result checkpoint")


def _unusable(operation: dict[str, Any]) -> None:
    if not isinstance(operation.get("validation_error"), str) or not operation["validation_error"]:
        _fail("unusable observed operation lacks its typed validation error")


def _validate_operation(record: dict[str, Any], task: dict[str, Any], repair: dict[str, Any], operation: dict[str, Any], purpose: str, repair_attempt: object, candidate: object) -> None:
    if type(repair_attempt) is not int or repair_attempt < 1:
        _fail("repair operation attempt is malformed")
    candidate = _candidate(candidate, "repair operation candidate")
    if operation.get("slice") != repair["slice_id"] or operation.get("task") != task or operation.get("purpose") != purpose or operation.get("repair_attempt") != repair_attempt:
        _fail("repair operation purpose differs from durable repair policy")
    if "route" in operation and operation["route"] != route_for_operation(record["approval"], operation):
        _fail("repair intent route differs from immutable approval")
    expected = _operation_id(record, task, operation["phase"], repair_attempt, candidate, purpose)
    identities = operation_identities(record["approval"]["run_id"], expected, operation["phase"])
    if operation.get("id") != expected or {name: operation.get(name) for name in identities} != identities:
        _fail("repair operation identity is not derived from immutable purpose")


def repair_operation_id(record: dict[str, Any], task: dict[str, Any], phase: str, repair_attempt: int, candidate: dict[str, str], purpose: str) -> str:
    """Public deterministic operation identity used by the fixture coordinator."""
    return _operation_id(record, task, phase, repair_attempt, candidate, purpose)


def copy_repair(value: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(value)

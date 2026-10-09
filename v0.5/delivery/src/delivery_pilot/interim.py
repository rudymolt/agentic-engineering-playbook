"""Validated, exact-ref records for the explicitly weaker interim coordinator.

The record and store validate the one human approval, persist its checkpoint to
the approval's exact remote ref, and make uncertain publication a reconciliation
problem. The ``advance`` entrypoint delegates host effects to the shipped
adapters only after loading that durable authority.
"""

from __future__ import annotations

import subprocess
import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .canonical import CanonicalError, canonical_bytes, digest, load_strict
from .git_control import GitControlStore, GitSnapshot
from .state import CasMismatch


class InterimError(ValueError):
    """The interim coordinator refused malformed or unapproved input."""


CHECKPOINT_FAILURE_CODES = frozenset({"unspecified", "missing", "fetch", "corrupt", "moved",
                                      "target", "cas-lost", "push-failed"})


class InterimCheckpointError(RuntimeError):
    """The exact remote checkpoint could not be safely published or reconciled.

    ``code`` is a fixed, log-safe failure detail such as ``moved`` or
    ``corrupt``; the message itself never enters recovery logs.
    """
    def __init__(self, message: str = "", code: str = "unspecified"):
        super().__init__(message)
        self.code = code if code in CHECKPOINT_FAILURE_CODES else "unspecified"


# A concurrent delivery may publish between ls-remote and fetch.  Reloading is
# read-only, so a bounded re-read is always safe; a ref that keeps moving is
# still refused.
RELOAD_ATTEMPTS = 3


@dataclass(frozen=True)
class InterimCheckpointSnapshot:
    value: dict[str, Any]
    digest: str
    commit_sha: str
    reconciled: bool = False
    # The control record cannot contain its own commit hash (that would be a
    # cryptographic fixed point).  Monitoring instead binds a wake record to
    # the one parent commit that the exact-ref CAS advanced from.
    parent_commits: tuple[str, ...] = ()


_APPROVAL_FIELDS = {
    "kind", "version", "approval_id", "source_event_id", "run_id", "repository", "tracker", "slices",
    "implementation_paths", "workspaces", "coordinator", "routes", "forecast", "progress_checkpoint_policy", "hard_limits",
    "maximum_action", "checkpoint", "whole_run_stop",
}
_S2_APPROVAL_FIELDS = _APPROVAL_FIELDS | {"tasks"}
_ESCALATION_APPROVAL_FIELDS = _APPROVAL_FIELDS | {"escalation_policy"}
_S2_ESCALATION_APPROVAL_FIELDS = _S2_APPROVAL_FIELDS | {"escalation_policy"}
_RECORD_FIELDS = {"kind", "version", "approval", "approval_digest", "forecasts", "usage", "state"}
_S3_RECORD_FIELDS = _RECORD_FIELDS | {"repair"}
_S4_RECORD_FIELDS = _S3_RECORD_FIELDS | {"recovery"}
_S4_BASE_RECORD_FIELDS = _RECORD_FIELDS | {"recovery"}
_S6_BASE_RECORD_FIELDS = _RECORD_FIELDS | {"monitoring"}
_S6_REPAIR_RECORD_FIELDS = _S3_RECORD_FIELDS | {"monitoring"}
_S6_RECOVERY_BASE_RECORD_FIELDS = _S4_BASE_RECORD_FIELDS | {"monitoring"}
_S6_RECORD_FIELDS = _S4_RECORD_FIELDS | {"monitoring"}
_ROUTE_NAMES = {"build", "verify", "diagnosis"}
_DIGEST_PREFIX = "sha256:"


def _record_field_sets() -> tuple[set[str], ...]:
    """All additive interim records, including the S5 stack extension.

    Each slice has deliberately extended the same portable checkpoint rather
    than creating an adjacent local state file.  Keep that shape explicit here
    so an S5 checkpoint can still travel through the S3/S4 validators.
    """
    bases = (_RECORD_FIELDS, _S3_RECORD_FIELDS, _S4_BASE_RECORD_FIELDS, _S4_RECORD_FIELDS)
    extended = bases + (_S6_BASE_RECORD_FIELDS, _S6_REPAIR_RECORD_FIELDS, _S6_RECOVERY_BASE_RECORD_FIELDS, _S6_RECORD_FIELDS)
    variants = extended + tuple(fields | {"stack"} for fields in extended)
    variants += tuple(fields | {"repair_history"} for fields in variants if "repair" in fields)
    return variants + tuple(fields | {"recovery_disposition"} for fields in variants)


def _fail(message: str) -> None:
    raise InterimError(message)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{name} must be a non-empty string")
    return value


def _path(value: object, name: str) -> str:
    value = _text(value, name)
    parts = value.split("/")
    if value.startswith("/") or value.endswith("/") or any(part in {"", ".", ".."} for part in parts):
        _fail(f"{name} must be a normalized relative path")
    return value


def _digest(value: object, name: str) -> str:
    value = _text(value, name)
    if len(value) != 71 or not value.startswith(_DIGEST_PREFIX) or any(char not in "0123456789abcdef" for char in value[7:]):
        _fail(f"{name} must be a sha256 digest")
    return value


def _control_ref(value: object, name: str, run_id: str) -> str:
    value = _text(value, name)
    expected = f"refs/heads/delivery-control/issue-{run_id}"
    if value != expected:
        _fail(f"{name} must be the run-specific control ref")
    if subprocess.run(["git", "check-ref-format", value], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode:
        _fail(f"{name} is not valid Git ref syntax")
    return value


def _utc_timestamp(value: object, name: str) -> str:
    value = _text(value, name)
    if not value.endswith("Z") or "T" not in value:
        _fail(f"{name} must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InterimError(f"{name} must be a UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        _fail(f"{name} must be a UTC timestamp")
    return value


def _nonoverlapping_paths(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail(f"{name} must be a non-empty path list")
    paths = [_path(item, name) for item in value]
    if len(paths) != len(set(paths)):
        _fail(f"{name} must be unique")
    for index, path in enumerate(paths):
        if any(path.startswith(other + "/") or other.startswith(path + "/") for other in paths[:index]):
            _fail(f"{name} must not overlap")
    return paths


def _acyclic_slices(slices: list[dict[str, Any]]) -> None:
    by_id = {item["id"]: item for item in slices}
    for item in slices:
        dependencies = item["dependencies"]
        if len(dependencies) != len(set(dependencies)):
            _fail("slice dependencies must be unique")
        if item["id"] in dependencies:
            _fail("slice must not depend on itself")
        if any(dependency not in by_id for dependency in dependencies):
            _fail("slice dependency is outside approved scope")
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(slice_id: str) -> None:
        if slice_id in complete:
            return
        if slice_id in visiting:
            _fail("slice dependencies must be acyclic")
        visiting.add(slice_id)
        for dependency in by_id[slice_id]["dependencies"]:
            visit(dependency)
        visiting.remove(slice_id)
        complete.add(slice_id)

    for slice_id in by_id:
        visit(slice_id)


def _route(value: object, name: str) -> None:
    value = _mapping(value, name)
    if set(value) != {"model", "effort", "fallback"}:
        _fail(f"{name} has unknown or missing fields")
    _text(value["model"], f"{name} model")
    _text(value["effort"], f"{name} effort")
    if value["fallback"] is not None:
        _text(value["fallback"], f"{name} fallback")


def validate_approval(value: object) -> dict[str, Any]:
    """Validate the complete, immutable S1 approval contract without defaults."""
    approval = _mapping(value, "interim approval")
    if "hard_limits" not in approval:
        _fail("hard_limits must be explicitly none or human-selected values")
    if set(approval) not in (_APPROVAL_FIELDS, _S2_APPROVAL_FIELDS, _ESCALATION_APPROVAL_FIELDS, _S2_ESCALATION_APPROVAL_FIELDS) or approval.get("kind") != "interim-run-approval" or approval.get("version") != 1:
        _fail("interim approval has unknown or missing fields")
    if "escalation_policy" in approval:
        policy = _mapping(approval["escalation_policy"], "escalation policy")
        if (set(policy) != {"route", "trigger", "scope", "authority", "cycles_per_slice"}
                or type(policy["trigger"]) is not int or policy["trigger"] < 1
                or type(policy["cycles_per_slice"]) is not int or policy["cycles_per_slice"] < 1
                or policy["scope"] != "approved-slice" or policy["authority"] != "diagnose-and-implement"):
            _fail("escalation policy must explicitly bound trigger, slice scope, authority, and cycles")
        route = _mapping(policy["route"], "escalation route")
        if set(route) != {"model", "effort"}:
            _fail("escalation route must name one model and effort")
        for name in ("model", "effort"):
            _text(route[name], "escalation " + name)
    for name in ("approval_id", "source_event_id", "run_id", "progress_checkpoint_policy", "whole_run_stop"):
        _text(approval[name], name)
    repository = _mapping(approval["repository"], "repository")
    if set(repository) not in ({"remote", "fetch_url", "push_url", "control_ref"},
                               {"remote", "fetch_url", "push_url", "control_ref", "base_ref"}):
        _fail("repository has unknown or missing fields")
    _text(repository["remote"], "repository remote")
    _text(repository["fetch_url"], "repository fetch_url")
    _text(repository["push_url"], "repository push_url")
    if "base_ref" in repository:
        base_ref = _text(repository["base_ref"], "repository base_ref")
        if not base_ref.startswith("refs/heads/") or subprocess.run(["git", "check-ref-format", base_ref], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode:
            _fail("repository base_ref must be a full branch ref")
    _control_ref(repository["control_ref"], "repository control_ref", approval["run_id"])
    tracker = _mapping(approval["tracker"], "tracker")
    if set(tracker) != {"id", "spec_revision"}:
        _fail("tracker has unknown or missing fields")
    _text(tracker["id"], "tracker id")
    _digest(tracker["spec_revision"], "tracker spec_revision")
    slices = approval["slices"]
    if not isinstance(slices, list) or not slices:
        _fail("slices must be a non-empty list")
    slice_ids: set[str] = set()
    normalized_slices: list[dict[str, Any]] = []
    for item in slices:
        item = _mapping(item, "slice")
        if set(item) != {"id", "dependencies", "mode"}:
            _fail("slice has unknown or missing fields")
        slice_id = _text(item["id"], "slice id")
        if slice_id in slice_ids:
            _fail("slice IDs must be unique")
        slice_ids.add(slice_id)
        if not isinstance(item["dependencies"], list) or any(not isinstance(dependency, str) or not dependency for dependency in item["dependencies"]):
            _fail("slice dependencies must be a string list")
        if item["mode"] not in {"AFK", "HITL"}:
            _fail("slice mode must be AFK or HITL")
        normalized_slices.append(item)
    _acyclic_slices(normalized_slices)
    if "tasks" in approval:
        if not isinstance(approval["tasks"], list) or not approval["tasks"]:
            _fail("S2 tasks must be a non-empty list")
        seen_tasks: set[str] = set()
        for task in approval["tasks"]:
            task = _mapping(task, "S2 task")
            if set(task) != {"id", "slice_id", "spec_revision", "digest"}:
                _fail("S2 task has unknown or missing fields")
            task_id = _text(task["id"], "S2 task id")
            if task_id in seen_tasks:
                _fail("S2 task IDs must be unique")
            seen_tasks.add(task_id)
            _text(task["slice_id"], "S2 task slice_id")
            if task["slice_id"] not in slice_ids:
                _fail("S2 task is outside approved slice scope")
            if task["spec_revision"] != tracker["spec_revision"]:
                _fail("S2 task must bind the approved tracker spec revision")
            _digest(task["digest"], "S2 task digest")
    _nonoverlapping_paths(approval["implementation_paths"], "implementation_paths")
    workspaces = _mapping(approval["workspaces"], "workspaces")
    if set(workspaces) != {"coordinator", "candidate"}:
        _fail("workspaces has unknown or missing fields")
    _nonoverlapping_paths([workspaces["coordinator"], workspaces["candidate"]], "workspaces")
    coordinator = _mapping(approval["coordinator"], "coordinator")
    if set(coordinator) != {"session_id"}:
        _fail("coordinator has unknown or missing fields")
    _text(coordinator["session_id"], "coordinator session_id")
    routes = _mapping(approval["routes"], "routes")
    if set(routes) not in (_ROUTE_NAMES, _ROUTE_NAMES | {"escalated_verify"}):
        _fail("routes has unknown or missing fields")
    for name in _ROUTE_NAMES:
        _route(routes[name], f"{name} route")
    if "escalated_verify" in routes:
        _route(routes["escalated_verify"], "escalated_verify")
        if routes["escalated_verify"] != {"model": "gpt-6.1-sol", "effort": "high", "fallback": None}:
            _fail("new escalated Verify policy requires gpt-6.1-sol/high without fallback")
    forecast = _mapping(approval["forecast"], "forecast")
    allowed_forecasts = ({"work_units", "verification_units"}, {"work_units", "verification_units", "likely_repair_units", "final_handback_units"})
    if set(forecast) not in allowed_forecasts or any(type(forecast[name]) is not int or forecast[name] < 0 for name in forecast):
        _fail("forecast must contain non-negative work, verification, repair, and handback units")
    hard_limits = approval["hard_limits"]
    if hard_limits != "none":
        hard_limits = _mapping(hard_limits, "hard_limits")
        if not set(hard_limits) or not set(hard_limits) <= {"deadline_at", "dispatch_max"}:
            _fail("hard_limits must be none or selected deadline_at/dispatch_max")
        if "deadline_at" in hard_limits:
            _utc_timestamp(hard_limits["deadline_at"], "hard_limits deadline_at")
        if "dispatch_max" in hard_limits and (type(hard_limits["dispatch_max"]) is not int or hard_limits["dispatch_max"] < 1):
            _fail("hard_limits dispatch_max must be positive")
    if approval["maximum_action"] != "open-pr":
        _fail("maximum_action must be open-pr")
    checkpoint = _mapping(approval["checkpoint"], "checkpoint")
    if set(checkpoint) != {"ref"}:
        _fail("checkpoint has unknown or missing fields")
    if checkpoint["ref"] != repository["control_ref"]:
        _fail("checkpoint must bind the declared repository exact ref")
    _control_ref(checkpoint["ref"], "checkpoint ref", approval["run_id"])
    return deepcopy(approval)


def initial_record(approval: object) -> dict[str, Any]:
    approval = validate_approval(approval)
    usage: dict[str, Any] = {"operations": [], "launches": [], "host_counters": {"tokens": None, "cost": None}}
    if "tasks" in approval:
        usage["charges"] = []
    return {
        "kind": "interim-run",
        "version": 1,
        "approval": approval,
        "approval_digest": digest(approval),
        "forecasts": {"initial": deepcopy(approval["forecast"]), "revised": []},
        "usage": usage,
        "state": {"next_action": "preflight", "candidate": None, "review": None, "handback": None},
    }


def validate_record(value: object) -> dict[str, Any]:
    record = _mapping(value, "interim record")
    if set(record) not in _record_field_sets() or record.get("kind") != "interim-run" or record.get("version") != 1:
        _fail("interim record has unknown or missing fields")
    approval = validate_approval(record["approval"])
    if record["approval_digest"] != digest(approval):
        _fail("interim approval is immutable")
    state = _mapping(record["state"], "state")
    if set(state) not in ({"next_action"}, {"next_action", "candidate", "review", "handback"}, {"next_action", "slice_id", "candidate", "review", "handback"}, {"next_action", "slice_id", "candidate", "review", "handback", "operation_id"}):
        _fail("state has unknown or missing fields")
    _text(state["next_action"], "next action")
    if "operation_id" in state and (state["next_action"] not in {"await-worker", "worker-failed", "verify-failed"}
                                    or not isinstance(state["operation_id"], str) or not state["operation_id"]):
        _fail("awaited operation identity is malformed")
    if state["next_action"] in {"await-worker", "worker-failed", "verify-failed"} and "operation_id" not in state:
        _fail("worker boundary lacks its exact operation")
    if "slice_id" in state and state["slice_id"] not in {item["id"] for item in approval["slices"]}:
        _fail("state slice is outside approved scope")
    forecasts = _mapping(record["forecasts"], "forecasts")
    if set(forecasts) != {"initial", "revised"} or forecasts["initial"] != approval["forecast"] or not isinstance(forecasts["revised"], list):
        _fail("forecasts must retain the immutable initial forecast separately")
    if "tasks" in approval:
        for revision in forecasts["revised"]:
            revision = _mapping(revision, "revised forecast")
            required_revision = {"at", "reason", "forecast", "evidence"} if "repair" in record else {"at", "reason", "forecast"}
            if set(revision) != required_revision:
                _fail("revised forecast has unknown or missing fields")
            _utc_timestamp(revision["at"], "revised forecast at")
            _text(revision["reason"], "revised forecast reason")
            forecast = _mapping(revision["forecast"], "revised forecast value")
            if set(forecast) != set(approval["forecast"]) or any(type(forecast[name]) is not int or forecast[name] < 0 for name in forecast):
                _fail("revised forecast is malformed")
            if "repair" in record:
                evidence = _mapping(revision["evidence"], "revised forecast evidence")
                if set(evidence) != {"operation_id", "reason"}:
                    _fail("revised forecast evidence is malformed")
                _text(evidence["operation_id"], "revised forecast operation_id")
                _text(evidence["reason"], "revised forecast evidence reason")
    usage = _mapping(record["usage"], "usage")
    legacy_usage = ({"operations", "host_counters"}, {"operations", "launches", "host_counters"})
    expected_usage = {"operations", "launches", "charges", "host_counters"}
    allowed_usage = (expected_usage,) if "tasks" in approval else legacy_usage
    if set(usage) not in allowed_usage or not isinstance(usage["operations"], list):
        _fail("usage has unknown or missing fields")
    if "launches" in usage and not isinstance(usage["launches"], list):
        _fail("launches are malformed")
    counters = _mapping(usage["host_counters"], "host counters")
    if set(counters) != {"tokens", "cost"} or any(value is not None for value in counters.values()):
        _fail("unavailable host counters must be null, never fabricated")
    if "tasks" in approval:
        if not isinstance(usage["launches"], list) or not isinstance(usage["charges"], list):
            _fail("S2 accounting containers are malformed")
        operation_ids: set[str] = set()
        operations_by_id: dict[str, dict[str, Any]] = {}
        for operation in usage["operations"]:
            operation = _mapping(operation, "S2 operation")
            required = {"id", "slice", "phase", "session_id", "message_id", "terminal_turn_id", "status", "issued_at", "elapsed_seconds"}
            if not required <= set(operation) or any(not isinstance(operation[name], str) or not operation[name] for name in required - {"elapsed_seconds"}):
                _fail("S2 operation is malformed")
            if operation["id"] in operation_ids or operation["phase"] not in {"coordinator", "build", "verify", "stack-verify", "stack-final-qa", "stack-final-ci", "stack-final-review", "diagnosis", "repair", "repair-verify", "wake"} or operation["status"] not in {"intent", "active", "result", "result-unusable", "reconcile-required", "reconciled", "unfinished-cancelled", "cancellation-uncertain", "accounted"}:
                _fail("S2 operation identity or status is malformed")
            if type(operation["elapsed_seconds"]) is not int or operation["elapsed_seconds"] < 0:
                _fail("S2 operation elapsed time is malformed")
            _utc_timestamp(operation["issued_at"], "S2 operation issued_at")
            for receipt_name in ("receipt", "cancellation"):
                if receipt_name not in operation:
                    continue
                receipt = _mapping(operation[receipt_name], f"S2 operation {receipt_name}")
                observation = _mapping(receipt.get("observation"), f"S2 operation {receipt_name} observation")
                expected = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
                if observation != expected:
                    _fail("S2 operation receipt is not correlated to its durable identity")
            if operation["status"] == "result-unusable":
                if not isinstance(operation.get("receipt"), dict) or not isinstance(operation.get("validation_error"), str) or not operation["validation_error"]:
                    _fail("unusable observed operation must retain its receipt and typed validation error")
            if "failure_reconciliation" in operation:
                fact = _mapping(operation["failure_reconciliation"], "failed worker reconciliation")
                expected = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
                candidate = fact.get("candidate")
                work = fact.get("candidate_work")
                pr = fact.get("pr")
                valid_pr = pr is None or (
                    isinstance(candidate, dict) and isinstance(pr, dict) and set(pr) == {"url", "repository", "number", "state", "head", "base", "base_ref"}
                    and type(pr["number"]) is int and pr["number"] > 0 and pr["state"] == "open"
                    and pr["head"] == candidate.get("head") and pr["base"] == candidate.get("base")
                    and pr["base_ref"] == approval["repository"].get("base_ref")
                    and isinstance(pr["repository"], str)
                    and pr["url"] == f"https://github.com/{pr['repository']}/pull/{pr['number']}"
                    and any(approval["repository"]["fetch_url"] == prefix + pr["repository"] + suffix
                            and approval["repository"]["push_url"] == prefix + pr["repository"] + suffix
                            for prefix in ("https://github.com/", "git@github.com:") for suffix in ("", ".git")))
                if (operation["status"] != "result-unusable" and not (operation["phase"] == "verify" and operation["status"] in {"result", "reconciled"} and operation["receipt"].get("verdict") == "fail")
                        or set(fact) != {"observation", "ceased", "candidate", "branch_head", "pr", "candidate_work", "effects_complete"}
                        or fact["observation"] != expected or fact["ceased"] is not True or fact["effects_complete"] is not True
                        or not isinstance(candidate, dict) or set(candidate) != {"head", "base"}
                        or candidate["base"] != operation["task"]["base"] or not isinstance(candidate["head"], str)
                        or len(candidate["head"]) != 40 or any(char not in "0123456789abcdef" for char in candidate["head"])
                        or fact["branch_head"] not in {None, candidate["head"]} or not valid_pr
                        or pr is not None and fact["branch_head"] != candidate["head"]
                        or not isinstance(work, dict) or set(work) != {"paths", "digest", "head"} or work["head"] != candidate["head"]
                        or not isinstance(work["paths"], list) or any(not isinstance(path, str) for path in work["paths"])
                        or len(work["paths"]) != len(set(work["paths"]))
                        or any(not any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in approval["implementation_paths"]) for path in work["paths"])
                        or not isinstance(work["digest"], str) or not work["digest"].startswith("sha256:") or len(work["digest"]) != 71
                        or any(char not in "0123456789abcdef" for char in work["digest"][7:])):
                    _fail("failed worker reconciliation lacks exact cessation and effect readback")
            if "pr_create_intent" in operation:
                marker = _mapping(operation["pr_create_intent"], "PR create intent")
                candidate = operation.get("candidate")
                if (operation["phase"] != "verify" or set(marker) != {"head", "base", "base_ref", "at"}
                        or not isinstance(candidate, dict) or marker.get("head") != candidate.get("head")
                        or marker.get("base") != candidate.get("base")
                        or marker.get("base_ref") != approval["repository"].get("base_ref")):
                    _fail("PR create intent differs from approved Verify candidate")
                _utc_timestamp(marker["at"], "PR create intent at")
            if "send_admission" in operation:
                admission = _mapping(operation["send_admission"], "worker send admission")
                if (operation["phase"] not in {"build", "verify", "diagnosis", "repair", "repair-verify"} or set(admission) != {"operation_id", "at"}
                        or admission.get("operation_id") != operation["id"]):
                    _fail("worker send admission differs from its durable operation")
                _utc_timestamp(admission["at"], "worker send admission at")
            operation_ids.add(operation["id"])
            operations_by_id[operation["id"]] = operation
        if state["next_action"] in {"await-worker", "worker-failed", "verify-failed"}:
            awaited = operations_by_id.get(state["operation_id"])
            expected_status = ({"intent", "reconcile-required"} if state["next_action"] == "await-worker" else
                               {"result-unusable"} if state["next_action"] == "worker-failed" else {"result", "reconciled"})
            if (awaited is None or awaited["status"] not in expected_status or awaited["phase"] in {"wake", "coordinator"}
                    or awaited["slice"] != state["slice_id"]):
                _fail("worker boundary is not bound to its exact operation")
        launch_ids: set[str] = set()
        for launch in usage["launches"]:
            launch = _mapping(launch, "S2 launch")
            if set(launch) != {"operation_id", "phase", "issued_at"} or launch["operation_id"] not in operation_ids or launch["operation_id"] in launch_ids or launch["phase"] != operations_by_id[launch["operation_id"]]["phase"]:
                _fail("S2 launch ledger is malformed")
            _utc_timestamp(launch["issued_at"], "S2 launch issued_at")
            launch_ids.add(launch["operation_id"])
        charge_ids: set[str] = set()
        for charge in usage["charges"]:
            charge = _mapping(charge, "S2 charge")
            if set(charge) != {"operation_id", "work_units", "status", "charged_at"} or charge["operation_id"] not in operation_ids or charge["operation_id"] in charge_ids or type(charge["work_units"]) is not int or charge["work_units"] != 1 or charge["status"] not in {"pending", "observed"}:
                _fail("S2 charge ledger is malformed")
            _utc_timestamp(charge["charged_at"], "S2 charge charged_at")
            charge_ids.add(charge["operation_id"])
        if launch_ids != operation_ids or charge_ids != operation_ids:
            _fail("S2 accounting must retain one launch and charge per operation")
        from .interim_semantics import SemanticError, validate_s2_portable
        try:
            validate_s2_portable(record)
        except SemanticError as exc:
            _fail(f"S2 portable semantics refused: {exc}")
        if "repair" in record:
            from .interim_repair import RepairPolicyError, validate_repair
            try:
                history = record.get("repair_history", [])
                if not isinstance(history, list) or len({item.get("slice_id") for item in history if isinstance(item, dict)}) != len(history) or any(not isinstance(item, dict) or item.get("status") != "completed" or item.get("slice_id") == record["repair"].get("slice_id") for item in history):
                    _fail("completed repair history is malformed")
                for item in history:
                    validate_repair({**record, "repair": item})
                validate_repair(record)
            except RepairPolicyError as exc:
                _fail(f"S3 repair policy refused: {exc}")
        if "recovery_disposition" in record:
            from .interim_disposition import validate_disposition
            try:
                validate_disposition(record)
            except (ValueError, TypeError, KeyError) as exc:
                _fail(f"recovery disposition refused: {exc}")
        if "recovery" in record:
            from .interim_recovery import RecoveryPolicyError, validate_recovery
            try:
                validate_recovery(record)
            except RecoveryPolicyError as exc:
                _fail(f"S4 recovery policy refused: {exc}")
        if "monitoring" in record:
            from .interim_monitor import MonitoringPolicyError, validate_monitoring
            try:
                validate_monitoring(record)
            except MonitoringPolicyError as exc:
                _fail(f"TASK-409 monitoring policy refused: {exc}")
    if "stack" in record:
        from .interim_stack import StackPolicyError, validate_stack
        try:
            validate_stack(record)
        except StackPolicyError as exc:
            _fail(f"S5 stack policy refused: {exc}")
    return deepcopy(record)


def preflight(record: object, requested_slices: list[str]) -> dict[str, Any]:
    """Validate approved AFK scope and return a checkpoint-only next action."""
    record = validate_record(record)
    if not isinstance(requested_slices, list) or not requested_slices:
        _fail("requested slices must be a non-empty list")
    if any(not isinstance(slice_id, str) or not slice_id for slice_id in requested_slices) or len(requested_slices) != len(set(requested_slices)):
        _fail("requested slices must be unique non-empty IDs")
    approved = {item["id"]: item for item in record["approval"]["slices"]}
    for slice_id in requested_slices:
        if slice_id not in approved:
            _fail("requested slice is outside approved scope")
        if approved[slice_id]["mode"] != "AFK":
            _fail("requested HITL slice requires explicit human approval")
        if any(dependency not in requested_slices for dependency in approved[slice_id]["dependencies"]):
            _fail("requested slice dependencies are not approved in this preflight")
    return {"action": "checkpoint", "run_id": record["approval"]["run_id"], "slices": list(requested_slices), "worker_dispatch": "unavailable"}


class InterimCheckpointStore:
    """Exact-ref remote persistence with readback after any ambiguous push."""

    def __init__(self, repository: Path, remote: str, control_ref: str,
                 monitoring_workspace_id: str | None = None,
                 dispatch_emitter: Callable[[dict[str, str]], None] | None = None):
        _text(remote, "checkpoint remote")
        self.repository, self.remote, self.control_ref = repository, remote, control_ref
        self._store = GitControlStore(repository, control_ref)
        # This is an explicit opt-in at the shipped start boundary.  Once a
        # record is enrolled, persist_lifecycle also derives its authority from
        # the durable record so coordinator/recovery/repair/stack processes do
        # not need an out-of-band registry or a remembered helper call.
        self.monitoring_workspace_id = monitoring_workspace_id
        self.dispatch_emitter = dispatch_emitter

    def monitored(self, coordinator_workspace_id: str,
                  dispatch_emitter: Callable[[dict[str, str]], None] | None = None) -> "InterimCheckpointStore":
        """Configure this exact store's approved monitored-start boundary."""
        self.monitoring_workspace_id = coordinator_workspace_id
        self.dispatch_emitter = dispatch_emitter
        return self

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(["git", *args], cwd=self.repository, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)
        except OSError as exc:
            raise InterimCheckpointError("checkpoint repository is unavailable") from exc

    def remote_commit(self) -> str | None:
        try:
            result = self._git("ls-remote", self.remote, self.control_ref)
        except subprocess.CalledProcessError as exc:
            raise InterimCheckpointError("remote checkpoint could not be read") from exc
        lines = [line.split() for line in result.stdout.decode().splitlines() if line]
        if not lines:
            return None
        if len(lines) != 1 or len(lines[0]) != 2 or lines[0][1] != self.control_ref:
            raise InterimCheckpointError("remote checkpoint ref is ambiguous")
        return lines[0][0]

    def _parents(self, commit_sha: str) -> tuple[str, ...]:
        result = self._git("rev-list", "--parents", "-n", "1", commit_sha, check=False)
        if result.returncode:
            raise InterimCheckpointError("checkpoint parent lineage could not be read")
        fields = result.stdout.decode().strip().split()
        if not fields or fields[0] != commit_sha or any(len(parent) not in {40, 64} for parent in fields[1:]):
            raise InterimCheckpointError("checkpoint parent lineage is malformed")
        return tuple(fields[1:])

    def _published(self, snapshot: GitSnapshot, reconciled: bool = False) -> InterimCheckpointSnapshot:
        return InterimCheckpointSnapshot(snapshot.value, snapshot.digest, snapshot.commit_sha, reconciled,
                                         self._parents(snapshot.commit_sha))

    def _remote_urls(self, push: bool) -> list[str]:
        args = ("remote", "get-url", "--push", "--all", self.remote) if push else ("remote", "get-url", "--all", self.remote)
        result = self._git(*args, check=False)
        if result.returncode:
            raise InterimCheckpointError("approved repository identity could not be read")
        values = [line for line in result.stdout.decode().splitlines() if line]
        if not values:
            raise InterimCheckpointError("approved repository identity is empty")
        return values

    def _assert_approved_target(self, record: dict[str, Any]) -> None:
        approval, checkpoint = record["approval"], record["approval"]["checkpoint"]
        repository = approval["repository"]
        if repository["remote"] != self.remote or checkpoint["ref"] != self.control_ref:
            raise InterimCheckpointError("checkpoint adapter target differs from immutable approval", code="target")
        fetch_urls, push_urls = self._remote_urls(False), self._remote_urls(True)
        if len(fetch_urls) != 1 or len(push_urls) != 1:
            raise InterimCheckpointError("approved repository must have exactly one effective fetch and push target", code="target")
        if repository["fetch_url"] != fetch_urls[0] or repository["push_url"] != push_urls[0]:
            raise InterimCheckpointError("approved repository identity changed; reload or hand back", code="target")

    def _push_or_reconcile(self, snapshot: GitSnapshot, expected_remote_commit: str | None) -> InterimCheckpointSnapshot:
        try:
            self._store.push(self.remote, expected_remote_commit, snapshot.commit_sha)
            return self._published(snapshot)
        except Exception as exc:
            current = self.remote_commit()
            if current == snapshot.commit_sha:
                return self._published(snapshot, reconciled=True)
            # Only a remote that moved off the expected commit lost the CAS; an
            # unchanged remote means the push itself failed.
            code = "cas-lost" if current != expected_remote_commit else "push-failed"
            raise InterimCheckpointError("remote checkpoint moved or publication is ambiguous; reload and reconcile", code=code) from exc

    def create_and_publish(self, record: object) -> InterimCheckpointSnapshot:
        record = validate_record(record)
        if self.monitoring_workspace_id is not None and "monitoring" not in record:
            # Local import preserves the portable S1 validator and avoids a
            # module cycle: monitoring itself depends on this store.
            from .interim_monitor import enroll
            record = enroll(record, self.monitoring_workspace_id)
        self._assert_approved_target(record)
        if self.remote_commit() is not None:
            raise InterimCheckpointError("remote checkpoint ref already exists")
        return self._push_or_reconcile(self._store.create(record), None)

    def _fetch_consistent(self, label: str) -> GitSnapshot:
        """Fetch this ref at one remote commit, re-reading a torn ls-remote/fetch pair."""
        for _ in range(RELOAD_ATTEMPTS):
            remote_commit = self.remote_commit()
            if remote_commit is None:
                raise InterimCheckpointError(f"{label} checkpoint ref is missing", code="missing")
            result = self._git("fetch", self.remote, f"+{self.control_ref}:{self.control_ref}", check=False)
            if result.returncode:
                raise InterimCheckpointError(f"{label} checkpoint could not be fetched", code="fetch")
            try:
                snapshot = self._store.read()
            except CanonicalError as exc:
                raise InterimCheckpointError(f"{label} checkpoint record is corrupt; cannot safely advance", code="corrupt") from exc
            if snapshot.commit_sha == remote_commit:
                return snapshot
        raise InterimCheckpointError(f"{label} checkpoint changed during reload", code="moved")

    def reload(self, approved_record: object) -> InterimCheckpointSnapshot:
        approved = validate_record(approved_record)
        self._assert_approved_target(approved)
        snapshot = self._fetch_consistent("remote")
        try:
            record = validate_record(snapshot.value)
        except InterimError as exc:
            raise InterimCheckpointError("remote checkpoint record is corrupt; cannot safely advance", code="corrupt") from exc
        self._assert_approved_target(record)
        if record["approval_digest"] != approved["approval_digest"]:
            raise InterimCheckpointError("remote checkpoint approval differs from immutable approval", code="target")
        return self._published(snapshot)

    def reload_registered(self) -> InterimCheckpointSnapshot:
        """Reload one registered ref without trusting the registry's content.

        A registry supplies only a ref-shaped locator. The fetched record still
        has to validate as a complete immutable approval and bind this exact
        remote/ref before a monitor can use it.
        """
        snapshot = self._fetch_consistent("registered")
        try:
            record = validate_record(snapshot.value)
        except InterimError as exc:
            raise InterimCheckpointError("registered checkpoint record is corrupt; cannot safely advance", code="corrupt") from exc
        self._assert_approved_target(record)
        return self._published(snapshot)

    def persist(self, expected: InterimCheckpointSnapshot, record: object) -> InterimCheckpointSnapshot:
        record = validate_record(record)
        self._assert_approved_target(record)
        if digest(expected.value) != expected.digest:
            raise InterimCheckpointError("expected checkpoint snapshot is not self-consistent")
        try:
            actual = self._store.read()
        except (CasMismatch, FileNotFoundError) as exc:
            raise InterimCheckpointError("local checkpoint could not be read") from exc
        if actual.commit_sha != expected.commit_sha or actual.digest != expected.digest:
            raise InterimCheckpointError("local checkpoint moved; reload and reconcile", code="cas-lost")
        previous = validate_record(actual.value)
        if record["approval_digest"] != previous["approval_digest"]:
            raise InterimCheckpointError("approval amendment is unavailable in S1")
        if self.remote_commit() != actual.commit_sha:
            raise InterimCheckpointError("remote checkpoint moved; reload and reconcile", code="cas-lost")
        try:
            snapshot = self._store._write_from_snapshot(actual.commit_sha, actual.digest, record, actual)
        except CasMismatch as exc:
            raise InterimCheckpointError("local checkpoint moved; reload and reconcile", code="cas-lost") from exc
        return self._push_or_reconcile(snapshot, expected.commit_sha)

    def persist_lifecycle(self, expected: InterimCheckpointSnapshot,
                          record: object) -> InterimCheckpointSnapshot:
        """Persist a production continuation boundary for a monitored run.

        The four shipped coordinator families use this one method.  It leaves
        legacy records byte-for-byte on their existing path, ignores monitor
        reservation/audit writes, retires terminal/human/limit states, and
        records the successor wake *before* its optional dispatch hint.
        """
        previous, projected = validate_record(expected.value), validate_record(record)
        monitoring = previous.get("monitoring")
        if not isinstance(monitoring, dict):
            return self.persist(expected, projected)
        # Monitoring owns its own reservation, reconciliation, and audit
        # records.  Rewrapping those writes would manufacture wake generations
        # or recursively emit events.
        from .interim_monitor import _terminal, checkpoint_transition, locator, retire
        terminal = _terminal(projected)
        emitted: dict[str, str] | None = None
        if terminal:
            projected = retire(projected, terminal)
        elif projected.get("monitoring") != monitoring or self._wake_write(previous, projected):
            return self.persist(expected, projected)
        elif monitoring.get("state") == "active" and self._continuation_is_stable(projected):
            reason = "coordinator-boundary-" + projected["state"]["next_action"]
            projected = checkpoint_transition(projected, reason, expected.commit_sha)
            pending = projected["monitoring"]["pending_wake"]
            emitted = locator({"run_id": projected["approval"]["run_id"],
                               "control_ref": projected["monitoring"]["control_ref"],
                               "generation": pending["generation"]})
        persisted = self.persist(expected, projected)
        if emitted is not None and self.dispatch_emitter is not None:
            try:
                self.dispatch_emitter(emitted)
            except (OSError, TimeoutError, ConnectionError):
                # The CAS-persisted wake remains discoverable by the backup.
                pass
        return persisted

    @staticmethod
    def _wake_write(previous: dict[str, Any], projected: dict[str, Any]) -> bool:
        """True for the monitor's own durable reservation/reconciliation IO."""
        before = {item["id"]: item for item in previous["usage"]["operations"] if item.get("phase") == "wake"}
        after = {item["id"]: item for item in projected["usage"]["operations"] if item.get("phase") == "wake"}
        return before != after

    @staticmethod
    def _continuation_is_stable(record: dict[str, Any]) -> bool:
        """Only completed coordinator work reaches a successor wake boundary."""
        if record["state"]["next_action"] == "await-worker":
            awaited = record["state"]["operation_id"]
            pending = [item for item in record["usage"]["operations"]
                       if item.get("phase") not in {"wake", "coordinator"}
                       and item.get("status") in {"intent", "reconcile-required"}]
            return len(pending) == 1 and pending[0]["id"] == awaited
        if record["state"]["next_action"] == "worker-failed":
            failed = [item for item in record["usage"]["operations"]
                      if item.get("id") == record["state"]["operation_id"]
                      and item.get("phase") not in {"wake", "coordinator"}
                      and item.get("status") == "result-unusable"]
            active = [item for item in record["usage"]["operations"]
                      if item.get("phase") not in {"wake", "coordinator"}
                      and item.get("status") in {"intent", "active", "reconcile-required", "cancellation-uncertain"}]
            return len(failed) == 1 and not active
        settled = {"result", "reconciled", "accounted", "unfinished-cancelled"}
        return not any(item.get("phase") not in {"wake", "coordinator"} and item.get("status") not in settled and not (item.get("status") == "result-unusable" and "failure_reconciliation" in item)
                       for item in record["usage"]["operations"])


def _read(path: Path) -> dict[str, Any]:
    try:
        value = load_strict(path.read_bytes())
    except (OSError, CanonicalError) as exc:
        raise InterimError(f"could not read {path}: {exc}") from exc
    return _mapping(value, str(path))


def _emit(value: dict[str, Any]) -> None:
    print(canonical_bytes(value).decode())


def main(argv: list[str] | None = None) -> int:
    """Run validate, checkpoint-only preflight, monitored start, publish, or reload."""
    class SafeParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            self.exit(2, "interim refusal: invalid arguments\n")
    parser = SafeParser(description="Validate, checkpoint, or advance an approved interim run.")
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate approval and print its initial record")
    validate.add_argument("--approval", type=Path, required=True)
    preflight_command = commands.add_parser("preflight", help="validate approved AFK slices; returns checkpoint-only")
    preflight_command.add_argument("--record", type=Path, required=True)
    preflight_command.add_argument("--slice", dest="slices", action="append", required=True)
    publish = commands.add_parser("publish", help="create and publish the approved checkpoint")
    publish.add_argument("--repository", type=Path, required=True)
    publish.add_argument("--record", type=Path, required=True)
    monitored_start = commands.add_parser("monitor-start", help="start one explicitly approved monitored coordinator run")
    monitored_start.add_argument("--repository", type=Path, required=True)
    monitored_start.add_argument("--record", type=Path, required=True)
    monitored_start.add_argument("--coordinator-workspace-id", required=True)
    reload_command = commands.add_parser("reload", help="reload the exact approved checkpoint")
    reload_command.add_argument("--repository", type=Path, required=True)
    reload_command.add_argument("--record", type=Path, required=True)
    status_command = commands.add_parser("status", help="read durable recovery and decision status without contacting the host")
    status_command.add_argument("--repository", type=Path, required=True)
    status_command.add_argument("--record", type=Path, required=True)
    advance_command = commands.add_parser("advance", help="advance one exact-ref coordinator step")
    advance_command.add_argument("--repository", type=Path, required=True)
    advance_command.add_argument("--record", type=Path, required=True)
    advance_command.add_argument("--tasks", type=Path, required=True)
    advance_command.add_argument("--agent", default="codex")
    args = parser.parse_args(argv)
    if args.command == "advance":
        # Neither raw file contents nor host exception strings reach this CLI.
        try:
            from .interim_advance import advance_once
            from .interim_conductor_host import ConductorHostAdapter
            approved = validate_record(_read(args.record))
            tasks = _read(args.tasks)
            store = InterimCheckpointStore(args.repository, approved["approval"]["repository"]["remote"],
                                           approved["approval"]["checkpoint"]["ref"])
            snapshot = store.reload(approved)
            record = snapshot.value
            monitoring = record.get("monitoring")
            if not isinstance(monitoring, dict) or monitoring.get("state") != "active":
                raise InterimError("advance requires active monitored enrollment")
            configured_routes = deepcopy(record["approval"]["routes"])
            if "escalation_policy" in record["approval"]:
                configured_routes["escalation"] = deepcopy(record["approval"]["escalation_policy"]["route"])
            host = ConductorHostAdapter(monitoring["coordinator_workspace_id"], agent=args.agent,
                                        routes=configured_routes)
            host.load_checkpoint(record)
            _emit(advance_once(store, approved, tasks, host))
            return 0
        except Exception:
            parser.exit(2, "interim advance refused; inspect the exact checkpoint and host state\n")
    try:
        if args.command == "validate":
            _emit(initial_record(_read(args.approval)))
        elif args.command == "preflight":
            _emit(preflight(_read(args.record), args.slices))
        else:
            record = _read(args.record)
            approval = validate_record(record)["approval"]
            store = InterimCheckpointStore(args.repository, approval["repository"]["remote"], approval["checkpoint"]["ref"])
            if args.command == "publish":
                snapshot = store.create_and_publish(record)
            elif args.command == "monitor-start":
                # The monitored store is the actual shipped enrollment
                # boundary.  Later coordinator/recovery/repair/stack writers
                # derive monitoring from the durable record, never this CLI.
                snapshot = store.monitored(args.coordinator_workspace_id).create_and_publish(record)
            else:
                snapshot = store.reload(record)
            if args.command == "status":
                durable = snapshot.value
                disposition = durable.get("recovery_disposition", {})
                _emit({"outcome": durable["state"]["next_action"], "commit_sha": snapshot.commit_sha,
                       "monitoring": durable.get("monitoring", {}).get("state", "unenrolled"),
                       "recovery_check": disposition.get("active"),
                       "decision_notices": disposition.get("notices", [])})
            else:
                _emit({"outcome": "checkpointed", "commit_sha": snapshot.commit_sha, "reconciled": snapshot.reconciled, "worker_dispatch": "unavailable"})
    except (InterimError, InterimCheckpointError) as exc:
        parser.exit(2, f"interim refusal: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic S5 stack policy over the durable interim checkpoint.

This is intentionally an adapter seam, not a GitHub or merge client.  It makes
the facts needed to stack reviewable slices portable: acceptance, merge and
shipment are different facts; every review names its exact head/base; and a
stack effect is first recorded as a correlated intent.  The same S4 exact-ref
store is used for persistence and recovery.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from .canonical import digest
from .interim_identity import operation_identities
from .interim import InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, _digest, _utc_timestamp, validate_record


class StackPolicyError(InterimError):
    """A stack observation cannot safely advance the approved AFK run."""


class RoutineStackConflict(Exception):
    """A bounded in-scope conflict was observed before a stack effect."""


def _fail(message: str) -> None:
    raise StackPolicyError(message)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _at(now: datetime) -> str:
    return now.isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        _fail(f"{label} must be a lowercase Git SHA")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(f"{label} must be non-empty text")
    return value


def _candidate(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"head", "base"}:
        _fail(f"{label} must contain exact head and base")
    return {"head": _sha(value["head"], label + " head"), "base": _sha(value["base"], label + " base")}


def _runtime(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"model", "effort", "runner", "permissions"} or any(not isinstance(item, str) or not item for item in value.values()):
        _fail(f"{label} must retain complete runtime identity")
    return value


def _slice_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in record["approval"]["slices"]}


def _review_binding(record: dict[str, Any], entry: dict[str, Any], review: dict[str, Any]) -> None:
    """Bind a retained review to approved route and exact evidence facts."""
    candidate = entry["candidate"]
    if candidate is None or _candidate(review["candidate"], "review candidate") != candidate:
        _fail("review binding is stale for candidate/base")
    operation = next((item for item in record["usage"]["operations"] if item.get("id") == review["verify_operation_id"]), None)
    if not isinstance(operation, dict) or operation.get("phase") not in {"verify", "stack-verify"} or operation.get("status") not in {"result", "reconciled"}:
        _fail("review lacks a durable accepted Verify operation")
    task = operation.get("task")
    receipt = operation.get("receipt")
    if not isinstance(task, dict) or task.get("slice_id") != entry["id"] or not isinstance(task.get("runtimes"), dict) or not isinstance(task["runtimes"].get("verify"), dict) or not isinstance(receipt, dict):
        _fail("review Verify ledger lacks bounded task/runtime facts")
    approved_task = next((item for item in record["approval"].get("tasks", []) if item["id"] == task.get("id") and item["slice_id"] == entry["id"]), None)
    if not isinstance(approved_task, dict) or approved_task["spec_revision"] != record["approval"]["tracker"]["spec_revision"] or approved_task["digest"] != digest(task):
        _fail("review Verify task is not an immutable approved task reference")
    # ``stack-verify`` has a deliberately separate phase name so legacy S2's
    # one-Build/one-Verify ordering stays intact.  It is nevertheless the
    # exact same bounded Verify contract: preserve the original intent fields
    # before adapting only its phase name for the shared validator.
    if operation.get("candidate") != candidate or operation.get("criteria") != task.get("criteria"):
        _fail("review Verify intent differs from its approved candidate or criteria")
    from .interim_semantics import SemanticError, restack_bound_verify_task, validate_worker_result
    try:
        effective_task = restack_bound_verify_task(record, operation, task)
        validate_worker_result(receipt, {**operation, "phase": "verify"}, "verify", record["approval"]["routes"]["verify"], effective_task, candidate)
    except SemanticError as exc:
        _fail(f"review Verify receipt fails the bounded contract: {exc}")
    runtime = _runtime(receipt.get("runtime"), "review runtime")
    route = record["approval"]["routes"]["verify"]
    if runtime["model"] != route["model"] or runtime["effort"] != route["effort"]:
        _fail("review runtime differs from the approved Verify route")
    expected = task["runtimes"]["verify"]
    if runtime["runner"] != expected.get("runner") or runtime["permissions"] != expected.get("permissions"):
        _fail("review runtime differs from its durable slice task")
    artifact = receipt.get("evidence", {}).get("artifact") if isinstance(receipt.get("evidence"), dict) else None
    if not isinstance(artifact, dict) or artifact.get("operation_id") != operation["id"] or artifact.get("head") != candidate["head"] or artifact.get("base") != candidate["base"]:
        _fail("review Verify artifact is not correlated to candidate/operation")
    if review["findings"] != receipt.get("nonblocking_findings", []):
        _fail("review findings differ from the accepted Verify receipt")
    _digest(review["verification_environment_digest"], "review verification environment digest")
    if review["verification_environment_digest"] != entry["verification_environment_digest"]:
        _fail("review environment differs from the current observed candidate")
    expected_digest = digest({"candidate": candidate, "runtime": runtime, "artifact_id": artifact.get("id"), "operation_id": operation["id"], "verification_environment_digest": review["verification_environment_digest"]})
    if review["binding_digest"] != expected_digest:
        _fail("review binding digest is not bound to its evidence")


def _review_task(record: dict[str, Any], entry: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return the immutable task, operation, and artifact behind an accepted review."""
    review = entry["review"]
    if not isinstance(review, dict):
        _fail("final evidence requires an accepted slice Verify review")
    operation = next((item for item in record["usage"]["operations"] if item.get("id") == review["verify_operation_id"]), None)
    if not isinstance(operation, dict) or not isinstance(operation.get("task"), dict) or not isinstance(operation.get("receipt"), dict):
        _fail("final evidence lacks the accepted slice Verify ledger")
    artifact = operation["receipt"].get("evidence", {}).get("artifact") if isinstance(operation["receipt"].get("evidence"), dict) else None
    if not isinstance(artifact, dict):
        _fail("final evidence lacks the accepted slice Verify artifact")
    return operation["task"], operation, artifact


def _final_operation_id(record: dict[str, Any], kind: str, candidates: list[dict[str, Any]], *, bound_inputs: bool = False) -> str:
    identity = {"run": record["approval"]["run_id"], "kind": kind, "candidates": candidates}
    if bound_inputs:
        identity["verify_inputs"] = [{"slice_id": entry["id"], "binding_digest": entry["review"]["binding_digest"]} for entry in record["stack"]["slices"]]
    return "stack-final-" + digest(identity)[7:23]


def _bound_final_id(record, kind, candidates, operation_id):
    operation = next((item for item in record["usage"]["operations"] if item["id"] == operation_id), {})
    return _final_operation_id(record, kind, candidates, bound_inputs="final_context" in operation)


def _final_operation(record: dict[str, Any], kind: str, candidates: list[dict[str, Any]], operation_id: object) -> dict[str, Any]:
    """Resolve one final receipt from the accounted checkpoint ledger only."""
    expected_id = _bound_final_id(record, kind, candidates, operation_id)
    if operation_id != expected_id:
        _fail(f"final {kind} operation identity is not derived from current candidates")
    operation = next((item for item in record["usage"]["operations"] if item.get("id") == operation_id), None)
    phase = "stack-final-review" if kind == "cross-slice-review" else "stack-" + kind
    expected_observation = {"id": expected_id, **operation_identities(record["approval"]["run_id"], expected_id, phase)}
    if not isinstance(operation, dict) or operation.get("phase") != phase or operation.get("slice") != "stack" or operation.get("status") not in {"result", "reconciled"} or {name: operation.get(name) for name in expected_observation} != expected_observation:
        _fail(f"final {kind} receipt is not an existing correlated ledger operation")
    receipt = operation.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("observation") != expected_observation or receipt.get("transport") != "accepted" or receipt.get("terminal_turn") is not True or receipt.get("task_success") is not True or receipt.get("operation_id") != expected_id:
        _fail(f"final {kind} ledger receipt is not a terminal accepted observation")
    return receipt


def _final_phase_evidence(record: dict[str, Any], entries: list[dict[str, Any]], candidates: list[dict[str, Any]], kind: str, receipt: object) -> None:
    """Validate current-head QA/CI observations against the accepted task ledger."""
    if not isinstance(receipt, dict) or set(receipt) - {"runtime", "wall_time_seconds", "elapsed_seconds", "tools", "host_counters"} != {"observation", "transport", "terminal_turn", "task_success", "operation_id", "artifacts", "checks"}:
        _fail(f"final {kind} evidence must be a correlated structured receipt")
    operation_id = _bound_final_id(record, "final-" + kind, candidates, receipt.get("operation_id"))
    if receipt["operation_id"] != operation_id:
        _fail(f"final {kind} operation identity is not derived from current candidates")
    if not isinstance(receipt["artifacts"], list) or len(receipt["artifacts"]) != len(entries):
        _fail(f"final {kind} artifacts are incomplete")
    artifacts: dict[str, dict[str, Any]] = {}
    for item in receipt["artifacts"]:
        if not isinstance(item, dict) or set(item) != {"id", "slice_id", "task_id", "task_digest", "candidate", "operation_id"}:
            _fail(f"final {kind} artifact is malformed")
        slice_id = item.get("slice_id")
        if slice_id in artifacts or not isinstance(slice_id, str) or item.get("operation_id") != operation_id:
            _fail(f"final {kind} artifact is not uniquely correlated")
        artifacts[slice_id] = item
    expected_checks: list[dict[str, Any]] = []
    for entry, candidate in zip(entries, candidates):
        task, _, _ = _review_task(record, entry)
        artifact = artifacts.get(entry["id"])
        if not isinstance(artifact, dict) or not isinstance(artifact.get("id"), str) or not artifact["id"]:
            _fail(f"final {kind} artifact is unrelated to its approved task")
        expected_artifact = {"id": artifact["id"], "slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "operation_id": operation_id}
        if artifact != expected_artifact:
            _fail(f"final {kind} artifact is unrelated to its approved task")
        for command in task["commands"][kind]:
            expected_checks.append({"slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "command": command, "result": "pass", "artifact_id": artifact["id"], "operation_id": operation_id})
    if receipt["checks"] != expected_checks:
        _fail(f"final {kind} checks are not the complete approved current-head commands")


def _final_review_evidence(record: dict[str, Any], entries: list[dict[str, Any]], candidates: list[dict[str, Any]], review: object) -> dict[str, Any]:
    """Validate a fresh independent cross-slice review bound to verified inputs."""
    required = {"observation", "transport", "terminal_turn", "task_success", "verdict", "fresh_context", "candidates", "runtime", "artifact", "operation_id", "verification_environment_digest", "binding_digest", "findings", "inputs", "checks"}
    if not isinstance(review, dict) or set(review) - {"wall_time_seconds", "elapsed_seconds", "tools", "host_counters"} != required or review.get("fresh_context") is not True or review.get("candidates") != candidates or not isinstance(review.get("findings"), list) or any(not isinstance(item, dict) for item in review["findings"]):
        _fail("final independent review is stale or malformed")
    operation_id = _bound_final_id(record, "cross-slice-review", candidates, review.get("operation_id"))
    if review["operation_id"] != operation_id:
        _fail("final review operation identity is not derived from current candidates")
    runtime = _runtime(review["runtime"], "final reviewer runtime")
    route = record["approval"]["routes"]["verify"]
    if runtime["model"] != route["model"] or runtime["effort"] != route["effort"]:
        _fail("final review runtime differs from the approved Verify route")
    expected_inputs: list[dict[str, Any]] = []
    expected_checks: list[dict[str, Any]] = []
    expected_runner_permissions: set[tuple[str, str]] = set()
    for entry, candidate in zip(entries, candidates):
        task, verify_operation, verify_artifact = _review_task(record, entry)
        expected_runner_permissions.add((task["runtimes"]["verify"]["runner"], task["runtimes"]["verify"]["permissions"]))
        expected_inputs.append({"slice_id": entry["id"], "candidate": candidate["candidate"], "verify_operation_id": verify_operation["id"], "task_id": task["id"], "task_digest": digest(task), "artifact_id": verify_artifact["id"]})
        for criterion in task["criteria"]:
            expected_checks.append({"slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "criterion_id": criterion, "command": task["commands"]["verify"][0], "result": review["verdict"], "artifact_id": review["artifact"].get("id") if isinstance(review.get("artifact"), dict) else None, "operation_id": operation_id})
    if len(expected_runner_permissions) != 1 or (runtime["runner"], runtime["permissions"]) != next(iter(expected_runner_permissions)):
        _fail("final review runtime differs from its approved slice tasks")
    if review["inputs"] != expected_inputs:
        _fail("final review inputs are not correlated to accepted Verify evidence")
    artifact = review.get("artifact")
    if not isinstance(artifact, dict) or not isinstance(artifact.get("id"), str) or not artifact["id"]:
        _fail("final review artifact is not correlated to its operation")
    if artifact != {"id": artifact["id"], "operation_id": operation_id, "candidates": candidates}:
        _fail("final review artifact is not correlated to its operation")
    if review["verdict"] not in {"pass", "blocker"} or review["checks"] != expected_checks or (review["verdict"] == "blocker" and not review["findings"]):
        _fail("final review checks do not retain a current independent verdict")
    _digest(review["verification_environment_digest"], "final review verification environment digest")
    binding = {"candidates": candidates, "runtime": runtime, "artifact_id": artifact["id"], "operation_id": operation_id, "verification_environment_digest": review["verification_environment_digest"], "inputs": expected_inputs, "checks": expected_checks}
    if review["binding_digest"] != digest(binding):
        _fail("final review binding digest is not bound to its evidence")
    return review


def _validate_final_evidence(record: dict[str, Any], entries: list[dict[str, Any]], evidence: object) -> dict[str, Any]:
    if not isinstance(evidence, dict) or set(evidence) != {"qa_operation_id", "ci_operation_id", "review_operation_id"}:
        _fail("final evidence must reference accounted QA, CI, and independent review operations")
    candidates = [{"slice_id": item["id"], "candidate": item["candidate"]} for item in entries]
    qa = _final_operation(record, "final-qa", candidates, evidence["qa_operation_id"])
    ci = _final_operation(record, "final-ci", candidates, evidence["ci_operation_id"])
    review = _final_operation(record, "cross-slice-review", candidates, evidence["review_operation_id"])
    _final_phase_evidence(record, entries, candidates, "qa", qa)
    _final_phase_evidence(record, entries, candidates, "ci", ci)
    return _final_review_evidence(record, entries, candidates, review)


def _entry(value: object, approved: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"id", "branch", "candidate", "pr", "verification_environment_digest", "restack_base", "review", "accepted", "merged", "shipment", "findings"}:
        _fail("per-slice stack record has unknown or missing fields")
    slice_id = _text(value["id"], "stack slice id")
    if slice_id not in approved:
        _fail("stack slice is outside immutable approval")
    _text(value["branch"], "stack branch")
    candidate = value["candidate"]
    if candidate is not None:
        candidate = _candidate(candidate, "stack candidate")
    if value["verification_environment_digest"] is not None:
        _digest(value["verification_environment_digest"], "observed verification environment digest")
    pr = value["pr"]
    if pr is not None:
        if not isinstance(pr, dict) or set(pr) != {"url", "head", "base", "state"}:
            _fail("PR observation is malformed")
        _text(pr["url"], "PR URL"); _sha(pr["head"], "PR head"); _sha(pr["base"], "PR base")
        if pr["state"] not in {"open", "merged", "closed"}:
            _fail("PR state is malformed")
        if candidate is None or {"head": pr["head"], "base": pr["base"]} != candidate:
            _fail("PR observation differs from exact candidate/base")
    review = value["review"]
    if review is not None:
        if not isinstance(review, dict) or set(review) != {"candidate", "verdict", "fresh_context", "verify_operation_id", "verification_environment_digest", "binding_digest", "findings"}:
            _fail("review binding is malformed")
        if candidate is None or _candidate(review["candidate"], "review candidate") != candidate:
            _fail("review binding is stale for candidate/base")
        if review["verdict"] != "pass" or review["fresh_context"] is not True:
            _fail("accepted review must be a fresh pass")
        _text(review["verify_operation_id"], "review Verify operation ID")
        _digest(review["verification_environment_digest"], "review verification environment digest")
        _digest(review["binding_digest"], "review binding digest")
        if not isinstance(review["findings"], list) or any(not isinstance(item, dict) for item in review["findings"]):
            _fail("review findings must be retained objects")
    if type(value["accepted"]) is not bool or type(value["merged"]) is not bool or value["shipment"] != "unshipped" or not isinstance(value["findings"], list):
        _fail("stack acceptance, merge, shipment, or findings state is malformed")
    if value["accepted"] != (review is not None):
        _fail("accepted dependency must equal a current accepted review")
    if value["findings"] != ([] if review is None else review["findings"]):
        _fail("retained findings differ from the review record")
    if value["merged"] and (pr is None or pr["state"] != "merged"):
        _fail("merged state needs an observed merged PR")
    if value["restack_base"] is not None:
        _sha(value["restack_base"], "observed restack base")
        if not value["merged"]:
            _fail("only an observed merged predecessor may name a restack base")
    return value


def _stack_operation_id(record: dict[str, Any], kind: str, slice_id: str, candidate: dict[str, str], target_base: str | None) -> str:
    return "stack-" + digest({"run": record["approval"]["run_id"], "kind": kind, "slice": slice_id, "candidate": candidate, "target_base": target_base})[7:23]


def _operation(record: dict[str, Any], value: object, entries: dict[str, dict[str, Any]]) -> None:
    allowed = (
        {"id", "kind", "slice_id", "candidate", "expected_pr", "status", "issued_at"},
        {"id", "kind", "slice_id", "candidate", "expected_pr", "status", "issued_at", "receipt"},
        {"id", "kind", "slice_id", "candidate", "expected_pr", "status", "issued_at", "conflict"},
        {"id", "kind", "slice_id", "candidate", "target_base", "expected_pr", "status", "issued_at"},
        {"id", "kind", "slice_id", "candidate", "target_base", "expected_pr", "status", "issued_at", "receipt"},
        {"id", "kind", "slice_id", "candidate", "target_base", "expected_pr", "status", "issued_at", "conflict"},
    )
    if not isinstance(value, dict) or set(value) not in allowed:
        _fail("stack operation has unknown or missing fields")
    _text(value["id"], "stack operation id")
    if value["kind"] not in {"open-pr", "restack"} or value["slice_id"] not in entries:
        _fail("stack operation kind or slice is unavailable")
    if value["kind"] == "restack":
        _sha(value.get("target_base"), "restack target base")
    elif "target_base" in value:
        _fail("open-PR operation must not name a restack target")
    candidate = _candidate(value["candidate"], "stack operation candidate")
    if value["id"] != _stack_operation_id(record, value["kind"], value["slice_id"], candidate, value.get("target_base")):
        _fail("stack operation ID is not derived from immutable purpose")
    # Completed effects are historical accounting.  An observed later restack
    # may legitimately replace the current candidate, while an outstanding
    # intent must remain tied to what it is still allowed to affect.
    if value["status"] != "result" and entries[value["slice_id"]]["candidate"] != candidate:
        _fail("stack operation is not bound to its current candidate")
    if value["expected_pr"] is not None:
        _text(value["expected_pr"], "stack operation expected PR")
    if value["status"] not in {"intent", "reconcile-required", "routine-repair", "result"}:
        _fail("stack operation status is malformed")
    _utc_timestamp(value["issued_at"], "stack operation issued_at")
    receipt = value.get("receipt")
    if value["status"] == "intent" and receipt is not None:
        _fail("unperformed stack intent cannot carry a receipt")
    if receipt is not None:
        if not isinstance(receipt, dict) or set(receipt) != {"operation_id", "candidate", "pr", "effect"}:
            _fail("stack operation receipt is malformed")
        receipt_candidate = _candidate(receipt["candidate"], "stack receipt candidate")
        if receipt["operation_id"] != value["id"] or (value["kind"] == "open-pr" and receipt_candidate != candidate):
            _fail("stack receipt is not correlated to its intent")
        if value["kind"] == "restack" and receipt_candidate["base"] != value["target_base"]:
            _fail("restack receipt does not prove its authorized target base")
        if receipt["effect"] != value["kind"]:
            _fail("stack receipt effect differs from its intent")
        pr = receipt["pr"]
        if not isinstance(pr, dict) or set(pr) != {"url", "head", "base", "state"} or pr["state"] not in {"open", "merged", "closed"}:
            _fail("stack receipt PR is malformed")
        if {"head": pr["head"], "base": pr["base"]} != receipt_candidate:
            _fail("stack receipt PR differs from candidate/base")
    if value["status"] == "result" and receipt is None:
        _fail("completed stack operation lacks correlated receipt")
    conflict = value.get("conflict")
    if value["status"] == "routine-repair":
        if value["kind"] != "restack" or not isinstance(conflict, dict) or set(conflict) != {"kind", "detail", "attempt"} or conflict["kind"] != "routine" or not isinstance(conflict["detail"], str) or not conflict["detail"] or type(conflict["attempt"]) is not int or not 1 <= conflict["attempt"] <= 3:
            _fail("routine stack repair must retain its bounded conflict")
    elif conflict is not None:
        _fail("only a routine stack repair may retain a conflict")


def validate_stack(record: dict[str, Any]) -> None:
    """Validate the S5 portable state without allowing a merge or shipment fact."""
    stack = record.get("stack")
    if not isinstance(stack, dict) or set(stack) != {"slices", "operations", "final"}:
        _fail("stack state has unknown or missing fields")
    approved = _slice_map(record)
    if not isinstance(stack["slices"], list) or not isinstance(stack["operations"], list):
        _fail("stack state containers are malformed")
    entries: dict[str, dict[str, Any]] = {}
    for item in stack["slices"]:
        item = _entry(item, approved)
        if item["id"] in entries:
            _fail("stack slices must be unique")
        entries[item["id"]] = item
    if set(entries) != set(approved):
        _fail("stack must retain every approved slice")
    for item in entries.values():
        if item["review"] is not None:
            _review_binding(record, item, item["review"])
    for slice_id, item in entries.items():
        dependencies = approved[slice_id]["dependencies"]
        if item["accepted"] and dependencies:
            predecessors = [entries[name] for name in dependencies]
            predecessor = predecessors[-1]
            target = predecessor["restack_base"] if predecessor["merged"] else predecessor["candidate"]["head"] if predecessor["candidate"] else None
            if not all(entry["accepted"] for entry in predecessors) or item["candidate"]["base"] != target:
                _fail("accepted stack review requires current dependency/restack bases")
    ids: set[str] = set()
    for operation in stack["operations"]:
        _operation(record, operation, entries)
        if operation["id"] in ids:
            _fail("stack operation identities must be unique")
        ids.add(operation["id"])
    from .interim_stack_dispatch import validate_dispatch
    validate_dispatch(record)
    final = stack["final"]
    if final is not None:
        if not isinstance(final, dict) or set(final) != {"outcome", "evidence", "retained_findings"} or final["outcome"] not in {"review-ready", "s3-repair-policy"} or not isinstance(final["retained_findings"], list):
            _fail("final stack handback is malformed")
        final_review = _validate_final_evidence(record, list(entries.values()), final["evidence"])
        retained = [finding for entry in entries.values() for finding in entry["findings"]] + deepcopy(final_review["findings"])
        if final["retained_findings"] != retained:
            _fail("final retained findings differ from correlated review evidence")
        if (final["outcome"] == "review-ready") != (final_review["verdict"] == "pass"):
            _fail("final outcome differs from its correlated review verdict")
        if final["outcome"] == "review-ready" and record["state"].get("next_action") != "review-ready":
            _fail("review-ready evidence must have the review-ready state")
        if final["outcome"] == "s3-repair-policy" and record["state"].get("next_action") != "handback":
            _fail("final blocker must be an S3 repair handback")


def _invalidate_dependents(record: dict[str, Any]) -> bool:
    entries = {item["id"]: item for item in record["stack"]["slices"]}
    invalidated = False
    # Approval permits any acyclic slice order. Each changing pass revokes at
    # least one retained review, so at most one pass per slice is sufficient.
    for _ in range(len(entries)):
        changed = False
        for approved in record["approval"]["slices"]:
            child = entries[approved["id"]]
            if child["candidate"] is None or not approved["dependencies"]:
                continue
            predecessors = [entries[name] for name in approved["dependencies"]]
            predecessor = predecessors[-1]
            target = predecessor["restack_base"] if predecessor["merged"] else predecessor["candidate"]["head"] if predecessor["candidate"] else None
            stale = not all(item["accepted"] for item in predecessors) or child["candidate"]["base"] != target
            if stale and (child["accepted"] or child["review"] is not None or child["findings"]):
                child["review"], child["accepted"], child["findings"] = None, False, []
                changed = invalidated = True
        if not changed:
            break
    return invalidated


class StackAdapter(Protocol):
    """Narrow fixture boundary; intentionally no merge method exists."""
    def apply(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def reconcile(self, operation: dict[str, Any]) -> dict[str, Any]: ...
    def observe(self, slice_id: str, branch: str) -> dict[str, Any]: ...


class InterimStackCoordinator:
    def __init__(self, store: InterimCheckpointStore, clock: Callable[[], datetime] = _now):
        self.store, self.clock = store, clock

    def _persist(self, snapshot: InterimCheckpointSnapshot, record: dict[str, Any]) -> InterimCheckpointSnapshot:
        return self.store.persist_lifecycle(snapshot, record)

    def initialise(self, snapshot: InterimCheckpointSnapshot, branches: dict[str, str]) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value)
        if "stack" in record:
            return snapshot
        approved = _slice_map(record)
        if set(branches) != set(approved) or any(not isinstance(value, str) or not value for value in branches.values()):
            _fail("every approved slice needs one explicit candidate branch")
        record["stack"] = {"slices": [{"id": slice_id, "branch": branches[slice_id], "candidate": None, "pr": None, "verification_environment_digest": None, "restack_base": None, "review": None, "accepted": False, "merged": False, "shipment": "unshipped", "findings": []} for slice_id in approved], "operations": [], "final": None}
        return self._persist(snapshot, record)

    def frontier(self, snapshot: InterimCheckpointSnapshot) -> dict[str, Any]:
        record = validate_record(snapshot.value); stack = record.get("stack")
        if not isinstance(stack, dict):
            _fail("stack must be initialised before selecting a frontier")
        entries = {item["id"]: item for item in stack["slices"]}
        for approved in record["approval"]["slices"]:
            entry = entries[approved["id"]]
            if entry["accepted"]:
                continue
            if approved["mode"] != "AFK":
                return {"action": "handback", "reason": "approved HITL slice blocks the dependency frontier", "slice_id": approved["id"]}
            dependencies = [entries[item] for item in approved["dependencies"]]
            if not all(item["accepted"] for item in dependencies):
                return {"action": "wait", "reason": "accepted dependency review is required", "slice_id": approved["id"]}
            if not dependencies:
                return {"action": "dispatch", "slice_id": approved["id"], "base": None}
            predecessor = dependencies[-1]
            if predecessor["merged"]:
                if predecessor["restack_base"] is None:
                    return {"action": "handback", "reason": "merged dependency lacks a current observed post-merge base", "slice_id": approved["id"]}
                # An existing child can still be observed on the old parent
                # head after that parent merges.  It is a restack candidate,
                # not authority to dispatch another worker or accept review.
                if entry["candidate"] is not None and entry["candidate"]["base"] != predecessor["restack_base"]:
                    return {"action": "restack", "slice_id": approved["id"], "base": predecessor["restack_base"]}
                return {"action": "dispatch", "slice_id": approved["id"], "base": predecessor["restack_base"]}
            action = "restack" if entry["candidate"] is not None and entry["candidate"]["base"] != predecessor["candidate"]["head"] else "dispatch"
            return {"action": action, "slice_id": approved["id"], "base": predecessor["candidate"]["head"]}
        return {"action": "final-review"}

    def observe_slice(self, snapshot: InterimCheckpointSnapshot, slice_id: str, observation: dict[str, Any]) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); entries = {item["id"]: item for item in record["stack"]["slices"]}
        if slice_id not in entries or not isinstance(observation, dict) or set(observation) not in ({"candidate", "pr", "verification_environment_digest"}, {"candidate", "pr", "verification_environment_digest", "restack_base"}):
            _fail("slice observation is malformed or outside approved scope")
        candidate = _candidate(observation["candidate"], "observed candidate")
        environment = _digest(observation["verification_environment_digest"], "observed verification environment digest")
        pr = observation["pr"]
        if not isinstance(pr, dict) or set(pr) != {"url", "head", "base", "state"}:
            _fail("observed PR is malformed")
        if {"head": pr["head"], "base": pr["base"]} != candidate:
            _fail("observed PR is not bound to candidate/base")
        restack_base = observation.get("restack_base")
        if restack_base is not None:
            _sha(restack_base, "observed restack base")
            if pr["state"] != "merged":
                _fail("restack base requires an observed merged predecessor")
        entry = entries[slice_id]
        dependencies = _slice_map(record)[slice_id]["dependencies"]
        stale_merged_dependency = False
        # An ordinary child may have been built on its separately approved
        # original base. Its exact accepted receipt authorizes observation,
        # while the existing restack contract remains the only base transition.
        from .interim_semantics import SemanticError, accepted_slice_candidate
        try:
            ordinary_candidate = accepted_slice_candidate(record, slice_id)
        except SemanticError:
            ordinary_candidate = None
        if dependencies:
            predecessor = entries[dependencies[-1]]
            if not predecessor["accepted"]:
                _fail("successor candidate requires an accepted dependency")
            if predecessor["merged"]:
                if predecessor["restack_base"] is None:
                    _fail("merged successor requires a current observed post-merge base")
                if candidate["base"] == predecessor["restack_base"]:
                    pass
                elif ordinary_candidate == candidate or (entry["candidate"] == candidate and candidate["base"] == predecessor["candidate"]["head"]):
                    # Preserve an already observed stale child so the durable
                    # coordinator can restack it.  Do not mistake it for a
                    # new post-merge dispatch or retain its old review.
                    stale_merged_dependency = True
                else:
                    _fail("merged successor must branch from the observed post-merge base")
            elif candidate["base"] != predecessor["candidate"]["head"]:
                if ordinary_candidate != candidate:
                    _fail("unmerged successor must branch from accepted predecessor candidate")
                stale_merged_dependency = True
        changed = entry["candidate"] != candidate or entry["verification_environment_digest"] != environment
        entry["candidate"], entry["pr"], entry["verification_environment_digest"], entry["merged"], entry["restack_base"] = candidate, deepcopy(pr), environment, pr["state"] == "merged", restack_base
        if changed or stale_merged_dependency:
            record["stack"]["final"] = None
            if record["state"]["next_action"] == "review-ready":
                record["state"] = {"next_action": "stack-verify", "candidate": deepcopy(candidate), "review": None, "handback": None}
            entry["review"], entry["accepted"], entry["findings"] = None, False, []
        # A newly observed predecessor merge/head invalidates its descendants
        # immediately; a later child poll is not required to revoke stale review.
        invalidated = changed or stale_merged_dependency
        invalidated = _invalidate_dependents(record) or invalidated
        if invalidated:
            record["stack"]["final"] = None
            if record["state"]["next_action"] == "review-ready":
                record["state"] = {"next_action": "stack-verify", "candidate": None, "review": None, "handback": None}
        return self._persist(snapshot, record)

    def accept_review(self, snapshot: InterimCheckpointSnapshot, slice_id: str, review: dict[str, Any]) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); entry = next((item for item in record["stack"]["slices"] if item["id"] == slice_id), None)
        if entry is None or entry["candidate"] is None or not isinstance(review, dict) or set(review) != {"candidate", "verdict", "fresh_context", "verify_operation_id", "verification_environment_digest", "binding_digest", "findings"}:
            _fail("fresh review lacks an observed candidate")
        if _candidate(review["candidate"], "review candidate") != entry["candidate"] or review["verdict"] != "pass" or review["fresh_context"] is not True or not isinstance(review["findings"], list):
            _fail("review is stale, non-accepting, or not fresh")
        _review_binding(record, entry, review)
        entry["review"], entry["accepted"], entry["findings"] = deepcopy(review), True, deepcopy(review["findings"])
        return self._persist(snapshot, record)

    def stack_action(self, snapshot: InterimCheckpointSnapshot, kind: str, slice_id: str, adapter: StackAdapter) -> InterimCheckpointSnapshot:
        if kind not in {"open-pr", "restack"}:
            _fail("stack adapter has no merge operation")
        record = validate_record(snapshot.value); entry = next((item for item in record["stack"]["slices"] if item["id"] == slice_id), None)
        if entry is None or entry["candidate"] is None:
            _fail("stack action needs an observed candidate")
        if entry["merged"]:
            _fail("stack adapter refuses writes to an observed merged branch")
        target_base = self._target_base(record, slice_id, entry) if kind == "restack" else None
        operation = {"id": _stack_operation_id(record, kind, slice_id, entry["candidate"], target_base), "kind": kind, "slice_id": slice_id, "candidate": deepcopy(entry["candidate"]), "expected_pr": None if entry["pr"] is None else entry["pr"]["url"], "status": "intent", "issued_at": _at(self.clock())}
        if target_base is not None:
            operation["target_base"] = target_base
        existing = next((item for item in record["stack"]["operations"] if item["id"] == operation["id"]), None)
        if existing is not None:
            if existing["status"] == "result":
                return snapshot
            # A durable intent may already have reached the provider.  Its
            # exact effect is now a reconciliation question, never grounds to
            # resend an open/update operation with the same logical identity.
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "stack operation " + existing["id"] + " requires reconciliation", "finding": None}}
            return self._persist(snapshot, record)
        else:
            record["stack"]["operations"].append(operation)
            snapshot = self._persist(snapshot, record)
        try:
            receipt = adapter.apply(deepcopy(operation))
        except RoutineStackConflict:
            if kind != "restack":
                _fail("only restack can enter bounded routine repair")
            record = validate_record(snapshot.value); current = next(item for item in record["stack"]["operations"] if item["id"] == operation["id"])
            current["status"] = "routine-repair"; current["conflict"] = {"kind": "routine", "detail": "routine in-scope restack conflict", "attempt": 1}
            record["state"] = {"next_action": "stack-repair", "candidate": None, "review": None, "handback": {"reason": "routine restack conflict may use bounded in-scope repair", "finding": None}}
            return self._persist(snapshot, record)
        except (OSError, TimeoutError, ConnectionError):
            record = validate_record(snapshot.value); current = next(item for item in record["stack"]["operations"] if item["id"] == operation["id"])
            current["status"] = "reconcile-required"
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "stack operation " + operation["id"] + " effect is ambiguous; reconcile exact PR observation", "finding": None}}
            return self._persist(snapshot, record)
        return self._settle(snapshot, operation["id"], receipt)

    @staticmethod
    def _target_base(record: dict[str, Any], slice_id: str, entry: dict[str, Any]) -> str:
        """Bind restack to the last accepted predecessor's observed base."""
        dependencies = _slice_map(record)[slice_id]["dependencies"]
        if not dependencies:
            return entry["candidate"]["base"]
        entries = {item["id"]: item for item in record["stack"]["slices"]}
        predecessor = entries[dependencies[-1]]
        if not predecessor["accepted"] or predecessor["pr"] is None:
            _fail("restack target requires an accepted predecessor PR observation")
        if predecessor["merged"]:
            if predecessor["restack_base"] is None:
                _fail("merged predecessor requires a current observed restack base")
            return predecessor["restack_base"]
        return predecessor["candidate"]["head"]

    def repair_restack(self, snapshot: InterimCheckpointSnapshot, slice_id: str, adapter: StackAdapter) -> InterimCheckpointSnapshot:
        """Retry one pre-effect routine conflict, bounded to three attempts."""
        record = validate_record(snapshot.value)
        operation = next((item for item in record["stack"]["operations"] if item["slice_id"] == slice_id and item["kind"] == "restack" and item["status"] == "routine-repair"), None)
        if operation is None:
            _fail("no bounded routine restack repair is available")
        if operation["conflict"]["attempt"] >= 3:
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "routine restack conflict exceeded bounded repair; human reconciliation required", "finding": None}}
            return self._persist(snapshot, record)
        attempt = operation["conflict"]["attempt"] + 1
        operation["conflict"]["attempt"] = attempt
        # This records the exact retry intent before the adapter can alter a
        # candidate branch. The pre-effect conflict remains durable only until
        # that retry begins.
        del operation["conflict"]; operation["status"] = "intent"
        snapshot = self._persist(snapshot, record)
        try:
            receipt = adapter.apply(deepcopy(operation))
        except RoutineStackConflict:
            record = validate_record(snapshot.value); current = next(item for item in record["stack"]["operations"] if item["id"] == operation["id"])
            current["status"] = "routine-repair"; current["conflict"] = {"kind": "routine", "detail": "routine in-scope restack conflict", "attempt": attempt}
            record["state"] = {"next_action": "stack-repair", "candidate": None, "review": None, "handback": {"reason": "routine restack conflict remains within bounded repair", "finding": None}}
            return self._persist(snapshot, record)
        except (OSError, TimeoutError, ConnectionError):
            record = validate_record(snapshot.value); current = next(item for item in record["stack"]["operations"] if item["id"] == operation["id"])
            current["status"] = "reconcile-required"
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "restack repair effect is ambiguous; reconcile exact PR observation", "finding": None}}
            return self._persist(snapshot, record)
        return self._settle(snapshot, operation["id"], receipt)

    def _settle(self, snapshot: InterimCheckpointSnapshot, operation_id: str, receipt: object) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); operation = next((item for item in record["stack"]["operations"] if item["id"] == operation_id), None)
        if operation is None or not isinstance(receipt, dict):
            _fail("stack operation receipt is absent")
        operation["receipt"], operation["status"] = deepcopy(receipt), "result"
        try:
            validate_record(record)
        except InterimError:
            # A receipt that cannot be tied to its intent remains an explicit
            # reconciliation problem rather than becoming a new side effect.
            record = validate_record(snapshot.value); current = next(item for item in record["stack"]["operations"] if item["id"] == operation_id)
            current["status"] = "reconcile-required"
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "stack operation " + operation_id + " has an ambiguous effect; reconcile exact PR observation", "finding": None}}
            return self._persist(snapshot, record)
        entry = next(item for item in record["stack"]["slices"] if item["id"] == operation["slice_id"])
        resulting = _candidate(receipt["candidate"], "settled stack receipt candidate")
        changed = entry["candidate"] != resulting
        entry["candidate"], entry["pr"], entry["merged"] = resulting, deepcopy(receipt["pr"]), receipt["pr"]["state"] == "merged"
        if changed:
            # A restack receipt is itself the observed post-effect candidate;
            # no unrelated later PR poll is needed to invalidate old review.
            entry["review"], entry["accepted"], entry["findings"] = None, False, []
            _invalidate_dependents(record)
            record["stack"]["final"] = None
            if record["state"]["next_action"] == "review-ready":
                record["state"] = {"next_action": "stack-verify", "candidate": deepcopy(resulting), "review": None, "handback": None}
        return self._persist(snapshot, record)

    def reconcile(self, snapshot: InterimCheckpointSnapshot, adapter: StackAdapter) -> InterimCheckpointSnapshot:
        """Reload through S4's exact-ref path, then observe only durable intents."""
        snapshot = self.store.reload(snapshot.value); record = validate_record(snapshot.value)
        for operation in list(record["stack"]["operations"]):
            if operation["status"] not in {"intent", "reconcile-required"}:
                continue
            try:
                receipt = adapter.reconcile(deepcopy(operation))
            except (OSError, TimeoutError, ConnectionError):
                continue
            snapshot = self._settle(snapshot, operation["id"], receipt)
            record = validate_record(snapshot.value)
        for entry in list(record["stack"]["slices"]):
            try:
                observation = adapter.observe(entry["id"], entry["branch"])
            except (OSError, TimeoutError, ConnectionError):
                continue
            snapshot = self.observe_slice(snapshot, entry["id"], observation)
            record = validate_record(snapshot.value)
        return snapshot

    def verify_slice(self, snapshot, slice_id, task, adapter):
        """Reserve or poll one approved Verify, then project current review."""
        from .interim_stack_dispatch import verify_slice
        return verify_slice(self, snapshot, slice_id, task, adapter)

    def final_review(self, snapshot, adapter):
        """Resume accounted final QA, CI and cross-slice Verify to handback."""
        from .interim_stack_dispatch import final_review
        return final_review(self, snapshot, adapter)

    def finalise(self, snapshot: InterimCheckpointSnapshot, evidence: dict[str, Any]) -> InterimCheckpointSnapshot:
        record = validate_record(snapshot.value); entries = record["stack"]["slices"]
        if not all(item["accepted"] for item in entries):
            _fail("final review requires accepted current evidence for every slice")
        if any(item["pr"] is None or item["pr"]["state"] not in {"open", "merged"} for item in entries):
            _fail("final review requires current PR links for every slice")
        review = _validate_final_evidence(record, entries, evidence)
        retained = [finding for entry in entries for finding in entry["findings"]] + deepcopy(review["findings"])
        if review["verdict"] == "blocker":
            record["stack"]["final"] = {"outcome": "s3-repair-policy", "evidence": deepcopy(evidence), "retained_findings": retained}
            record["state"] = {"next_action": "handback", "candidate": None, "review": None, "handback": {"reason": "final review blocker requires S3 repair policy", "finding": review["findings"][0] if review["findings"] else None}}
        elif review["verdict"] == "pass":
            record["stack"]["final"] = {"outcome": "review-ready", "evidence": deepcopy(evidence), "retained_findings": retained}
            record["state"] = {"next_action": "review-ready", "candidate": None, "review": None, "handback": {"outcome": "review-ready", "shipment": "unshipped", "merge": "unavailable"}}
        else:
            _fail("final review must pass or name a blocker")
        return self._persist(snapshot, record)

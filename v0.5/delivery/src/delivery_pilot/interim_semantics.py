"""Pure S2 portable-record semantics shared by checkpoint load and transitions."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import digest
from .interim_identity import operation_identities


class SemanticError(ValueError):
    pass


def _fail(message: str) -> None:
    raise SemanticError(message)


def _sha(value: object) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        _fail("candidate revision is malformed")
    return value


def _bounded_task_shape(task: object) -> dict[str, Any]:
    """Validate the immutable full S2 task contract before using it anywhere.

    Stack Verify is not allowed to introduce a smaller look-alike task.  The
    same bounded task that authorizes Build/Verify/QA/CI is what its approval
    reference digests.
    """
    if not isinstance(task, dict) or set(task) != {"id", "slice_id", "attempt", "candidate_ref", "base", "criteria", "runtimes", "commands", "limits"}:
        _fail("bounded task has unknown or missing fields")
    if not all(isinstance(task[key], str) and task[key] for key in ("id", "slice_id", "candidate_ref")) or type(task["attempt"]) is not int or task["attempt"] < 1:
        _fail("bounded task identity is malformed")
    _sha(task["base"])
    criteria = task["criteria"]
    if not isinstance(criteria, list) or not criteria or len(criteria) != len(set(criteria)) or any(not isinstance(item, str) or not item for item in criteria):
        _fail("bounded task criteria are malformed")
    runtimes = task["runtimes"]
    if not isinstance(runtimes, dict) or set(runtimes) != {"build", "verify"}:
        _fail("bounded task runtime expectations are missing")
    for phase in ("build", "verify"):
        runtime = runtimes[phase]
        if not isinstance(runtime, dict) or set(runtime) != {"runner", "permissions"} or any(not isinstance(value, str) or not value for value in runtime.values()):
            _fail("bounded task runtime expectations are malformed")
    commands = task["commands"]
    if not isinstance(commands, dict) or set(commands) != {"build", "verify", "qa", "ci"}:
        _fail("bounded task command identities are missing")
    for command_set in commands.values():
        if not isinstance(command_set, list) or not command_set or len(command_set) != len(set(command_set)) or any(not isinstance(command, str) or not command for command in command_set):
            _fail("bounded task commands are malformed")
    limits = task["limits"]
    if not isinstance(limits, dict) or set(limits) != {"max_artifacts", "max_tools", "wall_time_seconds"} or any(type(value) is not int or value < 1 for value in limits.values()):
        _fail("bounded task limits are malformed")
    return task


def _task(record: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    task = operation.get("task")
    task = _bounded_task_shape(task)
    approved = record["approval"].get("tasks", [])
    task_digest = digest(task)
    if not any(item["id"] == task["id"] and item["slice_id"] == task["slice_id"] and item["spec_revision"] == record["approval"]["tracker"]["spec_revision"] and item["digest"] == task_digest for item in approved):
        _fail("operation task is not bound by immutable approval")
    return task


def _expected_id(record: dict[str, Any], task: dict[str, Any], phase: str, candidate: str | dict[str, str] | None = None) -> str:
    if phase == "coordinator":
        body = {"run": record["approval"]["run_id"], "task": task["id"], "attempt": task["attempt"], "phase": phase}
    else:
        body = {"run": record["approval"]["run_id"], "slice": task["slice_id"], "task": task["id"], "attempt": task["attempt"], "candidate": candidate or task["candidate_ref"], "phase": phase}
    return "op-" + digest(body)[7:23]


def _identity(record: dict[str, Any], operation: dict[str, Any]) -> dict[str, Any]:
    phase = operation["phase"]
    if "route" in operation:
        route_phase = "verify" if phase == "stack-verify" else phase
        if operation["route"] != {key: record["approval"]["routes"][route_phase][key] for key in ("model", "effort")}:
            _fail("worker intent route differs from immutable approval")
    task = _task(record, operation)
    if operation["slice"] != task["slice_id"]:
        _fail("operation slice differs from its approved task")
    candidate: str | dict[str, str] | None = None
    if phase in {"verify", "stack-verify"}:
        if operation.get("criteria") != task["criteria"]:
            _fail("Verify intent criteria differ from its approved task")
        receipt = operation.get("receipt")
        # A queued/active host receipt is deliberately incomplete.  Its
        # immutable intent candidate remains the authority until a terminal
        # structured worker-result supplies the same candidate.
        candidate_value = operation.get("candidate")
        if not isinstance(candidate_value, dict):
            _fail("Verify operation has no candidate receipt")
        candidate_record = {"head": _sha(candidate_value.get("head")), "base": _sha(candidate_value.get("base"))}
        if operation["status"] != "result-unusable" and isinstance(receipt, dict) and "candidate" in receipt and operation.get("candidate") != receipt.get("candidate"):
            _fail("Verify intent candidate differs from its receipt")
        # Generic S2 Verify retains its established head-bound identity.  A
        # stack Verify instead includes the exact current candidate/base: a
        # restack can leave the head unchanged while changing its authority.
        candidate = candidate_record if phase == "stack-verify" else candidate_record["head"]
    if phase == "stack-verify" and "verification_environment_digest" in operation:
        candidate = {**candidate, "verification_environment_digest": operation["verification_environment_digest"]}
    expected = _expected_id(record, task, phase, candidate)
    if operation["id"] != expected:
        _fail("operation ID is not derived from immutable purpose")
    identities = operation_identities(record["approval"]["run_id"], expected, phase, record["approval"]["coordinator"]["session_id"])
    if {name: operation[name] for name in identities} != identities:
        _fail("operation session/message/turn identity differs from immutable purpose")
    return task


def restack_bound_verify_task(record: dict[str, Any], operation: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    """Derive a Verify task for one observed, completed restack only.

    The approved task remains immutable and digest-bound.  When an externally
    observed predecessor merge causes a restack to change the candidate base,
    this derives just that base from the exact completed restack receipt.  It
    never accepts a caller-selected base or an unrelated stack operation.
    """
    candidate = operation.get("candidate")
    if not isinstance(candidate, dict) or set(candidate) != {"head", "base"}:
        _fail("stack Verify candidate is malformed")
    _sha(candidate["head"]); _sha(candidate["base"])
    restack_id = operation.get("restack_operation_id")
    if candidate["base"] == task["base"]:
        if restack_id is not None:
            _fail("unchanged-base stack Verify cannot name a restack")
        return task
    if not isinstance(restack_id, str) or not restack_id:
        _fail("changed-base stack Verify requires a correlated completed restack")
    stack = record.get("stack")
    if not isinstance(stack, dict) or not isinstance(stack.get("slices"), list) or not isinstance(stack.get("operations"), list):
        _fail("changed-base stack Verify lacks durable stack state")
    entry = next((item for item in stack["slices"] if isinstance(item, dict) and item.get("id") == task["slice_id"]), None)
    if not isinstance(entry, dict):
        _fail("changed-base stack Verify candidate is not the current observed candidate")
    restack = next((item for item in stack["operations"] if isinstance(item, dict) and item.get("id") == restack_id), None)
    if not isinstance(restack, dict) or restack.get("kind") != "restack" or restack.get("slice_id") != task["slice_id"] or restack.get("status") != "result" or restack.get("target_base") != candidate["base"]:
        _fail("changed-base stack Verify restack binding is unavailable or stale")
    receipt = restack.get("receipt")
    if not isinstance(receipt, dict) or receipt.get("operation_id") != restack_id or receipt.get("candidate") != candidate:
        _fail("changed-base stack Verify restack receipt is not correlated to candidate/base")
    derived = deepcopy(task)
    derived["base"] = candidate["base"]
    return derived


def _observation(operation: dict[str, Any], value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("observation") != {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}:
        _fail("operation observation is not correlated to durable identity")
    return value


def validate_worker_result(result: object, intent: dict[str, Any], phase: str, route: dict[str, Any], task: dict[str, Any], candidate: dict[str, str] | None = None) -> dict[str, Any]:
    """Accept one bounded worker receipt without mutating evidence or doing I/O."""
    phase = phase.lower()
    if phase not in {"build", "verify"}:
        _fail("worker phase must be Build or Verify")
    if intent.get("phase") != phase:
        _fail("worker result phase differs from its durable intent")
    if phase == "verify" and (candidate is None or intent.get("candidate") != candidate or intent.get("criteria") != task["criteria"]):
        _fail("Verify intent differs from the accepted Build candidate or approved criteria")
    if not isinstance(result, dict):
        _fail(f"{phase} result is missing")
    # Transport acceptance, terminal turn, and actual task success remain separate.
    if result.get("transport") != "accepted" or result.get("terminal_turn") is not True or result.get("task_success") is not True:
        _fail(f"{phase} transport, idle, or terminal state is not success")
    _observation(intent, result)
    actual = result.get("candidate")
    if not isinstance(actual, dict) or set(actual) != {"head", "base"} or any(not isinstance(actual[key], str) or len(actual[key]) != 40 or any(char not in "0123456789abcdef" for char in actual[key]) for key in actual):
        _fail(f"{phase} exact candidate and base are required")
    if actual["base"] != task["base"]:
        _fail(f"{phase} candidate base differs from bounded task")
    if candidate is not None and actual != candidate:
        _fail("fresh Verify candidate/base differs from Build")
    criteria = result.get("criteria")
    if not isinstance(criteria, dict) or set(criteria) != set(task["criteria"]) or any(value != "pass" for value in criteria.values()):
        _fail(f"{phase} criteria are missing, failed, or uncertain")
    checks = result.get("executed_checks")
    if not isinstance(checks, list) or any(not isinstance(item, str) or not item for item in checks) or len(checks) != len(set(checks)) or set(checks) != set(task["criteria"]):
        _fail(f"{phase} executed checks must name the approved criteria")
    runtime = result.get("runtime")
    if not isinstance(runtime, dict) or set(runtime) != {"model", "effort", "runner", "permissions"} or any(not isinstance(value, str) or not value for value in runtime.values()):
        _fail(f"{phase} runtime identity is incomplete or malformed")
    if runtime["model"] != route["model"] or runtime["effort"] != route["effort"] or runtime["runner"] != task["runtimes"][phase.lower()]["runner"] or runtime["permissions"] != task["runtimes"][phase.lower()]["permissions"]:
        _fail(f"{phase} runtime differs from the immutable approved route")
    for name, maximum in (("artifacts", task["limits"]["max_artifacts"]), ("tools", task["limits"]["max_tools"])):
        if not isinstance(result.get(name), list) or not result[name] or len(result[name]) > maximum or any(not isinstance(item, str) or not item for item in result[name]) or len(result[name]) != len(set(result[name])):
            _fail(f"{phase} bounded {name} evidence is missing")
    if set(result["tools"]) != set(task["commands"][phase.lower()]):
        _fail(f"{phase} executed tools differ from the approved bounded task")
    if type(result.get("wall_time_seconds")) is not int or result["wall_time_seconds"] < 0 or result["wall_time_seconds"] > task["limits"]["wall_time_seconds"]:
        _fail(f"{phase} bounded wall-time evidence is missing")
    if result.get("host_counters") != {"tokens": None, "cost": None}:
        _fail(f"{phase} unavailable host counters must be explicit nulls")
    evidence = result.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"artifact", "commands", "checks"}:
        _fail(f"{phase} structured evidence is missing")
    artifact = evidence["artifact"]
    if not isinstance(artifact, dict) or artifact != {"id": result["artifacts"][0], "task_id": task["id"], "operation_id": intent["id"], "head": actual["head"], "base": actual["base"]}:
        _fail(f"{phase} artifact evidence is unrelated or stale")
    commands = evidence["commands"]
    if not isinstance(commands, list) or not commands or len(commands) > task["limits"]["max_tools"]:
        _fail(f"{phase} command evidence is missing")
    command_names: set[str] = set()
    for command in commands:
        if not isinstance(command, dict) or set(command) != {"command", "result", "artifact_id", "operation_id"} or not isinstance(command["command"], str) or not command["command"] or command["result"] != "pass" or command["artifact_id"] != artifact["id"] or command["operation_id"] != intent["id"] or command["command"] not in result["tools"] or command["command"] in command_names:
            _fail(f"{phase} command evidence is unlocatable")
        command_names.add(command["command"])
    check_evidence = evidence["checks"]
    if not isinstance(check_evidence, list) or len(check_evidence) != len(task["criteria"]):
        _fail(f"{phase} check evidence is missing")
    seen_criteria: set[str] = set()
    for check in check_evidence:
        if not isinstance(check, dict) or set(check) != {"criterion_id", "command", "result", "artifact_id", "operation_id"} or not isinstance(check["criterion_id"], str) or not isinstance(check["command"], str) or check["criterion_id"] not in task["criteria"] or check["criterion_id"] in seen_criteria or check["command"] not in command_names or check["result"] != "pass" or check["artifact_id"] != artifact["id"] or check["operation_id"] != intent["id"]:
            _fail(f"{phase} check evidence is unlocatable or unrelated")
        seen_criteria.add(check["criterion_id"])
    if command_names != set(task["commands"][phase.lower()]):
        _fail(f"{phase} command evidence differs from the approved bounded task")
    if phase == "verify" and (result.get("fresh_context") is not True or result.get("builder_transcript") is not False or result.get("verdict") != "pass"):
        _fail("Verify must be fresh, transcript-free, and accepting")
    return result


def validate_handoff(value: object, candidate: dict[str, str], intent: dict[str, Any], task: dict[str, Any], artifact_id: str, runtime: dict[str, Any]) -> dict[str, Any]:
    """Accept the complete S2 handoff using the already validated Verify bindings."""
    if not isinstance(value, dict) or set(value) != {"qa", "ci", "final_review", "pr"}:
        _fail("PR-ready handback requires QA, CI, final review, and PR evidence")
    for name in ("qa", "ci"):
        evidence = value[name]
        if not isinstance(evidence, list) or len(evidence) != len(task["commands"][name]):
            _fail(f"PR-ready {name} evidence is missing or incomplete")
        seen_commands: set[str] = set()
        for command in evidence:
            if not isinstance(command, dict) or command.get("command") not in task["commands"][name] or command.get("command") in seen_commands or command != {"status": "pass", "head": candidate["head"], "command": command["command"], "result": "pass", "artifact_id": artifact_id, "operation_id": intent["id"]}:
                _fail(f"PR-ready {name} evidence is unapproved, duplicate, or stale")
            seen_commands.add(command["command"])
        if seen_commands != set(task["commands"][name]):
            _fail(f"PR-ready {name} evidence does not cover every approved command")
    review = value["final_review"]
    if not isinstance(review, dict) or review.get("fresh_context") is not True or review != {"verdict": "pass", "candidate": candidate, "fresh_context": True, "runtime": runtime, "artifact_id": artifact_id, "operation_id": intent["id"], "criteria": list(task["criteria"])}:
        _fail("PR-ready final review evidence is missing or stale")
    pr = value["pr"]
    if not isinstance(pr, dict) or set(pr) != {"url", "head", "base", "state", "operation_id", "artifact_id", "merge"} or not isinstance(pr["url"], str) or not pr["url"] or pr["head"] != candidate["head"] or pr["base"] != candidate["base"] or pr["state"] != "open" or pr["operation_id"] != intent["id"] or pr["artifact_id"] != artifact_id or pr["merge"] != "unavailable":
        _fail("PR-ready evidence cannot merge or name a different candidate")
    return value


def _result(record: dict[str, Any], operation: dict[str, Any], task: dict[str, Any], result: object) -> dict[str, str]:
    """Supply immutable portable bindings to the same transition contract."""
    if operation["phase"] not in ("build", "verify"):
        _fail("a coordinator observation cannot be accepted as a worker result")
    candidate = None
    if operation["phase"] == "verify":
        builds = [item for item in record["usage"]["operations"] if item["phase"] == "build" and item["slice"] == operation["slice"] and item.get("task") == task]
        if len(builds) != 1 or builds[0].get("task") != task:
            _fail("Verify result lacks its approved Build task")
        candidate = _result(record, builds[0], task, builds[0].get("receipt"))
    return validate_worker_result(
        result, operation, operation["phase"], record["approval"]["routes"][operation["phase"]],
        task, candidate,
    )["candidate"]



def validate_ordinary_verify_failure(record: dict[str, Any], operation: dict[str, Any], task: dict[str, Any], receipt: object) -> dict[str, str]:
    """Retain a complete failing review without widening success acceptance."""
    if not isinstance(receipt, dict) or receipt.get("task_success") is not True or receipt.get("verdict") != "fail":
        _fail("dependency requires a complete failing ordinary Verify")
    criteria = receipt.get("criteria")
    if not isinstance(criteria, dict) or set(criteria) != set(task["criteria"]) or any(value not in {"pass", "fail"} for value in criteria.values()) or "fail" not in criteria.values():
        _fail("ordinary Verify failure lacks complete approved criterion outcomes")
    builds = [op for op in record["usage"]["operations"] if op["phase"] == "build" and op["slice"] == operation["slice"] and op.get("task") == task]
    if len(builds) != 1 or builds[0]["status"] not in {"result", "reconciled"}:
        _fail("ordinary Verify failure lacks its accepted Build")
    candidate = _result(record, builds[0], task, builds[0].get("receipt"))
    projected = deepcopy(receipt)
    projected["verdict"] = "pass"
    projected["criteria"] = {criterion: "pass" for criterion in task["criteria"]}
    validate_worker_result(projected, operation, "verify", record["approval"]["routes"]["verify"], task, candidate)
    return candidate

def validate_s2_portable(record: dict[str, Any]) -> None:
    # S3 adds separately validated diagnosis/repair operations to the same
    # cumulative ledger.  Keep the original coordinator/Build/Verify proof
    # intact instead of letting the new phases widen it.
    operations = [item for item in record["usage"]["operations"] if item["phase"] in {"coordinator", "build", "verify", "stack-verify"}]
    by_phase: dict[str, list[dict[str, Any]]] = {"coordinator": [], "build": [], "verify": []}
    for operation in operations:
        task = _identity(record, operation)
        if operation["phase"] in by_phase:
            by_phase[operation["phase"]].append(operation)
        receipt = operation.get("receipt")
        status = operation["status"]
        if status in {"result", "reconciled"}:
            if not isinstance(receipt, dict):
                _fail("completed operation lacks a retained receipt")
            if receipt.get("transport") == "accepted" and receipt.get("terminal_turn") is True and receipt.get("task_success") is True:
                if operation["phase"] == "stack-verify":
                    effective_task = restack_bound_verify_task(record, operation, task)
                    validate_worker_result(receipt, {**operation, "phase": "verify"}, "verify", record["approval"]["routes"]["verify"], effective_task, operation["candidate"])
                elif operation["phase"] == "verify" and receipt.get("verdict") == "fail":
                    validate_ordinary_verify_failure(record, operation, task, receipt)
                else:
                    _result(record, operation, task, receipt)
            else:
                _observation(operation, receipt)
        elif status == "intent":
            if receipt is not None:
                _fail("worker intent must not carry a receipt")
        elif status == "reconcile-required":
            if not isinstance(receipt, dict) or (receipt.get("transport") not in ("timeout", "unknown") and receipt.get("worker_state") not in {"queued", "active", "unknown"}):
                _fail("reconciliation-required operation lacks an incomplete correlated receipt")
            _observation(operation, receipt)
        elif status == "active":
            if operation["phase"] != "coordinator" or not isinstance(receipt, dict) or receipt.get("current_coordinator") != record["approval"]["coordinator"]["session_id"] or receipt.get("state") != "active":
                _fail("active coordinator receipt is malformed")
            _observation(operation, receipt)
        elif status == "cancellation-uncertain":
            if not isinstance(receipt, dict) or receipt.get("terminal_turn") is True or not isinstance(operation.get("cancellation"), dict) or operation["cancellation"].get("state") != "uncertain":
                _fail("uncertain cancellation state is malformed")
            _observation(operation, receipt); _observation(operation, operation["cancellation"])
        elif status == "unfinished-cancelled":
            if not isinstance(operation.get("cancellation"), dict) or operation["cancellation"].get("state") != "cancelled":
                _fail("cancelled unfinished operation lacks cancellation receipt")
            _observation(operation, operation["cancellation"])
    # One coordinator serves the run; each approved slice retains one exact
    # ordinary Build/Verify pair. Stack Verify keeps its separate identity.
    if len(by_phase["coordinator"]) > 1:
        _fail("S2 operation ordering is malformed")
    ordinary = [op for op in operations if op["phase"] in {"coordinator", "build", "verify"}]
    if by_phase["coordinator"] and ordinary[0]["phase"] != "coordinator":
        _fail("S2 operation ordering is malformed")
    groups = {}
    for operation in ordinary:
        if operation["phase"] == "coordinator":
            continue
        if operation["phase"] == "build":
            prior = record["usage"]["operations"][:record["usage"]["operations"].index(operation)]
            prefix = {**record, "usage": {**record["usage"], "operations": prior}}
            approved_slice = next(item for item in record["approval"]["slices"] if item["id"] == operation["slice"])
            for dependency in approved_slice["dependencies"]:
                accepted_slice_candidate(prefix, dependency)
            if any(op["phase"] in {"build", "verify"} and op["slice"] != operation["slice"] and op["status"] in {"intent", "reconcile-required", "cancellation-uncertain"} for op in prior):
                _fail("S2 ordinary workers must advance sequentially")
        group = groups.setdefault(operation["slice"], {"build": [], "verify": []})
        group[operation["phase"]].append(operation)
        if len(group[operation["phase"]]) > 1 or (operation["phase"] == "verify" and not group["build"]):
            _fail("S2 operation ordering is malformed")
        if group["verify"] and group["build"][0]["task"] != group["verify"][0]["task"]:
            _fail("S2 Build/Verify tasks differ within a slice")
    state = record["state"]
    if state["next_action"] in {"pr-ready", "verify"}:
        current_slice = state.get("slice_id")
        if current_slice is None and len(groups) == 1:
            current_slice = next(iter(groups))  # legacy single-slice checkpoint
        if current_slice not in groups:
            _fail("active S2 state requires one unambiguous current slice")
        by_phase = groups[current_slice]
    if state["next_action"] == "pr-ready":
        if len(by_phase["build"]) != 1 or len(by_phase["verify"]) != 1:
            _fail("PR-ready state lacks Build/Verify ledger")
        build, verify = by_phase["build"][0], by_phase["verify"][0]
        task = _task(record, build)
        build_candidate = _result(record, build, task, build.get("receipt"))
        verify_candidate = _result(record, verify, task, verify.get("receipt"))
        if build_candidate != verify_candidate or state.get("candidate") != build_candidate or state.get("review") != {"findings": verify["receipt"].get("nonblocking_findings", []), "verdict": "pass"}:
            _fail("PR-ready state candidate/review differs from ledger")
        receipt = verify["receipt"]
        validate_handoff(receipt.get("handoff"), build_candidate, verify, task,
                         receipt["evidence"]["artifact"]["id"], receipt["runtime"])
        if state.get("handback") != {"outcome": "pr-ready", "merge": "unavailable", "evidence": verify["receipt"]["handoff"]}:
            _fail("PR-ready handback differs from Verify evidence")
    elif state["next_action"] == "verify":
        if len(by_phase["build"]) != 1:
            _fail("Verify state lacks Build ledger")
        task = _task(record, by_phase["build"][0])
        if state.get("candidate") != _result(record, by_phase["build"][0], task, by_phase["build"][0].get("receipt")):
            _fail("Verify state candidate differs from Build evidence")
    elif state["next_action"] == "review-ready" and "stack" not in record:
        accepted = {}
        for approved in record["approval"]["slices"]:
            accepted[approved["id"]] = accepted_slice_candidate(record, approved["id"])
        final_id = state.get("slice_id")
        if final_id not in accepted:
            _fail("review-ready final slice is outside accepted scope")
        final_candidate = accepted[final_id]
        handback = state.get("handback")
        pr = handback.get("pr") if isinstance(handback, dict) else None
        review = state.get("review")
        if state.get("candidate") != final_candidate or not isinstance(review, dict) or review.get("verdict") != "pass":
            _fail("review-ready requires the final independently verified candidate")
        if not isinstance(handback, dict) or set(handback) != {"outcome", "merge", "pr"} or handback["outcome"] != "review-ready" or handback["merge"] != "unavailable":
            _fail("review-ready handback is malformed")
        if not isinstance(pr, dict) or set(pr) != {"url", "repository", "number", "state", "head", "base", "base_ref"} or pr["state"] != "open" or pr["head"] != final_candidate["head"] or pr["base"] != final_candidate["base"] or pr["base_ref"] != record["approval"]["repository"].get("base_ref") or type(pr["number"]) is not int or pr["number"] < 1:
            _fail("review-ready PR differs from final verified candidate")
        if not isinstance(pr["repository"], str) or not pr["repository"] or pr["url"] != f"https://github.com/{pr['repository']}/pull/{pr['number']}":
            _fail("review-ready PR identity is malformed")
        approved_urls = record["approval"]["repository"]
        if not any(approved_urls["fetch_url"] == prefix + pr["repository"] + suffix and
                   approved_urls["push_url"] == prefix + pr["repository"] + suffix
                   for prefix in ("https://github.com/", "git@github.com:") for suffix in ("", ".git")):
            _fail("review-ready PR repository differs from immutable approval")


def accepted_ordinary_candidate(record: dict[str, Any], slice_id: str) -> dict[str, str]:
    """Require the exact successful ordinary pair, independently of current state."""
    builds = [op for op in record["usage"]["operations"] if op["phase"] == "build" and op["slice"] == slice_id]
    verifies = [op for op in record["usage"]["operations"] if op["phase"] == "verify" and op["slice"] == slice_id]
    if len(builds) != 1 or len(verifies) != 1 or any(op["status"] not in {"result", "reconciled"} for op in builds + verifies):
        _fail("dependency requires an accepted ordinary Build/Verify pair")
    build, verify = builds[0], verifies[0]
    task = _task(record, build)
    if verify.get("task") != task:
        _fail("dependency Build/Verify tasks differ")
    candidate = _result(record, build, task, build.get("receipt"))
    if _result(record, verify, task, verify.get("receipt")) != candidate:
        _fail("dependency Verify candidate differs from Build")
    receipt = verify["receipt"]
    validate_handoff(receipt.get("handoff"), candidate, verify, task, receipt["evidence"]["artifact"]["id"], receipt["runtime"])
    return candidate


def accepted_slice_candidate(record: dict[str, Any], slice_id: str) -> dict[str, str]:
    """A completed same-slice S3 repair supersedes its retained ordinary failure."""
    repair = record.get("repair")
    if not isinstance(repair, dict) or repair.get("slice_id") != slice_id:
        prior = [item for item in record.get("repair_history", []) if item.get("slice_id") == slice_id]
        if not prior:
            return accepted_ordinary_candidate(record, slice_id)
        if len(prior) != 1:
            _fail("dependency repair history has duplicate slice")
        record = {**record, "repair": prior[0]}
        repair = prior[0]
    if repair.get("status") != "completed":
        _fail("dependency repair has not completed with fresh Verify")
    from .interim_repair import RepairPolicyError, validate_repair, _worker
    try:
        # A dependency prefix excludes later operations. Forecast revisions
        # belong to the full ledger, so validate only revisions whose receipt
        # is present in this prefix while retaining the shared repair checker.
        observed = {item["id"] for item in record["usage"]["operations"] if isinstance(item.get("receipt"), dict)}
        checked = {**record, "forecasts": {**record["forecasts"], "revised": [item for item in record["forecasts"]["revised"] if item["evidence"]["operation_id"] in observed]}}
        validate_repair(checked)
        ordinary_builds = [op for op in record["usage"]["operations"] if op["phase"] == "build" and op["slice"] == slice_id]
        ordinary_verifies = [op for op in record["usage"]["operations"] if op["phase"] == "verify" and op["slice"] == slice_id]
        if "origin_operation_id" in repair["opening"]:
            origin = next((op for op in record["usage"]["operations"] if op["id"] == repair["opening"]["origin_operation_id"]), None)
            if (not isinstance(origin, dict) or origin.get("slice") != slice_id or origin.get("status") not in {"result-unusable", "result", "reconciled"}
                    or not isinstance(origin.get("failure_reconciliation"), dict)
                    or origin.get("status") in {"result", "reconciled"} and (origin.get("phase") != "verify" or origin.get("receipt", {}).get("verdict") != "fail")
                    or origin["failure_reconciliation"]["candidate"] != repair["opening"]["revisions"]):
                _fail("dependency repair lacks exact reconciled failed predecessor")
        else:
            if len(ordinary_builds) != 1 or len(ordinary_verifies) != 1 or any(op["status"] not in {"result", "reconciled"} for op in ordinary_builds + ordinary_verifies):
                _fail("dependency repair requires one completed ordinary Build/Verify antecedent")
            ordinary_build, ordinary_verify = ordinary_builds[0], ordinary_verifies[0]
            task = _task(record, ordinary_build)
            if ordinary_verify.get("task") != task:
                _fail("dependency repair ordinary tasks differ")
            opening_candidate = validate_ordinary_verify_failure(record, ordinary_verify, task, ordinary_verify.get("receipt"))
            if repair["opening"]["revisions"] != opening_candidate:
                _fail("dependency repair opening differs from failed ordinary candidate")
            finding = repair["opening"]["finding"]
            failure = ordinary_verify["receipt"]
            if failure["criteria"].get(finding["criterion_id"]) != "fail":
                _fail("dependency repair finding does not name a failed Verify criterion")
            failed_check_evidence = {(item["command"], item["artifact_id"]) for item in failure["evidence"]["checks"] if item["criterion_id"] == finding["criterion_id"]}
            for evidence in (finding["evidence"], repair["opening"]["execution_evidence"]):
                if any((item["command"], item["artifact_id"]) not in failed_check_evidence for item in evidence):
                    _fail("dependency repair opening evidence is unrelated to failed Verify")
        cycle = repair["cycles"][-1]
        operations = {op["id"]: op for op in record["usage"]["operations"]}
        build = operations[cycle["repair_operation_id"]]
        verify = operations[cycle["verify_operation_id"]]
        if cycle["outcome"] != "pass" or any(op["status"] not in {"result", "reconciled"} or op["slice"] != slice_id for op in (build, verify)):
            _fail("dependency repair lacks completed correlated workers")
        candidate = _worker(record, build, "build", build.get("receipt"))["candidate"]
        _worker(record, verify, "verify", verify.get("receipt"), candidate)
        return candidate
    except (RepairPolicyError, KeyError, IndexError, TypeError) as exc:
        _fail("dependency repair evidence is invalid: " + str(exc))

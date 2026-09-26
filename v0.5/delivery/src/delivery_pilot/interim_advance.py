"""One exact-ref, observe-first interim coordinator continuation."""
from __future__ import annotations

import json
import re
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from .interim import InterimCheckpointError, InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, validate_record
from .interim_coordinator import InterimFixtureCoordinator, InterimDispatchError, _limit, _handback, _task
from .interim_semantics import SemanticError, accepted_slice_candidate
from .interim_disposition import eligible as recovery_check_eligible, unresolved as unresolved_disposition, clear as clear_disposition
from .interim_repair_coordinator import InterimRepairCoordinator, repair_opening_authority
from .interim_recovery import InterimRecoveryCoordinator
from datetime import datetime, timezone


def _repository_name(record: dict[str, Any]) -> str:
    urls = (record["approval"]["repository"][key] for key in ("fetch_url", "push_url"))
    names = []
    for url in urls:
        match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", url)
        if match is None:
            raise InterimDispatchError("approved repository is not a single GitHub repository")
        names.append(match.group(1))
    if names[0] != names[1]:
        raise InterimDispatchError("approved fetch and push repositories differ")
    return names[0]


def github_hint_emitter(record: dict[str, Any]) -> Callable[[dict[str, str]], None]:
    repository = _repository_name(record)
    def emit(where: dict[str, str]) -> None:
        from .interim_github import DISPATCH_TYPE
        payload = json.dumps({"event_type": DISPATCH_TYPE, "client_payload": where}, separators=(",", ":"))
        result = subprocess.run(["gh", "api", "--method", "POST", f"repos/{repository}/dispatches", "--input", "-"],
                                input=payload, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if result.returncode:
            raise OSError("GitHub event hint unavailable")
    return emit


def github_pr_readback(record: dict[str, Any], claimed_url: str,
                       command: Callable[[list[str]], dict[str, Any]] | None = None) -> dict[str, Any]:
    """Read a claimed PR by number; never treat the worker URL as proof."""
    repository = _repository_name(record)
    base_ref = record["approval"]["repository"].get("base_ref")
    if not isinstance(base_ref, str) or not base_ref.startswith("refs/heads/"):
        raise InterimDispatchError("final PR requires an approved base branch ref")
    parsed = urlsplit(claimed_url)
    match = re.fullmatch(r"/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/pull/(\d+)", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "github.com" or match is None or match.group(1) != repository or parsed.query or parsed.fragment:
        raise InterimDispatchError("claimed PR URL differs from approved repository")
    number = match.group(2)
    if command is None:
        def command(argv: list[str]) -> dict[str, Any]:
            result = subprocess.run(argv, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            if result.returncode:
                raise InterimDispatchError("GitHub PR readback unavailable")
            try:
                value = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise InterimDispatchError("GitHub PR readback malformed") from exc
            return value
    value = command(["gh", "api", f"repos/{repository}/pulls/{number}"])
    if not isinstance(value, dict) or type(value.get("number")) is not int or value["number"] != int(number) or value.get("html_url") != claimed_url or value.get("state") != "open":
        raise InterimDispatchError("GitHub does not confirm the claimed open PR")
    base, head = value.get("base"), value.get("head")
    if not isinstance(base, dict) or not isinstance(head, dict) or not isinstance(base.get("repo"), dict) or not isinstance(head.get("repo"), dict):
        raise InterimDispatchError("GitHub PR identity is incomplete")
    if base["repo"].get("full_name") != repository or head["repo"].get("full_name") != repository or base.get("ref") != base_ref.removeprefix("refs/heads/"):
        raise InterimDispatchError("GitHub PR repository differs from approval")
    return {"url": claimed_url, "repository": repository, "number": int(number),
            "state": "open", "head": head.get("sha"), "base": base.get("sha"), "base_ref": base_ref}


def _accepted(record: dict[str, Any]) -> dict[str, dict[str, str]]:
    accepted = {}
    for item in record["approval"]["slices"]:
        try:
            accepted[item["id"]] = accepted_slice_candidate(record, item["id"])
        except SemanticError:
            pass
    return accepted


def _open_failed_or_decide(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                           tasks: dict[str, Any], clock: Callable[[], datetime]) -> InterimCheckpointSnapshot:
    record = validate_record(snapshot.value)
    slice_id = record["state"]["slice_id"]
    task = _task(tasks[slice_id], slice_id)
    refusal = repair_opening_authority(record, slice_id)
    if refusal:
        return store.persist_lifecycle(snapshot, _handback(deepcopy(record),
            refusal + "; exact failed-worker effects are reconciled and further repair needs a scoped decision"))
    return InterimRepairCoordinator(store, clock=clock).open_failed_worker(snapshot, slice_id, task)


def _settle_failed_worker(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
                          tasks: dict[str, Any], host: Any, clock: Callable[[], datetime]) -> dict[str, str]:
    record = validate_record(snapshot.value)
    operation = next(item for item in record["usage"]["operations"] if item["id"] == record["state"]["operation_id"])
    if not hasattr(host, "reconcile_failed"):
        return {"outcome": record["state"]["next_action"], "operation_id": operation["id"]}
    try:
        fact = host.reconcile_failed(deepcopy(operation), deepcopy(record), store.repository)
        projected = deepcopy(record)
        failed = next(item for item in projected["usage"]["operations"] if item["id"] == operation["id"])
        failed["failure_reconciliation"] = fact
        projected["state"] = {"next_action": "failure-reconciled", "slice_id": operation["slice"],
                              "candidate": deepcopy(fact["candidate"]), "review": None, "handback": None}
        clear_disposition(projected)
        validate_record(projected)
    except (InterimError, OSError, ValueError, KeyError, TypeError):
        projected = deepcopy(record)
        if unresolved_disposition(projected, "uncertain-effect", operation["id"], clock()):
            projected = _handback(projected, "worker cessation or effects remained uncertain for three backup cycles")
        snapshot = store.persist_lifecycle(snapshot, projected)
        return {"outcome": snapshot.value["state"]["next_action"], "commit_sha": snapshot.commit_sha}
    snapshot = store.persist_lifecycle(snapshot, projected)
    # The charged wake establishes effects before any replacement authority.
    # A final selected slot may settle the failure but cannot send a repair.
    limit = _limit(snapshot.value, clock())
    if limit:
        snapshot = store.persist_lifecycle(snapshot, _handback(deepcopy(snapshot.value), limit))
        return {"outcome": "selected-limit", "commit_sha": snapshot.commit_sha}
    if operation["phase"] in {"build", "verify"}:
        snapshot = _open_failed_or_decide(store, snapshot, tasks, clock)
        return {"outcome": snapshot.value["state"]["next_action"], "commit_sha": snapshot.commit_sha}
    return {"outcome": "failure-reconciled", "commit_sha": snapshot.commit_sha}


def _finish_pr(store: InterimCheckpointStore, snapshot: InterimCheckpointSnapshot,
               pr_readback: Callable[[dict[str, Any], str], dict[str, Any]]) -> InterimCheckpointSnapshot | None:
    record = snapshot.value
    candidate = record["state"]["candidate"]
    claimed = record["state"]["handback"]["evidence"]["pr"]["url"]
    observed = pr_readback(record, claimed)
    if observed.get("head") != candidate["head"] or observed.get("base") != candidate["base"]:
        return None
    projected = deepcopy(record)
    projected["state"] = {"next_action": "review-ready", "slice_id": record["state"]["slice_id"],
                          "candidate": candidate, "review": deepcopy(record["state"]["review"]),
                          "handback": {"outcome": "review-ready", "merge": "unavailable", "pr": observed}}
    return store.persist_lifecycle(snapshot, projected)


def advance_once(store: InterimCheckpointStore, approved_record: dict[str, Any],
                 tasks: dict[str, Any], host: Any,
                 pr_readback: Callable[[dict[str, Any], str], dict[str, Any]] = github_pr_readback,
                 now: datetime | None = None) -> dict[str, str]:
    """Reconcile one awaited worker, then finish its bounded successor step."""
    snapshot = store.reload(approved_record)
    record = validate_record(snapshot.value)
    if record.get("monitoring", {}).get("state") == "active" and store.dispatch_emitter is None:
        store.dispatch_emitter = github_hint_emitter(record)
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    at = clock()
    recovery = record.get("recovery", {})
    if recovery.get("status") == "uncertain" and isinstance(recovery.get("stop"), dict):
        if record.get("monitoring", {}).get("state") == "inactive" and any(
                item["cause"] == "unconfirmed-cancellation" for item in record.get("recovery_disposition", {}).get("notices", [])):
            return {"outcome": "unconfirmed-cancellation"}
        if not recovery_check_eligible(record, at):
            return {"outcome": "recovery-wait"}
        snapshot = InterimRecoveryCoordinator(store, clock=lambda: at).stop(snapshot, recovery["stop"]["instruction"], host)
        projected = deepcopy(snapshot.value)
        if projected["recovery"]["status"] != "stopped":
            pending = [item for item in projected["usage"]["operations"] if item["status"] in {"intent", "active", "reconcile-required", "cancellation-uncertain"}]
            operation_id = pending[-1]["id"] if pending else projected["approval"]["coordinator"]["session_id"]
            if unresolved_disposition(projected, "unconfirmed-cancellation", operation_id, at):
                projected = _handback(projected, "cancellation remained unconfirmed for three backup cycles")
            snapshot = store.persist_lifecycle(snapshot, projected)
        return {"outcome": "whole-run-stop" if snapshot.value["recovery"]["status"] == "stopped" else "unconfirmed-cancellation",
                "commit_sha": snapshot.commit_sha}
    if record.get("monitoring", {}).get("state") == "inactive" or record["state"]["next_action"] in {"review-ready", "handback"}:
        return {"outcome": record["state"]["next_action"]}
    if record.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"}:
        return {"outcome": "whole-run-stop"}
    if not recovery_check_eligible(record, at):
        return {"outcome": "recovery-wait"}
    if record["state"]["next_action"] in {"worker-failed", "verify-failed"}:
        try:
            return _settle_failed_worker(store, snapshot, tasks, host, clock)
        except InterimCheckpointError as exc:
            if exc.code != "cas-lost":
                raise
            snapshot = store.reload(approved_record)
            return {"outcome": snapshot.value["state"]["next_action"], "commit_sha": snapshot.commit_sha}
    pending = any(item.get("phase") not in {"coordinator", "wake"} and item.get("status") in {"intent", "reconcile-required"}
                  for item in record["usage"]["operations"])
    limit = _limit(record, at)
    if not pending and record["state"]["next_action"] != "pr-ready" and limit:
        snapshot = store.persist_lifecycle(snapshot, _handback(deepcopy(record), limit))
        return {"outcome": "selected-limit", "commit_sha": snapshot.commit_sha}
    coordinator = InterimFixtureCoordinator(store, clock=clock)
    action = record["state"]["next_action"]
    try:
        repair = record.get("repair")
        if action == "failure-reconciled":
            failed = next(item for item in record["usage"]["operations"] if item["id"] == next(
                item["id"] for item in reversed(record["usage"]["operations"]) if isinstance(item.get("failure_reconciliation"), dict)
                and item["slice"] == record["state"]["slice_id"]))
            repair_coordinator = InterimRepairCoordinator(store, clock=clock)
            if failed["phase"] in {"build", "verify"}:
                snapshot = _open_failed_or_decide(store, snapshot, tasks, clock)
            else:
                projected = deepcopy(record)
                policy = projected["repair"]
                failed = next(item for item in projected["usage"]["operations"] if item["id"] == failed["id"])
                if failed["phase"] == "diagnosis":
                    policy["status"] = "diagnosis-required"
                    projected["state"] = {"next_action": "diagnosis", "candidate": deepcopy(failed["failure_reconciliation"]["candidate"]), "review": None, "handback": None}
                elif failed["phase"] == "repair" and "escalated_slot" in failed:
                    repair_coordinator._close_escalated_without_candidate(projected, policy, "escalated worker failed after safe effect reconciliation")
                elif failed["phase"] == "repair-verify" and "escalated_verify" in failed:
                    same_candidate = failed["failure_reconciliation"]["candidate"] == failed["candidate"]
                    attempts = sum(item["phase"] == "repair-verify" and item.get("escalated_verify") == failed["escalated_verify"]
                                   for item in projected["usage"]["operations"])
                    if not same_candidate or attempts >= 3:
                        policy["status"] = "stuck"
                        projected = _handback(projected, "fresh Verify recovery exhausted or candidate SHA changed; retain the unaccepted candidate")
                    else:
                        policy["status"] = "repair-verify-ready"
                        projected["state"] = {"next_action": "repair-verify", "candidate": deepcopy(failed["candidate"]), "review": None, "handback": None}
                else:
                    cycle = repair_coordinator._cycle(projected, failed)
                    repair_coordinator._no_progress(projected, policy, cycle, "failed repair worker required a new decision after reconciliation")
                snapshot = store.persist_lifecycle(snapshot, projected)
        elif isinstance(repair, dict) and repair["status"] not in {"completed", "handback", "stuck"}:
            repair_coordinator = InterimRepairCoordinator(store, clock=clock)
            slice_id = repair["slice_id"]
            if repair["status"] in {"diagnosis-required", "waiting-diagnosis"}:
                snapshot = repair_coordinator.diagnose(snapshot, slice_id, tasks[slice_id], host)
            elif repair["status"] in {"repair-ready", "repair-verify-ready", "waiting-repair", "waiting-repair-verify", "escalation-ready"}:
                if repair["status"] == "escalation-ready":
                    snapshot = repair_coordinator.escalate_once(snapshot, slice_id, tasks[slice_id], host, host)
                else:
                    snapshot = repair_coordinator.repair_once(snapshot, slice_id, tasks[slice_id], host, host)
            else:
                return {"outcome": "worker-failed"}
        elif action == "await-worker":
            operation = next(item for item in record["usage"]["operations"] if item["id"] == record["state"]["operation_id"])
            if operation["phase"] not in {"build", "verify"}:
                return {"outcome": "await-other-worker"}
            snapshot = coordinator.reconcile_pending(snapshot, operation["id"], host)
            if snapshot.value["state"]["next_action"] in {"worker-failed", "verify-failed"}:
                return _settle_failed_worker(store, snapshot, tasks, host, clock)
            # A completed ordinary worker leaves a durable result and a fresh
            # successor boundary. Use this same charged turn for the next
            # authorized step. run_frontier admits at most one new worker, and
            # its send path rechecks Stop, limits and the exact CAS before send.
            if snapshot.value["state"]["next_action"] in {"build", "verify"}:
                snapshot = coordinator.run_frontier(snapshot, tasks, host, host, one_step=True)
            if snapshot.value["state"]["next_action"] == "pr-ready" and len(_accepted(snapshot.value)) == len(snapshot.value["approval"]["slices"]):
                finished = _finish_pr(store, snapshot, pr_readback)
                if finished is None:
                    return {"outcome": "pr-head-or-base-changed"}
                snapshot = finished
            elif snapshot.value["state"]["next_action"] == "pr-ready":
                snapshot = coordinator.run_frontier(snapshot, tasks, host, host, one_step=True)
        elif action == "pr-ready" and len(_accepted(record)) == len(record["approval"]["slices"]):
            finished = _finish_pr(store, snapshot, pr_readback)
            if finished is None:
                return {"outcome": "pr-head-or-base-changed"}
            snapshot = finished
        else:
            snapshot = coordinator.run_frontier(snapshot, tasks, host, host, one_step=True)
    except InterimCheckpointError as exc:
        if exc.code != "cas-lost":
            raise
        snapshot = store.reload(approved_record)
    final_state = snapshot.value["state"]
    handback = final_state.get("handback")
    outcome = ("selected-limit" if final_state["next_action"] == "handback" and isinstance(handback, dict)
               and isinstance(handback.get("reason"), str) and handback["reason"].startswith("selected ")
               else final_state["next_action"])
    return {"outcome": outcome, "commit_sha": snapshot.commit_sha}

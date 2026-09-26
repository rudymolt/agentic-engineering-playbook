"""Verify-owned, exact-operation GitHub PR opening with durable ambiguity."""
from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode

from .interim import InterimCheckpointError, InterimCheckpointStore, validate_record
from .interim_advance import _repository_name, github_pr_readback
from .interim_coordinator import InterimDispatchError, _limit


Api = Callable[[str, str, dict[str, Any] | None], Any]


def _gh_api(method: str, path: str, payload: dict[str, Any] | None) -> Any:
    argv = ["gh", "api", "--method", method, path]
    if payload is not None:
        argv += ["--input", "-"]
    result = subprocess.run(argv, input=json.dumps(payload) if payload is not None else None,
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if result.returncode:
        raise InterimDispatchError("GitHub PR API unavailable")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InterimDispatchError("GitHub PR API returned malformed JSON") from exc


def ensure_verify_pr(store: InterimCheckpointStore, operation_id: str, api: Api = _gh_api) -> dict[str, Any]:
    """Open at most one PR for a durable Verify intent, or observe its effect.

    A persisted create marker is never cleared or reissued after an ambiguous
    response. A subsequent invocation reads GitHub only, including after a
    process crash immediately following the POST.
    """
    snapshot = store.reload_registered()
    record = validate_record(snapshot.value)
    matches = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
    if len(matches) != 1 or matches[0]["phase"] != "verify":
        raise InterimDispatchError("PR lookup requires one approved Verify operation")
    operation = matches[0]
    candidate = operation.get("candidate")
    task = operation.get("task")
    if not isinstance(candidate, dict) or not isinstance(task, dict) or candidate.get("base") != task.get("base"):
        raise InterimDispatchError("Verify candidate does not bind its approved base")
    repository = _repository_name(record)
    base_ref = record["approval"]["repository"].get("base_ref")
    if not isinstance(base_ref, str) or not base_ref.startswith("refs/heads/"):
        raise InterimDispatchError("approved base branch ref is missing")
    head_ref = "refs/heads/" + task["candidate_ref"]
    if subprocess.run(["git", "check-ref-format", head_ref], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL, check=False).returncode:
        raise InterimDispatchError("approved candidate branch ref is malformed")
    for ref, expected in ((head_ref, candidate["head"]), (base_ref, candidate["base"])):
        observed = api("GET", f"repos/{repository}/git/ref/{quote(ref.removeprefix('refs/'), safe='/')}", None)
        if not isinstance(observed, dict) or not isinstance(observed.get("object"), dict) or observed["object"].get("sha") != expected:
            raise InterimDispatchError("GitHub branch moved from approved Verify candidate")
    head_name = head_ref.removeprefix("refs/heads/")
    base_name = base_ref.removeprefix("refs/heads/")
    query = urlencode({"state": "open", "head": repository.split("/", 1)[0] + ":" + head_name,
                       "base": base_name})
    list_path = f"repos/{repository}/pulls?{query}"

    def existing() -> dict[str, Any] | None:
        values = api("GET", list_path, None)
        if not isinstance(values, list) or len(values) > 1:
            raise InterimDispatchError("GitHub PR lookup is ambiguous")
        if not values:
            return None
        value = values[0]
        if not isinstance(value, dict) or not isinstance(value.get("html_url"), str):
            raise InterimDispatchError("GitHub PR lookup is malformed")
        observed = github_pr_readback(record, value["html_url"],
                                      lambda _: api("GET", f"repos/{repository}/pulls/{value.get('number')}", None))
        if observed["head"] != candidate["head"] or observed["base"] != candidate["base"]:
            raise InterimDispatchError("GitHub PR differs from independently verified candidate")
        return observed

    found = existing()
    if found is not None:
        return found
    # GitHub reads above may take time. Reload immediately before the durable
    # effect-admission CAS, so a committed Stop during those reads wins.
    current = store.reload_registered()
    authority = validate_record(current.value)
    current_matches = [item for item in authority["usage"]["operations"] if item["id"] == operation_id]
    if (len(current_matches) != 1 or
            current_matches[0].get("candidate") != candidate or
            current_matches[0].get("task") != task or
            authority.get("monitoring", {}).get("state") != "active" or
            authority.get("recovery", {}).get("status") in {"stopping", "stopped", "uncertain"} or
            current_matches[0]["status"] not in {"intent", "reconcile-required"}):
        raise InterimDispatchError("PR creation lacks active Verify authority")
    if _limit(authority, datetime.now(timezone.utc)):
        raise InterimDispatchError("selected limit refuses PR creation")
    if "pr_create_intent" in current_matches[0]:
        raise InterimDispatchError("prior PR create effect remains unresolved")
    projected = deepcopy(authority)
    intended = next(item for item in projected["usage"]["operations"] if item["id"] == operation_id)
    intended["pr_create_intent"] = {"head": candidate["head"], "base": candidate["base"],
                                    "base_ref": base_ref, "at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    try:
        store.persist_lifecycle(current, projected)
    except InterimCheckpointError as exc:
        if exc.code == "cas-lost":
            raise InterimDispatchError("PR create admission lost to concurrent checkpoint") from exc
        raise
    # This CAS is the final effect-admission boundary. A later Stop must
    # reconcile this exact potentially in-flight POST; it cannot revoke it.
    try:
        api("POST", f"repos/{repository}/pulls",
            {"title": record["approval"]["tracker"]["id"] + " approved interim run",
             "body": "Verified interim run " + record["approval"]["run_id"],
             "head": head_name, "base": base_name})
    except (InterimDispatchError, OSError, TimeoutError, ConnectionError):
        # The response is never retry authority; the exact PR is read below.
        pass
    found = existing()
    if found is None:
        raise InterimDispatchError("PR create effect remains unresolved")
    return found


def main(argv: list[str] | None = None) -> int:
    class SafeParser(argparse.ArgumentParser):
        def error(self, message: str) -> None:
            self.exit(2, "interim PR refused: invalid arguments\n")
    parser = SafeParser(description="Observe or create one approved Verify PR")
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--control-ref", required=True)
    parser.add_argument("--operation-id", required=True)
    args = parser.parse_args(argv)
    try:
        value = ensure_verify_pr(InterimCheckpointStore(args.repository, args.remote, args.control_ref), args.operation_id)
    except Exception:
        parser.exit(2, "interim PR unavailable or unresolved; inspect the exact operation\n")
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

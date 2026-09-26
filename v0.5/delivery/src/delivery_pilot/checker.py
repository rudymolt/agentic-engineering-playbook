"""Fresh-checker route and launcher receipt validation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .contracts import ContractError, SHA256


LAUNCHER_V2_POLICY = {
    "python_bytecode_control": "env-and-flag",
    "repository_temp_policy": "outside-checkout",
    "repository_write_policy": "forbidden",
    "transient_write_monitor": "enabled",
}
LAUNCHER_V3_STATIC_POLICY = {
    **LAUNCHER_V2_POLICY,
    "macos_mach_lookup_allowlist": ["com.apple.FSEvents"],
}
LAUNCHER_V4_POLICY = {
    "python_bytecode_control": "env-and-flag",
    "repository_temp_policy": "outside-checkout",
    "repository_write_policy": "forbidden-except-provider-checkpoints",
    "transient_write_monitor": "enabled",
    "provider_checkpoint_policy": "conductor-turn-bound",
}

LAUNCHER_V4_CHECKOUT_FIELDS = {
    "start_head_sha", "end_head_sha", "start_tree", "end_tree",
    "start_index_digest", "end_index_digest",
    "start_staged_diff_digest", "end_staged_diff_digest",
    "start_worktree_digest", "end_worktree_digest",
    "start_untracked", "end_untracked",
    "start_noncheckpoint_refs_digest", "end_noncheckpoint_refs_digest",
    "clean", "read_only", "builder_context_input",
}
LAUNCHER_V4_PROVIDER_FIELDS = {
    "provider", "actor_name", "actor_email", "ref_namespace", "turn_id",
    "start_ref", "end_ref", "start_commit", "end_commit",
    "start_tree", "end_tree", "start_created_at", "end_created_at",
    "metadata_digest",
}
CHECKER_LIFECYCLE_FIELDS = {
    "schema_version", "lifecycle_id", "launch_id", "session_id", "candidate_tree",
    "command_manifest_digest", "command_manifest_locator", "command_count",
    "all_required_commands_completed", "all_exit_codes_observed", "child_processes_reaped",
    "last_command_completed_at", "monitor_stopped_at", "completion_marker",
}
GIT_OBJECT_ID = re.compile(r"^[0-9a-f]{40}$")


def select_route(builder_family: str, builder_model: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    available = [item for item in candidates if item.get("available")]
    rungs = (
        (lambda x: x.get("family") != builder_family and not x.get("degraded"), 1, "cross-family", "full"),
        (lambda x: x.get("family") != builder_family, 2, "cross-family-degraded", "degraded"),
        (lambda x: x.get("family") == builder_family and x.get("model") != builder_model, 3, "same-family-different-model", "weakened"),
        (lambda x: x.get("family") == builder_family and x.get("model") == builder_model, 4, "same-family-same-model", "weakened"),
    )
    for predicate, rung, independence, strength in rungs:
        candidate = next((item for item in available if predicate(item)), None)
        if candidate:
            return {**candidate, "rung": rung, "independence": independence, "gate_strength": strength}
    return {"rung": None, "independence": "none", "gate_strength": "none", "status": "waiting_capacity"}


def _validate_common_launcher_receipt(
    receipt: dict[str, Any],
    tier: str,
    expected: dict[str, Any] | None,
    schema_version: int,
) -> None:
    required = {
        "schema_version", "launch_id", "session_id", "workspace_id", "parent_context",
        "requested", "runtime", "prompt_digest", "envelope_digest", "spec_digest",
        "candidate", "checkout", "started_at", "ended_at", "termination_state",
        "raw_evidence_digest", "raw_evidence_locator", "execution_policy",
    }
    missing = required - set(receipt)
    if missing:
        raise ContractError(f"launcher missing {sorted(missing)}")
    if receipt["schema_version"] != schema_version or receipt["parent_context"] is not False:
        raise ContractError("checker must be a fresh, non-forked session")
    if receipt["requested"] != receipt["runtime"]:
        raise ContractError("requested/runtime checker identity mismatch")
    checkout = receipt["checkout"]
    if checkout.get("clean") is not True or checkout.get("read_only") is not True:
        raise ContractError("checker checkout is dirty or write-enabled")
    if checkout.get("builder_context_input") is not False:
        raise ContractError("checker consumed builder-only context")
    if checkout.get("start_tree") != checkout.get("end_tree") or checkout.get("start_untracked") != checkout.get("end_untracked"):
        raise ContractError("checker checkout mutated")
    if receipt["termination_state"] != "completed":
        raise ContractError("checker did not complete")
    if tier in {"B", "C"} and not receipt.get("host_proof"):
        raise ContractError("host-proof receipt required")
    if expected:
        for field in ("prompt_digest", "envelope_digest", "spec_digest"):
            if field in expected and receipt.get(field) != expected[field]:
                raise ContractError(f"launcher {field} mismatch")
        if "candidate" in expected and receipt.get("candidate") != expected["candidate"]:
            raise ContractError("launcher candidate tuple mismatch")


def validate_launcher_receipt(receipt: dict[str, Any], tier: str, expected: dict[str, Any] | None = None) -> None:
    """Validate immutable historical Launcher V2 semantics."""
    _validate_common_launcher_receipt(receipt, tier, expected, schema_version=2)
    if receipt["execution_policy"] != LAUNCHER_V2_POLICY:
        raise ContractError("checker execution policy does not enforce a transient-write-free checkout")


def validate_launcher_v3_receipt(receipt: dict[str, Any], tier: str, expected: dict[str, Any] | None = None) -> None:
    """Validate Launcher V3 including the exact macOS service and profile binding."""
    _validate_common_launcher_receipt(receipt, tier, expected, schema_version=3)
    policy = receipt["execution_policy"]
    if not isinstance(policy, dict) or set(policy) != set(LAUNCHER_V3_STATIC_POLICY) | {"seatbelt_profile_digest"}:
        raise ContractError("launcher V3 execution policy fields do not match")
    for field, value in LAUNCHER_V3_STATIC_POLICY.items():
        if policy.get(field) != value:
            raise ContractError(f"launcher V3 execution policy mismatch: {field}")
    if not isinstance(policy.get("seatbelt_profile_digest"), str) or not SHA256.match(policy["seatbelt_profile_digest"]):
        raise ContractError("launcher V3 Seatbelt profile digest is invalid")
    if expected and "execution_policy" in expected and policy != expected["execution_policy"]:
        raise ContractError("launcher execution policy mismatch")


def validate_launcher_v4_receipt(receipt: dict[str, Any], tier: str, expected: dict[str, Any] | None = None) -> None:
    """Validate a Cloud checker with only exact Conductor checkpoint writes."""
    _validate_common_launcher_receipt(receipt, tier, expected, schema_version=4)
    policy = receipt["execution_policy"]
    if policy != LAUNCHER_V4_POLICY:
        raise ContractError("launcher V4 execution policy mismatch")

    checkout = receipt["checkout"]
    if not isinstance(checkout, dict) or set(checkout) != LAUNCHER_V4_CHECKOUT_FIELDS:
        raise ContractError("launcher V4 checkout fields do not match")
    if checkout["clean"] is not True or checkout["read_only"] is not True or checkout["builder_context_input"] is not False:
        raise ContractError("launcher V4 checkout is dirty or write-enabled")
    for field in ("start_head_sha", "end_head_sha", "start_tree", "end_tree"):
        if not isinstance(checkout.get(field), str) or not checkout[field]:
            raise ContractError(f"launcher V4 checkout identity is invalid: {field}")
    for prefix in (
        "head_sha", "tree", "index_digest", "staged_diff_digest",
        "worktree_digest", "untracked", "noncheckpoint_refs_digest",
    ):
        if checkout[f"start_{prefix}"] != checkout[f"end_{prefix}"]:
            raise ContractError(f"launcher V4 checkout mutated: {prefix}")
    for field in (
        "start_index_digest", "end_index_digest", "start_staged_diff_digest",
        "end_staged_diff_digest", "start_worktree_digest", "end_worktree_digest",
        "start_untracked", "end_untracked", "start_noncheckpoint_refs_digest",
        "end_noncheckpoint_refs_digest",
    ):
        if not isinstance(checkout.get(field), str) or not SHA256.fullmatch(checkout[field]):
            raise ContractError(f"launcher V4 checkout digest is invalid: {field}")
    candidate = receipt["candidate"]
    if not isinstance(candidate, dict) or checkout["start_tree"] != candidate.get("tree_sha"):
        raise ContractError("launcher V4 checkout does not bind the candidate tree")

    checkpoints = receipt.get("provider_checkpoints")
    if not isinstance(checkpoints, dict) or set(checkpoints) != LAUNCHER_V4_PROVIDER_FIELDS:
        raise ContractError("launcher V4 provider checkpoint fields do not match")
    exact = {
        "provider": "conductor",
        "actor_name": "Checkpointer",
        "actor_email": "checkpointer@noreply",
        "ref_namespace": "refs/conductor-checkpoints/",
    }
    for field, value in exact.items():
        if checkpoints.get(field) != value:
            raise ContractError(f"launcher V4 provider checkpoint mismatch: {field}")
    turn_id = checkpoints.get("turn_id")
    if not isinstance(turn_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", turn_id):
        raise ContractError("launcher V4 checkpoint turn ID is invalid")
    turn_prefix = f"refs/conductor-checkpoints/session-{receipt['session_id']}-turn-{turn_id}-"
    if checkpoints["start_ref"] != turn_prefix + "start" or checkpoints["end_ref"] != turn_prefix + "end":
        raise ContractError("launcher V4 checkpoint refs do not bind the session turn")
    for field in ("start_commit", "end_commit"):
        if not isinstance(checkpoints.get(field), str) or not GIT_OBJECT_ID.fullmatch(checkpoints[field]):
            raise ContractError(f"launcher V4 checkpoint commit is invalid: {field}")
    if checkpoints["start_tree"] != checkout["start_tree"] or checkpoints["end_tree"] != checkout["end_tree"]:
        raise ContractError("launcher V4 checkpoint tree does not bind the candidate")
    if not isinstance(checkpoints.get("metadata_digest"), str) or not SHA256.fullmatch(checkpoints["metadata_digest"]):
        raise ContractError("launcher V4 checkpoint metadata digest is invalid")
    try:
        started = datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00"))
        checkpoint_started = datetime.fromisoformat(checkpoints["start_created_at"].replace("Z", "+00:00"))
        checkpoint_ended = datetime.fromisoformat(checkpoints["end_created_at"].replace("Z", "+00:00"))
        ended = datetime.fromisoformat(receipt["ended_at"].replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ContractError("launcher V4 checkpoint chronology is invalid") from exc
    if any(value.tzinfo is None or value.utcoffset() is None for value in (started, checkpoint_started, checkpoint_ended, ended)):
        raise ContractError("launcher V4 checkpoint chronology requires UTC offsets")
    if not started <= checkpoint_started <= checkpoint_ended <= ended:
        raise ContractError("launcher V4 checkpoint chronology is out of bounds")
    if expected and "execution_policy" in expected and policy != expected["execution_policy"]:
        raise ContractError("launcher execution policy mismatch")
    if expected and "provider_checkpoints" in expected and checkpoints != expected["provider_checkpoints"]:
        raise ContractError("launcher provider checkpoint evidence mismatch")


def validate_checker_session_lifecycle(lifecycle: dict[str, Any], launcher: dict[str, Any]) -> None:
    """Bind completed checker child processes to a Launcher V4 host turn."""
    validate_launcher_v4_receipt(launcher, tier="A")
    if not isinstance(lifecycle, dict) or set(lifecycle) != CHECKER_LIFECYCLE_FIELDS:
        raise ContractError("checker lifecycle fields do not match")
    if lifecycle.get("schema_version") != 1:
        raise ContractError("checker lifecycle schema version is invalid")
    for field in ("lifecycle_id", "launch_id", "session_id", "candidate_tree", "command_manifest_locator"):
        if not isinstance(lifecycle.get(field), str) or not lifecycle[field]:
            raise ContractError(f"checker lifecycle field is empty: {field}")
    if not isinstance(lifecycle.get("command_manifest_digest"), str) or not SHA256.fullmatch(lifecycle["command_manifest_digest"]):
        raise ContractError("checker lifecycle command manifest digest is invalid")
    count = lifecycle.get("command_count")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ContractError("checker lifecycle command count is invalid")
    if lifecycle.get("launch_id") != launcher.get("launch_id") or lifecycle.get("session_id") != launcher.get("session_id"):
        raise ContractError("checker lifecycle does not bind the launcher session")
    if lifecycle.get("candidate_tree") != launcher.get("candidate", {}).get("tree_sha"):
        raise ContractError("checker lifecycle does not bind the candidate tree")
    if lifecycle.get("all_required_commands_completed") is not True:
        raise ContractError("checker lifecycle did not complete every required command")
    if lifecycle.get("all_exit_codes_observed") is not True:
        raise ContractError("checker lifecycle lacks observed exit codes")
    if lifecycle.get("child_processes_reaped") is not True:
        raise ContractError("checker lifecycle left child processes unjoined")
    if lifecycle.get("completion_marker") != "checker-session-complete/v1":
        raise ContractError("checker lifecycle completion marker is invalid")
    provider = launcher["provider_checkpoints"]
    try:
        times = [
            datetime.fromisoformat(str(launcher["started_at"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(provider["start_created_at"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(lifecycle["last_command_completed_at"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(lifecycle["monitor_stopped_at"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(provider["end_created_at"]).replace("Z", "+00:00")),
            datetime.fromisoformat(str(launcher["ended_at"]).replace("Z", "+00:00")),
        ]
    except (AttributeError, ValueError) as exc:
        raise ContractError("checker lifecycle chronology is invalid") from exc
    if any(item.tzinfo is None or item.utcoffset() is None for item in times) or times != sorted(times):
        raise ContractError("checker lifecycle chronology is out of bounds")

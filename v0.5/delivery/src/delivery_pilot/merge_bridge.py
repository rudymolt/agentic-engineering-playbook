"""K4.1 process-attested fresh-agent merge bridge.

This module deliberately does not promote the bridge to Tier B.  It separates
the builder/coordinator role from one fresh merge-agent session, binds an exact
candidate and policy, and uses expected-head dispatch.  The shared credential
remains bypassable, which is why every receipt says so explicitly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Protocol

from .canonical import digest
from .authority import validate_approval
from .contracts import CANDIDATE_FIELDS, ContractError, SHA256


MILESTONE = "K4.1"
AUTHORITY_CLASS = "process-attested-fresh-merge"
MERGE_METHODS = {"squash", "merge", "rebase"}
DEFERRED_ENVELOPE_FIELDS = {
    "pr_number", "candidate_head", "candidate_tree", "candidate",
}
REQUIRED_FLAGS = {
    "process_attested_only": True,
    "non_bypass_protection": False,
    "tier_b_authority": False,
    "deploy_authority": False,
    "release_authority": False,
}
PROCESS_MERGE_FIELDS = {
    "schema_version", "receipt_id", "decision_digest", "decision_authorization",
    "repository", "pr_number", "base_ref", "expected_head_sha", "merge_commit_sha",
    "merge_method", "dispatch_mode", "actor", "dispatched_at", "observed_at", "outcome",
    "ambiguous_response_observed", "host_evidence_digest", "host_evidence_locator",
    *REQUIRED_FLAGS,
}


class MergeHost(Protocol):
    """Minimal host adapter; implementations must use expected-head merge."""

    def inspect(self, repository: str, pr_number: int) -> dict[str, Any]: ...

    def merge(
        self,
        repository: str,
        pr_number: int,
        expected_head_sha: str,
        merge_method: str,
        operation_id: str,
    ) -> dict[str, Any]: ...

    def claim_operation(
        self, repository: str, pr_number: int, operation_id: str, decision_digest: str, expected_head_sha: str,
    ) -> bool: ...

    def operation_claimed(self, repository: str, operation_id: str, expected_head_sha: str) -> bool: ...


def _candidate_tuple(candidate: Any, label: str) -> dict[str, Any]:
    if not isinstance(candidate, dict) or any(field not in candidate for field in CANDIDATE_FIELDS):
        raise ContractError(f"{label}: incomplete frozen candidate tuple")
    result = {field: candidate[field] for field in CANDIDATE_FIELDS}
    for field in ("head_sha", "tree_sha", "base_sha", "policy_sha"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(result[field])):
            raise ContractError(f"{label}: invalid {field}")
    for field in ("ruleset_fingerprint", "verification_environment_digest"):
        if not isinstance(result[field], str) or not result[field]:
            raise ContractError(f"{label}: invalid {field}")
    merge_group = result["merge_group_sha"]
    if merge_group is not None and not re.fullmatch(r"[0-9a-f]{40}", str(merge_group)):
        raise ContractError(f"{label}: invalid merge_group_sha")
    return result


def validate_merge_gate(gate: dict[str, Any]) -> None:
    candidate = _candidate_tuple(gate.get("candidate"), "merge-gate")
    if candidate["head_sha"] != gate.get("candidate_head") or candidate["tree_sha"] != gate.get("candidate_tree"):
        raise ContractError("merge-gate: legacy head/tree fields do not bind the frozen candidate")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_bridge_fields(record: dict[str, Any], label: str) -> None:
    expected = {
        "rollout_milestone": MILESTONE,
        "authority_class": AUTHORITY_CLASS,
        "maximum_action": "merge",
    }
    for field, value in expected.items():
        if record.get(field) != value:
            raise ContractError(f"{label}: {field} must be {value}")


def _normalized_path(value: Any, label: str, *, prefix: bool = False) -> str:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        raise ContractError(f"{label} must be a normalized repository-relative path")
    if prefix and not value.endswith("/"):
        raise ContractError(f"{label} must end with /")
    if not prefix and value.endswith("/"):
        raise ContractError(f"{label} must name a file")
    components = (value[:-1] if prefix else value).split("/")
    if any(component in {"", ".", ".."} for component in components):
        raise ContractError(f"{label} must be a normalized repository-relative path")
    return value


def _approved_scope(authority: dict[str, Any], label: str) -> dict[str, Any]:
    risk_class = authority.get("risk_class")
    if not isinstance(risk_class, str) or not risk_class:
        raise ContractError(f"{label} risk_class is required")
    planning_prefix = _normalized_path(authority.get("planning_prefix"), f"{label} planning_prefix", prefix=True)
    implementation_paths = authority.get("implementation_paths")
    if not isinstance(implementation_paths, list) or not implementation_paths:
        raise ContractError(f"{label} implementation_paths must be non-empty")
    normalized = [_normalized_path(path, f"{label} implementation path") for path in implementation_paths]
    if normalized != sorted(set(normalized)):
        raise ContractError(f"{label} implementation_paths must be sorted and unique")
    if any(path.startswith(planning_prefix) for path in normalized):
        raise ContractError(f"{label} implementation_paths cannot use the planning prefix")
    return {
        "risk_class": risk_class,
        "planning_prefix": planning_prefix,
        "implementation_paths": normalized,
    }


def _scope_violation(scope: dict[str, Any], changed_paths: Any, risk_class: Any) -> bool:
    approved = _approved_scope(scope, "approved scope")
    if risk_class != approved["risk_class"]:
        return True
    if not isinstance(changed_paths, list):
        raise ContractError("changed paths must be a list")
    if not changed_paths:
        return True
    try:
        normalized = [_normalized_path(path, "changed path") for path in changed_paths]
    except ContractError:
        return True
    if normalized != sorted(set(normalized)):
        return True
    implementation = sorted(path for path in normalized if not path.startswith(approved["planning_prefix"]))
    return implementation != approved["implementation_paths"]


def _changed_paths_are_normalized(changed_paths: Any) -> bool:
    if not isinstance(changed_paths, list):
        raise ContractError("changed paths must be a list")
    if not changed_paths:
        return False
    try:
        normalized = [_normalized_path(path, "changed path") for path in changed_paths]
    except ContractError:
        return False
    return normalized == sorted(set(normalized))


def validate_k41_envelope(envelope: dict[str, Any]) -> None:
    """Public K4.1 envelope validation shared with the bridge consumer."""

    _require_bridge_fields(envelope, "envelope")
    authority = envelope.get("authority", {})
    expected = {
        "maximum": "merge",
        "builder_maximum": "open-pr",
        "coordinator_maximum": "open-pr",
        "fresh_merge_agent_maximum": "merge",
        "tier_b_authority": False,
        "non_bypass_protection": False,
        "deploy_authority": False,
        "release_authority": False,
        "repository": None,
        "project": None,
        "mission_id": None,
        "base_ref": None,
        "merge_method": None,
        "candidate_binding": "post-freeze",
        "pr_binding": "post-pr",
    }
    for field, value in expected.items():
        if value is not None and authority.get(field) != value:
            raise ContractError(f"envelope authority {field} must be {value}")
    if not re.fullmatch(r"[^/]+/[^/]+", str(authority.get("repository", ""))):
        raise ContractError("envelope authority repository must be owner/name")
    if not isinstance(authority.get("project"), str) or not authority["project"]:
        raise ContractError("envelope authority project is required")
    if not isinstance(authority.get("mission_id"), str) or not authority["mission_id"]:
        raise ContractError("envelope authority mission_id is required")
    if not isinstance(authority.get("base_ref"), str) or not authority["base_ref"]:
        raise ContractError("envelope authority base_ref is required")
    present_deferred = sorted(DEFERRED_ENVELOPE_FIELDS.intersection(authority))
    if present_deferred:
        raise ContractError(f"envelope authority defers post-freeze fields: {present_deferred}")
    scope = _approved_scope(authority, "envelope authority")
    feature_slug = envelope.get("feature", {}).get("slug")
    if scope["planning_prefix"] != f"planning/{feature_slug}/":
        raise ContractError("envelope authority planning_prefix must bind the feature slug")
    if authority.get("merge_method") not in MERGE_METHODS:
        raise ContractError("envelope authority merge_method is unsupported")
    merge = authority.get("merge", {})
    if merge.get("target") != authority["base_ref"] or merge.get("method") != authority["merge_method"]:
        raise ContractError("envelope authority merge target/method is inconsistent")


def validate_bridge_authority_chain(
    envelope: dict[str, Any],
    approval: dict[str, Any],
    attempt: dict[str, Any],
    gate: dict[str, Any],
    handback: dict[str, Any],
) -> None:
    """Bind K4.1 across all authority-bearing records without widening Tier A."""

    for label, record in (
        ("envelope", envelope),
        ("approval", approval),
        ("attempt", attempt),
        ("gate", gate),
        ("handback", handback),
    ):
        _require_bridge_fields(record, label)
    validate_k41_envelope(envelope)
    validate_approval(envelope, approval)
    if attempt.get("tier") != "A":
        raise ContractError("K4.1 accepts only a Tier A attempt")
    envelope_digest = digest(envelope)
    if approval.get("envelope_digest") != envelope_digest or attempt.get("envelope_digest") != envelope_digest:
        raise ContractError("approval and attempt must bind the exact K4.1 envelope")
    envelope_authority = envelope["authority"]
    if (
        envelope_authority["mission_id"] != attempt.get("mission_id")
        or gate.get("mission_id") != attempt.get("mission_id")
        or handback.get("mission_id") != attempt.get("mission_id")
    ):
        raise ContractError("gate and handback must bind the attempt mission")
    validate_merge_gate(gate)
    gate_candidate = _candidate_tuple(gate.get("candidate"), "merge-gate")
    if gate_candidate != _candidate_tuple(handback.get("candidate"), "handback"):
        raise ContractError("gate and handback frozen candidate tuples differ")
    if envelope_authority["base_ref"] != gate.get("base_ref"):
        raise ContractError("envelope and merge gate base differ")
    if attempt.get("project") != envelope_authority["project"]:
        raise ContractError("attempt project does not bind the envelope project")
    if not re.fullmatch(r"github:pr/[1-9][0-9]*", str(handback.get("pr_ref", ""))):
        raise ContractError("handback PR must bind a positive post-freeze PR")
    if gate.get("g1_g8") != "pass" or any(
        gate.get(field) != 0 for field in ("open_findings", "open_review_threads", "required_actions")
    ):
        raise ContractError("K4.1 requires passing G1-G8 and no open work")
    if gate.get("taste_interrupt_open") is not False or gate.get("safety_interrupt_open") is not False:
        raise ContractError("K4.1 cannot proceed with an open taste or safety interrupt")
    if handback.get("open_action_count") != 0:
        raise ContractError("K4.1 handback has open actions")


def classify_paths(policy: dict[str, Any], changed_paths: list[str], risk_class: str) -> list[str]:
    """Return protected matches using only policy read from the default branch."""

    policy_fields = {
        "allowed_risk_classes", "authority_class", "human_merge_path_prefixes",
        "human_merge_path_names", "human_merge_path_name_prefixes", "policy_version", "source_branch",
    }
    if not isinstance(policy, dict) or set(policy) != policy_fields:
        raise ContractError("K4.1 default-branch policy fields are incomplete")
    if (
        policy.get("policy_version") != 1
        or policy.get("authority_class") != AUTHORITY_CLASS
        or policy.get("source_branch") != "default-branch-only"
    ):
        raise ContractError("unsupported K4.1 default-branch policy")
    allowed = policy.get("allowed_risk_classes")
    if not isinstance(risk_class, str) or not risk_class:
        raise ContractError("K4.1 risk class must be non-empty")
    if not isinstance(allowed, list) or not allowed or any(not isinstance(item, str) or not item for item in allowed):
        raise ContractError("K4.1 policy requires allowed risk classes")
    if risk_class not in allowed:
        return [f"risk:{risk_class}"]
    prefixes = policy.get("human_merge_path_prefixes")
    if not isinstance(prefixes, list) or not prefixes or any(not isinstance(item, str) or not item for item in prefixes):
        raise ContractError("K4.1 policy requires human-merge path prefixes")
    names = policy.get("human_merge_path_names")
    if not isinstance(names, list) or not names or any(not isinstance(item, str) or not item or "/" in item for item in names):
        raise ContractError("K4.1 policy requires human-merge instruction names")
    name_prefixes = policy.get("human_merge_path_name_prefixes")
    if not isinstance(name_prefixes, list) or not name_prefixes or any(
        not isinstance(item, str) or not item or "/" in item or "." in item for item in name_prefixes
    ):
        raise ContractError("K4.1 policy requires human-merge instruction-name prefixes")
    matches: list[str] = []
    for path in changed_paths:
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
            raise ContractError("changed paths must be normalized repository-relative paths")
        path_parts = path.split("/")
        for prefix in prefixes:
            prefix_parts = prefix.rstrip("/").split("/")
            if any(path_parts[index:index + len(prefix_parts)] == prefix_parts for index in range(len(path_parts))):
                matches.append(path)
                break
        basename = path.rsplit("/", 1)[-1]
        if basename in names or any(basename.startswith(prefix + ".") for prefix in name_prefixes):
            matches.append(path)
    return sorted(set(matches))


def validate_merge_decision(record: dict[str, Any]) -> None:
    _require_bridge_fields({**record, "maximum_action": "merge"}, "merge-decision")
    for field, expected in REQUIRED_FLAGS.items():
        if record.get(field) is not expected:
            raise ContractError(f"merge-decision: {field} must be {expected}")
    if record.get("merge_method") not in MERGE_METHODS:
        raise ContractError("merge-decision: unsupported merge method")
    for field in ("expected_head_sha", "expected_tree_sha", "control_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", str(record.get(field, ""))):
            raise ContractError(f"merge-decision: invalid {field}")
    expected_candidate = _candidate_tuple(record.get("expected_candidate"), "merge-decision")
    if (
        expected_candidate["head_sha"] != record.get("expected_head_sha")
        or expected_candidate["tree_sha"] != record.get("expected_tree_sha")
    ):
        raise ContractError("merge-decision: head/tree fields do not bind the frozen candidate")
    if record.get("decision") not in {"allow", "deny"}:
        raise ContractError("merge-decision: unsupported decision")
    for field in (
        "policy_digest", "standing_authority_digest", "envelope_digest", "approval_digest", "attempt_digest",
        "handback_digest", "gate_digest", "launcher_digest", "control_digest",
    ):
        if not SHA256.fullmatch(str(record.get(field, ""))):
            raise ContractError(f"merge-decision: invalid {field}")
    verification = record.get("verification_digests")
    if not isinstance(verification, list) or not verification or any(
        not SHA256.fullmatch(str(item)) for item in verification
    ):
        raise ContractError("merge-decision: verification digests must be non-empty SHA-256 values")
    if not isinstance(record.get("controller_generation"), int) or isinstance(record["controller_generation"], bool) or record["controller_generation"] < 1:
        raise ContractError("merge-decision: controller generation must be positive")
    if record.get("control_ref") != f"refs/heads/delivery-control/{record.get('mission_id')}":
        raise ContractError("merge-decision: control ref does not bind the mission")
    if not isinstance(record.get("evidence_locators"), list) or not record["evidence_locators"]:
        raise ContractError("merge-decision: durable evidence locators are required")
    agent = record.get("agent")
    required_agent_fields = {"role", "session_id", "family", "model", "effort", "fresh_context", "builder_separation"}
    if not isinstance(agent, dict) or set(agent) != required_agent_fields:
        raise ContractError("merge-decision: incomplete agent provenance")
    if agent["role"] != "fresh-merge-agent" or agent["fresh_context"] is not True:
        raise ContractError("merge-decision: only a fresh merge agent may decide")
    if agent["builder_separation"] != "live-controller-session-different":
        raise ContractError("merge-decision: builder separation is not host-attested")
    if any(not isinstance(agent[field], str) or not agent[field] for field in ("session_id", "family", "model", "effort")):
        raise ContractError("merge-decision: agent provenance strings must be non-empty")
    protected = record.get("protected_path_matches")
    if not isinstance(protected, list):
        raise ContractError("merge-decision: protected_path_matches must be a list")
    risk_policy = record.get("risk_policy")
    if not isinstance(risk_policy, dict) or digest(risk_policy) != record.get("policy_digest"):
        raise ContractError("merge-decision: embedded risk policy does not bind policy digest")
    changed_paths = record.get("changed_paths")
    paths_are_normalized = _changed_paths_are_normalized(changed_paths)
    computed_protected = classify_paths(
        risk_policy, changed_paths if paths_are_normalized else [], record.get("risk_class"),
    )
    if protected != computed_protected:
        raise ContractError("merge-decision: protected path classification mismatch")
    approved_scope = record.get("approved_scope")
    if not isinstance(approved_scope, dict) or set(approved_scope) != {
        "risk_class", "planning_prefix", "implementation_paths",
    }:
        raise ContractError("merge-decision: approved scope is incomplete")
    scope_violation = _scope_violation(approved_scope, record.get("changed_paths"), record.get("risk_class"))
    reasons = record.get("reason_codes")
    if not isinstance(reasons, list) or not reasons or any(not isinstance(reason, str) or not reason for reason in reasons):
        raise ContractError("merge-decision: reason codes must be non-empty strings")
    scope_reason_present = "scope-outside-approved-paths" in reasons
    if scope_violation != scope_reason_present:
        raise ContractError("merge-decision: approved scope classification mismatch")
    if record["decision"] == "allow" and protected:
        raise ContractError("merge-decision: protected paths require human merge")
    if record["decision"] == "allow" and scope_violation:
        raise ContractError("merge-decision: candidate exceeds approved scope")
    if record["decision"] == "allow" and record.get("reason_codes") != ["all-controls-pass"]:
        raise ContractError("merge-decision: allow requires the canonical reason code")
    if record["decision"] == "deny" and not reasons:
        raise ContractError("merge-decision: deny requires reason codes")


def validate_merge_decision_attestation(attestation: dict[str, Any], decision: dict[str, Any]) -> None:
    """Require an exact durable readback of the decision before dispatch."""

    decision_digest = digest(decision)
    if attestation.get("decision_digest") != decision_digest:
        raise ContractError("merge-decision-attestation: decision digest mismatch")
    if attestation.get("readback_digest") != decision_digest:
        raise ContractError("merge-decision-attestation: durable readback digest mismatch")
    if attestation.get("session_id") != decision.get("agent", {}).get("session_id"):
        raise ContractError("merge-decision-attestation: session mismatch")
    if not str(attestation.get("source_event_id", "")).startswith("github:issue-comment:"):
        raise ContractError("merge-decision-attestation: unsupported durable source")
    try:
        issued_at = datetime.fromisoformat(str(decision.get("issued_at", "")).replace("Z", "+00:00"))
        attested_at = datetime.fromisoformat(str(attestation.get("attested_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("merge-decision-attestation: invalid chronology") from exc
    if issued_at.tzinfo is None or issued_at.utcoffset() is None or attested_at.tzinfo is None or attested_at.utcoffset() is None:
        raise ContractError("merge-decision-attestation: chronology requires UTC offsets")
    if attested_at < issued_at:
        raise ContractError("merge-decision-attestation: readback predates decision")


def issue_merge_decision(
    *,
    envelope: dict[str, Any],
    approval: dict[str, Any],
    attempt: dict[str, Any],
    gate: dict[str, Any],
    handback: dict[str, Any],
    launcher: dict[str, Any],
    policy: dict[str, Any],
    standing_authority: dict[str, Any],
    facts: dict[str, Any],
    issued_at: str,
) -> dict[str, Any]:
    """Create a deterministic allow/deny decision from independently observed facts."""

    validate_bridge_authority_chain(envelope, approval, attempt, gate, handback)
    _require_bridge_fields(standing_authority, "standing-authority")
    for field, expected_flag in REQUIRED_FLAGS.items():
        if standing_authority.get(field) is not expected_flag:
            raise ContractError(f"standing-authority: {field} must be {expected_flag}")
    if standing_authority.get("enabled") is not True:
        raise ContractError("standing-authority: lane is disabled")
    if standing_authority.get("repository") != facts.get("repository"):
        raise ContractError("standing-authority: repository mismatch")
    envelope_authority = envelope.get("authority", {})
    if standing_authority.get("project") != envelope_authority.get("project"):
        raise ContractError("standing-authority: project mismatch")
    if envelope_authority.get("repository") != facts.get("repository"):
        raise ContractError("envelope authority: repository mismatch")
    handback_match = re.fullmatch(r"github:pr/([1-9][0-9]*)", str(handback.get("pr_ref", "")))
    if handback_match is None or int(handback_match.group(1)) != facts.get("pr_number"):
        raise ContractError("handback PR does not bind the observed PR")
    if gate.get("base_ref") != standing_authority.get("default_branch"):
        raise ContractError("standing-authority: gate base is not the approved default branch")
    if envelope.get("authority", {}).get("merge", {}).get("target") != standing_authority.get("default_branch"):
        raise ContractError("standing-authority: envelope merge target is not the approved default branch")
    if standing_authority.get("policy_digest") != digest(policy):
        raise ContractError("standing-authority: policy digest mismatch")
    if gate.get("policy_digest") != digest(policy):
        raise ContractError("merge-gate: policy digest mismatch")
    if standing_authority.get("implementation_digest") != facts.get("implementation_digest"):
        raise ContractError("standing-authority: implementation digest mismatch")
    if standing_authority.get("kill_generation") != facts.get("kill_generation"):
        raise ContractError("standing-authority: kill generation mismatch")
    if launcher.get("envelope_digest") != digest(envelope):
        raise ContractError("launcher: envelope digest mismatch")
    if launcher.get("spec_digest") != standing_authority.get("spec_digest"):
        raise ContractError("launcher: implementation spec digest mismatch")
    if launcher.get("prompt_digest") != standing_authority.get("prompt_digest"):
        raise ContractError("launcher: fixed merge prompt digest mismatch")
    gate_candidate = _candidate_tuple(gate.get("candidate"), "merge-gate")
    launcher_candidate = _candidate_tuple(launcher.get("candidate"), "launcher")
    if launcher_candidate != gate_candidate:
        raise ContractError("launcher: candidate tuple mismatch")
    checkout = launcher.get("checkout", {})
    if checkout.get("start_tree") != gate.get("candidate_tree") or checkout.get("end_tree") != gate.get("candidate_tree"):
        raise ContractError("launcher: checkout tree does not bind the candidate")
    for field in ("start_head_sha", "end_head_sha"):
        if field in checkout and checkout[field] != gate.get("candidate_head"):
            raise ContractError("launcher: checkout head does not bind the candidate")
    try:
        decision_time = datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
        approved = datetime.fromisoformat(str(standing_authority["approved_at"]).replace("Z", "+00:00"))
        expiry = datetime.fromisoformat(str(standing_authority["expires_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ContractError("standing-authority: invalid expiry") from exc
    if decision_time < approved:
        raise ContractError("standing-authority: decision predates approval")
    if decision_time > expiry:
        raise ContractError("standing-authority: expired")
    chronology = (
        ("approval", approval.get("approved_at")),
        ("attempt", attempt.get("registered_at")),
        ("gate", gate.get("issued_at")),
        ("handback", handback.get("issued_at")),
        ("launcher start", launcher.get("started_at")),
        ("launcher end", launcher.get("ended_at")),
        ("decision", issued_at),
    )
    try:
        chronology_times = [datetime.fromisoformat(str(value).replace("Z", "+00:00")) for _, value in chronology]
    except ValueError as exc:
        raise ContractError("K4.1 authority chronology contains an invalid timestamp") from exc
    if any(current > following for current, following in zip(chronology_times, chronology_times[1:])):
        raise ContractError("K4.1 authority chronology is out of order")
    changed_paths = facts.get("changed_paths", [])
    risk_class = facts.get("risk_class", "unknown")
    paths_are_normalized = _changed_paths_are_normalized(changed_paths)
    protected = classify_paths(policy, changed_paths if paths_are_normalized else [], risk_class)
    approved_scope = _approved_scope(envelope_authority, "envelope authority")
    scope_violation = _scope_violation(approved_scope, changed_paths, risk_class)
    expected = {
        "repository": facts.get("repository"),
        "pr_number": facts.get("pr_number"),
        "base_ref": gate.get("base_ref"),
        "head_sha": gate.get("candidate_head"),
        "tree_sha": gate.get("candidate_tree"),
        "candidate": gate_candidate,
        "merge_method": envelope.get("authority", {}).get("merge", {}).get("method"),
    }
    host = facts.get("host", {})
    reasons: list[str] = []
    for field, value in expected.items():
        if host.get(field) != value:
            reasons.append(f"host-{field}-mismatch")
    if host.get("default_branch") != standing_authority.get("default_branch"):
        reasons.append("host-default-branch-mismatch")
    if host.get("default_branch_policy_digest") != digest(policy):
        reasons.append("host-default-branch-policy-mismatch")
    required_true = (
        "pr_open", "mergeable", "checks_pass", "verification_pass", "checkout_clean",
        "evidence_resolved", "review_threads_closed", "reviews_clear", "findings_closed", "required_actions_closed",
        "standing_authority_current", "default_branch_policy_current", "kill_switch_enabled", "generation_current",
    )
    reasons.extend(field.replace("_", "-") for field in required_true if facts.get(field) is not True)
    if protected:
        reasons.append("human-merge-required")
    if scope_violation:
        reasons.append("scope-outside-approved-paths")
    runtime = launcher.get("runtime", {})
    requested = launcher.get("requested", {})
    runtime_fields = ("family", "model", "effort", "role")
    if requested != runtime or any(not isinstance(runtime.get(field), str) or not runtime[field] for field in runtime_fields):
        raise ContractError("launcher: fresh merge-agent runtime identity is incomplete")
    if runtime.get("role") != "fresh-merge-agent":
        raise ContractError("launcher: role must be fresh-merge-agent")
    builder_session_ids = facts.get("builder_session_ids")
    coordinator_session_id = facts.get("coordinator_session_id")
    if not isinstance(builder_session_ids, list) or not builder_session_ids or any(
        not isinstance(item, str) or not item for item in builder_session_ids
    ):
        raise ContractError("facts: host-observed builder session IDs are required")
    if not isinstance(coordinator_session_id, str) or not coordinator_session_id:
        raise ContractError("facts: host-observed coordinator session ID is required")
    agent = {
        "role": "fresh-merge-agent",
        "session_id": launcher.get("session_id"),
        "family": runtime["family"],
        "model": runtime["model"],
        "effort": runtime["effort"],
        "fresh_context": launcher.get("parent_context") is False,
        "builder_separation": "live-controller-session-different",
    }
    if agent["session_id"] in builder_session_ids:
        reasons.append("builder-self-merge")
    if agent["session_id"] == coordinator_session_id:
        reasons.append("coordinator-self-merge")
    decision = "deny" if reasons else "allow"
    record = {
        "schema_version": 1,
        "decision_id": "merge-decision-" + digest({"mission": attempt["mission_id"], "host": host, "facts": facts}).split(":", 1)[1][:24],
        "mission_id": attempt["mission_id"],
        "rollout_milestone": MILESTONE,
        "authority_class": AUTHORITY_CLASS,
        "repository": expected["repository"],
        "pr_number": expected["pr_number"],
        "base_ref": expected["base_ref"],
        "expected_head_sha": expected["head_sha"],
        "expected_tree_sha": expected["tree_sha"],
        "expected_candidate": expected["candidate"],
        "merge_method": expected["merge_method"],
        "policy_digest": digest(policy),
        "risk_policy": policy,
        "standing_authority_digest": digest(standing_authority),
        "envelope_digest": digest(envelope),
        "approval_digest": digest(approval),
        "attempt_digest": digest(attempt),
        "handback_digest": digest(handback),
        "gate_digest": digest(gate),
        "launcher_digest": digest(launcher),
        "verification_digests": list(facts.get("verification_digests", [])),
        "risk_class": risk_class,
        "approved_scope": approved_scope,
        "changed_paths": list(changed_paths),
        "protected_path_matches": protected,
        "controller_generation": facts.get("controller_generation"),
        "control_ref": facts.get("control_ref"),
        "control_commit": facts.get("control_commit"),
        "control_digest": facts.get("control_digest"),
        "agent": agent,
        "decision": decision,
        "reason_codes": sorted(set(reasons)) if reasons else ["all-controls-pass"],
        **REQUIRED_FLAGS,
        "issued_at": issued_at,
        "evidence_locators": list(facts.get("evidence_locators", [])),
    }
    validate_merge_decision(record)
    return record


def _host_matches_decision(host: dict[str, Any], decision: dict[str, Any]) -> bool:
    return (
        host.get("repository") == decision["repository"]
        and host.get("pr_number") == decision["pr_number"]
        and host.get("base_ref") == decision["base_ref"]
        and host.get("default_branch") == decision["base_ref"]
        and host.get("head_sha") == decision["expected_head_sha"]
        and host.get("tree_sha") == decision["expected_tree_sha"]
        and host.get("candidate") == decision["expected_candidate"]
        and host.get("merge_method") == decision["merge_method"]
        and host.get("changed_paths") == decision["changed_paths"]
        and host.get("controller_generation") == decision["controller_generation"]
        and host.get("control_ref") == decision["control_ref"]
        and host.get("control_commit") == decision["control_commit"]
        and host.get("control_digest") == decision["control_digest"]
        and host.get("standing_authority_digest") == decision["standing_authority_digest"]
        and host.get("default_branch_policy_digest") == decision["policy_digest"]
    )


def dispatch_merge(
    decision: dict[str, Any], host_adapter: MergeHost, current_session_id: str | None,
) -> dict[str, Any]:
    """Expected-head merge with mandatory observe-before-dispatch/retry behavior."""

    validate_merge_decision(decision)
    if decision["decision"] != "allow":
        raise ContractError("a denied decision cannot dispatch merge")
    if current_session_id != decision["agent"]["session_id"]:
        raise ContractError("only the deciding fresh-agent session may dispatch merge")
    operation_id = "op-merge-" + digest(decision).split(":", 1)[1]
    before = host_adapter.inspect(decision["repository"], decision["pr_number"])
    if not _host_matches_decision(before, decision):
        raise ContractError("dispatch-time PR tuple differs from merge decision")
    if before.get("merged") is True:
        if not host_adapter.operation_claimed(
            decision["repository"], operation_id, decision["expected_head_sha"],
        ):
            raise ContractError("PR was already merged without this K4.1 operation claim")
        operation_claimed = False
    else:
        if before.get("mergeable") is not True or before.get("checks_pass") is not True:
            raise ContractError("dispatch-time host gates do not pass")
        for field in ("pr_open", "review_threads_closed", "reviews_clear", "standing_authority_current", "default_branch_policy_current", "kill_switch_enabled", "generation_current"):
            if before.get(field) is not True:
                raise ContractError(f"dispatch-time {field} does not pass")
        operation_claimed = host_adapter.claim_operation(
            decision["repository"], decision["pr_number"], operation_id, digest(decision), decision["expected_head_sha"],
        )
    dispatched_at = _utc_now()
    ambiguous = not operation_claimed
    dispatch_succeeded = False
    dispatch_evidence: dict[str, Any]
    if operation_claimed:
        try:
            response = host_adapter.merge(
                decision["repository"], decision["pr_number"], decision["expected_head_sha"],
                decision["merge_method"], operation_id,
            )
            dispatch_succeeded = True
            dispatch_evidence = {"status": "succeeded", "response": response}
        except TimeoutError:
            ambiguous = True
            dispatch_evidence = {"status": "timeout"}
        except Exception as exc:
            ambiguous = True
            dispatch_evidence = {"status": "failed", "error_type": type(exc).__name__}
    else:
        dispatch_evidence = {"status": "previously-claimed-observe-only"}
    observed: dict[str, Any] = {}
    observation_errors: list[str] = []
    for _ in range(3):
        try:
            observed = host_adapter.inspect(decision["repository"], decision["pr_number"])
        except Exception as exc:
            observation_errors.append(type(exc).__name__)
            continue
        if observed.get("merged") is True:
            break
    if not observed or observed.get("merged") is not True:
        ambiguous = True
        observed = {
            **observed,
            "merged": False,
            "host_evidence": {
                "status": "observation-not-authoritative",
                "error_types": observation_errors,
                "last_observation": observed.get("host_evidence", observed),
            },
            "evidence_locator": observed.get(
                "evidence_locator", f"github:{decision['repository']}/pull/{decision['pr_number']}",
            ),
        }
    observed_at = _utc_now()
    observed_expected_merge = (
        observed.get("merged") is True
        and observed.get("merged_head_sha") == decision["expected_head_sha"]
        and re.fullmatch(r"[0-9a-f]{40}", str(observed.get("merge_commit_sha", ""))) is not None
    )
    if dispatch_succeeded and not observed_expected_merge:
        ambiguous = True
    # An observe-only retry cannot know whether the prior endpoint call
    # succeeded or an external actor merged the same head. Preserve the host
    # observation as evidence, but never attribute that merge to this agent.
    merged = dispatch_succeeded and observed_expected_merge
    outcome = "merged" if merged else ("ambiguous" if ambiguous or observed_expected_merge else "denied")
    evidence = {"dispatch": dispatch_evidence, "observation": observed.get("host_evidence", observed)}
    receipt = {
        "schema_version": 1,
        "receipt_id": "merge-receipt-" + digest({"operation": operation_id, "observed": observed}).split(":", 1)[1][:24],
        "decision_digest": digest(decision),
        "decision_authorization": "allow",
        "repository": decision["repository"],
        "pr_number": decision["pr_number"],
        "base_ref": decision["base_ref"],
        "expected_head_sha": decision["expected_head_sha"],
        "merge_commit_sha": observed.get("merge_commit_sha") if merged else None,
        "merge_method": decision["merge_method"],
        "dispatch_mode": "dispatched" if operation_claimed else "reconcile-only",
        "actor": "fresh-merge-agent:" + decision["agent"]["session_id"],
        "dispatched_at": dispatched_at,
        "observed_at": observed_at,
        "outcome": outcome,
        "ambiguous_response_observed": ambiguous,
        "host_evidence_digest": digest(evidence),
        "host_evidence_locator": observed.get("evidence_locator", f"github:{decision['repository']}/pull/{decision['pr_number']}"),
        **REQUIRED_FLAGS,
    }
    validate_process_attested_merge(receipt, decision)
    return receipt


def validate_process_attested_merge(receipt: dict[str, Any], decision: dict[str, Any]) -> None:
    validate_merge_decision(decision)
    if not isinstance(receipt, dict) or set(receipt) != PROCESS_MERGE_FIELDS:
        raise ContractError("process-attested-merge: receipt fields are incomplete")
    if receipt.get("schema_version") != 1 or not isinstance(receipt.get("receipt_id"), str) or not receipt["receipt_id"]:
        raise ContractError("process-attested-merge: invalid receipt identity")
    if not SHA256.fullmatch(str(receipt.get("host_evidence_digest", ""))):
        raise ContractError("process-attested-merge: invalid host evidence digest")
    if not isinstance(receipt.get("host_evidence_locator"), str) or not receipt["host_evidence_locator"]:
        raise ContractError("process-attested-merge: host evidence locator is required")
    if not isinstance(receipt.get("pr_number"), int) or isinstance(receipt["pr_number"], bool) or receipt["pr_number"] < 1:
        raise ContractError("process-attested-merge: PR number must be positive")
    if receipt.get("outcome") not in {"merged", "denied", "ambiguous"}:
        raise ContractError("process-attested-merge: invalid outcome")
    if not isinstance(receipt.get("ambiguous_response_observed"), bool):
        raise ContractError("process-attested-merge: ambiguity flag must be boolean")
    try:
        dispatched_at = datetime.fromisoformat(str(receipt.get("dispatched_at", "")).replace("Z", "+00:00"))
        observed_at = datetime.fromisoformat(str(receipt.get("observed_at", "")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError("process-attested-merge: invalid chronology") from exc
    if (
        dispatched_at.tzinfo is None or dispatched_at.utcoffset() is None
        or observed_at.tzinfo is None or observed_at.utcoffset() is None
        or observed_at < dispatched_at
    ):
        raise ContractError("process-attested-merge: invalid chronology")
    for field, expected in REQUIRED_FLAGS.items():
        if receipt.get(field) is not expected:
            raise ContractError(f"process-attested-merge: {field} must be {expected}")
    if receipt.get("decision_digest") != digest(decision):
        raise ContractError("process-attested-merge does not bind the decision")
    if receipt.get("decision_authorization") != "allow" or decision.get("decision") != "allow":
        raise ContractError("process-attested-merge: only an allow decision can produce a receipt")
    for field in ("repository", "pr_number", "base_ref", "merge_method"):
        if receipt.get(field) != decision.get(field):
            raise ContractError(f"process-attested-merge: {field} mismatch")
    if receipt.get("expected_head_sha") != decision.get("expected_head_sha"):
        raise ContractError("process-attested-merge: expected head mismatch")
    if receipt.get("dispatch_mode") not in {"dispatched", "reconcile-only"}:
        raise ContractError("process-attested-merge: invalid dispatch mode")
    if receipt.get("dispatch_mode") == "reconcile-only" and receipt.get("outcome") != "ambiguous":
        raise ContractError("process-attested-merge: reconciliation must remain ambiguous")
    if receipt.get("dispatch_mode") == "reconcile-only" and receipt.get("ambiguous_response_observed") is not True:
        raise ContractError("process-attested-merge: reconciliation must record ambiguity")
    if (receipt.get("outcome") == "ambiguous") != (receipt.get("ambiguous_response_observed") is True):
        raise ContractError("process-attested-merge: outcome and ambiguity flag disagree")
    if receipt.get("actor") != "fresh-merge-agent:" + decision["agent"]["session_id"]:
        raise ContractError("process-attested-merge: actor does not bind the fresh merge session")
    if receipt.get("outcome") == "merged" and not receipt.get("merge_commit_sha"):
        raise ContractError("process-attested-merge: merged outcome lacks merge commit")
    if receipt.get("merge_commit_sha") is not None and not re.fullmatch(r"[0-9a-f]{40}", str(receipt["merge_commit_sha"])):
        raise ContractError("process-attested-merge: invalid merge commit SHA")
    if receipt.get("outcome") == "ambiguous" and receipt.get("merge_commit_sha") is not None:
        raise ContractError("process-attested-merge: ambiguous outcome cannot claim a merge commit")
    if receipt.get("outcome") == "denied" and receipt.get("merge_commit_sha") is not None:
        raise ContractError("process-attested-merge: denied outcome cannot claim a merge commit")

"""Pilot attempt registration, qualifying metrics, and Tier A handback."""

from __future__ import annotations

from typing import Any

from .canonical import digest
from .contracts import ContractError


CORE_METRICS = {
    "attempt_id", "mission_id", "outcome_id", "phase_timestamps",
    "active_seconds_total", "active_seconds_by_phase", "parked_seconds",
    "queue_seconds", "setup_seconds", "resume_seconds", "planned_taste_minutes",
    "planned_safety_minutes", "unplanned_human_rescue_minutes",
    "chat_reconstruction_required", "checker_launches", "checker_rungs",
    "fix_cycles", "findings", "ci_runs", "ci_minutes", "operation_retries",
    "operation_ambiguities", "operation_duplicates", "cloud_admission_seconds",
    "cloud_candidate_seconds", "cloud_cr_reuse", "cloud_cr_reruns",
    "workspace_count", "workspace_sleeps", "archive_latency_seconds",
    "post_merge_defects", "outstanding_terminal_residue",
}


def register_attempt(
    attempt_id: str,
    mission_id: str,
    feature: str,
    project: str,
    tier: str,
    venue: str,
    envelope_digest: str,
    observation_contract_ref: str,
    observation_contract_digest: str,
    test_manifest_digest: str,
    registered_at: str,
    rollout_milestone: str | None = None,
    authority_class: str | None = None,
    maximum_action: str | None = None,
) -> dict[str, Any]:
    if tier not in {"A", "B", "C"}:
        raise ContractError("unknown attempt tier")
    receipt = {
        "schema_version": 3,
        "attempt_id": attempt_id,
        "mission_id": mission_id,
        "feature": feature,
        "project": project,
        "tier": tier,
        "venue": venue,
        "envelope_digest": envelope_digest,
        "observation_contract_ref": observation_contract_ref,
        "observation_contract_digest": observation_contract_digest,
        "test_manifest_digest": test_manifest_digest,
        "registered_at": registered_at,
    }
    bridge = {
        "rollout_milestone": rollout_milestone,
        "authority_class": authority_class,
        "maximum_action": maximum_action,
    }
    if any(value is not None for value in bridge.values()):
        if any(value is None for value in bridge.values()):
            raise ContractError("K4.1 attempt authority fields must appear together")
        receipt.update(bridge)
    return receipt


def validate_core_metrics(metrics: dict[str, Any], venue: str) -> None:
    missing = CORE_METRICS - set(metrics)
    if missing:
        raise ContractError(f"missing core metrics: {sorted(missing)}")
    universally_non_null = CORE_METRICS - {
        "cloud_admission_seconds", "cloud_candidate_seconds", "archive_latency_seconds"
    }
    nulls = sorted(field for field in universally_non_null if metrics.get(field) is None)
    if nulls:
        raise ContractError(f"applicable core metrics are null: {nulls}")
    if venue == "cloud" and any(metrics.get(field) is None for field in ("cloud_admission_seconds", "cloud_candidate_seconds")):
        raise ContractError("Cloud attempt is missing readiness timing")
    if metrics["chat_reconstruction_required"] is not False:
        raise ContractError("chat reconstruction makes the attempt nonqualifying")
    if metrics["unplanned_human_rescue_minutes"] > 10:
        raise ContractError("unplanned human rescue threshold exceeded")


def issue_handback(
    *,
    mission_id: str,
    candidate: dict[str, Any],
    pr_ref: str,
    attestation_refs: list[str],
    owner_id: str,
    workspace_disposition: str,
    issue_ref: str,
    issued_at: str,
    open_findings: list[dict[str, Any]],
    required_actions: list[str],
    metrics: dict[str, Any],
    rollout_milestone: str | None = None,
    authority_class: str | None = None,
    maximum_action: str | None = None,
) -> dict[str, Any]:
    validate_core_metrics(metrics, venue="cloud" if metrics.get("cloud_candidate_seconds") is not None else "local")
    if open_findings:
        raise ContractError("handback blocked by open findings")
    if required_actions:
        raise ContractError("handback blocked by required actions")
    if len(attestation_refs) < 2:
        raise ContractError("handback requires final-check and QA attestations")
    if not candidate.get("head_sha") or not pr_ref or not owner_id:
        raise ContractError("handback lacks candidate, PR, or owner")
    handback_id = "handback-" + digest({"mission_id": mission_id, "candidate": candidate, "pr_ref": pr_ref}).split(":", 1)[1][:24]
    receipt = {
        "schema_version": 1,
        "handback_id": handback_id,
        "mission_id": mission_id,
        "candidate": candidate,
        "pr_ref": pr_ref,
        "attestation_refs": attestation_refs,
        "open_action_count": 0,
        "owner_id": owner_id,
        "workspace_disposition": workspace_disposition,
        "issue_ref": issue_ref,
        "issued_at": issued_at,
        "issuer": "delivery-pilot/process-attested",
    }
    bridge = {
        "rollout_milestone": rollout_milestone,
        "authority_class": authority_class,
        "maximum_action": maximum_action,
    }
    if any(value is not None for value in bridge.values()):
        if any(value is None for value in bridge.values()):
            raise ContractError("K4.1 handback authority fields must appear together")
        receipt.update(bridge)
    return receipt

"""Candidate freeze, invalidation, QA, and Cloud-readiness selection."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .contracts import CANDIDATE_FIELDS, ContractError


READINESS_MATRIX = {
    "dependency_lock": {"CR3", "CR4", "CR6"},
    "package_manifest": {"CR3", "CR4", "CR6"},
    "tool_manifest": {"CR3", "CR4", "CR6"},
    "native_dependency": {"CR3", "CR4", "CR6"},
    "data_schema": {"CR5", "CR6", "CR9"},
    "migration": {"CR5", "CR6", "CR9"},
    "seed": {"CR5", "CR6", "CR9"},
    "fixture": {"CR5", "CR6", "CR9"},
    "test_account": {"CR5", "CR6", "CR9"},
    "service_configuration": {"CR7", "CR8"},
    "browser_journey": {"CR9"},
    "auth_fixture": {"CR9"},
    "process_loss_executable": {"CR10"},
    "resume_executable": {"CR10"},
    "stop_executable": {"CR10"},
    "cleanup_executable": {"CR10"},
}


def freeze_candidate(candidate: dict[str, Any], clean: bool, builder_quiescent: bool, frozen_at: str) -> dict[str, Any]:
    missing = [field for field in CANDIDATE_FIELDS if field not in candidate]
    if missing:
        raise ContractError(f"candidate tuple missing {missing}")
    if not clean or not builder_quiescent:
        raise ContractError("candidate cannot freeze until clean and quiescent")
    result = {field: deepcopy(candidate[field]) for field in CANDIDATE_FIELDS}
    result["frozen_at"] = frozen_at
    return result


def invalidation_phase(frozen: dict[str, Any], observed: dict[str, Any]) -> str:
    if any(frozen.get(field) != observed.get(field) for field in CANDIDATE_FIELDS):
        return "build"
    return "final-check"


def candidate_readiness_selection(
    changed_inputs: set[str], admission_current: bool, epochs_observable: bool
) -> dict[str, Any]:
    unknown = changed_inputs - set(READINESS_MATRIX)
    if unknown:
        raise ContractError(f"unknown readiness input classes: {sorted(unknown)}")
    if not admission_current or not epochs_observable:
        required = {f"CR{i}" for i in range(1, 11)}
        return {
            "required": sorted(required),
            "may_reuse_admission": False,
            "reason": "admission missing/stale or Cloud epochs unobservable",
        }
    required: set[str] = {"CR5", "CR6", "CR7", "CR8", "CR9"}
    # Candidate mode always proves CR5-CR9. Changed inputs add the minimum
    # extra rows (principally fresh CR3/4 or CR10) and prevent affected reuse.
    if changed_inputs:
        required |= set().union(*(READINESS_MATRIX[item] for item in changed_inputs))
    return {
        "required": sorted(required),
        "may_reuse_admission": True,
        "changed_inputs": sorted(changed_inputs),
        "reason": "minimum union from the frozen invalidation matrix",
    }


def validate_qa_findings(findings: list[dict[str, Any]], closures: list[dict[str, Any]]) -> None:
    closed = {item.get("finding_id") for item in closures if item.get("attestation_ref") and item.get("fixing_sha")}
    unresolved = [item.get("finding_id") for item in findings if item.get("status") != "closed" or item.get("finding_id") not in closed]
    invalid = [item.get("finding_id") for item in findings if not isinstance(item.get("locator"), dict) or not item["locator"].get("type")]
    if invalid:
        raise ContractError(f"findings missing typed locators: {invalid}")
    if unresolved:
        raise ContractError(f"unresolved findings: {unresolved}")


def validate_gate_blockers(
    *,
    verdict_outcome: str,
    findings: list[dict[str, Any]],
    closures: list[dict[str, Any]],
    blocking_todos_mirrored: bool,
    unresolved_host_threads: int,
    open_interrupts: int,
    required_actions: list[str],
) -> None:
    if verdict_outcome != "pass":
        raise ContractError(f"verdict {verdict_outcome} is nonmergeable")
    validate_qa_findings(findings, closures)
    if not blocking_todos_mirrored:
        raise ContractError("blocking Todos are not mirrored into the finding ledger")
    if unresolved_host_threads:
        raise ContractError("unresolved host review threads")
    if open_interrupts:
        raise ContractError("open taste or safety interrupt")
    if required_actions:
        raise ContractError("required actions remain open")

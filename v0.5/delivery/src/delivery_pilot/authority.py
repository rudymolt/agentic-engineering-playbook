"""Envelope, approval, venue, and bounded taste-amendment rules."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .canonical import digest
from .contracts import ContractError


FORBIDDEN_TASTE_PREFIXES = (
    "/authority",
    "/constraints/coordinator_venue",
    "/constraints/ceilings",
    "/constraints/protected_paths",
    "/safety",
    "/records",
)


def validate_approval(envelope: dict[str, Any], approval: dict[str, Any]) -> None:
    if approval.get("envelope_digest") != digest(envelope):
        raise ContractError("approval does not bind the current envelope")
    actors = envelope.get("authority", {}).get("authorized_human_ids", [])
    if not actors or approval.get("actor_id") not in actors:
        raise ContractError("approval actor is not authorized")
    for field in ("envelope_ref", "source_event_id", "approved_at", "channel"):
        if not approval.get(field):
            raise ContractError(f"approval missing {field}")
    if envelope.get("rollout_milestone") == "K4.1":
        expected = {
            "rollout_milestone": "K4.1",
            "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge",
        }
        for field, value in expected.items():
            if approval.get(field) != value:
                raise ContractError(f"K4.1 approval {field} must be {value}")


def validate_venue_approval(
    envelope: dict[str, Any], venue: str, displayed_digest: str, selected_digest: str
) -> None:
    current = digest(envelope)
    if displayed_digest != current or selected_digest != current:
        raise ContractError("venue answer references a stale or incomplete envelope")
    if venue != envelope.get("constraints", {}).get("coordinator_venue"):
        raise ContractError("venue does not match approved envelope")


def _pointer_parent(document: dict[str, Any], pointer: str) -> tuple[dict[str, Any], str]:
    if not pointer.startswith("/") or "~" in pointer:
        raise ContractError("only unescaped absolute JSON pointers are supported")
    parts = pointer[1:].split("/")
    current: Any = document
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise ContractError(f"patch path does not exist: {pointer}")
        current = current[part]
    if not isinstance(current, dict):
        raise ContractError(f"patch parent is not an object: {pointer}")
    return current, parts[-1]


def apply_taste_answer(
    envelope: dict[str, Any], question: dict[str, Any], answer: dict[str, Any]
) -> dict[str, Any]:
    if question.get("base_envelope_digest") != digest(envelope):
        raise ContractError("question is stale")
    if answer.get("question_id") != question.get("question_id") or answer.get("options_revision") != question.get("options_revision"):
        raise ContractError("answer does not bind the current question revision")
    if answer.get("actor_id") not in envelope.get("authority", {}).get("authorized_human_ids", []):
        raise ContractError("answer actor is not authorized")
    option = next((o for o in question.get("options", []) if o.get("id") == answer.get("option_id")), None)
    if option is None:
        raise ContractError("answer names an unknown option")
    patch = option.get("patch", [])
    if digest(patch) != option.get("patch_digest"):
        raise ContractError("taste patch digest mismatch")
    allowed = set(option.get("allowed_paths", []))
    result = deepcopy(envelope)
    for operation in patch:
        path = operation.get("path", "")
        if path not in allowed or path.startswith(FORBIDDEN_TASTE_PREFIXES):
            raise ContractError(f"taste patch path is not authorized: {path}")
        if operation.get("op") not in {"add", "replace", "remove"}:
            raise ContractError("unsupported taste patch operation")
        parent, key = _pointer_parent(result, path)
        if operation["op"] == "remove":
            if key not in parent:
                raise ContractError("cannot remove a missing path")
            del parent[key]
        else:
            if operation["op"] == "replace" and key not in parent:
                raise ContractError("cannot replace a missing path")
            parent[key] = deepcopy(operation.get("value"))
    result["revision"] = envelope["revision"] + 1
    expected = option.get("result_envelope_digest")
    if digest(result) != expected or answer.get("result_envelope_digest") != expected:
        raise ContractError("derived envelope digest mismatch")
    return result

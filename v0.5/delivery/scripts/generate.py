#!/usr/bin/env python3
"""Generate schemas, examples, test manifest, rule index, and pack manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.canonical import canonical_bytes, digest, load_strict  # noqa: E402
from delivery_pilot.contracts import CANDIDATE_FIELDS, MISSION_PHASES, MISSION_STATUSES  # noqa: E402


def rendered_json(value: Any) -> bytes:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True).encode() + b"\n"


def json_schema(schema_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    json_types = {dict: "object", list: "array", str: "string", int: "integer", bool: "boolean", float: "number"}
    example = entry.get("example", {})
    properties: dict[str, Any] = {
        field: ({"type": json_types[type(example[field])]} if field in example and example[field] is not None else {})
        for field in entry.get("required", []) + entry.get("optional", [])
    }
    properties["schema_version"] = {"const": entry["version"]}
    for field, options in entry.get("enums", {}).items():
        properties[field] = {"enum": options}
    for field in entry.get("digest_fields", []):
        digest_type: str | list[str] = ["string", "null"] if example.get(field) is None else "string"
        properties[field] = {"type": digest_type, "pattern": "^sha256:[0-9a-f]{64}$"}
    for field in entry.get("git_sha_fields", []):
        properties[field] = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
    for field in entry.get("nullable_git_sha_fields", []):
        properties[field] = {"type": ["string", "null"], "pattern": "^[0-9a-f]{40}$"}
    for field in entry.get("non_empty_fields", []):
        field_schema = properties.setdefault(field, {})
        example_value = example.get(field)
        if isinstance(example_value, (list, dict)):
            field_schema["minItems" if isinstance(example_value, list) else "minProperties"] = 1
        elif isinstance(example_value, str):
            field_schema["minLength"] = 1
    for field in entry.get("positive_fields", []):
        properties.setdefault(field, {})["exclusiveMinimum"] = 0
    for field in entry.get("string_list_fields", []):
        properties.setdefault(field, {}).update({"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}})
    for field in entry.get("offset_timestamp_fields", []):
        properties.setdefault(field, {}).update({"type": "string", "format": "date-time"})
    for field, prefix in entry.get("prefix_fields", {}).items():
        properties.setdefault(field, {}).update({"type": "string", "pattern": "^" + prefix})
    for field, prefixes in entry.get("allowed_prefix_fields", {}).items():
        properties.setdefault(field, {}).update({
            "type": "string",
            "anyOf": [{"pattern": "^" + prefix + ".+$"} for prefix in prefixes],
        })
    for field, required in entry.get("object_required", {}).items():
        field_schema = properties.setdefault(field, {})
        field_schema.update({
            "type": "object",
            "additionalProperties": False,
            "required": required,
            "properties": {nested: {} for nested in required},
        })
        for nested in entry.get("object_digest_fields", {}).get(field, []):
            field_schema["properties"][nested] = {
                "type": "string",
                "pattern": "^sha256:[0-9a-f]{64}$",
            }
        for nested in entry.get("object_string_fields", {}).get(field, []):
            field_schema["properties"].setdefault(nested, {}).update({"type": "string", "minLength": 1})
        for nested in entry.get("object_offset_timestamp_fields", {}).get(field, []):
            field_schema["properties"][nested] = {"type": "string", "format": "date-time"}
        for nested, options in entry.get("object_enums", {}).get(field, {}).items():
            field_schema["properties"][nested] = {"enum": options}
    for field, required in entry.get("list_object_required", {}).items():
        item_properties = {nested: {} for nested in required}
        for nested in entry.get("list_object_string_fields", {}).get(field, []):
            item_properties[nested] = {"type": "string", "minLength": 1}
        for nested, options in entry.get("list_object_enums", {}).get(field, {}).items():
            item_properties[nested] = {"enum": options}
        for nested in entry.get("list_object_offset_timestamp_fields", {}).get(field, []):
            item_properties[nested] = {"type": "string", "format": "date-time"}
        properties[field] = {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": item_properties,
            },
        }
    result = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://playbook.local/delivery-pilot/{schema_id}/v{entry['version']}",
        "title": f"{schema_id}/v{entry['version']}",
        "type": "object",
        "additionalProperties": bool(entry.get("additional_properties", False)),
        "required": entry.get("required", []),
        "properties": properties,
    }
    groups = entry.get("all_or_none", [])
    if groups:
        result["dependentRequired"] = {
            field: [peer for peer in group if peer != field]
            for group in groups
            for field in group
        }
    conditional_values = entry.get("conditional_values", [])
    if conditional_values:
        result.setdefault("allOf", []).extend({
            "if": {
                "required": [condition["field"]],
                "properties": {condition["field"]: {"const": condition["equals"]}},
            },
            "then": {"properties": {condition["target"]: {"const": condition["value"]}}},
        } for condition in conditional_values)
    if schema_id == "envelope":
        _k41_envelope_schema(result)
    if schema_id == "handback":
        _k41_handback_schema(result)
    if schema_id == "mission":
        _mission_schema(result)
    if schema_id == "process-attested-merge":
        result["allOf"] = [{
            "if": {"properties": {"outcome": {"const": "merged"}}},
            "then": {"properties": {"merge_commit_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}}},
            "else": {"properties": {"merge_commit_sha": {"type": "null"}}},
        }, {
            "if": {"properties": {"dispatch_mode": {"const": "reconcile-only"}}},
            "then": {"properties": {
                "outcome": {"const": "ambiguous"},
                "merge_commit_sha": {"type": "null"},
                "ambiguous_response_observed": {"const": True},
            }},
        }, {
            "if": {"properties": {"outcome": {"const": "ambiguous"}}},
            "then": {"properties": {"ambiguous_response_observed": {"const": True}}},
            "else": {"properties": {"ambiguous_response_observed": {"const": False}}},
        }]
    if schema_id == "readiness-profile":
        _cloud_profile_schema(result["properties"])
    elif schema_id == "readiness-receipt":
        _cloud_receipt_schema(result["properties"])
    elif schema_id == "launcher-v4":
        _launcher_v4_schema(result["properties"])
    elif schema_id == "merge-gate":
        result["properties"]["candidate"] = _candidate_schema()
    elif schema_id == "merge-decision":
        _merge_decision_schema(result)
    return result


def _object(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": properties}


def _mission_schema(result: dict[str, Any]) -> None:
    properties = result["properties"]
    text = {"type": "string", "minLength": 1}
    nullable_text = {"type": ["string", "null"]}
    terminal_outcomes = ["delivered", "rolled_back", "merged_no_deploy", "pr_ready", "cancelled"]
    digest_value = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    properties["revision"] = {"type": "integer", "minimum": 1}
    properties["prior_digest"] = {"type": ["string", "null"], "pattern": "^sha256:[0-9a-f]{64}$"}
    properties["updated_at"] = {"type": "string", "format": "date-time"}
    properties["controller"] = _object(
        ["generation", "workspace_id", "session_id"],
        {"generation": {"type": "integer", "minimum": 1}, "workspace_id": text, "session_id": text},
    )
    authority_fields = [
        "command", "requested_tier", "effective_tier", "envelope_ref", "envelope_digest",
        "approval_receipt_ref", "policy_kind", "policy_ref", "policy_digest",
    ]
    properties["authority"] = _object(authority_fields, {
        "command": {"const": "deliver-to-pr"},
        "requested_tier": {"const": "A"},
        "effective_tier": {"const": "A"},
        "envelope_ref": {"type": "string", "pattern": "^planning/.+"},
        "approval_receipt_ref": text,
        "policy_kind": {"const": "pilot-composite"},
        "policy_ref": text,
        "envelope_digest": digest_value, "policy_digest": digest_value,
    })
    properties["aggregate"] = {
        **_object(
        ["phase", "status", "terminal_outcome", "wake_guard"],
        {
            "phase": {"enum": sorted(MISSION_PHASES)},
            "status": {"enum": sorted(MISSION_STATUSES)},
            "terminal_outcome": {"enum": [*terminal_outcomes, None]},
            "wake_guard": nullable_text,
        },
        ),
        "allOf": [
            {
                "if": {"properties": {"phase": {"const": "complete"}}, "required": ["phase"]},
                "then": {
                    "properties": {
                        "status": {"enum": ["complete", "cancelled"]},
                        "terminal_outcome": {"enum": terminal_outcomes},
                    }
                },
                "else": {
                    "properties": {
                        "status": {"not": {"enum": ["complete", "cancelled"]}},
                        "terminal_outcome": {"type": "null"},
                    }
                },
            },
            {
                "if": {"properties": {"status": {"const": "cancelled"}}, "required": ["status"]},
                "then": {"properties": {"terminal_outcome": {"const": "cancelled"}}},
            },
            {
                "if": {"properties": {"status": {"const": "complete"}}, "required": ["status"]},
                "then": {"properties": {"terminal_outcome": {"enum": [item for item in terminal_outcomes if item != "cancelled"]}}},
            },
            {
                "if": {"properties": {"status": {"enum": ["running", "complete", "cancelled"]}}, "required": ["status"]},
                "then": {"properties": {"wake_guard": {"type": "null"}}},
                "else": {"properties": {"wake_guard": {"type": "string", "minLength": 1}}},
            },
        ],
    }
    candidate_fields = [
        "head_sha", "tree_sha", "base_sha", "policy_sha", "ruleset_fingerprint", "merge_group_sha",
        "verification_environment_digest", "frozen_at", "builder_session_ids",
    ]
    properties["candidate"] = _object(candidate_fields, {
        **{field: nullable_text for field in candidate_fields if field != "builder_session_ids"},
        "builder_session_ids": {"type": "array", "items": text},
    })
    locator = _object(["type", "value"], {"type": text, "value": text})
    finding_fields = ["schema_version", "finding_id", "severity", "class", "evidence_digest", "locator", "status"]
    properties["findings"] = {"type": "array", "items": _object(finding_fields, {
        "schema_version": {"const": 1}, "finding_id": text, "severity": text, "class": text, "evidence_digest": digest_value,
        "locator": locator, "status": {"enum": ["open", "closed"]},
    })}
    interrupt_fields = [
        "schema_version", "interrupt_id", "mission_id", "phase", "trigger", "evidence_refs", "blast_radius",
        "dispositions", "recommended", "status",
    ]
    properties["interrupts"] = {
        "type": "array",
        "items": {
            **_object(interrupt_fields, {
                "schema_version": {"const": 1},
                **{field: text for field in ("interrupt_id", "mission_id", "phase", "trigger", "blast_radius", "recommended")},
                "evidence_refs": {"type": "array", "items": text},
                "dispositions": {"type": "array", "items": text},
                "status": {"enum": ["open", "resolved"]},
                "answer_ref": text,
            }),
            "required": interrupt_fields,
        },
    }
    properties["required_actions"] = {"type": "array", "items": text}
    result.setdefault("allOf", []).extend([
        {
            "if": {"properties": {"revision": {"const": 1}}},
            "then": {"properties": {"prior_digest": {"type": "null"}}},
        },
        {
            "if": {"properties": {"revision": {"minimum": 2}}},
            "then": {"properties": {"prior_digest": digest_value}},
        },
    ])


def _k41_envelope_schema(result: dict[str, Any]) -> None:
    exact = {
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
        "risk_class": None,
        "planning_prefix": None,
        "implementation_paths": None,
        "candidate_binding": "post-freeze",
        "pr_binding": "post-pr",
    }
    result.setdefault("allOf", []).append({
        "if": {
            "required": ["rollout_milestone"],
            "properties": {"rollout_milestone": {"const": "K4.1"}},
        },
        "then": {
            "properties": {
                "authority": {
                    "type": "object",
                    "required": list(exact),
                    "properties": {
                        **{field: {"const": value} for field, value in exact.items() if value is not None},
                        "repository": {"type": "string", "pattern": "^[^/]+/[^/]+$"},
                        "project": {"type": "string", "minLength": 1},
                        "mission_id": {"type": "string", "minLength": 1},
                        "base_ref": {"type": "string", "minLength": 1},
                        "merge_method": {"enum": ["squash", "merge", "rebase"]},
                        "risk_class": {"type": "string", "minLength": 1},
                        "planning_prefix": {"type": "string", "pattern": "^planning/[^/]+/$"},
                        "implementation_paths": {
                            "type": "array", "minItems": 1, "uniqueItems": True,
                            "items": {"type": "string", "minLength": 1},
                        },
                    },
                    "not": {"anyOf": [
                        {"required": [field]}
                        for field in ("pr_number", "candidate_head", "candidate_tree", "candidate")
                    ]},
                }
            }
        },
    })


def _k41_handback_schema(result: dict[str, Any]) -> None:
    result.setdefault("allOf", []).append({
        "if": {
            "required": ["rollout_milestone"],
            "properties": {"rollout_milestone": {"const": "K4.1"}},
        },
        "then": {
            "properties": {
                "pr_ref": {"type": "string", "pattern": "^github:pr/[1-9][0-9]*$"},
            },
        },
    })


def _cloud_profile_schema(properties: dict[str, Any]) -> None:
    digest_value = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    text = {"type": "string", "minLength": 1}
    cloud_fields = ["build_epoch_name", "expected_build_epoch", "setup_epoch_name", "expected_setup_epoch", "repository_setup_ref", "repository_setup_digest", "os_family", "required_environment", "tool_probes"]
    properties["cloud"] = _object(cloud_fields, {
        **{field: text for field in cloud_fields[:5]}, "repository_setup_digest": digest_value, "os_family": text,
        "required_environment": {"type": "array", "items": _object(["name", "kind", "probe"], {"name": text, "kind": {"enum": ["secret", "non-secret"]}, "probe": {"const": "presence-only"}})},
        "tool_probes": {"type": "array", "items": _object(["name", "command", "version"], {"name": text, "command": text, "version": text})},
    })
    service_fields = ["id", "start", "restart", "stop", "port", "healthcheck", "log_paths"]
    properties["services"] = {"type": "array", "minItems": 1, "items": _object(service_fields, {
        **{field: text for field in ("id", "start", "restart", "stop", "healthcheck")}, "port": {"type": "integer", "minimum": 1, "maximum": 65535}, "log_paths": {"type": "array", "minItems": 1, "items": text},
    })}
    properties["data"] = _object(["migrate", "reset", "seed", "fixture_digest", "test_accounts_ref"], {"migrate": text, "reset": text, "seed": text, "fixture_digest": digest_value, "test_accounts_ref": {"type": "string", "pattern": "^secret-ref:.+"}})
    properties["verification"] = _object(["commands"], {"commands": {"type": "array", "minItems": 1, "items": text}})
    properties["preview"] = _object(["review_route", "health_url", "human_forward_sandbox_port"], {"review_route": {"enum": ["same-workspace-headless", "isolated-workspace-rebuild", "external-preview"]}, "health_url": text, "human_forward_sandbox_port": {"type": "integer", "minimum": 1, "maximum": 65535}})
    properties["browser_review"] = _object(["journeys_ref", "journeys_digest", "evidence"], {"journeys_ref": text, "journeys_digest": digest_value, "evidence": {"type": "array", "items": {"enum": ["assertions", "screenshots", "console", "failed-network", "trace"]}, "minItems": 5, "maxItems": 5, "uniqueItems": True}})
    properties["recovery"] = _object(["process_loss_probe", "process_loss_probe_digest", "resume", "resume_digest"], {"process_loss_probe": text, "process_loss_probe_digest": digest_value, "resume": text, "resume_digest": digest_value})


def _cloud_receipt_schema(properties: dict[str, Any]) -> None:
    condition = _object(["outcome", "evidence_locators"], {"outcome": {"enum": ["pass", "fail", "not-run", "reused"]}, "evidence_locators": {"type": "array", "items": {"type": "string", "minLength": 1}}})
    properties["conditions"] = _object([f"CR{i}" for i in range(1, 11)], {f"CR{i}": condition for i in range(1, 11)})
    properties["raw_evidence_locators"] = {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}}
    properties["review_route"] = {"enum": ["same-workspace-headless", "isolated-workspace-rebuild", "external-preview"]}
    for field in ("started_at", "ended_at", "expires_at"):
        properties[field] = {"type": "string", "format": "date-time"}


def _launcher_v4_schema(properties: dict[str, Any]) -> None:
    properties["termination_state"] = {"const": "completed"}
    checkpoints = properties["provider_checkpoints"]["properties"]
    checkpoints["turn_id"].update({"pattern": "^[A-Za-z0-9_.-]+$"})
    checkpoints["start_ref"].update({"pattern": "^refs/conductor-checkpoints/session-.+-turn-.+-start$"})
    checkpoints["end_ref"].update({"pattern": "^refs/conductor-checkpoints/session-.+-turn-.+-end$"})
    for field in ("start_commit", "end_commit"):
        checkpoints[field].update({"pattern": "^[0-9a-f]{40}$"})


def _merge_decision_schema(result: dict[str, Any]) -> None:
    properties = result["properties"]
    text = {"type": "string", "minLength": 1}
    digest_value = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    sha = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
    agent_fields = ["role", "session_id", "family", "model", "effort", "fresh_context", "builder_separation"]
    properties["agent"] = _object(agent_fields, {
        "role": {"const": "fresh-merge-agent"},
        "session_id": text,
        "family": text,
        "model": text,
        "effort": text,
        "fresh_context": {"const": True},
        "builder_separation": {"const": "live-controller-session-different"},
    })
    properties["expected_head_sha"] = sha
    properties["expected_tree_sha"] = sha
    properties["expected_candidate"] = _candidate_schema()
    properties["controller_generation"] = {"type": "integer", "minimum": 1}
    properties["control_ref"] = {"type": "string", "pattern": "^refs/heads/delivery-control/.+$"}
    properties["control_commit"] = sha
    properties["control_digest"] = digest_value
    policy_fields = [
        "allowed_risk_classes", "authority_class", "human_merge_path_prefixes",
        "human_merge_path_names", "human_merge_path_name_prefixes", "policy_version", "source_branch",
    ]
    non_empty_text_list = {"type": "array", "minItems": 1, "items": text}
    properties["risk_policy"] = _object(policy_fields, {
        "allowed_risk_classes": non_empty_text_list,
        "authority_class": {"const": "process-attested-fresh-merge"},
        "human_merge_path_prefixes": non_empty_text_list,
        "human_merge_path_names": non_empty_text_list,
        "human_merge_path_name_prefixes": non_empty_text_list,
        "policy_version": {"const": 1},
        "source_branch": {"const": "default-branch-only"},
    })
    scope_fields = ["risk_class", "planning_prefix", "implementation_paths"]
    properties["approved_scope"] = _object(scope_fields, {
        "risk_class": text,
        "planning_prefix": {"type": "string", "pattern": "^planning/[^/]+/$"},
        "implementation_paths": {"type": "array", "minItems": 1, "uniqueItems": True, "items": text},
    })
    properties["protected_path_matches"] = {"type": "array", "items": text}
    properties["changed_paths"] = {"type": "array"}
    properties["verification_digests"] = {"type": "array", "minItems": 1, "items": digest_value}
    result.setdefault("allOf", []).append({
        "if": {"properties": {"decision": {"const": "allow"}}},
        "then": {"properties": {
            "protected_path_matches": {"type": "array", "maxItems": 0},
            "reason_codes": {"const": ["all-controls-pass"]},
        }},
        "else": {"properties": {"reason_codes": {"type": "array", "minItems": 1}}},
    })
    normalized_path = r"^(?!/)(?!.*\\)(?!.*//)(?!.*(?:^|/)\.\.?(?:/|$))(?!.*\/$).+$"
    result["allOf"].append({
        "if": {"properties": {"changed_paths": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "pattern": normalized_path},
            "uniqueItems": True,
        }}},
        "else": {"properties": {
            "decision": {"const": "deny"},
            "reason_codes": {"type": "array", "contains": {"const": "scope-outside-approved-paths"}},
        }},
    })


def _candidate_schema() -> dict[str, Any]:
    sha = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
    text = {"type": "string", "minLength": 1}
    return _object(list(CANDIDATE_FIELDS), {
        "head_sha": sha,
        "tree_sha": sha,
        "base_sha": sha,
        "policy_sha": sha,
        "ruleset_fingerprint": text,
        "verification_environment_digest": text,
        "merge_group_sha": {"type": ["string", "null"], "pattern": "^[0-9a-f]{40}$"},
    })


def generated_outputs() -> dict[Path, bytes]:
    registry = load_strict((PACK / "contracts" / "registry.yml").read_bytes())
    outputs: dict[Path, bytes] = {}
    for schema_id, entry in registry["schemas"].items():
        outputs[Path("contracts/generated/schemas") / f"{schema_id}.schema.json"] = rendered_json(json_schema(schema_id, entry))
        outputs[Path("contracts/generated/examples") / f"{schema_id}.json"] = rendered_json(entry["example"])
    test_manifest = {
        "schema_version": 1,
        "registry_digest": digest(registry),
        "sets": registry["test_sets"],
    }
    outputs[Path("contracts/generated/test-manifest.json")] = rendered_json(test_manifest)
    rule_index = {
        "schema_version": 1,
        "schemas": sorted(f"{name}/v{entry['version']}" for name, entry in registry["schemas"].items()),
        "gates": sorted(registry["gates"]),
        "deploy_gates": sorted(registry["deploy_gates"]),
        "phases": ["authorized", "build", "slice-check", "qa", "freeze", "candidate-readiness", "final-check", "pr-ready", "handback", "merge", "deploy", "canary", "recovery", "closeout", "retro", "cleanup", "archive-ready", "externally-archived", "complete"],
        "public_interfaces": ["control_ref_create", "registry_locator_upsert", "branch_ensure", "pr_upsert", "question_publish"],
    }
    outputs[Path("contracts/generated/spec-rule-index.yml")] = rendered_json(rule_index)
    return outputs


def installed_path(relative: Path) -> str | None:
    raw = relative.as_posix()
    if raw == "skill/SKILL.md":
        return "SKILL.md"
    if raw.startswith("skill/agents/"):
        return raw.removeprefix("skill/")
    if raw.startswith("skill/scripts/"):
        return raw.removeprefix("skill/")
    if raw.startswith("skill/references/"):
        return raw.removeprefix("skill/")
    if raw.startswith("src/delivery_pilot/"):
        return "runtime/" + raw.removeprefix("src/")
    if raw == "contracts/registry.yml" or raw.startswith("contracts/generated/"):
        return raw
    return None


def source_files() -> list[Path]:
    return sorted(
        path.relative_to(PACK)
        for path in PACK.rglob("*")
        if path.is_file()
        and path.name != "MANIFEST.yml"
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
    )


def manifest() -> dict[str, Any]:
    files = []
    for relative in source_files():
        raw = (PACK / relative).read_bytes()
        files.append({
            "source": relative.as_posix(),
            "install_path": installed_path(relative),
            "digest": "sha256:" + hashlib.sha256(raw).hexdigest(),
        })
    identity = {"manifest_schema_version": 1, "files": files}
    return {**identity, "pack_digest": digest(identity), "manifest_self_rule": "pack_digest covers the complete non-manifest source inventory"}


def apply(check: bool) -> int:
    stale: list[str] = []
    for relative, raw in generated_outputs().items():
        target = PACK / relative
        if check:
            if not target.exists() or target.read_bytes() != raw:
                stale.append(relative.as_posix())
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    manifest_raw = rendered_json(manifest())
    manifest_path = PACK / "MANIFEST.yml"
    if check:
        if not manifest_path.exists() or manifest_path.read_bytes() != manifest_raw:
            stale.append("MANIFEST.yml")
    else:
        manifest_path.write_bytes(manifest_raw)
    if stale:
        print("stale generated files: " + ", ".join(stale))
        return 1
    print("delivery-pilot generated artifacts are current")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    raise SystemExit(apply(parser.parse_args().check))

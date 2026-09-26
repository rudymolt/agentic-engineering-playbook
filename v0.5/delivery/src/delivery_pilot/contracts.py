"""Registry-owned contract validation."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .canonical import CanonicalError, load_strict


SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
MISSION_PHASES = {
    "authorized", "build", "slice-check", "qa", "freeze", "candidate-readiness", "final-check",
    "pr-ready", "handback", "merge", "deploy", "canary", "recovery", "closeout", "retro", "cleanup",
    "archive-ready", "externally-archived", "complete",
}
MISSION_STATUSES = {
    "running", "parked", "waiting_taste", "waiting_safety", "waiting_capacity", "ceiling", "errored",
    "cancelling", "intervention_required", "complete", "cancelled",
}
MISSION_TERMINAL_OUTCOMES = {
    "delivered", "rolled_back", "merged_no_deploy", "pr_ready", "cancelled",
}
CANDIDATE_FIELDS = (
    "head_sha", "tree_sha", "base_sha", "policy_sha", "ruleset_fingerprint",
    "verification_environment_digest", "merge_group_sha",
)


class ContractError(ValueError):
    pass


class ContractRegistry:
    def __init__(self, source: dict[str, Any], path: Path | None = None):
        self.source = source
        self.path = path
        if source.get("registry_version") != 1 or not isinstance(source.get("schemas"), dict):
            raise ContractError("unsupported or malformed registry")

    @classmethod
    def load(cls, path: Path) -> "ContractRegistry":
        try:
            return cls(load_strict(path.read_bytes()), path)
        except (OSError, CanonicalError) as exc:
            raise ContractError(str(exc)) from exc

    @property
    def schema_ids(self) -> tuple[str, ...]:
        return tuple(self.source["schemas"])

    def schema(self, schema_id: str) -> dict[str, Any]:
        try:
            return self.source["schemas"][schema_id]
        except KeyError as exc:
            raise ContractError(f"unregistered schema: {schema_id}") from exc

    def schema_version(self, schema_id: str) -> int:
        return int(self.schema(schema_id)["version"])

    def example(self, schema_id: str) -> dict[str, Any]:
        return deepcopy(self.schema(schema_id)["example"])

    def validate(self, schema_id: str, value: Any) -> None:
        schema = self.schema(schema_id)
        if not isinstance(value, dict):
            raise ContractError(f"{schema_id}: record must be an object")
        if value.get("schema_version") != schema["version"]:
            raise ContractError(f"{schema_id}: unknown schema_version")
        for field in schema.get("required", []):
            if field not in value:
                raise ContractError(f"{schema_id}: missing {field}")
        example = schema.get("example", {})
        for field, actual in value.items():
            expected = example.get(field)
            if expected is None:
                continue
            if isinstance(expected, bool):
                valid_type = isinstance(actual, bool)
            elif isinstance(expected, int):
                valid_type = isinstance(actual, int) and not isinstance(actual, bool)
            else:
                valid_type = isinstance(actual, type(expected))
            if not valid_type:
                raise ContractError(f"{schema_id}: wrong type for {field}")
        allowed = set(schema.get("required", [])) | set(schema.get("optional", []))
        unknown = set(value) - allowed
        if unknown and not schema.get("additional_properties", False):
            raise ContractError(f"{schema_id}: unknown fields {sorted(unknown)}")
        for field, options in schema.get("enums", {}).items():
            if field in value and value[field] not in options:
                raise ContractError(f"{schema_id}: unknown {field} value")
        for field in schema.get("digest_fields", []):
            nullable = schema.get("example", {}).get(field) is None
            if (value.get(field) is None and not nullable) or (
                value.get(field) is not None and not SHA256.match(str(value[field]))
            ):
                raise ContractError(f"{schema_id}: invalid digest {field}")
        for field in schema.get("git_sha_fields", []):
            if not re.fullmatch(r"[0-9a-f]{40}", str(value.get(field, ""))):
                raise ContractError(f"{schema_id}: invalid Git SHA in {field}")
        for field in schema.get("nullable_git_sha_fields", []):
            candidate = value.get(field)
            if candidate is not None and not re.fullmatch(r"[0-9a-f]{40}", str(candidate)):
                raise ContractError(f"{schema_id}: invalid Git SHA in {field}")
        for field in schema.get("non_empty_fields", []):
            if value.get(field) in (None, "", [], {}):
                raise ContractError(f"{schema_id}: empty {field}")
        for field in schema.get("positive_fields", []):
            actual = value.get(field)
            if isinstance(actual, bool) or not isinstance(actual, (int, float)) or actual <= 0:
                raise ContractError(f"{schema_id}: {field} must be positive")
        for field in schema.get("string_list_fields", []):
            actual = value.get(field)
            if not isinstance(actual, list) or not actual or any(not isinstance(item, str) or not item for item in actual):
                raise ContractError(f"{schema_id}: {field} must contain non-empty strings")
        for field, prefix in schema.get("prefix_fields", {}).items():
            if not isinstance(value.get(field), str) or not value[field].startswith(prefix):
                raise ContractError(f"{schema_id}: {field} must start with {prefix}")
        for field, prefixes in schema.get("allowed_prefix_fields", {}).items():
            actual = value.get(field)
            if not isinstance(actual, str) or not any(
                actual.startswith(prefix) and len(actual) > len(prefix) for prefix in prefixes
            ):
                rendered = ", ".join(prefixes)
                raise ContractError(f"{schema_id}: {field} must start with one of {rendered} and include an ID")
        for field in schema.get("offset_timestamp_fields", []):
            try:
                parsed = datetime.fromisoformat(str(value.get(field, "")).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContractError(f"{schema_id}: invalid timestamp {field}") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ContractError(f"{schema_id}: {field} must include a UTC offset")
        for field, required in schema.get("object_required", {}).items():
            nested = value.get(field)
            if not isinstance(nested, dict):
                raise ContractError(f"{schema_id}: {field} must be an object")
            for nested_field in required:
                if nested.get(nested_field) in (None, "", [], {}):
                    raise ContractError(f"{schema_id}: missing {field}.{nested_field}")
            unknown_nested = set(nested) - set(required)
            if unknown_nested:
                raise ContractError(f"{schema_id}: unknown {field} fields {sorted(unknown_nested)}")
        for field, digest_fields in schema.get("object_digest_fields", {}).items():
            nested = value.get(field, {})
            for nested_field in digest_fields:
                if not SHA256.match(str(nested.get(nested_field, ""))):
                    raise ContractError(f"{schema_id}: invalid digest {field}.{nested_field}")
        for field, string_fields in schema.get("object_string_fields", {}).items():
            nested = value.get(field, {})
            for nested_field in string_fields:
                if not isinstance(nested.get(nested_field), str) or not nested[nested_field]:
                    raise ContractError(f"{schema_id}: {field}.{nested_field} must be a non-empty string")
        for field, timestamp_fields in schema.get("object_offset_timestamp_fields", {}).items():
            nested = value.get(field, {})
            for nested_field in timestamp_fields:
                try:
                    parsed = datetime.fromisoformat(str(nested.get(nested_field, "")).replace("Z", "+00:00"))
                except ValueError as exc:
                    raise ContractError(f"{schema_id}: invalid timestamp {field}.{nested_field}") from exc
                if parsed.tzinfo is None or parsed.utcoffset() is None:
                    raise ContractError(f"{schema_id}: {field}.{nested_field} must include a UTC offset")
        for field, enums in schema.get("object_enums", {}).items():
            nested = value.get(field, {})
            for nested_field, options in enums.items():
                if nested.get(nested_field) not in options:
                    raise ContractError(f"{schema_id}: unknown {field}.{nested_field} value")
        for field, required in schema.get("list_object_required", {}).items():
            items = value.get(field)
            if not isinstance(items, list) or not items:
                raise ContractError(f"{schema_id}: {field} must be a non-empty object list")
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise ContractError(f"{schema_id}: {field}[{index}] must be an object")
                for nested_field in required:
                    if item.get(nested_field) in (None, "", [], {}):
                        raise ContractError(f"{schema_id}: missing {field}[{index}].{nested_field}")
                unknown_nested = set(item) - set(required)
                if unknown_nested:
                    raise ContractError(f"{schema_id}: unknown {field}[{index}] fields {sorted(unknown_nested)}")
        for field, enums in schema.get("list_object_enums", {}).items():
            for index, item in enumerate(value.get(field, [])):
                for nested_field, options in enums.items():
                    if item.get(nested_field) not in options:
                        raise ContractError(f"{schema_id}: unknown {field}[{index}].{nested_field} value")
        for field, string_fields in schema.get("list_object_string_fields", {}).items():
            for index, item in enumerate(value.get(field, [])):
                for nested_field in string_fields:
                    if not isinstance(item.get(nested_field), str) or not item[nested_field]:
                        raise ContractError(f"{schema_id}: {field}[{index}].{nested_field} must be a non-empty string")
        for field, timestamp_fields in schema.get("list_object_offset_timestamp_fields", {}).items():
            for index, item in enumerate(value.get(field, [])):
                for nested_field in timestamp_fields:
                    try:
                        parsed = datetime.fromisoformat(str(item.get(nested_field, "")).replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise ContractError(f"{schema_id}: invalid timestamp {field}[{index}].{nested_field}") from exc
                    if parsed.tzinfo is None or parsed.utcoffset() is None:
                        raise ContractError(f"{schema_id}: {field}[{index}].{nested_field} must include a UTC offset")
        for earlier, later in schema.get("ordered_time_fields", []):
            try:
                earlier_value = datetime.fromisoformat(str(value[earlier]).replace("Z", "+00:00"))
                later_value = datetime.fromisoformat(str(value[later]).replace("Z", "+00:00"))
            except (KeyError, ValueError) as exc:
                raise ContractError(f"{schema_id}: invalid timestamp order {earlier}/{later}") from exc
            if earlier_value > later_value:
                raise ContractError(f"{schema_id}: {later} precedes {earlier}")
        for condition in schema.get("conditional_required", []):
            if value.get(condition["field"]) == condition["equals"]:
                for field in condition["required"]:
                    if value.get(field) is None:
                        raise ContractError(f"{schema_id}: {field} required by condition")
        for condition in schema.get("conditional_values", []):
            if value.get(condition["field"]) == condition["equals"] and value.get(condition["target"]) != condition["value"]:
                raise ContractError(f"{schema_id}: {condition['target']} must be {condition['value']} by condition")
        for group in schema.get("all_or_none", []):
            present = [field for field in group if field in value]
            if present and len(present) != len(group):
                raise ContractError(f"{schema_id}: fields must appear together: {group}")
        if schema_id == "envelope" and value.get("rollout_milestone") == "K4.1":
            from .merge_bridge import validate_k41_envelope

            validate_k41_envelope(value)
        elif schema_id == "handback" and value.get("rollout_milestone") == "K4.1":
            if not re.fullmatch(r"github:pr/[1-9][0-9]*", str(value.get("pr_ref", ""))):
                raise ContractError("handback: pr_ref must bind a positive post-freeze PR")
        elif schema_id == "mission":
            self._validate_mission_shape(value)
        elif schema_id == "readiness-profile":
            self._validate_readiness_profile_shape(value)
        elif schema_id == "readiness-receipt":
            self._validate_readiness_receipt_shape(value)
        elif schema_id == "launcher-v4":
            self._validate_launcher_v4_shape(value)
        elif schema_id == "checker-session-lifecycle":
            self._validate_checker_session_lifecycle_shape(value)
        elif schema_id == "merge-gate":
            from .merge_bridge import validate_merge_gate

            validate_merge_gate(value)
        elif schema_id == "merge-decision":
            # Delayed import avoids a module cycle while keeping the public
            # registry validator aligned with the specialized K4.1 consumer.
            from .merge_bridge import validate_merge_decision

            validate_merge_decision(value)
        elif schema_id == "merge-decision-attestation":
            # Cross-record digest/session validation is performed by the
            # dispatch boundary after this public shape validation.
            pass
        elif schema_id == "process-attested-merge":
            if value.get("outcome") == "merged" and value.get("merge_commit_sha") is None:
                raise ContractError("process-attested-merge: merged outcome lacks merge commit")
            if value.get("outcome") != "merged" and value.get("merge_commit_sha") is not None:
                raise ContractError("process-attested-merge: non-merged outcome cannot claim a merge commit")
            if value.get("dispatch_mode") == "reconcile-only" and value.get("outcome") != "ambiguous":
                raise ContractError("process-attested-merge: reconciliation must remain ambiguous")
            if value.get("dispatch_mode") == "reconcile-only" and value.get("ambiguous_response_observed") is not True:
                raise ContractError("process-attested-merge: reconciliation must record ambiguity")
            if (value.get("outcome") == "ambiguous") != (value.get("ambiguous_response_observed") is True):
                raise ContractError("process-attested-merge: outcome and ambiguity flag disagree")

    @staticmethod
    def _exact_nested(value: Any, fields: set[str], label: str) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != fields:
            raise ContractError(f"{label}: fields must be exactly {sorted(fields)}")
        return value

    @classmethod
    def _validate_mission_shape(cls, value: dict[str, Any]) -> None:
        revision = value.get("revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ContractError("mission: revision must be positive")
        prior = value.get("prior_digest")
        if (revision == 1 and prior is not None) or (revision > 1 and not SHA256.fullmatch(str(prior))):
            raise ContractError("mission: prior digest does not match revision")
        cls._exact_nested(value.get("controller"), {"generation", "workspace_id", "session_id"}, "mission.controller")
        controller = value["controller"]
        if (
            not isinstance(controller["generation"], int)
            or isinstance(controller["generation"], bool)
            or controller["generation"] < 1
            or any(not isinstance(controller[field], str) or not controller[field] for field in ("workspace_id", "session_id"))
        ):
            raise ContractError("mission: invalid controller")
        cls._exact_nested(value.get("authority"), {
            "command", "requested_tier", "effective_tier", "envelope_ref", "envelope_digest",
            "approval_receipt_ref", "policy_kind", "policy_ref", "policy_digest",
        }, "mission.authority")
        if any(not SHA256.fullmatch(str(value["authority"].get(field))) for field in ("envelope_digest", "policy_digest")):
            raise ContractError("mission: invalid authority digest")
        authority = value["authority"]
        if (
            any(not isinstance(authority[field], str) or not authority[field] for field in authority)
            or
            authority["command"] != "deliver-to-pr"
            or authority["requested_tier"] != "A"
            or authority["effective_tier"] != "A"
            or authority["policy_kind"] != "pilot-composite"
            or not authority["envelope_ref"].startswith("planning/")
            or not authority["approval_receipt_ref"]
            or not authority["policy_ref"]
        ):
            raise ContractError("mission: authority is not Tier A delivery")
        cls._exact_nested(value.get("aggregate"), {"phase", "status", "terminal_outcome", "wake_guard"}, "mission.aggregate")
        aggregate = value["aggregate"]
        phase = aggregate["phase"]
        status = aggregate["status"]
        terminal_outcome = aggregate["terminal_outcome"]
        wake_guard = aggregate["wake_guard"]
        if phase not in MISSION_PHASES or status not in MISSION_STATUSES:
            raise ContractError("mission: invalid aggregate phase or status")
        if phase == "complete":
            if status not in {"complete", "cancelled"}:
                raise ContractError("mission: complete phase requires a terminal status")
            if terminal_outcome not in MISSION_TERMINAL_OUTCOMES:
                raise ContractError("mission: complete phase requires a recognized terminal outcome")
            if (status == "cancelled") != (terminal_outcome == "cancelled"):
                raise ContractError("mission: terminal status and outcome disagree")
        elif status in {"complete", "cancelled"} or terminal_outcome is not None:
            raise ContractError("mission: terminal status or outcome requires complete phase")
        if status in {"running", "complete", "cancelled"}:
            if wake_guard is not None:
                raise ContractError("mission: active or terminal status cannot have a wake guard")
        elif not isinstance(wake_guard, str) or not wake_guard:
            raise ContractError("mission: paused status requires a wake guard")
        cls._exact_nested(value.get("candidate"), {
            "head_sha", "tree_sha", "base_sha", "policy_sha", "ruleset_fingerprint", "merge_group_sha",
            "verification_environment_digest", "frozen_at", "builder_session_ids",
        }, "mission.candidate")
        builders = value["candidate"]["builder_session_ids"]
        if not isinstance(builders, list) or any(not isinstance(item, str) or not item for item in builders):
            raise ContractError("mission: invalid candidate builder sessions")
        findings = value.get("findings")
        finding_fields = {"schema_version", "finding_id", "severity", "class", "evidence_digest", "locator", "status"}
        if not isinstance(findings, list):
            raise ContractError("mission: invalid findings")
        for item in findings:
            if not isinstance(item, dict) or set(item) != finding_fields:
                raise ContractError("mission: invalid findings")
            if item["schema_version"] != 1 or item["status"] not in {"open", "closed"} or not SHA256.fullmatch(str(item["evidence_digest"])):
                raise ContractError("mission: invalid finding status or digest")
            if any(not isinstance(item[field], str) or not item[field] for field in ("finding_id", "severity", "class")):
                raise ContractError("mission: invalid finding identity")
            locator = item["locator"]
            if not isinstance(locator, dict) or set(locator) != {"type", "value"} or any(
                not isinstance(locator[field], str) or not locator[field] for field in ("type", "value")
            ):
                raise ContractError("mission: invalid finding locator")
        interrupts = value.get("interrupts")
        interrupt_required = {
            "schema_version", "interrupt_id", "mission_id", "phase", "trigger", "evidence_refs", "blast_radius",
            "dispositions", "recommended", "status",
        }
        if not isinstance(interrupts, list):
            raise ContractError("mission: invalid interrupts")
        for item in interrupts:
            if not isinstance(item, dict) or not interrupt_required <= set(item) or set(item) - interrupt_required != ({"answer_ref"} if "answer_ref" in item else set()):
                raise ContractError("mission: invalid interrupts")
            if item["schema_version"] != 1 or item["status"] not in {"open", "resolved"} or any(
                not isinstance(item[field], list) for field in ("evidence_refs", "dispositions")
            ):
                raise ContractError("mission: invalid interrupt status or evidence")
            if any(
                not isinstance(item[field], str) or not item[field]
                for field in ("interrupt_id", "mission_id", "phase", "trigger", "blast_radius", "recommended")
            ) or any(
                not isinstance(entry, str) or not entry
                for field in ("evidence_refs", "dispositions") for entry in item[field]
            ):
                raise ContractError("mission: invalid interrupt identity")
            if "answer_ref" in item and (not isinstance(item["answer_ref"], str) or not item["answer_ref"]):
                raise ContractError("mission: invalid interrupt answer")
        actions = value.get("required_actions")
        if not isinstance(actions, list) or any(not isinstance(item, str) or not item for item in actions):
            raise ContractError("mission: invalid required actions")

    @classmethod
    def _validate_readiness_profile_shape(cls, value: dict[str, Any]) -> None:
        # Keep the public registry validator aligned with the generated exact
        # K3 schema; top-level validation alone is insufficient here.
        cloud = cls._exact_nested(value["cloud"], {
            "build_epoch_name", "expected_build_epoch", "setup_epoch_name", "expected_setup_epoch",
            "repository_setup_ref", "repository_setup_digest", "os_family", "required_environment", "tool_probes",
        }, "readiness-profile.cloud")
        for field in ("repository_setup_digest",):
            if not SHA256.fullmatch(str(cloud[field])):
                raise ContractError(f"readiness-profile.cloud: invalid {field}")
        if not isinstance(cloud["required_environment"], list) or not isinstance(cloud["tool_probes"], list):
            raise ContractError("readiness-profile.cloud: probes must be lists")
        for item in cloud["required_environment"]:
            cls._exact_nested(item, {"name", "kind", "probe"}, "readiness-profile.required_environment[]")
            if item["kind"] not in {"secret", "non-secret"} or item["probe"] != "presence-only":
                raise ContractError("readiness-profile: environment probes are presence-only")
        for item in cloud["tool_probes"]:
            cls._exact_nested(item, {"name", "command", "version"}, "readiness-profile.tool_probes[]")
        if not isinstance(value["services"], list) or not value["services"]:
            raise ContractError("readiness-profile.services must be non-empty")
        for service in value["services"]:
            cls._exact_nested(service, {"id", "start", "restart", "stop", "port", "healthcheck", "log_paths"}, "readiness-profile.services[]")
        data = cls._exact_nested(value["data"], {"migrate", "reset", "seed", "fixture_digest", "test_accounts_ref"}, "readiness-profile.data")
        if not SHA256.fullmatch(str(data["fixture_digest"])) or not str(data["test_accounts_ref"]).startswith("secret-ref:"):
            raise ContractError("readiness-profile.data bindings are invalid")
        cls._exact_nested(value["verification"], {"commands"}, "readiness-profile.verification")
        preview = cls._exact_nested(value["preview"], {"review_route", "health_url", "human_forward_sandbox_port"}, "readiness-profile.preview")
        if preview["review_route"] not in {"same-workspace-headless", "isolated-workspace-rebuild", "external-preview"}:
            raise ContractError("readiness-profile.preview: unknown review route")
        browser = cls._exact_nested(value["browser_review"], {"journeys_ref", "journeys_digest", "evidence"}, "readiness-profile.browser_review")
        if not SHA256.fullmatch(str(browser["journeys_digest"])):
            raise ContractError("readiness-profile.browser_review: invalid journeys digest")
        recovery = cls._exact_nested(value["recovery"], {"process_loss_probe", "process_loss_probe_digest", "resume", "resume_digest"}, "readiness-profile.recovery")
        if any(not SHA256.fullmatch(str(recovery[field])) for field in ("process_loss_probe_digest", "resume_digest")):
            raise ContractError("readiness-profile.recovery: invalid executable digest")

    @classmethod
    def _validate_readiness_receipt_shape(cls, value: dict[str, Any]) -> None:
        conditions = value["conditions"]
        expected = {f"CR{i}" for i in range(1, 11)}
        if not isinstance(conditions, dict) or set(conditions) != expected:
            raise ContractError("readiness-receipt.conditions must contain exactly CR1-CR10")
        for name, condition in conditions.items():
            cls._exact_nested(condition, {"outcome", "evidence_locators"}, f"readiness-receipt.{name}")
            if condition["outcome"] not in {"pass", "fail", "not-run", "reused"} or not isinstance(condition["evidence_locators"], list):
                raise ContractError(f"readiness-receipt.{name} is malformed")
        if not isinstance(value["raw_evidence_locators"], list) or not value["raw_evidence_locators"]:
            raise ContractError("readiness-receipt.raw_evidence_locators must be non-empty")

    @staticmethod
    def _validate_launcher_v4_shape(value: dict[str, Any]) -> None:
        if value["parent_context"] is not False or value["requested"] != value["runtime"]:
            raise ContractError("launcher-v4 requires a fresh session with matching runtime identity")
        if value["termination_state"] != "completed":
            raise ContractError("launcher-v4 requires a completed checker session")
        checkout = value["checkout"]
        for field in (
            "head_sha", "tree", "index_digest", "staged_diff_digest",
            "worktree_digest", "untracked", "noncheckpoint_refs_digest",
        ):
            if checkout[f"start_{field}"] != checkout[f"end_{field}"]:
                raise ContractError(f"launcher-v4: checkout mutated: {field}")
        candidate = value["candidate"]
        if not isinstance(candidate, dict) or checkout["start_tree"] != candidate.get("tree_sha"):
            raise ContractError("launcher-v4: checkout does not bind candidate tree")
        checkpoints = value["provider_checkpoints"]
        turn_id = checkpoints["turn_id"]
        if not isinstance(turn_id, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", turn_id):
            raise ContractError("launcher-v4: invalid checkpoint turn ID")
        prefix = f"refs/conductor-checkpoints/session-{value['session_id']}-turn-{turn_id}-"
        if checkpoints["start_ref"] != prefix + "start" or checkpoints["end_ref"] != prefix + "end":
            raise ContractError("launcher-v4: checkpoint refs do not bind session turn")
        if not re.fullmatch(r"[0-9a-f]{40}", checkpoints["start_commit"]) or not re.fullmatch(r"[0-9a-f]{40}", checkpoints["end_commit"]):
            raise ContractError("launcher-v4: invalid checkpoint commit")
        if checkpoints["start_tree"] != checkout["start_tree"] or checkpoints["end_tree"] != checkout["end_tree"]:
            raise ContractError("launcher-v4: checkpoint tree does not bind candidate")
        try:
            times = [
                datetime.fromisoformat(str(value["started_at"]).replace("Z", "+00:00")),
                datetime.fromisoformat(str(checkpoints["start_created_at"]).replace("Z", "+00:00")),
                datetime.fromisoformat(str(checkpoints["end_created_at"]).replace("Z", "+00:00")),
                datetime.fromisoformat(str(value["ended_at"]).replace("Z", "+00:00")),
            ]
        except ValueError as exc:
            raise ContractError("launcher-v4: invalid checkpoint chronology") from exc
        if any(item.tzinfo is None or item.utcoffset() is None for item in times) or times != sorted(times):
            raise ContractError("launcher-v4: checkpoint chronology is out of bounds")

    @staticmethod
    def _validate_checker_session_lifecycle_shape(value: dict[str, Any]) -> None:
        if value["all_required_commands_completed"] is not True or value["all_exit_codes_observed"] is not True or value["child_processes_reaped"] is not True:
            raise ContractError("checker-session-lifecycle: command completion is not fully observed")
        if value["completion_marker"] != "checker-session-complete/v1":
            raise ContractError("checker-session-lifecycle: invalid completion marker")

"""Cloud readiness contracts, invalidation, and recovery decisions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import digest
from .contracts import ContractError, ContractRegistry, SHA256
from .verification import candidate_readiness_selection


CR_IDS = tuple(f"CR{i}" for i in range(1, 11))
REVIEW_ROUTES = {"same-workspace-headless", "isolated-workspace-rebuild", "external-preview"}
PROFILE_REFS = (
    ("cloud", "repository_setup_ref", "repository_setup_digest"),
    ("browser_review", "journeys_ref", "journeys_digest"),
    ("recovery", "process_loss_probe", "process_loss_probe_digest"),
    ("recovery", "resume", "resume_digest"),
)
FORBIDDEN_SECRET_KEYS = {"value", "secret_value", "password", "token", "cookie", "authorization", "credential"}


def _nonempty(value: Any, label: str) -> Any:
    if value in (None, "", [], {}):
        raise ContractError(f"readiness profile: missing {label}")
    return value


def _exact_object(value: Any, required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"readiness profile: {label} must be an object")
    missing = required - set(value)
    unknown = set(value) - required
    if missing:
        raise ContractError(f"readiness profile: missing {label} fields {sorted(missing)}")
    if unknown:
        raise ContractError(f"readiness profile: unknown {label} fields {sorted(unknown)}")
    return value


def _reject_secret_values(value: Any, path: str = "profile") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            if lowered in FORBIDDEN_SECRET_KEYS or lowered.endswith(("_password", "_token", "_cookie", "_credential")):
                raise ContractError(f"readiness profile: secret-bearing field forbidden at {path}.{key}")
            _reject_secret_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_values(child, f"{path}[{index}]")


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_bound_file(project: Path, ref: str, expected: str, label: str) -> None:
    if not isinstance(ref, str) or not ref or ref.startswith(("secret-ref:", "/")) or ".." in Path(ref).parts:
        raise ContractError(f"readiness profile: invalid {label} reference")
    if not SHA256.fullmatch(str(expected)):
        raise ContractError(f"readiness profile: invalid {label} digest")
    path = project / ref
    if not path.is_file():
        raise ContractError(f"readiness profile: unresolved {label} reference {ref}")
    if _file_digest(path) != expected:
        raise ContractError(f"readiness profile: digest mismatch for {ref}")


def validate_readiness_profile(
    profile: dict[str, Any], project: Path, registry: ContractRegistry, expected_digest: str | None = None
) -> str:
    """Validate the exact K3 profile and all content-bound references."""

    _reject_secret_values(profile)
    registry.validate("readiness-profile", profile)
    if expected_digest is not None and digest(profile) != expected_digest:
        raise ContractError("readiness profile digest does not match the envelope")
    cloud = _exact_object(profile["cloud"], {
        "build_epoch_name", "expected_build_epoch", "setup_epoch_name", "expected_setup_epoch",
        "repository_setup_ref", "repository_setup_digest", "os_family", "required_environment", "tool_probes",
    }, "cloud")
    for field in ("build_epoch_name", "expected_build_epoch", "setup_epoch_name", "expected_setup_epoch", "os_family"):
        _nonempty(cloud[field], f"cloud.{field}")
    if not isinstance(cloud["required_environment"], list) or not isinstance(cloud["tool_probes"], list):
        raise ContractError("readiness profile: environment and tool probes must be lists")
    env_names: set[str] = set()
    for item in cloud["required_environment"]:
        item = _exact_object(item, {"name", "kind", "probe"}, "cloud.required_environment[]")
        name = _nonempty(item["name"], "required environment name")
        if name in env_names:
            raise ContractError(f"readiness profile: duplicate environment name {name}")
        env_names.add(name)
        if item["kind"] not in {"secret", "non-secret"} or item["probe"] != "presence-only":
            raise ContractError("readiness profile: environment probes are presence-only")
    tool_names: set[str] = set()
    for item in cloud["tool_probes"]:
        item = _exact_object(item, {"name", "command", "version"}, "cloud.tool_probes[]")
        name = _nonempty(item["name"], "tool name")
        if name in tool_names:
            raise ContractError(f"readiness profile: duplicate tool probe {name}")
        tool_names.add(name)
        _nonempty(item["command"], "tool command")
        _nonempty(item["version"], "tool constraint")

    if not isinstance(profile["services"], list) or not profile["services"]:
        raise ContractError("readiness profile: services must be a non-empty list")
    service_ids: set[str] = set()
    for item in profile["services"]:
        item = _exact_object(item, {"id", "start", "restart", "stop", "port", "healthcheck", "log_paths"}, "services[]")
        service_id = _nonempty(item["id"], "service id")
        if service_id in service_ids:
            raise ContractError(f"readiness profile: duplicate service {service_id}")
        service_ids.add(service_id)
        if not isinstance(item["port"], int) or isinstance(item["port"], bool) or not 1 <= item["port"] <= 65535:
            raise ContractError(f"readiness profile: invalid port for {service_id}")
        for field in ("start", "restart", "stop", "healthcheck"):
            _nonempty(item[field], f"services.{service_id}.{field}")
        if not isinstance(item["log_paths"], list) or not item["log_paths"]:
            raise ContractError(f"readiness profile: {service_id} requires log paths")

    data = _exact_object(profile["data"], {"migrate", "reset", "seed", "fixture_digest", "test_accounts_ref"}, "data")
    for field in ("migrate", "reset", "seed", "test_accounts_ref"):
        _nonempty(data[field], f"data.{field}")
    if not SHA256.fullmatch(str(data["fixture_digest"])) or not str(data["test_accounts_ref"]).startswith("secret-ref:"):
        raise ContractError("readiness profile: data fixture digest or test-account reference is invalid")

    verification = _exact_object(profile["verification"], {"commands"}, "verification")
    if not isinstance(verification["commands"], list) or not verification["commands"] or any(not isinstance(x, str) or not x for x in verification["commands"]):
        raise ContractError("readiness profile: verification commands must be non-empty strings")
    preview = _exact_object(profile["preview"], {"review_route", "health_url", "human_forward_sandbox_port"}, "preview")
    if preview["review_route"] not in REVIEW_ROUTES:
        raise ContractError("readiness profile: unknown review route")
    if not isinstance(preview["human_forward_sandbox_port"], int) or isinstance(preview["human_forward_sandbox_port"], bool):
        raise ContractError("readiness profile: preview port must be an integer")
    browser = _exact_object(profile["browser_review"], {"journeys_ref", "journeys_digest", "evidence"}, "browser_review")
    required_evidence = {"assertions", "screenshots", "console", "failed-network", "trace"}
    if set(browser["evidence"]) != required_evidence:
        raise ContractError("readiness profile: browser evidence set is incomplete")
    recovery = _exact_object(profile["recovery"], {"process_loss_probe", "process_loss_probe_digest", "resume", "resume_digest"}, "recovery")
    if not isinstance(profile["local_only_dependencies"], list):
        raise ContractError("readiness profile: local_only_dependencies must be a list")

    for parent, ref_field, digest_field in PROFILE_REFS:
        container = profile[parent]
        _resolve_bound_file(project, container[ref_field], container[digest_field], f"{parent}.{ref_field}")
    _resolve_bound_file(project, profile["cleanup"], profile["cleanup_digest"], "cleanup")
    return digest(profile)


def _parse_time(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ContractError(f"readiness receipt: invalid {field}") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractError(f"readiness receipt: {field} must include a UTC offset")
    return result


def validate_readiness_receipt(
    receipt: dict[str, Any], profile: dict[str, Any], registry: ContractRegistry,
    *, expected_candidate: dict[str, Any] | None = None, required_conditions: set[str] | None = None,
    tier: str = "A",
) -> None:
    registry.validate("readiness-receipt", receipt)
    if receipt["profile_id"] != profile["profile_id"] or receipt["profile_digest"] != digest(profile):
        raise ContractError("readiness receipt does not bind the profile")
    cloud = profile["cloud"]
    if receipt["observed_build_epoch"] != cloud["expected_build_epoch"] or receipt["observed_setup_epoch"] != cloud["expected_setup_epoch"]:
        raise ContractError("readiness receipt Cloud epoch mismatch")
    conditions = receipt["conditions"]
    if not isinstance(conditions, dict) or set(conditions) != set(CR_IDS):
        raise ContractError("readiness receipt must contain exactly CR1-CR10")
    for condition_id, condition in conditions.items():
        if not isinstance(condition, dict) or set(condition) != {"outcome", "evidence_locators"}:
            raise ContractError(f"readiness receipt: malformed {condition_id}")
        if condition["outcome"] not in {"pass", "fail", "not-run", "reused"}:
            raise ContractError(f"readiness receipt: unknown {condition_id} outcome")
        if not isinstance(condition["evidence_locators"], list):
            raise ContractError(f"readiness receipt: malformed {condition_id} locators")
    required = set(CR_IDS) if receipt["mode"] == "admission" else set(required_conditions or ())
    if receipt["mode"] == "candidate" and not required:
        raise ContractError("candidate readiness receipt lacks required-condition binding")
    failed = sorted(item for item in required if item not in conditions or conditions[item]["outcome"] != "pass")
    if failed:
        raise ContractError(f"readiness receipt: required conditions did not pass {failed}")
    if not isinstance(receipt["raw_evidence_locators"], list) or not receipt["raw_evidence_locators"]:
        raise ContractError("readiness receipt lacks raw evidence locators")
    if not isinstance(receipt["bound_digests"], dict) or any(not SHA256.fullmatch(str(value)) for value in receipt["bound_digests"].values()):
        raise ContractError("readiness receipt bound digests are malformed")
    if not isinstance(receipt["environment_presence"], dict) or any(value is not True for value in receipt["environment_presence"].values()):
        raise ContractError("readiness receipt environment probes must contain presence booleans only")
    required_environment = {item["name"] for item in profile["cloud"]["required_environment"]}
    if set(receipt["environment_presence"]) != required_environment:
        raise ContractError("readiness receipt environment-name set mismatch")
    if not isinstance(receipt["fingerprints"], dict) or not receipt["fingerprints"]:
        raise ContractError("readiness receipt fingerprints are missing")
    declared_locators = {locator for condition in conditions.values() for locator in condition["evidence_locators"]}
    if not declared_locators.issubset(set(receipt["raw_evidence_locators"])):
        raise ContractError("readiness receipt condition evidence is not retained")
    if receipt["review_route"] != profile["preview"]["review_route"]:
        raise ContractError("readiness receipt review route mismatch")
    started = _parse_time(receipt["started_at"], "started_at")
    ended = _parse_time(receipt["ended_at"], "ended_at")
    expires = _parse_time(receipt["expires_at"], "expires_at")
    if not started <= ended < expires or expires - ended > timedelta(days=30):
        raise ContractError("readiness receipt chronology or TTL is invalid")
    issuer = receipt["issuer"]
    if tier == "A":
        if not (issuer.startswith("process-attested:") or issuer.startswith("protected-store:")):
            raise ContractError("Tier A readiness issuer is unsupported")
    elif not issuer.startswith("protected-store:"):
        raise ContractError("Tier B/C readiness requires a protected issuer")
    if receipt["mode"] == "candidate":
        candidate = receipt.get("candidate")
        if not isinstance(candidate, dict) or expected_candidate is None or candidate != expected_candidate:
            raise ContractError("candidate readiness receipt tuple mismatch")


def admission_reuse(
    receipt: dict[str, Any], profile: dict[str, Any], *, now: datetime, observed_environment_names: set[str]
) -> tuple[bool, str]:
    cloud = profile["cloud"]
    if not receipt.get("observed_build_epoch") or not receipt.get("observed_setup_epoch"):
        return False, "Cloud epochs are absent or unobservable"
    if receipt["observed_build_epoch"] != cloud["expected_build_epoch"] or receipt["observed_setup_epoch"] != cloud["expected_setup_epoch"]:
        return False, "Cloud epoch changed"
    if receipt.get("profile_digest") != digest(profile):
        return False, "readiness profile changed"
    required = {item["name"] for item in cloud["required_environment"]}
    if required != observed_environment_names:
        return False, "required environment names changed or are absent"
    if _parse_time(receipt["expires_at"], "expires_at") <= now.astimezone(timezone.utc):
        return False, "admission receipt expired"
    return True, "admission receipt is current"


def candidate_condition_plan(changed_inputs: set[str], admission_current: bool, epochs_observable: bool) -> dict[str, Any]:
    return candidate_readiness_selection(changed_inputs, admission_current, epochs_observable)


def runtime_recovery_decision(*, health: str, resume_exit: int | None, post_resume_health: str | None) -> dict[str, Any]:
    """Return the only permitted continuation after Cloud process loss."""

    if health == "healthy":
        return {"outcome": "ready", "required": ["CR7", "CR8"], "resume_dispatched": False}
    if health != "unhealthy":
        raise ContractError("Cloud runtime health is ambiguous")
    if resume_exit is None:
        return {"outcome": "resume-required", "required": ["CR7", "CR8"], "resume_dispatched": False}
    if resume_exit != 0 or post_resume_health != "healthy":
        return {"outcome": "blocked", "required": ["CR7", "CR8"], "resume_dispatched": True}
    return {"outcome": "ready", "required": ["CR7", "CR8"], "resume_dispatched": True}

"""Thin, checked command boundary for Pilot A delivery."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, digest, load_strict
from .authority import validate_approval
from .checker import (
    validate_checker_session_lifecycle,
    validate_launcher_receipt,
    validate_launcher_v3_receipt,
    validate_launcher_v4_receipt,
)
from .completion import issue_handback, register_attempt
from .cloud import CR_IDS, runtime_recovery_decision, validate_readiness_profile, validate_readiness_receipt
from .conductor_api import ConductorApiClient, session_completion
from .cloud_runner import CloudReadinessRunner
from .contracts import ContractError, ContractRegistry
from .gates import evaluate_gates, simulate_g9
from .git_control import GitControlStore
from .github_merge import GitHubCliDecisionStore, GitHubCliMergeHost
from .merge_bridge import (
    dispatch_merge,
    issue_merge_decision,
    validate_merge_decision,
    validate_merge_decision_attestation,
)
from .state import MissionStore, transition
from .verification import candidate_readiness_selection


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _registry() -> ContractRegistry:
    return ContractRegistry.load(_skill_root() / "contracts" / "registry.yml")


def _read(path: Path) -> dict[str, Any]:
    return load_strict(path.read_bytes())


def _result(outcome: str, next_phase: str | None, required_actions: list[str], **extra: Any) -> dict[str, Any]:
    return {"outcome": outcome, "next_phase": next_phase, "required_actions": required_actions, **extra}


def _resolve_contract(project: Path, explicit: Path | None, name: str) -> Path | None:
    if explicit:
        return explicit.resolve()
    direct = project / "planning" / name
    if direct.exists():
        return direct
    matches = sorted((project / "planning").glob(f"*/{name}")) if (project / "planning").exists() else []
    if len(matches) > 1:
        raise ContractError(f"multiple {name} records; pass an explicit path")
    return matches[0] if matches else None


def _project_reference(project: Path, reference: str) -> Path:
    path = (project / reference).resolve()
    if not path.is_relative_to(project.resolve()):
        raise ContractError("observation contract reference escapes the project")
    return path


def _trusted_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"invalid {label} timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ContractError(f"{label} timestamp must include a UTC offset")
    return parsed


def preflight(project: Path, envelope_arg: Path | None = None, approval_arg: Path | None = None) -> dict[str, Any]:
    actions: list[str] = []
    lock = _skill_root() / "manifest-lock.yml"
    if not lock.exists():
        actions.append("reinstall the manifest-owned pilot pack")
    envelope_path = _resolve_contract(project, envelope_arg, "delivery-envelope.yml")
    approval_path = _resolve_contract(project, approval_arg, "delivery-approval.json")
    if envelope_path is None or not envelope_path.exists():
        actions.append("produce planning/{feature}/delivery-envelope.yml through stages 04–06")
    if approval_path is None or not approval_path.exists():
        actions.append("record planning/{feature}/delivery-approval.json from an authorized source event")
    if actions:
        return _result("blocked", None, actions, effective_tier=None)
    registry = _registry()
    envelope = _read(envelope_path)
    approval = _read(approval_path)
    registry.validate("envelope", envelope)
    registry.validate("approval", approval)
    validate_approval(envelope, approval)
    observation = envelope["observation"]
    observation_path = _project_reference(project, observation["contract_ref"])
    if not observation_path.exists():
        actions.append(f"create the declared observation contract at {observation['contract_ref']}")
        observation_contract = None
    else:
        observation_contract = _read(observation_path)
        registry.validate("pilot-observation-contract", observation_contract)
        if observation["contract_digest"] != digest(observation_contract):
            actions.append("refresh the stale observation contract digest and envelope approval")
        declared_at = _trusted_time(observation_contract["declared_at"], "observation declaration")
        approved_at = _trusted_time(approval["approved_at"], "approval")
        if declared_at > approved_at:
            actions.append("declare the observation contract before envelope approval")
    if envelope.get("rollout_milestone") == "K4.1":
        bridge = {
            "rollout_milestone": "K4.1",
            "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge",
        }
        if any(envelope.get(field) != value for field, value in bridge.items()):
            actions.append("bind the complete K4.1 fresh-agent merge authority class")
        authority = envelope.get("authority", {})
        if authority.get("maximum") != "merge" or authority.get("builder_maximum") != "open-pr" or authority.get("coordinator_maximum") != "open-pr":
            actions.append("cap builder and coordinator at open-pr while reserving merge for the fresh merge agent")
    elif envelope["authority"].get("maximum") != "open-pr":
        actions.append("approve a Tier A envelope capped at open-pr for Pilot A")
    if envelope["constraints"].get("coordinator_venue") == "cloud":
        readiness = envelope.get("evidence", {}).get("cloud_readiness")
        if not readiness:
            actions.append("supply a current CR1–CR10 Cloud admission receipt")
    if approval.get("envelope_digest") != digest(envelope):
        actions.append("refresh the stale envelope approval")
    if approval.get("actor_id") not in envelope["authority"].get("authorized_human_ids", []):
        actions.append("obtain approval from an authorized human")
    return _result("blocked" if actions else "ready", "authorized" if not actions else None, actions, effective_tier="A")


def validate_record(schema_id: str, path: Path) -> dict[str, Any]:
    value = _read(path)
    _registry().validate(schema_id, value)
    return _result("valid", None, [], schema_id=schema_id, digest=digest(value))


def k41_decision_from_files(
    envelope_path: Path,
    approval_path: Path,
    attempt_path: Path,
    gate_path: Path,
    handback_path: Path,
    launcher_path: Path,
    policy_path: Path,
    standing_authority_path: Path,
    facts_path: Path,
    issued_at: str,
) -> dict[str, Any]:
    registry = _registry()
    records = {
        "envelope": _read(envelope_path),
        "approval": _read(approval_path),
        "pilot-attempt": _read(attempt_path),
        "merge-gate": _read(gate_path),
        "handback": _read(handback_path),
        "k41-standing-authority": _read(standing_authority_path),
    }
    for schema_id, value in records.items():
        registry.validate(schema_id, value)
    launcher = _read(launcher_path)
    if launcher.get("schema_version") == 2:
        registry.validate("launcher", launcher)
        validate_launcher_receipt(launcher, tier="A")
    elif launcher.get("schema_version") == 3:
        registry.validate("launcher-v3", launcher)
        validate_launcher_v3_receipt(launcher, tier="A")
    elif launcher.get("schema_version") == 4:
        registry.validate("launcher-v4", launcher)
        validate_launcher_v4_receipt(launcher, tier="A")
    else:
        raise ContractError("K4.1 requires a valid Launcher V2, V3, or V4 receipt")
    policy = _read(policy_path)
    facts = _read(facts_path)
    if not isinstance(facts.get("repository"), str) or not isinstance(facts.get("pr_number"), int):
        raise ContractError("K4.1 facts require a repository and integer PR number")
    host_adapter = GitHubCliMergeHost(
        merge_method=records["envelope"].get("authority", {}).get("merge", {}).get("method"),
        standing_authority=records["k41-standing-authority"],
        expected_controller_generation=facts.get("controller_generation"),
        expected_candidate=records["merge-gate"]["candidate"],
        expected_envelope_digest=digest(records["envelope"]),
        mission_id=records["pilot-attempt"]["mission_id"],
    )
    observed_host = host_adapter.inspect(facts.get("repository"), facts.get("pr_number"))
    facts = dict(
        facts,
        host=observed_host,
        changed_paths=observed_host.get("changed_paths"),
        controller_generation=observed_host.get("controller_generation"),
        builder_session_ids=observed_host.get("builder_session_ids"),
        coordinator_session_id=observed_host.get("coordinator_session_id"),
        control_ref=observed_host.get("control_ref"),
        control_commit=observed_host.get("control_commit"),
        control_digest=observed_host.get("control_digest"),
    )
    for field in (
        "pr_open", "mergeable", "checks_pass", "review_threads_closed", "reviews_clear",
        "standing_authority_current", "default_branch_policy_current", "kill_switch_enabled",
        "generation_current",
        "findings_closed", "required_actions_closed",
    ):
        facts[field] = observed_host.get(field)
    decision = issue_merge_decision(
        envelope=records["envelope"],
        approval=records["approval"],
        attempt=records["pilot-attempt"],
        gate=records["merge-gate"],
        handback=records["handback"],
        launcher=launcher,
        policy=policy,
        standing_authority=records["k41-standing-authority"],
        facts=facts,
        issued_at=issued_at,
    )
    registry.validate("merge-decision", decision)
    return _result(decision["decision"], None, decision["reason_codes"] if decision["decision"] == "deny" else [], decision=decision, decision_digest=digest(decision))


def k41_merge_from_files(
    decision_path: Path,
    standing_authority_path: Path,
    decision_attestation_path: Path,
    current_session_id: str | None = None,
) -> dict[str, Any]:
    registry = _registry()
    decision = _read(decision_path)
    standing_authority = _read(standing_authority_path)
    decision_attestation = _read(decision_attestation_path)
    registry.validate("merge-decision", decision)
    registry.validate("k41-standing-authority", standing_authority)
    registry.validate("merge-decision-attestation", decision_attestation)
    validate_merge_decision(decision)
    validate_merge_decision_attestation(decision_attestation, decision)
    GitHubCliDecisionStore().verify(decision_attestation, decision)
    if decision["standing_authority_digest"] != digest(standing_authority):
        raise ContractError("merge decision does not bind the standing authority")
    host = GitHubCliMergeHost(
        merge_method=decision["merge_method"],
        standing_authority=standing_authority,
        expected_controller_generation=decision["controller_generation"],
        expected_candidate=decision["expected_candidate"],
        expected_envelope_digest=decision["envelope_digest"],
        mission_id=decision["mission_id"],
    )
    session_id = current_session_id or os.environ.get("CONDUCTOR_SESSION_ID")
    receipt = dispatch_merge(decision, host, session_id)
    registry.validate("process-attested-merge", receipt)
    return _result(receipt["outcome"], None, [] if receipt["outcome"] == "merged" else ["observe and reconcile the host outcome before any retry"], receipt=receipt, receipt_digest=digest(receipt))


def k41_persist_decision(decision_path: Path, attestation_output: Path) -> dict[str, Any]:
    if attestation_output.exists():
        raise ContractError("decision attestation output already exists")
    if not attestation_output.parent.is_dir():
        raise ContractError("decision attestation output parent does not exist")
    registry = _registry()
    decision = _read(decision_path)
    registry.validate("merge-decision", decision)
    validate_merge_decision(decision)
    attestation = GitHubCliDecisionStore().persist(decision)
    registry.validate("merge-decision-attestation", attestation)
    validate_merge_decision_attestation(attestation, decision)
    try:
        with attestation_output.open("xb") as handle:
            handle.write(canonical_bytes(attestation) + b"\n")
    except OSError as exc:
        raise ContractError(f"cannot persist decision attestation: {exc}") from exc
    return _result("persisted", None, [], attestation=attestation, attestation_digest=digest(attestation))


def validate_launcher(path: Path, tier: str, expected_path: Path | None = None) -> dict[str, Any]:
    value = _read(path)
    expected = _read(expected_path) if expected_path else None
    if value.get("schema_version") == 2:
        schema_id = "launcher"
        validator = validate_launcher_receipt
    elif value.get("schema_version") == 3:
        schema_id = "launcher-v3"
        validator = validate_launcher_v3_receipt
    elif value.get("schema_version") == 4:
        schema_id = "launcher-v4"
        validator = validate_launcher_v4_receipt
    else:
        raise ContractError("launcher: unknown schema_version")
    _registry().validate(schema_id, value)
    validator(value, tier=tier, expected=expected)
    return _result("valid", None, [], schema_id=schema_id, digest=digest(value))


def validate_checker_lifecycle(launcher_path: Path, lifecycle_path: Path) -> dict[str, Any]:
    registry = _registry()
    launcher = _read(launcher_path)
    lifecycle = _read(lifecycle_path)
    registry.validate("launcher-v4", launcher)
    registry.validate("checker-session-lifecycle", lifecycle)
    validate_checker_session_lifecycle(lifecycle, launcher)
    return _result(
        "valid", None, [], launcher_digest=digest(launcher), lifecycle_digest=digest(lifecycle)
    )


def canonical_digest(path: Path) -> dict[str, Any]:
    value = _read(path)
    return _result("observed", None, [], digest=digest(value))


def gate_oracle(path: Path) -> dict[str, Any]:
    facts = _read(path)
    result = evaluate_gates(facts)
    return _result("pass" if result["pass"] else "fail", "pr-ready" if result["pass"] else "build", [], oracle=result)


def g9_oracle(path: Path) -> dict[str, Any]:
    result = simulate_g9(_read(path))
    return _result("pass" if result["would_authorize"] else "fail", None, [], simulation=result)


def control_init(repository: Path, control_ref: str, genesis: Path) -> dict[str, Any]:
    value = _read(genesis)
    snapshot = GitControlStore(repository, control_ref).create(value)
    return _result("created", "authorized", [], control_ref=control_ref, commit_sha=snapshot.commit_sha, digest=snapshot.digest)


def control_read(repository: Path, control_ref: str) -> dict[str, Any]:
    snapshot = GitControlStore(repository, control_ref).read()
    return _result("observed", snapshot.value.get("mission", snapshot.value).get("aggregate", {}).get("phase"), [], commit_sha=snapshot.commit_sha, digest=snapshot.digest, record=snapshot.value)


def control_write(repository: Path, control_ref: str, record: Path, expected_commit: str, expected_digest: str) -> dict[str, Any]:
    value = _read(record)
    snapshot = GitControlStore(repository, control_ref).write(expected_commit, expected_digest, value)
    return _result("checkpointed", value.get("mission", value).get("aggregate", {}).get("phase"), [], commit_sha=snapshot.commit_sha, digest=snapshot.digest)


def mission_transition(
    store_path: Path,
    expected_digest: str,
    phase: str,
    status: str,
    wake_guard: str | None,
    terminal_outcome: str | None,
    updated_at: str,
) -> dict[str, Any]:
    store = MissionStore(store_path)
    current = store.read()
    value = transition(
        current.value,
        phase,
        status=status,
        wake_guard=wake_guard,
        terminal_outcome=terminal_outcome,
    )
    snapshot = store.write(expected_digest, value, updated_at)
    return _result("checkpointed", phase, [], digest=snapshot.digest, revision=snapshot.value["revision"])


def readiness(changed: str, admission_current: bool, epochs_observable: bool) -> dict[str, Any]:
    selection = candidate_readiness_selection({item for item in changed.split(",") if item}, admission_current, epochs_observable)
    return _result("selected", "candidate-readiness", [], selection=selection)


def attempt_from_files(path: Path, contract_path: Path, envelope_path: Path, approval_path: Path) -> dict[str, Any]:
    value = _read(path)
    contract = _read(contract_path)
    envelope = _read(envelope_path)
    approval = _read(approval_path)
    registry = _registry()
    registry.validate("pilot-observation-contract", contract)
    registry.validate("envelope", envelope)
    registry.validate("approval", approval)
    validate_approval(envelope, approval)
    requested_version = value.pop("schema_version", 3)
    if requested_version != 3:
        raise ContractError("pilot-attempt: unknown schema_version")
    receipt = register_attempt(**value)
    registry.validate("pilot-attempt", receipt)
    if receipt["tier"] != "A":
        raise ContractError("Pilot A may register only Tier A attempts")
    if envelope.get("rollout_milestone") == "K4.1":
        for field in ("rollout_milestone", "authority_class", "maximum_action"):
            if receipt.get(field) != envelope.get(field):
                raise ContractError(f"K4.1 attempt {field} does not match the envelope")
    if receipt["venue"] != envelope["constraints"].get("coordinator_venue"):
        raise ContractError("attempt venue does not match the envelope coordinator venue")
    contract_digest = digest(contract)
    if receipt["attempt_id"] != contract["attempt_id"] or receipt["mission_id"] != contract["mission_id"]:
        raise ContractError("attempt and observation contract IDs do not match")
    if receipt["envelope_digest"] != digest(envelope):
        raise ContractError("attempt envelope digest does not match")
    if receipt["observation_contract_ref"] != envelope["observation"]["contract_ref"]:
        raise ContractError("attempt observation contract reference does not match the envelope")
    if receipt["observation_contract_digest"] != contract_digest or envelope["observation"]["contract_digest"] != contract_digest:
        raise ContractError("attempt observation contract digest does not match")
    declared_at = _trusted_time(contract["declared_at"], "observation declaration")
    approved_at = _trusted_time(approval["approved_at"], "approval")
    registered_at = _trusted_time(receipt["registered_at"], "attempt registration")
    if declared_at > registered_at:
        raise ContractError("attempt was registered before observation contract declaration")
    if declared_at > approved_at:
        raise ContractError("observation contract was declared after envelope approval")
    if approved_at > registered_at:
        raise ContractError("attempt was registered before envelope approval")
    return _result("registered", "authorized", [], receipt=receipt, receipt_digest=digest(receipt))


def observation_from_files(observation_path: Path, contract_path: Path, attempt_path: Path) -> dict[str, Any]:
    registry = _registry()
    observation = _read(observation_path)
    contract = _read(contract_path)
    attempt = _read(attempt_path)
    registry.validate("pilot-observation", observation)
    registry.validate("pilot-observation-contract", contract)
    registry.validate("pilot-attempt", attempt)
    contract_digest = digest(contract)
    if observation["attempt_id"] != attempt["attempt_id"] or contract["attempt_id"] != attempt["attempt_id"]:
        raise ContractError("observation, contract, and attempt IDs do not match")
    if contract["mission_id"] != attempt["mission_id"]:
        raise ContractError("observation contract and attempt mission IDs do not match")
    if attempt["observation_contract_digest"] != contract_digest or observation["observation_contract_digest"] != contract_digest:
        raise ContractError("observation contract digest binding does not match")
    declared_at = _trusted_time(contract["declared_at"], "observation declaration")
    registered_at = _trusted_time(attempt["registered_at"], "attempt registration")
    if registered_at < declared_at:
        raise ContractError("observation attempt predates its contract declaration")
    if observation["receipt_issuer"] != contract["receipt_issuer"]:
        raise ContractError("observation receipt issuer does not match the declared contract")
    if attempt["tier"] in {"B", "C"} and not observation["receipt_issuer"].startswith("protected-store:"):
        raise ContractError("Tier B/C observation receipts require a protected-store issuer")
    signal_ids = {item.get("id") for item in observation["signals"] if isinstance(item, dict)}
    missing_signals = set(contract["required_signals"]) - signal_ids
    if missing_signals:
        raise ContractError(f"observation is missing declared signals: {sorted(missing_signals)}")
    if not set(contract["raw_evidence_locators"]) <= set(observation["raw_evidence_locators"]):
        raise ContractError("observation is missing declared raw-evidence locators")
    started = _trusted_time(observation["window_started_at"], "observation window start")
    ended = _trusted_time(observation["window_ended_at"], "observation window end")
    if registered_at > started:
        raise ContractError("observation attempt was registered after its window started")
    if (ended - started).total_seconds() < contract["window_duration_hours"] * 3600:
        raise ContractError("observation window is shorter than the declared contract")
    matching_events = []
    for event in observation["host_events"]:
        occurred_at = _trusted_time(event["occurred_at"], "host event")
        if (
            event["event"] == contract["window_starts_on"]
            and event["subject_id"] == observation["merged_sha_or_release_id"]
            and occurred_at == started
        ):
            matching_events.append(event)
    if len(matching_events) != 1:
        raise ContractError("observation requires exactly one matching host start event")
    start_event = matching_events[0]
    if start_event["evidence_locator"] not in observation["raw_evidence_locators"]:
        raise ContractError("host start-event locator is absent from raw evidence")
    host_proof = observation["host_proof"]
    if host_proof["event_digest"] != digest(start_event):
        raise ContractError("host proof does not bind the host start event")
    if host_proof["evidence_locator"] != start_event["evidence_locator"]:
        raise ContractError("host proof locator does not match the host start event")
    return _result("valid", None, [], observation_digest=digest(observation), contract_digest=contract_digest)


def handback_from_file(path: Path) -> dict[str, Any]:
    receipt = issue_handback(**_read(path))
    _registry().validate("handback", receipt)
    return _result("pr_ready", "handback", [], receipt=receipt, receipt_digest=digest(receipt))


def readiness_profile_from_file(project: Path, path: Path, expected_digest: str | None) -> dict[str, Any]:
    profile = _read(path)
    profile_digest = validate_readiness_profile(profile, project, _registry(), expected_digest)
    return _result("valid", None, [], profile_id=profile["profile_id"], profile_digest=profile_digest)


def readiness_receipt_from_file(
    project: Path, profile_path: Path, receipt_path: Path, candidate_path: Path | None,
    required: str, tier: str,
) -> dict[str, Any]:
    profile = _read(profile_path)
    validate_readiness_profile(profile, project, _registry())
    receipt = _read(receipt_path)
    candidate = _read(candidate_path) if candidate_path else None
    required_conditions = {item for item in required.split(",") if item}
    validate_readiness_receipt(
        receipt, profile, _registry(), expected_candidate=candidate,
        required_conditions=required_conditions, tier=tier,
    )
    return _result("valid", None, [], readiness_id=receipt["readiness_id"], receipt_digest=digest(receipt))


def cloud_runtime_from_file(path: Path) -> dict[str, Any]:
    facts = _read(path)
    decision = runtime_recovery_decision(
        health=facts.get("health"), resume_exit=facts.get("resume_exit"),
        post_resume_health=facts.get("post_resume_health"),
    )
    required_actions = [] if decision["outcome"] == "ready" else ["restore runtime and re-establish CR7/CR8"]
    return _result(decision["outcome"], "candidate-readiness", required_actions, recovery=decision)


def cloud_session_from_file(path: Path) -> dict[str, Any]:
    facts = _read(path)
    if not isinstance(facts, dict):
        raise ContractError("Conductor session facts are malformed")
    outcome = session_completion(facts.get("status_history", []), facts.get("messages", []))
    actions = [] if outcome == "complete" else ["continue observing with the after-message cursor"]
    return _result(outcome, None, actions)


def cloud_run_from_files(project: Path, profile_path: Path, facts_path: Path, evidence_dir: Path) -> dict[str, Any]:
    profile = _read(profile_path)
    facts = _read(facts_path)
    receipt = CloudReadinessRunner(project, profile, evidence_dir, _registry()).run(facts)
    required = set(CR_IDS) if receipt["mode"] == "admission" else set(facts.get("required_conditions", []))
    validate_readiness_receipt(
        receipt, profile, _registry(), expected_candidate=facts.get("candidate"),
        required_conditions=required, tier=facts.get("tier", "A"),
    )
    return _result("valid", None, [], receipt=receipt, receipt_digest=digest(receipt))


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="ai-playbook-deliver")
    sub = cli.add_subparsers(dest="command", required=True)
    command = sub.add_parser("preflight")
    command.add_argument("--project", type=Path, required=True)
    command.add_argument("--envelope", type=Path)
    command.add_argument("--approval", type=Path)
    command = sub.add_parser("validate")
    command.add_argument("--schema", required=True)
    command.add_argument("--record", type=Path, required=True)
    command = sub.add_parser("validate-launcher")
    command.add_argument("--record", type=Path, required=True)
    command.add_argument("--tier", choices=("A", "B", "C"), required=True)
    command.add_argument("--expected", type=Path)
    command = sub.add_parser("validate-checker-lifecycle")
    command.add_argument("--launcher", type=Path, required=True)
    command.add_argument("--lifecycle", type=Path, required=True)
    command = sub.add_parser("k41-decide")
    command.add_argument("--envelope", type=Path, required=True)
    command.add_argument("--approval", type=Path, required=True)
    command.add_argument("--attempt", type=Path, required=True)
    command.add_argument("--gate", type=Path, required=True)
    command.add_argument("--handback", type=Path, required=True)
    command.add_argument("--launcher", type=Path, required=True)
    command.add_argument("--policy", type=Path, required=True)
    command.add_argument("--standing-authority", type=Path, required=True)
    command.add_argument("--facts", type=Path, required=True)
    command.add_argument("--issued-at", required=True)
    command = sub.add_parser("k41-merge")
    command.add_argument("--decision", type=Path, required=True)
    command.add_argument("--decision-attestation", type=Path, required=True)
    command.add_argument("--standing-authority", type=Path, required=True)
    command = sub.add_parser("k41-persist-decision")
    command.add_argument("--decision", type=Path, required=True)
    command.add_argument("--attestation-output", type=Path, required=True)
    command = sub.add_parser("canonical-digest")
    command.add_argument("--input", type=Path, required=True)
    command = sub.add_parser("gate-dry-run")
    command.add_argument("--facts", type=Path, required=True)
    command = sub.add_parser("g9-simulate")
    command.add_argument("--facts", type=Path, required=True)
    command = sub.add_parser("control-init")
    command.add_argument("--repository", type=Path, required=True)
    command.add_argument("--control-ref", required=True)
    command.add_argument("--genesis", type=Path, required=True)
    command = sub.add_parser("control-read")
    command.add_argument("--repository", type=Path, required=True)
    command.add_argument("--control-ref", required=True)
    command = sub.add_parser("control-write")
    command.add_argument("--repository", type=Path, required=True)
    command.add_argument("--control-ref", required=True)
    command.add_argument("--record", type=Path, required=True)
    command.add_argument("--expected-commit", required=True)
    command.add_argument("--expected-digest", required=True)
    command = sub.add_parser("mission-transition")
    command.add_argument("--store", type=Path, required=True)
    command.add_argument("--expected-digest", required=True)
    command.add_argument("--phase", required=True)
    command.add_argument("--status", default="running")
    command.add_argument("--wake-guard")
    command.add_argument("--terminal-outcome", choices=("delivered", "rolled_back", "merged_no_deploy", "pr_ready", "cancelled"))
    command.add_argument("--updated-at", required=True)
    command = sub.add_parser("readiness-select")
    command.add_argument("--changed", default="")
    command.add_argument("--admission-current", action="store_true")
    command.add_argument("--epochs-observable", action="store_true")
    command = sub.add_parser("register-attempt")
    command.add_argument("--input", type=Path, required=True)
    command.add_argument("--contract", type=Path, required=True)
    command.add_argument("--envelope", type=Path, required=True)
    command.add_argument("--approval", type=Path, required=True)
    command = sub.add_parser("validate-observation")
    command.add_argument("--observation", type=Path, required=True)
    command.add_argument("--contract", type=Path, required=True)
    command.add_argument("--attempt", type=Path, required=True)
    command = sub.add_parser("issue-handback")
    command.add_argument("--input", type=Path, required=True)
    command = sub.add_parser("cloud-profile-validate")
    command.add_argument("--project", type=Path, required=True)
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--expected-digest")
    command = sub.add_parser("cloud-receipt-validate")
    command.add_argument("--project", type=Path, required=True)
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--receipt", type=Path, required=True)
    command.add_argument("--candidate", type=Path)
    command.add_argument("--required", default="")
    command.add_argument("--tier", choices=("A", "B", "C"), default="A")
    command = sub.add_parser("cloud-runtime-reconcile")
    command.add_argument("--facts", type=Path, required=True)
    command = sub.add_parser("cloud-session-evaluate")
    command.add_argument("--facts", type=Path, required=True)
    command = sub.add_parser("cloud-readiness-run")
    command.add_argument("--project", type=Path, required=True)
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--facts", type=Path, required=True)
    command.add_argument("--evidence-dir", type=Path, required=True)
    sub.add_parser("conductor-capability-preflight")
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "preflight":
            result = preflight(args.project.resolve(), args.envelope, args.approval)
        elif args.command == "validate":
            result = validate_record(args.schema, args.record)
        elif args.command == "validate-launcher":
            result = validate_launcher(args.record, args.tier, args.expected)
        elif args.command == "k41-decide":
            result = k41_decision_from_files(
                args.envelope, args.approval, args.attempt, args.gate, args.handback,
                args.launcher, args.policy, args.standing_authority, args.facts, args.issued_at,
            )
        elif args.command == "k41-merge":
            result = k41_merge_from_files(args.decision, args.standing_authority, args.decision_attestation)
        elif args.command == "k41-persist-decision":
            result = k41_persist_decision(args.decision, args.attestation_output)
        elif args.command == "canonical-digest":
            result = canonical_digest(args.input)
        elif args.command == "gate-dry-run":
            result = gate_oracle(args.facts)
        elif args.command == "g9-simulate":
            result = g9_oracle(args.facts)
        elif args.command == "control-init":
            result = control_init(args.repository.resolve(), args.control_ref, args.genesis)
        elif args.command == "control-read":
            result = control_read(args.repository.resolve(), args.control_ref)
        elif args.command == "control-write":
            result = control_write(args.repository.resolve(), args.control_ref, args.record, args.expected_commit, args.expected_digest)
        elif args.command == "mission-transition":
            result = mission_transition(
                args.store, args.expected_digest, args.phase, args.status,
                args.wake_guard, args.terminal_outcome, args.updated_at,
            )
        elif args.command == "readiness-select":
            result = readiness(args.changed, args.admission_current, args.epochs_observable)
        elif args.command == "register-attempt":
            result = attempt_from_files(args.input, args.contract, args.envelope, args.approval)
        elif args.command == "validate-observation":
            result = observation_from_files(args.observation, args.contract, args.attempt)
        elif args.command == "validate-checker-lifecycle":
            result = validate_checker_lifecycle(args.launcher, args.lifecycle)
        elif args.command == "issue-handback":
            result = handback_from_file(args.input)
        elif args.command == "cloud-profile-validate":
            result = readiness_profile_from_file(args.project.resolve(), args.profile, args.expected_digest)
        elif args.command == "cloud-receipt-validate":
            result = readiness_receipt_from_file(args.project.resolve(), args.profile, args.receipt, args.candidate, args.required, args.tier)
        elif args.command == "cloud-runtime-reconcile":
            result = cloud_runtime_from_file(args.facts)
        elif args.command == "cloud-session-evaluate":
            result = cloud_session_from_file(args.facts)
        elif args.command == "cloud-readiness-run":
            result = cloud_run_from_files(args.project.resolve(), args.profile, args.facts, args.evidence_dir)
        else:
            result = _result("ready", None, [], capability=ConductorApiClient.from_environment().capability_preflight())
    except (OSError, ValueError, ContractError) as exc:
        result = _result("blocked", None, [str(exc)], error_class=type(exc).__name__)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    successful = {"ready", "valid", "pass", "allow", "merged", "created", "observed", "checkpointed", "selected", "registered", "persisted", "pr_ready", "complete"}
    return 0 if result["outcome"] in successful else 2

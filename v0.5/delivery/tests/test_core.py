from __future__ import annotations

import json
import io
import os
import base64
import runpy
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PACK = Path(__file__).resolve().parents[1]
SRC = PACK / "src"
sys.path.insert(0, str(SRC))

from delivery_pilot.authority import (  # noqa: E402
    apply_taste_answer,
    validate_approval,
    validate_venue_approval,
)
from delivery_pilot.budget import ActiveTimeLedger, CeilingError  # noqa: E402
from delivery_pilot.canonical import (  # noqa: E402
    CanonicalError,
    canonical_bytes,
    digest,
    load_strict,
)
from delivery_pilot.checker import (  # noqa: E402
    LAUNCHER_V2_POLICY,
    LAUNCHER_V4_POLICY,
    select_route,
    validate_checker_session_lifecycle,
    validate_launcher_receipt,
    validate_launcher_v3_receipt,
    validate_launcher_v4_receipt,
)
from delivery_pilot.contracts import CANDIDATE_FIELDS, ContractRegistry, ContractError  # noqa: E402
from delivery_pilot.gates import evaluate_gates, simulate_g9  # noqa: E402
from delivery_pilot.git_control import GitControlStore  # noqa: E402
from delivery_pilot.github_merge import GitHubCliDecisionStore, GitHubCliMergeHost  # noqa: E402
from delivery_pilot.completion import issue_handback, register_attempt, validate_core_metrics  # noqa: E402
from delivery_pilot.discovery import discover_mission  # noqa: E402
from delivery_pilot.interfaces import ExternalOperations  # noqa: E402
from delivery_pilot.merge_bridge import (  # noqa: E402
    classify_paths,
    dispatch_merge,
    issue_merge_decision,
    validate_bridge_authority_chain,
    validate_k41_envelope,
    validate_merge_decision,
    validate_merge_decision_attestation,
    validate_process_attested_merge,
)
from delivery_pilot.operations import FileReceiptStore, MemoryReceiptStore, OperationCoordinator  # noqa: E402
from delivery_pilot.state import (  # noqa: E402
    ALLOWED,
    CasMismatch,
    MissionStore,
    PHASES,
    STATUS_PHASES,
    STATUSES,
    WAKE_PREFIX,
    TransitionError,
    transition,
    validate_mission_invariants,
)
from delivery_pilot.verification import (  # noqa: E402
    candidate_readiness_selection,
    freeze_candidate,
    invalidation_phase,
    validate_gate_blockers,
)
from delivery_pilot.workflow import attempt_from_files, k41_decision_from_files, observation_from_files  # noqa: E402


def sha(label: str) -> str:
    return "sha256:" + (label.encode().hex() + "0" * 64)[:64]


def envelope() -> dict:
    return {
        "schema_version": 2,
        "envelope_id": "envelope-example",
        "revision": 1,
        "feature": {"slug": "example", "tracker_ref": "TASK-000"},
        "records": {"terminal_store": "tracker:TASK-000"},
        "scope": {
            "spec_ref": "planning/example/spec.md",
            "spec_digest": sha("spec"),
            "slices_ref": "planning/example/slices.md",
            "slices_digest": sha("slices"),
            "acceptance_refs": [],
        },
        "evidence": {
            "plan_ref": "planning/example/evidence-plan.yml",
            "plan_digest": sha("plan"),
            "verification_profile": "standard",
            "reasoning_tier": "medium",
            "required_qa_environments": ["local"],
        },
        "authority": {
            "maximum": "open-pr",
            "merge": {"target": "main", "method": "squash"},
            "deploy_targets": [],
            "authorized_human_ids": ["human-1"],
            "safety_approver_ids": ["human-1"],
        },
        "observation": {
            "contract_ref": "planning/example/pilot-observation-contract.json",
            "contract_digest": sha("observation-contract"),
        },
        "constraints": {
            "protected_paths": [],
            "allowed_dependencies": [],
            "coordinator_venue": "local",
            "allowed_qa_venues": ["local"],
            "ceilings": {
                "active_minutes_total": 480,
                "active_minutes_by_phase": {},
                "mission_ttl_days": 14,
                "fix_cycles_per_slice": 3,
                "final_check_cycles": 3,
                "api_rate_limit_retries": 5,
            },
        },
        "safety": {
            "risk_classes": [],
            "migration": {
                "present": False,
                "backup_required": False,
                "rollback_drill_ref": None,
            },
            "deploy_adapter": None,
            "rollback_adapter": None,
            "canary_policy": None,
            "archive_finalizer": None,
        },
    }


def mission() -> dict:
    return {
        "schema_version": 1,
        "mission_id": "delivery-example-01JTEST",
        "revision": 1,
        "prior_digest": None,
        "updated_at": "2026-08-08T00:00:00Z",
        "control_ref": "refs/heads/delivery-control/delivery-example-01JTEST",
        "control_path": "mission.yml",
        "controller": {"generation": 1, "workspace_id": "w1", "session_id": "s1"},
        "authority": {
            "command": "deliver-to-pr",
            "requested_tier": "A",
            "effective_tier": "A",
            "envelope_ref": "planning/example/delivery-envelope.yml",
            "envelope_digest": sha("env"),
            "approval_receipt_ref": "tracker:TASK-000#approval",
            "policy_kind": "pilot-composite",
            "policy_ref": ".agents/skills/ai-playbook-deliver/manifest-lock.yml",
            "policy_digest": sha("policy"),
        },
        "aggregate": {
            "phase": "authorized",
            "status": "running",
            "terminal_outcome": None,
            "wake_guard": None,
        },
        "budget": {
            "authorized_at": "2026-08-08T00:00:00Z",
            "ttl_expires_at": "2026-08-22T00:00:00Z",
            "active_seconds_total": 0,
            "active_seconds_by_phase": {},
            "charged_interval_ids": [],
            "fix_cycles_by_slice": {},
            "final_check_cycles": 0,
            "api_retries": 0,
        },
        "slices": {"s1": {"status": "pending", "candidate_sha": None}},
        "candidate": {
            "head_sha": None,
            "tree_sha": None,
            "base_sha": None,
            "policy_sha": None,
            "ruleset_fingerprint": None,
            "merge_group_sha": None,
            "verification_environment_digest": None,
            "frozen_at": None,
            "builder_session_ids": [],
        },
        "checks": {
            "launches": [],
            "final_attestation_ref": None,
            "qa_attestation_ref": None,
            "candidate_readiness_ref": None,
            "final_gate_strength": None,
            "minimum_observed_strength": None,
        },
        "findings": [],
        "interrupts": [],
        "required_actions": [],
        "operations": [],
        "deployment": {
            "merge_commit_sha": None,
            "artifact_digest": None,
            "release_id": None,
            "predecessor_release": None,
            "canary_policy_digest": None,
            "deploy_receipt_ref": None,
            "canary_receipt_ref": None,
            "rollback_operation_id": None,
        },
        "metrics": {},
        "terminal": {"handback_ref": None, "receipt_ref": None, "archive_state": "active"},
    }


class CanonicalTests(unittest.TestCase):
    def test_canonical_fixture_and_digest_are_stable(self) -> None:
        value = {"z": [3, True, None], "a": "é"}
        self.assertEqual(canonical_bytes(value), b'{"a":"\xc3\xa9","z":[3,true,null]}')
        self.assertEqual(digest(value), digest(load_strict(canonical_bytes(value))))

    def test_rfc8785_ecmascript_number_boundaries(self) -> None:
        value = {"negative_zero": -0.0, "fixed_low": 1e-6, "scientific_low": 1e-7, "fixed_high": 1e20, "scientific_high": 1e21}
        self.assertEqual(
            canonical_bytes(value),
            b'{"fixed_high":100000000000000000000,"fixed_low":0.000001,"negative_zero":0,"scientific_high":1e+21,"scientific_low":1e-7}',
        )

    def test_strict_parser_rejects_duplicate_nonfinite_and_traversal(self) -> None:
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"ref":"../secret"}'):
            with self.subTest(raw=raw), self.assertRaises(CanonicalError):
                load_strict(raw)

    def test_strict_yaml_supports_block_and_flow_forms(self) -> None:
        raw = b"""schema_version: 1
feature: {slug: example, tracker_ref: TASK-000}
authority:
  maximum: open-pr
  deploy_targets: []
services:
  - id: web
    port: 3000
"""
        self.assertEqual(
            load_strict(raw),
            {
                "schema_version": 1,
                "feature": {"slug": "example", "tracker_ref": "TASK-000"},
                "authority": {"maximum": "open-pr", "deploy_targets": []},
                "services": [{"id": "web", "port": 3000}],
            },
        )
        with self.assertRaises(CanonicalError):
            load_strict("schema_version: 1\nschema_version: 2\n")


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")

    def test_registry_owns_every_required_record(self) -> None:
        required = {
            "envelope", "approval", "envelope-amendment", "composite-policy-identity",
            "mission", "slice", "launcher", "launcher-v3", "launcher-v4", "checker-session-lifecycle", "verdict", "finding", "finding-closure",
            "qa", "question", "answer", "safety", "active-time", "ceiling-extension",
            "cancellation", "operation", "readiness-profile", "readiness-receipt",
            "host-evidence-manifest", "host-evidence-bundle", "handback", "pilot-attempt",
            "merge-decision-attestation", "merge-operation-intent",
            "pilot-observation-contract", "pilot-observation", "pilot-promotion", "canary", "recovery", "clean-tree",
            "closeout", "finalization-intent", "finalization-bundle", "terminal",
        }
        self.assertTrue(required <= set(self.registry.schema_ids))
        self.assertEqual(2, self.registry.schema_version("envelope"))
        self.assertEqual(2, self.registry.schema_version("approval"))
        self.assertEqual(2, self.registry.schema_version("launcher"))
        self.assertEqual(3, self.registry.schema_version("launcher-v3"))
        self.assertEqual(4, self.registry.schema_version("launcher-v4"))
        self.assertEqual(3, self.registry.schema_version("pilot-attempt"))
        self.assertEqual(4, self.registry.schema_version("pilot-observation"))
        self.assertTrue(all(self.registry.schema_version(name) == 1 for name in required - {"envelope", "approval", "launcher", "launcher-v3", "launcher-v4", "pilot-attempt", "pilot-observation"}))

    def test_examples_validate_and_unknown_values_fail_closed(self) -> None:
        for schema_id in self.registry.schema_ids:
            example = self.registry.example(schema_id)
            self.registry.validate(schema_id, example)
            bad = dict(example)
            bad["schema_version"] = 99
            with self.assertRaises(ContractError):
                self.registry.validate(schema_id, bad)
        with self.assertRaises(ContractError):
            self.registry.validate("not-registered", {})

    def test_mission_rejects_widened_authority_and_fabricated_closures(self) -> None:
        widened = mission()
        widened["authority"].update({"command": "deploy-and-release", "requested_tier": "C", "effective_tier": "C"})
        with self.assertRaisesRegex(ContractError, "Tier A delivery"):
            self.registry.validate("mission", widened)
        fabricated = mission()
        fabricated["findings"] = [{"status": "closed", "fabricated": True}]
        with self.assertRaisesRegex(ContractError, "invalid findings"):
            self.registry.validate("mission", fabricated)
        fabricated = mission()
        fabricated["interrupts"] = [{"status": "resolved", "fabricated": True}]
        with self.assertRaisesRegex(ContractError, "invalid interrupts"):
            self.registry.validate("mission", fabricated)

        for phase, status, terminal_outcome in (
            ("complete", "running", None),
            ("complete", "complete", None),
            ("complete", "complete", "invented-outcome"),
            ("complete", "complete", "cancelled"),
            ("pr-ready", "complete", "cancelled"),
        ):
            invalid = mission()
            invalid["aggregate"].update({
                "phase": phase, "status": status, "terminal_outcome": terminal_outcome,
            })
            with self.subTest(phase=phase, status=status, terminal_outcome=terminal_outcome), self.assertRaisesRegex(
                ContractError, "mission: (complete phase|terminal status|terminal status and outcome)",
            ):
                self.registry.validate("mission", invalid)

    def test_every_enum_and_conditional_field_fails_closed(self) -> None:
        for schema_id in self.registry.schema_ids:
            schema = self.registry.schema(schema_id)
            for field in schema.get("enums", {}):
                bad = self.registry.example(schema_id)
                bad[field] = "unknown-enum-value"
                with self.subTest(schema=schema_id, field=field), self.assertRaises(ContractError):
                    self.registry.validate(schema_id, bad)
        candidate = self.registry.example("readiness-receipt")
        candidate["mode"] = "candidate"
        with self.assertRaises(ContractError):
            self.registry.validate("readiness-receipt", candidate)
        wrong_type = self.registry.example("pilot-attempt")
        wrong_type["attempt_id"] = ["not", "a", "string"]
        with self.assertRaises(ContractError):
            self.registry.validate("pilot-attempt", wrong_type)
        launcher = self.registry.example("launcher")
        for field, value in (
            ("python_bytecode_control", "env-only"),
            ("repository_temp_policy", "inside-checkout"),
            ("repository_write_policy", "best-effort"),
            ("transient_write_monitor", "disabled"),
        ):
            invalid = json.loads(json.dumps(launcher))
            invalid["execution_policy"][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                self.registry.validate("launcher", invalid)
        launcher_v3 = self.registry.example("launcher-v3")
        for allowlist in ([], ["com.apple.FSEvents", "com.apple.unapproved"], ["com.apple.fseventsd"]):
            invalid = json.loads(json.dumps(launcher_v3))
            invalid["execution_policy"]["macos_mach_lookup_allowlist"] = allowlist
            with self.subTest(allowlist=allowlist), self.assertRaises(ContractError):
                self.registry.validate("launcher-v3", invalid)
        invalid = json.loads(json.dumps(launcher_v3))
        invalid["execution_policy"]["seatbelt_profile_digest"] = "not-a-digest"
        with self.assertRaises(ContractError):
            self.registry.validate("launcher-v3", invalid)
        launcher_v4 = self.registry.example("launcher-v4")
        for field, value in (
            ("repository_write_policy", "forbidden"),
            ("provider_checkpoint_policy", "unbound"),
        ):
            invalid = json.loads(json.dumps(launcher_v4))
            invalid["execution_policy"][field] = value
            with self.subTest(field=field), self.assertRaises(ContractError):
                self.registry.validate("launcher-v4", invalid)
        invalid = json.loads(json.dumps(launcher_v4))
        invalid["provider_checkpoints"]["provider"] = "untrusted"
        with self.assertRaises(ContractError):
            self.registry.validate("launcher-v4", invalid)

    def test_observation_contracts_reject_empty_or_unbound_planning_provenance(self) -> None:
        empty_envelope = envelope()
        empty_envelope["observation"] = {}
        with self.assertRaises(ContractError):
            self.registry.validate("envelope", empty_envelope)
        planning_only = envelope()
        planning_only["observation"]["minimum_duration_hours"] = 24
        with self.assertRaises(ContractError):
            self.registry.validate("envelope", planning_only)
        contract = self.registry.example("pilot-observation-contract")
        for field, value in (
            ("required_signals", []),
            ("raw_evidence_locators", []),
            ("defect_classification_route", ""),
            ("receipt_issuer", ""),
            ("receipt_issuer", "process-attested:self"),
            ("receipt_issuer", "process-attested:linear:"),
            ("receipt_issuer", "protected-store:"),
            ("receipt_issuer", "local-file:self"),
            ("defect_classification_route", "local-file:defects.json"),
            ("window_duration_hours", 0),
        ):
            with self.subTest(field=field), self.assertRaises(ContractError):
                self.registry.validate("pilot-observation-contract", {**contract, field: value})
        for issuer in ("process-attested:linear:TASK-339", "protected-store:pilot-ledger"):
            self.registry.validate("pilot-observation-contract", {**contract, "receipt_issuer": issuer})
        receipt = self.registry.example("pilot-observation")
        with self.assertRaises(ContractError):
            self.registry.validate("pilot-observation", {**receipt, "signals": []})
        with self.assertRaises(ContractError):
            self.registry.validate("pilot-observation", {**receipt, "signals": [{"id": "real-use-smoke"}]})
        malformed_id = json.loads(json.dumps(receipt))
        malformed_id["signals"][0]["id"] = ["not", "a", "string"]
        with self.assertRaises(ContractError):
            self.registry.validate("pilot-observation", malformed_id)
        with self.assertRaises(ContractError):
            self.registry.validate("pilot-observation", {**receipt, "observed_at": "2026-08-08T00:00:00Z"})


class AuthorityTests(unittest.TestCase):
    def test_approval_binds_exact_envelope_and_actor(self) -> None:
        env = envelope()
        approval = {
            "schema_version": 2,
            "approval_id": "approval-1",
            "envelope_ref": "planning/example/delivery-envelope.yml",
            "envelope_digest": digest(env),
            "actor_id": "human-1",
            "channel": "linear",
            "source_event_id": "event-1",
            "approved_at": "2026-08-08T00:00:00Z",
        }
        validate_approval(env, approval)
        stale = dict(approval, envelope_digest=sha("stale"))
        with self.assertRaises(ContractError):
            validate_approval(env, stale)

    def test_venue_requires_displayed_complete_digest(self) -> None:
        env = envelope()
        validate_venue_approval(env, "local", digest(env), digest(env))
        with self.assertRaises(ContractError):
            validate_venue_approval(env, "cloud", digest(env), digest(env))

    def test_taste_patch_is_path_limited_and_digest_bound(self) -> None:
        env = envelope()
        patch = [{"op": "replace", "path": "/scope/spec_ref", "value": "planning/example/spec-v2.md"}]
        question = {
            "schema_version": 1,
            "question_id": "q1",
            "base_envelope_digest": digest(env),
            "options_revision": 1,
            "options": [{
                "id": "a",
                "addendum_digest": digest("choose-v2"),
                "allowed_paths": ["/scope/spec_ref"],
                "patch": patch,
                "patch_digest": digest(patch),
                "result_envelope_digest": "pending",
            }],
        }
        expected = json.loads(json.dumps(env))
        expected["scope"]["spec_ref"] = "planning/example/spec-v2.md"
        expected["revision"] = 2
        question["options"][0]["result_envelope_digest"] = digest(expected)
        answer = {
            "schema_version": 1,
            "answer_id": "a1",
            "question_id": "q1",
            "options_revision": 1,
            "option_id": "a",
            "actor_id": "human-1",
            "source_event_id": "event-a1",
            "answered_at": "2026-08-08T01:00:00Z",
            "result_envelope_digest": digest(expected),
        }
        self.assertEqual(expected, apply_taste_answer(env, question, answer))
        question["options"][0]["patch"] = [{"op": "replace", "path": "/authority/maximum", "value": "merge"}]
        question["options"][0]["patch_digest"] = digest(question["options"][0]["patch"])
        with self.assertRaises(ContractError):
            apply_taste_answer(env, question, answer)
        for field, value in (("options_revision", 2), ("actor_id", "intruder"), ("result_envelope_digest", sha("wrong"))):
            with self.subTest(field=field), self.assertRaises(ContractError):
                apply_taste_answer(env, {**question, "options": [{
                    "id": "a", "addendum_digest": digest("choose-v2"),
                    "allowed_paths": ["/scope/spec_ref"], "patch": patch,
                    "patch_digest": digest(patch), "result_envelope_digest": digest(expected),
                }]}, {**answer, field: value})


class StateTests(unittest.TestCase):
    def test_cas_and_generation_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MissionStore(Path(tmp) / "mission.json")
            first = store.create(mission())
            claimed = store.claim(first.digest, "w2", "s2", "2026-08-08T01:00:00Z")
            self.assertEqual(2, claimed.value["controller"]["generation"])
            with self.assertRaises(CasMismatch):
                store.claim(first.digest, "w3", "s3", "2026-08-08T02:00:00Z")

    def test_candidate_readiness_transitions_and_wake_guards(self) -> None:
        state = mission()
        state = transition(state, "build")
        state = transition(state, "slice-check")
        state = transition(state, "qa")
        state = transition(state, "freeze")
        state = transition(state, "candidate-readiness")
        state = transition(state, "candidate-readiness", status="parked", wake_guard="manual_resume")
        state = transition(state, "candidate-readiness", status="running", wake_guard=None)
        state = transition(state, "final-check")
        self.assertEqual("final-check", state["aggregate"]["phase"])
        with self.assertRaises(TransitionError):
            transition(state, "complete")
        with self.assertRaises(TransitionError):
            transition(mission(), "authorized", status="waiting_capacity", wake_guard="capacity_after:tomorrow")

    def test_mission_rejects_two_mutable_slices_and_ambiguous_cancel(self) -> None:
        state = mission()
        state["slices"] = {"s1": {"status": "building"}, "s2": {"status": "fixing"}}
        with self.assertRaises(TransitionError):
            validate_mission_invariants(state)
        state = mission()
        state["aggregate"]["phase"] = "handback"
        state["operations"] = [{"status": "ambiguous"}]
        with self.assertRaises(TransitionError):
            transition(state, "complete", status="cancelled", terminal_outcome="cancelled")

    def test_terminal_cancellation_requires_explicit_two_step_transition(self) -> None:
        state = mission()
        state["aggregate"].update({
            "phase": "candidate-readiness",
            "status": "ceiling",
            "wake_guard": "ceiling_extension:fresh-checker-launches",
        })
        with self.assertRaisesRegex(TransitionError, "illegal transition"):
            transition(state, "complete", status="cancelled", terminal_outcome="cancelled")

        cancelling = transition(
            state,
            "candidate-readiness",
            status="cancelling",
            wake_guard="operations_terminal",
        )
        terminal = transition(
            cancelling,
            "complete",
            status="cancelled",
            terminal_outcome="cancelled",
        )
        self.assertEqual(
            {
                "phase": "complete",
                "status": "cancelled",
                "terminal_outcome": "cancelled",
                "wake_guard": None,
            },
            terminal["aggregate"],
        )

    def test_terminal_cancellation_rejects_unresolved_operations(self) -> None:
        for operation_status in ("intent_committed", "dispatched", "ambiguous"):
            state = mission()
            state["aggregate"].update({
                "phase": "candidate-readiness",
                "status": "cancelling",
                "wake_guard": "operations_terminal",
            })
            state["operations"] = [{"status": operation_status}]
            with self.subTest(operation_status=operation_status), self.assertRaisesRegex(
                TransitionError, "unresolved operations"
            ):
                transition(state, "complete", status="cancelled", terminal_outcome="cancelled")

    def test_terminal_cancellation_accepts_only_terminal_operations(self) -> None:
        for operation_status in ("observed_succeeded", "observed_failed", "cancelled"):
            state = mission()
            state["aggregate"].update({
                "phase": "candidate-readiness",
                "status": "cancelling",
                "wake_guard": "operations_terminal",
            })
            state["operations"] = [{"status": operation_status}]
            terminal = transition(
                state,
                "complete",
                status="cancelled",
                terminal_outcome="cancelled",
            )
            self.assertEqual("cancelled", terminal["aggregate"]["terminal_outcome"])

    def test_terminal_transition_requires_recognized_matching_outcome(self) -> None:
        state = mission()
        state["aggregate"]["phase"] = "handback"
        with self.assertRaisesRegex(TransitionError, "recognized terminal outcome"):
            transition(state, "complete")
        with self.assertRaisesRegex(TransitionError, "recognized terminal outcome"):
            transition(state, "complete", terminal_outcome="invented-outcome")
        with self.assertRaisesRegex(TransitionError, "status and outcome disagree"):
            transition(state, "complete", status="complete", terminal_outcome="cancelled")
        terminal = transition(state, "complete", terminal_outcome="pr_ready")
        self.assertEqual("pr_ready", terminal["aggregate"]["terminal_outcome"])

    def test_transition_table_is_exhaustive_and_unknown_edges_fail(self) -> None:
        for current in PHASES:
            for target in PHASES:
                state = mission()
                state["aggregate"]["phase"] = current
                state["aggregate"]["status"] = "complete" if current == "complete" else "running"
                state["aggregate"]["terminal_outcome"] = "pr_ready" if current == "complete" else None
                should_pass = target == current or target in ALLOWED[current]
                if should_pass:
                    transition(state, target, terminal_outcome="pr_ready" if target == "complete" else None)
                else:
                    with self.subTest(current=current, target=target), self.assertRaises(TransitionError):
                        transition(state, target, terminal_outcome="pr_ready" if target == "complete" else None)

    def test_every_restricted_status_rejects_the_wrong_phase(self) -> None:
        guards = {
            "waiting_taste": "answer:q1:1",
            "waiting_capacity": "capacity_after:2026-08-09T00:00:00Z",
            "intervention_required": "safety_disposition:s1",
        }
        for status, allowed_phases in STATUS_PHASES.items():
            wrong = next(phase for phase in PHASES if phase not in allowed_phases and phase != "complete")
            state = mission()
            state["aggregate"]["phase"] = wrong
            with self.subTest(status=status, phase=wrong), self.assertRaises(TransitionError):
                transition(state, wrong, status=status, wake_guard=guards[status])

    def test_every_parked_status_requires_its_typed_wake_guard(self) -> None:
        phases = {
            "parked": "build", "waiting_taste": "build", "waiting_safety": "build",
            "waiting_capacity": "slice-check", "ceiling": "build", "errored": "build",
            "cancelling": "build", "intervention_required": "deploy",
        }
        for status, prefixes in WAKE_PREFIX.items():
            state = mission()
            state["aggregate"]["phase"] = phases[status]
            valid = prefixes[0] if prefixes[0] in {"manual_resume", "operations_terminal"} else prefixes[0] + "proof"
            transition(state, phases[status], status=status, wake_guard=valid)
            with self.subTest(status=status), self.assertRaises(TransitionError):
                transition(state, phases[status], status=status, wake_guard="wrong:guard")

    def test_every_phase_round_trips_without_chat_and_can_be_claimed(self) -> None:
        for phase in PHASES[:-1]:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as tmp:
                value = mission()
                value["aggregate"]["phase"] = phase
                store = MissionStore(Path(tmp) / "mission.json")
                created = store.create(value)
                observed = store.read()
                self.assertEqual(phase, observed.value["aggregate"]["phase"])
                claimed = store.claim(created.digest, "replacement-workspace", "replacement-session", "2026-08-08T03:00:00Z")
                self.assertEqual(2, claimed.value["controller"]["generation"])

    def test_git_control_ref_create_and_cas_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Pilot Test"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "pilot@example.invalid"], cwd=repo, check=True)
            store = GitControlStore(repo, "refs/heads/delivery-control/m1")
            created = store.create({"operation_intent": "control-ref-create", "envelope_digest": sha("env"), "mission": mission()})
            self.assertEqual("control-ref-create", created.value["operation_intent"])
            value = dict(created.value)
            value["mission"] = transition(value["mission"], "build")
            updated = store.write(created.commit_sha, created.digest, value)
            self.assertNotEqual(created.commit_sha, updated.commit_sha)
            with self.assertRaises(CasMismatch):
                store.write(created.commit_sha, created.digest, value)


class BudgetTests(unittest.TestCase):
    def test_concurrent_intervals_charge_independently_and_once(self) -> None:
        ledger = ActiveTimeLedger(600, {"build": 500})
        ledger.start("i1", "build", 100)
        ledger.start("i2", "build", 120)
        ledger.stop("i1", 200)
        ledger.stop("i2", 220)
        ledger.stop("i2", 220)
        self.assertEqual(200, ledger.total_seconds)
        self.assertEqual(200, ledger.by_phase["build"])

    def test_unknown_end_and_ttl_fail_closed(self) -> None:
        ledger = ActiveTimeLedger(10)
        ledger.start("i1", "build", 0)
        with self.assertRaises(CeilingError):
            ledger.reconcile_unknown("i1")
        with self.assertRaises(CeilingError):
            ledger.check_ttl(datetime(2026, 8, 9, tzinfo=timezone.utc), datetime(2026, 8, 8, tzinfo=timezone.utc))

    def test_backward_stop_keeps_the_interval_open_for_a_valid_later_close(self) -> None:
        ledger = ActiveTimeLedger(10)
        ledger.start("backward-clock", "build", 10)
        before = ledger.to_record()
        with self.assertRaisesRegex(CeilingError, "ended before"):
            ledger.stop("backward-clock", 9)
        self.assertEqual(ledger.to_record(), before)
        self.assertEqual(1, ledger.stop("backward-clock", 11))
        self.assertEqual((ledger.open_intervals, ledger.charged_ids, ledger.total_seconds),
                         ({}, {"backward-clock"}, 1))

    def test_phase_split_and_authorized_extension_preserve_charged_time(self) -> None:
        ledger = ActiveTimeLedger(100, {"build": 50})
        ledger.start("i1", "build", 0)
        next_id = ledger.split("i1", "qa", 40)
        ledger.stop(next_id, 60)
        ledger.extend("active_seconds_total", 200, authorized=True)
        ledger.extend("active_seconds_by_phase.build", 80, authorized=True)
        self.assertEqual(60, ledger.total_seconds)
        with self.assertRaises(CeilingError):
            ledger.extend("active_seconds_total", 250, authorized=False)


class FakeProvider:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.effects: dict[str, dict] = {}
        self.dispatches = 0

    def query(self, key: str):
        return self.effects.get(key)

    def dispatch(self, key: str, payload: dict):
        self.dispatches += 1
        if self.mode == "ambiguous":
            raise TimeoutError("provider result unknown")
        self.effects[key] = {"status": "succeeded", "external_ref": "ext-1", "evidence_digest": digest(payload)}
        return self.effects[key]


class EffectThenTimeoutProvider(FakeProvider):
    def dispatch(self, key: str, payload: dict):
        self.dispatches += 1
        self.effects[key] = {"status": "succeeded", "external_ref": "ext-after-timeout", "evidence_digest": digest(payload)}
        raise TimeoutError("reply lost after effect")


class OperationTests(unittest.TestCase):
    def test_query_before_create_and_resume_do_not_duplicate(self) -> None:
        provider = FakeProvider()
        coordinator = OperationCoordinator(provider)
        receipt1 = coordinator.run("m1", 1, "pr-upsert", "repo#branch", {"title": "PR"})
        receipt2 = coordinator.run("m1", 2, "pr-upsert", "repo#branch", {"title": "PR"})
        self.assertEqual("observed_succeeded", receipt1["status"])
        self.assertEqual(receipt1["operation_id"], receipt2["operation_id"])
        self.assertEqual(1, provider.dispatches)

    def test_intent_is_persisted_before_dispatch_and_lost_reply_reconciles(self) -> None:
        provider = EffectThenTimeoutProvider()
        with tempfile.TemporaryDirectory() as tmp:
            store = FileReceiptStore(Path(tmp))
            coordinator = OperationCoordinator(provider, store)
            first = coordinator.run("m1", 1, "branch-ensure", "repo#feature", {"sha": "base"})
            self.assertEqual("ambiguous", first["status"])
            persisted = store.get(first["operation_id"])
            self.assertEqual("ambiguous", persisted["status"])
            second = coordinator.run("m1", 2, "branch-ensure", "repo#feature", {"sha": "base"})
            self.assertEqual("observed_succeeded", second["status"])
            self.assertEqual(1, provider.dispatches)

    def test_ambiguous_result_parks(self) -> None:
        receipt = OperationCoordinator(FakeProvider("ambiguous")).run("m1", 1, "question-publish", "TASK-1#q1", {"q": "?"})
        self.assertEqual("ambiguous", receipt["status"])

    def test_frozen_public_interfaces_emit_typed_operation_receipts(self) -> None:
        provider = FakeProvider()
        interface = ExternalOperations(OperationCoordinator(provider), "m1", 4)
        calls = [
            interface.control_ref_create("refs/heads/delivery-control/m1", {"genesis": True}, True),
            interface.registry_locator_upsert({"mission_id": "m1"}, 0),
            interface.branch_ensure("owner/repo", "feature", "base", "absent"),
            interface.pr_upsert("owner/repo", "feature", "main", "agent-delivery:m1", sha("metadata"), "head"),
            interface.question_publish("TASK-1", "q1", 1, sha("question")),
        ]
        self.assertEqual(
            ["control-ref-create", "registry-locator-upsert", "branch-ensure", "pr-upsert", "question-publish"],
            [item["kind"] for item in calls],
        )
        self.assertTrue(all(item["status"] == "observed_succeeded" for item in calls))

    def test_lost_reply_matrix_reconciles_each_tier_a_operation_once(self) -> None:
        kinds = ("control-ref-create", "registry-locator-upsert", "branch-ensure", "pr-upsert", "question-publish")
        for kind in kinds:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                provider = EffectThenTimeoutProvider()
                coordinator = OperationCoordinator(provider, FileReceiptStore(Path(tmp)))
                first = coordinator.run("m1", 1, kind, f"target:{kind}", {"kind": kind})
                self.assertEqual("ambiguous", first["status"])
                second = coordinator.run("m1", 2, kind, f"target:{kind}", {"kind": kind})
                self.assertEqual("observed_succeeded", second["status"])
                self.assertEqual(1, provider.dispatches)


class VerificationTests(unittest.TestCase):
    def test_freeze_binds_tuple_and_changes_invalidate_to_owning_phase(self) -> None:
        candidate = {
            "head_sha": "h", "tree_sha": "t", "base_sha": "b", "policy_sha": "p",
            "ruleset_fingerprint": "r", "verification_environment_digest": "e", "merge_group_sha": None,
        }
        frozen = freeze_candidate(candidate, clean=True, builder_quiescent=True, frozen_at="2026-08-08T00:00:00Z")
        self.assertEqual("h", frozen["head_sha"])
        self.assertEqual("build", invalidation_phase(frozen, dict(frozen, head_sha="h2")))
        self.assertEqual("final-check", invalidation_phase(frozen, frozen))
        for field in ("head_sha", "tree_sha", "base_sha", "policy_sha", "ruleset_fingerprint", "verification_environment_digest", "merge_group_sha"):
            changed = dict(frozen)
            changed[field] = "changed"
            self.assertEqual("build", invalidation_phase(frozen, changed), field)

    def test_readiness_matrix_selects_minimum_union(self) -> None:
        selection = candidate_readiness_selection(
            {"dependency_lock", "browser_journey", "cleanup_executable"},
            admission_current=True,
            epochs_observable=True,
        )
        self.assertEqual({"CR3", "CR4", "CR5", "CR6", "CR7", "CR8", "CR9", "CR10"}, set(selection["required"]))
        self.assertTrue(selection["may_reuse_admission"])
        no_epochs = candidate_readiness_selection(set(), admission_current=True, epochs_observable=False)
        self.assertFalse(no_epochs["may_reuse_admission"])
        self.assertEqual({f"CR{i}" for i in range(1, 11)}, set(no_epochs["required"]))

    def test_risk_todos_threads_interrupts_and_actions_block(self) -> None:
        base = {
            "verdict_outcome": "pass", "findings": [], "closures": [],
            "blocking_todos_mirrored": True, "unresolved_host_threads": 0,
            "open_interrupts": 0, "required_actions": [],
        }
        validate_gate_blockers(**base)
        for field, value in (
            ("verdict_outcome", "risk"),
            ("blocking_todos_mirrored", False),
            ("unresolved_host_threads", 1),
            ("open_interrupts", 1),
            ("required_actions", ["do-x"]),
        ):
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_gate_blockers(**dict(base, **{field: value}))


class DiscoveryAndCompletionTests(unittest.TestCase):
    def test_discovery_order_and_mirror_conflict_fail_closed(self) -> None:
        sources = {
            "local_locator": {"mission_id": "m1", "control_ref": "refs/heads/delivery-control/m1"},
            "protected_registry": {"mission_id": "m1", "control_ref": "refs/heads/delivery-control/m1"},
            "labelled_prs": [{"mission_id": "m1"}],
            "finalization_intents": [],
            "control_refs": ["refs/heads/delivery-control/m1"],
        }
        found = discover_mission(sources)
        self.assertEqual("local_locator", found["source"])
        sources["protected_registry"]["mission_id"] = "m2"
        with self.assertRaises(ContractError):
            discover_mission(sources)

    def test_each_discovery_fallback_is_reachable(self) -> None:
        ordered = ("local_locator", "protected_registry", "labelled_prs", "finalization_intents", "control_refs")
        values = {
            "local_locator": {"mission_id": "m1"},
            "protected_registry": {"mission_id": "m1"},
            "labelled_prs": [{"mission_id": "m1"}],
            "finalization_intents": [{"mission_id": "m1"}],
            "control_refs": ["refs/heads/delivery-control/m1"],
        }
        for index, source in enumerate(ordered):
            case = {name: ([] if isinstance(values[name], list) else None) for name in ordered}
            case[source] = values[source]
            self.assertEqual(source, discover_mission(case)["source"])

    def test_attempt_registration_metrics_and_handback(self) -> None:
        attempt = register_attempt(
            "attempt-1", "m1", "feature", "sample-project", "A", "local", sha("env"),
            "planning/feature/pilot-observation-contract.json", sha("contract"), sha("tests"),
            "2026-08-08T00:00:00Z",
        )
        self.assertEqual("attempt-1", attempt["attempt_id"])
        self.assertEqual(3, attempt["schema_version"])
        metrics = {
            "attempt_id": "attempt-1", "mission_id": "m1", "outcome_id": "handback-1",
            "phase_timestamps": {}, "active_seconds_total": 10, "active_seconds_by_phase": {"build": 10},
            "parked_seconds": 0, "queue_seconds": 0, "setup_seconds": 0, "resume_seconds": 0,
            "planned_taste_minutes": 0, "planned_safety_minutes": 0, "unplanned_human_rescue_minutes": 0,
            "chat_reconstruction_required": False, "checker_launches": 1, "checker_rungs": [1],
            "fix_cycles": 0, "findings": 0, "ci_runs": 1, "ci_minutes": 1,
            "operation_retries": 0, "operation_ambiguities": 0, "operation_duplicates": 0,
            "cloud_admission_seconds": None, "cloud_candidate_seconds": None, "cloud_cr_reuse": [], "cloud_cr_reruns": [],
            "workspace_count": 1, "workspace_sleeps": 0, "archive_latency_seconds": None,
            "post_merge_defects": [], "outstanding_terminal_residue": 0,
        }
        validate_core_metrics(metrics, venue="local")
        with self.assertRaises(ContractError):
            validate_core_metrics({key: value for key, value in metrics.items() if key != "ci_runs"}, venue="local")
        receipt = issue_handback(
            mission_id="m1", candidate={"head_sha": "h"}, pr_ref="github:pr/1",
            attestation_refs=["artifact:final", "artifact:qa"], owner_id="human-1",
            workspace_disposition="sleep", issue_ref="TASK-1", issued_at="2026-08-08T00:01:00Z",
            open_findings=[], required_actions=[], metrics=metrics,
        )
        self.assertEqual(0, receipt["open_action_count"])
        bridge_attempt = register_attempt(
            "attempt-2", "m2", "feature", "sample-project", "A", "cloud", sha("env"),
            "planning/feature/pilot-observation-contract.json", sha("contract"), sha("tests"),
            "2026-08-08T00:00:00Z", "K4.1", "process-attested-fresh-merge", "merge",
        )
        self.assertEqual("merge", bridge_attempt["maximum_action"])
        bridge_handback = issue_handback(
            mission_id="m1", candidate={"head_sha": "h"}, pr_ref="github:pr/1",
            attestation_refs=["artifact:final", "artifact:qa"], owner_id="human-1",
            workspace_disposition="sleep", issue_ref="TASK-1", issued_at="2026-08-08T00:01:00Z",
            open_findings=[], required_actions=[], metrics=metrics,
            rollout_milestone="K4.1", authority_class="process-attested-fresh-merge",
            maximum_action="merge",
        )
        self.assertEqual("K4.1", bridge_handback["rollout_milestone"])
        with self.assertRaisesRegex(ContractError, "must appear together"):
            register_attempt(
                "attempt-3", "m3", "feature", "sample-project", "A", "local", sha("env"),
                "planning/feature/pilot-observation-contract.json", sha("contract"), sha("tests"),
                "2026-08-08T00:00:00Z", rollout_milestone="K4.1",
            )
        with self.assertRaises(ContractError):
            issue_handback(
                mission_id="m1", candidate={"head_sha": "h"}, pr_ref="github:pr/1",
                attestation_refs=["artifact:final"], owner_id="human-1", workspace_disposition="sleep",
                issue_ref="TASK-1", issued_at="2026-08-08T00:01:00Z",
                open_findings=[{"finding_id": "f1"}], required_actions=[], metrics=metrics,
            )

    def test_observation_receipt_binds_declared_contract_attempt_and_window(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        contract = registry.example("pilot-observation-contract")
        contract["raw_evidence_locators"] = ["github:owner/repo/commit/sha"]
        contract_digest = digest(contract)
        attempt = registry.example("pilot-attempt")
        attempt.update({
            "attempt_id": contract["attempt_id"],
            "mission_id": contract["mission_id"],
            "observation_contract_digest": contract_digest,
        })
        observation = registry.example("pilot-observation")
        observation.update({
            "attempt_id": contract["attempt_id"],
            "observation_contract_digest": contract_digest,
            "receipt_issuer": contract["receipt_issuer"],
            "window_started_at": "2026-08-08T01:00:00Z",
            "window_ended_at": "2026-08-09T01:00:00Z",
            "observed_at": "2026-08-09T01:00:00Z",
        })
        observation["host_events"][0]["occurred_at"] = observation["window_started_at"]
        observation["host_proof"]["event_digest"] = digest(observation["host_events"][0])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name, value in (("observation.json", observation), ("contract.json", contract), ("attempt.json", attempt)):
                path = root / name
                path.write_bytes(canonical_bytes(value))
                paths.append(path)
            self.assertEqual("valid", observation_from_files(*paths)["outcome"])
            invalid_cases = []
            too_short = json.loads(json.dumps(observation))
            too_short["window_ended_at"] = "2026-08-08T01:00:00Z"
            invalid_cases.append(too_short)
            unrelated_subject = json.loads(json.dumps(observation))
            unrelated_subject["host_events"][0]["subject_id"] = "unrelated-release"
            unrelated_subject["host_proof"]["event_digest"] = digest(unrelated_subject["host_events"][0])
            invalid_cases.append(unrelated_subject)
            wrong_event = json.loads(json.dumps(observation))
            wrong_event["host_events"][0]["event"] = "released_at"
            wrong_event["host_proof"]["event_digest"] = digest(wrong_event["host_events"][0])
            invalid_cases.append(wrong_event)
            unbound_proof = json.loads(json.dumps(observation))
            unbound_proof["host_proof"]["event_digest"] = sha("unrelated-event")
            invalid_cases.append(unbound_proof)
            wrong_locator = json.loads(json.dumps(observation))
            wrong_locator["host_proof"]["evidence_locator"] = "github:owner/repo/commit/unrelated"
            invalid_cases.append(wrong_locator)
            duplicate_start = json.loads(json.dumps(observation))
            duplicate_start["host_events"].append(dict(duplicate_start["host_events"][0]))
            invalid_cases.append(duplicate_start)
            for invalid in invalid_cases:
                paths[0].write_bytes(canonical_bytes(invalid))
                with self.assertRaises(ContractError):
                    observation_from_files(*paths)
            predeclaration_attempt = dict(attempt, registered_at="2026-08-07T23:59:00Z")
            paths[0].write_bytes(canonical_bytes(observation))
            paths[2].write_bytes(canonical_bytes(predeclaration_attempt))
            with self.assertRaisesRegex(ContractError, "predates its contract declaration"):
                observation_from_files(*paths)
            late_attempt = dict(attempt, registered_at="2026-08-08T02:00:00Z")
            paths[2].write_bytes(canonical_bytes(late_attempt))
            with self.assertRaisesRegex(ContractError, "after its window started"):
                observation_from_files(*paths)

            process_contract = dict(contract, receipt_issuer="process-attested:linear:TASK-339")
            process_digest = digest(process_contract)
            process_attempt = dict(attempt, observation_contract_digest=process_digest)
            process_observation = json.loads(json.dumps(observation))
            process_observation.update({
                "observation_contract_digest": process_digest,
                "receipt_issuer": process_contract["receipt_issuer"],
            })
            for path, value in zip(paths, (process_observation, process_contract, process_attempt)):
                path.write_bytes(canonical_bytes(value))
            self.assertEqual("valid", observation_from_files(*paths)["outcome"])

            protected_required = dict(process_attempt, tier="B")
            paths[2].write_bytes(canonical_bytes(protected_required))
            with self.assertRaisesRegex(ContractError, "require a protected-store issuer"):
                observation_from_files(*paths)

    def test_attempt_registration_binds_envelope_and_observation_contract(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        contract = registry.example("pilot-observation-contract")
        env = envelope()
        env["observation"]["contract_digest"] = digest(contract)
        attempt = registry.example("pilot-attempt")
        attempt.update({
            "attempt_id": contract["attempt_id"],
            "mission_id": contract["mission_id"],
            "envelope_digest": digest(env),
            "observation_contract_ref": env["observation"]["contract_ref"],
            "observation_contract_digest": digest(contract),
        })
        approval = registry.example("approval")
        approval.update({
            "envelope_digest": digest(env),
            "actor_id": "human-1",
            "approved_at": "2026-08-08T00:01:00Z",
        })
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name, value in (("attempt.json", attempt), ("contract.json", contract), ("envelope.json", env), ("approval.json", approval)):
                path = root / name
                path.write_bytes(canonical_bytes(value))
                paths.append(path)
            self.assertEqual("registered", attempt_from_files(*paths)["outcome"])

            process_contract = dict(contract, receipt_issuer="process-attested:linear:TASK-339")
            process_digest = digest(process_contract)
            process_env = json.loads(json.dumps(env))
            process_env["observation"]["contract_digest"] = process_digest
            process_attempt = dict(attempt,
                observation_contract_digest=process_digest,
                envelope_digest=digest(process_env),
            )
            process_approval = dict(approval, envelope_digest=digest(process_env))
            for path, value in zip(paths, (process_attempt, process_contract, process_env, process_approval)):
                path.write_bytes(canonical_bytes(value))
            self.assertEqual("registered", attempt_from_files(*paths)["outcome"])

            tier_b_attempt = dict(process_attempt, tier="B")
            paths[0].write_bytes(canonical_bytes(tier_b_attempt))
            with self.assertRaisesRegex(ContractError, "only Tier A"):
                attempt_from_files(*paths)

            wrong_venue_attempt = dict(process_attempt, venue="cloud")
            paths[0].write_bytes(canonical_bytes(wrong_venue_attempt))
            with self.assertRaisesRegex(ContractError, "coordinator venue"):
                attempt_from_files(*paths)

            for path, value in zip(paths, (attempt, contract, env, approval)):
                path.write_bytes(canonical_bytes(value))
            attempt["observation_contract_digest"] = sha("stale")
            paths[0].write_bytes(canonical_bytes(attempt))
            with self.assertRaises(ContractError):
                attempt_from_files(*paths)

            late_contract = dict(contract, declared_at="2026-08-08T00:03:00Z")
            late_digest = digest(late_contract)
            late_env = json.loads(json.dumps(env))
            late_env["observation"]["contract_digest"] = late_digest
            late_attempt = dict(attempt,
                observation_contract_digest=late_digest,
                envelope_digest=digest(late_env),
                registered_at="2026-08-08T00:02:00Z",
            )
            late_approval = dict(approval, envelope_digest=digest(late_env), approved_at="2026-08-08T00:04:00Z")
            for path, value in zip(paths, (late_attempt, late_contract, late_env, late_approval)):
                path.write_bytes(canonical_bytes(value))
            with self.assertRaisesRegex(ContractError, "before observation contract declaration"):
                attempt_from_files(*paths)

            valid_contract = contract
            valid_digest = digest(valid_contract)
            valid_env = json.loads(json.dumps(env))
            valid_env["observation"]["contract_digest"] = valid_digest
            early_attempt = dict(attempt,
                observation_contract_digest=valid_digest,
                envelope_digest=digest(valid_env),
                registered_at="2026-08-08T00:00:30Z",
            )
            valid_approval = dict(approval, envelope_digest=digest(valid_env), approved_at="2026-08-08T00:01:00Z")
            for path, value in zip(paths, (early_attempt, valid_contract, valid_env, valid_approval)):
                path.write_bytes(canonical_bytes(value))
            with self.assertRaisesRegex(ContractError, "before envelope approval"):
                attempt_from_files(*paths)


class CheckerAndGateTests(unittest.TestCase):
    def test_capacity_ladder_prefers_cross_family_and_never_builder_context(self) -> None:
        route = select_route(
            builder_family="openai",
            builder_model="gpt-build",
            candidates=[
                {"family": "openai", "model": "gpt-check", "available": True},
                {"family": "anthropic", "model": "claude-check", "available": True},
            ],
        )
        self.assertEqual("cross-family", route["independence"])
        self.assertEqual("full", route["gate_strength"])
        same_family = select_route("openai", "builder", [{"family": "openai", "model": "checker", "available": True}])
        self.assertEqual(3, same_family["rung"])
        same_model = select_route("openai", "builder", [{"family": "openai", "model": "builder", "available": True}])
        self.assertEqual(4, same_model["rung"])
        self.assertEqual("waiting_capacity", select_route("openai", "builder", [])["status"])

    def test_launcher_rejects_fork_dirty_or_identity_mismatch(self) -> None:
        receipt = {
            "schema_version": 2,
            "launch_id": "l1", "session_id": "s1", "workspace_id": "w1",
            "parent_context": False,
            "requested": {"agent": "codex", "family": "openai", "model": "gpt-check", "effort": "high"},
            "runtime": {"agent": "codex", "family": "openai", "model": "gpt-check", "effort": "high"},
            "prompt_digest": sha("prompt"), "envelope_digest": sha("env"), "spec_digest": sha("spec"),
            "candidate": {"head_sha": "h", "tree_sha": "t", "base_sha": "b", "policy_sha": "p", "ruleset_fingerprint": "r", "verification_environment_digest": "e", "merge_group_sha": None},
            "checkout": {"start_tree": "t", "end_tree": "t", "start_untracked": sha("u"), "end_untracked": sha("u"), "clean": True, "read_only": True, "builder_context_input": False},
            "execution_policy": {
                "python_bytecode_control": "env-and-flag",
                "repository_temp_policy": "outside-checkout",
                "repository_write_policy": "forbidden",
                "transient_write_monitor": "enabled",
            },
            "started_at": "2026-08-08T00:00:00Z", "ended_at": "2026-08-08T00:01:00Z", "termination_state": "completed",
            "raw_evidence_digest": sha("raw"), "raw_evidence_locator": "artifact:1",
        }
        validate_launcher_receipt(receipt, tier="A")
        with self.assertRaises(ContractError):
            validate_launcher_receipt(dict(receipt, parent_context=True), tier="A")
        with self.assertRaises(ContractError):
            validate_launcher_receipt(receipt, tier="A", expected={"prompt_digest": sha("wrong")})
        for field in ("envelope_digest", "spec_digest"):
            with self.subTest(field=field), self.assertRaises(ContractError):
                validate_launcher_receipt(receipt, tier="A", expected={field: sha("wrong")})
        with self.assertRaises(ContractError):
            validate_launcher_receipt(receipt, tier="A", expected={"candidate": {"head_sha": "wrong"}})
        for checkout_field, value in (("clean", False), ("read_only", False), ("builder_context_input", True)):
            changed = dict(receipt)
            changed["checkout"] = dict(receipt["checkout"], **{checkout_field: value})
            with self.subTest(field=checkout_field), self.assertRaises(ContractError):
                validate_launcher_receipt(changed, tier="A")
        for policy_field, value in (
            ("python_bytecode_control", "env-only"),
            ("repository_temp_policy", "inside-checkout"),
            ("repository_write_policy", "best-effort"),
            ("transient_write_monitor", "disabled"),
        ):
            changed = dict(receipt)
            changed["execution_policy"] = dict(receipt["execution_policy"], **{policy_field: value})
            with self.subTest(field=policy_field), self.assertRaises(ContractError):
                validate_launcher_receipt(changed, tier="A")

    def test_launcher_v3_binds_exact_fsevents_allowlist_and_profile(self) -> None:
        receipt = self._launcher_v3_receipt()
        validate_launcher_v3_receipt(receipt, tier="A")
        for field, value in (
            ("python_bytecode_control", "env-only"),
            ("repository_temp_policy", "inside-checkout"),
            ("repository_write_policy", "best-effort"),
            ("transient_write_monitor", "disabled"),
            ("macos_mach_lookup_allowlist", []),
            ("macos_mach_lookup_allowlist", ["com.apple.FSEvents", "com.apple.unapproved"]),
            ("seatbelt_profile_digest", "invalid"),
        ):
            changed = json.loads(json.dumps(receipt))
            changed["execution_policy"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ContractError):
                validate_launcher_v3_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["execution_policy"]["unreceipted_policy"] = "allowed"
        with self.assertRaises(ContractError):
            validate_launcher_v3_receipt(changed, tier="A")
        expected = {"execution_policy": dict(receipt["execution_policy"], seatbelt_profile_digest=sha("other"))}
        with self.assertRaisesRegex(ContractError, "execution policy mismatch"):
            validate_launcher_v3_receipt(receipt, tier="A", expected=expected)

    def test_launcher_v4_binds_only_conductor_turn_checkpoints(self) -> None:
        receipt = self._launcher_v4_receipt()
        validate_launcher_v4_receipt(receipt, tier="A")
        for field, value in (
            ("python_bytecode_control", "env-only"),
            ("repository_temp_policy", "inside-checkout"),
            ("repository_write_policy", "forbidden"),
            ("transient_write_monitor", "disabled"),
            ("provider_checkpoint_policy", "conductor-session-bound"),
        ):
            changed = json.loads(json.dumps(receipt))
            changed["execution_policy"][field] = value
            with self.subTest(policy=field), self.assertRaises(ContractError):
                validate_launcher_v4_receipt(changed, tier="A")
        for field, value in (
            ("end_head_sha", "other"),
            ("end_tree", "other"),
            ("end_index_digest", sha("other")),
            ("end_staged_diff_digest", sha("other")),
            ("end_worktree_digest", sha("other")),
            ("end_untracked", sha("other")),
            ("end_noncheckpoint_refs_digest", sha("other")),
        ):
            changed = json.loads(json.dumps(receipt))
            changed["checkout"][field] = value
            with self.subTest(checkout=field), self.assertRaises(ContractError):
                validate_launcher_v4_receipt(changed, tier="A")
        for field, value in (
            ("provider", "other"),
            ("actor_name", "Agent"),
            ("actor_email", "agent@example.com"),
            ("ref_namespace", "refs/heads/"),
            ("turn_id", "other/turn"),
            ("start_ref", "refs/conductor-checkpoints/session-other-turn-t4-start"),
            ("end_ref", "refs/conductor-checkpoints/session-s4-turn-other-end"),
            ("start_commit", "not-an-object"),
            ("start_tree", "other"),
            ("metadata_digest", "invalid"),
            ("start_created_at", "2026-08-08T00:02:00Z"),
        ):
            changed = json.loads(json.dumps(receipt))
            changed["provider_checkpoints"][field] = value
            with self.subTest(checkpoint=field), self.assertRaises(ContractError):
                validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["provider_checkpoints"]["extra"] = "forbidden"
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["provider_checkpoints"]["end_ref"] = (
            "refs/conductor-checkpoints/session-s4-turn-t5-end"
        )
        with self.assertRaisesRegex(ContractError, "session turn"):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        del changed["provider_checkpoints"]["metadata_digest"]
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["checkout"]["start_head_sha"] = ""
        changed["checkout"]["end_head_sha"] = ""
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["checkout"]["start_tree"] = ""
        changed["checkout"]["end_tree"] = ""
        changed["candidate"]["tree_sha"] = ""
        changed["provider_checkpoints"]["start_tree"] = ""
        changed["provider_checkpoints"]["end_tree"] = ""
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["termination_state"] = "cancelled"
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")
        changed = json.loads(json.dumps(receipt))
        changed["candidate"]["tree_sha"] = "other"
        with self.assertRaises(ContractError):
            validate_launcher_v4_receipt(changed, tier="A")

    def test_checker_lifecycle_requires_commands_and_monitor_to_finish_before_turn_end(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        launcher = self._launcher_v4_receipt()
        lifecycle = self._checker_lifecycle()
        validate_checker_session_lifecycle(lifecycle, launcher)
        registry.validate("checker-session-lifecycle", lifecycle)

        for field, value in (
            ("command_count", 0),
            ("all_required_commands_completed", False),
            ("all_exit_codes_observed", False),
            ("child_processes_reaped", False),
            ("completion_marker", "provider-idle-only"),
            ("command_manifest_digest", "invalid"),
        ):
            changed = json.loads(json.dumps(lifecycle))
            changed[field] = value
            with self.subTest(field=field, surface="public"), self.assertRaises(ContractError):
                registry.validate("checker-session-lifecycle", changed)
            with self.subTest(field=field, surface="specialized"), self.assertRaises(ContractError):
                validate_checker_session_lifecycle(changed, launcher)

        for field, value in (
            ("last_command_completed_at", "2026-08-08T00:01:00Z"),
            ("monitor_stopped_at", "2026-08-08T00:00:20Z"),
        ):
            changed = json.loads(json.dumps(lifecycle))
            changed[field] = value
            with self.subTest(chronology=field), self.assertRaisesRegex(ContractError, "lifecycle chronology"):
                validate_checker_session_lifecycle(changed, launcher)
        for field in ("launch_id", "session_id", "candidate_tree"):
            changed = json.loads(json.dumps(lifecycle))
            changed[field] = "other"
            with self.subTest(binding=field), self.assertRaisesRegex(ContractError, "does not bind"):
                validate_checker_session_lifecycle(changed, launcher)

    @staticmethod
    def _checker_lifecycle() -> dict[str, object]:
        return {
            "schema_version": 1,
            "lifecycle_id": "checker-lifecycle-1",
            "launch_id": "l4",
            "session_id": "s4",
            "candidate_tree": "t",
            "command_manifest_digest": sha("commands"),
            "command_manifest_locator": "artifact:checker/commands.json",
            "command_count": 3,
            "all_required_commands_completed": True,
            "all_exit_codes_observed": True,
            "child_processes_reaped": True,
            "last_command_completed_at": "2026-08-08T00:00:30Z",
            "monitor_stopped_at": "2026-08-08T00:00:45Z",
            "completion_marker": "checker-session-complete/v1",
        }

    @staticmethod
    def _launcher_v4_receipt() -> dict[str, object]:
        receipt = ContractRegistry.load(PACK / "contracts" / "registry.yml").example("launcher-v4")
        receipt["launch_id"] = "l4"
        receipt["session_id"] = "s4"
        receipt["candidate"] = {"head_sha": "h", "tree_sha": "t"}
        receipt["checkout"]["start_tree"] = "t"
        receipt["checkout"]["end_tree"] = "t"
        receipt["provider_checkpoints"]["turn_id"] = "t4"
        receipt["provider_checkpoints"]["start_ref"] = "refs/conductor-checkpoints/session-s4-turn-t4-start"
        receipt["provider_checkpoints"]["end_ref"] = "refs/conductor-checkpoints/session-s4-turn-t4-end"
        receipt["provider_checkpoints"]["start_tree"] = "t"
        receipt["provider_checkpoints"]["end_tree"] = "t"
        receipt["execution_policy"] = dict(LAUNCHER_V4_POLICY)
        return receipt

    @staticmethod
    def _launcher_v3_receipt() -> dict[str, object]:
        return {
            "schema_version": 3,
            "launch_id": "l3", "session_id": "s3", "workspace_id": "w3",
            "parent_context": False,
            "requested": {"agent": "codex", "family": "openai", "model": "gpt-check", "effort": "high"},
            "runtime": {"agent": "codex", "family": "openai", "model": "gpt-check", "effort": "high"},
            "prompt_digest": sha("prompt"), "envelope_digest": sha("env"), "spec_digest": sha("spec"),
            "candidate": {"head_sha": "h", "tree_sha": "t"},
            "checkout": {"start_tree": "t", "end_tree": "t", "start_untracked": sha("u"), "end_untracked": sha("u"), "clean": True, "read_only": True, "builder_context_input": False},
            "execution_policy": {
                **LAUNCHER_V2_POLICY,
                "macos_mach_lookup_allowlist": ["com.apple.FSEvents"],
                "seatbelt_profile_digest": sha("profile"),
            },
            "started_at": "2026-08-08T00:00:00Z", "ended_at": "2026-08-08T00:01:00Z", "termination_state": "completed",
            "raw_evidence_digest": sha("raw"), "raw_evidence_locator": "artifact:3",
        }

    def test_launcher_v3_profile_builder_applies_only_the_exact_delta(self) -> None:
        namespace = runpy.run_path(str(PACK / "skill" / "scripts" / "checker-launcher-v3.py"))
        effective_profile = namespace["effective_profile"]
        delta = namespace["PROFILE_DELTA"]
        base = b"(version 1)\n(deny default)\n"
        self.assertEqual(base + delta, effective_profile(base))
        with self.assertRaises(namespace["LauncherError"]):
            effective_profile(base + delta)

    def test_launcher_v3_executor_applies_profile_and_preserves_failure(self) -> None:
        namespace = runpy.run_path(str(PACK / "skill" / "scripts" / "checker-launcher-v3.py"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repository = root / "repository"
            external = root / "external"
            runtime = external / "runtime"
            repository.mkdir()
            runtime.mkdir(parents=True)
            base_profile = root / "base.sbpl"
            base_profile.write_bytes(b"(version 1)\n(deny default)\n")
            fake_sandbox = root / "sandbox-exec"
            fake_sandbox.write_text("#!/bin/sh\nshift 2\nexec \"$@\"\n")
            fake_sandbox.chmod(0o755)
            expected_digest = namespace["sha256_bytes"](namespace["effective_profile"](base_profile.read_bytes()))
            environment = {
                **{key: str(runtime / key.lower()) for key in namespace["EXTERNAL_ENVIRONMENT_KEYS"]},
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            class CapturedStdout:
                def __init__(self) -> None:
                    self.buffer = io.BytesIO()

            captured = CapturedStdout()
            namespace["main"].__globals__["SANDBOX_EXEC"] = fake_sandbox
            with patch.dict(os.environ, environment, clear=True), \
                    patch.object(namespace["platform"], "system", return_value="Darwin"), \
                    patch.object(namespace["sys"], "stdout", captured):
                exit_code = namespace["main"]([
                    "--repository", str(repository),
                    "--base-profile", str(base_profile),
                    "--expected-profile-digest", expected_digest,
                    "--external-root", str(external),
                    "--evidence-dir", str(external / "evidence"),
                    "--", sys.executable, "-c", "raise SystemExit(13)",
                ])
            self.assertEqual(13, exit_code)
            evidence = json.loads((external / "evidence" / "launcher-execution.json").read_text())
            self.assertEqual(13, evidence["exit_code"])
            self.assertEqual(expected_digest, evidence["profile_digest"])
            self.assertEqual(["com.apple.FSEvents"], evidence["allowlist"])

    def test_each_gate_has_machine_reason_and_g9_never_dispatches(self) -> None:
        facts = {f"G{i}": True for i in range(1, 9)}
        result = evaluate_gates(facts)
        self.assertTrue(result["pass"])
        facts["G6"] = False
        failed = evaluate_gates(facts)
        self.assertEqual(["G6"], [x["id"] for x in failed["failures"]])
        simulation = simulate_g9({"delivery_enabled": True, "generation_current": True, "expected_head": True, "operations_reconciled": True})
        self.assertTrue(simulation["would_authorize"])
        self.assertFalse(simulation["dispatched"])

    def test_every_gate_failure_is_named(self) -> None:
        for gate in [f"G{i}" for i in range(1, 9)]:
            facts = {f"G{i}": True for i in range(1, 9)}
            facts[gate] = False
            result = evaluate_gates(facts)
            self.assertEqual([gate], [item["id"] for item in result["failures"]])


class K41MergeBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        self.envelope = envelope()
        self.envelope.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge",
        })
        self.envelope["authority"].update({
            "maximum": "merge",
            "builder_maximum": "open-pr",
            "coordinator_maximum": "open-pr",
            "fresh_merge_agent_maximum": "merge",
            "tier_b_authority": False,
            "non_bypass_protection": False,
            "deploy_authority": False,
            "release_authority": False,
            "repository": "owner/repo",
            "project": "sample-project",
            "mission_id": "delivery-example",
            "base_ref": "main",
            "merge_method": "squash",
            "risk_class": "test-tooling",
            "planning_prefix": "planning/example/",
            "implementation_paths": ["tests/example.test.ts"],
            "candidate_binding": "post-freeze",
            "pr_binding": "post-pr",
        })
        self.approval = registry.example("approval")
        self.approval.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge", "envelope_digest": digest(self.envelope), "actor_id": "human-1",
        })
        self.attempt = registry.example("pilot-attempt")
        self.attempt.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge", "mission_id": "delivery-example", "envelope_digest": digest(self.envelope),
        })
        self.gate = registry.example("merge-gate")
        self.gate["issued_at"] = "2026-08-08T00:03:00Z"
        self.candidate = {
            "head_sha": self.gate["candidate_head"],
            "tree_sha": self.gate["candidate_tree"],
            "base_sha": "2" * 40,
            "policy_sha": "4" * 40,
            "ruleset_fingerprint": sha("ruleset"),
            "verification_environment_digest": sha("verification-environment"),
            "merge_group_sha": None,
        }
        self.gate["candidate"] = dict(self.candidate)
        self.approval["envelope_digest"] = digest(self.envelope)
        self.attempt["envelope_digest"] = digest(self.envelope)
        self.handback = registry.example("handback")
        self.handback.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge", "candidate": dict(self.candidate),
            "issued_at": "2026-08-08T00:04:00Z",
        })
        self.launcher = registry.example("launcher-v4")
        self.policy = json.loads((PACK / "skill/references/k41-policy.json").read_text())
        self.gate["policy_digest"] = digest(self.policy)
        self.standing_authority = registry.example("k41-standing-authority")
        self.standing_authority.update({
            "repository": "owner/repo", "policy_digest": digest(self.policy),
            "approved_at": "2026-08-17T00:00:00Z", "expires_at": "2026-09-18T00:00:00Z",
        })
        self.launcher.update({
            "session_id": "fresh-1", "workspace_id": "workspace-fresh-1",
            "requested": {"family": "openai", "model": "gpt", "effort": "high", "role": "fresh-merge-agent"},
            "runtime": {"family": "openai", "model": "gpt", "effort": "high", "role": "fresh-merge-agent"},
            "prompt_digest": self.standing_authority["prompt_digest"],
            "spec_digest": self.standing_authority["spec_digest"],
            "envelope_digest": digest(self.envelope),
            "candidate": dict(self.candidate),
            "started_at": "2026-08-08T00:05:00Z", "ended_at": "2026-08-08T00:06:00Z",
        })
        self.launcher["checkout"].update({
            "start_head_sha": self.gate["candidate_head"], "end_head_sha": self.gate["candidate_head"],
            "start_tree": self.gate["candidate_tree"], "end_tree": self.gate["candidate_tree"],
        })
        self.launcher["provider_checkpoints"].update({
            "start_ref": "refs/conductor-checkpoints/session-fresh-1-turn-t1-start",
            "end_ref": "refs/conductor-checkpoints/session-fresh-1-turn-t1-end",
            "start_tree": self.gate["candidate_tree"], "end_tree": self.gate["candidate_tree"],
            "start_created_at": "2026-08-08T00:05:01Z", "end_created_at": "2026-08-08T00:05:59Z",
        })
        self.facts = {
            "repository": "owner/repo", "pr_number": 1, "risk_class": "test-tooling",
            "changed_paths": ["tests/example.test.ts"], "controller_generation": 7, "kill_generation": 1,
            "control_ref": "refs/heads/delivery-control/delivery-example",
            "control_commit": "3" * 40,
            "control_digest": sha("control"),
            "implementation_digest": self.standing_authority["implementation_digest"],
            "host": {
                "repository": "owner/repo", "pr_number": 1, "base_ref": "main",
                "head_sha": self.gate["candidate_head"], "tree_sha": self.gate["candidate_tree"],
                "candidate": dict(self.candidate),
                "merge_method": "squash", "default_branch": "main",
                "default_branch_policy_digest": digest(self.policy),
            },
            "builder_session_ids": ["builder-1"], "coordinator_session_id": "coordinator-1",
            "verification_digests": [sha("verification")],
            "evidence_locators": ["linear:issue:TASK-1"],
            "pr_open": True, "mergeable": True, "checks_pass": True, "verification_pass": True,
            "checkout_clean": True, "evidence_resolved": True, "review_threads_closed": True,
            "reviews_clear": True,
            "findings_closed": True, "required_actions_closed": True, "standing_authority_current": True,
            "default_branch_policy_current": True, "kill_switch_enabled": True, "generation_current": True,
        }

    def decision(self, **changes: object) -> dict:
        facts = json.loads(json.dumps(self.facts))
        facts.update(changes)
        return issue_merge_decision(
            envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
            handback=self.handback, launcher=self.launcher, policy=self.policy, facts=facts,
            standing_authority=self.standing_authority,
            issued_at="2026-08-18T00:00:00Z",
        )

    def test_bridge_authority_does_not_widen_builder_or_tier_b(self) -> None:
        validate_bridge_authority_chain(self.envelope, self.approval, self.attempt, self.gate, self.handback)
        widened = json.loads(json.dumps(self.envelope))
        widened["authority"]["builder_maximum"] = "merge"
        with self.assertRaisesRegex(ContractError, "builder_maximum"):
            validate_bridge_authority_chain(widened, self.approval, self.attempt, self.gate, self.handback)
        tier_b = json.loads(json.dumps(self.envelope))
        tier_b["authority"]["tier_b_authority"] = True
        with self.assertRaisesRegex(ContractError, "tier_b_authority"):
            validate_bridge_authority_chain(tier_b, self.approval, self.attempt, self.gate, self.handback)
        attempt_b = dict(self.attempt, tier="B")
        with self.assertRaisesRegex(ContractError, "only a Tier A"):
            validate_bridge_authority_chain(self.envelope, self.approval, attempt_b, self.gate, self.handback)
        with self.assertRaisesRegex(ContractError, "attempt project"):
            validate_bridge_authority_chain(
                self.envelope, self.approval, dict(self.attempt, project="alternate-project"), self.gate, self.handback,
            )
        with self.assertRaisesRegex(ContractError, "handback PR"):
            validate_bridge_authority_chain(
                self.envelope, self.approval, self.attempt, self.gate, dict(self.handback, pr_ref="github:pr/0"),
            )
        for field in ("base_sha", "policy_sha", "ruleset_fingerprint", "verification_environment_digest", "merge_group_sha"):
            changed = json.loads(json.dumps(self.handback))
            changed["candidate"][field] = "f" * 40
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, "frozen candidate tuples differ"):
                validate_bridge_authority_chain(self.envelope, self.approval, self.attempt, self.gate, changed)

    def test_envelope_binds_scope_upfront_and_defers_candidate_and_pr(self) -> None:
        validate_k41_envelope(self.envelope)
        ContractRegistry.load(PACK / "contracts" / "registry.yml").validate("envelope", self.envelope)
        for field, value in (
            ("pr_number", 1),
            ("candidate_head", "0" * 40),
            ("candidate_tree", "1" * 40),
            ("candidate", dict(self.candidate)),
        ):
            altered = json.loads(json.dumps(self.envelope))
            altered["authority"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, "defers post-freeze fields"):
                validate_k41_envelope(altered)

    def test_decision_enforces_approved_scope_after_pr_exists(self) -> None:
        decision = self.decision(changed_paths=["planning/example/qa.json", "tests/example.test.ts"])
        self.assertEqual("allow", decision["decision"])
        self.assertEqual({
            "risk_class": "test-tooling",
            "planning_prefix": "planning/example/",
            "implementation_paths": ["tests/example.test.ts"],
        }, decision["approved_scope"])
        self.assertEqual(
            ["scope-outside-approved-paths"],
            self.decision(changed_paths=["src/unapproved.ts", "tests/example.test.ts"])["reason_codes"],
        )
        self.assertEqual(
            ["scope-outside-approved-paths"],
            self.decision(changed_paths=["planning/example/qa.json"])["reason_codes"],
        )
        self.assertEqual(
            ["human-merge-required", "scope-outside-approved-paths"],
            self.decision(risk_class="runtime")["reason_codes"],
        )
        malformed = json.loads(json.dumps(self.envelope))
        malformed["authority"]["implementation_paths"] = ["tests//example.test.ts"]
        with self.assertRaisesRegex(ContractError, "normalized repository-relative"):
            validate_k41_envelope(malformed)

    def test_decision_denies_malformed_or_duplicate_host_paths(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        for changed_paths in (
            [],
            ["tests/example.test.ts", "tests/example.test.ts"],
            ["tests//example.test.ts"],
            ["tests/./example.test.ts"],
            ["tests/../example.test.ts"],
            ["/tests/example.test.ts"],
            ["tests/example/"],
            [r"tests\example.test.ts"],
            [1],
            [None],
        ):
            with self.subTest(changed_paths=changed_paths):
                decision = self.decision(changed_paths=changed_paths)
                self.assertEqual("deny", decision["decision"])
                self.assertEqual(["scope-outside-approved-paths"], decision["reason_codes"])
                self.assertEqual(changed_paths, decision["changed_paths"])
                validate_merge_decision(decision)
                registry.validate("merge-decision", decision)
                with self.assertRaisesRegex(ContractError, "denied decision cannot dispatch"):
                    dispatch_merge(decision, None, "fresh-1")  # type: ignore[arg-type]

        invalid_policy = dict(self.policy)
        del invalid_policy["policy_version"]
        invalid_gate = json.loads(json.dumps(self.gate))
        invalid_gate["policy_digest"] = digest(invalid_policy)
        invalid_authority = dict(self.standing_authority, policy_digest=digest(invalid_policy))
        invalid_facts = json.loads(json.dumps(self.facts))
        invalid_facts["changed_paths"] = ["tests//example.test.ts"]
        invalid_facts["host"]["default_branch_policy_digest"] = digest(invalid_policy)
        with self.assertRaisesRegex(ContractError, "policy fields are incomplete"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=invalid_gate,
                handback=self.handback, launcher=self.launcher, policy=invalid_policy,
                facts=invalid_facts, standing_authority=invalid_authority,
                issued_at="2026-08-18T00:00:00Z",
            )

        for changed_paths in ("tests/example.test.ts", None, {}):
            with self.subTest(non_list=changed_paths), self.assertRaisesRegex(ContractError, "must be a list"):
                self.decision(changed_paths=changed_paths)

    def test_full_frozen_candidate_tuple_binds_launcher_host_and_decision(self) -> None:
        decision = self.decision()
        self.assertEqual(self.candidate, decision["expected_candidate"])
        altered_launcher = json.loads(json.dumps(self.launcher))
        altered_launcher["candidate"]["policy_sha"] = "f" * 40
        with self.assertRaisesRegex(ContractError, "launcher: candidate tuple mismatch"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=altered_launcher, policy=self.policy, facts=self.facts,
                standing_authority=self.standing_authority, issued_at="2026-08-18T00:00:00Z",
            )
        altered_host = json.loads(json.dumps(self.facts["host"]))
        altered_host["candidate"]["verification_environment_digest"] = sha("drifted-environment")
        self.assertEqual("deny", self.decision(host=altered_host)["decision"])
        malformed = json.loads(json.dumps(decision))
        del malformed["expected_candidate"]["base_sha"]
        with self.assertRaisesRegex(ContractError, "incomplete frozen candidate"):
            validate_merge_decision(malformed)

    def test_public_contracts_reject_partial_bridge_authority(self) -> None:
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        for schema_id in ("envelope", "approval", "pilot-attempt", "handback"):
            with self.subTest(schema_id=schema_id):
                record = registry.example(schema_id)
                record["rollout_milestone"] = "K4.1"
                with self.assertRaisesRegex(ContractError, "must appear together"):
                    registry.validate(schema_id, record)
                schema = json.loads((PACK / f"contracts/generated/schemas/{schema_id}.schema.json").read_text())
                self.assertEqual(
                    ["authority_class", "maximum_action"],
                    schema["dependentRequired"]["rollout_milestone"],
                )
        public_envelope = envelope()
        public_envelope.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge",
        })
        with self.assertRaisesRegex(ContractError, "authority maximum"):
            registry.validate("envelope", public_envelope)
        public_attempt = registry.example("pilot-attempt")
        public_attempt.update({
            "rollout_milestone": "K4.1", "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge", "tier": "B",
        })
        with self.assertRaisesRegex(ContractError, "tier must be A"):
            registry.validate("pilot-attempt", public_attempt)

        public_handback = registry.example("handback")
        public_handback.update({
            "rollout_milestone": "K4.1",
            "authority_class": "process-attested-fresh-merge",
            "maximum_action": "merge",
            "pr_ref": "github:pr/0",
        })
        with self.assertRaisesRegex(ContractError, "positive post-freeze PR"):
            registry.validate("handback", public_handback)

        for field in ("actor_id", "source_event_id"):
            standing = registry.example("k41-standing-authority")
            standing[field] = ""
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, f"empty {field}"):
                registry.validate("k41-standing-authority", standing)

        merge_receipt = registry.example("process-attested-merge")
        merge_receipt["outcome"] = "merged"
        with self.assertRaisesRegex(ContractError, "lacks merge commit"):
            registry.validate("process-attested-merge", merge_receipt)
        merge_receipt["merge_commit_sha"] = "not-a-sha"
        with self.assertRaisesRegex(ContractError, "invalid Git SHA"):
            registry.validate("process-attested-merge", merge_receipt)
        merge_receipt = registry.example("process-attested-merge")
        merge_receipt.update({
            "dispatch_mode": "reconcile-only",
            "outcome": "merged",
            "merge_commit_sha": "9" * 40,
        })
        with self.assertRaisesRegex(ContractError, "reconciliation must remain ambiguous"):
            registry.validate("process-attested-merge", merge_receipt)
        merge_receipt = registry.example("process-attested-merge")
        merge_receipt["decision_authorization"] = "deny"
        with self.assertRaisesRegex(ContractError, "unknown decision_authorization"):
            registry.validate("process-attested-merge", merge_receipt)
        merge_receipt = registry.example("process-attested-merge")
        merge_receipt.update({"dispatch_mode": "reconcile-only", "outcome": "ambiguous"})
        with self.assertRaisesRegex(ContractError, "reconciliation must record ambiguity"):
            registry.validate("process-attested-merge", merge_receipt)

    def test_allow_decision_binds_fresh_session_exact_tuple_and_policy(self) -> None:
        decision = self.decision()
        self.assertEqual("allow", decision["decision"])
        self.assertEqual(self.launcher["session_id"], decision["agent"]["session_id"])
        self.assertEqual(self.launcher["runtime"]["model"], decision["agent"]["model"])
        self.assertEqual(["all-controls-pass"], decision["reason_codes"])
        self.assertEqual(self.envelope["authority"]["implementation_paths"], decision["approved_scope"]["implementation_paths"])
        self.assertFalse(decision["non_bypass_protection"])
        validate_merge_decision(decision)
        ContractRegistry.load(PACK / "contracts" / "registry.yml").validate("merge-decision", decision)

        for field in ("session_id", "family", "model", "effort"):
            altered = json.loads(json.dumps(decision))
            altered["agent"][field] = ""
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, "agent provenance strings"):
                validate_merge_decision(altered)

        forged = json.loads(json.dumps(decision))
        forged["changed_paths"] = [".github/workflows/merge.yml"]
        forged["protected_path_matches"] = []
        with self.assertRaisesRegex(ContractError, "protected path classification mismatch"):
            validate_merge_decision(forged)

        forged = json.loads(json.dumps(decision))
        forged["risk_policy"]["human_merge_path_prefixes"] = ["safe-only/"]
        with self.assertRaisesRegex(ContractError, "risk policy does not bind policy digest"):
            validate_merge_decision(forged)

    def test_decision_attestation_requires_exact_durable_readback_and_session(self) -> None:
        decision = self.decision()
        registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        attestation = registry.example("merge-decision-attestation")
        attestation.update({
            "decision_digest": digest(decision),
            "readback_digest": digest(decision),
            "session_id": decision["agent"]["session_id"],
            "attested_at": "2026-08-18T00:01:00Z",
        })
        registry.validate("merge-decision-attestation", attestation)
        validate_merge_decision_attestation(attestation, decision)

        for field, value, message in (
            ("decision_digest", sha("other-decision"), "decision digest mismatch"),
            ("readback_digest", sha("other-readback"), "durable readback digest mismatch"),
            ("session_id", "different-session", "session mismatch"),
            ("attested_at", "2026-08-17T23:59:59Z", "readback predates decision"),
        ):
            altered = {**attestation, field: value}
            with self.subTest(field=field), self.assertRaisesRegex(ContractError, message):
                validate_merge_decision_attestation(altered, decision)

    def test_github_decision_store_posts_and_rereads_exact_canonical_body(self) -> None:
        decision = self.decision()
        stored: dict[str, object] = {"issue_url": "https://api.github.com/repos/owner/repo/issues/1"}

        def runner(command, **kwargs):
            if "--method" in command:
                stored["body"] = next(item.removeprefix("body=") for item in command if item.startswith("body="))
                body = {"id": 41, "created_at": "2026-08-18T00:01:00Z", "body": stored["body"], "issue_url": stored["issue_url"]}
            else:
                body = {"id": 41, "created_at": "2026-08-18T00:01:00Z", "body": stored["body"], "issue_url": stored["issue_url"]}
            return subprocess.CompletedProcess(command, 0, json.dumps(body), "")

        store = GitHubCliDecisionStore(runner=runner)
        attestation = store.persist(decision)
        self.assertEqual("github:issue-comment:owner/repo:1:41", attestation["source_event_id"])
        self.assertEqual(canonical_bytes(decision).decode(), stored["body"])
        store.verify(attestation, decision)
        stored["body"] = canonical_bytes({**decision, "decision": "deny"}).decode()
        with self.assertRaisesRegex(ContractError, "host readback body mismatch"):
            store.verify(attestation, decision)
        stored["body"] = canonical_bytes(decision).decode()
        stored["issue_url"] = "https://api.github.com/repos/owner/repo/issues/999"
        with self.assertRaisesRegex(ContractError, "host comment subject mismatch"):
            store.verify(attestation, decision)

    def test_github_operation_claim_is_durable_and_one_shot(self) -> None:
        refs: dict[str, str] = {}

        def runner(command, **kwargs):
            if "--method" in command:
                ref = next(item.removeprefix("ref=") for item in command if item.startswith("ref="))
                sha_value = next(item.removeprefix("sha=") for item in command if item.startswith("sha="))
                if ref in refs:
                    return subprocess.CompletedProcess(command, 1, json.dumps({"status": "422"}), "")
                refs[ref] = sha_value
                return subprocess.CompletedProcess(command, 0, json.dumps({"ref": ref}), "")
            operation_ref = next(iter(refs))
            return subprocess.CompletedProcess(
                command, 0, json.dumps({"ref": operation_ref, "object": {"sha": refs[operation_ref]}}), "",
            )

        host = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=runner,
        )
        operation_id = "op-merge-" + "0" * 64
        decision_digest = "sha256:" + "0" * 64
        self.assertTrue(host.claim_operation("owner/repo", 1, operation_id, decision_digest, "a" * 40))
        self.assertFalse(host.claim_operation("owner/repo", 1, operation_id, decision_digest, "a" * 40))
        self.assertTrue(host.operation_claimed("owner/repo", operation_id, "a" * 40))
        self.assertEqual(1, len(refs))

    def test_head_base_method_open_work_and_missing_evidence_fail_closed(self) -> None:
        cases = (
            {"host": {**self.facts["host"], "head_sha": "changed"}},
            {"host": {**self.facts["host"], "base_ref": "wrong"}},
            {"host": {**self.facts["host"], "merge_method": "merge"}},
            {"findings_closed": False},
            {"evidence_resolved": False},
            {"generation_current": False},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.assertEqual("deny", self.decision(**changes)["decision"])

        with self.assertRaisesRegex(ContractError, "predates approval"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=self.launcher, policy=self.policy, facts=self.facts,
                standing_authority=self.standing_authority, issued_at="2026-08-16T00:00:00Z",
            )

        wrong_launcher = json.loads(json.dumps(self.launcher))
        wrong_launcher["candidate"]["head_sha"] = "f" * 40
        with self.assertRaisesRegex(ContractError, "candidate tuple mismatch"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=wrong_launcher, policy=self.policy, facts=self.facts,
                standing_authority=self.standing_authority, issued_at="2026-08-18T00:00:00Z",
            )
        wrong_prompt = json.loads(json.dumps(self.launcher))
        wrong_prompt["prompt_digest"] = sha("other-prompt")
        with self.assertRaisesRegex(ContractError, "prompt digest mismatch"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=wrong_prompt, policy=self.policy, facts=self.facts,
                standing_authority=self.standing_authority, issued_at="2026-08-18T00:00:00Z",
            )
        wrong_checkout = json.loads(json.dumps(self.launcher))
        wrong_checkout["checkout"]["start_tree"] = wrong_checkout["checkout"]["end_tree"] = "f" * 40
        with self.assertRaisesRegex(ContractError, "checkout tree"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=wrong_checkout, policy=self.policy, facts=self.facts,
                standing_authority=self.standing_authority, issued_at="2026-08-18T00:00:00Z",
            )
        wrong_branch_authority = dict(self.standing_authority, default_branch="release")
        with self.assertRaisesRegex(ContractError, "gate base"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=self.launcher, policy=self.policy, facts=self.facts,
                standing_authority=wrong_branch_authority, issued_at="2026-08-18T00:00:00Z",
            )
        with self.assertRaisesRegex(ContractError, "project mismatch"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=self.launcher, policy=self.policy, facts=self.facts,
                standing_authority=dict(self.standing_authority, project="alternate-project"),
                issued_at="2026-08-18T00:00:00Z",
            )

    def test_protected_paths_and_unknown_risk_require_human_merge(self) -> None:
        protected = self.decision(changed_paths=[".github/workflows/merge.yml"])
        self.assertEqual("deny", protected["decision"])
        self.assertEqual([".github/workflows/merge.yml"], protected["protected_path_matches"])
        self.assertEqual(["risk:security"], classify_paths(self.policy, ["src/a.ts"], "security"))
        self.assertEqual(
            [".claude/rules/review.md", "AGENTS.override.md", "CODEOWNERS", "docs/CODEOWNERS", "package.json", "packages/app/CLAUDE.md", "src/auth/login.py"],
            classify_paths(
                self.policy,
                ["AGENTS.override.md", "packages/app/CLAUDE.md", ".claude/rules/review.md", "CODEOWNERS", "docs/CODEOWNERS", "package.json", "src/auth/login.py"],
                "documentation-maintenance",
            ),
        )

    def test_builder_self_merge_is_denied_and_cannot_dispatch(self) -> None:
        self.assertEqual("deny", self.decision(builder_session_ids=["fresh-1"])["decision"])
        self.assertEqual("deny", self.decision(coordinator_session_id="fresh-1")["decision"])
        denied = self.decision(findings_closed=False)
        with self.assertRaises(ContractError):
            dispatch_merge(denied, object(), "fresh-1")

    def test_expected_head_dispatch_and_observe_before_retry(self) -> None:
        decision = self.decision()

        class Host:
            def __init__(self, *, timeout: bool = False, change_head: bool = False, observation_failure: bool = False, visibility_lag: bool = False, wrong_merged_head: bool = False, missing_merge_sha: bool = False):
                self.timeout = timeout
                self.change_head = change_head
                self.observation_failure = observation_failure
                self.visibility_lag = visibility_lag
                self.wrong_merged_head = wrong_merged_head
                self.missing_merge_sha = missing_merge_sha
                self.dispatched = 0
                self.merged = False
                self.claimed = False

            def inspect(self, repository: str, pr_number: int) -> dict:
                if self.observation_failure and self.dispatched:
                    raise ContractError("post-dispatch observation unavailable")
                head = "changed" if self.change_head and not self.merged else decision["expected_head_sha"]
                return {
                    "repository": repository, "pr_number": pr_number, "base_ref": decision["base_ref"],
                    "default_branch": decision["base_ref"], "default_branch_policy_current": True,
                    "default_branch_policy_digest": decision["policy_digest"],
                    "head_sha": head, "merge_method": decision["merge_method"], "mergeable": True,
                    "tree_sha": decision["expected_tree_sha"], "candidate": decision["expected_candidate"],
                    "checks_pass": True, "pr_open": not self.merged, "review_threads_closed": True,
                    "reviews_clear": True,
                    "standing_authority_current": True, "kill_switch_enabled": True, "generation_current": True,
                    "standing_authority_digest": decision["standing_authority_digest"],
                    "changed_paths": decision["changed_paths"],
                    "controller_generation": decision["controller_generation"],
                    "control_ref": decision["control_ref"], "control_commit": decision["control_commit"],
                    "control_digest": decision["control_digest"],
                    "merged": self.merged,
                    "merged_head_sha": "f" * 40 if self.wrong_merged_head and self.merged else decision["expected_head_sha"],
                    "merge_commit_sha": None if self.missing_merge_sha else (
                        "2222222222222222222222222222222222222222" if self.merged else None
                    ),
                    "evidence_locator": "github:owner/repo/pull/1",
                }

            def merge(self, repository: str, pr_number: int, expected_head_sha: str, merge_method: str, operation_id: str) -> dict:
                self.dispatched += 1
                self.assertions = (expected_head_sha, merge_method, operation_id)
                if not self.visibility_lag:
                    self.merged = True
                if self.timeout:
                    raise TimeoutError("lost response")
                return {"merged": True}

            def claim_operation(self, repository: str, pr_number: int, operation_id: str, decision_digest: str, expected_head_sha: str) -> bool:
                if self.claimed:
                    return False
                self.claimed = True
                return True

            def operation_claimed(self, repository: str, operation_id: str, expected_head_sha: str) -> bool:
                return self.claimed

        host = Host()
        receipt = dispatch_merge(decision, host, "fresh-1")
        self.assertEqual("merged", receipt["outcome"])
        self.assertEqual(1, host.dispatched)
        self.assertEqual(decision["expected_head_sha"], host.assertions[0])
        incomplete = dict(receipt)
        incomplete.pop("host_evidence_locator")
        with self.assertRaisesRegex(ContractError, "receipt fields are incomplete"):
            validate_process_attested_merge(incomplete, decision)
        altered = dict(receipt)
        altered.update({"dispatch_mode": "reconcile-only", "outcome": "merged"})
        with self.assertRaisesRegex(ContractError, "reconciliation must remain ambiguous"):
            validate_process_attested_merge(altered, decision)
        altered = dict(receipt)
        altered.update({
            "dispatch_mode": "reconcile-only", "outcome": "ambiguous",
            "merge_commit_sha": None, "ambiguous_response_observed": False,
        })
        with self.assertRaisesRegex(ContractError, "reconciliation must record ambiguity"):
            validate_process_attested_merge(altered, decision)
        altered = dict(receipt)
        altered["ambiguous_response_observed"] = True
        with self.assertRaisesRegex(ContractError, "outcome and ambiguity flag disagree"):
            validate_process_attested_merge(altered, decision)
        deny = self.decision(changed_paths=[".github/workflows/merge.yml"])
        self.assertEqual("deny", deny["decision"])
        altered = dict(receipt, decision_digest=digest(deny))
        with self.assertRaisesRegex(ContractError, "only an allow decision"):
            validate_process_attested_merge(altered, deny)

        visibility_lag = Host(visibility_lag=True)
        receipt = dispatch_merge(decision, visibility_lag, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        reconciled = dispatch_merge(decision, visibility_lag, "fresh-1")
        self.assertEqual("ambiguous", reconciled["outcome"])
        self.assertEqual("reconcile-only", reconciled["dispatch_mode"])
        self.assertEqual(1, visibility_lag.dispatched)
        visibility_lag.merged = True
        reconciled = dispatch_merge(decision, visibility_lag, "fresh-1")
        self.assertEqual("ambiguous", reconciled["outcome"])
        self.assertEqual("reconcile-only", reconciled["dispatch_mode"])
        self.assertIsNone(reconciled["merge_commit_sha"])
        self.assertEqual(1, visibility_lag.dispatched)

        lost_then_visible = Host(timeout=True)
        first = dispatch_merge(decision, lost_then_visible, "fresh-1")
        self.assertEqual("ambiguous", first["outcome"])
        second = dispatch_merge(decision, lost_then_visible, "fresh-1")
        self.assertEqual("ambiguous", second["outcome"])
        self.assertEqual("reconcile-only", second["dispatch_mode"])
        self.assertIsNone(second["merge_commit_sha"])
        self.assertEqual(1, lost_then_visible.dispatched)

        already_merged = Host()
        already_merged.merged = True
        with self.assertRaisesRegex(ContractError, "without this K4.1 operation claim"):
            dispatch_merge(decision, already_merged, "fresh-1")
        self.assertFalse(already_merged.claimed)

        wrong_observation = Host(wrong_merged_head=True)
        receipt = dispatch_merge(decision, wrong_observation, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        self.assertIsNone(receipt["merge_commit_sha"])

        missing_merge_sha = Host(missing_merge_sha=True)
        receipt = dispatch_merge(decision, missing_merge_sha, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        self.assertIsNone(receipt["merge_commit_sha"])
        self.assertTrue(receipt["ambiguous_response_observed"])
        self.assertEqual(1, missing_merge_sha.dispatched)

        lost_reply = Host(timeout=True)
        receipt = dispatch_merge(decision, lost_reply, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        self.assertTrue(receipt["ambiguous_response_observed"])
        self.assertEqual(1, lost_reply.dispatched)

        external = Host()
        def failed_merge(*args, **kwargs):
            external.dispatched += 1
            external.merged = True
            raise ContractError("host rejected request")
        external.merge = failed_merge
        receipt = dispatch_merge(decision, external, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        self.assertIsNone(receipt["merge_commit_sha"])

        unavailable = Host(timeout=True, observation_failure=True)
        receipt = dispatch_merge(decision, unavailable, "fresh-1")
        self.assertEqual("ambiguous", receipt["outcome"])
        self.assertEqual(1, unavailable.dispatched)

        with self.assertRaisesRegex(ContractError, "deciding fresh-agent session"):
            dispatch_merge(decision, Host(), "builder-1")

        stale = Host(change_head=True)
        with self.assertRaisesRegex(ContractError, "tuple differs"):
            dispatch_merge(decision, stale, "fresh-1")
        self.assertEqual(0, stale.dispatched)

    def test_github_adapter_uses_expected_head_and_reads_review_threads(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if command[:3] == ["gh", "pr", "view"]:
                body = {
                    "state": "OPEN", "isDraft": False, "headRefOid": self.gate["candidate_head"],
                    "baseRefName": "main", "baseRefOid": self.candidate["base_sha"], "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                    "statusCheckRollup": [{"name": "required-ci", "conclusion": "SUCCESS"}], "reviewDecision": "", "mergedAt": None,
                    "mergeCommit": None, "url": "https://github.com/owner/repo/pull/1",
                }
            elif command[:3] == ["gh", "api", f"repos/owner/repo/git/commits/{self.gate['candidate_head']}"]:
                body = {"tree": {"sha": self.gate["candidate_tree"]}}
            elif command[:3] == ["gh", "api", "graphql"]:
                body = {"data": {"repository": {"pullRequest": {
                    "reviewThreads": {"nodes": [{"isResolved": True}], "pageInfo": {"hasNextPage": False}},
                }}}}
            elif command[:4] == ["gh", "api", "--paginate", "--slurp"]:
                body = [[{
                    "filename": "tests/example.test.ts", "previous_filename": ".github/workflows/old.yml",
                    "status": "renamed",
                }]]
            elif command[:3] == ["gh", "api", "repos/owner/repo"]:
                body = {"default_branch": "main"}
            elif command[:3] == ["gh", "api", "repos/owner/repo/contents/.agents/skills/ai-playbook-deliver/references/k41-policy.json?ref=main"]:
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(self.policy)).decode()}
            elif command[:3] == ["gh", "api", "repos/owner/repo/contents/.agents/k41-standing-authority.json?ref=main"]:
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(self.standing_authority)).decode()}
            elif command[:3] == ["gh", "api", "repos/owner/repo/git/ref/heads/delivery-control/delivery-example"]:
                body = {"object": {"sha": "3" * 40}}
            elif command[:3] == ["gh", "api", "repos/owner/repo/contents/mission.yml?ref=" + "3" * 40]:
                control = mission()
                control.update({
                    "mission_id": "delivery-example", "control_ref": "refs/heads/delivery-control/delivery-example",
                    "controller": {"generation": 7, "workspace_id": "workspace-1", "session_id": "coordinator-1"},
                })
                control["candidate"].update({
                    **self.candidate,
                    "head_sha": self.gate["candidate_head"], "tree_sha": self.gate["candidate_tree"],
                    "builder_session_ids": ["builder-1"], "frozen_at": "2026-08-08T00:00:00Z",
                })
                control["authority"]["envelope_digest"] = digest(self.envelope)
                control["aggregate"].update({"phase": "handback", "status": "running"})
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(control)).decode()}
            else:
                body = {"merged": True, "sha": "2222222222222222222222222222222222222222"}
            return subprocess.CompletedProcess(command, 0, json.dumps(body), "")

        adapter = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope),
            mission_id="delivery-example", runner=runner,
        )
        observed = adapter.inspect("owner/repo", 1)
        self.assertTrue(observed["review_threads_closed"])
        self.assertTrue(observed["checks_pass"])
        self.assertTrue(observed["default_branch_policy_current"])
        self.assertIn(".github/workflows/old.yml", observed["changed_paths"])
        adapter.merge("owner/repo", 1, self.gate["candidate_head"], "squash", "op-merge-" + "0" * 64)
        merge_call = calls[-1]
        self.assertIn(f"sha={self.gate['candidate_head']}", merge_call)
        self.assertIn("merge_method=squash", merge_call)

        def graphql_error_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "graphql"]:
                return subprocess.CompletedProcess(command, 0, json.dumps({"errors": [{"message": "denied"}]}), "")
            return runner(command, **kwargs)

        broken = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope),
            mission_id="delivery-example", runner=graphql_error_runner,
        )
        with self.assertRaisesRegex(ContractError, "GraphQL errors"):
            broken.inspect("owner/repo", 1)

        def incomplete_page_info_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "graphql"]:
                body = {"data": {"repository": {"pullRequest": {
                    "reviewThreads": {"nodes": [{"isResolved": True}], "pageInfo": {}},
                }}}}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)

        incomplete_pages = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope),
            mission_id="delivery-example", runner=incomplete_page_info_runner,
        )
        with self.assertRaisesRegex(ContractError, "review-thread observation is incomplete"):
            incomplete_pages.inspect("owner/repo", 1)

        def saturated_files_runner(command, **kwargs):
            if command[:4] == ["gh", "api", "--paginate", "--slurp"]:
                body = [[{"filename": f"tests/file-{index}.test.ts", "status": "modified"} for index in range(3000)]]
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)

        saturated = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope),
            mission_id="delivery-example", runner=saturated_files_runner,
        )
        with self.assertRaisesRegex(ContractError, "GitHub files API limit"):
            saturated.inspect("owner/repo", 1)

        future_authority = dict(
            self.standing_authority, approved_at="2099-01-01T00:00:00Z", expires_at="2100-01-01T00:00:00Z",
        )
        def future_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "repos/owner/repo/contents/.agents/k41-standing-authority.json?ref=main"]:
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(future_authority)).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        future = GitHubCliMergeHost(
            merge_method="squash", standing_authority=future_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=future_runner,
        )
        self.assertFalse(future.inspect("owner/repo", 1)["standing_authority_current"])

        def finding_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "repos/owner/repo/contents/mission.yml?ref=" + "3" * 40]:
                control = mission()
                control.update({
                    "mission_id": "delivery-example", "control_ref": "refs/heads/delivery-control/delivery-example",
                    "controller": {"generation": 7, "workspace_id": "workspace-1", "session_id": "coordinator-1"},
                })
                control["candidate"].update({
                    **self.candidate,
                    "head_sha": self.gate["candidate_head"], "tree_sha": self.gate["candidate_tree"],
                    "builder_session_ids": ["builder-1"], "frozen_at": "2026-08-08T00:00:00Z",
                })
                control["authority"]["envelope_digest"] = digest(self.envelope)
                control["aggregate"].update({"phase": "handback", "status": "running"})
                finding = ContractRegistry.load(PACK / "contracts" / "registry.yml").example("finding")
                finding["status"] = "open"
                control["findings"] = [finding]
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(control)).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        finding_host = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=finding_runner,
        )
        finding_observation = finding_host.inspect("owner/repo", 1)
        self.assertFalse(finding_observation["generation_current"])
        self.assertFalse(finding_observation["findings_closed"])

        def truncated_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "repos/owner/repo/contents/mission.yml?ref=" + "3" * 40]:
                truncated = {
                    "schema_version": 1, "mission_id": "delivery-example",
                    "control_ref": "refs/heads/delivery-control/delivery-example",
                }
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(truncated)).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        truncated_host = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=truncated_runner,
        )
        with self.assertRaisesRegex(ContractError, "mission: missing"):
            truncated_host.inspect("owner/repo", 1)

        def invalid_chronology_runner(command, **kwargs):
            if command[:3] == ["gh", "api", "repos/owner/repo/contents/mission.yml?ref=" + "3" * 40]:
                control = mission()
                control.update({
                    "mission_id": "delivery-example", "control_ref": "refs/heads/delivery-control/delivery-example",
                    "revision": 2, "prior_digest": None,
                })
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(control)).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        invalid_chronology = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=invalid_chronology_runner,
        )
        with self.assertRaisesRegex(ContractError, "prior digest"):
            invalid_chronology.inspect("owner/repo", 1)

        def invalid_chain_runner(command, **kwargs):
            current_ref = "repos/owner/repo/contents/mission.yml?ref=" + "3" * 40
            prior_ref = "repos/owner/repo/contents/mission.yml?ref=" + "4" * 40
            if command[:3] == ["gh", "api", current_ref]:
                control = mission()
                control.update({
                    "mission_id": "delivery-example", "control_ref": "refs/heads/delivery-control/delivery-example",
                    "revision": 2, "prior_digest": sha("wrong-prior"),
                    "controller": {"generation": 7, "workspace_id": "workspace-1", "session_id": "coordinator-1"},
                })
                control["candidate"].update({
                    **self.candidate,
                    "head_sha": self.gate["candidate_head"], "tree_sha": self.gate["candidate_tree"],
                    "builder_session_ids": ["builder-1"], "frozen_at": "2026-08-08T00:00:00Z",
                })
                control["authority"]["envelope_digest"] = digest(self.envelope)
                control["aggregate"].update({"phase": "handback", "status": "running"})
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(control)).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            if command[:3] == ["gh", "api", "repos/owner/repo/git/commits/" + "3" * 40]:
                return subprocess.CompletedProcess(command, 0, json.dumps({"parents": [{"sha": "4" * 40}]}), "")
            if command[:3] == ["gh", "api", prior_ref]:
                body = {"encoding": "base64", "content": base64.b64encode(canonical_bytes(mission())).decode()}
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        invalid_chain = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=invalid_chain_runner,
        )
        with self.assertRaisesRegex(ContractError, "prior chain"):
            invalid_chain.inspect("owner/repo", 1)

        def empty_checks_runner(command, **kwargs):
            if command[:3] == ["gh", "pr", "view"]:
                body = {
                    "state": "OPEN", "isDraft": False, "headRefOid": self.gate["candidate_head"],
                    "baseRefName": "main", "baseRefOid": self.candidate["base_sha"], "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                    "statusCheckRollup": [], "reviewDecision": "", "mergedAt": None,
                    "mergeCommit": None, "url": "https://github.com/owner/repo/pull/1",
                }
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        empty_checks = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=empty_checks_runner,
        )
        empty_clean_observation = empty_checks.inspect("owner/repo", 1)
        self.assertTrue(empty_clean_observation["checks_pass"])
        self.assertTrue(empty_clean_observation["mergeable"])
        empty_clean_decision = self.decision(
            checks_pass=empty_clean_observation["checks_pass"],
            mergeable=empty_clean_observation["mergeable"],
        )
        self.assertEqual("allow", empty_clean_decision["decision"])

        def empty_blocked_runner(command, **kwargs):
            if command[:3] == ["gh", "pr", "view"]:
                body = {
                    "state": "OPEN", "isDraft": False, "headRefOid": self.gate["candidate_head"],
                    "baseRefName": "main", "baseRefOid": self.candidate["base_sha"], "mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED",
                    "statusCheckRollup": [], "reviewDecision": "", "mergedAt": None,
                    "mergeCommit": None, "url": "https://github.com/owner/repo/pull/1",
                }
                return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
            return runner(command, **kwargs)
        empty_blocked = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=empty_blocked_runner,
        )
        empty_blocked_observation = empty_blocked.inspect("owner/repo", 1)
        self.assertTrue(empty_blocked_observation["checks_pass"])
        self.assertFalse(empty_blocked_observation["mergeable"])
        empty_blocked_decision = self.decision(
            checks_pass=empty_blocked_observation["checks_pass"],
            mergeable=empty_blocked_observation["mergeable"],
        )
        self.assertEqual("deny", empty_blocked_decision["decision"])
        self.assertEqual(["mergeable"], empty_blocked_decision["reason_codes"])

        def wrong_tree_runner(command, **kwargs):
            if command[:3] == ["gh", "api", f"repos/owner/repo/git/commits/{self.gate['candidate_head']}"]:
                return subprocess.CompletedProcess(command, 0, json.dumps({"tree": {"sha": "f" * 40}}), "")
            return runner(command, **kwargs)
        wrong_tree = GitHubCliMergeHost(
            merge_method="squash", standing_authority=self.standing_authority,
            expected_controller_generation=7, expected_candidate=self.gate["candidate"],
            expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=wrong_tree_runner,
        )
        wrong_tree_observation = wrong_tree.inspect("owner/repo", 1)
        self.assertEqual("f" * 40, wrong_tree_observation["tree_sha"])
        self.assertFalse(wrong_tree_observation["generation_current"])

        for status, conclusion in (
            ("COMPLETED", "FAILURE"),
            ("COMPLETED", "SKIPPED"),
            ("IN_PROGRESS", None),
        ):
            def non_success_runner(command, **kwargs):
                if command[:3] == ["gh", "pr", "view"]:
                    body = {
                        "state": "OPEN", "isDraft": False, "headRefOid": self.gate["candidate_head"],
                        "baseRefName": "main", "baseRefOid": self.candidate["base_sha"], "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                        "statusCheckRollup": [{"name": "required-ci", "status": status, "conclusion": conclusion}],
                        "reviewDecision": "", "mergedAt": None, "mergeCommit": None,
                        "url": "https://github.com/owner/repo/pull/1",
                    }
                    return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
                return runner(command, **kwargs)
            non_success_host = GitHubCliMergeHost(
                merge_method="squash", standing_authority=self.standing_authority,
                expected_controller_generation=7, expected_candidate=self.gate["candidate"],
                expected_envelope_digest=digest(self.envelope), mission_id="delivery-example", runner=non_success_runner,
            )
            with self.subTest(status=status, conclusion=conclusion):
                self.assertFalse(non_success_host.inspect("owner/repo", 1)["checks_pass"])

    def test_public_decision_command_uses_live_host_observation(self) -> None:
        observed = {
            "repository": "owner/repo", "pr_number": 1, "base_ref": "main",
            "default_branch": "main", "default_branch_policy_digest": digest(self.policy),
            "head_sha": self.gate["candidate_head"], "tree_sha": self.gate["candidate_tree"], "merge_method": "squash",
            "candidate": dict(self.candidate),
            "pr_open": True, "mergeable": True, "checks_pass": True,
            "review_threads_closed": True, "reviews_clear": True,
            "standing_authority_current": True, "default_branch_policy_current": True,
            "kill_switch_enabled": True, "generation_current": True,
            "findings_closed": True, "required_actions_closed": True,
            "changed_paths": ["tests/example.test.ts"], "controller_generation": 7,
            "builder_session_ids": ["builder-1"], "coordinator_session_id": "coordinator-1",
            "control_ref": "refs/heads/delivery-control/delivery-example",
            "control_commit": "3" * 40, "control_digest": sha("control"),
        }

        class LiveHost:
            def __init__(self, **kwargs):
                pass

            def inspect(self, repository, pr_number):
                return dict(observed)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = {
                "envelope": self.envelope, "approval": self.approval, "attempt": self.attempt,
                "gate": self.gate, "handback": self.handback, "launcher": self.launcher,
                "policy": self.policy, "standing": self.standing_authority,
                "facts": {**self.facts, "host": {"base_ref": "release"}, "checks_pass": False},
            }
            paths = {}
            for name, value in values.items():
                paths[name] = root / f"{name}.json"
                paths[name].write_bytes(canonical_bytes(value) + b"\n")
            with patch("delivery_pilot.workflow.GitHubCliMergeHost", LiveHost):
                result = k41_decision_from_files(
                    paths["envelope"], paths["approval"], paths["attempt"], paths["gate"],
                    paths["handback"], paths["launcher"], paths["policy"], paths["standing"],
                    paths["facts"], "2026-08-18T00:00:00Z",
                )
            self.assertEqual("allow", result["outcome"])
            self.assertEqual("main", result["decision"]["base_ref"])

    def test_public_decision_uses_host_paths_and_controller_identity(self) -> None:
        observed = {
            "repository": "owner/repo", "pr_number": 1, "base_ref": "main", "default_branch": "main",
            "default_branch_policy_digest": digest(self.policy), "head_sha": self.gate["candidate_head"],
            "tree_sha": self.gate["candidate_tree"], "merge_method": "squash", "pr_open": True,
            "candidate": dict(self.candidate),
            "mergeable": True, "checks_pass": True, "review_threads_closed": True, "reviews_clear": True,
            "standing_authority_current": True, "default_branch_policy_current": True,
            "kill_switch_enabled": True, "generation_current": True,
            "findings_closed": True, "required_actions_closed": True,
            "changed_paths": [".github/workflows/merge.yml"], "controller_generation": 9,
            "builder_session_ids": ["builder-live"], "coordinator_session_id": "coordinator-live",
            "control_ref": "refs/heads/delivery-control/delivery-example",
            "control_commit": "4" * 40, "control_digest": sha("live-control"),
        }

        class LiveHost:
            def __init__(self, **kwargs):
                pass
            def inspect(self, repository, pr_number):
                return dict(observed)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            values = {
                "envelope": self.envelope, "approval": self.approval, "attempt": self.attempt,
                "gate": self.gate, "handback": self.handback, "launcher": self.launcher,
                "policy": self.policy, "standing": self.standing_authority,
                "facts": {**self.facts, "changed_paths": ["tests/benign.ts"], "builder_session_ids": ["invented"]},
            }
            paths = {}
            for name, value in values.items():
                paths[name] = root / f"{name}.json"
                paths[name].write_bytes(canonical_bytes(value) + b"\n")
            with patch("delivery_pilot.workflow.GitHubCliMergeHost", LiveHost):
                result = k41_decision_from_files(
                    paths["envelope"], paths["approval"], paths["attempt"], paths["gate"],
                    paths["handback"], paths["launcher"], paths["policy"], paths["standing"],
                    paths["facts"], "2026-08-18T00:00:00Z",
                )
        self.assertEqual("deny", result["outcome"])
        self.assertEqual([".github/workflows/merge.yml"], result["decision"]["changed_paths"])
        self.assertEqual(9, result["decision"]["controller_generation"])

    def test_semantic_approval_exact_target_role_and_chronology_fail_closed(self) -> None:
        bad_approval = dict(self.approval, actor_id="not-authorized")
        with self.assertRaisesRegex(ContractError, "approval actor"):
            issue_merge_decision(
                envelope=self.envelope, approval=bad_approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=self.launcher, policy=self.policy,
                standing_authority=self.standing_authority, facts=self.facts, issued_at="2026-08-18T00:00:00Z",
            )
        wrong_target = json.loads(json.dumps(self.envelope))
        wrong_target["authority"]["repository"] = "other/repo"
        rebound = dict(self.approval, envelope_digest=digest(wrong_target))
        with self.assertRaisesRegex(ContractError, "repository mismatch"):
            issue_merge_decision(
                envelope=wrong_target, approval=rebound, attempt=dict(self.attempt, envelope_digest=digest(wrong_target)),
                gate=self.gate, handback=self.handback, launcher=dict(self.launcher, envelope_digest=digest(wrong_target)),
                policy=self.policy, standing_authority=self.standing_authority, facts=self.facts,
                issued_at="2026-08-18T00:00:00Z",
            )
        wrong_role = json.loads(json.dumps(self.launcher))
        wrong_role["requested"]["role"] = wrong_role["runtime"]["role"] = "checker"
        with self.assertRaisesRegex(ContractError, "role must be fresh-merge-agent"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=self.gate,
                handback=self.handback, launcher=wrong_role, policy=self.policy,
                standing_authority=self.standing_authority, facts=self.facts, issued_at="2026-08-18T00:00:00Z",
            )
        late_gate = dict(self.gate, issued_at="2026-08-08T00:07:00Z")
        with self.assertRaisesRegex(ContractError, "chronology"):
            issue_merge_decision(
                envelope=self.envelope, approval=self.approval, attempt=self.attempt, gate=late_gate,
                handback=self.handback, launcher=self.launcher, policy=self.policy,
                standing_authority=self.standing_authority, facts=self.facts, issued_at="2026-08-18T00:00:00Z",
            )


class GenerationTests(unittest.TestCase):
    def test_k41_generated_schemas_split_scope_approval_from_candidate_binding(self) -> None:
        for schema_id, field in (("merge-gate", "candidate"), ("merge-decision", "expected_candidate")):
            schema = json.loads((PACK / f"contracts/generated/schemas/{schema_id}.schema.json").read_text())
            candidate = schema["properties"][field]
            with self.subTest(schema_id=schema_id):
                self.assertEqual(set(CANDIDATE_FIELDS), set(candidate["required"]))
                self.assertFalse(candidate["additionalProperties"])
        decision_schema = json.loads((PACK / "contracts/generated/schemas/merge-decision.schema.json").read_text())
        self.assertFalse(decision_schema["properties"]["risk_policy"]["additionalProperties"])
        self.assertIn("approved_scope", decision_schema["required"])
        envelope_schema = json.loads((PACK / "contracts/generated/schemas/envelope.schema.json").read_text())
        authority = envelope_schema["allOf"][-1]["then"]["properties"]["authority"]
        self.assertNotIn("candidate", authority["required"])
        self.assertTrue({"risk_class", "planning_prefix", "implementation_paths", "candidate_binding", "pr_binding"}.issubset(authority["required"]))
        self.assertEqual(
            {"pr_number", "candidate_head", "candidate_tree", "candidate"},
            {item["required"][0] for item in authority["not"]["anyOf"]},
        )
        handback_schema = json.loads((PACK / "contracts/generated/schemas/handback.schema.json").read_text())
        self.assertEqual(
            "^github:pr/[1-9][0-9]*$",
            handback_schema["allOf"][-1]["then"]["properties"]["pr_ref"]["pattern"],
        )

        receipt = json.loads((PACK / "contracts/generated/schemas/process-attested-merge.schema.json").read_text())
        self.assertNotIn("operation_id", receipt["required"])
        self.assertNotIn("operation_id", receipt["properties"])
        self.assertEqual(["allow"], receipt["properties"]["decision_authorization"]["enum"])
        self.assertTrue(any(
            rule.get("then", {}).get("properties", {}).get("ambiguous_response_observed", {}).get("const") is True
            for rule in receipt["allOf"]
        ))

        standing = json.loads((PACK / "contracts/generated/schemas/k41-standing-authority.schema.json").read_text())
        self.assertEqual(1, standing["properties"]["actor_id"]["minLength"])
        self.assertEqual(1, standing["properties"]["source_event_id"]["minLength"])

    def test_mission_generated_schema_encodes_terminal_state_semantics(self) -> None:
        schema = json.loads((PACK / "contracts/generated/schemas/mission.schema.json").read_text())
        aggregate = schema["properties"]["aggregate"]
        self.assertIn("pr-ready", aggregate["properties"]["phase"]["enum"])
        self.assertIn("cancelled", aggregate["properties"]["status"]["enum"])
        rendered = json.dumps(aggregate["allOf"], sort_keys=True)
        self.assertIn('"const": "complete"', rendered)
        self.assertIn('"const": "cancelled"', rendered)
        self.assertIn('"terminal_outcome"', rendered)
        self.assertIn('"wake_guard"', rendered)

    def test_required_k41_digests_are_non_nullable_in_public_schemas(self) -> None:
        for schema_id, fields in {
            "merge-decision-attestation": ("decision_digest", "readback_digest"),
            "merge-decision": ("policy_digest", "standing_authority_digest", "envelope_digest"),
            "k41-standing-authority": ("implementation_digest", "spec_digest", "policy_digest"),
        }.items():
            schema = json.loads((PACK / f"contracts/generated/schemas/{schema_id}.schema.json").read_text())
            for field in fields:
                with self.subTest(schema=schema_id, field=field):
                    self.assertEqual("string", schema["properties"][field]["type"])

    def test_launcher_v3_generated_schema_carries_exact_policy(self) -> None:
        schema = json.loads((PACK / "contracts/generated/schemas/launcher-v3.schema.json").read_text())
        policy = schema["properties"]["execution_policy"]
        self.assertFalse(policy["additionalProperties"])
        self.assertEqual(
            [["com.apple.FSEvents"]],
            policy["properties"]["macos_mach_lookup_allowlist"]["enum"],
        )
        self.assertEqual(
            "^sha256:[0-9a-f]{64}$",
            policy["properties"]["seatbelt_profile_digest"]["pattern"],
        )

    def test_launcher_v4_generated_schema_carries_exact_checkpoint_policy(self) -> None:
        schema = json.loads((PACK / "contracts/generated/schemas/launcher-v4.schema.json").read_text())
        policy = schema["properties"]["execution_policy"]
        checkpoints = schema["properties"]["provider_checkpoints"]
        checkout = schema["properties"]["checkout"]
        self.assertFalse(policy["additionalProperties"])
        self.assertEqual(["forbidden-except-provider-checkpoints"], policy["properties"]["repository_write_policy"]["enum"])
        self.assertEqual(["conductor-turn-bound"], policy["properties"]["provider_checkpoint_policy"]["enum"])
        self.assertFalse(checkpoints["additionalProperties"])
        self.assertEqual(["checkpointer@noreply"], checkpoints["properties"]["actor_email"]["enum"])
        self.assertEqual("^[A-Za-z0-9_.-]+$", checkpoints["properties"]["turn_id"]["pattern"])
        self.assertEqual("date-time", checkpoints["properties"]["start_created_at"]["format"])
        self.assertEqual("^sha256:[0-9a-f]{64}$", checkout["properties"]["start_index_digest"]["pattern"])
        self.assertEqual("completed", schema["properties"]["termination_state"]["const"])

    def test_checker_lifecycle_generated_schema_carries_completion_controls(self) -> None:
        schema = json.loads((PACK / "contracts/generated/schemas/checker-session-lifecycle.schema.json").read_text())
        properties = schema["properties"]
        self.assertEqual([True], properties["all_required_commands_completed"]["enum"])
        self.assertEqual([True], properties["all_exit_codes_observed"]["enum"])
        self.assertEqual([True], properties["child_processes_reaped"]["enum"])
        self.assertEqual(["checker-session-complete/v1"], properties["completion_marker"]["enum"])
        self.assertEqual(0, properties["command_count"]["exclusiveMinimum"])
        self.assertEqual("date-time", properties["monitor_stopped_at"]["format"])

    def test_generated_contracts_and_manifest_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PACK / "scripts" / "generate.py"), "--check"],
            cwd=PACK.parent,
            text=True,
            capture_output=True,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

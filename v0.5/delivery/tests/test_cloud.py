from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


PACK = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.canonical import digest
from delivery_pilot.cloud import (
    CR_IDS, admission_reuse, candidate_condition_plan, runtime_recovery_decision,
    validate_readiness_profile, validate_readiness_receipt,
)
from delivery_pilot.conductor_api import ConductorApiClient, normalize_api_url, session_completion, validate_runtime_review
from delivery_pilot.workflow import cloud_session_from_file
from delivery_pilot.cloud_runner import CloudReadinessRunner, _environment_presence, _version_ok
import delivery_pilot.cloud_runner as cloud_runner
from delivery_pilot.contracts import ContractError, ContractRegistry


ZERO = "sha256:" + "0" * 64


class CloudFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        for relative in ("scripts/setup.sh", "planning/journeys.yml", "scripts/loss.sh", "scripts/resume.sh", "scripts/cleanup.sh"):
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("#!/bin/sh\nexit 0\n")
        self.registry = ContractRegistry.load(PACK / "contracts" / "registry.yml")
        self.profile = {
            "schema_version": 1, "profile_id": "demo-cloud-v1", "project": "demo",
            "cloud": {
                "build_epoch_name": "PLAYBOOK_CLOUD_BUILD_EPOCH", "expected_build_epoch": "build-1",
                "setup_epoch_name": "PLAYBOOK_CLOUD_SETUP_EPOCH", "expected_setup_epoch": "setup-1",
                "repository_setup_ref": "scripts/setup.sh", "repository_setup_digest": self.sha("scripts/setup.sh"),
                "os_family": "amazon-linux-2023",
                "required_environment": [{"name": "DATABASE_URL", "kind": "secret", "probe": "presence-only"}],
                "tool_probes": [{"name": "node", "command": "node --version", "version": ">=22 <23"}],
            },
            "services": [{"id": "web", "start": "npm start", "restart": "npm start", "stop": "npm stop", "port": 3000, "healthcheck": "http://127.0.0.1:3000/health", "log_paths": [".context/web.log"]}],
            "data": {"migrate": "npm run migrate", "reset": "npm run reset", "seed": "npm run seed", "fixture_digest": ZERO, "test_accounts_ref": "secret-ref:qa-accounts"},
            "verification": {"commands": ["npm test", "npm run build"]},
            "preview": {"review_route": "same-workspace-headless", "health_url": "http://127.0.0.1:3000/health", "human_forward_sandbox_port": 3000},
            "browser_review": {"journeys_ref": "planning/journeys.yml", "journeys_digest": self.sha("planning/journeys.yml"), "evidence": ["assertions", "screenshots", "console", "failed-network", "trace"]},
            "recovery": {"process_loss_probe": "scripts/loss.sh", "process_loss_probe_digest": self.sha("scripts/loss.sh"), "resume": "scripts/resume.sh", "resume_digest": self.sha("scripts/resume.sh")},
            "cleanup": "scripts/cleanup.sh", "cleanup_digest": self.sha("scripts/cleanup.sh"), "local_only_dependencies": [],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def sha(self, relative: str) -> str:
        import hashlib
        return "sha256:" + hashlib.sha256((self.project / relative).read_bytes()).hexdigest()

    def receipt(self, mode: str = "admission") -> dict:
        locators = [f"artifact:cloud/{item}" for item in CR_IDS]
        result = {
            "schema_version": 1, "readiness_id": "ready-1", "mode": mode,
            "profile_id": self.profile["profile_id"], "profile_digest": digest(self.profile),
            "observed_build_epoch": "build-1", "observed_setup_epoch": "setup-1", "repository": "owner/demo",
            "base_sha": "base", "head_sha": "head", "tree_sha": "tree", "dependency_lock_digest": ZERO,
            "bound_digests": {"setup": self.profile["cloud"]["repository_setup_digest"]},
            "environment_presence": {"DATABASE_URL": True}, "fingerprints": {"node": "22.1.0", "lock": ZERO},
            "conditions": {item: {"outcome": "pass", "evidence_locators": [locators[index]]} for index, item in enumerate(CR_IDS)},
            "raw_evidence_locators": locators, "review_route": "same-workspace-headless",
            "started_at": "2026-08-12T00:00:00Z", "ended_at": "2026-08-12T00:10:00Z", "expires_at": "2026-09-11T00:10:00Z",
            "issuer": "process-attested:conductor:workspace-1",
        }
        if mode == "candidate":
            result["candidate"] = {"head_sha": "head", "tree_sha": "tree"}
        return result


class ProfileTests(CloudFixture):
    def test_cr1_validates_exact_profile_and_references(self):
        self.assertEqual(validate_readiness_profile(self.profile, self.project, self.registry, digest(self.profile)), digest(self.profile))

    def test_profile_digest_mismatch_blocks(self):
        with self.assertRaisesRegex(ContractError, "does not match"):
            validate_readiness_profile(self.profile, self.project, self.registry, ZERO)

    def test_profile_rejects_secret_value(self):
        self.profile["cloud"]["required_environment"][0]["value"] = "secret"
        with self.assertRaisesRegex(ContractError, "secret-bearing"):
            validate_readiness_profile(self.profile, self.project, self.registry)

    def test_profile_rejects_changed_bound_file(self):
        (self.project / "scripts/setup.sh").write_text("changed\n")
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            validate_readiness_profile(self.profile, self.project, self.registry)

    def test_profile_rejects_human_only_or_incomplete_browser_evidence(self):
        self.profile["preview"]["review_route"] = "human-forward-only"
        self.profile["browser_review"]["evidence"] = ["screenshots"]
        with self.assertRaises(ContractError):
            validate_readiness_profile(self.profile, self.project, self.registry)


class ReceiptTests(CloudFixture):
    def test_admission_cr1_to_cr10_pass(self):
        validate_readiness_receipt(self.receipt(), self.profile, self.registry)

    def test_candidate_binds_exact_tuple_and_selected_conditions(self):
        receipt = self.receipt("candidate")
        validate_readiness_receipt(receipt, self.profile, self.registry, expected_candidate=receipt["candidate"], required_conditions={"CR5", "CR6", "CR7", "CR8", "CR9"})

    def test_failed_required_condition_blocks(self):
        receipt = self.receipt()
        receipt["conditions"]["CR7"]["outcome"] = "fail"
        with self.assertRaisesRegex(ContractError, "CR7"):
            validate_readiness_receipt(receipt, self.profile, self.registry)

    def test_missing_raw_evidence_blocks(self):
        receipt = self.receipt()
        receipt["raw_evidence_locators"].remove("artifact:cloud/CR9")
        with self.assertRaisesRegex(ContractError, "not retained"):
            validate_readiness_receipt(receipt, self.profile, self.registry)

    def test_epoch_and_candidate_mismatch_block(self):
        receipt = self.receipt("candidate")
        receipt["observed_setup_epoch"] = "old"
        with self.assertRaisesRegex(ContractError, "epoch"):
            validate_readiness_receipt(receipt, self.profile, self.registry, expected_candidate=receipt["candidate"], required_conditions={"CR5"})

    def test_tier_b_rejects_process_attestation(self):
        with self.assertRaisesRegex(ContractError, "protected"):
            validate_readiness_receipt(self.receipt(), self.profile, self.registry, tier="B")

    def test_ttl_longer_than_thirty_days_blocks(self):
        receipt = self.receipt()
        receipt["expires_at"] = "2026-09-12T00:11:00Z"
        with self.assertRaisesRegex(ContractError, "TTL"):
            validate_readiness_receipt(receipt, self.profile, self.registry)

    def test_environment_values_are_never_allowed(self):
        receipt = self.receipt()
        receipt["environment_presence"]["DATABASE_URL"] = "postgres://secret"
        with self.assertRaisesRegex(ContractError, "presence booleans"):
            validate_readiness_receipt(receipt, self.profile, self.registry)

    def test_admission_reuse_requires_epochs_profile_env_and_ttl(self):
        receipt = self.receipt()
        current, _ = admission_reuse(receipt, self.profile, now=datetime(2026, 8, 13, tzinfo=timezone.utc), observed_environment_names={"DATABASE_URL"})
        self.assertTrue(current)
        receipt["observed_build_epoch"] = ""
        current, reason = admission_reuse(receipt, self.profile, now=datetime(2026, 8, 13, tzinfo=timezone.utc), observed_environment_names={"DATABASE_URL"})
        self.assertFalse(current)
        self.assertIn("unobservable", reason)

    def test_candidate_invalidation_matrix_unions_conditions(self):
        result = candidate_condition_plan({"dependency_lock", "service_configuration", "cleanup_executable"}, True, True)
        self.assertEqual(result["required"], ["CR10", "CR3", "CR4", "CR5", "CR6", "CR7", "CR8", "CR9"])


class ApiTests(unittest.TestCase):
    def test_url_normalization_avoids_double_v0(self):
        self.assertEqual(normalize_api_url("https://api.example.test"), ("https://api.example.test", "https://api.example.test/v0"))
        self.assertEqual(normalize_api_url("https://api.example.test/v0"), ("https://api.example.test", "https://api.example.test/v0"))
        with self.assertRaises(ContractError):
            normalize_api_url("https://api.example.test/v0/v0")

    def test_credential_precedence(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            if url.endswith("/me"):
                return 200, {"userId": "u1", "authMethod": "api-key", "workspaceId": "w1"}
            return 200, {"openapi": "3.0.3", "info": {"version": "0.0.1"}}
        old = dict(os.environ)
        try:
            os.environ.update({"CONDUCTOR_API_URL": "https://api.example.test", "CONDUCTOR_API_KEY": "preferred", "CONDUCTOR_API_TOKEN": "fallback", "CONDUCTOR_SESSION_ID": "s0"})
            result = ConductorApiClient.from_environment(transport).capability_preflight()
        finally:
            os.environ.clear(); os.environ.update(old)
        self.assertEqual(result["credential_scope"], "workspace")
        self.assertTrue(all(item[2]["Authorization"] == "Bearer preferred" for item in calls))
        self.assertTrue(all(item[2]["X-Conductor-Session-Id"] == "s0" for item in calls))

    def test_ambiguous_send_recovers_transcript_id_but_preserves_logical_id(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if method == "POST":
                return 503, {"error": "ambiguous"}
            if url.endswith("/status"):
                return 200, {"workspaceId": "workspace-1", "sessionId": "session-1", "status": "idle"}
            return 200, {"data": [{
                "id": "transcript-1", "sessionId": "session-1", "type": "userMessage",
                "content": {"id": "message-1", "message": "brief", "state": "sent"},
            }], "hasMore": False}
        client = ConductorApiClient("https://api.example.test/v0", "credential", transport=transport)
        result = client.send_message("session-1", "brief", "message-1")
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["logicalMessageId"], "message-1")
        self.assertEqual(result["transcriptId"], "transcript-1")
        self.assertEqual(result["id"], "transcript-1")
        self.assertEqual(sum(method == "POST" for method, _, _ in calls), 1)
        self.assertIn("https://api.example.test/v0/sessions/session-1/messages?limit=100", [url for _, url, _ in calls])

    def test_ambiguous_send_rejects_wrong_session_payload_and_pagination_cycles(self):
        cases = {
            "wrong-session": [{"id": "t1", "sessionId": "other", "type": "userMessage", "content": {"id": "m1", "message": "brief"}}],
            "wrong-payload": [{"id": "t1", "sessionId": "s1", "type": "userMessage", "content": {"id": "m1", "message": "other"}}],
            "wrong-record-type": [{"id": "t1", "sessionId": "s1", "type": "agent", "content": {"id": "m1", "message": "brief"}}],
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                calls = []
                def transport(method, url, headers, body):
                    calls.append((method, url))
                    if method == "POST": return 503, {}
                    if url.endswith("/status"): return 200, {"sessionId": "s1", "status": "idle"}
                    return 200, {"data": data, "hasMore": False}
                with self.assertRaises(ContractError):
                    ConductorApiClient("https://api.example.test", "credential", transport=transport).send_message("s1", "brief", "m1")
                self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

        calls = []
        def cyclic_transport(method, url, headers, body):
            calls.append((method, url))
            if method == "POST": return 503, {}
            if url.endswith("/status"): return 200, {"sessionId": "s1", "status": "idle"}
            return 200, {"data": [{"id": "same"}], "hasMore": True}
        with self.assertRaisesRegex(ContractError, "cycle"):
            ConductorApiClient("https://api.example.test", "credential", transport=cyclic_transport).send_message("s1", "brief", "m1")
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

    def test_ambiguous_launch_reconciles_only_exact_workspace_route_and_prompt(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if method == "POST": return 503, {}
            if url.startswith("https://api.example.test/v0/workspaces/workspace-1/sessions"):
                return 200, {"data": [{
                    "id": "session-1", "name": "checker", "model": "gpt-5.6-terra",
                    "resolvedModel": "gpt-5.6-terra", "effort": "high", "fastMode": False,
                }], "hasMore": False}
            if url.endswith("/status"): return 200, {"sessionId": "session-1", "status": "idle"}
            if url.startswith("https://api.example.test/v0/sessions/session-1/messages"):
                return 200, {"data": [{
                    "id": "transcript-1", "sessionId": "session-1", "type": "userMessage",
                    "content": {"id": "logical-1", "message": "check", "state": "sent"},
                }], "hasMore": False}
            raise AssertionError(url)
        result = ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
            "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
        )
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["id"], "session-1")
        self.assertEqual(result["initialMessage"]["messageId"], "logical-1")
        self.assertEqual(result["initialMessage"]["transcriptId"], "transcript-1")
        self.assertEqual(sum(method == "POST" for method, _, _ in calls), 1)

    def test_ambiguous_launch_selects_exact_message_candidate_before_validating_its_route(self):
        """Unrelated workspace sessions cannot preempt an exact recovered launch."""

        calls = []
        sessions = [
            {"id": "unrelated-before", "workspaceId": "workspace-1", "agent": "claude",
             "model": "claude-other", "effort": "high"},
            {"id": "candidate", "workspaceId": "workspace-1", "agent": "codex",
             "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"},
            {"id": "unrelated-after", "workspaceId": "workspace-1", "agent": "codex",
             "model": "gpt-6-astra", "effort": "high"},
        ]

        def transport(method, url, headers, body):
            calls.append((method, url, body))
            if method == "POST":
                return 503, {"error": "ambiguous"}
            if "/workspaces/workspace-1/sessions" in url:
                return 200, {"data": sessions, "hasMore": False}
            session_id = url.split("/sessions/")[1].split("/")[0]
            if session_id == "candidate":
                record = {"id": "transcript-candidate", "sessionId": "candidate", "type": "userMessage",
                          "content": {"id": "logical-1", "message": "check", "state": "sent"}}
            else:
                record = {"id": f"transcript-{session_id}", "sessionId": session_id, "type": "userMessage",
                          "content": {"id": f"unrelated-{session_id}", "message": "other"}}
            return 200, {"data": [record], "hasMore": False}

        result = ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
            "workspace-1", "check", "codex", "gpt-5.6-sol", "medium", "logical-1",
        )
        self.assertTrue(result["reconciled"])
        self.assertEqual(result["id"], "candidate")
        self.assertEqual(sum(method == "POST" for method, _, _ in calls), 1)

    def test_ambiguous_launch_refuses_listed_workspace_mismatch_before_transcript_access(self):
        calls = []
        sessions = [
            {"id": "foreign", "workspaceId": "outside", "agent": "claude",
             "model": "claude-sonnet", "effort": "medium"},
            {"id": "candidate", "workspaceId": "wanted", "agent": "codex",
             "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"},
        ]

        def transport(method, url, headers, body):
            calls.append((method, url))
            if method == "POST":
                return 503, {"error": "ambiguous"}
            if "/workspaces/wanted/sessions" in url:
                return 200, {"data": sessions, "hasMore": False}
            session_id = url.split("/sessions/")[1].split("/")[0]
            if session_id == "foreign":
                return 200, {"data": [], "hasMore": False}
            return 200, {"data": [{
                "id": "transcript-candidate", "sessionId": "candidate", "type": "userMessage",
                "content": {"id": "logical-1", "message": "check"},
            }], "hasMore": False}

        with self.assertRaisesRegex(ContractError, "workspace mismatch"):
            ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
                "wanted", "check", "codex", "gpt-5.6-sol", "medium", "logical-1",
            )
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
        self.assertFalse(any("/sessions/foreign/messages" in url for _, url in calls))

    def test_ambiguous_launch_refuses_conflicting_candidates_and_malformed_unmatched_records(self):
        cases = {
            "conflicting": [
                {"id": "candidate-a", "workspaceId": "workspace-1", "agent": "codex",
                 "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"},
                {"id": "candidate-b", "workspaceId": "workspace-1", "agent": "codex",
                 "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"},
            ],
            "malformed-unmatched": [
                {"id": "unrelated", "workspaceId": "workspace-1", "agent": [],
                 "model": "claude-other", "effort": "high"},
                {"id": "candidate", "workspaceId": "workspace-1", "agent": "codex",
                 "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"},
            ],
        }
        for name, sessions in cases.items():
            with self.subTest(name=name):
                calls = []

                def transport(method, url, headers, body):
                    calls.append((method, url))
                    if method == "POST":
                        return 503, {"error": "ambiguous"}
                    if "/workspaces/workspace-1/sessions" in url:
                        return 200, {"data": sessions, "hasMore": False}
                    session_id = url.split("/sessions/")[1].split("/")[0]
                    return 200, {"data": [{
                        "id": f"transcript-{session_id}", "sessionId": session_id, "type": "userMessage",
                        "content": {"id": "logical-1", "message": "check"},
                    }], "hasMore": False}

                expected = "conflicting" if name == "conflicting" else "malformed"
                with self.assertRaisesRegex(ContractError, expected):
                    ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
                        "workspace-1", "check", "codex", "gpt-5.6-sol", "medium", "logical-1",
                    )
                self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

    def test_ambiguous_launch_exhausts_the_shared_session_message_read_budget(self):
        calls = []
        sessions = [
            {"id": f"session-{index}", "workspaceId": "workspace-1", "agent": "codex",
             "model": "gpt-5.6-sol", "resolvedModel": "gpt-5.6-sol", "effort": "medium"}
            for index in range(10)
        ]

        def transport(method, url, headers, body):
            calls.append((method, url))
            if method == "POST":
                return 503, {"error": "ambiguous"}
            if "/workspaces/workspace-1/sessions" in url:
                return 200, {"data": sessions, "hasMore": False}
            session_id = url.split("/sessions/")[1].split("/")[0]
            return 200, {"data": [{
                "id": f"transcript-{session_id}", "sessionId": session_id, "type": "userMessage",
                "content": {"id": f"other-{session_id}", "message": "other"},
            }], "hasMore": False}

        with self.assertRaisesRegex(ContractError, "combined read bound"):
            ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
                "workspace-1", "check", "codex", "gpt-5.6-sol", "medium", "logical-1",
            )
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)
        self.assertEqual(sum(method == "GET" for method, _ in calls), 10)

    def test_ambiguous_launch_refuses_route_mismatch_and_exhausted_pagination(self):
        calls = []
        def wrong_route(method, url, headers, body):
            calls.append((method, url))
            if method == "POST": return 503, {}
            if "/workspaces/workspace-1/sessions" in url:
                return 200, {"data": [{
                    "id": "session-1", "model": "gpt-5.6-terra", "resolvedModel": "wrong-model", "effort": "high",
                }], "hasMore": False}
            if "/sessions/session-1/messages" in url:
                return 200, {"data": [{
                    "id": "transcript-1", "sessionId": "session-1", "type": "userMessage",
                    "content": {"id": "logical-1", "message": "check"},
                }], "hasMore": False}
            return 200, {"sessionId": "session-1", "status": "idle"}
        with self.assertRaisesRegex(ContractError, "route mismatch"):
            ConductorApiClient("https://api.example.test", "credential", transport=wrong_route).launch_checker(
                "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
            )
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

        page_calls = 0
        def endless_pages(method, url, headers, body):
            nonlocal page_calls
            if method == "POST": return 503, {}
            page_calls += 1
            return 200, {"data": [{"id": f"cursor-{page_calls}"}], "hasMore": True}
        with self.assertRaisesRegex(ContractError, "exhausted"):
            ConductorApiClient("https://api.example.test", "credential", transport=endless_pages).launch_checker(
                "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
            )

    def test_ambiguous_launch_refuses_observable_agent_or_workspace_contradictions(self):
        for name, extra in {
            "agent": {"agent": "claude"},
            "workspace": {"workspaceId": "other-workspace", "agent": "codex"},
            "malformed-agent": {"agent": []},
            "malformed-workspace": {"workspaceId": []},
        }.items():
            with self.subTest(name=name):
                calls = []

                def transport(method, url, headers, body):
                    calls.append((method, url))
                    if method == "POST":
                        return 503, {}
                    if "/workspaces/workspace-1/sessions" in url:
                        return 200, {"data": [{
                            "id": "session-1", "model": "gpt-5.6-terra",
                            "resolvedModel": "gpt-5.6-terra", "effort": "high", **extra,
                        }], "hasMore": False}
                    if "/sessions/session-1/messages" in url:
                        return 200, {"data": [{
                            "id": "transcript-1", "sessionId": "session-1", "type": "userMessage",
                            "content": {"id": "logical-1", "message": "check"},
                        }], "hasMore": False}
                    raise AssertionError(url)

                with self.assertRaisesRegex(ContractError, "mismatch|malformed"):
                    ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
                        "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
                    )
                self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

    def test_successful_launch_requires_a_session_id_and_rejects_supplied_identity_mismatches(self):
        cases = {
            "missing-session": {},
            "empty-session": {"id": ""},
            "list-session": {"id": []},
            "wrong-workspace": {"id": "session-1", "workspaceId": "other"},
            "list-workspace": {"id": "session-1", "workspaceId": []},
            "null-workspace": {"id": "session-1", "workspaceId": None},
            "wrong-agent": {"id": "session-1", "agent": "claude"},
            "list-agent": {"id": "session-1", "agent": []},
            "null-agent": {"id": "session-1", "agent": None},
            "wrong-model": {"id": "session-1", "model": "gpt-6-astra"},
            "conflicting-models": {"id": "session-1", "model": "gpt-5.6-terra", "resolvedModel": "gpt-6-astra"},
            "list-model": {"id": "session-1", "model": []},
            "null-model": {"id": "session-1", "model": None},
            "wrong-effort": {"id": "session-1", "effort": "low"},
            "list-effort": {"id": "session-1", "effort": []},
            "null-effort": {"id": "session-1", "effort": None},
        }
        for name, response in cases.items():
            with self.subTest(name=name):
                calls = []

                def transport(method, url, headers, body):
                    calls.append((method, url, body))
                    return 200, response

                with self.assertRaises(ContractError):
                    ConductorApiClient("https://api.example.test", "credential", transport=transport).launch_checker(
                        "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
                    )
                self.assertEqual(sum(method == "POST" for method, _, _ in calls), 1)

        def compatible_transport(method, url, headers, body):
            return 200, {"id": "session-1"}

        receipt = ConductorApiClient("https://api.example.test", "credential", transport=compatible_transport).launch_checker(
            "workspace-1", "check", "codex", "gpt-5.6-terra", "high", "logical-1",
        )
        self.assertEqual(receipt["id"], "session-1")

    def test_sleep_archived_is_not_success(self):
        def transport(method, url, headers, body): return 200, {"workspaceId": "w1", "status": "archived"}
        with self.assertRaisesRegex(ContractError, "archived"):
            ConductorApiClient("https://api.example.test", "credential", transport=transport).sleep_workspace("w1")

    def test_client_error_does_not_trigger_ambiguous_reconciliation(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append((method, url))
            return 400, {"error": "bad request"}
        with self.assertRaisesRegex(ContractError, "HTTP 400"):
            ConductorApiClient("https://api.example.test", "credential", transport=transport).send_message("s1", "brief", "m1")
        self.assertEqual(len(calls), 1)

    def test_message_pagination_uses_after_cursor(self):
        calls = []
        def transport(method, url, headers, body):
            calls.append(url)
            if url.endswith("/status"):
                return 200, {"workspaceId": "w1", "sessionId": "s1", "status": "idle", "updatedAt": "now"}
            if "after=m1" in url:
                return 200, {"data": [{"id": "m2"}], "offset": 0, "hasMore": False}
            return 200, {"data": [{"id": "m1"}], "offset": 0, "hasMore": True}
        result = ConductorApiClient("https://api.example.test", "credential", transport=transport).observe_session("s1")
        self.assertEqual([item["id"] for item in result["messages"]["data"]], ["m1", "m2"])

    def test_message_pagination_rejects_empty_progress_and_cursor_cycles(self):
        def empty_transport(method, url, headers, body):
            return 200, {"data": [], "hasMore": True}
        with self.assertRaisesRegex(ContractError, "no progress"):
            ConductorApiClient("https://api.example.test", "credential", transport=empty_transport).observe_session("s1")

        def cyclic_transport(method, url, headers, body):
            return 200, {"data": [{"id": "m1"}], "hasMore": True}
        with self.assertRaisesRegex(ContractError, "cycle"):
            ConductorApiClient("https://api.example.test", "credential", transport=cyclic_transport).observe_session("s1")

    def test_runtime_review_binds_workspace_session_and_route(self):
        result = validate_runtime_review(
            {"workspaceId": "w1", "status": "ready"},
            {"id": "s1", "agent": "codex", "model": "gpt-5.6-sol", "effort": "high"},
            workspace_id="w1", session_id="s1", agent="codex", model="gpt-5.6-sol", effort="high",
        )
        self.assertEqual(result["outcome"], "pass")
        with self.assertRaises(ContractError):
            validate_runtime_review({"workspaceId": "w2", "status": "ready"}, {"id": "s1", "model": "gpt-5.6-sol", "effort": "high"}, workspace_id="w1", session_id="s1", agent="codex", model="gpt-5.6-sol", effort="high")

    def test_error_is_adapter_failure_and_initial_idle_is_not_completion(self):
        self.assertEqual(session_completion(["idle"], []), "pending")
        self.assertEqual(session_completion(["working", "idle"], []), "pending")
        self.assertEqual(
            session_completion(
                ["working", "idle"],
                [{"type": "assistant", "content": "checker-session-complete/v1"}],
            ),
            "complete",
        )
        self.assertEqual(
            session_completion(
                ["working", "idle"],
                [
                    {"type": "assistant", "content": "checker-session-complete/v1"},
                    {"type": "user", "content": "follow-up"},
                ],
            ),
            "pending",
        )
        self.assertEqual(
            session_completion(
                ["working", "idle"],
                [
                    {"type": "assistant", "content": "checker-session-complete/v1"},
                    {"type": "userMessage", "content": {"id": "new", "turnId": "new", "message": "follow-up"}},
                ],
            ),
            "pending",
        )
        for empty_content in ("", "   "):
            with self.subTest(content=empty_content):
                self.assertEqual(
                    session_completion(
                        ["working", "idle"],
                        [{"type": "assistant", "content": empty_content}],
                    ),
                    "pending",
                )
        for malformed_content in (None, [], {}, 1):
            with self.subTest(content=malformed_content):
                with self.assertRaisesRegex(ContractError, "normalized assistant content"):
                    session_completion(
                        ["working", "idle"],
                        [{"type": "assistant", "content": malformed_content}],
                    )
        with self.assertRaisesRegex(ContractError, "error"):
            session_completion(["working", "error"], [])

    def test_raw_completion_requires_current_reply_and_completed_turn(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        started_turn = {"type": "agent", "content": {"rawPayload": {
            "thread_id": "thread-current", "event": {"type": "turn.started"},
        }}}
        raw_reply = {"type": "agent", "content": {"rawPayload": {"event": {
            "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"},
        }, "thread_id": "thread-current"}}}
        completed_turn = {"type": "agent", "content": {"rawPayload": {
            "event": {"type": "turn.completed"}, "thread_id": "thread-current",
        }}}
        self.assertEqual(session_completion(["working", "idle"], [current, started_turn, raw_reply, completed_turn]), "complete")
        cancelled_command = {"type": "agent", "content": {"rawPayload": {"event": {
            "type": "item.started", "item": {"type": "commandExecution", "command": "sleep 45"},
        }}}}
        self.assertEqual(session_completion(["working", "idle"], [current, cancelled_command]), "pending")
        old_reply = {"type": "agent", "content": {"rawPayload": {"event": {
            "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "old"},
        }, "thread_id": "old"}}}
        old_started = {"type": "agent", "content": {"rawPayload": {"event": {"type": "turn.started"}, "thread_id": "old"}}}
        old_turn = {"type": "agent", "content": {"rawPayload": {"event": {"type": "turn.completed"}, "thread_id": "old"}}}
        newer = {"type": "userMessage", "content": {"id": "logical-new", "turnId": "logical-new", "message": "new"}}
        self.assertEqual(session_completion(["working", "idle"], [old_started, old_reply, old_turn, newer]), "pending")
        wrong_thread_turn = {"type": "agent", "content": {"rawPayload": {"event": {
            "type": "turn.completed",
        }, "thread_id": "other-thread"}}}
        self.assertEqual(session_completion(["working", "idle"], [current, started_turn, raw_reply, wrong_thread_turn]), "pending")
        contradictory_turn = {"type": "agent", "content": {"rawPayload": {"event": {
            "type": "turn.completed", "turnId": "other-turn",
        }, "thread_id": "thread-current"}}}
        self.assertEqual(session_completion(["working", "idle"], [current, started_turn, raw_reply, contradictory_turn]), "pending")

    def test_raw_completion_refuses_later_turn_cancellation_or_user_boundary(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.started"}}}}
        reply = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"},
        }}}}
        completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.completed"}}}}
        cancelled = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.cancelled"}}}}
        another_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.started"}}}}
        newer_user = {"type": "userMessage", "content": "new task"}
        cases = {
            "later-turn": [current, started, reply, completed, another_started],
            "later-cancellation": [current, started, reply, completed, cancelled],
            "newer-user": [current, started, reply, completed, newer_user],
            "cancellation-before-terminal": [current, started, reply, cancelled, completed],
        }
        for name, messages in cases.items():
            with self.subTest(name=name):
                self.assertEqual(session_completion(["working", "idle"], messages), "pending")

    def test_raw_completion_allows_no_extra_failure_or_tool_event(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.started"}}}}
        reply = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"},
        }}}}
        completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.completed"}}}}
        failed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.failed"}}}}
        error = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "error"}}}}
        command_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.started", "item": {"type": "commandExecution", "command": "sleep 45"},
        }}}}
        cases = {
            "later-turn-failed": [current, started, reply, completed, failed],
            "later-error": [current, started, reply, completed, error],
            "later-command-start": [current, started, reply, completed, command_started],
            "error-before-terminal": [current, started, reply, error, completed],
        }
        for name, messages in cases.items():
            with self.subTest(name=name):
                self.assertEqual(session_completion(["working", "idle"], messages), "pending")

    def test_raw_completion_accepts_retained_final_message_lifecycle(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.started"}}}}
        tool_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.started", "item": {"type": "commandExecution", "id": "tool-1"},
        }}}}
        tool_completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.completed", "item": {"type": "commandExecution", "id": "tool-1"},
        }}}}
        final_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.started", "item": {"type": "agentMessage", "id": "message-1", "phase": "final_answer", "text": ""},
        }}}}
        final_completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.completed", "item": {"type": "agentMessage", "id": "message-1", "phase": "final_answer", "text": "done"},
        }}}}
        completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.completed"}}}}
        self.assertEqual(session_completion(["working", "idle"], [current, started, tool_started, tool_completed, final_started, final_completed, completed]), "complete")

    def test_raw_completion_accepts_same_thread_started_preamble(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        thread_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "thread.started"}}}}
        started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.started"}}}}
        reply = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {
            "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"},
        }}}}
        completed = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.completed"}}}}
        self.assertEqual(session_completion(["working", "idle"], [current, thread_started, started, reply, completed]), "complete")

    def test_raw_completion_refuses_mismatched_or_cancelled_thread_started_preamble(self):
        current = {"type": "userMessage", "content": {"id": "logical-current", "turnId": "logical-current", "message": "check"}}
        thread_started = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "thread.started"}}}}
        wrong_thread_turn = {"type": "agent", "content": {"rawPayload": {"thread_id": "other-thread", "event": {"type": "turn.started"}}}}
        cancelled = {"type": "agent", "content": {"rawPayload": {"thread_id": "thread", "event": {"type": "turn.cancelled"}}}}
        for name, messages in {
            "wrong-thread": [current, thread_started, wrong_thread_turn],
            "cancelled": [current, thread_started, cancelled],
        }.items():
            with self.subTest(name=name):
                self.assertEqual(session_completion(["working", "idle"], messages), "pending")

    def test_cli_reports_first_turn_complete_and_malformed_facts_as_contract_errors(self):
        first_turn = {
            "status_history": ["working", "idle"],
            "messages": [
                {"type": "userMessage", "content": {"id": "logical-1", "turnId": "logical-1", "message": "check"}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "thread.started"}}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.started"}}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {
                    "type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"},
                }}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.completed"}}}},
            ],
        }
        malformed = {
            "root": [],
            "status-list": {"status_history": "idle", "messages": []},
            "status-entry": {"status_history": ["working", None], "messages": []},
            "message-list": {"status_history": ["working", "idle"], "messages": {}},
            "message-entry": {"status_history": ["working", "idle"], "messages": [None]},
            "message-kind-list": {"status_history": ["working", "idle"], "messages": [{"type": []}]},
            "message-kind-object": {"status_history": ["working", "idle"], "messages": [{"type": {}}]},
            "message-kind-empty": {"status_history": ["working", "idle"], "messages": [{"type": ""}]},
            "raw-item-kind-list": {
                "status_history": ["working", "idle"],
                "messages": [
                    {"type": "userMessage", "content": {"id": "logical-1", "turnId": "logical-1", "message": "check"}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.started"}}}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "item.completed", "item": {"type": []}}}}},
                ],
            },
            "user-content-null": {"status_history": ["working", "idle"], "messages": [{"type": "userMessage", "content": None}]},
            "user-content-list": {"status_history": ["working", "idle"], "messages": [{"type": "userMessage", "content": []}]},
            "user-turn-scalar": {"status_history": ["working", "idle"], "messages": [{"type": "userMessage", "content": {"id": "logical-1", "turnId": 123}}]},
            "user-turn-alias-conflict": {"status_history": ["working", "idle"], "messages": [{"type": "userMessage", "content": {"id": "logical-1", "turnId": "turn-1", "turn_id": "turn-2"}}]},
            "agent-content-list": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": []}]},
            "agent-content-scalar": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": 1}]},
            "raw-payload-null": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": None}}]},
            "raw-payload-scalar": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": "bad"}}]},
            "raw-event-list": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": {"event": []}}}]},
            "raw-item-null": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": {"event": {"type": "item.completed", "item": None}}}}]},
            "raw-item-scalar": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": {"event": {"type": "item.completed", "item": "bad"}}}}]},
            "raw-item-list": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": {"event": {"type": "item.completed", "item": []}}}}]},
            "wrapper-thread-alias-conflict": {"status_history": ["working", "idle"], "messages": [{"type": "agent", "content": {"rawPayload": {"threadId": "thread-1", "thread_id": "thread-2", "event": {"type": "turn.started"}}}}]},
            "event-turn-alias-conflict": {
                "status_history": ["working", "idle"],
                "messages": [
                    {"type": "userMessage", "content": {"id": "logical-1", "turnId": "logical-1"}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.started"}}}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"}}}}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.completed", "turnId": "logical-1", "turn_id": "other"}}}},
                ],
            },
            "item-event-turn-conflict": {
                "status_history": ["working", "idle"],
                "messages": [
                    {"type": "userMessage", "content": {"id": "logical-1", "turnId": "logical-1"}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.started"}}}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "item.completed", "turnId": "logical-1", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done", "turn_id": "other"}}}}},
                    {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.completed"}}}},
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            facts = Path(temporary) / "facts.json"

            def run(value):
                facts.write_text(json.dumps(value))
                return subprocess.run(
                    [sys.executable, "-B", str(PACK / "skill/scripts/deliver.py"), "cloud-session-evaluate", "--facts", str(facts)],
                    cwd=PACK.parents[1], env={"PYTHONPATH": str(PACK / "src")}, text=True, capture_output=True, check=False,
                )

            result = run(first_turn)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["outcome"], "complete")
            for name, value in malformed.items():
                with self.subTest(name=name):
                    result = run(value)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["outcome"], "blocked")
                    self.assertEqual(payload["error_class"], "ContractError")

    def test_well_formed_incomplete_raw_evidence_stays_pending(self):
        cases = [
            {"type": "agent", "content": {}},
            {"type": "agent", "content": {"rawPayload": {}}},
            {"type": "agent", "content": {"rawPayload": {"event": {}}}},
        ]
        for message in cases:
            with self.subTest(message=message):
                self.assertEqual(session_completion(["working", "idle"], [message]), "pending")

    def test_cli_refuses_current_content_identities_that_conflict_with_raw_evidence(self):
        first_turn = {
            "status_history": ["working", "idle"],
            "messages": [
                {"type": "userMessage", "content": {"id": "logical-1", "turnId": "logical-1", "message": "check"}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "thread.started"}}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.started"}}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "done"}}}}},
                {"type": "agent", "content": {"rawPayload": {"thread_id": "thread-1", "event": {"type": "turn.completed"}}}},
            ],
        }
        cases = {
            "user-thread": (0, "threadId"),
            "agent-wrapper-thread": (1, "threadId"),
            "agent-wrapper-turn": (1, "turnId"),
        }
        with tempfile.TemporaryDirectory() as temporary:
            facts = Path(temporary) / "facts.json"
            for name, (index, field) in cases.items():
                with self.subTest(name=name):
                    value = json.loads(json.dumps(first_turn))
                    value["messages"][index]["content"][field] = "contradictory"
                    facts.write_text(json.dumps(value))
                    result = subprocess.run(
                        [sys.executable, "-B", str(PACK / "skill/scripts/deliver.py"), "cloud-session-evaluate", "--facts", str(facts)],
                        cwd=PACK.parents[1], env={"PYTHONPATH": str(PACK / "src")}, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 2, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["outcome"], "blocked")
                    self.assertEqual(payload["error_class"], "ContractError")

    def test_cli_boundary_does_not_report_cancelled_command_as_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            facts = Path(temporary) / "facts.json"
            facts.write_text('{"status_history":["working","idle"],"messages":[{"type":"agent","content":{"rawPayload":{"event":{"type":"item.started","item":{"type":"commandExecution"}}}}}]}')
            result = cloud_session_from_file(facts)
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["required_actions"], ["continue observing with the after-message cursor"])


class RuntimeTests(unittest.TestCase):
    def test_healthy_runtime_reestablishes_cr7_cr8(self):
        self.assertEqual(runtime_recovery_decision(health="healthy", resume_exit=None, post_resume_health=None)["required"], ["CR7", "CR8"])

    def test_process_loss_requires_resume_and_health(self):
        self.assertEqual(runtime_recovery_decision(health="unhealthy", resume_exit=None, post_resume_health=None)["outcome"], "resume-required")
        self.assertEqual(runtime_recovery_decision(health="unhealthy", resume_exit=0, post_resume_health="healthy")["outcome"], "ready")
        self.assertEqual(runtime_recovery_decision(health="unhealthy", resume_exit=1, post_resume_health="unhealthy")["outcome"], "blocked")

    def test_ambiguous_health_blocks(self):
        with self.assertRaises(ContractError):
            runtime_recovery_decision(health="unknown", resume_exit=None, post_resume_health=None)


class RunnerTests(CloudFixture):
    def test_version_probe_ignores_wrapper_diagnostic_numbers(self):
        output = "/usr/bin/google-chrome: line 26: wrapper 999.0 diagnostics for /dev/fd/63\nGoogle Chrome 151.0.7922.137\nexit=0\n"
        self.assertTrue(_version_ok(output, ">=120 <200"))
        self.assertFalse(_version_ok(output, ">=200 <300"))

    def test_version_probe_accepts_node_v_prefix(self):
        self.assertTrue(_version_ok("v22.23.2\nexit=0\n", ">=22 <23"))
        self.assertFalse(_version_ok("v22.23.2\nexit=0\n", ">=23 <24"))

    def test_environment_presence_is_independent_of_tool_results(self):
        required = [{"name": "DATABASE_URL", "kind": "secret", "probe": "presence-only"}]
        self.assertEqual(_environment_presence({"DATABASE_URL": "present"}, required), {"DATABASE_URL": True})
        self.assertEqual(_environment_presence({}, required), {"DATABASE_URL": False})

    def runner(self) -> CloudReadinessRunner:
        return CloudReadinessRunner(
            self.project, self.profile, self.project / ".context/evidence", self.registry, {}
        )

    def test_readiness_id_must_be_a_safe_single_component(self):
        for value in ("", ".", "..", "../escape", "/absolute", "nested/path", "nested\\path", "bad\0id", None):
            with self.subTest(value=value), self.assertRaisesRegex(ContractError, "safe single path component"):
                self.runner()._prepare_evidence_dir(value)

    def test_run_evidence_is_isolated_and_preserved_siblings_are_ignored(self):
        root = self.project / ".context/evidence"
        prior = root / "prior-evidence"
        prior.mkdir(parents=True)
        prior_file = prior / "retained.log"
        prior_file.write_bytes(b"prior")
        (prior / "escape").symlink_to(self.project / "scripts/setup.sh")
        prior_receipt = root / "prior-receipt.json"
        prior_receipt.write_bytes(b"{}\n")
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        runner._record("CR1", "profile", b"current")
        self.assertTrue(runner._evidence_inventory_retained())
        self.assertEqual(prior_file.read_bytes(), b"prior")
        self.assertEqual(prior_receipt.read_bytes(), b"{}\n")
        self.assertEqual(runner.evidence_dir, root / "run-1-evidence")

    def test_external_locators_include_the_isolated_run_directory(self):
        external_root = Path(self.temporary.name).parent / f"{self.project.name}-external-evidence"
        self.addCleanup(lambda: __import__("shutil").rmtree(external_root, ignore_errors=True))
        runner = CloudReadinessRunner(self.project, self.profile, external_root, self.registry, {})
        runner._prepare_evidence_dir("run-1")
        runner._record("CR1", "profile", b"current")
        self.assertEqual(runner.locators, ["artifact:external/run-1-evidence/cr1-profile.log"])

    def test_distinct_readiness_ids_are_disjoint_and_reuse_fails_closed(self):
        first = self.runner()
        first._prepare_evidence_dir("run-1")
        first._record("CR1", "profile", b"first")
        second = self.runner()
        second._prepare_evidence_dir("run-2")
        second._record("CR1", "profile", b"second")
        self.assertNotEqual(first.evidence_dir, second.evidence_dir)
        self.assertNotEqual(first.locators, second.locators)
        self.assertEqual((first.evidence_dir / "cr1-profile.log").read_bytes(), b"first")
        with self.assertRaisesRegex(ContractError, "already exists"):
            self.runner()._prepare_evidence_dir("run-1")

    def test_exact_inventory_rejects_missing_extra_nested_and_symlink_entries(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        expected = runner._evidence_path("CR1", "profile")
        runner._record("CR1", "profile", b"current")
        expected.unlink()
        self.assertFalse(runner._evidence_inventory_retained())
        expected.write_bytes(b"current")
        (runner.evidence_dir / "extra.log").write_bytes(b"extra")
        self.assertFalse(runner._evidence_inventory_retained())
        (runner.evidence_dir / "extra.log").unlink()
        nested = runner.evidence_dir / "nested"
        nested.mkdir()
        self.assertFalse(runner._evidence_inventory_retained())
        nested.rmdir()
        expected.unlink()
        expected.symlink_to(self.project / "scripts/setup.sh")
        self.assertFalse(runner._evidence_inventory_retained())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_exact_inventory_rejects_special_files(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        special = runner._evidence_path("CR1", "profile")
        runner.expected_evidence[special.name] = ZERO
        os.mkfifo(special)
        self.assertFalse(runner._evidence_inventory_retained())

    def test_record_never_overwrites_existing_current_run_entry(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        runner._record("CR1", "profile", b"first")
        with self.assertRaisesRegex(ContractError, "already exists"):
            runner._record("CR1", "profile", b"second")
        self.assertEqual(runner._evidence_path("CR1", "profile").read_bytes(), b"first")

    def test_inventory_rejects_external_content_overwrite(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        path = runner._evidence_path("CR1", "profile")
        runner._record("CR1", "profile", b"first")
        path.write_bytes(b"forged")
        self.assertFalse(runner._evidence_inventory_retained())

    def test_inventory_rejects_directory_entry_replacement_during_read(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        path = runner._evidence_path("CR1", "profile")
        runner._record("CR1", "profile", b"first")
        detached = self.project / "detached-evidence.log"
        replaced = False

        def replacing_sha(raw: bytes) -> str:
            nonlocal replaced
            if not replaced:
                path.rename(detached)
                path.write_bytes(b"first")
                replaced = True
            return "sha256:" + __import__("hashlib").sha256(raw).hexdigest()

        with patch.object(cloud_runner, "_sha", side_effect=replacing_sha):
            self.assertFalse(runner._evidence_inventory_retained())

    def test_inventory_rejects_previously_checked_entry_replaced_during_later_read(self):
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        first = runner._evidence_path("CR1", "first")
        runner._record("CR1", "first", b"first")
        runner._record("CR1", "second", b"second")
        detached = self.project / "detached-first.log"
        replaced = False

        def replacing_sha(raw: bytes) -> str:
            nonlocal replaced
            if raw == b"second" and not replaced:
                first.rename(detached)
                first.write_bytes(b"first")
                replaced = True
            return "sha256:" + __import__("hashlib").sha256(raw).hexdigest()

        with patch.object(cloud_runner, "_sha", side_effect=replacing_sha):
            self.assertFalse(runner._evidence_inventory_retained())

    def test_inventory_rejects_replaced_run_directory(self):
        import shutil
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        runner._record("CR1", "profile", b"first")
        original = runner.evidence_dir.with_name("detached-evidence")
        runner.evidence_dir.rename(original)
        runner.evidence_dir.mkdir()
        (runner.evidence_dir / "cr1-profile.log").write_bytes(b"first")
        self.assertFalse(runner._evidence_inventory_retained())
        shutil.rmtree(runner.evidence_dir)
        original.rename(runner.evidence_dir)

    def test_inventory_rejects_replaced_evidence_root(self):
        import shutil
        runner = self.runner()
        runner._prepare_evidence_dir("run-1")
        runner._record("CR1", "profile", b"first")
        original = runner.evidence_root.with_name("detached-root")
        runner.evidence_root.rename(original)
        runner.evidence_root.mkdir()
        replacement = runner.evidence_root / "run-1-evidence"
        replacement.mkdir()
        (replacement / "cr1-profile.log").write_bytes(b"first")
        self.assertFalse(runner._evidence_inventory_retained())
        shutil.rmtree(runner.evidence_root)
        original.rename(runner.evidence_root)

    def test_fresh_cloud_runner_executes_cr1_to_cr10(self):
        import json
        import subprocess
        subprocess.run(["git", "init", "-q"], cwd=self.project, check=True)
        runtime = self.project / ".context/runtime"
        runtime.mkdir(parents=True)
        port = 31987
        start = f"mkdir -p .context/runtime; python3 -m http.server {port} --bind 127.0.0.1 >.context/runtime/web.log 2>&1 & echo $! >.context/web.pid"
        stop = "test ! -f .context/web.pid || { kill $(cat .context/web.pid) 2>/dev/null || true; rm -f .context/web.pid; }"
        for relative, command in {
            "scripts/setup.sh": "mkdir -p .context/generated",
            "scripts/loss.sh": stop,
            "scripts/resume.sh": start,
            "scripts/cleanup.sh": stop,
        }.items():
            path = self.project / relative
            path.write_text("#!/bin/sh\nset -eu\n" + command + "\n")
            path.chmod(0o755)
        browser_evidence_types = ("assertions", "screenshots", "console", "failed-network", "trace")
        journeys = []
        expected_browser_evidence = {}
        for journey_index, journey_id in enumerate(("health", "recovery"), start=1):
            outputs = {
                name: f".context/browser-{journey_id}-{name}.json"
                for name in browser_evidence_types
            }
            command = "; ".join(
                f"printf '{journey_id}-{name}' > {path}"
                for name, path in outputs.items()
            )
            journeys.append({"id": journey_id, "command": command, "evidence_paths": outputs})
            expected_browser_evidence.update({
                f"cr9-journey-{journey_index}-browser-{name}.log": f"{journey_id}-{name}".encode()
                for name in browser_evidence_types
            })
        (self.project / "planning/journeys.yml").write_text(json.dumps({"journeys": journeys}) + "\n")
        self.profile["cloud"].update({
            "repository_setup_digest": self.sha("scripts/setup.sh"), "os_family": "linux",
            "tool_probes": [{"name": "python", "command": "python3 --version", "version": ">=3 <4"}],
        })
        self.profile["services"][0].update({"start": start, "restart": start, "stop": stop, "port": port, "healthcheck": f"http://127.0.0.1:{port}/", "log_paths": [".context/runtime/web.log"]})
        self.profile["data"].update({"reset": "true", "migrate": "true", "seed": "true"})
        self.profile["verification"] = {"commands": ["printf \'%s\' \"$DATABASE_URL\""]}
        self.profile["preview"].update({"health_url": f"http://127.0.0.1:{port}/", "human_forward_sandbox_port": port})
        self.profile["browser_review"]["journeys_digest"] = self.sha("planning/journeys.yml")
        self.profile["recovery"].update({"process_loss_probe_digest": self.sha("scripts/loss.sh"), "resume_digest": self.sha("scripts/resume.sh")})
        self.profile["cleanup_digest"] = self.sha("scripts/cleanup.sh")
        environment = dict(os.environ, PLAYBOOK_CLOUD_BUILD_EPOCH="build-1", PLAYBOOK_CLOUD_SETUP_EPOCH="setup-1", DATABASE_URL="secret-value")
        facts = {"readiness_id": "run-1", "mode": "admission", "expected_profile_digest": digest(self.profile), "repository": "owner/demo", "base_sha": "base", "head_sha": "head", "tree_sha": "tree", "dependency_lock_digest": ZERO, "dependency_state_paths": [".context/generated"], "data_environment": "isolated-qa", "review_principal": "checker", "cleanup_residue_paths": [".context/web.pid"], "issuer": "process-attested:conductor:w1"}
        evidence_root = self.project / ".context/evidence"
        prior = evidence_root / "prior-evidence"
        prior.mkdir(parents=True)
        (prior / "retained.log").write_bytes(b"prior")
        prior_receipt = evidence_root / "prior-receipt.json"
        prior_receipt.write_bytes(b"{}\n")
        receipt = CloudReadinessRunner(self.project, self.profile, evidence_root, self.registry, environment).run(facts)
        self.assertEqual({item: receipt["conditions"][item]["outcome"] for item in CR_IDS}, {item: "pass" for item in CR_IDS})
        validate_readiness_receipt(receipt, self.profile, self.registry)
        evidence_dir = self.project / ".context/evidence/run-1-evidence"
        evidence = b"".join(path.read_bytes() for path in evidence_dir.iterdir())
        self.assertNotIn(b"secret-value", evidence)
        self.assertIn(b"[REDACTED]", evidence)
        self.assertEqual((prior / "retained.log").read_bytes(), b"prior")
        self.assertEqual(prior_receipt.read_bytes(), b"{}\n")
        self.assertEqual(
            {
                path.name: path.read_bytes()
                for path in evidence_dir.glob("cr9-journey-*-browser-*.log")
            },
            expected_browser_evidence,
        )
        self.assertEqual(
            {
                name for name in receipt["fingerprints"]["evidence"]
                if name.startswith("cr9-journey-") and "-browser-" in name
            },
            set(expected_browser_evidence),
        )
        for name in (
            "cr3-dependency-state.log", "cr7-web-observation.log", "cr8-web-health.log",
            "cr8-preview-health.log", "cr10-recovery-observation.log",
        ):
            self.assertTrue((evidence_dir / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()

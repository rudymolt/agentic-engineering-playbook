from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from copy import deepcopy
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim_conductor_host import ConductorHostAdapter, fixture_envelope  # noqa: E402
from delivery_pilot.interim_identity import operation_identities  # noqa: E402
from delivery_pilot.interim_coordinator import InterimDispatchError  # noqa: E402
from delivery_pilot.interim_coordinator import InterimFixtureCoordinator  # noqa: E402
from delivery_pilot.interim import InterimCheckpointStore, initial_record  # noqa: E402
from delivery_pilot.canonical import digest  # noqa: E402
from test_interim import approval  # noqa: E402


WORKSPACE = "11111111-1111-4111-8111-111111111111"
COORDINATOR = "22222222-2222-4222-8222-222222222222"


def operation(phase: str = "build") -> dict:
    identity = operation_identities("run-1", "op-1", phase, COORDINATOR)
    return {"id": "op-1", "phase": phase, **identity,
            "task": {"id": "task-1", "criteria": ["AC25", "AC27"]}}


class HostAdapterTests(unittest.TestCase):
    def test_escalated_route_prepares_idle_exact_session_and_reads_host_identity(self):
        item = operation("repair")
        item["escalated_slot"] = 1
        item["route"] = {"model": "gpt-6-astra", "effort": "high"}
        calls = []
        def command(argv):
            calls.append(argv)
            if argv[:2] == ["session", "create"]:
                self.assertNotIn("--message", argv)
                return {"id": item["session_id"], "model": "gpt-6-astra", "resolvedModel": "gpt-6-astra", "effort": "high", "deepLink": "conductor://session"}
            if argv[:2] == ["session", "get"]:
                return {"id": item["session_id"], "model": "gpt-6-astra", "resolvedModel": "gpt-6-astra", "effort": "high", "deepLink": "conductor://session"}
            if argv[:2] == ["session", "status"]:
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "idle", "updatedAt": "2026-09-25T00:00:00Z"}
            if argv[:2] == ["session", "message"]:
                return {"data": [], "hasMore": False, "limit": 1, "offset": 0}
            if argv[:2] == ["message", "create"]:
                return {"messageId": item["message_id"], "state": "queued", "deepLink": "conductor://message"}
            self.fail(argv)
        adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes={"escalation": item["route"]}, command=command)
        identity = adapter.preflight_escalated(item)
        self.assertEqual(identity["model"], "gpt-6-astra")
        self.assertEqual(identity["effort"], "high")
        item["route_preflight"] = identity
        adapter.send(item)
        self.assertEqual([argv[:2] for argv in calls], [["session", "create"], ["session", "get"], ["session", "status"], ["session", "message"], ["message", "create"]])
        brief = calls[-1][-1]
        self.assertIn("one reserved escalated slot", brief)
        self.assertIn("diagnosis", brief)
        self.assertIn("next_experiment", brief)
        self.assertIn("in-scope prerequisite", brief)
        self.assertIn("fresh Sol/high Verify", brief)

    def test_escalated_verify_cli_brief_has_candidate_evidence_without_astra_reasoning(self):
        item = operation("repair-verify")
        item["escalated_verify"] = "op-escalated"
        item["candidate"] = {"head": "a" * 40, "base": "b" * 40}
        item["verify_context"] = {"build_operation_id": "op-escalated", "candidate": item["candidate"],
                                  "criteria": ["AC25", "AC27"], "artifact_id": "artifact-escalated"}
        item["route"] = {"model": "gpt-6.1-sol", "effort": "high"}
        calls = []
        def command(argv):
            calls.append(argv)
            return {"id": item["session_id"], "deepLink": "conductor://session",
                    "initialMessage": {"messageId": item["message_id"], "state": "queued", "deepLink": "conductor://message"}}
        adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes={"escalated_verify": item["route"]}, command=command)
        adapter.send(item)
        brief = calls[0][-1]
        self.assertIn("fresh gpt-6.1-sol/high Verify", brief)
        self.assertIn("artifact-escalated", brief)
        self.assertIn('"head":"' + "a" * 40, brief)
        self.assertNotIn("prior_hypotheses", brief)
        self.assertNotIn('"diagnosis"', brief)

    def test_historical_escalated_verify_brief_and_dispatch_retain_approved_route(self):
        item = operation("repair-verify")
        item["escalated_verify"] = "old-escalated-operation"
        item["route"] = {"model": "gpt-6-sol", "effort": "high"}
        calls = []

        def command(argv):
            calls.append(argv)
            return {"id": item["session_id"], "deepLink": "conductor://session", "initialMessage": {"messageId": item["message_id"], "state": "queued", "deepLink": "conductor://message"}}

        adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes={}, command=command)
        adapter.send(item)
        self.assertEqual(calls[0][calls[0].index("--model") + 1], "gpt-6-sol")
        self.assertIn("fresh gpt-6-sol/high Verify", calls[0][-1])
        self.assertNotIn("gpt-6.1-sol", calls[0][-1])
        forged = deepcopy(item)
        forged["route"]["effort"] = "medium"
        with self.assertRaises(InterimDispatchError):
            adapter.send(forged)
        self.assertEqual(len(calls), 1)

    def test_escalated_preflight_refuses_missing_resolved_model_and_prior_turn(self):
        item = operation("repair")
        item["escalated_slot"] = 1
        item["route"] = {"model": "gpt-6-astra", "effort": "high"}
        for scenario in ("missing-model", "prior-turn"):
            with self.subTest(scenario=scenario):
                calls = []
                def command(argv):
                    calls.append(argv[:2])
                    if argv[:2] == ["session", "create"]:
                        return {"id": item["session_id"], "deepLink": "conductor://session"}
                    if argv[:2] == ["session", "get"]:
                        result = {"id": item["session_id"], "model": "gpt-6-astra", "effort": "high"}
                        if scenario != "missing-model":
                            result["resolvedModel"] = "gpt-6-astra"
                        return result
                    if argv[:2] == ["session", "status"]:
                        return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "idle", "updatedAt": "2026-09-25T00:00:00Z"}
                    if argv[:2] == ["session", "message"]:
                        return {"data": [{"id": "prior-turn"}] if scenario == "prior-turn" else [], "hasMore": False}
                    self.fail(argv)
                adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes={"escalation": item["route"]}, command=command)
                with self.assertRaises(InterimDispatchError):
                    adapter.preflight_escalated(item)
                self.assertNotIn(["message", "create"], calls)

    def test_failed_worker_retains_scoped_dirty_candidate_and_detects_changed_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote, coordinator, candidate = root / "remote.git", root / "coordinator", root / "candidate"
            real_run = subprocess.run
            def git(*args, cwd=None):
                return real_run(["git", *args], cwd=cwd or root, check=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
            git("init", "--bare", str(remote))
            git("clone", str(remote), str(coordinator))
            git("config", "user.name", "Test", cwd=coordinator)
            git("config", "user.email", "test@example.invalid", cwd=coordinator)
            (coordinator / "src").mkdir()
            (coordinator / "src" / "file.txt").write_text("base\n")
            git("add", "src/file.txt", cwd=coordinator)
            git("commit", "-m", "base", cwd=coordinator)
            git("push", "origin", "HEAD", cwd=coordinator)
            git("clone", str(remote), str(candidate))
            git("config", "user.name", "Test", cwd=candidate)
            git("config", "user.email", "test@example.invalid", cwd=candidate)
            git("checkout", "-b", "candidate-task-413", cwd=candidate)
            head = git("rev-parse", "HEAD", cwd=candidate)
            (candidate / "src" / "file.txt").write_text("retained edit\n")
            (candidate / "src" / "new.txt").write_text("retained new file\n")
            item = operation()
            item["task"] = {"candidate_ref": "candidate-task-413", "base": head}
            record = {"approval": {"workspaces": {"coordinator": "coordinator", "candidate": "candidate"},
                                   "repository": {"remote": "origin", "fetch_url": str(remote),
                                                  "push_url": str(remote), "base_ref": "refs/heads/master"},
                                   "implementation_paths": ["src"]}}
            def command(argv):
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"],
                        "status": "error", "updatedAt": "2026-09-25T00:00:00Z"}
            adapter = ConductorHostAdapter(WORKSPACE, command=command)
            pr_visible = [False]
            def fixture_run(argv, *args, **kwargs):
                if argv[0] == "gh":
                    url = "https://github.com/acme/playbook/pull/7"
                    if pr_visible[0] and "/pulls?" in argv[-1]:
                        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps([{"number": 7, "html_url": url}]), stderr="")
                    if pr_visible[0] and argv[-1].endswith("/pulls/7"):
                        body = {"number": 7, "html_url": url, "state": "open",
                                "base": {"repo": {"full_name": "acme/playbook"}, "ref": "master", "sha": head},
                                "head": {"repo": {"full_name": "acme/playbook"}, "sha": head}}
                        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(body), stderr="")
                    return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")
                return real_run(argv, *args, **kwargs)
            with mock.patch("delivery_pilot.interim_advance._repository_name", return_value="acme/playbook"), \
                 mock.patch("delivery_pilot.interim_conductor_host.subprocess.run", side_effect=fixture_run):
                fact = adapter.reconcile_failed(item, record, coordinator)
                self.assertEqual(fact["candidate"], {"head": head, "base": head})
                self.assertEqual(fact["candidate_work"]["paths"], ["src/file.txt", "src/new.txt"])
                adapter.preflight_repair_candidate(record, coordinator, fact["candidate_work"])
                (candidate / "src" / "file.txt").write_text("changed after reconciliation\n")
                with self.assertRaises(InterimDispatchError):
                    adapter.preflight_repair_candidate(record, coordinator, fact["candidate_work"])
                (candidate / "src" / "file.txt").write_text("retained edit\n")
                git("push", "origin", "candidate-task-413", cwd=candidate)
                pr_visible[0] = True
                observed = adapter.reconcile_failed(item, record, coordinator)
                self.assertEqual(observed["branch_head"], head)
                self.assertEqual(observed["pr"]["url"], "https://github.com/acme/playbook/pull/7")
                git("commit", "--allow-empty", "-m", "unexpected new head", cwd=candidate)
                with self.assertRaises(InterimDispatchError):
                    adapter.preflight_repair_candidate(record, coordinator, observed["candidate_work"])

    def test_remove_watchdog_prefix_renames_and_confirms_readback(self):
        calls = []
        names = ["UNATTENDED_INTERIM_V1 run=one mode=interim-coordinator", "run=one mode=interim-coordinator"]

        def command(argv):
            calls.append(argv)
            if argv[:2] == ["session", "get"]:
                return {"id": COORDINATOR, "name": names.pop(0)}
            self.assertEqual(argv, ["session", "rename", COORDINATOR, "--name", "run=one mode=interim-coordinator"])
            return {"id": COORDINATOR, "name": "run=one mode=interim-coordinator"}

        receipt = ConductorHostAdapter(WORKSPACE, command=command).remove_prefix(COORDINATOR, "stop-policy")
        self.assertEqual(receipt, {"prefix": "stop-policy", "readback_removed": True})
        self.assertEqual(len(calls), 3)

    def test_message_create_maps_actual_envelope_to_queued_and_persists_uuid(self):
        calls = []
        item = operation("wake")
        def command(argv):
            calls.append(argv)
            return {"messageId": item["message_id"], "state": "sent", "deepLink": "conductor://message"}
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        receipt = adapter.send_wake(item)
        self.assertEqual(receipt["worker_state"], "queued")
        self.assertEqual(receipt["observation"], {key: item[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")})
        self.assertEqual(calls[0][:3], ["message", "create", "--session"])

    def test_session_create_supplies_exact_approved_route_and_uuid_ids(self):
        calls = []
        item = operation()
        def command(argv):
            calls.append(argv)
            return {"id": item["session_id"], "deepLink": "conductor://session", "initialMessage": {"messageId": item["message_id"], "state": "queued", "deepLink": "conductor://message"}}
        adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes={"build": {"model": "gpt-5.6-terra", "effort": "high"}}, command=command)
        receipt = adapter.send(item)
        self.assertEqual(receipt["worker_state"], "queued")
        self.assertEqual(calls[0][:16], ["session", "create", "--workspace", WORKSPACE, "--agent", "codex", "--session-id", item["session_id"], "--name", "interim build op-1", "--model", "gpt-5.6-terra", "--effort", "high", "--message-id", item["message_id"]])
        self.assertIn('"criteria":["AC25","AC27"]', calls[0][-1])
        self.assertIn("JSON interim worker-result contract", calls[0][-1])

    def test_transcript_paginates_and_only_terminal_agent_event_can_settle(self):
        item = operation()
        host_event = "33333333-3333-4333-8333-333333333333"
        terminal_event = "44444444-4444-4444-8444-444444444444"
        def command(argv):
            if argv[:2] == ["session", "status"]:
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "idle", "updatedAt": "2026-09-20T00:00:00Z"}
            offset = argv[argv.index("--offset") + 1]
            if offset == "0":
                return {"data": [{"id": host_event, "sessionId": item["session_id"], "sessionIndex": 1, "type": "userMessage", "content": {"id": item["message_id"], "message": "brief", "state": "sent", "turnId": item["message_id"]}, "receivedAt": "now"}], "hasMore": True}
            return {"data": [{"id": terminal_event, "sessionId": item["session_id"], "sessionIndex": 2, "type": "agent", "content": {"turnId": item["message_id"], "userMessageId": item["message_id"], "rawPayload": {"event": {"type": "turn.completed"}}}, "receivedAt": "now"}], "hasMore": False}
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        receipt = adapter.observe(item)
        self.assertEqual((receipt["worker_state"], receipt["host_event_id"], receipt["host_turn_id"]), ("terminal", host_event, item["message_id"]))

    def test_transcript_refuses_turn_id_that_is_not_the_durable_message_uuid(self):
        item = operation()
        def command(argv):
            if argv[:2] == ["session", "status"]:
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "working", "updatedAt": "now"}
            return {"data": [{"id": "33333333-3333-4333-8333-333333333333", "sessionId": item["session_id"], "type": "userMessage", "content": {"id": item["message_id"], "state": "sent", "turnId": "44444444-4444-4444-8444-444444444444"}}], "hasMore": False}
        with self.assertRaisesRegex(InterimDispatchError, "turn identity"):
            ConductorHostAdapter(WORKSPACE, command=command).observe(item)

    def test_routine_workspaces_are_part_of_the_approved_envelope(self):
        self.assertEqual(fixture_envelope(main_workspaces=1, routine_deliveries=4, named_sessions=11, session_limit=11, workspace_limit=5), {"workspaces": 5, "sessions": 11, "routine_workspaces": 4})
        with self.assertRaisesRegex(ValueError, "exceeds"):
            fixture_envelope(main_workspaces=1, routine_deliveries=4, named_sessions=11, session_limit=11, workspace_limit=1)

    def test_terminal_event_extracts_only_its_exact_structured_result_contract(self):
        item = operation()
        terminal = {"transport": "accepted", "terminal_turn": True, "task_success": True,
                    "observation": {key: item[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                    "candidate": {"head": "a" * 40, "base": "b" * 40}}
        def command(argv):
            if argv[:2] == ["session", "status"]:
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "idle", "updatedAt": "now"}
            return {"data": [
                {"id": "33333333-3333-4333-8333-333333333333", "sessionId": item["session_id"], "type": "userMessage", "content": {"id": item["message_id"], "state": "sent", "turnId": item["message_id"]}},
                {"id": "44444444-4444-4444-8444-444444444444", "sessionId": item["session_id"], "type": "agent", "content": {"turnId": item["message_id"], "userMessageId": item["message_id"], "rawPayload": {"event": {"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": json.dumps(terminal)}}}}},
                {"id": "55555555-5555-4555-8555-555555555555", "sessionId": item["session_id"], "type": "agent", "content": {"turnId": item["message_id"], "userMessageId": item["message_id"], "rawPayload": {"event": {"type": "turn.completed"}}}},
            ], "hasMore": False}
        self.assertEqual(ConductorHostAdapter(WORKSPACE, command=command).observe(item), terminal)

    def test_completed_malformed_or_conflicting_final_is_unusable_in_every_worker_phase(self):
        for phase in ("build", "verify", "diagnosis", "repair", "repair-verify"):
            for output in ("malformed", "conflicting"):
                with self.subTest(phase=phase, output=output):
                    item = operation(phase)
                    identity = {key: item[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
                    def command(argv):
                        if argv[:2] == ["session", "status"]:
                            return {"workspaceId": WORKSPACE, "sessionId": item["session_id"],
                                    "status": "idle", "updatedAt": "2026-09-25T00:00:00Z"}
                        texts = ["{bad-json"] if output == "malformed" else ["{}", "{}"]
                        events = [{"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": text}}
                                  for text in texts] + [{"type": "turn.completed"}]
                        records = [{"id": "33333333-3333-4333-8333-333333333333", "sessionId": item["session_id"],
                                    "type": "userMessage", "content": {"id": item["message_id"], "state": "sent", "turnId": item["message_id"]}}]
                        for index, event in enumerate(events):
                            records.append({"id": f"{index + 4:08d}-4444-4444-8444-444444444444",
                                            "sessionId": item["session_id"], "type": "agent",
                                            "content": {"turnId": item["message_id"], "userMessageId": item["message_id"],
                                                        "rawPayload": {"event": event}}})
                        return {"data": records, "hasMore": False}
                    receipt = ConductorHostAdapter(WORKSPACE, command=command).observe(item)
                    self.assertEqual(receipt["observation"], identity)
                    self.assertEqual((receipt["worker_state"], receipt["terminal_turn"], receipt["task_success"]),
                                     ("terminal", True, False))

    def test_active_coordinator_observation_does_not_require_an_unsent_message(self):
        item = operation("coordinator")
        calls = []
        def command(argv):
            calls.append(argv)
            return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "working", "updatedAt": "now"}
        receipt = ConductorHostAdapter(WORKSPACE, command=command).observe_coordinator(item)
        self.assertEqual(receipt["state"], "active")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("terminal_turn", receipt)

    def test_cancelled_worker_is_terminal_without_fabricating_task_success(self):
        item = operation()
        def command(argv):
            if argv[:2] in (["session", "cancel"], ["session", "status"]):
                return {"workspaceId": WORKSPACE, "sessionId": item["session_id"], "status": "idle", "updatedAt": "now"}
            return {"data": [], "hasMore": False}
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        cancelled = adapter.cancel(item)
        # A fresh adapter recovers the confirmation from the durable stop ledger.
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        adapter.load_checkpoint({"usage": {"operations": [item]}, "recovery": {"stop": {"cancellations": [{"operation_id": item["id"], "state": "cancelled", "receipt": cancelled}]}}})
        receipt = adapter.observe(item)
        self.assertEqual(receipt["worker_state"], "terminal")
        self.assertNotIn("task_success", receipt)
        self.assertNotIn("terminal_turn", receipt)

    def test_cancel_accepts_exact_worker_session_in_verifier_workspace(self):
        item = operation()
        other_workspace = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        def command(argv):
            self.assertIn(argv[:2], (["session", "cancel"], ["session", "status"]))
            return {"workspaceId": other_workspace, "sessionId": item["session_id"],
                    "status": "idle", "updatedAt": "now"}
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        receipt = adapter.cancel(item)
        self.assertEqual(receipt["state"], "cancelled")
        self.assertEqual(receipt["host_workspace_id"], other_workspace)
        observed = adapter.observe(item)
        self.assertEqual(observed["worker_state"], "terminal")

    def test_owned_workers_uses_status_only_across_worker_workspaces(self):
        item = operation()
        item["status"] = "result-unusable"
        other_workspace = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        calls = []
        def command(argv):
            calls.append(argv)
            return {"workspaceId": other_workspace, "sessionId": item["session_id"],
                    "status": "idle", "updatedAt": "now"}
        adapter = ConductorHostAdapter(WORKSPACE, command=command)
        adapter.load_checkpoint({"usage": {"operations": [item]}, "recovery": {"stop": None}})
        owned = adapter.owned_workers("run-1")
        self.assertEqual(owned[0]["state"], "terminal")
        self.assertEqual(owned[0]["receipt"]["host_workspace_id"], other_workspace)
        self.assertEqual(calls, [["session", "status", item["session_id"]]])

    def test_queued_build_and_verify_reconcile_same_ids_before_pr_ready(self):
        task = {"id": "task", "slice_id": "TASK-413", "attempt": 1, "candidate_ref": "candidate", "base": "b" * 40,
                "criteria": ["AC25"], "runtimes": {"build": {"runner": "build-runner", "permissions": "read-only"}, "verify": {"runner": "verify-runner", "permissions": "read-only"}},
                "commands": {"build": ["unit"], "verify": ["unit"], "qa": ["qa"], "ci": ["ci"]}, "limits": {"max_artifacts": 1, "max_tools": 1, "wall_time_seconds": 60}}
        class QueueThenTerminal:
            def observe_coordinator(self, op):
                return {"observation": {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "current_coordinator": op["session_id"], "state": "active", "elapsed_seconds": 0}
            def send(self, op):
                return {"observation": {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
            def reconcile(self, op):
                phase = op["phase"]; artifact = phase + "-artifact"
                route = {"model": "gpt-5.6-sol", "effort": "medium"} if phase == "verify" else {"model": "gpt-5.6-terra", "effort": "high"}
                result = {"observation": {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "transport": "accepted", "terminal_turn": True, "task_success": True, "candidate": {"head": "a" * 40, "base": "b" * 40}, "criteria": {"AC25": "pass"}, "executed_checks": ["AC25"], "runtime": {**route, "runner": phase + "-runner", "permissions": "read-only"}, "artifacts": [artifact], "tools": ["unit"], "wall_time_seconds": 1, "elapsed_seconds": 1, "host_counters": {"tokens": None, "cost": None}, "fresh_context": phase == "verify", "builder_transcript": False, "verdict": "pass", "nonblocking_findings": [], "evidence": {"artifact": {"id": artifact, "task_id": "task", "operation_id": op["id"], "head": "a" * 40, "base": "b" * 40}, "commands": [{"command": "unit", "result": "pass", "artifact_id": artifact, "operation_id": op["id"]}], "checks": [{"criterion_id": "AC25", "command": "unit", "result": "pass", "artifact_id": artifact, "operation_id": op["id"]}]}}
                if phase == "verify":
                    result["handoff"] = {"qa": [{"status": "pass", "head": "a" * 40, "command": "qa", "result": "pass", "artifact_id": artifact, "operation_id": op["id"]}], "ci": [{"status": "pass", "head": "a" * 40, "command": "ci", "result": "pass", "artifact_id": artifact, "operation_id": op["id"]}], "final_review": {"verdict": "pass", "candidate": result["candidate"], "fresh_context": True, "runtime": result["runtime"], "artifact_id": artifact, "operation_id": op["id"], "criteria": ["AC25"]}, "pr": {"url": "https://example.invalid/pr/1", "head": "a" * 40, "base": "b" * 40, "state": "open", "operation_id": op["id"], "artifact_id": artifact, "merge": "unavailable"}}
                return result
            def cancel(self, op): return {"observation": {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "cancelled"}
        with tempfile.TemporaryDirectory() as directory:
            remote, checkout = Path(directory) / "remote.git", Path(directory) / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": digest(task)}]
            store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"]); snapshot = store.create_and_publish(initial_record(item)); worker = QueueThenTerminal(); coordinator = InterimFixtureCoordinator(store)
            snapshot = coordinator.run_one(snapshot, "TASK-413", task, worker, worker)
            self.assertEqual(next(op for op in snapshot.value["usage"]["operations"] if op["phase"] == "build")["status"], "reconcile-required")
            snapshot = coordinator.run_one(snapshot, "TASK-413", task, worker, worker)
            self.assertEqual(next(op for op in snapshot.value["usage"]["operations"] if op["phase"] == "build")["status"], "reconciled")
            snapshot = coordinator.run_one(snapshot, "TASK-413", task, worker, worker)
            self.assertEqual(next(op for op in snapshot.value["usage"]["operations"] if op["phase"] == "verify")["status"], "reconcile-required")
            snapshot = coordinator.run_one(snapshot, "TASK-413", task, worker, worker)
            snapshot = coordinator.run_one(snapshot, "TASK-413", task, worker, worker)
            self.assertEqual(snapshot.value["state"]["next_action"], "pr-ready", snapshot.value["state"])


if __name__ == "__main__":
    unittest.main()

"""Shipped exact-ref advance and PR readback regressions."""
from __future__ import annotations

import os
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import test_interim_coordinator as fixtures
from test_interim_coordinator import Fixture
from delivery_pilot.canonical import digest
from delivery_pilot.interim import InterimError, initial_record, validate_record
from delivery_pilot.interim import main as interim_main
from delivery_pilot import interim as interim_module
from delivery_pilot.interim_disposition import unresolved as recovery_unresolved
from delivery_pilot.interim_disposition import ObservationFailure
from delivery_pilot.interim_advance import advance_once, github_pr_readback
from delivery_pilot.interim_coordinator import InterimDispatchError
from delivery_pilot.interim_conductor_host import ConductorHostAdapter
from delivery_pilot.interim_pr import ensure_verify_pr
from test_interim_host_continuation import QueuedConductor
from test_interim_repair import RepairFixture, EscalatedFixture
from control_ref_test_support import memoized_control_refs




class PhaseHost:
    def __init__(self, test, pr_url="https://example.invalid/pr/1", candidates=None):
        self.test = test
        self.pr_url = pr_url
        self.candidates = candidates or {}
        self.sent = []
        self.reconciled = []

    def observe_coordinator(self, operation):
        return Fixture({}).observe_coordinator(operation)

    def send(self, operation):
        self.sent.append(operation["id"])
        phase = operation["phase"]
        receipt = Fixture(self.test.result("verify" if phase == "verify" else "build", self.candidates.get(operation["slice"]))).send(operation)
        if phase == "verify":
            receipt["handoff"]["pr"]["url"] = self.pr_url
        return receipt

    def reconcile(self, operation):
        self.reconciled.append(operation["id"])
        return Fixture(self.test.result("verify" if operation["phase"] == "verify" else "build")).send(operation)


class AdvanceTests(unittest.TestCase):
    def test_escalated_candidate_recovers_same_sha_verify_without_new_slot(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["forecast"] = {"work_units": 9, "verification_units": 5, "likely_repair_units": 4, "final_handback_units": 1}
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class Host(PhaseHost):
            def __init__(self, test):
                super().__init__(test)
                self.verify_attempts = 0
            def preflight_repair_candidate(self, durable, repository, expected):
                pass
            def preflight_escalated(self, operation):
                return {"session_id": operation["session_id"], **operation["route"]}
            def reconcile_failed(self, operation, durable, repository):
                candidate = operation.get("candidate", {"head": "a" * 40, "base": task["base"]})
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": candidate, "branch_head": candidate["head"], "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": candidate["head"]}, "effects_complete": True}
            def send(self, operation):
                self.sent.append(operation["id"])
                observation = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
                if operation["phase"] == "build":
                    return {"observation": observation, "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                if operation["phase"] == "diagnosis":
                    receipt = RepairFixture().send(operation)
                    receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["finding"]["id"]
                    return receipt
                if operation.get("escalated_slot"):
                    receipt = EscalatedFixture().send(operation)
                    receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["opening"]["finding"]["id"]
                    return receipt
                if operation["phase"] == "repair":
                    return RepairFixture("incomplete").send(operation)
                self.verify_attempts += 1
                if self.verify_attempts == 1:
                    return {"observation": observation, "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                return RepairFixture().send(operation)
        host = Host(self)
        tasks = {task["slice_id"]: task}
        outcomes = [advance_once(store, record, tasks, host)["outcome"] for _ in range(12)]
        saved = store.reload(record).value
        self.assertEqual(saved["repair"]["status"], "completed", outcomes)
        self.assertEqual(host.verify_attempts, 2)
        self.assertEqual(len(saved["repair"]["escalated_slots"]), 1)
        self.assertEqual(len({op["id"] for op in saved["usage"]["operations"]}), len(saved["usage"]["operations"]))
        forged = deepcopy(saved)
        first_verify = next(op for op in forged["usage"]["operations"] if op.get("escalated_verify") and op.get("verify_attempt") == 1)
        first_verify["route"] = {"model": "gpt-6.1-sol", "effort": "medium"}
        with self.assertRaises(InterimError):
            validate_record(forged)

    for _name in ("setUp", "tearDown", "git", "clone", "approval", "store", "task", "s2_approval", "result"):
        locals()[_name] = getattr(fixtures.CoordinatorTests, _name)

    def s2_approval(self):
        approved = fixtures.CoordinatorTests.s2_approval(self)
        approved["workspaces"] = {"coordinator": self.first.name, "candidate": self.second.name}
        return approved
    def _run(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        # The disposable local bare remote models the exact CAS store.  The
        # PR reader is injected below; production keeps the URL/remote check.
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        return store, record, {"TASK-413": self.task()}, PhaseHost(self)

    @staticmethod
    def _stopping(record):
        stopped = deepcopy(record)
        stopped["recovery"] = {"status": "stopping", "wakes": [], "observations": [],
                               "stop": {"intent_at": "2026-09-25T00:00:00Z", "instruction": "stop",
                                        "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
        return stopped

    def test_one_step_sync_build_then_verify_then_pr_readback(self):
        store, record, tasks, host = self._run()
        first = advance_once(store, record, tasks, host)
        self.assertEqual(first["outcome"], "verify")
        self.assertEqual(len(host.sent), 1)
        second = advance_once(store, record, tasks, host)
        self.assertEqual(second["outcome"], "pr-ready")
        self.assertEqual(len(host.sent), 2)
        self.assertEqual(advance_once(store, record, tasks, host, pr_readback=lambda *_: {"head": "f" * 40, "base": "b" * 40})["outcome"], "pr-head-or-base-changed")
        self.assertEqual(len(host.sent), 2)
        self.assertEqual(len(store.reload(record).value["usage"]["charges"]), 3)

    def test_advance_selected_dispatch_limit_retires_with_decision_notice(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = {"dispatch_max": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        result = advance_once(store, record, {"TASK-413": self.task()}, PhaseHost(self))
        saved = store.reload(record).value
        self.assertEqual(result["outcome"], "selected-limit")
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(saved["recovery_disposition"]["notices"][0]["cause"], "selected-limit")

    def test_resumed_terminal_readback_crossing_deadline_cannot_send_verify(self):
        before = datetime.now(timezone.utc) + timedelta(minutes=1)
        after = before + timedelta(seconds=2)
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = {"deadline_at": (before + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        clock = {"at": before}
        class FakeDatetime:
            @classmethod
            def now(cls, tz):
                return clock["at"]
        class Queued(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["phase"])
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(self, operation):
                clock["at"] = after
                return Fixture(self.test.result("build")).send(operation)
        host = Queued(self)
        tasks = {"TASK-413": self.task()}
        self.assertEqual(advance_once(store, record, tasks, host, now=before)["outcome"], "await-worker")
        with mock.patch("delivery_pilot.interim_advance.datetime", FakeDatetime):
            result = advance_once(store, record, tasks, host)
        saved = store.reload(record).value
        self.assertEqual(result["outcome"], "selected-limit")
        self.assertEqual(host.sent, ["build"])
        self.assertEqual(len(saved["usage"]["launches"]), 2)
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(saved["recovery_disposition"]["notices"][0]["cause"], "selected-limit")

    def test_host_binding_crossing_deadline_cannot_admit_worker_send(self):
        before = datetime.now(timezone.utc) + timedelta(minutes=1)
        after = before + timedelta(seconds=2)
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = {"deadline_at": (before + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        clock = {"at": before}
        class FakeDatetime:
            @classmethod
            def now(cls, tz):
                return clock["at"]
        class Binding(PhaseHost):
            def bind_worker_hint(self, durable, operation_id, repository):
                clock["at"] = after
        host = Binding(self)
        with mock.patch("delivery_pilot.interim_advance.datetime", FakeDatetime):
            result = advance_once(store, record, {"TASK-413": self.task()}, host)
        saved = store.reload(record).value
        self.assertEqual(result["outcome"], "selected-limit")
        self.assertEqual(host.sent, [])
        self.assertEqual(saved["monitoring"]["state"], "inactive")

    def test_legacy_failed_build_natural_wake_makes_one_durable_authority_decision(self):
        from delivery_pilot.interim_monitor import reconcile
        from test_interim_monitor import FakeConductor
        start = datetime(2026, 9, 25, 16, tzinfo=timezone.utc)
        store, record, tasks, _ = self._run()
        task = tasks["TASK-413"]
        self.assertEqual(record["approval"]["hard_limits"], "none")
        class Failed(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(self, operation):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": None, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40},
                        "effects_complete": True}
        host = Failed(self)
        self.assertEqual(advance_once(store, record, tasks, host, now=start)["outcome"], "await-worker")
        pending = store.reload(record).value
        build = next(op for op in pending["usage"]["operations"] if op["phase"] == "build")
        where = {"run_id": pending["approval"]["run_id"], "control_ref": pending["monitoring"]["control_ref"],
                 "generation": pending["monitoring"]["pending_wake"]["generation"]}
        observed = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                  "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                                  "awaited_worker": {**{name: build[name] for name in
                                                        ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "error"}})
        _, decision = reconcile(store, record, where, "backup", observed, start)
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(advance_once(store, record, tasks, host, now=start)["outcome"], "handback")
        saved = store.reload(record).value
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(saved["recovery_disposition"]["notices"][0]["cause"], "outside-authority")
        self.assertEqual(len(saved["recovery_disposition"]["notices"]), 1)
        self.assertEqual(len(saved["usage"]["launches"]), 3)
        self.assertEqual(len(host.sent), 1)
        self.assertIn("failure_reconciliation", next(op for op in saved["usage"]["operations"] if op["phase"] == "build"))
        self.assertEqual(advance_once(store, record, tasks, host, now=start + timedelta(minutes=15))["outcome"], "handback")
        _, repeat = reconcile(store, record, where, "backup", FakeConductor(), start + timedelta(minutes=15))
        self.assertNotEqual(repeat["action"], "resume-coordinator")
        self.assertEqual(len(store.reload(record).value["usage"]["launches"]), 3)

    def test_reconciled_legacy_failure_after_crash_gets_same_authority_decision(self):
        store, record, tasks, _ = self._run()
        task = tasks["TASK-413"]
        class Failed(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": None, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40},
                        "effects_complete": True}
        host = Failed(self)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        with mock.patch("delivery_pilot.interim_advance._open_failed_or_decide", side_effect=RuntimeError("crash after exact effect checkpoint")):
            with self.assertRaisesRegex(RuntimeError, "crash after exact effect checkpoint"):
                advance_once(store, record, tasks, host)
        intermediate = store.reload(record).value
        validate_record(intermediate)
        self.assertEqual(intermediate["state"]["next_action"], "failure-reconciled")
        self.assertIn("failure_reconciliation", next(op for op in intermediate["usage"]["operations"] if op["phase"] == "build"))
        self.assertEqual(len(intermediate["usage"]["launches"]), 2)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "handback")
        saved = store.reload(record).value
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(saved["recovery_disposition"]["notices"][0]["cause"], "outside-authority")
        self.assertEqual(len(saved["usage"]["launches"]), 2)
        self.assertEqual(len(host.sent), 1)

    def test_failed_effect_readback_crossing_deadline_settles_without_repair(self):
        before = datetime.now(timezone.utc) + timedelta(minutes=1)
        after = before + timedelta(seconds=2)
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = {"deadline_at": (before + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")}
        approved["forecast"] = {"work_units": 5, "verification_units": 3,
                                "likely_repair_units": 2, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        clock = {"at": before}
        class FakeDatetime:
            @classmethod
            def now(cls, tz):
                return clock["at"]
        class Failed(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
            def reconcile_failed(self, operation, durable, repository):
                clock["at"] = after
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": None, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40},
                        "effects_complete": True}
        host = Failed(self)
        tasks = {task["slice_id"]: task}
        self.assertEqual(advance_once(store, record, tasks, host, now=before)["outcome"], "worker-failed")
        with mock.patch("delivery_pilot.interim_advance.datetime", FakeDatetime):
            result = advance_once(store, record, tasks, host)
        saved = store.reload(record).value
        self.assertEqual(result["outcome"], "selected-limit")
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertIsNone(saved.get("repair"))
        self.assertEqual(len(host.sent), 1)
        self.assertIn("failure_reconciliation", next(op for op in saved["usage"]["operations"] if op["phase"] == "build"))

    def test_ambiguous_send_reconciles_exact_id_after_restart(self):
        store, record, tasks, host = self._run()
        sent = []
        original = host.send
        def lost_response(operation):
            sent.append(operation["id"])
            original(operation)
            raise TimeoutError("response lost")
        host.send = lost_response
        waiting = advance_once(store, record, tasks, host)
        self.assertEqual(waiting["outcome"], "await-worker")
        self.assertEqual(len(sent), 1)
        host.send = lambda operation: (self.fail("pending operation was resent") if operation["id"] == sent[0]
                                       else Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                                     "task_success": False, "elapsed_seconds": 0}).send(operation))
        observed = advance_once(store, record, tasks, host)
        self.assertEqual(observed["outcome"], "await-worker")
        self.assertEqual(host.reconciled, sent)
        self.assertEqual(len(store.reload(record).value["usage"]["charges"]), 3)

    def test_malformed_terminal_build_is_one_retained_failed_attempt(self):
        store, record, tasks, host = self._run()
        original = host.send
        def malformed(operation):
            receipt = original(operation)
            receipt.pop("candidate", None)
            return receipt
        host.send = malformed
        result = advance_once(store, record, tasks, host)
        self.assertEqual(result["outcome"], "worker-failed")
        saved = store.reload(record).value
        build = next(item for item in saved["usage"]["operations"] if item["phase"] == "build")
        self.assertEqual(build["status"], "result-unusable")
        self.assertEqual(saved["state"]["operation_id"], build["id"])
        self.assertEqual(len(saved["usage"]["charges"]), 2)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        self.assertEqual(len(host.sent), 1)

    def test_actual_cli_completed_malformed_build_enters_reconciled_repair(self):
        self.git("checkout", "-b", "master", cwd=self.first)
        (self.first / "src").mkdir()
        (self.first / "src" / "partial.txt").write_text("base\n")
        self.git("add", "src/partial.txt", cwd=self.first)
        self.git("commit", "-m", "fixture base", cwd=self.first)
        self.git("push", "origin", "master", cwd=self.first)
        self.git("fetch", "origin", "master", cwd=self.second)
        self.git("checkout", "-b", "candidate-task-413", "FETCH_HEAD", cwd=self.second)
        self.git("push", "origin", "candidate-task-413", cwd=self.second)
        candidate_head = self.git("rev-parse", "HEAD", cwd=self.second).stdout.strip()
        github_remote = "https://github.com/acme/playbook.git"
        self.git("remote", "set-url", "origin", github_remote, cwd=self.first)
        self.git("remote", "set-url", "origin", github_remote, cwd=self.second)
        (self.second / "src" / "partial.txt").write_text("retained partial work\n")
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["coordinator"]["session_id"] = str(uuid4())
        approved["workspaces"] = {"coordinator": "first", "candidate": "second"}
        approved["implementation_paths"] = ["src"]
        approved["repository"]["base_ref"] = "refs/heads/master"
        approved["repository"]["fetch_url"] = github_remote
        approved["repository"]["push_url"] = github_remote
        approved["forecast"] = {"work_units": 8, "verification_units": 4,
                                "likely_repair_units": 3, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        known, sent = {}, []
        workspace = "11111111-1111-4111-8111-111111111111"
        def command(argv):
            if argv[:2] == ["session", "create"]:
                session_id = argv[argv.index("--session-id") + 1]
                operation = next(item for item in known.values() if item["session_id"] == session_id)
                sent.append(operation["id"])
                return {"id": session_id, "initialMessage": {"messageId": operation["message_id"], "state": "queued"}}
            session_id = argv[2]
            if session_id == approved["coordinator"]["session_id"]:
                return {"workspaceId": workspace, "sessionId": session_id, "status": "working", "updatedAt": "2026-09-25T00:00:00Z"}
            operation = next(item for item in known.values() if item["session_id"] == session_id)
            if argv[:2] == ["session", "status"]:
                return {"workspaceId": workspace, "sessionId": session_id, "status": "idle", "updatedAt": "2026-09-25T00:00:00Z"}
            self.assertEqual(argv[:2], ["session", "message"])
            records = [{"id": str(uuid4()), "sessionId": session_id, "type": "userMessage",
                        "content": {"id": operation["message_id"], "state": "sent", "turnId": operation["message_id"]}}]
            for event in ({"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": "{malformed-json"}},
                          {"type": "turn.completed"}):
                records.append({"id": str(uuid4()), "sessionId": session_id, "type": "agent",
                                "content": {"turnId": operation["message_id"], "userMessageId": operation["message_id"],
                                            "rawPayload": {"event": event}}})
            return {"data": records, "hasMore": False}
        task = self.task()
        real_run = subprocess.run
        gh_calls = []
        def gh_readback(argv, *args, **kwargs):
            if argv[0] == "gh":
                gh_calls.append(argv)
                url = "https://github.com/acme/playbook/pull/7"
                if "/pulls?" in argv[-1]:
                    body = [{"number": 7, "html_url": url}]
                else:
                    body = {"number": 7, "html_url": url, "state": "open",
                            "base": {"repo": {"full_name": "acme/playbook"}, "ref": "master", "sha": task["base"]},
                            "head": {"repo": {"full_name": "acme/playbook"}, "sha": candidate_head}}
                return subprocess.CompletedProcess(argv, 0, json.dumps(body), "")
            if argv[0] == "git" and any(verb in argv[1:] for verb in ("ls-remote", "fetch", "push")):
                # The approved URL stays GitHub-shaped; transport commands in
                # these owned checkouts reach only the disposable bare remote.
                argv = ["git", "-c", f"url.{self.remote}.insteadOf={github_remote}", *argv[1:]]
            return real_run(argv, *args, **kwargs)
        def host():
            adapter = ConductorHostAdapter(workspace, agent="codex", routes=approved["routes"], command=command)
            adapter.load_checkpoint(store.reload(record).value)
            known.update(adapter.operations)
            send = adapter.send
            def remembered(operation):
                known[operation["id"]] = operation
                return send(operation)
            adapter.send = remembered
            return adapter
        with mock.patch("delivery_pilot.interim_conductor_host.subprocess.run", side_effect=gh_readback):
            store.create_and_publish(record)
            self.assertEqual(advance_once(store, record, {task["slice_id"]: task}, host())["outcome"], "await-worker")
            self.assertEqual(advance_once(store, record, {task["slice_id"]: task}, host())["outcome"], "diagnosis")
            failed = store.reload(record).value
            build = next(item for item in failed["usage"]["operations"] if item["phase"] == "build")
            self.assertEqual(build["status"], "result-unusable")
            self.assertEqual(build["receipt"]["terminal_turn"], True)
            self.assertFalse(build["receipt"]["task_success"])
            direct_fact = host().reconcile_failed(build, failed, self.first)
            self.assertEqual(direct_fact["branch_head"], candidate_head)
            self.assertEqual(direct_fact["pr"]["url"], "https://github.com/acme/playbook/pull/7")
            reconciled = store.reload(record).value
            failed_build = next(item for item in reconciled["usage"]["operations"] if item["phase"] == "build")
            self.assertEqual(failed_build["failure_reconciliation"]["branch_head"], candidate_head)
            self.assertEqual(failed_build["failure_reconciliation"]["pr"]["url"],
                             "https://github.com/acme/playbook/pull/7")
        with mock.patch("delivery_pilot.interim_conductor_host.subprocess.run", side_effect=gh_readback):
            saved = store.reload(record).value
        self.assertEqual(saved["repair"]["opening"]["origin_operation_id"], build["id"])
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(saved["usage"]["charges"]), 2)
        self.assertTrue(gh_calls)
        self.assertTrue(all("POST" not in call for call in gh_calls))
        self.assertEqual((self.second / "src" / "partial.txt").read_text(), "retained partial work\n")

    def test_transient_observation_counts_backup_cycles_and_not_duplicate_ticks(self):
        store, record, tasks, host = self._run()
        def queued(operation):
            host.sent.append(operation["id"])
            return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                    "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
        host.send = queued
        start = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        self.assertEqual(advance_once(store, record, tasks, host, now=start)["outcome"], "await-worker")
        host.reconcile = lambda _: (_ for _ in ()).throw(OSError("temporary outage"))
        for when, expected in ((start, 1), (start + timedelta(minutes=1), 1),
                               (start + timedelta(minutes=15), 2), (start + timedelta(minutes=30), 3)):
            advance_once(store, record, tasks, host, now=when)
            saved = store.reload(record).value
            self.assertEqual(saved["recovery_disposition"]["active"]["count"], expected)
        saved = store.reload(record).value
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(len(saved["recovery_disposition"]["notices"]), 1)
        self.assertEqual(saved["recovery_disposition"]["notices"][0]["cause"], "transient-outage")

    def test_exception_then_exact_unknown_preserves_three_cycle_guard_and_retry_after(self):
        store, record, tasks, host = self._run()
        def queued(operation):
            return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                    "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
        host.send = queued
        start = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
        advance_once(store, record, tasks, host, now=start)
        host.reconcile = lambda _: (_ for _ in ()).throw(ObservationFailure("ambiguous-missing-session", start + timedelta(minutes=20)))
        advance_once(store, record, tasks, host, now=start)
        saved = store.reload(record).value
        self.assertEqual(saved["recovery_disposition"]["active"]["category"], "ambiguous-missing-session")
        self.assertEqual(saved["recovery_disposition"]["active"]["next_check_at"], "2026-09-25T12:20:00Z")
        host.reconcile = lambda operation: {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                             "transport": "unknown", "worker_state": "unknown", "elapsed_seconds": 0}
        advance_once(store, record, tasks, host, now=start + timedelta(minutes=20))
        self.assertEqual(store.reload(record).value["recovery_disposition"]["active"]["count"], 2)
        advance_once(store, record, tasks, host, now=start + timedelta(minutes=35))
        saved = store.reload(record).value
        self.assertEqual(saved["recovery_disposition"]["active"]["count"], 3)
        self.assertEqual(saved["monitoring"]["state"], "inactive")

    def test_status_reads_durable_decision_without_host_connection(self):
        store, record, tasks, host = self._run()
        current = store.reload(record)
        projected = deepcopy(current.value)
        operation = projected["approval"]["coordinator"]["session_id"]
        for minutes in (0, 15, 30):
            recovery_unresolved(projected, "authority-denied", operation,
                                datetime(2026, 9, 25, 12, tzinfo=timezone.utc) + timedelta(minutes=minutes))
        store.persist(current, projected)
        record_file = self.root / "approved-record.json"
        record_file.write_text(json.dumps(record))
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(interim_main(["status", "--repository", str(self.first), "--record", str(record_file)]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(len(value["decision_notices"]), 1)
        self.assertEqual(value["decision_notices"][0]["cause"], "authority-denied")

    def test_exact_worker_error_reconciles_before_diagnosis_without_second_build(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["forecast"] = {"work_units": 5, "verification_units": 3,
                                "likely_repair_units": 2, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class FailedHost(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                if operation["phase"] == "build":
                    return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                            "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                receipt = RepairFixture().send(operation)
                if operation["phase"] == "diagnosis":
                    receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["finding"]["id"]
                return receipt
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": "a" * 40, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40}, "effects_complete": True}
            def preflight_repair_candidate(self, durable, repository, expected):
                self.test.assertEqual(expected["paths"], [])
        host = FailedHost(self)
        tasks = {task["slice_id"]: task}
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        from delivery_pilot.interim_monitor import reconcile
        from test_interim_monitor import FakeConductor
        failed = store.reload(record).value
        where = {"run_id": failed["approval"]["run_id"],
                 "control_ref": failed["monitoring"]["control_ref"],
                 "generation": failed["monitoring"]["pending_wake"]["generation"]}
        _, decision = reconcile(store, record, where, "backup", FakeConductor())
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "diagnosis")
        self.assertEqual(len([op for op in store.reload(record).value["usage"]["operations"] if op["phase"] == "build"]), 1)
        for _ in range(2):
            advance_once(store, record, tasks, host)
        saved = store.reload(record).value
        self.assertEqual(len([op for op in saved["usage"]["operations"] if op["phase"] == "build"]), 1)
        self.assertEqual(len([op for op in saved["usage"]["operations"] if op["phase"] == "diagnosis"]), 1)
        self.assertEqual(len([op for op in saved["usage"]["operations"] if op["phase"] == "diagnosis"]), 1)
        advance_once(store, record, tasks, host)
        saved = store.reload(record).value
        self.assertEqual(saved["repair"]["status"], "completed", saved["state"])
        from delivery_pilot.interim_semantics import accepted_slice_candidate
        self.assertEqual(accepted_slice_candidate(saved, task["slice_id"]),
                         {"head": "c" * 40, "base": task["base"]})
        self.assertEqual(len([op for op in saved["usage"]["operations"] if op["phase"] == "build"]), 1)
        self.assertEqual(len(saved["usage"]["charges"]), len(saved["usage"]["operations"]))

    def test_failed_worker_unknown_effect_uses_wakes_without_replacement(self):
        from delivery_pilot.interim_monitor import reconcile
        from test_interim_monitor import FakeConductor
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = "none"
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class UncertainHost(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(self, operation):
                self.reconciled.append(operation["id"])
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
            def reconcile_failed(self, operation, durable, repository):
                raise OSError("effect read unavailable")
        host = UncertainHost(self)
        tasks = {task["slice_id"]: task}
        start = datetime.now(timezone.utc)
        self.assertEqual(advance_once(store, record, tasks, host, now=start)["outcome"], "await-worker")
        for index in range(3):
            snapshot = store.reload(record).value
            pending = snapshot["monitoring"]["pending_wake"]
            where = {"run_id": snapshot["approval"]["run_id"], "control_ref": snapshot["monitoring"]["control_ref"],
                     "generation": pending["generation"]}
            worker = next(op for op in snapshot["usage"]["operations"] if op["phase"] == "build")
            observation = {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False,
                           "active_workers": False, "working_ambiguous": False}
            if index == 0:
                observation["awaited_worker"] = {**{name: worker[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                                   "state": "error"}
            wake, decision = reconcile(store, record, where, "backup", FakeConductor(observation), start + timedelta(minutes=15 * index))
            self.assertEqual(decision["action"], "resume-coordinator", decision)
            advance_once(store, record, tasks, host, now=start + timedelta(minutes=15 * index))
            saved = store.reload(record).value
            self.assertEqual(len([op for op in saved["usage"]["operations"] if op["phase"] == "build"]), 1)
            self.assertFalse(any(op["phase"] in {"diagnosis", "repair", "verify"} for op in saved["usage"]["operations"]))
        self.assertEqual(saved["monitoring"]["state"], "inactive", saved["recovery_disposition"])
        self.assertEqual(saved["recovery_disposition"]["active"]["count"], 3)
        self.assertEqual(len(saved["recovery_disposition"]["notices"]), 1)

    def test_two_slice_first_pr_continues_to_one_next_build(self):
        from delivery_pilot.interim_monitor import reconcile
        from test_interim_monitor import FakeConductor
        approved = self.s2_approval()
        approved["slices"][1]["mode"] = "AFK"
        first = self.task()
        second = deepcopy(first)
        second.update(id="build-task-419", slice_id="TASK-419", candidate_ref="candidate-task-419", base="a" * 40)
        approved["tasks"].append({"id": second["id"], "slice_id": second["slice_id"],
                                  "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(second)})
        approved["hard_limits"] = {"dispatch_max": 6}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        class QueuedHost(PhaseHost):
            def send(self, operation):
                self.sent.append((operation["phase"], operation["slice"], operation["id"]))
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(self, operation):
                self.reconciled.append(operation["id"])
                candidate = {"head": "c" * 40, "base": "a" * 40} if operation["slice"] == "TASK-419" else None
                return Fixture(self.test.result(operation["phase"], candidate)).send(operation)
        host = QueuedHost(self)
        tasks = {"TASK-413": first, "TASK-419": second}
        readbacks = []
        def no_intermediate_readback(*args):
            readbacks.append(args)
            self.fail("intermediate PR must not finish the run")
        self.assertEqual(advance_once(store, record, tasks, host, pr_readback=no_intermediate_readback)["outcome"], "await-worker")
        for phase, next_phase in (("build", "verify"), ("verify", "build")):
            prior = store.reload(record).value
            awaited = next(op for op in prior["usage"]["operations"] if op["phase"] == phase and op["slice"] == "TASK-413")
            where = {"run_id": prior["approval"]["run_id"], "control_ref": prior["monitoring"]["control_ref"],
                     "generation": prior["monitoring"]["pending_wake"]["generation"]}
            observed = {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False,
                        "active_workers": False, "working_ambiguous": False,
                        "awaited_worker": {**{name: awaited[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                           "state": "terminal"}}
            wake_host = FakeConductor(observed)
            wake, decision = reconcile(store, record, where, "backup", wake_host)
            self.assertEqual(decision["action"], "resume-coordinator", decision)
            self.assertEqual(advance_once(store, record, tasks, host, pr_readback=no_intermediate_readback)["outcome"], "await-worker")
            after = store.reload(record).value
            self.assertEqual(after["monitoring"]["state"], "active")
            self.assertEqual(host.sent[-1][:2], (next_phase, "TASK-419" if phase == "verify" else "TASK-413"))
            prior_wake = next(op for op in after["usage"]["operations"] if op["phase"] == "wake" and op["id"] == wake.value["usage"]["operations"][-1]["id"])
            self.assertEqual(prior_wake["status"], "accounted")
            _, duplicate = reconcile(store, record, where, "backup", wake_host)
            self.assertEqual((duplicate["action"], duplicate["reason"]), ("reconcile-coordinator-wake", "stale-settled-wake"))
            self.assertEqual(len(wake_host.send_calls), 1)
        final = store.reload(record).value
        self.assertEqual([item[:2] for item in host.sent], [("build", "TASK-413"), ("verify", "TASK-413"), ("build", "TASK-419")])
        self.assertEqual(len(final["usage"]["launches"]), 6)
        self.assertEqual(readbacks, [])

    def test_crashed_wake_receipt_settles_same_id_before_successor(self):
        from delivery_pilot.interim_monitor import MonitoringPolicyError, reconcile
        from test_interim_monitor import FakeConductor
        store, record, tasks, _ = self._run()
        class QueuedHost(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(self, operation):
                self.reconciled.append(operation["id"])
                return Fixture(self.test.result(operation["phase"])).send(operation)
        host = QueuedHost(self)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "await-worker")
        waiting = store.reload(record).value
        build = next(op for op in waiting["usage"]["operations"] if op["phase"] == "build")
        old = {"run_id": waiting["approval"]["run_id"], "control_ref": waiting["monitoring"]["control_ref"],
               "generation": waiting["monitoring"]["pending_wake"]["generation"]}
        terminal = {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False,
                    "active_workers": False, "working_ambiguous": False,
                    "awaited_worker": {**{name: build[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                       "state": "terminal"}}
        class CrashAfterSend(FakeConductor):
            def send_wake(self, operation):
                self.send_calls.append(deepcopy(operation))
                raise SystemExit("simulated host process crash after send")
        crash = CrashAfterSend(terminal)
        with self.assertRaises(SystemExit):
            reconcile(store, record, old, "backup", crash)
        durable = store.reload(record).value
        old_wake = next(op for op in durable["usage"]["operations"] if op["phase"] == "wake")
        self.assertEqual(old_wake["status"], "reconcile-required")
        with self.assertRaises(MonitoringPolicyError):
            advance_once(store, record, tasks, host)  # no successor before old wake receipt settles
        self.assertEqual(store.reload(record).value["monitoring"]["pending_wake"]["generation"], old["generation"])
        observer = FakeConductor()
        settled, decision = reconcile(store, record, old, "backup", observer)
        self.assertEqual(decision["action"], "reconcile-coordinator-wake", decision)
        old_wake = next(op for op in settled.value["usage"]["operations"] if op["phase"] == "wake")
        self.assertEqual(old_wake["status"], "accounted")
        self.assertEqual(len(crash.send_calls), 1)
        self.assertEqual(observer.send_calls, [])
        self.assertEqual(len(settled.value["usage"]["charges"]), 3)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "await-worker")
        successor = store.reload(record).value
        self.assertNotEqual(successor["monitoring"]["pending_wake"]["generation"], old["generation"])
        verify = next(op for op in successor["usage"]["operations"] if op["phase"] == "verify")
        current = {"run_id": old["run_id"], "control_ref": old["control_ref"],
                   "generation": successor["monitoring"]["pending_wake"]["generation"]}
        verify_terminal = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                         "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                                         "awaited_worker": {**{name: verify[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                                            "state": "terminal"}})
        _, decision = reconcile(store, record, current, "backup", verify_terminal)
        self.assertEqual(decision["action"], "resume-coordinator")

    def test_stop_during_failure_effect_readback_cannot_open_repair(self):
        store, record, tasks, host = self._run()
        def failed_send(operation):
            host.sent.append(operation["id"])
            return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                    "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
        host.send = failed_send
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        def stop_during_read(operation, durable, repository):
            current = store.reload(record)
            store.persist(current, self._stopping(current.value))
            return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                    "ceased": True, "candidate": {"head": "a" * 40, "base": tasks["TASK-413"]["base"]},
                    "branch_head": None, "pr": None,
                    "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40}, "effects_complete": True}
        host.reconcile_failed = stop_during_read
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        saved = store.reload(record).value
        self.assertEqual(saved["recovery"]["status"], "stopping")
        self.assertEqual(len(host.sent), 1)
        self.assertFalse(any(op["phase"] in {"diagnosis", "repair"} for op in saved["usage"]["operations"]))

    def test_final_selected_wake_settles_failure_without_replacement(self):
        from delivery_pilot.interim_monitor import reconcile
        from test_interim_monitor import FakeConductor
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["hard_limits"] = {"dispatch_max": 3}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class Failed(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": None, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40}, "effects_complete": True}
        host = Failed(self)
        tasks = {task["slice_id"]: task}
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "worker-failed")
        failed = store.reload(record).value
        where = {"run_id": failed["approval"]["run_id"], "control_ref": failed["monitoring"]["control_ref"],
                 "generation": failed["monitoring"]["pending_wake"]["generation"]}
        _, decision = reconcile(store, record, where, "backup", FakeConductor())
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "selected-limit")
        saved = store.reload(record).value
        self.assertEqual(saved["monitoring"]["state"], "inactive")
        self.assertEqual(len(saved["usage"]["launches"]), 3)
        self.assertEqual(len(host.sent), 1)
        self.assertIsNotNone(next(op for op in saved["usage"]["operations"] if op["phase"] == "build")["failure_reconciliation"])
        self.assertEqual(len(saved["recovery_disposition"]["notices"]), 1)

    def test_stop_during_final_pr_readback_cannot_publish_review_ready(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["repository"].update(fetch_url="https://github.com/acme/approved.git",
                                      push_url="https://github.com/acme/approved.git", base_ref="refs/heads/main")
        record = initial_record(approved)
        store = self.store(self.first)
        store._assert_approved_target = lambda _: None  # local bare Git CAS fixture
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        tasks = {"TASK-413": self.task()}
        url = "https://github.com/acme/approved/pull/7"
        host = PhaseHost(self, url)
        advance_once(store, record, tasks, host)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "pr-ready")
        def stop_during_read(durable, claimed):
            current = store.reload(record)
            store.persist(current, self._stopping(current.value))
            pr = {"number": 7, "html_url": url, "state": "open",
                  "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
                  "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
            return github_pr_readback(durable, claimed, lambda _: pr)
        self.assertEqual(advance_once(store, record, tasks, host, pr_readback=stop_during_read)["outcome"], "pr-ready")
        saved = store.reload(record).value
        self.assertEqual(saved["recovery"]["status"], "stopping")
        self.assertNotEqual(saved["state"]["next_action"], "review-ready")
        self.assertEqual(len(host.sent), 2)

    def test_failed_diagnosis_is_reconciled_then_retried_with_new_identity(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["forecast"] = {"work_units": 8, "verification_units": 4,
                                "likely_repair_units": 3, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class Host(PhaseHost):
            def __init__(self, test):
                super().__init__(test)
                self.diagnoses = 0
            def send(self, operation):
                self.sent.append(operation["id"])
                if operation["phase"] == "build":
                    return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                            "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                if operation["phase"] == "diagnosis":
                    self.diagnoses += 1
                    if self.diagnoses == 1:
                        return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                                "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                receipt = RepairFixture().send(operation)
                if operation["phase"] == "diagnosis":
                    receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["finding"]["id"]
                return receipt
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": "a" * 40, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40}, "effects_complete": True}
            def preflight_repair_candidate(self, durable, repository, expected):
                pass
        host = Host(self)
        tasks = {task["slice_id"]: task}
        outcomes = [advance_once(store, record, tasks, host)["outcome"] for _ in range(8)]
        final = store.reload(record).value
        self.assertEqual(final["repair"]["status"], "completed", outcomes)
        diagnoses = [op for op in final["usage"]["operations"] if op["phase"] == "diagnosis"]
        self.assertEqual(len(diagnoses), 2)
        self.assertNotEqual(diagnoses[0]["id"], diagnoses[1]["id"])
        self.assertEqual((diagnoses[0]["status"], diagnoses[1]["status"]), ("result-unusable", "result"))

    def test_failed_repair_worker_is_reconciled_before_next_cycle(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["forecast"] = {"work_units": 10, "verification_units": 5,
                                "likely_repair_units": 4, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class Host(PhaseHost):
            def __init__(self, test):
                super().__init__(test)
                self.repairs = 0
            def send(self, operation):
                self.sent.append(operation["id"])
                if operation["phase"] == "build" or operation["phase"] == "repair" and self.repairs == 0:
                    if operation["phase"] == "repair":
                        self.repairs += 1
                    return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                            "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                receipt = RepairFixture().send(operation)
                if operation["phase"] == "diagnosis":
                    receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["finding"]["id"]
                return receipt
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": {"head": "a" * 40, "base": task["base"]},
                        "branch_head": "a" * 40, "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": "a" * 40}, "effects_complete": True}
            def preflight_repair_candidate(self, durable, repository, expected):
                pass
        host = Host(self)
        tasks = {task["slice_id"]: task}
        outcomes = [advance_once(store, record, tasks, host)["outcome"] for _ in range(10)]
        final = store.reload(record).value
        self.assertEqual(final["repair"]["status"], "completed", outcomes)
        repairs = [op for op in final["usage"]["operations"] if op["phase"] == "repair"]
        self.assertEqual(len(repairs), 2)
        self.assertEqual((repairs[0]["status"], repairs[1]["status"]), ("result-unusable", "result"))

    def test_complete_failing_verify_enters_repair_without_erasing_its_verdict(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["forecast"] = {"work_units": 5, "verification_units": 3,
                                "likely_repair_units": 2, "final_handback_units": 1}
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        task = self.task()
        class FailedVerify(PhaseHost):
            def send(self, operation):
                self.sent.append(operation["id"])
                if operation["phase"] in {"diagnosis", "repair", "repair-verify"}:
                    receipt = RepairFixture().send(operation)
                    if operation["phase"] == "diagnosis":
                        receipt["diagnosis"]["next_experiment"]["finding_id"] = operation["repair_context"]["finding"]["id"]
                    return receipt
                receipt = Fixture(self.test.result("verify" if operation["phase"] == "verify" else "build")).send(operation)
                if operation["phase"] == "verify":
                    receipt.update(verdict="fail", criteria={"AC01": "fail"})
                    receipt.pop("handoff")
                return receipt
            def reconcile_failed(self, operation, durable, repository):
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": operation["candidate"], "branch_head": operation["candidate"]["head"],
                        "pr": None, "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": operation["candidate"]["head"]}, "effects_complete": True}
            def preflight_repair_candidate(self, durable, repository, expected):
                pass
        host = FailedVerify(self)
        tasks = {task["slice_id"]: task}
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "verify")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "verify-failed")
        original = store.reload(record).value
        verify = next(op for op in original["usage"]["operations"] if op["phase"] == "verify")
        self.assertEqual((verify["status"], verify["receipt"]["verdict"]), ("result", "fail"))
        for _ in range(4):
            advance_once(store, record, tasks, host)
        final = store.reload(record).value
        self.assertEqual(final["repair"]["status"], "completed")
        retained = next(op for op in final["usage"]["operations"] if op["id"] == verify["id"])
        self.assertEqual(retained["receipt"], verify["receipt"])
        self.assertEqual(retained["failure_reconciliation"]["observation"]["id"], verify["id"])

    def test_process_exit_after_host_acceptance_before_receipt_uses_same_id(self):
        store, record, tasks, host = self._run()
        original = host.send
        def crash_after_send(operation):
            original(operation)
            raise SystemExit(99)
        host.send = crash_after_send
        with self.assertRaises(SystemExit):
            advance_once(store, record, tasks, host)
        pending = store.reload(record).value
        build = next(item for item in pending["usage"]["operations"] if item["phase"] == "build")
        self.assertEqual(build["status"], "intent")
        host.send = lambda operation: self.fail("crashed operation was resent")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "build")
        self.assertEqual(host.reconciled, [build["id"]])
        self.assertEqual(len(store.reload(record).value["usage"]["charges"]), 2)

    def test_concurrent_advance_has_one_dispatch_and_charge(self):
        store, record, tasks, host = self._run()
        second = self.store(self.second)
        second.dispatch_emitter = lambda _: None
        gate = threading.Barrier(2)
        for current in (store, second):
            original = current.reload
            first = [True]
            def racing(value, original=original, first=first):
                snapshot = original(value)
                if first[0]:
                    first[0] = False
                    gate.wait(timeout=10)
                return snapshot
            current.reload = racing
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda current: advance_once(current, record, tasks, host), (store, second)))
        self.assertEqual(len(host.sent), 1)
        self.assertEqual(len(self.store(self.second).reload(record).value["usage"]["charges"]), 2)
        self.assertIn("verify", {item["outcome"] for item in results})

    def test_real_host_adapter_advances_queued_build_and_verify_by_exact_ids(self):
        approved = self.s2_approval()
        approved["coordinator"]["session_id"] = str(uuid4())
        approved["slices"] = approved["slices"][:1]
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        conductor = QueuedConductor(approved, lambda operation: Fixture(self.result("verify" if operation["phase"] == "verify" else "build")).send(operation), store)
        tasks = {"TASK-413": self.task()}
        self.assertEqual(advance_once(store, record, tasks, conductor.adapter)["outcome"], "await-worker")
        build_id = conductor.sent[0]
        conductor.terminal = True
        conductor.reload(store.reload(record))
        self.assertEqual(advance_once(store, record, tasks, conductor.adapter)["outcome"], "await-worker")
        self.assertIn(build_id, conductor.polls)
        conductor.reload(store.reload(record))
        self.assertEqual(len(conductor.sent), 2)
        verify_id = conductor.sent[-1]
        conductor.reload(store.reload(record))
        self.assertEqual(advance_once(store, record, tasks, conductor.adapter,
                                      pr_readback=lambda _, __: {"head": "f" * 40, "base": "b" * 40})["outcome"], "pr-head-or-base-changed")
        self.assertIn(verify_id, conductor.polls, conductor.polls)
        self.assertEqual(len(conductor.sent), 2)

    def test_stop_refuses_new_effect(self):
        store, record, tasks, host = self._run()
        current = store.reload(record)
        stopped = deepcopy(current.value)
        stopped["recovery"] = {"status": "stopping", "wakes": [], "observations": [],
                               "stop": {"intent_at": "2026-09-25T00:00:00Z", "instruction": "stop", "prefix_removed": False,
                                        "cancellations": [], "uncertainty": None}, "resume": None}
        store.persist(current, stopped)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "whole-run-stop")
        self.assertEqual(host.sent, [])

    def test_stop_after_intent_before_send_refuses_worker_effect(self):
        store, record, tasks, host = self._run()
        original = store.reload
        calls = [0]
        def racing(approved):
            calls[0] += 1
            current = original(approved)
            if calls[0] == 2:
                stopped = deepcopy(current.value)
                stopped["recovery"] = {"status": "stopping", "wakes": [], "observations": [],
                                       "stop": {"intent_at": "2026-09-25T00:00:00Z", "instruction": "stop",
                                                "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
                store.persist(current, stopped)
                return original(approved)
            return current
        store.reload = racing
        advance_once(store, record, tasks, host)
        self.assertEqual(host.sent, [])
        self.assertEqual(original(record).value["recovery"]["status"], "stopping")

    def test_stop_during_slow_binding_precedes_send_admission(self):
        store, record, tasks, host = self._run()
        def stop_during_binding(bound_record, operation_id, repository):
            current = store.reload(record)
            store.persist(current, self._stopping(current.value))
        host.bind_worker_hint = stop_during_binding
        result = advance_once(store, record, tasks, host)
        self.assertEqual(result["outcome"], "build")
        self.assertEqual(host.sent, [])
        self.assertEqual(store.reload(record).value["recovery"]["status"], "stopping")

    def test_stop_winning_final_admission_cas_refuses_send(self):
        store, record, tasks, host = self._run()
        original = store.persist_lifecycle
        injected = []
        def stop_before_admission(snapshot, projected):
            if not injected and any(item.get("send_admission") for item in projected["usage"]["operations"]):
                injected.append(True)
                current = store.reload(record)
                store.persist(current, self._stopping(current.value))
            return original(snapshot, projected)
        store.persist_lifecycle = stop_before_admission
        advance_once(store, record, tasks, host)
        self.assertEqual(injected, [True])
        self.assertEqual(host.sent, [])
        self.assertEqual(store.reload(record).value["recovery"]["status"], "stopping")

    def test_stop_after_durable_send_admission_retains_one_in_flight_effect(self):
        store, record, tasks, host = self._run()
        original = host.send
        def stop_after_admission(operation):
            current = store.reload(record)
            admitted = next(item for item in current.value["usage"]["operations"] if item["id"] == operation["id"])
            self.assertEqual(admitted["send_admission"]["operation_id"], operation["id"])
            store.persist(current, self._stopping(current.value))
            return original(operation)
        host.send = stop_after_admission
        advance_once(store, record, tasks, host)
        self.assertEqual(len(host.sent), 1)
        current = store.reload(record).value
        self.assertEqual(current["recovery"]["status"], "stopping")
        self.assertEqual(len(current["usage"]["charges"]), 2)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "whole-run-stop")
        self.assertEqual(len(host.sent), 1)

    def test_github_readback_requires_actual_repo_open_base_and_head(self):
        record = initial_record(self.s2_approval())
        record["approval"]["repository"]["fetch_url"] = "https://github.com/acme/approved.git"
        record["approval"]["repository"]["push_url"] = "https://github.com/acme/approved.git"
        record["approval"]["repository"]["base_ref"] = "refs/heads/main"
        record["approval_digest"] = digest(record["approval"])
        url = "https://github.com/acme/approved/pull/7"
        pr = {"number": 7, "html_url": url, "state": "open", "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
              "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
        self.assertEqual(github_pr_readback(record, url, lambda _: pr)["head"], "a" * 40)
        for change in ({"state": "closed"}, {"base": {"sha": "b" * 40, "ref": "other", "repo": {"full_name": "acme/approved"}}},
                       {"base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/other"}}},
                       {"html_url": "https://github.com/acme/other/pull/7"}):
            with self.subTest(change=change), self.assertRaises(InterimDispatchError):
                github_pr_readback(record, url, lambda _, change=change: {**pr, **change})
        with self.assertRaises(InterimDispatchError):
            github_pr_readback(record, "https://github.com/acme/other/pull/7", lambda _: pr)

    def test_final_open_pr_retires_monitoring_and_survives_clean_reload(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["repository"].update(fetch_url="https://github.com/acme/approved.git",
                                      push_url="https://github.com/acme/approved.git", base_ref="refs/heads/main")
        record = initial_record(approved)
        store = self.store(self.first)
        store._assert_approved_target = lambda _: None  # local bare Git CAS fixture
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        url = "https://github.com/acme/approved/pull/7"
        host = PhaseHost(self, url)
        tasks = {"TASK-413": self.task()}
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "verify")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "pr-ready")
        pr = {"number": 7, "html_url": url, "state": "open",
              "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
              "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
        for mutation in ({"state": "closed"}, {"base": {"sha": "b" * 40, "ref": "other", "repo": {"full_name": "acme/approved"}}},
                         {"head": {"sha": "f" * 40, "repo": {"full_name": "acme/approved"}}}):
            with self.subTest(mutation=mutation):
                if mutation.get("head"):
                    self.assertEqual(advance_once(store, record, tasks, host,
                                     pr_readback=lambda value, claimed, mutation=mutation: github_pr_readback(value, claimed, lambda _: {**pr, **mutation}))["outcome"], "pr-head-or-base-changed")
                else:
                    with self.assertRaises(InterimDispatchError):
                        advance_once(store, record, tasks, host,
                                     pr_readback=lambda value, claimed, mutation=mutation: github_pr_readback(value, claimed, lambda _: {**pr, **mutation}))
                self.assertEqual(store.reload(record).value["state"]["next_action"], "pr-ready")
        result = advance_once(store, record, tasks, host,
                              pr_readback=lambda value, claimed: github_pr_readback(value, claimed, lambda _: pr))
        self.assertEqual(result["outcome"], "review-ready")
        final = store.reload(record).value
        self.assertEqual(final["monitoring"]["state"], "inactive")
        self.assertEqual(validate_record(final)["state"]["handback"]["merge"], "unavailable")
        for key, value in (("head", "f" * 40), ("base_ref", "refs/heads/other"), ("repository", "acme/other")):
            corrupt = deepcopy(final)
            corrupt["state"]["handback"]["pr"][key] = value
            with self.subTest(key=key), self.assertRaises(InterimError):
                validate_record(corrupt)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "review-ready")
        self.assertEqual(len(host.sent), 2)

    @memoized_control_refs
    def test_bound_host_brief_names_candidate_checkout_and_implementation_paths(self):
        store, record, tasks, host = self._run()
        advance_once(store, record, tasks, host)
        current = store.reload(record).value
        operation = next(item for item in current["usage"]["operations"] if item["phase"] == "build")
        captured = []
        def command(argv):
            captured.append(argv)
            return {"id": operation["session_id"], "deepLink": "conductor://session",
                    "initialMessage": {"messageId": operation["message_id"], "state": "queued"}}
        adapter = ConductorHostAdapter("11111111-1111-4111-8111-111111111111", agent="codex",
                                       routes=current["approval"]["routes"], command=command)
        adapter.bind_worker_hint(current, operation["id"], self.first)
        adapter.send(operation)
        brief = captured[0][captured[0].index("--message") + 1]
        self.assertIn(str(self.second.resolve()), brief)
        for path in current["approval"]["implementation_paths"]:
            self.assertIn(path, brief)
        self.assertIn("coordinator checkout is used only", brief)
        self.assertTrue((self.second / ".git").exists())
        for workspaces in ({"coordinator": ".context/unrelated", "candidate": self.second.name},
                           {"coordinator": self.first.name, "candidate": "missing-candidate"}):
            wrong = deepcopy(current)
            wrong["approval"]["workspaces"] = workspaces
            wrong["approval_digest"] = digest(wrong["approval"])
            with self.subTest(workspaces=workspaces), self.assertRaises(InterimDispatchError):
                adapter.bind_worker_hint(wrong, operation["id"], self.first)
        self.git("remote", "set-url", "origin", "https://github.com/acme/unrelated.git", cwd=self.second)
        with self.assertRaises(InterimDispatchError):
            adapter.bind_worker_hint(current, operation["id"], self.first)

    @memoized_control_refs
    def test_bound_candidate_symlink_cannot_escape_shared_workspace_root(self):
        store, record, tasks, host = self._run()
        advance_once(store, record, tasks, host)
        current = store.reload(record).value
        operation = next(item for item in current["usage"]["operations"] if item["phase"] == "build")
        adapter = ConductorHostAdapter("11111111-1111-4111-8111-111111111111", agent="codex",
                                       routes=current["approval"]["routes"], command=lambda _: {})
        adapter.bind_worker_hint(current, operation["id"], self.first)
        self.assertEqual(adapter.worker_hints[operation["id"]][5], self.second.resolve())
        with tempfile.TemporaryDirectory(prefix="public-external-candidate-") as outside:
            external = Path(outside) / "candidate"
            shutil.move(str(self.second), str(external))
            self.second.symlink_to(external, target_is_directory=True)
            try:
                with self.assertRaises(InterimDispatchError):
                    adapter.bind_worker_hint(current, operation["id"], self.first)
            finally:
                self.second.unlink()
                shutil.move(str(external), str(self.second))

    @memoized_control_refs
    def test_bound_verify_send_includes_pr_helper_before_worker_done(self):
        store, record, tasks, host = self._run()
        advance_once(store, record, tasks, host)
        advance_once(store, record, tasks, host)
        current = store.reload(record).value
        operation = next(item for item in current["usage"]["operations"] if item["phase"] == "verify")
        captured = []
        def command(argv):
            captured.append(argv)
            return {"id": operation["session_id"], "deepLink": "conductor://session",
                    "initialMessage": {"messageId": operation["message_id"], "state": "queued"}}
        adapter = ConductorHostAdapter("11111111-1111-4111-8111-111111111111", agent="codex",
                                       routes=current["approval"]["routes"], command=command)
        adapter.bind_worker_hint(current, operation["id"], self.first)
        adapter.send(operation)
        brief = captured[0][captured[0].index("--message") + 1]
        self.assertLess(brief.index("delivery_pilot.interim_pr"), brief.index("delivery_pilot.interim_github"))
        self.assertIn(str(self.second.resolve()), brief)

    def test_intermediate_pr_ready_advances_next_approved_slice(self):
        approved = self.s2_approval()
        approved["slices"][1]["mode"] = "AFK"
        second_task = deepcopy(self.task())
        second_task.update(id="build-task-419", slice_id="TASK-419", candidate_ref="candidate-task-419", base="a" * 40)
        approved["tasks"].append({"id": second_task["id"], "slice_id": second_task["slice_id"],
                                  "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(second_task)})
        record = initial_record(approved)
        store = self.store(self.first)
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        host = PhaseHost(self, candidates={"TASK-419": {"head": "c" * 40, "base": "a" * 40}})
        tasks = {"TASK-413": self.task(), "TASK-419": second_task}
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "verify")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "pr-ready")
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "verify")
        self.assertEqual(store.reload(record).value["state"]["slice_id"], "TASK-419")

    def test_advance_cli_does_not_echo_untrusted_payload(self):
        record_path = self.root / "malformed-record.json"
        task_path = self.root / "tasks.json"
        record_path.write_text('{"payload":"private-sentinel"}')
        task_path.write_text('{"payload":"private-sentinel"}')
        result = subprocess.run([sys.executable, "-m", "delivery_pilot.interim", "advance",
                                 "--repository", str(self.first), "--record", str(record_path),
                                 "--tasks", str(task_path)], text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False,
                                env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("private-sentinel", result.stderr)
        for module in ("delivery_pilot.interim", "delivery_pilot.interim_pr"):
            with self.subTest(module=module):
                args = [sys.executable, "-m", module]
                if module.endswith(".interim"):
                    args.append("advance")
                args.append("--unknown=private-sentinel")
                rejected = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          check=False, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")})
                self.assertEqual(rejected.returncode, 2)
                self.assertNotIn("private-sentinel", rejected.stdout + rejected.stderr)

    def test_lost_pr_create_response_reuses_exact_open_pr(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["repository"].update(fetch_url="https://github.com/acme/approved.git",
                                      push_url="https://github.com/acme/approved.git", base_ref="refs/heads/main")
        record = initial_record(approved)
        store = self.store(self.first)
        store._assert_approved_target = lambda _: None
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        host = PhaseHost(self)
        def queued_verify(operation):
            if operation["phase"] == "verify":
                host.sent.append(operation["id"])
                return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
            return PhaseHost.send(host, operation)
        host.send = queued_verify
        tasks = {"TASK-413": self.task()}
        advance_once(store, record, tasks, host)
        self.assertEqual(advance_once(store, record, tasks, host)["outcome"], "await-worker")
        operation_id = host.sent[-1]
        url = "https://github.com/acme/approved/pull/7"
        pr = {"number": 7, "html_url": url, "state": "open",
              "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
              "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
        created = []
        def api(method, path, payload):
            if "/git/ref/" in path:
                return {"object": {"sha": "a" * 40 if path.endswith("candidate-task-413") else "b" * 40}}
            if path.endswith("/pulls/7"):
                return pr
            if method == "GET":
                return [{"number": 7, "html_url": url}] if created else []
            self.assertEqual(method, "POST")
            durable = store.reload(record).value
            operation = next(item for item in durable["usage"]["operations"] if item["id"] == operation_id)
            self.assertEqual(operation["pr_create_intent"]["head"], "a" * 40)
            # Stop after the durable admission cannot revoke this in-flight POST.
            store.persist(store.reload(record), self._stopping(durable))
            created.append(payload)
            raise TimeoutError("lost response")
        observed = ensure_verify_pr(store, operation_id, api)
        self.assertEqual(observed["url"], url)
        self.assertEqual(ensure_verify_pr(store, operation_id, api), observed)
        self.assertEqual(len(created), 1)
        self.assertEqual(len(store.reload(record).value["usage"]["charges"]), 3)

    def test_stop_winning_pr_admission_cas_refuses_create(self):
        approved = self.s2_approval()
        approved["slices"] = approved["slices"][:1]
        approved["repository"].update(fetch_url="https://github.com/acme/approved.git",
                                      push_url="https://github.com/acme/approved.git", base_ref="refs/heads/main")
        record = initial_record(approved)
        store = self.store(self.first)
        store._assert_approved_target = lambda _: None
        store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
        store.create_and_publish(record)
        host = PhaseHost(self)
        original_send = host.send
        def queued(operation):
            if operation["phase"] == "verify":
                host.sent.append(operation["id"])
                return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
            return original_send(operation)
        host.send = queued
        tasks = {"TASK-413": self.task()}
        advance_once(store, record, tasks, host)
        advance_once(store, record, tasks, host)
        original_persist = store.persist_lifecycle
        def stop_on_admission(snapshot, projected):
            if any("pr_create_intent" in op for op in projected["usage"]["operations"]):
                store.persist(snapshot, self._stopping(snapshot.value))
            return original_persist(snapshot, projected)
        store.persist_lifecycle = stop_on_admission
        posts = []
        def api(method, path, payload):
            if method == "POST":
                posts.append(payload)
                return {}
            if "/git/ref/" in path:
                return {"object": {"sha": "a" * 40 if path.endswith("candidate-task-413") else "b" * 40}}
            return []
        with self.assertRaises(InterimDispatchError):
            ensure_verify_pr(store, host.sent[-1], api)
        self.assertEqual(posts, [])
        self.assertNotIn("pr_create_intent", next(op for op in store.reload(record).value["usage"]["operations"] if op["phase"] == "verify"))


class ControlRefMemoizationTests(unittest.TestCase):
    def test_success_is_reused_but_every_validator_call_still_runs(self):
        original = interim_module._control_ref
        ref = "refs/heads/delivery-control/issue-test-run"
        @memoized_control_refs
        def exercise():
            for _ in range(2):
                self.assertEqual(interim_module._control_ref(ref, "name", "test-run"), ref)
            # The other diagnostic label still runs the complete validator.
            self.assertEqual(interim_module._control_ref(ref, "other", "test-run"), ref)
        with mock.patch.object(interim_module, "_control_ref", wraps=original) as validator:
            with mock.patch.object(subprocess, "run", wraps=subprocess.run) as git:
                exercise()
                self.assertEqual(validator.call_count, 3)
                self.assertEqual(git.call_count, 1)
                exercise()
                self.assertEqual(validator.call_count, 6)
                self.assertEqual(git.call_count, 2)

    def test_real_invalid_refs_and_nonstring_inputs_are_not_cached(self):
        @memoized_control_refs
        def exercise():
            for _ in range(2):
                with self.assertRaisesRegex(InterimError, "not valid Git ref syntax"):
                    interim_module._control_ref("refs/heads/delivery-control/issue-invalid..run", "name", "invalid..run")
                with self.assertRaisesRegex(InterimError, "run-specific"):
                    interim_module._control_ref("refs/heads/other", "name", "test-run")
                for value in ([], {}):
                    with self.assertRaises(InterimError):
                        interim_module._control_ref(value, "name", "test-run")
        with mock.patch.object(subprocess, "run", wraps=subprocess.run) as git:
            exercise()
            self.assertEqual(git.call_count, 2)

    def test_other_commands_options_and_distinct_refs_are_not_reused(self):
        @memoized_control_refs
        def exercise():
            for ref in ("refs/heads/one", "refs/heads/two"):
                for _ in range(2):
                    self.assertEqual(interim_module.subprocess.run(["git", "check-ref-format", ref],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).returncode, 0)
            for _ in range(2):
                interim_module.subprocess.run(["git", "check-ref-format", "refs/heads/one"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, cwd=self.root)
                interim_module.subprocess.run(["git", "--version"], stdout=subprocess.PIPE)
        with tempfile.TemporaryDirectory() as tmp:
            self.root = tmp
            with mock.patch.object(subprocess, "run", wraps=subprocess.run) as git:
                exercise()
                self.assertEqual(git.call_count, 6)

    def test_exception_restores_the_original_subprocess_module(self):
        @memoized_control_refs
        def exercise():
            raise RuntimeError("test failed")
        original = interim_module.subprocess
        with self.assertRaisesRegex(RuntimeError, "test failed"):
            exercise()
        self.assertIs(interim_module.subprocess, original)


if __name__ == "__main__":
    unittest.main()

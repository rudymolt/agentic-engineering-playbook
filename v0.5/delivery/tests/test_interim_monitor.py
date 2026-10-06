from __future__ import annotations

import http.server
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from unittest import mock
from copy import deepcopy
from contextlib import redirect_stdout
from io import StringIO
from datetime import datetime, timedelta, timezone
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from control_ref_test_support import memoized_control_refs  # noqa: E402

from delivery_pilot.interim import InterimCheckpointError, InterimCheckpointStore, initial_record, validate_record  # noqa: E402
from delivery_pilot.interim import main as interim_main  # noqa: E402
from delivery_pilot.git_control import GitControlStore  # noqa: E402
from delivery_pilot.interim_github import (DISPATCH_TYPE, MAX_REGISTERED_REFS, ConductorHttpAdapter, RegisteredRunner,  # noqa: E402
                                            backup_registry, emit_worker_done, http_request, load_event_file, repository_dispatch, worker_done_locator, workflow_dispatch)
from delivery_pilot.interim_monitor import (checkpoint_transition, enroll, generation, persist_checkpoint_transition,
                                            reconcile, resume, retire, start_monitored_run)  # noqa: E402
from delivery_pilot.interim_watchdog import PREFIX, reserve_and_persist  # noqa: E402
from test_interim import approval  # noqa: E402
from test_interim_watchdog import WatchdogFixture  # noqa: E402
import test_interim_coordinator as coordinator_tests  # noqa: E402
from test_interim_coordinator import Fixture  # noqa: E402
from delivery_pilot.interim_coordinator import InterimDispatchError, InterimFixtureCoordinator  # noqa: E402
from delivery_pilot.interim_conductor_host import ConductorHostAdapter  # noqa: E402
from delivery_pilot.interim_repair_coordinator import InterimRepairCoordinator  # noqa: E402
from delivery_pilot.interim_recovery import InterimRecoveryCoordinator  # noqa: E402
from delivery_pilot.interim_advance import advance_once, github_pr_readback  # noqa: E402
from test_interim_recovery import RecoveryFixture  # noqa: E402
import test_interim_repair as repair_tests  # noqa: E402
from test_interim_repair import RepairFixture  # noqa: E402
from delivery_pilot.canonical import digest  # noqa: E402
from delivery_pilot.interim_disposition import ObservationFailure  # noqa: E402
from delivery_pilot.interim_disposition import unresolved as recovery_unresolved  # noqa: E402


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)

class FakeConductor(WatchdogFixture):
    """No network fixture: only existing-coordinator wake calls are observable."""
    def __init__(self, observation=None, **kwargs):
        super().__init__(**kwargs)
        self.monitor_calls = 0
        self.observation = observation or {"current_turn": "interrupted", "pending_messages": False,
                                           "pending_effects": False, "active_workers": False,
                                           "working_ambiguous": False}

    def monitoring_observation(self, record):
        self.monitor_calls += 1
        return deepcopy(self.observation)


class MonitoringTests(unittest.TestCase):
    def test_suppressed_hint_backup_drives_shipped_advance_to_verified_pr(self):
        task = coordinator_tests.CoordinatorTests.task(self)
        item = approval(str(self.remote), str(self.remote))
        item["slices"] = item["slices"][:1]
        item["hard_limits"] = {"dispatch_max": 5}
        item["repository"]["base_ref"] = "refs/heads/main"
        github_remote = "https://github.com/acme/approved.git"
        item["repository"]["fetch_url"] = github_remote
        item["repository"]["push_url"] = github_remote
        for checkout in (self.first, self.second):
            subprocess.run(["git", "remote", "set-url", "origin", github_remote], cwd=checkout, check=True)
            subprocess.run(["git", "config", "--local", f"url.{self.remote}.insteadOf", github_remote], cwd=checkout, check=True)
        # Git's local URL rewrite keeps the disposable transport in /tmp;
        # the approval/readback still names the exact public repository.
        self.store._remote_urls = lambda _push: [github_remote]
        item["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": item["tracker"]["spec_revision"], "digest": digest(task)}]
        approved = initial_record(item)
        self.approval = lambda: item
        start_monitored_run(self.store, approved, self.workspace)
        self.store.dispatch_emitter = lambda _where: None  # lost worker hint; backup is authoritative
        url = "https://github.com/acme/approved/pull/7"
        class Worker:
            def __init__(inner):
                inner.sent, inner.reads = [], []
            def observe_coordinator(inner, operation):
                return Fixture({}).observe_coordinator(operation)
            def send(inner, operation):
                inner.sent.append(operation["id"])
                return Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}).send(operation)
            def reconcile(inner, operation):
                inner.reads.append(operation["id"])
                phase = operation["phase"]
                receipt = Fixture(coordinator_tests.CoordinatorTests.result(self, phase)).send(operation)
                if phase == "verify":
                    receipt["handoff"]["pr"]["url"] = url
                return receipt
        worker = Worker()
        tasks = {task["slice_id"]: task}
        pr = {"number": 7, "html_url": url, "state": "open",
              "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
              "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
        def readback(record, claimed):
            return github_pr_readback(record, claimed, lambda argv: pr)
        self.assertEqual(advance_once(self.store, approved, tasks, worker, pr_readback=readback)["outcome"], "await-worker")
        build_wait = self.store.reload(approved)
        build = next(op for op in build_wait.value["usage"]["operations"] if op["phase"] == "build")
        def terminal(op):
            return FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                  "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                                  "awaited_worker": {**{key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "terminal"}})
        first_wake = terminal(build)
        _, decision = reconcile(self.store, approved, self._where(build_wait), "backup", first_wake, NOW)
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(advance_once(self.store, approved, tasks, worker, pr_readback=readback)["outcome"], "await-worker")
        verify_wait = self.store.reload(approved)
        verify = next(op for op in verify_wait.value["usage"]["operations"] if op["phase"] == "verify")
        second_wake = terminal(verify)
        _, decision = reconcile(self.store, approved, self._where(verify_wait), "backup", second_wake, NOW + timedelta(minutes=15))
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(advance_once(self.store, approved, tasks, worker, pr_readback=readback)["outcome"], "review-ready")
        final = self.store.reload(approved).value
        self.assertEqual(final["state"]["handback"]["pr"]["head"], "a" * 40)
        phases = [op["phase"] for op in final["usage"]["operations"]]
        self.assertEqual((phases.count("build"), phases.count("verify"), phases.count("wake")), (1, 1, 2))
        self.assertEqual(len(final["usage"]["operations"]), len(final["usage"]["charges"]))
        self.assertEqual(len(final["usage"]["launches"]), 5)
        self.assertEqual(advance_once(self.store, approved, tasks, worker, pr_readback=readback)["outcome"], "review-ready")
        self.assertEqual(len(self.store.reload(approved).value["usage"]["launches"]), 5)
        self.assertEqual((len(worker.sent), len(worker.reads), len(first_wake.send_calls), len(second_wake.send_calls)), (2, 2, 1, 1))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name); self.remote = self.root / "remote.git"
        self.first = self.root / "first"; self.second = self.root / "second"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, stdout=subprocess.PIPE)
        for checkout in (self.first, self.second):
            subprocess.run(["git", "clone", "-q", str(self.remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
        item = approval(str(self.remote), str(self.remote))
        item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
        self.approved = initial_record(item)
        self.store = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"])
        self.workspace = "11111111-1111-4111-8111-111111111111"

    def tearDown(self):
        self.temp.cleanup()

    def enrolled(self):
        record = enroll(deepcopy(self.approved), self.workspace)
        return self.store.create_and_publish(record)

    def test_backup_host_outage_has_one_durable_decision_after_three_cycles(self):
        snapshot = self.enrolled()
        where = {"run_id": snapshot.value["approval"]["run_id"],
                 "control_ref": snapshot.value["monitoring"]["control_ref"],
                 "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
        class Down(FakeConductor):
            def monitoring_observation(self, record):
                self.monitor_calls += 1
                raise OSError("host unavailable")
        host = Down()
        for when, count in ((NOW, 1), (NOW + timedelta(minutes=1), 1),
                            (NOW + timedelta(minutes=15), 2), (NOW + timedelta(minutes=30), 3)):
            snapshot, _ = reconcile(self.store, self.approved, where, "backup", host, now=when)
            self.assertEqual(snapshot.value["recovery_disposition"]["active"]["count"], count)
            if snapshot.value["monitoring"]["pending_wake"]:
                where["generation"] = snapshot.value["monitoring"]["pending_wake"]["generation"]
        self.assertEqual(snapshot.value["monitoring"]["state"], "inactive")
        self.assertEqual(len(snapshot.value["recovery_disposition"]["notices"]), 1)
        self.assertEqual(host.monitor_calls, 3)

    def test_selected_limit_retirement_has_one_status_readable_decision_report(self):
        snapshot = self.enrolled()
        report = retire(deepcopy(snapshot.value), "selected-limit-exhausted")
        notice = report["recovery_disposition"]["notices"][0]
        self.assertEqual(notice["cause"], "selected-limit")
        self.assertTrue(notice["happened"] and notice["decision"] and notice["options"])
        self.assertEqual(len(retire(report, "selected-limit-exhausted")["recovery_disposition"]["notices"]), 1)

    def test_http_denied_authority_is_typed_without_provider_prose(self):
        with mock.patch("delivery_pilot.interim_github.urlopen", side_effect=HTTPError("https://example.invalid", 403, "opaque", {}, None)):
            request = http_request("https://example.invalid", "test-token")
            with self.assertRaises(ObservationFailure) as caught:
                request("GET", "/v0/sessions/exact/status", None)
        self.assertEqual(caught.exception.category, "authority-denied")

    def test_http_rate_limit_retry_after_sets_next_eligible_check(self):
        with mock.patch("delivery_pilot.interim_github.urlopen", side_effect=HTTPError("https://example.invalid", 429, "opaque", {"Retry-After": "1200"}, None)):
            request = http_request("https://example.invalid", "test-token")
            with self.assertRaises(ObservationFailure) as caught:
                request("GET", "/v0/sessions/exact/status", None)
        self.assertEqual(caught.exception.category, "transient-outage")
        self.assertGreater(caught.exception.retry_after, datetime.now(timezone.utc) + timedelta(minutes=15))

    def test_http_retry_after_date_is_parsed_from_structured_response(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        from email.utils import format_datetime
        headers = {"Retry-After": format_datetime(future, usegmt=True)}
        with mock.patch("delivery_pilot.interim_github.urlopen", side_effect=HTTPError("https://example.invalid", 503, "opaque", headers, None)):
            request = http_request("https://example.invalid", "test-token")
            with self.assertRaises(ObservationFailure) as caught:
                request("GET", "/v0/sessions/exact/status", None)
        self.assertEqual(caught.exception.category, "transient-outage")
        self.assertGreater(caught.exception.retry_after, datetime.now(timezone.utc) + timedelta(minutes=45))

    def test_local_http_oversized_retry_after_is_typed_in_both_transport_paths(self):
        class RateLimited(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(429)
                self.send_header("Retry-After", "9" * 1000)
                self.end_headers()
            def log_message(self, *_args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RateLimited)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for mode in ("urllib", "deadline"):
                with self.subTest(mode=mode):
                    request = http_request(f"http://127.0.0.1:{server.server_port}", "fixture-token")
                    if mode == "deadline":
                        request.set_event_deadline(time.monotonic() + 5, time.monotonic)
                    with self.assertRaises(ObservationFailure) as caught:
                        request("GET", "/v0/sessions/exact/status", None)
                    self.assertEqual((caught.exception.category, caught.exception.retry_after),
                                     ("transient-outage", None))
            snapshot = self.enrolled()
            where = {"run_id": snapshot.value["approval"]["run_id"],
                     "control_ref": snapshot.value["monitoring"]["control_ref"],
                     "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
            adapter = ConductorHttpAdapter(self.workspace, http_request(f"http://127.0.0.1:{server.server_port}", "fixture-token"))
            saved, _ = reconcile(self.store, self.approved, where, "backup", adapter, now=NOW)
            self.assertEqual(saved.value["recovery_disposition"]["active"]["count"], 1)
            self.assertEqual(saved.value["recovery_disposition"]["active"]["category"], "transient-outage")
        finally:
            server.shutdown()
            server.server_close()

    def test_confirmed_denied_authority_retires_with_one_notice(self):
        snapshot = self.enrolled()
        where = {"run_id": snapshot.value["approval"]["run_id"],
                 "control_ref": snapshot.value["monitoring"]["control_ref"],
                 "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
        class Denied(FakeConductor):
            def monitoring_observation(self, record):
                self.monitor_calls += 1
                raise ObservationFailure("authority-denied")
        host = Denied()
        stopped, _ = reconcile(self.store, self.approved, where, "backup", host, now=NOW)
        self.assertEqual(stopped.value["monitoring"]["state"], "inactive")
        self.assertEqual(stopped.value["recovery_disposition"]["active"]["count"], 1)
        self.assertEqual(stopped.value["recovery_disposition"]["notices"][0]["cause"], "authority-denied")
        again, _ = reconcile(self.store, self.approved, where, "backup", host, now=NOW + timedelta(minutes=15))
        self.assertEqual(len(again.value["recovery_disposition"]["notices"]), 1)
        self.assertEqual(host.monitor_calls, 1)

    def test_local_http_403_has_truthful_immediate_report_on_status(self):
        class Denied(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(403); self.end_headers(); self.wfile.write(b"{}")
            def log_message(self, *_args):
                pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Denied)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            snapshot = self.enrolled()
            where = {"run_id": snapshot.value["approval"]["run_id"],
                     "control_ref": snapshot.value["monitoring"]["control_ref"],
                     "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
            adapter = ConductorHttpAdapter(self.workspace, http_request(f"http://127.0.0.1:{server.server_port}", "fixture-token"))
            stopped, _ = reconcile(self.store, self.approved, where, "backup", adapter, now=NOW)
            notice = stopped.value["recovery_disposition"]["notices"][0]
            reason = stopped.value["state"]["handback"]["reason"]
            self.assertEqual(stopped.value["recovery_disposition"]["active"]["count"], 1)
            self.assertEqual(stopped.value["monitoring"]["state"], "inactive")
            self.assertNotIn("three backup cycles", reason)
            self.assertIn("authority", reason.lower())
            self.assertIn("denied", notice["happened"].lower())
            self.assertNotIn("persisted", notice["happened"].lower())
            self.assertTrue(any("authority" in option.lower() for option in notice["options"]))
            approved_file = self.root / "approved.json"
            approved_file.write_text(json.dumps(self.approved))
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(interim_main(["status", "--repository", str(self.first),
                                               "--record", str(approved_file)]), 0)
            self.assertEqual(json.loads(output.getvalue())["decision_notices"], [notice])
            duplicate, _ = reconcile(self.store, self.approved, where, "backup", adapter, now=NOW + timedelta(minutes=15))
            self.assertEqual(len(duplicate.value["recovery_disposition"]["notices"]), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_all_confirmed_immediate_causes_have_specific_one_check_decisions(self):
        for category, expected in (("authority-denied", "authority"),
                                   ("credentials-revoked", "credential"),
                                   ("missing-session", "session")):
            with self.subTest(category=category):
                record = deepcopy(self.approved)
                operation = record["approval"]["coordinator"]["session_id"]
                self.assertTrue(recovery_unresolved(record, category, operation, NOW))
                notice = record["recovery_disposition"]["notices"][0]
                self.assertEqual(notice["cause"], category)
                self.assertIn(expected, notice["happened"].lower())
                self.assertIn(expected, " ".join(notice["options"]).lower())
                self.assertNotIn("persisted", notice["happened"])
                self.assertEqual(notice["remains"], [operation])

    def test_same_operation_changed_observation_category_keeps_unresolved_count(self):
        snapshot = self.enrolled()
        where = {"run_id": snapshot.value["approval"]["run_id"],
                 "control_ref": snapshot.value["monitoring"]["control_ref"],
                 "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
        class Alternating(FakeConductor):
            categories = iter(("ambiguous-missing-session", "transient-outage", "uncertain-effect"))
            def monitoring_observation(self, record):
                self.monitor_calls += 1
                raise ObservationFailure(next(self.categories))
        host = Alternating()
        for minutes, count in ((0, 1), (15, 2), (30, 3)):
            snapshot, _ = reconcile(self.store, self.approved, where, "backup", host, now=NOW + timedelta(minutes=minutes))
            self.assertEqual(snapshot.value["recovery_disposition"]["active"]["count"], count)
            if snapshot.value["monitoring"]["pending_wake"]:
                where["generation"] = snapshot.value["monitoring"]["pending_wake"]["generation"]
        self.assertEqual(snapshot.value["monitoring"]["state"], "inactive")
        self.assertEqual(snapshot.value["recovery_disposition"]["notices"][0]["cause"], "uncertain-effect")

    def test_repeated_exact_missing_session_becomes_definitive_decision(self):
        snapshot = self.enrolled()
        where = {"run_id": snapshot.value["approval"]["run_id"],
                 "control_ref": snapshot.value["monitoring"]["control_ref"],
                 "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}
        class Missing(FakeConductor):
            def monitoring_observation(self, record):
                raise ObservationFailure("ambiguous-missing-session")
        host = Missing()
        first, _ = reconcile(self.store, self.approved, where, "backup", host, now=NOW)
        self.assertEqual(first.value["monitoring"]["state"], "active")
        where["generation"] = first.value["monitoring"]["pending_wake"]["generation"]
        second, _ = reconcile(self.store, self.approved, where, "backup", host, now=NOW + timedelta(minutes=15))
        self.assertEqual(second.value["monitoring"]["state"], "inactive")
        self.assertEqual(second.value["recovery_disposition"]["notices"][0]["cause"], "missing-session")

    def test_queued_worker_observation_clears_prior_unresolved_cycle(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        where = self._where(pending)
        class Down(FakeConductor):
            def monitoring_observation(self, record):
                raise OSError("temporary")
        failed, _ = reconcile(self.store, approved, where, "backup", Down(), now=NOW)
        self.assertEqual(failed.value["recovery_disposition"]["active"]["count"], 1)
        where = self._where(failed)
        identity = {name: op[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        queued = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                "pending_effects": False, "active_workers": False,
                                "working_ambiguous": False, "awaited_worker": {**identity, "state": "queued"}})
        observed, result = reconcile(self.store, approved, where, "backup", queued, now=NOW + timedelta(minutes=15))
        self.assertIsNone(observed.value["recovery_disposition"]["active"])
        self.assertEqual(result["reason"], "awaited-worker-still-running")
        self.assertEqual(queued.send_calls, [])

    def test_exact_unknown_worker_observation_spends_backup_cycle_after_outage(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        class Down(FakeConductor):
            def monitoring_observation(self, record):
                raise ObservationFailure("transient-outage")
        first, _ = reconcile(self.store, approved, self._where(pending), "backup", Down(), now=NOW)
        identity = {name: op[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        unknown = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                 "pending_effects": False, "active_workers": False,
                                 "working_ambiguous": False, "awaited_worker": {**identity, "state": "unknown"}})
        second, _ = reconcile(self.store, approved, self._where(first), "backup", unknown,
                              now=NOW + timedelta(minutes=15))
        self.assertEqual(second.value["recovery_disposition"]["active"]["count"], 2)
        third, _ = reconcile(self.store, approved, self._where(second), "backup", unknown,
                             now=NOW + timedelta(minutes=30))
        self.assertEqual(third.value["recovery_disposition"]["active"]["count"], 3)
        self.assertEqual(third.value["monitoring"]["state"], "inactive")
        self.assertEqual(unknown.send_calls, [])

    def test_unconfirmed_stop_cancellation_remains_monitored_for_bounded_recheck(self):
        approved, _, pending, _ = self._awaiting_build()
        operation = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        projected = deepcopy(pending.value)
        projected["recovery"] = {"status": "uncertain", "wakes": [], "observations": [],
                                  "stop": {"intent_at": "2026-09-21T00:00:00Z", "instruction": "Stop",
                                           "prefix_removed": True, "cancellations": [],
                                           "uncertainty": "cancellation response unavailable"}, "resume": None}
        uncertain = self.store.persist_lifecycle(pending, projected)
        self.assertEqual(uncertain.value["monitoring"]["state"], "active")
        class Unavailable(FakeConductor):
            def observe(self, item):
                self.monitor_calls += 1
                self.assert_same = item["id"] == operation["id"]
                raise ObservationFailure("unconfirmed-cancellation")
        host = Unavailable()
        for minutes, count in ((0, 1), (15, 2), (30, 3)):
            uncertain, _ = reconcile(self.store, approved, self._where(uncertain), "backup", host,
                                     now=NOW + timedelta(minutes=minutes))
            self.assertEqual(uncertain.value["recovery_disposition"]["active"]["count"], count)
        self.assertEqual(uncertain.value["monitoring"]["state"], "inactive")
        self.assertEqual(uncertain.value["recovery_disposition"]["notices"][0]["cause"], "unconfirmed-cancellation")
        self.assertTrue(host.assert_same)

    def test_terminal_worker_observation_clears_prior_unresolved_cycle(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        class Down(FakeConductor):
            def monitoring_observation(self, record):
                raise OSError("temporary")
        failed, _ = reconcile(self.store, approved, self._where(pending), "backup", Down(), now=NOW)
        identity = {name: op[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        terminal = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                  "pending_effects": False, "active_workers": False,
                                  "working_ambiguous": False, "awaited_worker": {**identity, "state": "terminal"}})
        observed, decision = reconcile(self.store, approved, self._where(failed), "backup", terminal,
                                       now=NOW + timedelta(minutes=15))
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertIsNone(observed.value["recovery_disposition"]["active"])

    def _awaiting_build(self, repair=False):
        task = coordinator_tests.CoordinatorTests.task(self)
        item = approval(str(self.remote), str(self.remote))
        if repair:
            item["forecast"] = {"work_units": 12, "verification_units": 12,
                                "likely_repair_units": 12, "final_handback_units": 1}
        item["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"],
                          "spec_revision": item["tracker"]["spec_revision"], "digest": digest(task)}]
        approved = initial_record(item)
        root = start_monitored_run(self.store, approved, self.workspace)
        queued = {"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                  "task_success": False, "elapsed_seconds": 0}
        build = Fixture(queued)
        pending = InterimFixtureCoordinator(self.store).run_one(root, "TASK-413", task, build, Fixture(queued))
        return approved, task, pending, build

    def _fresh_task_run(self, hard_limits=None, workspaces=None):
        task = coordinator_tests.CoordinatorTests.task(self)
        item = approval(str(self.remote), str(self.remote))
        if hard_limits is not None:
            item["hard_limits"] = hard_limits
        if workspaces is not None:
            item["workspaces"] = workspaces
        item["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"],
                          "spec_revision": item["tracker"]["spec_revision"], "digest": digest(task)}]
        approved = initial_record(item)
        self.approval = lambda: item
        return approved, task, start_monitored_run(self.store, approved, self.workspace)

    def test_build_send_exception_waits_and_reconciles_same_operation(self):
        approved, task, root = self._fresh_task_run()
        class LostSend(Fixture):
            sends = 0
            reads = 0
            def send(self, operation):
                self.sends += 1
                raise InterimDispatchError("host command response unavailable")
            def reconcile(self, operation):
                self.reads += 1
                if self.reads == 1:
                    raise OSError("temporary host read failure")
                return Fixture.send(self, operation)
        build = LostSend(coordinator_tests.CoordinatorTests.result(self))
        coordinator = InterimFixtureCoordinator(self.store)
        waiting = coordinator.run_one(root, "TASK-413", task, build, Fixture(coordinator_tests.CoordinatorTests.result(self, "verify")))
        operation = next(op for op in waiting.value["usage"]["operations"] if op["phase"] == "build")
        self.assertEqual((waiting.value["state"]["next_action"], waiting.value["state"]["operation_id"],
                          waiting.value["monitoring"]["state"], operation["status"]),
                         ("await-worker", operation["id"], "active", "intent"))
        self.assertIsNotNone(waiting.value["monitoring"]["pending_wake"])
        still_waiting = coordinator.reconcile_pending(waiting, operation["id"], build)
        self.assertEqual((still_waiting.value["state"]["next_action"],
                          still_waiting.value["recovery_disposition"]["active"]["count"]),
                         ("await-worker", 1))
        self.assertNotEqual(still_waiting.value["monitoring"]["pending_wake"]["generation"],
                            waiting.value["monitoring"]["pending_wake"]["generation"])
        completed = coordinator.reconcile_pending(still_waiting, operation["id"], build)
        self.assertEqual((completed.value["state"]["next_action"], build.sends,
                          len([item for item in completed.value["usage"]["launches"] if item["operation_id"] == operation["id"]])),
                         ("build", 1, 1))
        final = coordinator.run_one(completed, "TASK-413", task, build, Fixture(coordinator_tests.CoordinatorTests.result(self, "verify")))
        self.assertEqual(final.value["state"]["next_action"], "pr-ready")
        self.assertEqual(len([item for item in final.value["usage"]["charges"] if item["operation_id"] == operation["id"]]), 1)

    def test_verify_transport_exception_waits_and_reconciles_same_operation(self):
        approved, task, root = self._fresh_task_run()
        class LostSend(Fixture):
            sends = 0
            def send(self, operation):
                self.sends += 1
                raise TimeoutError("host response lost")
            def reconcile(self, operation):
                return Fixture.send(self, operation)
        build = Fixture(coordinator_tests.CoordinatorTests.result(self))
        verify = LostSend(coordinator_tests.CoordinatorTests.result(self, "verify"))
        coordinator = InterimFixtureCoordinator(self.store)
        waiting = coordinator.run_one(root, "TASK-413", task, build, verify)
        operation = next(op for op in waiting.value["usage"]["operations"] if op["phase"] == "verify")
        self.assertEqual((waiting.value["state"]["next_action"], waiting.value["state"]["operation_id"],
                          waiting.value["monitoring"]["state"], operation["status"]),
                         ("await-worker", operation["id"], "active", "intent"))
        completed = coordinator.reconcile_pending(waiting, operation["id"], verify)
        final = coordinator.run_one(completed, "TASK-413", task, build, verify)
        self.assertEqual((final.value["state"]["next_action"], verify.sends,
                          len([item for item in final.value["usage"]["launches"] if item["operation_id"] == operation["id"]])),
                         ("pr-ready", 1, 1))

    def test_verify_error_binds_failed_boundary_and_deadline_retires(self):
        approved, task, root = self._fresh_task_run({"deadline_at": "2026-09-21T00:01:00Z", "dispatch_max": 5})
        early = datetime(2026, 9, 21, tzinfo=timezone.utc)
        late = datetime(2026, 9, 21, 0, 2, tzinfo=timezone.utc)
        coordinator = InterimFixtureCoordinator(self.store, clock=lambda: early)
        build = Fixture(coordinator_tests.CoordinatorTests.result(self))
        queued = Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                          "task_success": False, "elapsed_seconds": 0})
        waiting = coordinator.run_one(root, "TASK-413", task, build, queued)
        operation = next(item for item in waiting.value["usage"]["operations"] if item["phase"] == "verify")
        queued.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                         "task_success": False, "elapsed_seconds": 0}
        failed = coordinator.reconcile_pending(waiting, operation["id"], queued)
        self.assertNotEqual(self._where(waiting)["generation"], self._where(failed)["generation"])
        retired, limit = reconcile(self.store, approved, self._where(failed), "backup", FakeConductor(), late)
        self.assertEqual((limit["reason"], retired.value["monitoring"]["state"]),
                         ("selected-limit-exhausted", "inactive"))

    def test_send_exception_crossing_selected_deadline_keeps_cancellation_guard(self):
        approved, task, root = self._fresh_task_run({"deadline_at": "2026-09-21T00:01:00Z", "dispatch_max": 5})
        clock = [datetime(2026, 9, 21, 0, 0, tzinfo=timezone.utc)]
        class LostSend(Fixture):
            def send(self, operation):
                clock[0] = datetime(2026, 9, 21, 0, 2, tzinfo=timezone.utc)
                raise TimeoutError("send outcome unknown")
        build = LostSend(coordinator_tests.CoordinatorTests.result(self))
        ended = InterimFixtureCoordinator(self.store, clock=lambda: clock[0]).run_one(
            root, "TASK-413", task, build, Fixture(coordinator_tests.CoordinatorTests.result(self, "verify")))
        operation = next(item for item in ended.value["usage"]["operations"] if item["phase"] == "build")
        self.assertEqual((ended.value["state"]["next_action"], ended.value["monitoring"]["state"],
                          operation["status"], operation["cancellation_intent"]["reason"]),
                         ("handback", "inactive", "unfinished-cancelled", "selected deadline reached"))

    def test_queued_build_waits_for_exact_turn_then_one_wake(self):
        approved, task, pending, build = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        self.assertEqual((pending.value["state"]["next_action"], pending.value["state"]["operation_id"],
                          pending.value["monitoring"]["state"]), ("await-worker", op["id"], "active"))
        self.assertEqual(len(build.operations), 1)
        where = self._where(pending)
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        for state in ("queued", "active", "unknown"):
            fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                  "pending_effects": False, "active_workers": False,
                                  "working_ambiguous": False, "awaited_worker": {**identity, "state": state}})
            observed, refused = reconcile(self.store, approved, where, "backup", fake, NOW)
            self.assertEqual((refused["action"], len(fake.send_calls)), ("refuse", 0))
            where = self._where(observed)
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False,
                              "working_ambiguous": False, "awaited_worker": {**identity, "state": "terminal"}})
        woken, decision = reconcile(self.store, approved, where, "event", fake, NOW + timedelta(minutes=15))
        self.assertEqual((decision["action"], len(fake.send_calls)), ("resume-coordinator", 1))
        duplicate, again = reconcile(self.store, approved, where, "backup", fake, NOW)
        self.assertEqual((again["action"], len(fake.send_calls)), ("reconcile-coordinator-wake", 1))
        self.assertEqual(len([op for op in duplicate.value["usage"]["operations"] if op["phase"] == "wake"]), 1)
        self.approval = lambda: approved["approval"]
        build.result = coordinator_tests.CoordinatorTests.result(self)
        coordinator = InterimFixtureCoordinator(self.store)
        completed = coordinator.reconcile_pending(duplicate, op["id"], build)
        self.assertEqual((completed.value["state"]["next_action"],
                          next(item for item in completed.value["usage"]["operations"] if item["id"] == op["id"])["status"]),
                         ("build", "reconciled"))
        verified = coordinator.run_one(completed, "TASK-413", task, build, Fixture(coordinator_tests.CoordinatorTests.result(self, "verify")))
        self.assertEqual(verified.value["state"]["next_action"], "pr-ready")

    def test_exact_worker_error_is_retained_once_without_completion(self):
        approved, task, pending, build = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False,
                              "working_ambiguous": False, "awaited_worker": {**identity, "state": "error"}})
        where = self._where(pending)
        woken, decision = reconcile(self.store, approved, where, "event", fake, NOW)
        self.assertEqual(decision["action"], "resume-coordinator")
        build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                        "task_success": False, "elapsed_seconds": 0}
        coordinator = InterimFixtureCoordinator(self.store)
        failed = coordinator.reconcile_pending(woken, op["id"], build)
        self.assertEqual((failed.value["state"]["next_action"], failed.value["usage"]["operations"][1]["status"]),
                         ("worker-failed", "result-unusable"))
        self.assertEqual(len(failed.value["usage"]["launches"]), 3)
        self.assertNotEqual(failed.value["monitoring"]["pending_wake"]["generation"],
                            woken.value["monitoring"]["pending_wake"]["generation"])
        failed_where = self._where(failed)
        wake_host = FakeConductor()
        check, decision = reconcile(self.store, approved, failed_where, "backup", wake_host, NOW)
        self.assertEqual(decision["action"], "resume-coordinator")
        duplicate_tick, duplicate_decision = reconcile(self.store, approved, failed_where, "event", wake_host, NOW)
        self.assertEqual(duplicate_decision["action"], "reconcile-coordinator-wake")
        self.assertEqual(len(wake_host.send_calls), 1)
        with self.assertRaises(Exception):
            coordinator.reconcile_pending(failed, op["id"], build)
        self.assertEqual(len(self.store.reload(approved).value["usage"]["operations"]),
                         len(failed.value["usage"]["operations"]) + 1)  # one charged recovery wake

    def test_host_requires_awaited_message_turn_and_error_is_explicit(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        def message(message_id, turn_id, state="sent"):
            return {"id": "item-" + message_id, "sessionId": op["session_id"], "sessionIndex": 0,
                    "type": "userMessage", "receivedAt": "2026-09-21T00:00:00Z",
                    "content": {"id": message_id, "turnId": turn_id, "state": state}}
        def completion(message_id, turn_id):
            return {"id": "done-" + message_id, "sessionId": op["session_id"], "sessionIndex": 1,
                    "type": "agent", "receivedAt": "2026-09-21T00:00:01Z",
                    "content": {"userMessageId": message_id, "turnId": turn_id,
                                "rawPayload": {"event": {"type": "turn.completed"}}}}
        status = "idle"
        records = [message(op["message_id"], op["terminal_turn_id"])]
        def request(method, path, body):
            if method == "POST":
                raise AssertionError("observation must not send")
            session_id = path.split("/")[3]
            if path.endswith("/status"):
                return {"workspaceId": self.workspace, "sessionId": session_id,
                        "status": status if session_id == op["session_id"] else "idle",
                        "updatedAt": "2026-09-21T00:00:00Z"}
            return {"data": deepcopy(records if session_id == op["session_id"] else []),
                    "offset": 0, "hasMore": False}
        adapter = ConductorHttpAdapter(self.workspace, request)
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "unknown")
        self.assertFalse(adapter.monitoring_observation(pending.value)["active_workers"])
        records.append(completion("other-message", "other-turn"))
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "unknown")
        records[-1] = completion(op["message_id"], op["terminal_turn_id"])
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "terminal")
        status = "working"
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "active")
        records.pop(); status = "error"
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "error")
        records.clear(); status = "idle"
        self.assertEqual(adapter.monitoring_observation(pending.value)["awaited_worker"]["state"], "unknown")

    def test_awaited_worker_unavailable_fails_closed_and_backup_can_retry(self):
        approved, _, pending, _ = self._awaiting_build()
        where = self._where(pending)
        unavailable = FakeConductor()
        unavailable.monitoring_observation = lambda _: (_ for _ in ()).throw(OSError("host unavailable"))
        _, decision = reconcile(self.store, approved, where, "event", unavailable, NOW)
        self.assertEqual((decision["action"], len(unavailable.send_calls)), ("refuse", 0))
        self.assertEqual(self.store.reload(approved).value["monitoring"]["state"], "active")

    def test_early_event_rechecks_exact_worker_then_one_backup_duplicate(self):
        approved, _, pending, _ = self._awaiting_build()
        where = self._where(pending)
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        clock = [0.0]; sleeps = []
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                              "awaited_worker": {**identity, "state": "active"}})
        def sleep(seconds):
            sleeps.append(seconds); clock[0] += seconds
            fake.observation["awaited_worker"]["state"] = "terminal"
        woken, decision = reconcile(self.store, approved, where, "event", fake, NOW,
                                    monotonic=lambda: clock[0], sleep=sleep)
        duplicate, again = reconcile(self.store, approved, where, "backup", FakeConductor(), NOW)
        wakes = [item for item in duplicate.value["usage"]["operations"] if item["phase"] == "wake"]
        self.assertEqual((decision["action"], again["action"], sleeps, fake.monitor_calls,
                          len(fake.send_calls), len(wakes)),
                         ("resume-coordinator", "reconcile-coordinator-wake", [20], 2, 1, 1))

    def test_registered_event_runner_rechecks_then_wakes_one_exact_worker(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                              "awaited_worker": {**identity, "state": "active"}})
        clock = [0.0]
        def sleep(seconds):
            clock[0] += seconds
            fake.observation["awaited_worker"]["state"] = "terminal"
        runner = RegisteredRunner(self.first, "origin", lambda _workspace: fake,
                                  monotonic=lambda: clock[0], sleep=sleep)
        first = runner.one(self._where(pending), "event", NOW)
        second = runner.one(self._where(pending), "backup", NOW)
        self.assertEqual((first["action"], second["action"], clock[0], fake.monitor_calls,
                          len(fake.send_calls)),
                         ("resume-coordinator", "reconcile-coordinator-wake", 20, 3, 1))

    def test_event_recheck_exhaustion_and_slow_host_observation(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        active = {"current_turn": "interrupted", "pending_messages": False,
                  "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                  "awaited_worker": {**identity, "state": "active"}}
        fake = FakeConductor(active); elapsed = [0.0]
        _, refusal = reconcile(self.store, approved, self._where(pending), "event", fake, NOW,
                               monotonic=lambda: elapsed[0], sleep=lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
        self.assertEqual((refusal["reason"], fake.monitor_calls, elapsed[0], len(fake.send_calls)),
                         ("awaited-worker-still-running", 5, 80, 0))
        slow = FakeConductor({**active, "awaited_worker": {**identity, "state": "terminal"}})
        original = slow.monitoring_observation
        def observe(record):
            result = original(record); elapsed[0] += 121; return result
        slow.monitoring_observation = observe
        _, late = reconcile(self.store, approved, self._where(pending), "event", slow, NOW,
                            monotonic=lambda: elapsed[0], sleep=lambda _: self.fail("slow observation must not sleep"))
        self.assertEqual((late["reason"], len(slow.send_calls)), ("event-recheck-time-exhausted", 0))

    def test_recheck_reloads_stop_stale_generation_and_selected_deadline(self):
        for changed in ("stop", "stale", "deadline"):
            with self.subTest(changed=changed):
                self.tearDown(); self.setUp()
                limits = {"deadline_at": "2026-09-21T00:00:10Z", "dispatch_max": 5} if changed == "deadline" else None
                approved, _, pending = self._fresh_task_run(limits)
                task = coordinator_tests.CoordinatorTests.task(self)
                queued = Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                  "task_success": False, "elapsed_seconds": 0})
                pending = InterimFixtureCoordinator(self.store, clock=lambda: NOW).run_one(pending, "TASK-413", task, queued, queued)
                where = self._where(pending)
                op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
                identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
                fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                                      "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                                      "awaited_worker": {**identity, "state": "active"}})
                elapsed = [0.0]
                def sleep(seconds):
                    elapsed[0] += seconds
                    if changed == "stop":
                        self.store.persist(pending, retire(deepcopy(pending.value), "human-stop"))
                    elif changed == "stale":
                        persist_checkpoint_transition(self.store, pending, "new-boundary")
                _, result = reconcile(self.store, approved, where, "event", fake,
                                      monotonic=lambda: elapsed[0], sleep=sleep,
                                      wall_clock=lambda: NOW + timedelta(seconds=elapsed[0]))
                self.assertEqual(len(fake.send_calls), 0)
                self.assertEqual(result["reason"], {"stop": "monitoring-inactive", "stale": "stale-or-unknown-generation",
                                                    "deadline": "selected-limit-exhausted"}[changed])

    def test_selected_deadline_crossed_during_terminal_host_read_refuses_before_wake(self):
        approved, task, root = self._fresh_task_run({"deadline_at": "2026-09-21T00:00:10Z", "dispatch_max": 5})
        queued = Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                          "task_success": False, "elapsed_seconds": 0})
        pending = InterimFixtureCoordinator(self.store, clock=lambda: NOW).run_one(root, "TASK-413", task, queued, queued)
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                              "awaited_worker": {**identity, "state": "terminal"}})
        elapsed = [0.0]
        original = fake.monitoring_observation
        def slow_observation(record):
            observed = original(record); elapsed[0] = 11; return observed
        fake.monitoring_observation = slow_observation
        ended, decision = reconcile(self.store, approved, self._where(pending), "event", fake,
                                    monotonic=lambda: elapsed[0], sleep=lambda _: self.fail("terminal host must not poll"),
                                    wall_clock=lambda: NOW + timedelta(seconds=elapsed[0]))
        self.assertEqual((decision["action"], decision["reason"], len(fake.send_calls),
                          ended.value["monitoring"]["state"]),
                         ("refuse", "selected-limit-exhausted", 0, "inactive"))

    def test_stop_published_during_terminal_host_read_wins_cas_before_wake(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        fake = FakeConductor({"current_turn": "interrupted", "pending_messages": False,
                              "pending_effects": False, "active_workers": False, "working_ambiguous": False,
                              "awaited_worker": {**identity, "state": "terminal"}})
        original = fake.monitoring_observation
        def stop_during_read(record):
            observed = original(record)
            self.store.persist(pending, retire(deepcopy(pending.value), "human-stop"))
            return observed
        fake.monitoring_observation = stop_during_read
        ended, _ = reconcile(self.store, approved, self._where(pending), "event", fake, NOW)
        self.assertEqual((len(fake.send_calls), ended.value["monitoring"]["state"]), (0, "inactive"))

    def test_event_deadline_blocks_new_paginated_transport_read(self):
        elapsed = [0.0]; calls = []
        def request(method, path, body):
            calls.append(path); elapsed[0] += 2
            return {"data": [{"id": "event-" + str(len(calls)), "sessionId": "session-1",
                              "sessionIndex": len(calls), "type": "agent", "content": {}, "receivedAt": "now"}],
                    "offset": 0, "hasMore": True}
        host = ConductorHttpAdapter(self.workspace, request)
        host.set_event_deadline(5, lambda: elapsed[0])
        with self.assertRaises(TimeoutError):
            host._transcript("session-1")
        self.assertEqual((len(calls), elapsed[0]), (3, 6))

    def test_real_http_boundary_uses_remaining_event_budget(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.wfile.write(b"HTTP/1.1 200 OK\r\n"); self.wfile.flush()
                try:
                    for byte in b"Content-Type: application/json\r\nContent-Length: 2\r\n\r\n{}":
                        self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(.015)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *_args): pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            request = http_request(f"http://127.0.0.1:{server.server_port}", "fixture-only-token", timeout=.05)
            start = time.monotonic()
            request.set_event_deadline(start + .08, time.monotonic)
            with self.assertRaises(OSError):
                request("GET", "/v0/sessions/one/status", None)
            elapsed = time.monotonic() - start
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertLess(elapsed, .5)

    def test_worker_done_hint_uses_current_registered_generation_and_is_silent_on_failure(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        self.assertEqual(worker_done_locator(self.first, "origin", approved["approval"]["run_id"],
                                             approved["approval"]["checkpoint"]["ref"], op["id"]), self._where(pending))
        self.assertIsNone(worker_done_locator(self.first, "origin", "wrong-run",
                                              approved["approval"]["checkpoint"]["ref"], op["id"]))
        with mock.patch("delivery_pilot.interim_github.subprocess.run", side_effect=OSError("no gh")):
            emit_worker_done(self.first, "origin", approved["approval"]["run_id"],
                             approved["approval"]["checkpoint"]["ref"], op["id"])

    def test_registered_coordinator_brief_executes_locator_only_dispatch_with_existing_gh(self):
        # The fake Git transport reports a GitHub approval URL while routing
        # checkpoint I/O to the local bare remote. The emitted command itself
        # runs from another cwd with no installed package or GitHub token.
        bin_dir = self.root / "bin"; bin_dir.mkdir()
        git = bin_dir / "git"; gh = bin_dir / "gh"; payload_file = self.root / "dispatch.json"
        real_git = shutil.which("git")
        git.write_text("#!/bin/sh\nif [ \"$1\" = remote ] && [ \"$2\" = get-url ]; then\n"
                       "  printf '%s\\n' 'https://github.com/acme/playbook.git'\nelse\n"
                       f"  exec {shlex.quote(real_git)} \"$@\"\nfi\n")
        gh.write_text("#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\n"
                      f"Path({str(payload_file)!r}).write_text(json.dumps({{'argv':sys.argv[1:],'payload':sys.stdin.read()}}))\n")
        git.chmod(0o755); gh.chmod(0o755)
        path = str(bin_dir) + os.pathsep + os.environ["PATH"]
        subprocess.run([real_git, "remote", "add", "control", str(self.remote)],
                       cwd=self.first, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run([real_git, "remote", "add", "control", str(self.remote)],
                       cwd=self.second, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.store = InterimCheckpointStore(self.first, "control", self.approved["approval"]["checkpoint"]["ref"])
        task = coordinator_tests.CoordinatorTests.task(self)
        item = approval("https://github.com/acme/playbook.git", "https://github.com/acme/playbook.git")
        item["repository"]["remote"] = "control"
        item["workspaces"] = {"coordinator": self.first.name, "candidate": self.second.name}
        item["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"],
                          "spec_revision": item["tracker"]["spec_revision"], "digest": digest(task)}]
        approved = initial_record(item)
        calls = []
        def command(argv):
            calls.append(argv)
            if argv[:2] == ["session", "create"]:
                session_id = argv[argv.index("--session-id") + 1]
                message_id = argv[argv.index("--message-id") + 1]
                return {"id": session_id, "deepLink": "conductor://session",
                        "initialMessage": {"messageId": message_id, "state": "queued", "deepLink": "conductor://message"}}
            raise AssertionError("unexpected host command")
        host = ConductorHostAdapter(self.workspace, agent="codex",
                                    routes={"build": {"model": item["routes"]["build"]["model"],
                                                      "effort": item["routes"]["build"]["effort"]}}, command=command)
        with mock.patch.dict(os.environ, {"PATH": path}):
            root = start_monitored_run(self.store, approved, self.workspace)
            pending = InterimFixtureCoordinator(self.store).run_one(root, "TASK-413", task, host,
                         Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                                  "task_success": False, "elapsed_seconds": 0}),
                         coordinator=Fixture({}))
            self.assertEqual(pending.value["state"]["next_action"], "await-worker")
            brief = calls[0][-1]
            self.assertEqual(brief.count("worker-done"), 1)
            self.assertIn("--remote control", brief)
            self.assertNotIn("GITHUB_TOKEN", brief)
            worker_command = brief.split("run exactly once: `", 1)[1].split("`", 1)[0]
            outside = self.root / "worker"; outside.mkdir()
            executed = subprocess.run(worker_command, shell=True, cwd=outside, env=dict(os.environ),
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            gh.write_text("#!/usr/bin/env python3\nraise SystemExit(1)\n"); gh.chmod(0o755)
            failed_hint = subprocess.run(worker_command, shell=True, cwd=outside, env=dict(os.environ),
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual((executed.returncode, executed.stdout, executed.stderr), (0, "", ""))
        self.assertEqual((failed_hint.returncode, failed_hint.stdout, failed_hint.stderr), (0, "", ""))
        sent = json.loads(payload_file.read_text())
        self.assertEqual(sent["argv"], ["api", "--method", "POST", "repos/acme/playbook/dispatches", "--input", "-"])
        self.assertEqual(json.loads(sent["payload"]),
                         {"event_type": DISPATCH_TYPE, "client_payload": self._where(pending)})

    def test_monitored_verify_dispatch_binds_host_hint_after_build(self):
        approved, task, root = self._fresh_task_run(workspaces={"coordinator": self.first.name,
                                                                  "candidate": self.second.name})
        calls = []
        def command(argv):
            calls.append(argv)
            return {"id": argv[argv.index("--session-id") + 1], "deepLink": "conductor://session",
                    "initialMessage": {"messageId": argv[argv.index("--message-id") + 1],
                                       "state": "queued", "deepLink": "conductor://message"}}
        host = ConductorHostAdapter(self.workspace, agent="codex",
                                    routes={"verify": {"model": approved["approval"]["routes"]["verify"]["model"],
                                                       "effort": approved["approval"]["routes"]["verify"]["effort"]}},
                                    command=command)
        build = Fixture(coordinator_tests.CoordinatorTests.result(self))
        pending = InterimFixtureCoordinator(self.store).run_one(root, "TASK-413", task, build, host,
                                                             coordinator=Fixture({}))
        self.assertEqual(pending.value["state"]["next_action"], "await-worker")
        self.assertEqual(pending.value["state"]["operation_id"],
                         next(item for item in pending.value["usage"]["operations"] if item["phase"] == "verify")["id"])
        self.assertIn("worker-done", calls[0][-1])
        self.assertIn(approved["approval"]["checkpoint"]["ref"], calls[0][-1])

    def test_queued_coordinator_wake_keeps_worker_wait_monitored(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        identity = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        class QueuedWake(FakeConductor):
            def send_wake(self, operation):
                self.send_calls.append(deepcopy(operation))
                return {"observation": {key: operation[key] for key in identity},
                        "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
        fake = QueuedWake({"current_turn": "interrupted", "pending_messages": False,
                           "pending_effects": False, "active_workers": False,
                           "working_ambiguous": False, "awaited_worker": {**identity, "state": "terminal"}})
        woken, decision = reconcile(self.store, approved, self._where(pending), "event", fake, NOW)
        self.assertEqual((decision["action"], woken.value["state"]["next_action"],
                          woken.value["monitoring"]["state"], len(fake.send_calls)),
                         ("resume-coordinator", "await-worker", "active", 1))

    def test_actual_coordinator_host_error_without_completed_turn_records_one_failure(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        def command(argv):
            self.assertEqual(argv[:2], ["session", "status"])
            self.assertEqual(argv[2], op["session_id"])
            return {"workspaceId": self.workspace, "sessionId": op["session_id"],
                    "status": "error", "updatedAt": "2026-09-21T00:00:00Z"}
        host = ConductorHostAdapter(self.workspace, command=command)
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(pending, op["id"], host)
        operation = next(item for item in failed.value["usage"]["operations"] if item["id"] == op["id"])
        self.assertEqual((failed.value["state"]["next_action"], operation["status"],
                          operation["receipt"]["worker_state"]), ("worker-failed", "result-unusable", "error"))
        self.assertEqual(len([item for item in failed.value["usage"]["launches"] if item["operation_id"] == op["id"]]), 1)
        self.assertEqual(self.store.reload(approved).value["state"], failed.value["state"])

    def test_http_error_without_completed_turn_wakes_once_then_cli_retains_failure(self):
        approved, _, pending, _ = self._awaiting_build()
        op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        posts = []
        def request(method, path, body):
            if method == "POST":
                posts.append(body["messageId"])
                return {"messageId": body["messageId"], "state": "sent", "deepLink": "conductor://wake"}
            if path.endswith("/status"):
                session_id = path.split("/")[3]
                return {"workspaceId": self.workspace, "sessionId": session_id,
                        "status": "error" if session_id == op["session_id"] else "idle",
                        "updatedAt": "2026-09-21T00:00:00Z"}
            return {"data": [], "offset": 0, "hasMore": False}
        monitor = ConductorHttpAdapter(self.workspace, request)
        woken, decision = reconcile(self.store, approved, self._where(pending), "backup", monitor, now=NOW)
        self.assertEqual(decision["action"], "resume-coordinator")
        self.assertEqual(len(posts), 1)
        def command(argv):
            self.assertEqual(argv[:2], ["session", "status"])
            return {"workspaceId": self.workspace, "sessionId": op["session_id"],
                    "status": "error", "updatedAt": "2026-09-21T00:00:00Z"}
        host = ConductorHostAdapter(self.workspace, command=command)
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(woken, op["id"], host)
        retained = next(item for item in failed.value["usage"]["operations"] if item["id"] == op["id"])
        self.assertEqual((retained["status"], retained["receipt"]["worker_state"],
                          failed.value["state"]["next_action"]), ("result-unusable", "error", "worker-failed"))
        self.assertEqual(len([item for item in failed.value["usage"]["charges"] if item["operation_id"] == op["id"]]), 1)

    def test_verify_queued_reuses_the_same_monitored_wait_boundary(self):
        approved, task, pending, build = self._awaiting_build()
        self.approval = lambda: approved["approval"]
        build.result = coordinator_tests.CoordinatorTests.result(self)
        coordinator = InterimFixtureCoordinator(self.store)
        build_op = next(item for item in pending.value["usage"]["operations"] if item["phase"] == "build")
        reconciled = coordinator.reconcile_pending(pending, build_op["id"], build)
        queued = Fixture({"transport": "accepted", "worker_state": "queued", "terminal_turn": False,
                          "task_success": False, "elapsed_seconds": 0})
        waiting = coordinator.run_one(reconciled, "TASK-413", task, build, queued)
        verify_op = next(item for item in waiting.value["usage"]["operations"] if item["phase"] == "verify")
        self.assertEqual((waiting.value["state"]["next_action"], waiting.value["state"]["operation_id"],
                          waiting.value["monitoring"]["state"]), ("await-worker", verify_op["id"], "active"))
        queued.result = coordinator_tests.CoordinatorTests.result(self, "verify")
        completed = coordinator.reconcile_pending(waiting, verify_op["id"], queued)
        self.assertEqual((completed.value["state"]["next_action"],
                          next(item for item in completed.value["usage"]["operations"] if item["id"] == verify_op["id"])["status"]),
                         ("verify", "reconciled"))
        self.assertEqual(coordinator.run_one(completed, "TASK-413", task, build, queued).value["state"]["next_action"], "pr-ready")

    def test_stop_during_repair_binding_refuses_diagnosis_send(self):
        approved, task, waiting, build = self._awaiting_build(repair=True)
        build_op = next(item for item in waiting.value["usage"]["operations"] if item["phase"] == "build")
        build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                        "task_success": False, "elapsed_seconds": 0}
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(waiting, build_op["id"], build)
        finding, evidence = repair_tests.RepairPolicyTests.finding(self)
        repair = InterimRepairCoordinator(self.store)
        opened = repair.open(failed, "TASK-413", task, finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        class StopDuringBind(RepairFixture):
            def bind_worker_hint(inner, record, operation_id, repository):
                current = self.store.reload(approved)
                projected = deepcopy(current.value)
                projected["recovery"] = {"status": "stopping", "wakes": [], "observations": [],
                                         "stop": {"intent_at": "2026-09-21T00:00:00Z", "instruction": "Stop",
                                                  "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
                self.store.persist(current, projected)
        host = StopDuringBind()
        repair.diagnose(opened, "TASK-413", task, host)
        self.assertEqual(host.operations, [])
        self.assertEqual(self.store.reload(approved).value["recovery"]["status"], "stopping")

    def test_terminal_unusable_diagnosis_stays_monitored_for_reconciliation(self):
        approved, task, waiting, build = self._awaiting_build(repair=True)
        build_op = next(item for item in waiting.value["usage"]["operations"] if item["phase"] == "build")
        build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                        "task_success": False, "elapsed_seconds": 0}
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(waiting, build_op["id"], build)
        finding, evidence = repair_tests.RepairPolicyTests.finding(self)
        repair = InterimRepairCoordinator(self.store)
        opened = repair.open(failed, "TASK-413", task, finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        class Malformed(RepairFixture):
            def send(self, operation):
                receipt = super().send(operation)
                receipt["diagnosis"]["next_experiment"]["finding_id"] = "wrong-finding"
                return receipt
        observed = repair.diagnose(opened, "TASK-413", task, Malformed())
        self.assertEqual(observed.value["state"]["next_action"], "worker-failed")
        self.assertEqual(observed.value["monitoring"]["state"], "active")

    def test_diagnosis_repair_and_repair_verify_share_exact_worker_wait(self):
        _, task, waiting_build, build = self._awaiting_build(repair=True)
        build_op = next(item for item in waiting_build.value["usage"]["operations"] if item["phase"] == "build")
        build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                        "task_success": False, "elapsed_seconds": 0}
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(waiting_build, build_op["id"], build)
        finding, evidence = repair_tests.RepairPolicyTests.finding(self)
        coordinator = InterimRepairCoordinator(self.store, clock=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
        opened = coordinator.open(failed, "TASK-413", task, finding,
                                  {"head": "a" * 40, "base": "b" * 40}, evidence)
        class Queued(RepairFixture):
            def bind_worker_hint(self, record, operation_id, repository):
                self.hint_ids = getattr(self, "hint_ids", []) + [operation_id]
                self.assert_bound = next(item for item in record["usage"]["operations"] if item["id"] == operation_id)["phase"]
                self.hint_repository = repository
            def send(self, operation):
                self.operations.append(deepcopy(operation))
                return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
            def reconcile(self, operation):
                return RepairFixture.send(self, operation)
        diagnosis = Queued()
        waiting = coordinator.diagnose(opened, "TASK-413", task, diagnosis)
        self.assertEqual(waiting.value["state"]["next_action"], "await-worker")
        diagnosed = coordinator.diagnose(waiting, "TASK-413", task, diagnosis)
        repair, verify = Queued(), Queued()
        waiting = coordinator.repair_once(diagnosed, "TASK-413", task, repair, verify)
        self.assertEqual(waiting.value["state"]["next_action"], "await-worker")
        self.assertEqual(waiting.value["state"]["operation_id"], repair.operations[0]["id"])
        waiting_verify = coordinator.repair_once(waiting, "TASK-413", task, repair, verify)
        self.assertEqual(waiting_verify.value["state"]["next_action"], "await-worker")
        self.assertEqual(waiting_verify.value["state"]["operation_id"], verify.operations[0]["id"])
        self.assertEqual(waiting_verify.value["monitoring"]["state"], "active")
        for adapter, phase in ((diagnosis, "diagnosis"), (repair, "repair"), (verify, "repair-verify")):
            self.assertEqual((adapter.hint_ids, adapter.assert_bound, adapter.hint_repository),
                             ([adapter.operations[0]["id"]], phase, self.first))

    def test_repair_diagnosis_unknown_read_keeps_bounded_observation_guard(self):
        approved, task, waiting_build, build = self._awaiting_build(repair=True)
        build_op = next(item for item in waiting_build.value["usage"]["operations"] if item["phase"] == "build")
        build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                        "task_success": False, "elapsed_seconds": 0}
        failed = InterimFixtureCoordinator(self.store).reconcile_pending(waiting_build, build_op["id"], build)
        finding, evidence = repair_tests.RepairPolicyTests.finding(self)
        repair = InterimRepairCoordinator(self.store, clock=lambda: NOW)
        opened = repair.open(failed, "TASK-413", task, finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        class Uncertain(RepairFixture):
            def send(self, operation):
                self.operations.append(deepcopy(operation))
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
            def reconcile(self, operation):
                if self.calls == 0:
                    self.calls += 1
                    raise ObservationFailure("transient-outage")
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "transport": "unknown", "worker_state": "unknown", "elapsed_seconds": 0}
        host = Uncertain(); host.calls = 0
        waiting = repair.diagnose(opened, "TASK-413", task, host)
        operation_id = waiting.value["state"]["operation_id"]
        first = repair.reconcile_pending(waiting, operation_id, host)
        self.assertEqual(first.value["recovery_disposition"]["active"]["count"], 1)
        repair.clock = lambda: NOW + timedelta(minutes=15)
        second = repair.reconcile_pending(first, operation_id, host)
        self.assertEqual(second.value["recovery_disposition"]["active"]["count"], 2)
        repair.clock = lambda: NOW + timedelta(minutes=30)
        third = repair.reconcile_pending(second, operation_id, host)
        self.assertEqual(third.value["recovery_disposition"]["active"]["count"], 3)
        self.assertEqual(third.value["monitoring"]["state"], "inactive")

    @memoized_control_refs
    def test_repair_worker_errors_keep_one_monitored_failed_operation(self):
        for index, phase in enumerate(("diagnosis", "repair", "repair-verify")):
            if index:
                self.tearDown(); self.setUp()
            with self.subTest(phase=phase):
                approved, task, waiting_build, build = self._awaiting_build(repair=True)
                build_op = next(item for item in waiting_build.value["usage"]["operations"] if item["phase"] == "build")
                build.result = {"transport": "accepted", "worker_state": "error", "terminal_turn": False,
                                "task_success": False, "elapsed_seconds": 0}
                failed_build = InterimFixtureCoordinator(self.store).reconcile_pending(waiting_build, build_op["id"], build)
                finding, evidence = repair_tests.RepairPolicyTests.finding(self)
                coordinator = InterimRepairCoordinator(self.store, clock=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
                opened = coordinator.open(failed_build, "TASK-413", task, finding,
                                          {"head": "a" * 40, "base": "b" * 40}, evidence)
                class ErrorAfterQueue(RepairFixture):
                    def send(self, operation):
                        self.operations.append(deepcopy(operation))
                        return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                                "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}
                    def reconcile(self, operation):
                        return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")},
                                "transport": "accepted", "worker_state": "error", "elapsed_seconds": 0}
                error_adapter = ErrorAfterQueue()
                diagnosis = error_adapter if phase == "diagnosis" else RepairFixture()
                current = coordinator.diagnose(opened, "TASK-413", task, diagnosis)
                if phase == "diagnosis":
                    waiting = current
                else:
                    repair_adapter = error_adapter if phase == "repair" else RepairFixture()
                    verify_adapter = error_adapter if phase == "repair-verify" else RepairFixture()
                    waiting = coordinator.repair_once(current, "TASK-413", task, repair_adapter, verify_adapter)
                operation_id = waiting.value["state"]["operation_id"]
                before = waiting.value["repair"]
                generation = waiting.value["monitoring"]["pending_wake"]["generation"]
                observed = coordinator.reconcile_pending(waiting, operation_id, error_adapter)
                operation = next(item for item in observed.value["usage"]["operations"] if item["id"] == operation_id)
                self.assertEqual((observed.value["state"]["next_action"], observed.value["state"]["operation_id"],
                                  observed.value["repair"]["status"], observed.value["monitoring"]["state"], operation["status"]),
                                 ("worker-failed", operation_id, "worker-failed", "active", "result-unusable"))
                self.assertEqual((observed.value["repair"]["diagnoses"], observed.value["repair"]["cycles"]),
                                 (before["diagnoses"], before["cycles"]))
                self.assertNotEqual(observed.value["monitoring"]["pending_wake"]["generation"], generation)
                generation = observed.value["monitoring"]["pending_wake"]["generation"]
                self.assertEqual(len([item for item in observed.value["usage"]["launches"] if item["operation_id"] == operation_id]), 1)
                duplicate = coordinator.reconcile_pending(observed, operation_id, error_adapter)
                self.assertEqual((duplicate.commit_sha, duplicate.value["monitoring"]["pending_wake"]["generation"]),
                                 (observed.commit_sha, generation))
                where = self._where(observed)
                wake_host = FakeConductor()
                checked, decision = reconcile(self.store, approved, where, "backup", wake_host, NOW)
                self.assertEqual(decision["action"], "resume-coordinator")
                checked_again, duplicate_decision = reconcile(self.store, approved, where, "event", wake_host, NOW)
                self.assertNotEqual(duplicate_decision["action"], "resume-coordinator")
                self.assertEqual(len(wake_host.send_calls), 1)
                recovery = InterimRecoveryCoordinator(self.store, clock=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
                stopped = recovery.stop(checked_again, "explicit whole-run stop", RecoveryFixture(observed_state="terminal"))
                self.assertEqual((stopped.value["recovery"]["status"], stopped.value["state"]["next_action"],
                                  stopped.value["monitoring"]["state"]), ("stopped", "handback", "inactive"))
                resumed = recovery.resume(stopped, "explicit resume", RecoveryFixture(observed_state="terminal"))
                self.assertEqual((resumed.value["recovery"]["status"], resumed.value["state"]["next_action"]),
                                 ("resumed", "recovered"))
                self.assertEqual(next(item for item in resumed.value["usage"]["operations"] if item["id"] == operation_id)["status"],
                                 "result-unusable")

    def test_enrollment_schema_retirement_resume_and_overlap_are_isolated(self):
        record = enroll(deepcopy(self.approved), self.workspace)
        monitor = record["monitoring"]
        self.assertEqual((monitor["state"], monitor["epoch"], monitor["coordinator_session_id"]), ("active", 1, "coordinator-1"))
        prior_usage = deepcopy(record["usage"])
        stopped = retire(record, "whole-run-stopped")
        self.assertEqual((stopped["monitoring"]["state"], stopped["monitoring"]["pending_wake"], stopped["usage"]), ("inactive", None, prior_usage))
        stopped["recovery"] = {"status": "resumed", "wakes": [], "observations": [],
                                "stop": {"intent_at": "2026-09-21T00:00:00Z", "instruction": "human stop", "prefix_removed": True, "cancellations": [], "uncertainty": None},
                                "resume": {"instruction": "human", "resumed_at": "2026-09-21T00:00:00Z"}}
        restarted = resume(stopped, "d" * 40, "human")
        self.assertEqual((restarted["monitoring"]["epoch"], restarted["monitoring"]["state"]), (2, "active"))
        running = deepcopy(stopped); running["recovery"]["status"] = "running"
        with self.assertRaisesRegex(Exception, "explicit authority"):
            resume(running, "d" * 40, "human")
        with self.assertRaisesRegex(Exception, "explicit human authority"):
            resume(stopped, "d" * 40, "")
        other = deepcopy(restarted); other["approval"]["run_id"] = "other-run"
        with self.assertRaisesRegex(Exception, "immutable|run-specific"):
            validate_record(other)

    def test_event_and_backup_converge_on_one_logical_wake_through_temp_git_cas(self):
        initial = self.enrolled()
        generation = initial.value["monitoring"]["pending_wake"]["generation"]
        locator = {"run_id": "run-task-413", "control_ref": initial.value["monitoring"]["control_ref"], "generation": generation}
        event = FakeConductor()
        settled, first = reconcile(self.store, self.approved, locator, "event", event, datetime(2026, 9, 21, tzinfo=timezone.utc))
        second_store = InterimCheckpointStore(self.second, "origin", locator["control_ref"])
        backup = FakeConductor()
        duplicate, second = reconcile(second_store, self.approved, locator, "backup", backup, datetime(2026, 9, 21, tzinfo=timezone.utc))
        wakes = [item for item in duplicate.value["usage"]["operations"] if item["phase"] == "wake"]
        self.assertEqual((first["action"], second["action"], len(wakes), len(event.send_calls), len(backup.send_calls)), ("resume-coordinator", "reconcile-coordinator-wake", 1, 1, 0))
        self.assertEqual(duplicate.value["monitoring"]["last_reconciliation"]["source"], "backup")

    def test_competing_independent_stores_race_on_one_remote_and_send_once(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": "run-task-413", "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        barrier = threading.Barrier(2)
        outcomes, fakes = [], []
        def compete(path, source):
            store = InterimCheckpointStore(path, "origin", where["control_ref"])
            fake = FakeConductor(); fakes.append(fake); barrier.wait()
            outcomes.append(reconcile(store, self.approved, where, source, fake))
        threads = [threading.Thread(target=compete, args=(self.first, "event")), threading.Thread(target=compete, args=(self.second, "backup"))]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        current = self.store.reload(self.approved)
        wakes = [item for item in current.value["usage"]["operations"] if item["phase"] == "wake"]
        self.assertEqual((len(outcomes), len(wakes), sum(len(fake.send_calls) for fake in fakes)), (2, 1, 1))

    def test_checkpoint_transition_persists_next_generation_before_its_event(self):
        initial = self.enrolled()
        first_generation = initial.value["monitoring"]["pending_wake"]["generation"]
        transitioned = checkpoint_transition(initial.value, "coordinator-checkpoint", initial.commit_sha)
        next_wake = transitioned["monitoring"]["pending_wake"]
        self.assertEqual((next_wake["reason"], next_wake["checkpoint_parent_commit"], next_wake["generation"] == first_generation), ("coordinator-checkpoint", initial.commit_sha, False))

    def test_predecessor_binding_accepts_one_cas_child_and_refuses_transplant_or_stale_parent_without_send(self):
        root = self.enrolled()
        transition = persist_checkpoint_transition(self.store, root, "coordinator-checkpoint")
        pending = transition.value["monitoring"]["pending_wake"]
        where = {"run_id": transition.value["approval"]["run_id"], "control_ref": transition.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        # Same bytes in a different descendant are not the one CAS child that
        # the pending wake named; it cannot send or charge again.
        transplanted = self.store.persist(transition, deepcopy(transition.value))
        bad = FakeConductor(); _, refused = reconcile(self.store, self.approved, where, "backup", bad)
        self.assertEqual((refused["action"], refused["reason"], len(bad.send_calls)), ("refuse", "checkpoint-parent-binding-mismatch", 0))
        self.assertNotEqual(transplanted.parent_commits[0], pending["checkpoint_parent_commit"])

    def test_start_and_transition_keep_checkpoint_when_event_emission_fails(self):
        # A separate exact run starts from its own root and dispatch failure is
        # post-CAS only; deterministic backup can still discover the record.
        item = approval(str(self.remote), str(self.remote)); item["run_id"] = "emit-run"
        ref = "refs/heads/delivery-control/issue-emit-run"; item["repository"]["control_ref"] = ref; item["checkpoint"]["ref"] = ref
        item["tasks"] = [{"id": "emit-task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "e" * 64}]
        store = InterimCheckpointStore(self.first, "origin", ref)
        root = start_monitored_run(store, initial_record(item), self.workspace)
        advanced = persist_checkpoint_transition(store, root, "checkpoint", lambda _where: (_ for _ in ()).throw(OSError("offline")))
        self.assertEqual((advanced.value["monitoring"]["state"], advanced.value["monitoring"]["pending_wake"]["checkpoint_parent_commit"]), ("active", root.commit_sha))

    def test_monitoring_schema_rejects_unknown_malformed_identity_and_preserves_legacy_records(self):
        self.assertEqual(validate_record(self.approved), self.approved)
        enrolled = enroll(deepcopy(self.approved), self.workspace)
        unknown = deepcopy(enrolled); unknown["monitoring"]["surprise"] = True
        with self.assertRaisesRegex(Exception, "unknown"):
            validate_record(unknown)
        bad_oid = deepcopy(enrolled); bad_oid["monitoring"]["pending_wake"]["checkpoint_parent_commit"] = "not-an-oid"
        with self.assertRaisesRegex(Exception, "object ID"):
            validate_record(bad_oid)
        bad_generation = deepcopy(enrolled); bad_generation["monitoring"]["pending_wake"]["generation"] = "wake-forged"
        with self.assertRaisesRegex(Exception, "generation"):
            validate_record(bad_generation)

    def test_refuses_active_or_ambiguous_work_without_a_conductor_message(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": "run-task-413", "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        for field in ("active_workers", "working_ambiguous", "pending_messages", "pending_effects"):
            observation = {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False,
                           "active_workers": False, "working_ambiguous": False}
            observation[field] = True
            fake = FakeConductor(observation)
            _, decision = reconcile(self.store, self.approved, where, "event", fake)
            self.assertEqual((decision["action"], len(fake.send_calls)), ("refuse", 0))

    def test_sleeping_or_unavailable_host_refuses_without_message_and_later_backup_can_retry(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": "run-task-413", "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        unavailable = FakeConductor()
        unavailable.monitoring_observation = lambda _record: (_ for _ in ()).throw(OSError("sleeping workspace"))
        refused, decision = reconcile(self.store, self.approved, where, "event", unavailable, now=NOW)
        self.assertEqual((decision["action"], decision["reason"], len(unavailable.send_calls)), ("refuse", "host-observation-unavailable-or-ineligible", 0))
        where = self._where(refused)
        recovered, retry = reconcile(self.store, self.approved, where, "backup", FakeConductor(), now=NOW + timedelta(minutes=15))
        self.assertEqual((retry["action"], len([op for op in recovered.value["usage"]["operations"] if op["phase"] == "wake"])), ("resume-coordinator", 1))

    def test_overlapping_control_refs_wake_independently(self):
        first = self.enrolled(); first_pending = first.value["monitoring"]["pending_wake"]
        first_locator = {"run_id": "run-task-413", "control_ref": first.value["monitoring"]["control_ref"], "generation": first_pending["generation"]}
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "other-run"
        other_ref = "refs/heads/delivery-control/issue-other-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "other-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "c" * 64}]
        other_approved = initial_record(other)
        other_store = InterimCheckpointStore(self.first, "origin", other_ref)
        second = other_store.create_and_publish(enroll(other_approved, self.workspace))
        second_pending = second.value["monitoring"]["pending_wake"]
        second_locator = {"run_id": "other-run", "control_ref": other_ref, "generation": second_pending["generation"]}
        first_result, first_decision = reconcile(self.store, self.approved, first_locator, "event", FakeConductor())
        second_result, second_decision = reconcile(other_store, other_approved, second_locator, "backup", FakeConductor())
        self.assertEqual((first_decision["action"], second_decision["action"], first_result.value["approval"]["run_id"], second_result.value["approval"]["run_id"]), ("resume-coordinator", "resume-coordinator", "run-task-413", "other-run"))

    def test_terminal_late_event_retires_only_its_run_and_malformed_locator_has_no_calls(self):
        initial = self.enrolled(); record = deepcopy(initial.value)
        record["recovery"] = {"status": "stopped", "wakes": [], "observations": [], "stop": {"intent_at": "2026-09-21T00:00:00Z", "instruction": "human stop", "prefix_removed": True, "cancellations": [], "uncertainty": None}, "resume": None}
        terminal = self.store.persist(initial, record)
        pending = terminal.value["monitoring"]["pending_wake"]
        where = {"run_id": "run-task-413", "control_ref": terminal.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        fake = FakeConductor(); retired, decision = reconcile(self.store, self.approved, where, "event", fake)
        self.assertEqual((decision["action"], retired.value["monitoring"]["state"], len(fake.send_calls)), ("refuse", "inactive", 0))
        with self.assertRaisesRegex(Exception, "locator"):
            reconcile(self.store, self.approved, {"run_id": "run-task-413"}, "event", fake)

    def test_github_payload_and_empty_registry_are_locator_only_and_zero_effect(self):
        self.assertEqual(backup_registry([]), [])
        locator = {"run_id": "run", "control_ref": "refs/heads/delivery-control/issue-run", "generation": "wake"}
        envelope = {"action": DISPATCH_TYPE, "client_payload": locator, "branch": "main", "repository": {"full_name": "untrusted/example"}, "sender": {"login": "untrusted"}, "installation": {"id": 1}}
        self.assertEqual(repository_dispatch(envelope), locator)
        self.assertEqual(workflow_dispatch('{"run_id":"run","control_ref":"refs/heads/delivery-control/issue-run","generation":"wake"}'), locator)
        with self.assertRaisesRegex(Exception, "malformed"):
            repository_dispatch({"action": "other", "client_payload": locator})

    def test_bounded_event_file_parses_both_github_triggers_without_echoing_payload(self):
        where = {"run_id": "untrusted-marker", "control_ref": "refs/heads/delivery-control/issue-untrusted-marker",
                 "generation": "wake-marker"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            for event_name, payload in (("repository_dispatch", {"action": DISPATCH_TYPE, "client_payload": where}),
                                        ("workflow_dispatch", {"inputs": {"locator": json.dumps(where)}})):
                path.write_text(json.dumps(payload))
                self.assertEqual(load_event_file(path, event_name), where)
            for invalid in (b"{malformed-untrusted-marker", b"[" * 10000 + b"0" + b"]" * 10000,
                            b"x" * 131073):
                path.write_bytes(invalid)
                with self.assertRaises(Exception) as caught:
                    load_event_file(path, "repository_dispatch")
                self.assertNotIn("untrusted-marker", str(caught.exception))
            path.write_text(json.dumps({"action": DISPATCH_TYPE, "client_payload": where}))
            result = subprocess.run([sys.executable, "-m", "delivery_pilot.interim_github", "--repository",
                                     str(self.first), "event", "--event-file", str(path)], check=False,
                                    capture_output=True, text=True,
                                    env={**os.environ, "GITHUB_EVENT_NAME": "repository_dispatch",
                                         "PYTHONPATH": str(PACK / "src")})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("untrusted-marker", result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)[0]["action"], "refuse")
            obsolete = subprocess.run([sys.executable, "-m", "delivery_pilot.interim_github", "event",
                                       "--event-file", str(path),
                                       "--workflow-locator", "PAYLOAD_MARKER_7f31"], check=False,
                                      capture_output=True, text=True,
                                      env={**os.environ, "PYTHONPATH": str(PACK / "src")})
            self.assertEqual(obsolete.returncode, 2)
            self.assertNotIn("PAYLOAD_MARKER_7f31", obsolete.stdout + obsolete.stderr)

    def test_registered_runner_uses_trusted_ref_not_envelope_and_empty_registry_has_no_adapter(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        calls = []
        def factory(_workspace):
            calls.append(_workspace); return FakeConductor()
        runner = RegisteredRunner(self.first, "origin", factory)
        self.assertEqual(runner.run([], "backup"), [])
        where = {"run_id": "run-task-413", "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        result = runner.run([where], "event")
        self.assertEqual((result[0]["action"], len(calls)), ("resume-coordinator", 1))

    def test_backup_discovery_uses_only_active_exact_control_refs_not_an_operator_registry(self):
        initial = self.enrolled(); calls = []
        runner = RegisteredRunner(self.first, "origin", lambda workspace: calls.append(workspace) or FakeConductor())
        found = runner.discover()
        self.assertEqual(found, [{"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": initial.value["monitoring"]["pending_wake"]["generation"]}])
        self.assertEqual(calls, [])

    def test_bounded_backup_discovery_isolates_bad_ref_and_refuses_overflow_without_http(self):
        initial = self.enrolled(); sha = self.store.remote_commit(); runner = RegisteredRunner(self.first, "origin", lambda _workspace: self.fail("discovery must not create an adapter"))
        valid = sha + "\t" + initial.value["monitoring"]["control_ref"] + "\n"
        malformed = sha + "\trefs/heads/delivery-control/issue-bad ref\n"
        import delivery_pilot.interim_github as github
        real_run = subprocess.run
        def listing(command, *args, **kwargs):
            if command[:4] == ["git", "ls-remote", "--heads", "origin"]:
                return subprocess.CompletedProcess(command, 0, stdout=valid + malformed, stderr="")
            return real_run(command, *args, **kwargs)
        with mock.patch.object(github.subprocess, "run", side_effect=listing):
            found = runner.discover()
        self.assertEqual(found, [{"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": initial.value["monitoring"]["pending_wake"]["generation"]}])
        self.assertEqual(runner.discovery_outcomes[-1]["reason"], "malformed-or-duplicate-control-ref")
        self.assertNotIn("issue-bad ref", json.dumps(runner.discovery_outcomes))
        overflow = (sha + "\trefs/heads/delivery-control/issue-many\n") * (MAX_REGISTERED_REFS + 1)
        with mock.patch.object(github.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=overflow, stderr="")):
            with self.assertRaisesRegex(Exception, "candidate limit"):
                runner.discover()

    def test_selected_limit_atomically_retires_monitoring_and_prevents_repeated_backup_attention(self):
        item = approval(str(self.remote), str(self.remote)); item["hard_limits"] = {"deadline_at": "2026-09-20T00:00:00Z"}
        item["tasks"] = [{"id": "limited", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "d" * 64}]
        record = initial_record(item); store = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"])
        snapshot = store.create_and_publish(enroll(record, self.workspace)); pending = snapshot.value["monitoring"]["pending_wake"]
        where = {"run_id": item["run_id"], "control_ref": item["checkpoint"]["ref"], "generation": pending["generation"]}
        first, decision = reconcile(store, record, where, "backup", FakeConductor(), datetime(2026, 9, 21, tzinfo=timezone.utc))
        second, later = reconcile(store, record, where, "backup", FakeConductor(), datetime(2026, 9, 21, tzinfo=timezone.utc))
        self.assertEqual((decision["reason"], first.value["monitoring"]["state"], later["reason"], second.value["usage"]), ("selected-limit-exhausted", "inactive", "monitoring-inactive", first.value["usage"]))

    def test_exact_admitted_timeout_settles_after_its_selected_dispatch_cap_is_exhausted(self):
        item = approval(str(self.remote), str(self.remote)); item["hard_limits"] = {"dispatch_max": 1}
        item["tasks"] = [{"id": "limited", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "d" * 64}]
        record = initial_record(item); store = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"])
        initial = store.create_and_publish(enroll(record, self.workspace)); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": item["run_id"], "control_ref": item["checkpoint"]["ref"], "generation": pending["generation"]}

        class AcceptedThenTimedOut(FakeConductor):
            def send_wake(self, operation):
                self.send_calls.append(deepcopy(operation))
                raise TimeoutError("accepted after transport timeout")

        first = AcceptedThenTimedOut()
        timed_out, first_decision = reconcile(store, record, where, "event", first, datetime(2026, 9, 19, tzinfo=timezone.utc))
        before_settlement = deepcopy(timed_out.value["usage"])
        settled_by = FakeConductor()
        settled, settlement = reconcile(store, record, where, "backup", settled_by, datetime(2026, 9, 19, tzinfo=timezone.utc))
        wake = next(operation for operation in settled.value["usage"]["operations"] if operation["phase"] == "wake")
        self.assertEqual((first_decision["action"], settlement["action"], wake["status"]), ("resume-coordinator", "reconcile-coordinator-wake", "accounted"))
        self.assertEqual((len(first.send_calls), len(settled_by.send_calls), [call["id"] for call in settled_by.observe_calls]), (1, 0, [wake["id"]]))
        self.assertEqual((len(settled.value["usage"]["operations"]), len(settled.value["usage"]["charges"]), settled.value["usage"]["launches"], settled.value["approval"]["hard_limits"]),
                         (len(before_settlement["operations"]), len(before_settlement["charges"]), before_settlement["launches"], {"dispatch_max": 1}))

    def test_exact_admitted_timeout_settles_after_its_selected_deadline_expires(self):
        item = approval(str(self.remote), str(self.remote)); item["hard_limits"] = {"deadline_at": "2026-09-20T00:00:00Z"}
        item["tasks"] = [{"id": "limited", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "d" * 64}]
        record = initial_record(item); store = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"])
        initial = store.create_and_publish(enroll(record, self.workspace)); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": item["run_id"], "control_ref": item["checkpoint"]["ref"], "generation": pending["generation"]}

        class AcceptedThenTimedOut(FakeConductor):
            def send_wake(self, operation):
                self.send_calls.append(deepcopy(operation))
                raise TimeoutError("accepted after transport timeout")

        first = AcceptedThenTimedOut()
        timed_out, _ = reconcile(store, record, where, "event", first, datetime(2026, 9, 19, tzinfo=timezone.utc))
        before_settlement = deepcopy(timed_out.value["usage"])
        settled_by = FakeConductor()
        settled, settlement = reconcile(store, record, where, "backup", settled_by, datetime(2026, 9, 21, tzinfo=timezone.utc))
        wake = next(operation for operation in settled.value["usage"]["operations"] if operation["phase"] == "wake")
        self.assertEqual((settlement["action"], wake["status"], len(first.send_calls), len(settled_by.send_calls)), ("reconcile-coordinator-wake", "accounted", 1, 0))
        self.assertEqual((len(settled.value["usage"]["operations"]), len(settled.value["usage"]["charges"]), settled.value["usage"]["launches"], settled.value["approval"]["hard_limits"]),
                         (len(before_settlement["operations"]), len(before_settlement["charges"]), before_settlement["launches"], {"deadline_at": "2026-09-20T00:00:00Z"}))

    def test_exact_wake_settlement_never_admits_a_new_generation_after_selected_cap_exhaustion(self):
        item = approval(str(self.remote), str(self.remote)); item["hard_limits"] = {"dispatch_max": 1}
        item["tasks"] = [{"id": "limited", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "d" * 64}]
        record = initial_record(item); store = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"])
        initial = store.create_and_publish(enroll(record, self.workspace)); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": item["run_id"], "control_ref": item["checkpoint"]["ref"], "generation": pending["generation"]}
        title = (PREFIX + " run=" + item["run_id"] + " mode=interim-coordinator checkpoint="
                 + item["checkpoint"]["ref"] + " progress=" + item["progress_checkpoint_policy"]
                 + " hard_limits=selected")
        admitted, first_decision = reserve_and_persist(store, initial, title, "coordinator-1", pending["generation"],
                                                        {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False},
                                                        datetime(2026, 9, 19, tzinfo=timezone.utc))
        successor = {"run_id": item["run_id"], "control_ref": item["checkpoint"]["ref"], "generation": "distinct-new-generation"}
        before_refusal = deepcopy(admitted.value["usage"])
        blocked_by = FakeConductor()
        blocked, refusal = reconcile(store, record, successor, "backup", blocked_by, datetime(2026, 9, 19, tzinfo=timezone.utc))
        settled_by = FakeConductor()
        settled, settlement = reconcile(store, record, where, "backup", settled_by, datetime(2026, 9, 19, tzinfo=timezone.utc))
        wake = next(operation for operation in settled.value["usage"]["operations"] if operation["phase"] == "wake")
        self.assertEqual((first_decision["action"], settlement["action"], wake["status"], refusal["action"]),
                         ("resume-coordinator", "reconcile-coordinator-wake", "accounted", "refuse"))
        self.assertEqual((blocked_by.monitor_calls, len(blocked_by.send_calls), len(blocked_by.observe_calls), blocked.value["usage"], blocked.value["approval"]["hard_limits"]),
                         (0, 0, 0, before_refusal, {"dispatch_max": 1}))
        self.assertEqual((len(settled_by.send_calls), [call["id"] for call in settled_by.observe_calls]), (0, [wake["id"]]))

    def test_registered_runner_refuses_a_ref_that_disappears_after_discovery_and_continues_later_overlap(self):
        initial = self.enrolled()
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "a-disappearing-run"
        other_ref = "refs/heads/delivery-control/issue-a-disappearing-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "other-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "e" * 64}]
        other_store = InterimCheckpointStore(self.first, "origin", other_ref)
        other_store.create_and_publish(enroll(initial_record(other), self.workspace))
        adapters = []
        runner = RegisteredRunner(self.first, "origin", lambda workspace: adapters.append(workspace) or FakeConductor())
        discovered = runner.discover()
        self.assertEqual({item["run_id"] for item in discovered}, {"run-task-413", "a-disappearing-run"})
        subprocess.run(["git", "push", "origin", ":" + other_ref], cwd=self.first, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        results = runner.run(discovered, "backup")
        self.assertEqual(results, [
            {"run_id": "unavailable", "control_ref": "unavailable", "action": "refuse", "reason": "checkpoint-reload-refused",
             "failure_boundary": "registered-reload", "failure_kind": "checkpoint", "failure_detail": "missing"},
            {"run_id": initial.value["approval"]["run_id"], "action": "resume-coordinator", "reason": "accepted"},
        ])
        self.assertEqual(adapters, [self.workspace])

    def test_registered_runner_refuses_malformed_checkpoint_after_discovery_and_continues_later_overlap(self):
        initial = self.enrolled()
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "a-malformed-run"
        other_ref = "refs/heads/delivery-control/issue-a-malformed-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "other-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "e" * 64}]
        other_store = InterimCheckpointStore(self.first, "origin", other_ref)
        other_store.create_and_publish(enroll(initial_record(other), self.workspace))
        adapters = []
        runner = RegisteredRunner(self.first, "origin", lambda workspace: adapters.append(workspace) or FakeConductor())
        discovered = runner.discover()
        self.assertEqual({item["run_id"] for item in discovered}, {"run-task-413", "a-malformed-run"})
        subprocess.run(["git", "fetch", "origin", "+" + other_ref + ":" + other_ref], cwd=self.second, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "checkout", "-q", "-B", "malformed-checkpoint", other_ref], cwd=self.second, check=True)
        (self.second / "mission.yml").write_bytes(b"monitoring: [\n")
        subprocess.run(["git", "add", "mission.yml"], cwd=self.second, check=True)
        subprocess.run(["git", "commit", "-qm", "corrupt checkpoint"], cwd=self.second, check=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD:" + other_ref], cwd=self.second, check=True)
        results = runner.run(discovered, "backup")
        self.assertEqual(results, [
            {"run_id": "unavailable", "control_ref": "unavailable", "action": "refuse", "reason": "checkpoint-reload-refused",
             "failure_boundary": "registered-reload", "failure_kind": "checkpoint", "failure_detail": "corrupt"},
            {"run_id": initial.value["approval"]["run_id"], "action": "resume-coordinator", "reason": "accepted"},
        ])
        self.assertEqual(adapters, [self.workspace])

    def test_registered_runner_reports_safe_boundary_for_git_commit_failure(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": initial.value["approval"]["run_id"], "control_ref": self.store.control_ref,
                 "generation": pending["generation"]}
        runner = RegisteredRunner(self.first, "origin", lambda _workspace: FakeConductor())
        failure = subprocess.CalledProcessError(128, ["git", "commit-tree"])
        with mock.patch("delivery_pilot.interim_github.reconcile", side_effect=failure):
            self.assertEqual(runner.run([where], "event"), [
                {"run_id": where["run_id"], "control_ref": where["control_ref"], "action": "refuse",
                 "reason": "checkpoint-reload-refused", "failure_boundary": "reconciliation",
                 "failure_kind": "git-subprocess",
                 "failure_detail": "none"},
            ])

    def _where(self, snapshot):
        return {"run_id": snapshot.value["approval"]["run_id"], "control_ref": snapshot.value["monitoring"]["control_ref"],
                "generation": snapshot.value["monitoring"]["pending_wake"]["generation"]}

    def _on_fetch(self, checkout, nth, action):
        """Run a competing delivery between one checkout's nth ls-remote and fetch."""
        real = InterimCheckpointStore._git; count = {"fetch": 0}
        def patched(store, *args, check=True):
            if args and args[0] == "fetch" and store.repository == checkout:
                count["fetch"] += 1
                if count["fetch"] == nth:
                    action()
            return real(store, *args, check=check)
        return mock.patch.object(InterimCheckpointStore, "_git", patched)

    def _final_usage(self):
        return InterimCheckpointStore(self.second, "origin", self.store.control_ref).reload_registered().value["usage"]

    def _limited_run(self):
        item = approval(str(self.remote), str(self.remote)); item["hard_limits"] = {"deadline_at": "2026-09-20T00:00:00Z", "dispatch_max": 1}
        item["tasks"] = [{"id": "limited", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "d" * 64}]
        record = initial_record(item)
        snapshot = InterimCheckpointStore(self.first, "origin", item["checkpoint"]["ref"]).create_and_publish(enroll(record, self.workspace))
        return record, snapshot

    def test_backup_race_loser_reconciles_when_winner_publishes_during_discovery_reload(self):
        initial = self.enrolled(); where = self._where(initial)
        event, backup = FakeConductor(), FakeConductor()
        winner = InterimCheckpointStore(self.second, "origin", self.store.control_ref)
        decisions = []
        runner = RegisteredRunner(self.first, "origin", lambda _workspace: backup)
        with self._on_fetch(self.first, 1, lambda: decisions.append(reconcile(winner, self.approved, where, "event", event, NOW)[1])):
            discovered = runner.discover()
        results = runner.discovery_outcomes + runner.run(discovered, "backup")
        self.assertEqual([decision["action"] for decision in decisions], ["resume-coordinator"])
        self.assertEqual(results, [{"run_id": where["run_id"], "action": "reconcile-coordinator-wake", "reason": "accepted"}])
        self.assertEqual((len(event.send_calls), len(backup.send_calls)), (1, 0))
        self.assertEqual(len(self._final_usage()["charges"]), 1)

    def test_backup_race_loser_reconciles_when_winner_publishes_inside_its_reconcile_reload(self):
        initial = self.enrolled(); where = self._where(initial)
        event, backup = FakeConductor(), FakeConductor()
        winner = InterimCheckpointStore(self.second, "origin", self.store.control_ref)
        runner = RegisteredRunner(self.first, "origin", lambda _workspace: backup)
        discovered = runner.discover()
        # Fetch 1 is RegisteredRunner.one's registered reload; fetch 2 is reconcile's exact reload.
        with self._on_fetch(self.first, 2, lambda: reconcile(winner, self.approved, where, "event", event, NOW)):
            results = runner.run(discovered, "backup")
        self.assertEqual(results, [{"run_id": where["run_id"], "action": "reconcile-coordinator-wake", "reason": "accepted"}])
        self.assertEqual((len(event.send_calls), len(backup.send_calls)), (1, 0))
        self.assertEqual(len(self._final_usage()["charges"]), 1)

    def test_selected_limit_retire_that_loses_cas_reevaluates_the_competitors_checkpoint(self):
        record, snapshot = self._limited_run(); where = self._where(snapshot)
        competitor = InterimCheckpointStore(self.second, "origin", where["control_ref"])
        loser = InterimCheckpointStore(self.first, "origin", where["control_ref"])
        real_persist = InterimCheckpointStore.persist; raced = []
        def persist(store, expected, value):
            if store is loser and not raced:
                raced.append(reconcile(competitor, record, where, "backup", FakeConductor(), NOW)[1])
            return real_persist(store, expected, value)
        adapter = FakeConductor()
        with mock.patch.object(InterimCheckpointStore, "persist", persist):
            current, decision = reconcile(loser, record, where, "event", adapter, NOW)
        self.assertEqual(raced, [{"action": "refuse", "reason": "selected-limit-exhausted"}])
        self.assertEqual(decision, {"action": "refuse", "reason": "monitoring-inactive"})
        self.assertEqual((current.value["monitoring"]["state"], current.value["usage"]["launches"], adapter.monitor_calls, len(adapter.send_calls)),
                         ("inactive", [], 0, 0))

    def test_retirement_that_fails_for_a_non_cas_reason_is_not_reevaluated(self):
        record, snapshot = self._limited_run(); where = self._where(snapshot)
        loser = InterimCheckpointStore(self.first, "origin", where["control_ref"])
        calls = []
        def persist(store, expected, value):
            calls.append(value)
            raise InterimCheckpointError("approved repository identity changed; reload or hand back", code="target")
        with mock.patch.object(InterimCheckpointStore, "persist", persist), \
                self.assertRaises(InterimCheckpointError) as raised:
            reconcile(loser, record, where, "event", FakeConductor(), NOW)
        self.assertEqual((raised.exception.code, len(calls)), ("target", 1))

    def test_retirement_push_rejected_without_remote_movement_is_not_a_lost_cas(self):
        record, snapshot = self._limited_run(); where = self._where(snapshot)
        loser = InterimCheckpointStore(self.first, "origin", where["control_ref"])
        rejected = subprocess.CalledProcessError(1, ["git", "push"])
        with mock.patch.object(GitControlStore, "push", side_effect=rejected) as push, \
                self.assertRaises(InterimCheckpointError) as raised:
            reconcile(loser, record, where, "event", FakeConductor(), NOW)
        self.assertEqual((raised.exception.code, push.call_count), ("push-failed", 1))
        self.assertEqual(loser.remote_commit(), snapshot.commit_sha)

    def test_wake_reservation_push_rejected_without_remote_movement_is_surfaced(self):
        initial = self.enrolled(); where = self._where(initial)
        adapter = FakeConductor()
        rejected = subprocess.CalledProcessError(1, ["git", "push"])
        with mock.patch.object(GitControlStore, "push", side_effect=rejected), \
                self.assertRaises(InterimCheckpointError) as raised:
            reconcile(self.store, self.approved, where, "event", adapter, NOW)
        self.assertEqual((raised.exception.code, len(adapter.send_calls)), ("push-failed", 0))
        self.assertEqual(self.store.remote_commit(), initial.commit_sha)

    def test_simultaneous_wake_reservations_in_the_same_second_send_exactly_once(self):
        initial = self.enrolled(); where = self._where(initial)
        event, backup = FakeConductor(), FakeConductor()
        winner = InterimCheckpointStore(self.first, "origin", self.store.control_ref)
        loser = InterimCheckpointStore(self.second, "origin", self.store.control_ref)
        real_push = GitControlStore.push; raced = []; state = {}
        def push(store, remote, expected, commit):
            if store.repository == self.second and "loser" not in state:
                # The backup has passed its remote CAS check.  Let the event
                # run, and land this stale push right after the event's
                # reservation push, before the event records its receipt.
                state["loser"] = (store, remote, expected, commit)
                raced.append(reconcile(winner, self.approved, where, "event", event, NOW)[1])
                if isinstance(state.get("landed"), Exception):
                    raise state["landed"]
                return None
            result = real_push(store, remote, expected, commit)
            if store.repository == self.first and "loser" in state and "landed" not in state:
                try:
                    real_push(*state["loser"]); state["landed"] = True
                except Exception as exc:  # the stale lease is rejected
                    state["landed"] = exc
            return result
        same_second = {"GIT_AUTHOR_DATE": "2026-09-21T00:00:00Z", "GIT_COMMITTER_DATE": "2026-09-21T00:00:00Z"}
        with mock.patch.dict(os.environ, same_second), mock.patch.object(GitControlStore, "push", push):
            _, decision = reconcile(loser, self.approved, where, "backup", backup, NOW)
        self.assertEqual(raced[0]["action"], "resume-coordinator")
        self.assertEqual(decision["action"], "reconcile-coordinator-wake")
        self.assertEqual((len(event.send_calls), len(backup.send_calls)), (1, 0))
        self.assertEqual(len(self._final_usage()["charges"]), 1)

    def test_identical_checkpoint_values_never_share_a_commit(self):
        record = enroll(deepcopy(self.approved), self.workspace)
        same_second = {"GIT_AUTHOR_DATE": "2026-09-21T00:00:00Z", "GIT_COMMITTER_DATE": "2026-09-21T00:00:00Z"}
        with mock.patch.dict(os.environ, same_second):
            first = GitControlStore(self.first, self.store.control_ref)._commit(record, None, "delivery control checkpoint")
            second = GitControlStore(self.second, self.store.control_ref)._commit(record, None, "delivery control checkpoint")
        self.assertNotEqual(first, second)

    def test_checkpoint_failure_codes_are_a_fixed_log_safe_set(self):
        self.assertEqual(InterimCheckpointError("x", code="moved").code, "moved")
        self.assertEqual(InterimCheckpointError("x", code="provider text: secret").code, "unspecified")

    def test_corrupt_bytes_after_registered_reload_are_a_typed_reconciliation_refusal(self):
        initial = self.enrolled(); where = self._where(initial)
        adapter = FakeConductor()
        def corrupt():
            subprocess.run(["git", "fetch", "-q", "origin", "+" + where["control_ref"] + ":" + where["control_ref"]], cwd=self.second, check=True)
            subprocess.run(["git", "checkout", "-q", "-B", "corrupt-checkpoint", where["control_ref"]], cwd=self.second, check=True)
            (self.second / "mission.yml").write_bytes(b"monitoring: [\n")
            subprocess.run(["git", "add", "mission.yml"], cwd=self.second, check=True)
            subprocess.run(["git", "commit", "-qm", "corrupt checkpoint"], cwd=self.second, check=True)
            subprocess.run(["git", "push", "-q", "origin", "HEAD:" + where["control_ref"]], cwd=self.second, check=True)
        # Fetch 1 is the registered reload; corrupt the ref before reconcile's exact reload.
        with self._on_fetch(self.first, 2, corrupt):
            results = RegisteredRunner(self.first, "origin", lambda _workspace: adapter).run([where], "event")
        self.assertEqual(results, [{"run_id": where["run_id"], "control_ref": where["control_ref"], "action": "refuse",
                                    "reason": "checkpoint-reload-refused", "failure_boundary": "reconciliation",
                                    "failure_kind": "checkpoint", "failure_detail": "corrupt"}])
        self.assertEqual((adapter.monitor_calls, len(adapter.send_calls)), (0, 0))

    def test_uncontended_selected_limit_event_on_a_fresh_checkout_retires_the_run(self):
        record, snapshot = self._limited_run(); where = self._where(snapshot)
        adapter = FakeConductor()
        results = RegisteredRunner(self.second, "origin", lambda _workspace: adapter).run([where], "event")
        self.assertEqual(results, [{"run_id": where["run_id"], "action": "refuse", "reason": "selected-limit-exhausted"}])
        self.assertEqual((adapter.monitor_calls, len(adapter.send_calls)), (0, 0))

    def test_checkpoint_that_keeps_moving_is_refused_after_bounded_reload_attempts(self):
        initial = self.enrolled(); where = self._where(initial)
        adapter = FakeConductor(); fetches = []
        real = InterimCheckpointStore._git
        def counting(store, *args, check=True):
            if args and args[0] == "fetch":
                fetches.append(args)
            return real(store, *args, check=check)
        with mock.patch.object(InterimCheckpointStore, "remote_commit", return_value="0" * 40), \
                mock.patch.object(InterimCheckpointStore, "_git", counting):
            results = RegisteredRunner(self.first, "origin", lambda _workspace: adapter).run([where], "event")
        self.assertEqual(results, [{"run_id": "unavailable", "control_ref": "unavailable", "action": "refuse",
                                    "reason": "checkpoint-reload-refused", "failure_boundary": "registered-reload",
                                    "failure_kind": "checkpoint", "failure_detail": "moved"}])
        self.assertEqual((len(fetches), adapter.monitor_calls, len(adapter.send_calls)), (3, 0, 0))

    def test_discovery_refusal_names_the_listed_ref_and_failure_detail(self):
        self.enrolled()
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "a-corrupt-run"
        other_ref = "refs/heads/delivery-control/issue-a-corrupt-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "other-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "e" * 64}]
        InterimCheckpointStore(self.first, "origin", other_ref).create_and_publish(enroll(initial_record(other), self.workspace))
        subprocess.run(["git", "fetch", "origin", "+" + other_ref + ":" + other_ref], cwd=self.second, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["git", "checkout", "-q", "-B", "corrupt-checkpoint", other_ref], cwd=self.second, check=True)
        (self.second / "mission.yml").write_bytes(b"monitoring: [\n")
        subprocess.run(["git", "add", "mission.yml"], cwd=self.second, check=True)
        subprocess.run(["git", "commit", "-qm", "corrupt checkpoint"], cwd=self.second, check=True)
        subprocess.run(["git", "push", "-q", "origin", "HEAD:" + other_ref], cwd=self.second, check=True)
        runner = RegisteredRunner(self.first, "origin", lambda _workspace: FakeConductor())
        self.assertEqual([item["run_id"] for item in runner.discover()], ["run-task-413"])
        self.assertEqual(runner.discovery_outcomes, [
            {"control_ref": other_ref, "action": "refuse", "reason": "checkpoint-reload-refused",
             "failure_boundary": "discovery-reload", "failure_kind": "checkpoint", "failure_detail": "corrupt"},
        ])

    def test_registered_runner_refusal_never_echoes_untrusted_locator(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        bad = {"run_id": "untrusted-marker", "control_ref": "refs/heads/delivery-control/issue-untrusted-marker",
               "generation": "wake-marker"}
        good = {"run_id": initial.value["approval"]["run_id"], "control_ref": self.store.control_ref,
                "generation": pending["generation"]}
        outcomes = RegisteredRunner(self.first, "origin", lambda _workspace: FakeConductor()).run([bad, good], "event")
        self.assertEqual([item["action"] for item in outcomes], ["refuse", "resume-coordinator"])
        self.assertNotIn("untrusted-marker", json.dumps(outcomes))

    def test_http_adapter_requires_all_authoritative_observations_and_uses_injected_fake(self):
        good = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-21T00:00:00Z"}
        transcript = {"data": [], "offset": 0, "hasMore": False}
        record = enroll(deepcopy(self.approved), self.workspace)
        adapter = ConductorHttpAdapter(self.workspace, lambda _method, path, _body: deepcopy(transcript if "/messages" in path else good))
        self.assertEqual(adapter.monitoring_observation(record)["current_turn"], "interrupted")
        bad = deepcopy(good); del bad["updatedAt"]
        with self.assertRaises(OSError):
            ConductorHttpAdapter(self.workspace, lambda *_: bad).monitoring_observation(record)

    def test_idle_unrelated_queued_transcript_prompt_refuses_before_post_or_charge(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-21T00:00:00Z"}
        transcript = {"data": [{"id": "unrelated", "sessionId": "coordinator-1", "sessionIndex": 0,
                                  "type": "userMessage", "content": {"id": "unrelated", "state": "queued", "turnId": "turn-unrelated"},
                                  "receivedAt": "2026-09-21T00:00:00Z"}], "offset": 0, "hasMore": False}
        posts = []
        def request(method, path, body):
            if method == "POST":
                posts.append((path, body)); raise AssertionError("queued transcript prompt must refuse before POST")
            return deepcopy(transcript if "/messages" in path else status)
        refused, decision = reconcile(self.store, self.approved, where, "event", ConductorHttpAdapter(self.workspace, request))
        self.assertEqual((decision["action"], posts, refused.value["usage"]["charges"]), ("refuse", [], []))

    def test_error_and_working_coordinator_sessions_refuse_before_post_or_charge(self):
        # TASK-409 S5 amendment: the live error case is proved here offline.
        # Every non-idle status takes the same refusal path as live `working`.
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        transcript = {"data": [], "offset": 0, "hasMore": False}
        for status_value, extra in (("error", {"errorMessage": "agent crashed", "lastError": "crash", "lastErrorAt": "2026-09-21T00:00:00Z"}),
                                    ("working", {})):
            with self.subTest(status=status_value):
                status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": status_value,
                          "updatedAt": "2026-09-21T00:00:00Z", **extra}
                posts = []
                def request(method, path, body, status=status):
                    if method == "POST":
                        posts.append(path); raise AssertionError("a non-idle coordinator must refuse before POST")
                    return deepcopy(transcript if "/messages" in path else status)
                refused, decision = reconcile(self.store, self.approved, where, "event", ConductorHttpAdapter(self.workspace, request))
                self.assertEqual(decision, {"action": "refuse", "reason": "host-observation-unavailable-or-ineligible"})
                self.assertEqual((posts, refused.value["usage"]["charges"], refused.value["usage"]["launches"]), ([], [], []))
                self.assertEqual(refused.value["monitoring"]["state"], "active")

    def test_http_adapter_accepts_live_additive_message_metadata_and_refuses_identity_conflicts(self):
        """The v0 transcript carries supported metadata beyond the three policy fields."""
        status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-22T17:49:00Z"}
        user = {"id": "transport-user-1", "sessionId": "coordinator-1", "sessionIndex": 7,
                "type": "userMessage", "receivedAt": "2026-09-22T17:49:00Z", "content": {
                    "id": "user-1", "state": "sent", "turnId": "turn-1", "type": "userMessage",
                    "config": {"model": "gpt-5.6-terra"}, "deliveryAttemptId": "delivery-1",
                    "eventId": "event-1", "message": "continue", "senderApiKeyName": "monitor",
                    "senderId": "sender-1"}}
        def agent(event_type):
            return {"id": "transport-agent-" + event_type, "sessionId": "coordinator-1", "sessionIndex": 8,
                    "type": "agent", "receivedAt": "2026-09-22T17:49:01Z", "content": {
                        "turnId": "turn-1", "userMessageId": "user-1", "eventId": "agent-" + event_type,
                        "rawPayload": {"event": {"type": event_type}}}}
        transcript = {"data": [user, agent("turn.started"), agent("turn.completed")], "offset": 0, "hasMore": False}
        adapter = ConductorHttpAdapter(self.workspace, lambda _method, path, _body: deepcopy(transcript if "/messages" in path else status))
        self.assertEqual(adapter.monitoring_observation(enroll(deepcopy(self.approved), self.workspace))["pending_messages"], False)

        def prompt(message_id="user-1", turn_id="turn-1", state="queued"):
            return [{"id": "transport-" + message_id + "-" + turn_id, "sessionId": "coordinator-1", "sessionIndex": 0,
                     "type": "userMessage", "receivedAt": "2026-09-22T17:49:00Z",
                     "content": {"id": message_id, "state": state, "turnId": turn_id, "eventId": "extra"}}]

        malformed = prompt()[0]
        for field, value in (("id", ""), ("state", "unknown"), ("turnId", None)):
            candidate = deepcopy(malformed)
            if value is None:
                del candidate["content"][field]
            else:
                candidate["content"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(OSError, "content/state/turn identity"):
                adapter._unconsumed_prompt([candidate])
        with self.assertRaisesRegex(OSError, "conflicting user message identities"):
            adapter._unconsumed_prompt(prompt("user-1", "turn-1") + prompt("user-1", "turn-2"))
        with self.assertRaisesRegex(OSError, "conflicting user message identities"):
            adapter._unconsumed_prompt(prompt("user-1", "turn-1") + prompt("user-2", "turn-1"))
        with self.assertRaisesRegex(OSError, "queued prompt has conflicting turn events"):
            adapter._unconsumed_prompt(prompt() + [agent("turn.started")])
        sent = prompt(state="sent")
        with self.assertRaisesRegex(OSError, "lacks a correlated started turn"):
            adapter._unconsumed_prompt(sent)

    def test_http_adapter_refuses_unhashable_and_malformed_top_level_values_without_aborting_overlap(self):
        status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-22T17:49:00Z"}

        def transcript(content=None):
            return {"data": [{"id": "transport-user-1", "sessionId": "coordinator-1", "sessionIndex": 0,
                              "type": "userMessage", "receivedAt": "2026-09-22T17:49:00Z",
                              "content": content or {"id": "user-1", "state": "queued", "turnId": "turn-1"}}],
                    "offset": 0, "hasMore": False}

        def adapter(current_status=status, current_transcript=None):
            return ConductorHttpAdapter(self.workspace, lambda _method, path, _body: deepcopy(current_transcript if "/messages" in path else current_status))

        record = enroll(deepcopy(self.approved), self.workspace)
        with self.assertRaisesRegex(OSError, "content/state/turn identity"):
            adapter(current_transcript=transcript({"id": "user-1", "state": [], "turnId": "turn-1"})).monitoring_observation(record)
        bad_status = deepcopy(status); bad_status["status"] = []
        with self.assertRaisesRegex(OSError, "session identity or status"):
            adapter(current_status=bad_status, current_transcript=transcript()).monitoring_observation(record)
        for field, value in (("sessionIndex", "0"), ("sessionIndex", -1), ("type", []), ("receivedAt", 0)):
            malformed = transcript(); malformed["data"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(OSError, "transcript item"):
                adapter(current_transcript=malformed).monitoring_observation(record)
        malformed_agent = transcript(); malformed_agent["data"][0]["type"] = "agent"; malformed_agent["data"][0]["content"] = []
        with self.assertRaisesRegex(OSError, "transcript item"):
            adapter(current_transcript=malformed_agent).monitoring_observation(record)

        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        bad_where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "later-valid-run"
        other_ref = "refs/heads/delivery-control/issue-later-valid-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "later-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "e" * 64}]
        other_workspace = "22222222-2222-4222-8222-222222222222"
        later = InterimCheckpointStore(self.first, "origin", other_ref).create_and_publish(enroll(initial_record(other), other_workspace))
        later_pending = later.value["monitoring"]["pending_wake"]
        later_where = {"run_id": other["run_id"], "control_ref": other_ref, "generation": later_pending["generation"]}
        calls = []
        def factory(workspace):
            calls.append(workspace)
            if workspace == self.workspace:
                return adapter(current_transcript=malformed_agent)
            return FakeConductor()
        results = RegisteredRunner(self.first, "origin", factory).run([bad_where, later_where], "backup")
        self.assertEqual(results, [
            {"run_id": bad_where["run_id"], "action": "refuse", "reason": "host-observation-unavailable-or-ineligible"},
            {"run_id": later_where["run_id"], "action": "resume-coordinator", "reason": "accepted"},
        ])
        self.assertEqual(calls, [self.workspace, other_workspace])

    def test_http_adapter_refuses_malformed_wake_receipts_without_aborting_overlap(self):
        status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-22T17:49:00Z"}
        empty = {"data": [], "offset": 0, "hasMore": False}
        operation = {"id": "wake-1", "session_id": "coordinator-1", "message_id": "message-1", "terminal_turn_id": "turn-1"}

        def adapter(receipt):
            return ConductorHttpAdapter(self.workspace, lambda method, path, _body: deepcopy(receipt if method == "POST" else empty if "/messages" in path else status))

        for field, value in (("messageId", []), ("state", []), ("deepLink", [])):
            receipt = {"messageId": "message-1", "state": "queued", "deepLink": "conductor://message/1"}
            receipt[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(OSError, "wake receipt"):
                adapter(receipt).send_wake(operation)

        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        bad_where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "later-wake-valid-run"
        other_ref = "refs/heads/delivery-control/issue-later-wake-valid-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "later-wake-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "f" * 64}]
        other_workspace = "33333333-3333-4333-8333-333333333333"
        later = InterimCheckpointStore(self.first, "origin", other_ref).create_and_publish(enroll(initial_record(other), other_workspace))
        later_pending = later.value["monitoring"]["pending_wake"]
        later_where = {"run_id": other["run_id"], "control_ref": other_ref, "generation": later_pending["generation"]}
        bad_receipt = {"messageId": "message-1", "state": [], "deepLink": "conductor://message/1"}
        calls = []
        def factory(workspace):
            calls.append(workspace)
            return adapter(bad_receipt) if workspace == self.workspace else FakeConductor()
        results = RegisteredRunner(self.first, "origin", factory).run([bad_where, later_where], "backup")
        self.assertEqual(results, [
            {"run_id": bad_where["run_id"], "action": "resume-coordinator", "reason": "accepted"},
            {"run_id": later_where["run_id"], "action": "resume-coordinator", "reason": "accepted"},
        ])
        self.assertEqual(calls, [self.workspace, other_workspace])

    def test_http_adapter_refuses_unsupported_transcript_types_before_a_hidden_prompt_can_send(self):
        status = {"workspaceId": self.workspace, "sessionId": "coordinator-1", "status": "idle", "updatedAt": "2026-09-22T17:49:00Z"}
        hidden_prompt = {"data": [{"id": "transport-hidden-1", "sessionId": "coordinator-1", "sessionIndex": 0,
                                   "type": "unsupported", "receivedAt": "2026-09-22T17:49:00Z",
                                   "content": {"id": "hidden-1", "state": "queued", "turnId": "turn-hidden-1"}}],
                         "offset": 0, "hasMore": False}
        posts = []
        def adapter():
            def request(method, path, _body):
                if method == "POST":
                    posts.append(path)
                    return {"messageId": "message-1", "state": "queued", "deepLink": "conductor://message/1"}
                return deepcopy(hidden_prompt if "/messages" in path else status)
            return ConductorHttpAdapter(self.workspace, request)

        record = enroll(deepcopy(self.approved), self.workspace)
        with self.assertRaisesRegex(OSError, "transcript item"):
            adapter().monitoring_observation(record)

        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        bad_where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        other = approval(str(self.remote), str(self.remote)); other["run_id"] = "later-type-valid-run"
        other_ref = "refs/heads/delivery-control/issue-later-type-valid-run"
        other["repository"]["control_ref"] = other_ref; other["checkpoint"]["ref"] = other_ref
        other["tasks"] = [{"id": "later-type-task", "slice_id": "TASK-413", "spec_revision": other["tracker"]["spec_revision"], "digest": "sha256:" + "a" * 64}]
        other_workspace = "44444444-4444-4444-8444-444444444444"
        later = InterimCheckpointStore(self.first, "origin", other_ref).create_and_publish(enroll(initial_record(other), other_workspace))
        later_pending = later.value["monitoring"]["pending_wake"]
        later_where = {"run_id": other["run_id"], "control_ref": other_ref, "generation": later_pending["generation"]}
        calls = []
        def factory(workspace):
            calls.append(workspace)
            return adapter() if workspace == self.workspace else FakeConductor()
        results = RegisteredRunner(self.first, "origin", factory).run([bad_where, later_where], "backup")
        self.assertEqual(results, [
            {"run_id": bad_where["run_id"], "action": "refuse", "reason": "host-observation-unavailable-or-ineligible"},
            {"run_id": later_where["run_id"], "action": "resume-coordinator", "reason": "accepted"},
        ])
        self.assertEqual((posts, calls), ([], [self.workspace, other_workspace]))

    def test_timeout_terminal_retirement_allows_same_wake_observe_only_reconciliation(self):
        initial = self.enrolled(); pending = initial.value["monitoring"]["pending_wake"]
        where = {"run_id": initial.value["approval"]["run_id"], "control_ref": initial.value["monitoring"]["control_ref"], "generation": pending["generation"]}
        class AppendedThenTimeout(FakeConductor):
            def send_wake(self, operation):
                self.send_calls.append(deepcopy(operation))
                raise TimeoutError("accepted after transport timeout")
        first = AppendedThenTimeout()
        timed_out, first_decision = reconcile(self.store, self.approved, where, "event", first)
        self.assertEqual((first_decision["action"], timed_out.value["monitoring"]["state"], len(first.send_calls)),
                         ("resume-coordinator", "inactive", 1))
        settled, second_decision = reconcile(self.store, self.approved, where, "backup", FakeConductor())
        wake = next(item for item in settled.value["usage"]["operations"] if item["phase"] == "wake")
        charges = [item for item in settled.value["usage"]["charges"] if item["operation_id"] == wake["id"]]
        self.assertEqual((second_decision["action"], wake["status"], len(charges)), ("reconcile-coordinator-wake", "accounted", 1))

    def test_monitored_store_lifecycle_is_used_by_shipped_coordinator_families(self):
        from delivery_pilot.interim_coordinator import InterimFixtureCoordinator
        from delivery_pilot.interim_recovery import InterimRecoveryCoordinator
        from delivery_pilot.interim_repair_coordinator import InterimRepairCoordinator
        from delivery_pilot.interim_stack import InterimStackCoordinator
        # The real monitor-start store enrolls without the former helper API.
        item = approval(str(self.remote), str(self.remote)); item["run_id"] = "lifecycle-run"
        ref = "refs/heads/delivery-control/issue-lifecycle-run"; item["repository"]["control_ref"] = ref; item["checkpoint"]["ref"] = ref
        item["tasks"] = [{"id": "lifecycle-task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "f" * 64}]
        calls = []; store = InterimCheckpointStore(self.first, "origin", ref).monitored(self.workspace, calls.append)
        root = store.create_and_publish(initial_record(item))
        self.assertEqual(root.value["monitoring"]["state"], "active")
        # All production coordinator persistence seams route through the same
        # lifecycle method; ordinary legacy records remain on raw persistence.
        for coordinator in (InterimFixtureCoordinator(store), InterimRecoveryCoordinator(store),
                            InterimRepairCoordinator(store), InterimStackCoordinator(store)):
            self.assertIn("persist_lifecycle", type(coordinator)._persist.__code__.co_names)
        advanced = InterimFixtureCoordinator(store)._persist(root, deepcopy(root.value))
        self.assertEqual((advanced.value["monitoring"]["pending_wake"]["checkpoint_parent_commit"], len(calls)),
                         (root.commit_sha, 1))

    def test_http_transport_uses_official_v0_paths_headers_and_message_body_without_live_provider(self):
        seen = []
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.command, self.path, self.headers.get("Authorization"), self.headers.get("User-Agent"), None))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(b'{"workspaceId":"w","sessionId":"s","status":"idle","updatedAt":"now"}')
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                seen.append((self.command, self.path, self.headers.get("Authorization"), self.headers.get("User-Agent"), body))
                self.send_response(201); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(b'{"messageId":"m","state":"queued","deepLink":"conductor://m"}')
            def log_message(self, *_args): pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            request = http_request(f"http://127.0.0.1:{server.server_port}", "not-a-real-token")
            request("GET", "/v0/sessions/s/status", None)
            request("POST", "/v0/sessions/s/messages", {"messageId": "m", "message": "resume"})
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertEqual(seen[0][:4], ("GET", "/v0/sessions/s/status", "Bearer not-a-real-token", "playbook-recovery/1"))
        self.assertEqual(seen[1], ("POST", "/v0/sessions/s/messages", "Bearer not-a-real-token", "playbook-recovery/1", '{"message":"resume","messageId":"m"}'))

    def test_http_streaming_body_cannot_extend_event_elapsed_budget(self):
        payload = json.dumps({"padding": "x" * 80}).encode()
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    for byte in payload:
                        self.wfile.write(bytes([byte])); self.wfile.flush(); time.sleep(0.015)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *_args): pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            request = http_request(f"http://127.0.0.1:{server.server_port}", "fixture-only-token", timeout=.05)
            start = time.monotonic()
            request.set_event_deadline(start + .08, time.monotonic)
            with self.assertRaises(OSError):
                request("GET", "/v0/sessions/s/status", None)
            elapsed = time.monotonic() - start
        finally:
            server.shutdown(); thread.join(); server.server_close()
        self.assertLess(elapsed, .5)

    def test_event_http_transport_accepts_complete_local_response(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = b'{"status":"idle"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            def log_message(self, *_args): pass
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            request = http_request(f"http://127.0.0.1:{server.server_port}", "fixture-only-token")
            request.set_event_deadline(time.monotonic() + 1, time.monotonic)
            self.assertEqual(request("GET", "/v0/sessions/one/status", None), {"status": "idle"})
        finally:
            server.shutdown(); thread.join(); server.server_close()




if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import subprocess
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim import InterimCheckpointError, InterimCheckpointStore, initial_record, InterimError, validate_record  # noqa: E402
from delivery_pilot.interim_recovery import wake_operation_id  # noqa: E402
from delivery_pilot.interim_watchdog import PREFIX, admit, parse_opt_in, prompt_config, reserve_and_persist, reserve_wake, resume_and_reconcile, wake_id  # noqa: E402
from test_interim import approval  # noqa: E402


class WatchdogFixture:
    """Deterministic host seam: each observation is for one durable wake ID."""

    def __init__(self, send_results=None, observations=None):
        self.send_results = list(send_results or [])
        self.observations = list(observations or [])
        self.send_calls = []
        self.observe_calls = []

    def coordinators(self, approved):
        return [{"session_id": approved["coordinator"]["session_id"]}]

    @staticmethod
    def receipt(operation, result):
        if isinstance(result, BaseException):
            raise result
        observation = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        if result == "accepted":
            return {"observation": observation, "transport": "accepted", "worker_state": "terminal", "elapsed_seconds": 1}
        if result == "mismatched":
            observation["id"] = "wrong-operation"
            return {"observation": observation, "transport": "accepted", "worker_state": "terminal", "elapsed_seconds": 1}
        return result

    def send_wake(self, operation):
        self.send_calls.append(deepcopy(operation))
        return self.receipt(operation, self.send_results.pop(0) if self.send_results else "accepted")

    def observe(self, operation):
        self.observe_calls.append(deepcopy(operation))
        return self.receipt(operation, self.observations.pop(0) if self.observations else "accepted")


class InterimWatchdogTests(unittest.TestCase):
    def setUp(self) -> None:
        item = approval()
        item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
        self.record = initial_record(item)
        self.title = (PREFIX + " run=run-task-413 mode=interim-coordinator "
                      "checkpoint=refs/heads/delivery-control/issue-run-task-413 "
                      "progress=worker-result-and-forecast-exceeded hard_limits=none")
        self.observation = {"current_turn": "interrupted", "pending_messages": False, "pending_effects": False}

    def verified_terminal(self):
        """Build a valid terminal checkpoint through the shipped offline flow."""
        from delivery_pilot.interim_advance import advance_once, github_pr_readback
        from test_interim_advance import AdvanceTests, PhaseHost

        base = AdvanceTests("run")
        base.setUp()
        try:
            approved = base.s2_approval()
            approved["slices"] = approved["slices"][:1]
            approved["repository"].update(fetch_url="https://github.com/acme/approved.git",
                                          push_url="https://github.com/acme/approved.git", base_ref="refs/heads/main")
            record = initial_record(approved)
            store = base.store(base.first)
            store._assert_approved_target = lambda _: None  # local bare Git CAS fixture
            store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _: None)
            store.create_and_publish(record)
            url = "https://github.com/acme/approved/pull/7"
            host = PhaseHost(base, url)
            task = {"TASK-413": base.task()}
            self.assertEqual(advance_once(store, record, task, host)["outcome"], "verify")
            self.assertEqual(advance_once(store, record, task, host)["outcome"], "pr-ready")
            pr = {"number": 7, "html_url": url, "state": "open",
                  "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "acme/approved"}},
                  "head": {"sha": "a" * 40, "repo": {"full_name": "acme/approved"}}}
            readback = lambda value, claimed: github_pr_readback(value, claimed, lambda _: pr)
            self.assertEqual(advance_once(store, record, task, host, pr_readback=readback)["outcome"], "review-ready")
            terminal = store.reload(record).value
            self.assertEqual(validate_record(terminal)["state"]["next_action"], "review-ready")
            self.assertEqual(len(host.sent), 2)
            return terminal
        finally:
            base.tearDown()

    def test_strict_opt_in_and_legacy_separation(self) -> None:
        self.assertIsNone(parse_opt_in("Unattended: deadline=2026-09-20 cap=2"))
        self.assertEqual(parse_opt_in(self.title)["mode"], "interim-coordinator")
        with self.assertRaisesRegex(InterimError, "missing"):
            parse_opt_in(PREFIX + " run=x")

    def test_only_exact_coordinator_and_identity_are_eligible(self) -> None:
        self.assertEqual(admit(self.record, self.title, "worker-1", "evt", self.observation)["reason"], "not-approved-coordinator")
        self.assertEqual(admit(self.record, self.title.replace("run=run-task-413", "run=other"), "coordinator-1", "evt", self.observation)["reason"], "interim-identity-mismatch")
        admitted = admit(self.record, self.title, "coordinator-1", "evt", self.observation)
        self.assertEqual(admitted["action"], "resume-coordinator")
        self.assertFalse(admitted["dispatch_worker"])

    def test_current_pending_terminal_and_selected_cap_refuse(self) -> None:
        for key, value in (("current_turn", "active"), ("pending_messages", True), ("pending_effects", True)):
            observation = deepcopy(self.observation); observation[key] = value
            self.assertEqual(admit(self.record, self.title, "coordinator-1", "evt", observation)["action"], "refuse")
        fabricated = deepcopy(self.record); fabricated["state"]["next_action"] = "review-ready"
        with self.assertRaisesRegex(InterimError, "accepted ordinary Build/Verify pair"):
            admit(fabricated, self.title, "coordinator-1", "evt", self.observation)
        terminal = self.verified_terminal()
        self.assertEqual(admit(terminal, self.title, "coordinator-1", "evt", self.observation)["reason"], "terminal-or-stopping-run")
        unchanged, refusal = reserve_wake(terminal, self.title, "coordinator-1", "evt", self.observation)
        self.assertEqual(refusal["reason"], "terminal-or-stopping-run")
        self.assertEqual(unchanged["usage"], terminal["usage"])
        capped_approval = approval(); capped_approval["hard_limits"] = {"dispatch_max": 1}
        capped_approval["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": capped_approval["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
        capped = initial_record(capped_approval)
        capped_title = self.title.replace("hard_limits=none", "hard_limits=selected")
        reserved, _ = reserve_wake(capped, capped_title, "coordinator-1", "one", self.observation)
        self.assertEqual(admit(reserved, capped_title, "coordinator-1", "two", self.observation)["reason"], "prior-wake-reconciliation-required")

    def test_stable_wake_identity_no_cap_and_no_complete(self) -> None:
        first = admit(self.record, self.title, "coordinator-1", "same-event", self.observation)
        duplicate = admit(self.record, self.title, "coordinator-1", "same-event", self.observation)
        second = admit(self.record, self.title, "coordinator-1", "later-event", self.observation)
        self.assertEqual(first["wake_id"], duplicate["wake_id"])
        self.assertNotEqual(first["wake_id"], second["wake_id"])
        self.assertEqual(first["wake_id"], wake_id("run-task-413", "same-event"))
        self.assertEqual(prompt_config()["complete_only_for"], "whole-run-review-ready")

    def test_reservation_accounts_once_and_reuses_duplicate_event(self) -> None:
        now = datetime(2026, 9, 20, tzinfo=timezone.utc)
        reserved, first = reserve_wake(self.record, self.title, "coordinator-1", "event-1", self.observation, now)
        self.assertEqual(first["action"], "resume-coordinator")
        self.assertEqual(len(reserved["usage"]["operations"]), 1)
        self.assertEqual(reserved["usage"]["charges"][0]["status"], "pending")
        repeated, second = reserve_wake(reserved, self.title, "coordinator-1", "event-1", self.observation, now)
        self.assertEqual(second["action"], "reconcile-coordinator-wake")
        self.assertEqual(len(repeated["usage"]["launches"]), 1)
        validate_record(repeated)

    def test_accepted_receipts_settle_each_interrupted_turn_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"])
            initial = store.create_and_publish(initial_record(item))
            fixture = WatchdogFixture()
            settled, decision = resume_and_reconcile(store, initial, self.title, "coordinator-1", "first-event", self.observation, fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
            operation = next(item for item in settled.value["usage"]["operations"] if item["phase"] == "wake")
            charge = next(item for item in settled.value["usage"]["charges"] if item["operation_id"] == operation["id"])
            self.assertEqual((decision["action"], operation["status"], charge["status"]), ("resume-coordinator", "accounted", "observed"))
            self.assertEqual((len(fixture.send_calls), len(fixture.observe_calls)), (1, 0))
            self.assertEqual(operation["id"], wake_operation_id(settled.value, decision["wake_id"]))
            duplicate_fixture = WatchdogFixture()
            duplicate, duplicate_decision = resume_and_reconcile(store, settled, self.title, "coordinator-1", "first-event", self.observation, duplicate_fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
            self.assertEqual((duplicate_decision["action"], duplicate.value["usage"]), ("reconcile-coordinator-wake", settled.value["usage"]))
            self.assertEqual((len(duplicate_fixture.send_calls), len(duplicate_fixture.observe_calls)), (0, 0))
            later_fixture = WatchdogFixture()
            later, later_decision = resume_and_reconcile(store, duplicate, self.title, "coordinator-1", "later-event", self.observation, later_fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
            wakes = [item for item in later.value["usage"]["operations"] if item["phase"] == "wake"]
            self.assertEqual((len(wakes), len({item["id"] for item in wakes}), later_decision["wake_id"] == decision["wake_id"]), (2, 2, False))
            self.assertTrue(all(item["status"] == "accounted" for item in wakes))
            self.assertEqual((len(later_fixture.send_calls), len(later_fixture.observe_calls)), (1, 0))

    def test_timeout_then_clean_reload_reconciles_without_a_second_charge_or_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; first = root / "first"; second = root / "second"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            for checkout in (first, second):
                subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
                subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            store_one = InterimCheckpointStore(first, "origin", item["checkpoint"]["ref"])
            initial = store_one.create_and_publish(initial_record(item))
            first_fixture = WatchdogFixture(send_results=[TimeoutError("provider detail must not persist")])
            timed_out, first_decision = resume_and_reconcile(store_one, initial, self.title, "coordinator-1", "initial-event", self.observation, first_fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
            pending = next(item for item in timed_out.value["usage"]["operations"] if item["phase"] == "wake")
            self.assertEqual((pending["status"], timed_out.value["state"]["next_action"]), ("reconcile-required", "handback"))
            self.assertNotIn("provider detail must not persist", timed_out.value["state"]["handback"]["reason"])
            self.assertEqual((len(first_fixture.send_calls), len(first_fixture.observe_calls)), (1, 0))
            store_two = InterimCheckpointStore(second, "origin", item["checkpoint"]["ref"])
            reloaded = store_two.reload(initial_record(item))
            delayed = WatchdogFixture()
            reconciled, second_decision = resume_and_reconcile(store_two, reloaded, self.title, "coordinator-1", "initial-event", self.observation, delayed, datetime(2026, 9, 20, tzinfo=timezone.utc))
            wake_operations = [item for item in reconciled.value["usage"]["operations"] if item["phase"] == "wake"]
            charges = [item for item in reconciled.value["usage"]["charges"] if item["operation_id"] == pending["id"]]
            self.assertEqual((first_decision["wake_id"], second_decision["wake_id"], second_decision["action"]), (first_decision["wake_id"], first_decision["wake_id"], "reconcile-coordinator-wake"))
            self.assertEqual((len(wake_operations), len(charges), wake_operations[0]["status"], charges[0]["status"]), (1, 1, "accounted", "observed"))
            self.assertEqual((len(delayed.send_calls), [call["id"] for call in delayed.observe_calls]), (0, [pending["id"]]))

    def test_timeout_then_distinct_event_refuses_before_a_successor_reservation_or_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"])
            initial = store.create_and_publish(initial_record(item))
            first = WatchdogFixture(send_results=[TimeoutError("provider detail must not persist")])
            pending, first_decision = resume_and_reconcile(store, initial, self.title, "coordinator-1", "event-a", self.observation, first, datetime(2026, 9, 20, tzinfo=timezone.utc))
            second = WatchdogFixture()
            refused, second_decision = resume_and_reconcile(store, pending, self.title, "coordinator-1", "event-b", self.observation, second, datetime(2026, 9, 20, tzinfo=timezone.utc))
            wake_operations = [item for item in refused.value["usage"]["operations"] if item["phase"] == "wake"]
            charges = [item for item in refused.value["usage"]["charges"] if item["operation_id"] == wake_operations[0]["id"]]
            self.assertEqual((first_decision["action"], second_decision), ("resume-coordinator", {"action": "refuse", "reason": "prior-wake-reconciliation-required", "operation_id": wake_operations[0]["id"]}))
            self.assertEqual((len(wake_operations), len(charges), wake_operations[0]["status"], charges[0]["status"], len(first.send_calls), len(second.send_calls)), (1, 1, "reconcile-required", "pending", 1, 0))

    def test_selected_last_slot_timeout_reloads_same_event_for_exact_settlement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; first = root / "first"; second = root / "second"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            for checkout in (first, second):
                subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
                subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["hard_limits"] = {"dispatch_max": 1}; item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            title = self.title.replace("hard_limits=none", "hard_limits=selected")
            store_one = InterimCheckpointStore(first, "origin", item["checkpoint"]["ref"])
            initial = store_one.create_and_publish(initial_record(item))
            first_fixture = WatchdogFixture(send_results=[TimeoutError("provider detail must not persist")])
            timed_out, first_decision = resume_and_reconcile(store_one, initial, title, "coordinator-1", "event-a", self.observation, first_fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
            store_two = InterimCheckpointStore(second, "origin", item["checkpoint"]["ref"])
            reloaded = store_two.reload(initial_record(item)); delayed = WatchdogFixture()
            settled, second_decision = resume_and_reconcile(store_two, reloaded, title, "coordinator-1", "event-a", self.observation, delayed, datetime(2026, 9, 20, tzinfo=timezone.utc))
            wake_operations = [item for item in settled.value["usage"]["operations"] if item["phase"] == "wake"]
            charges = [item for item in settled.value["usage"]["charges"] if item["operation_id"] == wake_operations[0]["id"]]
            self.assertEqual((first_decision["action"], second_decision["action"], len(wake_operations), len(charges), wake_operations[0]["status"], charges[0]["status"]), ("resume-coordinator", "reconcile-coordinator-wake", 1, 1, "accounted", "observed"))
            self.assertEqual((len(first_fixture.send_calls), len(delayed.send_calls), [call["id"] for call in delayed.observe_calls]), (1, 0, [wake_operations[0]["id"]]))

    def test_same_pending_event_reconciles_after_selected_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["hard_limits"] = {"deadline_at": "2026-09-20T00:00:00Z"}; item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            title = self.title.replace("hard_limits=none", "hard_limits=selected")
            store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"])
            initial = store.create_and_publish(initial_record(item))
            first = WatchdogFixture(send_results=[TimeoutError("provider detail must not persist")])
            timed_out, _ = resume_and_reconcile(store, initial, title, "coordinator-1", "event-a", self.observation, first, datetime(2026, 9, 19, tzinfo=timezone.utc))
            delayed = WatchdogFixture()
            settled, decision = resume_and_reconcile(store, timed_out, title, "coordinator-1", "event-a", self.observation, delayed, datetime(2026, 9, 21, tzinfo=timezone.utc))
            wake_operation = next(item for item in settled.value["usage"]["operations"] if item["phase"] == "wake")
            self.assertEqual((decision["action"], wake_operation["status"], len(delayed.send_calls), [call["id"] for call in delayed.observe_calls]), ("reconcile-coordinator-wake", "accounted", 0, [wake_operation["id"]]))

    def test_settled_wake_allows_successor_only_when_selected_limits_allow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
            subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
            item = approval(str(remote), str(remote)); item["hard_limits"] = {"dispatch_max": 1}; item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            title = self.title.replace("hard_limits=none", "hard_limits=selected")
            store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"])
            initial = store.create_and_publish(initial_record(item))
            settled, first_decision = resume_and_reconcile(store, initial, title, "coordinator-1", "event-a", self.observation, WatchdogFixture(), datetime(2026, 9, 20, tzinfo=timezone.utc))
            refused, second_decision = resume_and_reconcile(store, settled, title, "coordinator-1", "event-b", self.observation, WatchdogFixture(), datetime(2026, 9, 20, tzinfo=timezone.utc))
            self.assertEqual((first_decision["action"], second_decision), ("resume-coordinator", {"action": "refuse", "reason": "selected-dispatch-cap-reached"}))

    def test_malformed_or_mismatched_receipts_fail_closed(self) -> None:
        for label, fixture in (("malformed", WatchdogFixture(send_results=[{"not": "a receipt"}])), ("mismatched", WatchdogFixture(send_results=["mismatched"]))):
            with self.subTest(label=label):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory); remote = root / "remote.git"; checkout = root / "checkout"
                    subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
                    subprocess.run(["git", "clone", "-q", str(remote), str(checkout)], check=True)
                    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=checkout, check=True)
                    subprocess.run(["git", "config", "user.name", "Test"], cwd=checkout, check=True)
                    item = approval(str(remote), str(remote)); item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
                    store = InterimCheckpointStore(checkout, "origin", item["checkpoint"]["ref"])
                    initial = store.create_and_publish(initial_record(item))
                    failed, decision = resume_and_reconcile(store, initial, self.title, "coordinator-1", label, self.observation, fixture, datetime(2026, 9, 20, tzinfo=timezone.utc))
                    operation = next(item for item in failed.value["usage"]["operations"] if item["phase"] == "wake")
                    charge = next(item for item in failed.value["usage"]["charges"] if item["operation_id"] == operation["id"])
                    self.assertEqual((decision["action"], operation["status"], charge["status"], failed.value["state"]["next_action"]), ("resume-coordinator", "reconcile-required", "pending", "handback"))
                    self.assertIn("malformed", failed.value["state"]["handback"]["reason"])
                    self.assertEqual((len(fixture.send_calls), len(fixture.observe_calls)), (1, 0))

    def test_intermediate_repair_completion_remains_eligible_but_whole_run_terminal_refuses(self) -> None:
        import test_interim_repair as repair_tests

        base = repair_tests.RepairPolicyTests("run")
        base.setUp()
        try:
            coordinator, diagnosed = base.open_and_diagnose()
            completed = coordinator.repair_once(diagnosed, "TASK-413", base.task(), repair_tests.RepairFixture("pass"), repair_tests.RepairFixture("pass"))
            self.assertEqual((completed.value["repair"]["status"], completed.value["state"]["next_action"]), ("completed", "repair-complete"))
            completed_title = (PREFIX + " run=run-task-413 mode=interim-coordinator "
                               "checkpoint=refs/heads/delivery-control/issue-run-task-413 "
                               "progress=worker-result-and-forecast-exceeded hard_limits=none")
            self.assertEqual(admit(completed.value, completed_title, "coordinator-1", "late", self.observation)["action"], "resume-coordinator")
            base.tearDown(); base.setUp()
            coordinator = repair_tests.InterimRepairCoordinator(base.store(base.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
            finding, evidence = base.finding()
            opened = coordinator.open(base.failed_s2(), "TASK-413", base.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
            repair_handback = coordinator.diagnose(opened, "TASK-413", base.task(), repair_tests.RepairFixture(actionable=False))
            self.assertEqual(admit(repair_handback.value, completed_title, "coordinator-1", "late", self.observation)["reason"], "terminal-or-stopping-run")
            base.tearDown(); base.setUp()
            coordinator, stuck = base.open_and_diagnose()
            for _ in range(3):
                stuck = coordinator.repair_once(stuck, "TASK-413", base.task(), repair_tests.RepairFixture("fail", distinct=True), repair_tests.RepairFixture("fail", distinct=True))
            self.assertEqual(stuck.value["repair"]["status"], "stuck")
            self.assertEqual(admit(stuck.value, completed_title, "coordinator-1", "late", self.observation)["reason"], "terminal-or-stopping-run")
        finally:
            base.tearDown()
        terminal = self.verified_terminal()
        self.assertEqual(admit(terminal, self.title, "coordinator-1", "late", self.observation)["reason"], "terminal-or-stopping-run")

    def test_completed_afk_slice_pr_ready_remains_coordinator_resumable_for_next_afk_frontier(self) -> None:
        from delivery_pilot.interim_coordinator import InterimFixtureCoordinator
        from delivery_pilot.interim_recovery import InterimRecoveryCoordinator
        from test_interim_coordinator import CoordinatorTests, Fixture

        base = CoordinatorTests("run")
        base.setUp()
        try:
            approved = base.s2_approval()
            approved["slices"][1]["mode"] = "AFK"
            store = base.store(base.first)
            initial = store.create_and_publish(initial_record(approved))
            completed = InterimFixtureCoordinator(store).run_one(
                initial, "TASK-413", base.task(), Fixture(base.result()), Fixture(base.result("verify")))

            self.assertEqual(completed.value["state"]["next_action"], "pr-ready")
            self.assertEqual(completed.value["approval"]["slices"][1],
                             {"id": "TASK-419", "dependencies": ["TASK-413"], "mode": "AFK"})
            admitted = admit(completed.value, self.title, "coordinator-1", "after-first-slice", self.observation)
            self.assertEqual(admitted["action"], "resume-coordinator")
            self.assertFalse(admitted["dispatch_worker"])

            recovered = InterimRecoveryCoordinator(store).recover(completed.value, "after-first-slice", WatchdogFixture())
            wake = next(item for item in recovered.value["usage"]["operations"] if item["phase"] == "wake")
            self.assertEqual((recovered.value["state"]["next_action"], wake["status"]), ("pr-ready", "accounted"))
        finally:
            base.tearDown()

    def test_stale_snapshot_cannot_spend_last_selected_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); remote = root / "remote.git"; first = root / "first"; second = root / "second"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
            for clone in (first, second):
                subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
                subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=clone, check=True)
                subprocess.run(["git", "config", "user.name", "Test"], cwd=clone, check=True)
            item = approval(str(remote), str(remote)); item["hard_limits"] = {"dispatch_max": 1}
            item["tasks"] = [{"id": "task", "slice_id": "TASK-413", "spec_revision": item["tracker"]["spec_revision"], "digest": "sha256:" + "b" * 64}]
            record = initial_record(item); store_one = InterimCheckpointStore(first, "origin", item["checkpoint"]["ref"])
            original = store_one.create_and_publish(record)
            store_two = InterimCheckpointStore(second, "origin", item["checkpoint"]["ref"]); stale = store_two.reload(record)
            title = self.title.replace("hard_limits=none", "hard_limits=selected")
            published, _ = reserve_and_persist(store_one, original, title, "coordinator-1", "one", self.observation)
            with self.assertRaisesRegex(InterimCheckpointError, "moved"):
                reserve_and_persist(store_two, stale, title, "coordinator-1", "two", self.observation)
            self.assertEqual(len(published.value["usage"]["launches"]), 1)

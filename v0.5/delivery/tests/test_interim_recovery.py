from __future__ import annotations

import sys
import runpy
import unittest
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim import InterimCheckpointError, initial_record, validate_record  # noqa: E402
from delivery_pilot.interim_recovery import InterimRecoveryCoordinator  # noqa: E402
from delivery_pilot.interim_coordinator import InterimDispatchError  # noqa: E402
import test_interim_repair as repair_tests  # noqa: E402
from control_ref_test_support import memoized_control_refs  # noqa: E402


class RecoveryFixture:
    def __init__(self, rename=True, cancel="cancelled", coordinator_count=1, observed_state="active", owned=None, owned_sequence=None):
        self.rename, self.cancel_state, self.coordinator_count, self.observed_state, self.owned, self.calls = rename, cancel, coordinator_count, observed_state, owned or [], []
        self.owned_sequence, self.owned_calls = owned_sequence, 0

    def coordinators(self, approval):
        return [{"session_id": approval["coordinator"]["session_id"]} for _ in range(self.coordinator_count)]

    def observe(self, operation):
        self.calls.append(("observe", operation["id"]))
        return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "transport": "accepted", "worker_state": self.observed_state, "elapsed_seconds": 1}

    def remove_prefix(self, session_id, prefix):
        self.calls.append(("rename", session_id))
        if not self.rename:
            raise OSError("rename unavailable")
        return {"prefix": prefix, "readback_removed": True}

    def cancel(self, operation):
        self.calls.append(("cancel", operation["id"]))
        if self.cancel_state == "raise":
            raise TimeoutError("cancel timeout")
        return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": self.cancel_state}

    def owned_workers(self, run_id):
        self.owned_calls += 1
        if self.owned_sequence is not None:
            index = min(self.owned_calls - 1, len(self.owned_sequence) - 1)
            return deepcopy(self.owned_sequence[index])
        return deepcopy(self.owned)


class FaultRecoveryFixture(RecoveryFixture):
    """One fault at one invocation; the trace also detects effects after refusal."""

    def __init__(self, boundary, fault, invocation=1, **kwargs):
        super().__init__(observed_state="terminal", **kwargs)
        self.boundary, self.fault, self.invocation = boundary, fault, invocation
        self.trace, self.counts, self.fired = [], Counter(), False

    def _call(self, boundary, call, *args):
        self.counts[boundary] += 1
        self.trace.append((boundary, self.counts[boundary]))
        result = call(*args)
        if boundary in {"observe", "cancel"}:
            result["fixture_invocation"] = boundary + "-" + str(self.counts[boundary])
        if boundary == self.boundary and self.counts[boundary] == self.invocation:
            self.fired = True
            return self.fault(result)
        return result

    def coordinators(self, approval):
        return self._call("coordinators", super().coordinators, approval)

    def observe(self, operation):
        return self._call("observe", super().observe, operation)

    def remove_prefix(self, session_id, prefix):
        return self._call("remove_prefix", super().remove_prefix, session_id, prefix)

    def cancel(self, operation):
        return self._call("cancel", super().cancel, operation)

    def owned_workers(self, run_id):
        return self._call("owned_workers", super().owned_workers, run_id)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.base = repair_tests.RepairPolicyTests("run")
        self.base.setUp()
        self.snapshot = self.base.failed_s2()
        self.clock = lambda: datetime(2026, 9, 19, tzinfo=timezone.utc)
        self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)

    def tearDown(self):
        self.base.tearDown()

    def test_clean_clone_recovery_observes_active_worker_without_replacement_or_duplicate_wake(self):
        fixture = RecoveryFixture()
        recovered = self.coordinator.recover(initial_record(self.base.s2_approval()), "wake-1", fixture)
        self.assertEqual(recovered.value["recovery"]["observations"][0]["state"], "active")
        self.assertEqual([item["phase"] for item in recovered.value["usage"]["operations"]].count("build"), 1)
        self.assertEqual([call[0] for call in fixture.calls], ["observe"])
        duplicate = self.coordinator.recover(initial_record(self.base.s2_approval()), "wake-1", fixture)
        self.assertEqual(duplicate.value["usage"]["operations"], recovered.value["usage"]["operations"])

    def test_ambiguous_coordinator_and_stale_writer_hand_back_without_wake(self):
        stale = self.base.store(self.base.second).reload(initial_record(self.base.s2_approval()))
        advanced = self.coordinator.wake(self.snapshot, "wake-first", RecoveryFixture())
        with self.assertRaises(InterimCheckpointError):
            InterimRecoveryCoordinator(self.base.store(self.base.second), self.clock).wake(stale, "wake-stale", RecoveryFixture())
        self.assertTrue(advanced.value["recovery"]["wakes"])
        ambiguous = self.coordinator.recover(initial_record(self.base.s2_approval()), "wake-ambiguous", RecoveryFixture(coordinator_count=2))
        self.assertEqual(ambiguous.value["recovery"]["status"], "uncertain")
        self.assertEqual(ambiguous.value["state"]["next_action"], "handback")

    def test_stop_records_intent_prefix_readback_cancellation_uncertainty_and_deliberate_resume(self):
        stopped = self.coordinator.stop(self.snapshot, "human stop TASK-416", RecoveryFixture(observed_state="terminal"))
        self.assertEqual(stopped.value["recovery"]["status"], "stopped")
        self.assertTrue(stopped.value["recovery"]["stop"]["prefix_removed"])
        self.assertEqual(stopped.value["recovery"]["stop"]["cancellations"][0]["state"], "cancelled")
        late = self.coordinator.wake(stopped, "late-wake", RecoveryFixture())
        self.assertEqual(late.value["recovery"]["status"], "stopped")
        resumed = self.coordinator.resume(late, "human resume TASK-416", RecoveryFixture(observed_state="terminal"))
        self.assertEqual((resumed.value["recovery"]["status"], resumed.value["state"]["next_action"]), ("resumed", "recovered"))
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        uncertain = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(rename=False))
        self.assertEqual((uncertain.value["recovery"]["status"], uncertain.value["state"]["next_action"]), ("uncertain", "handback"))

    def test_recovery_validation_refuses_scope_corruption_and_preserves_history_over_clock_change(self):
        stopped = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(observed_state="terminal"))
        reloaded = self.base.store(self.base.second).reload(initial_record(self.base.s2_approval()))
        self.assertEqual(reloaded.value["usage"], stopped.value["usage"])
        corrupt = deepcopy(stopped.value); corrupt["approval"]["tracker"]["spec_revision"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(Exception, "spec revision|immutable|approval"):
            validate_record(corrupt)

    def test_canonical_set_expansion_keeps_every_preexisting_member(self):
        sets = runpy.run_path(str(PACK / "scripts" / "verify.py"))["SETS"]
        prior = {
            "A-continuation": {"test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py"},
            "A-core-local": {"test_core.py", "test_pack_lifecycle.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py"},
            "A-cloud": {"test_cloud.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py"},
            "A-complete": {"test_core.py", "test_pack_lifecycle.py", "test_cloud.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py"},
            "K4.1": {"test_core.py", "test_pack_lifecycle.py", "test_cloud.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py"},
        }
        for name, members in prior.items():
            with self.subTest(name=name):
                self.assertTrue(members <= set(sets[name]))
                self.assertIn("test_interim_recovery.py", sets[name])

    def test_stop_requires_durable_owned_identity_and_terminal_post_cancel_observation(self):
        unknown = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(owned=[{"operation_id": "unknown", "state": "active", "receipt": {}}]))
        self.assertEqual((unknown.value["recovery"]["status"], unknown.value["state"]["next_action"]), ("uncertain", "handback"))
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        active = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(observed_state="active"))
        self.assertEqual((active.value["recovery"]["status"], active.value["state"]["next_action"]), ("uncertain", "handback"))
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        queued = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(cancel="queued", observed_state="terminal"))
        self.assertEqual((queued.value["recovery"]["status"], queued.value["state"]["next_action"]), ("uncertain", "handback"))

    def test_resume_refuses_selected_cap_and_non_interim_record(self):
        self.base.tearDown(); self.base.setUp()
        approved = self.base.s2_approval(); approved["hard_limits"] = {"dispatch_max": 2}
        original = self.base.store(self.base.first).create_and_publish(initial_record(approved))
        from test_interim_coordinator import Fixture
        from delivery_pilot.interim_coordinator import InterimFixtureCoordinator
        failed = self.base.result(); failed["task_success"] = False
        limited = InterimFixtureCoordinator(self.base.store(self.base.first)).run_one(original, "TASK-413", self.base.task(), Fixture(failed), Fixture(self.base.result("verify")))
        coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        stopped = coordinator.stop(limited, "human stop", RecoveryFixture(observed_state="terminal"))
        refused = coordinator.resume(stopped, "human resume", RecoveryFixture(observed_state="terminal"))
        self.assertEqual(refused.value["state"]["next_action"], "handback")
        protected = deepcopy(stopped.value); protected["approval"]["kind"] = "protected-revoked-run"
        with self.assertRaisesRegex(Exception, "interim record|approval"):
            validate_record(protected)

    @staticmethod
    def owned(operation, state):
        return {"operation_id": operation["id"], "state": state, "receipt": {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}, "worker_state": state}}

    def test_unseen_wake_checks_selected_ceiling_before_any_accounting(self):
        self.base.tearDown(); self.base.setUp()
        approved = self.base.s2_approval(); approved["hard_limits"] = {"dispatch_max": 2}
        original = self.base.store(self.base.first).create_and_publish(initial_record(approved))
        from test_interim_coordinator import Fixture
        from delivery_pilot.interim_coordinator import InterimFixtureCoordinator
        failed = self.base.result(); failed["task_success"] = False
        limited = InterimFixtureCoordinator(self.base.store(self.base.first)).run_one(original, "TASK-413", self.base.task(), Fixture(failed), Fixture(self.base.result("verify")))
        before = deepcopy(limited.value["usage"])
        refused = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock).wake(limited, "new-wake", RecoveryFixture())
        self.assertEqual(refused.value["usage"], before)
        self.assertEqual(refused.value["state"]["next_action"], "handback")

    def test_stopping_reload_continues_each_effect_once_and_recover_never_wakes(self):
        record = deepcopy(self.snapshot.value)
        record["recovery"] = {"status": "stopping", "wakes": [], "observations": [], "stop": {"intent_at": "2026-09-19T00:00:00Z", "instruction": "human stop", "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
        durable = self.base.store(self.base.first).persist(self.snapshot, record)
        fixture = RecoveryFixture(observed_state="terminal")
        clean = InterimRecoveryCoordinator(self.base.store(self.base.second), self.clock).recover(initial_record(self.base.s2_approval()), "must-not-wake", fixture)
        self.assertEqual(clean.value["recovery"]["status"], "stopped")
        self.assertEqual([call[0] for call in fixture.calls].count("rename"), 1)
        again = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock).stop(clean, "same stop", fixture)
        self.assertEqual(again.value["recovery"]["status"], "stopped")
        self.assertEqual([call[0] for call in fixture.calls].count("rename"), 1)

    def test_stop_rereads_owned_race_and_resume_refuses_new_active_worker(self):
        operation = next(item for item in self.snapshot.value["usage"]["operations"] if item["phase"] == "build")
        fixture = RecoveryFixture(observed_state="terminal", owned_sequence=[[], [self.owned(operation, "active")], [self.owned(operation, "terminal")], []])
        stopped = self.coordinator.stop(self.snapshot, "human stop", fixture)
        self.assertGreaterEqual(fixture.owned_calls, 2)
        self.assertIn(stopped.value["recovery"]["status"], {"stopping", "uncertain", "stopped"})
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        confirmed = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(observed_state="terminal"))
        cancellation = confirmed.value["recovery"]["stop"]["cancellations"][0]["operation_id"]
        old = next(item for item in confirmed.value["usage"]["operations"] if item["id"] == cancellation)
        refused = self.coordinator.resume(confirmed, "human resume", RecoveryFixture(observed_state="terminal", owned=[self.owned(old, "active")]))
        self.assertEqual(refused.value["state"]["next_action"], "handback")
        self.assertEqual(refused.value["recovery"]["status"], "stopped")

    def test_stop_adapter_failures_are_durable_uncertainty(self):
        for label, fixture in (
            ("enumeration", RecoveryFixture(owned_sequence=None)),
            ("cancellation", RecoveryFixture(cancel="raise")),
            ("observation", RecoveryFixture(observed_state="active")),
        ):
            with self.subTest(label=label):
                self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
                if label == "enumeration":
                    fixture.owned_workers = lambda _run: (_ for _ in ()).throw(OSError("enumeration unavailable"))
                result = self.coordinator.stop(self.snapshot, "human stop", fixture)
                self.assertEqual((result.value["recovery"]["status"], result.value["state"]["next_action"]), ("uncertain", "handback"))

    def test_automatic_adapter_failures_checkpoint_stable_reconciliation_identity(self):
        class FailObserve(RecoveryFixture):
            def observe(self, operation):
                raise TimeoutError("observation unavailable")

        class FailCoordinators(RecoveryFixture):
            def coordinators(self, approval):
                raise OSError("coordinator enumeration unavailable")

        wake_failed = self.coordinator.wake(self.snapshot, "wake-observation-failure", FailObserve())
        wakes = [item for item in wake_failed.value["usage"]["operations"] if item["phase"] == "wake"]
        self.assertEqual((wake_failed.value["state"]["next_action"], len(wakes)), ("handback", 1))
        self.assertEqual(wakes[0]["status"], "reconcile-required")
        wake_charge = [item for item in wake_failed.value["usage"]["charges"] if item["operation_id"] == wakes[0]["id"]]
        self.assertEqual(len(wake_charge), 1)
        reconciled = self.coordinator.recover(initial_record(self.base.s2_approval()), "wake-observation-failure", RecoveryFixture(observed_state="terminal"))
        self.assertEqual(len([item for item in reconciled.value["usage"]["charges"] if item["operation_id"] == wakes[0]["id"]]), 1)
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        coordinator_failed = self.coordinator.wake(self.snapshot, "wake-coordinator-failure", FailCoordinators())
        self.assertEqual(coordinator_failed.value["state"]["next_action"], "handback")
        self.assertEqual([item["phase"] for item in coordinator_failed.value["usage"]["operations"]].count("wake"), 1)
        self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
        observed_failed = self.coordinator.recover(initial_record(self.base.s2_approval()), "recover-observation-failure", FailObserve())
        self.assertEqual(observed_failed.value["state"]["next_action"], "handback")
        active = next(item for item in observed_failed.value["usage"]["operations"] if item["phase"] == "coordinator")
        original = next(item for item in self.snapshot.value["usage"]["operations"] if item["id"] == active["id"])
        self.assertEqual(active, original)  # failed observation must not erase confirmed usage/receipt
        self.assertEqual(observed_failed.value["recovery"]["observations"][0]["state"], "unknown")
        self.assertIn("observe", observed_failed.value["state"]["handback"]["reason"])

    def test_false_stopped_checkpoint_refuses_transition_clean_reload_and_resume(self):
        corrupt = deepcopy(self.snapshot.value)
        corrupt["recovery"] = {"status": "stopped", "wakes": [], "observations": [], "stop": {"intent_at": None, "instruction": "human stop", "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
        with self.assertRaisesRegex(Exception, "intent_at|confirmed"):
            validate_record(corrupt)
        # Test-only lower-level injection proves a clean clone refuses corrupt
        # remote bytes before an automatic wake or resume can mutate anything.
        raw_store = self.base.store(self.base.first)
        injected = raw_store._store.write(self.snapshot.commit_sha, self.snapshot.digest, corrupt)
        raw_store._store.push("origin", self.snapshot.commit_sha, injected.commit_sha)
        with self.assertRaises(InterimCheckpointError):
            self.base.store(self.base.second).reload(initial_record(self.base.s2_approval()))
        with self.assertRaisesRegex(Exception, "intent_at|confirmed"):
            self.coordinator.resume(type(self.snapshot)(corrupt, self.snapshot.digest, self.snapshot.commit_sha), "human resume", RecoveryFixture(observed_state="terminal"))

    def test_stopped_receipt_wrappers_and_timestamps_must_be_truthful_utc(self):
        def mutate(kind, record):
            cancellation = record["recovery"]["stop"]["cancellations"][0]
            observation = next(item for item in record["recovery"]["observations"] if item["operation_id"] == cancellation["operation_id"])
            if kind == "cancellation":
                cancellation["receipt"]["state"] = "queued"
            elif kind == "observation":
                observation["receipt"]["worker_state"] = "active"
            elif kind == "stop-time":
                record["recovery"]["stop"]["intent_at"] = "2026-09-19Z"
            elif kind == "observation-time":
                observation["observed_at"] = "2026-09-19Z"
            else:
                record["recovery"]["resume"] = {"instruction": "human resume", "resumed_at": "2026-09-19Z"}
                record["recovery"]["status"] = "resumed"

        for kind in ("cancellation", "observation", "stop-time", "observation-time", "resume-time"):
            with self.subTest(kind=kind):
                self.base.tearDown(); self.base.setUp(); self.snapshot = self.base.failed_s2(); self.coordinator = InterimRecoveryCoordinator(self.base.store(self.base.first), self.clock)
                stopped = self.coordinator.stop(self.snapshot, "human stop", RecoveryFixture(observed_state="terminal"))
                corrupt = deepcopy(stopped.value); mutate(kind, corrupt)
                with self.assertRaisesRegex(Exception, "disagrees|UTC"):
                    validate_record(corrupt)
                raw_store = self.base.store(self.base.first)
                injected = raw_store._store.write(stopped.commit_sha, stopped.digest, corrupt)
                raw_store._store.push("origin", stopped.commit_sha, injected.commit_sha)
                with self.assertRaises(InterimCheckpointError):
                    self.base.store(self.base.second).reload(initial_record(self.base.s2_approval()))
                with self.assertRaisesRegex(Exception, "disagrees|UTC"):
                    self.coordinator.resume(type(stopped)(corrupt, stopped.digest, stopped.commit_sha), "human resume", RecoveryFixture(observed_state="terminal"))


class RecoveryBoundaryTests(unittest.TestCase):
    """Public transitions and real remote reloads, with nonempty S3 history."""

    def setUp(self):
        self.base = repair_tests.RepairPolicyTests("run")
        self.base.setUp()
        self.store = self.base.store(self.base.first)
        repair, diagnosed = self.base.open_and_diagnose()
        fixture = repair_tests.RepairFixture("fail")
        self.seed = repair.repair_once(diagnosed, "TASK-413", self.base.task(), fixture, fixture)
        self.assertTrue(self.seed.value["repair"]["cycles"])
        self.assertTrue(self.seed.value["repair"]["diagnoses"])
        self.assertTrue(self.seed.value["forecasts"]["revised"])
        self.approved = initial_record(self.base.s2_approval())
        self.clock = lambda: datetime(2026, 9, 19, tzinfo=timezone.utc)
        self.coordinator = InterimRecoveryCoordinator(self.store, self.clock)
        self.serial = 0

    def tearDown(self):
        self.base.tearDown()

    @staticmethod
    def change(key, value):
        def mutate(result):
            result[key] = value
            return result
        return mutate

    @staticmethod
    def raises(error):
        def fail(result):
            raise error
        return fail

    def start(self, path, owned=None):
        current = self.store.reload(self.approved)
        snapshot = self.store.persist(current, deepcopy(self.seed.value))
        if path == "resume":
            snapshot = self.coordinator.stop(snapshot, "original stop", RecoveryFixture(observed_state="terminal", owned=owned))
        elif path == "continue":
            record = deepcopy(snapshot.value)
            record["recovery"] = {"status": "stopping", "wakes": [], "observations": [], "stop": {"intent_at": "2026-09-19T00:00:00Z", "instruction": "original stop", "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
            snapshot = self.store.persist(snapshot, record)
        elif path == "recover-wake":
            snapshot = self.coordinator.wake(snapshot, "fault-wake", FaultRecoveryFixture("observe", self.raises(TimeoutError())))
        return snapshot

    def invoke(self, path, snapshot, fixture):
        if path == "stop":
            return self.coordinator.stop(snapshot, "original stop", fixture)
        if path == "resume":
            return self.coordinator.resume(snapshot, "attempted resume", fixture)
        if path == "wake":
            return self.coordinator.wake(snapshot, "fault-wake", fixture)
        return self.coordinator.recover(self.approved, "fault-wake", fixture)

    def reload(self, result):
        self.serial += 1
        clone = self.base.clone("boundary-reload-" + str(self.serial))
        fresh = self.base.store(clone).reload(self.approved)
        self.assertEqual((fresh.commit_sha, fresh.digest, fresh.value), (result.commit_sha, result.digest, result.value))
        return fresh

    def preserved(self, before, after, path):
        for key in ("approval", "approval_digest", "forecasts", "repair"):
            self.assertEqual(after[key], before[key], key)
        for key in ("operations", "launches", "charges"):
            self.assertGreaterEqual(len(after["usage"][key]), len(before["usage"][key]))
        ids = lambda record: [tuple(op[k] for k in ("id", "session_id", "message_id", "terminal_turn_id")) for op in record["usage"]["operations"]]
        self.assertEqual(ids(after)[:len(ids(before))], ids(before))
        if path in {"stop", "continue", "resume"}:
            self.assertEqual(after["usage"], before["usage"])
        else:
            self.assertEqual(after["usage"]["launches"][:len(before["usage"]["launches"])], before["usage"]["launches"])
            self.assertEqual(after["usage"]["charges"][:len(before["usage"]["charges"])], before["usage"]["charges"])
            for old, new in zip(before["usage"]["operations"], after["usage"]["operations"]):
                self.assertEqual(old["elapsed_seconds"], new["elapsed_seconds"])
                if "receipt" in old:
                    self.assertEqual(old["receipt"], new["receipt"])

    def check_fault(self, path, boundary, fault, invocation=1, **kwargs):
        snapshot = self.start(path, kwargs.get("owned"))
        before = deepcopy(snapshot.value)
        fixture = FaultRecoveryFixture(boundary, fault, invocation, **kwargs)
        result = self.invoke(path, snapshot, fixture)
        self.assertTrue(fixture.fired, fixture.trace)
        self.assertEqual(snapshot.value, before, "input snapshot was mutated")
        self.assertEqual(fixture.trace[-1], (boundary, invocation), "provider calls continued after refusal")
        self.assertEqual(result.value["state"]["next_action"], "handback")
        reason = result.value["state"]["handback"]["reason"]
        # Repeating the same failure against the same identity truthfully has
        # the same sanitized reason. Publication, trace, and reload prove the
        # new attempt was handled; inventing unique reason text would not.
        self.assertNotEqual(result.commit_sha, snapshot.commit_sha)
        self.assertIn(boundary, reason)
        if boundary == "observe" and invocation > 1:
            self.assertTrue(any(item["receipt"].get("fixture_invocation") == "observe-1" for item in result.value["recovery"]["observations"]), "earlier valid observation was lost")
        if boundary == "cancel" and invocation > 1:
            self.assertTrue(any(item["state"] == "cancelled" and item["receipt"].get("fixture_invocation") == "cancel-1" for item in result.value["recovery"]["stop"]["cancellations"]), "earlier confirmed cancellation was lost")
        if path == "resume":
            self.assertEqual(result.value["recovery"]["status"], "stopped")
            self.assertEqual(result.value["recovery"]["resume"], snapshot.value["recovery"]["resume"])
            self.assertIn("resume", reason)
        elif path in {"stop", "continue"}:
            self.assertEqual(result.value["recovery"]["status"], "uncertain")
            self.assertEqual(result.value["recovery"]["stop"]["uncertainty"], reason)
        self.preserved(snapshot.value, result.value, path)
        self.reload(result)
        return result

    def test_shared_boundary_red_matrix(self):
        wrong_id = lambda result: {**result, "observation": {**result["observation"], "message_id": "wrong"}}
        cases = [
            ("stop", "cancel", wrong_id),
            ("continue", "cancel", lambda _: None),
            ("resume", "coordinators", self.raises(OSError("provider unavailable"))),
            ("resume", "coordinators", lambda _: None),
            ("wake", "observe", self.change("worker_state", [])),
            ("recover", "observe", self.change("worker_state", {})),
            ("stop", "owned_workers", lambda _: [{"operation_id": [], "state": "terminal", "receipt": {}}]),
            ("resume", "owned_workers", lambda _: [{"operation_id": {}, "state": "terminal", "receipt": {}}]),
            ("wake", "observe", self.change("elapsed_seconds", -1)),
            ("stop", "observe", self.change("extra", object())),
            ("resume", "observe", self.change("worker_state", "unknown")),
        ]
        for path, boundary, fault in cases:
            with self.subTest(path=path, boundary=boundary):
                self.check_fault(path, boundary, fault)

    def inventory(self):
        return [RecoveryTests.owned(op, "terminal") for op in self.seed.value["usage"]["operations"][:2]]

    def sites(self):
        """All direct/delegated sites, plus later calls after confirmed progress."""
        owned = self.inventory()
        race = [owned[:1], owned, owned, owned]
        return [
            ("wake", "coordinators", 1, {}), ("wake", "observe", 1, {}),
            ("recover", "coordinators", 1, {}), ("recover", "coordinators", 2, {}),
            ("recover", "observe", 1, {}), ("recover", "observe", 2, {}),
            ("recover-wake", "observe", 2, {}),
            *[(path, boundary, occurrence, options) for path in ("stop", "continue") for boundary, occurrence, options in [
                ("remove_prefix", 1, {}),
                ("owned_workers", 1, {"owned": owned}),
                ("owned_workers", 2, {"owned": owned}),
                ("owned_workers", 3, {"owned_sequence": race}),
                ("owned_workers", 4, {"owned_sequence": race}),
                ("cancel", 1, {"owned": owned}), ("cancel", 2, {"owned": owned}),
                ("observe", 1, {"owned": owned}), ("observe", 2, {"owned": owned}),
            ]],
            ("resume", "coordinators", 1, {}), ("resume", "owned_workers", 1, {"owned": owned}),
            ("resume", "observe", 1, {"owned": owned}), ("resume", "observe", 2, {"owned": owned}),
        ]

    @memoized_control_refs
    def test_transport_failures_at_every_call_site(self):
        for path, boundary, occurrence, options in self.sites():
            for error in (OSError, TimeoutError, ConnectionError, InterimDispatchError):
                with self.subTest(path=path, boundary=boundary, occurrence=occurrence, error=error.__name__):
                    result = self.check_fault(path, boundary, self.raises(error("private-provider-text")), occurrence, **options)
                    self.assertNotIn("private-provider-text", repr(result.value))
                    self.assertIn("unavailable", result.value["state"]["handback"]["reason"])
                    self.assertIn(error.__name__, result.value["state"]["handback"]["reason"])
                    # Facts from earlier successful calls are still durable.
                    if boundary == "owned_workers" and occurrence > 1:
                        self.assertTrue(result.value["recovery"]["stop"]["prefix_removed"])
                        self.assertTrue(result.value["recovery"]["stop"]["cancellations"])
                        self.assertTrue(result.value["recovery"]["observations"])
                    if boundary == "cancel" and occurrence == 2:
                        self.assertEqual([x["state"] for x in result.value["recovery"]["stop"]["cancellations"]].count("cancelled"), 1)

    @staticmethod
    def correlated_fault(field, value):
        def mutate(receipt):
            receipt["observation"][field] = value
            return receipt
        return mutate

    def malformed_receipts(self, state_key):
        return [
            ("not-dict", lambda _: None),
            ("missing-correlation", lambda raw: {key: val for key, val in raw.items() if key != "observation"}),
            *[("correlation-" + field, self.correlated_fault(field, "wrong")) for field in ("id", "session_id", "message_id", "terminal_turn_id")],
            ("list-id", self.correlated_fault("id", [])),
            ("dict-id", self.correlated_fault("id", {})),
            ("missing-state", lambda raw: {key: val for key, val in raw.items() if key != state_key}),
            *[("state-" + str(value), self.change(state_key, value)) for value in ("bogus", [], {}, None, 1)],
            ("object-extra", self.change("extra", object())),
            ("nan-extra", self.change("extra", float("nan"))),
            ("nonstring-key", self.change(1, "value")),
            ("invalid-unicode", self.change("extra", "\ud800")),
        ]

    @memoized_control_refs
    def test_malformed_observation_and_cancellation_matrix(self):
        for path, boundary, occurrence, options in self.sites():
            if boundary not in {"observe", "cancel"}:
                continue
            for label, fault in self.malformed_receipts("state" if boundary == "cancel" else "worker_state"):
                with self.subTest(path=path, boundary=boundary, occurrence=occurrence, fault=label):
                    result = self.check_fault(path, boundary, fault, occurrence, **options)
                    self.assertIn("malformed", result.value["state"]["handback"]["reason"])
                    if boundary == "cancel":
                        latest = result.value["recovery"]["stop"]["cancellations"][-1]
                        self.assertEqual(latest["state"], "uncertain")
                        self.assertEqual(latest["receipt"]["state"], "uncertain")

    @memoized_control_refs
    def test_coordinator_and_prefix_malformed_matrix(self):
        coordinator_faults = [
            ("not-list", lambda _: None), ("non-object-item", lambda _: [None]),
            *[("session-" + str(value), lambda raw, value=value: [{"session_id": value}]) for value in ([], {}, None, 1, "")],
        ]
        prefix_faults = [
            ("not-dict", lambda _: None), ("wrong-prefix", self.change("prefix", "wrong")),
            ("list-prefix", self.change("prefix", [])),
            *[("readback-" + str(value), self.change("readback_removed", value)) for value in (None, 1, [], False)],
        ]
        for path, boundary, occurrence, options in self.sites():
            if boundary not in {"coordinators", "remove_prefix"}:
                continue
            for label, fault in coordinator_faults if boundary == "coordinators" else prefix_faults:
                with self.subTest(path=path, boundary=boundary, occurrence=occurrence, fault=label):
                    self.check_fault(path, boundary, fault, occurrence, **options)

    @memoized_control_refs
    def test_owned_inventory_malformed_matrix(self):
        def item_change(key, value):
            def mutate(items):
                items[-1][key] = value
                return items
            return mutate

        faults = [
            ("not-list", lambda _: None), ("bad-item", lambda _: [None]),
            ("missing-field", lambda raw: [{"operation_id": raw[0]["operation_id"]}]),
            ("duplicate-id", lambda raw: [raw[0], raw[0]]),
            *[("id-" + str(value), item_change("operation_id", value)) for value in ([], {}, None, 1, "foreign")],
            *[("state-" + str(value), item_change("state", value)) for value in ([], {}, None, 1, "bogus")],
            ("wrapper-disagrees", item_change("state", "active")),
        ]
        for label, receipt_fault in self.malformed_receipts("worker_state"):
            def mutate(items, receipt_fault=receipt_fault):
                items[-1]["receipt"] = receipt_fault(items[-1]["receipt"])
                return items
            faults.append(("receipt-" + label, mutate))
        for path, boundary, occurrence, options in self.sites():
            if boundary != "owned_workers":
                continue
            for label, fault in faults:
                with self.subTest(path=path, occurrence=occurrence, fault=label):
                    result = self.check_fault(path, boundary, fault, occurrence, **options)
                    self.assertIn("malformed", result.value["state"]["handback"]["reason"])

    def test_consumed_elapsed_is_validated_before_accounting(self):
        for path, occurrence in (("wake", 1), ("recover", 2), ("recover-wake", 2)):
            for elapsed in (-1, True, 1.5, "1", None, [], {}):
                with self.subTest(path=path, elapsed=elapsed):
                    result = self.check_fault(path, "observe", self.change("elapsed_seconds", elapsed), occurrence)
                    wake = next(op for op in result.value["usage"]["operations"] if op["phase"] == "wake")
                    self.assertEqual((wake["status"], wake["elapsed_seconds"]), ("reconcile-required", 0))
                    charge = next(item for item in result.value["usage"]["charges"] if item["operation_id"] == wake["id"])
                    self.assertEqual(charge["status"], "pending")
                    self.assertIn("elapsed_seconds", result.value["state"]["handback"]["reason"])

    def test_unknown_active_queued_and_terminal_are_distinct(self):
        for path in ("wake", "recover", "stop", "continue", "resume"):
            for state in ("unknown", "active", "queued", "terminal"):
                with self.subTest(path=path, state=state):
                    snapshot = self.start(path)
                    fixture = FaultRecoveryFixture("observe", self.change("worker_state", state))
                    result = self.invoke(path, snapshot, fixture)
                    if state != "terminal":
                        self.assertIn("remains " + state, result.value["state"]["handback"]["reason"])
                        self.assertEqual(fixture.trace[-1], ("observe", 1))
                    if path == "resume":
                        self.assertEqual(result.value["recovery"]["status"], "resumed" if state == "terminal" else "stopped")
                    elif path in {"stop", "continue"}:
                        self.assertEqual(result.value["recovery"]["status"], "stopped" if state == "terminal" else "uncertain")
                    elif path == "wake":
                        wake = result.value["usage"]["operations"][-1]
                        self.assertEqual(wake["status"], "reconcile-required" if state == "unknown" else "accounted")
                    self.preserved(snapshot.value, result.value, path)
                    self.reload(result)

    @memoized_control_refs
    def test_explicit_uncertain_stop_retry_retains_confirmed_progress(self):
        for boundary in ("cancel", "observe", "owned_workers"):
            with self.subTest(boundary=boundary):
                snapshot = self.start("stop")
                owned = self.inventory()
                fault = FaultRecoveryFixture(boundary, self.raises(TimeoutError()), 2, owned=owned)
                uncertain = self.coordinator.stop(snapshot, "original stop", fault)
                self.assertTrue(fault.fired)
                prior = deepcopy(uncertain.value["recovery"]["stop"])
                self.reload(uncertain)
                automatic = FaultRecoveryFixture("observe", lambda _: self.fail("automatic uncertain stop must not run effects"))
                refused = self.coordinator.recover(self.approved, "late", automatic)
                self.assertEqual(automatic.trace, [])
                self.assertEqual(refused.value["recovery"]["stop"], prior)
                fixture = FaultRecoveryFixture("unused", None, owned=owned)
                stopped = self.coordinator.stop(refused, "retry instruction must not replace intent", fixture)
                self.assertEqual(stopped.value["recovery"]["status"], "stopped")
                self.assertEqual(fixture.counts["remove_prefix"], 0)
                confirmed = [x for x in prior["cancellations"] if x["state"] == "cancelled"]
                self.assertEqual(fixture.counts["cancel"], len(owned) - len(confirmed))
                stop = stopped.value["recovery"]["stop"]
                self.assertEqual((stop["instruction"], stop["intent_at"]), (prior["instruction"], prior["intent_at"]))
                for cancellation in confirmed:
                    self.assertIn(cancellation, stop["cancellations"])
                self.assertIsNone(stop["uncertainty"])
                self.preserved(snapshot.value, stopped.value, "stop")
                fresh = self.reload(stopped)
                resumed = InterimRecoveryCoordinator(self.base.store(self.base.root / ("boundary-reload-" + str(self.serial))), self.clock).resume(fresh, "explicit resume", RecoveryFixture(observed_state="terminal"))
                self.assertEqual(resumed.value["recovery"]["status"], "resumed")
                self.preserved(snapshot.value, resumed.value, "resume")
                self.reload(resumed)

    def test_exhausted_ceiling_enumeration_failure_does_not_invent_a_wake(self):
        for limits, now in (({"dispatch_max": 5}, self.clock()), ({"deadline_at": "2030-01-01T00:00:00Z"}, datetime(2031, 1, 1, tzinfo=timezone.utc))):
            with self.subTest(limits=limits):
                # Build real S3 history under a separately approved ceiling.
                self.base.tearDown()
                self.base = repair_tests.RepairPolicyTests("run"); self.base.setUp()
                original_approval = self.base.s2_approval
                self.base.s2_approval = lambda task=None: {**original_approval(task), "hard_limits": limits}
                repair, diagnosed = self.base.open_and_diagnose()
                worker = repair_tests.RepairFixture("fail")
                snapshot = repair.repair_once(diagnosed, "TASK-413", self.base.task(), worker, worker)
                self.assertTrue(snapshot.value["repair"]["cycles"])
                self.assertEqual(len(snapshot.value["usage"]["launches"]), 5)
                self.approved = initial_record(self.base.s2_approval())
                self.store = self.base.store(self.base.first)
                coordinator = InterimRecoveryCoordinator(self.store, lambda: now)
                for fault in (self.raises(OSError()), lambda _: None):
                    fixture = FaultRecoveryFixture("coordinators", fault)
                    result = coordinator.recover(self.approved, "exhausted-wake", fixture)
                    self.assertEqual(result.value["usage"], snapshot.value["usage"])
                    self.assertEqual(result.value["recovery"]["wakes"], [])
                    self.assertIn("coordinators", result.value["state"]["handback"]["reason"])
                    self.assertEqual(fixture.trace, [("coordinators", 1)])
                    self.preserved(snapshot.value, result.value, "recover")
                    self.reload(result)
                fixture = FaultRecoveryFixture("unused", None)
                refused = coordinator.wake(result, "direct-exhausted-wake", fixture)
                self.assertEqual(fixture.trace, [])
                self.assertEqual(refused.value["usage"], snapshot.value["usage"])
                stopped = coordinator.stop(refused, "stop at ceiling", RecoveryFixture(observed_state="terminal"))
                refused = coordinator.resume(stopped, "cannot reset ceiling", fixture)
                self.assertEqual(fixture.trace, [])
                self.assertEqual(refused.value["recovery"]["status"], "stopped")
                self.preserved(snapshot.value, refused.value, "resume")
                self.reload(refused)

    @memoized_control_refs
    def test_provider_programmer_and_storage_exceptions_are_not_conflated(self):
        for path, boundary, occurrence, options in self.sites():
            # One representative call at each boundary/mode is sufficient here;
            # the fault-data matrix above separately covers later invocations.
            if occurrence != 1:
                continue
            for error in (TypeError, KeyError, ValueError, RuntimeError, AssertionError):
                with self.subTest(path=path, boundary=boundary, error=error.__name__):
                    snapshot = self.start(path, options.get("owned"))
                    exception = error("programmer defect")
                    fixture = FaultRecoveryFixture(boundary, self.raises(exception), **options)
                    with self.assertRaises(error) as caught:
                        self.invoke(path, snapshot, fixture)
                    self.assertIs(caught.exception, exception)
                    self.assertEqual(fixture.trace[-1], (boundary, 1))
                    durable = self.store.reload(self.approved)
                    self.assertNotIn("programmer defect", repr(durable.value))
        # Force publication failure immediately after a valid prefix readback.
        snapshot = self.start("continue")
        for exception in (OSError("storage unavailable"), InterimCheckpointError("stale exact-ref CAS"), TypeError("projection bug")):
            fixture = FaultRecoveryFixture("unused", None)
            with patch.object(self.store, "persist", side_effect=exception) as persist:
                with self.assertRaises(type(exception)) as caught:
                    self.invoke("continue", snapshot, fixture)
            self.assertIs(caught.exception, exception)
            self.assertEqual(persist.call_count, 1)
            self.assertEqual(fixture.trace, [("remove_prefix", 1)])
            self.assertEqual(self.store.reload(self.approved).commit_sha, snapshot.commit_sha)

    def test_reconciled_wake_and_duplicate_preserve_nonempty_history(self):
        snapshot = self.start("wake")
        failed = self.coordinator.wake(snapshot, "stable-wake", FaultRecoveryFixture("observe", self.raises(TimeoutError())))
        self.reload(failed)
        actor = InterimRecoveryCoordinator(self.base.store(self.base.root / ("boundary-reload-" + str(self.serial))), self.clock)
        reconciled = actor.recover(self.approved, "stable-wake", RecoveryFixture(observed_state="terminal"))
        self.preserved(snapshot.value, reconciled.value, "recover")
        wakes = [item for item in reconciled.value["usage"]["operations"] if item["phase"] == "wake"]
        self.assertEqual(len(wakes), 1)
        self.assertEqual(wakes[0]["status"], "accounted")
        for key in ("launches", "charges"):
            self.assertEqual(len([item for item in reconciled.value["usage"][key] if item["operation_id"] == wakes[0]["id"]]), 1)
        fixture = FaultRecoveryFixture("unused", None)
        duplicate = actor.wake(reconciled, "stable-wake", fixture)
        self.assertEqual(duplicate.commit_sha, reconciled.commit_sha)
        self.assertEqual(duplicate.value["usage"], reconciled.value["usage"])
        self.assertEqual(fixture.trace, [])
        self.reload(duplicate)

    def test_cancellation_pending_states_are_distinct_and_retryable(self):
        for state in ("queued", "uncertain"):
            with self.subTest(state=state):
                snapshot = self.start("stop")
                fixture = FaultRecoveryFixture("cancel", self.change("state", state))
                result = self.coordinator.stop(snapshot, "original stop", fixture)
                self.assertIn("remains " + state, result.value["state"]["handback"]["reason"])
                self.assertEqual(fixture.trace[-1], ("cancel", 1))
                self.assertEqual(result.value["recovery"]["stop"]["cancellations"][0]["state"], state)
                self.reload(result)
                resumed_stop = self.coordinator.stop(result, "explicit retry", RecoveryFixture(observed_state="terminal"))
                self.assertEqual(resumed_stop.value["recovery"]["status"], "stopped")
                self.assertEqual(resumed_stop.value["recovery"]["stop"]["instruction"], "original stop")
                self.preserved(snapshot.value, resumed_stop.value, "stop")
                self.reload(resumed_stop)

    def test_new_stop_after_resume_has_new_intent(self):
        snapshot = self.start("resume")
        resumed = self.coordinator.resume(snapshot, "explicit resume", RecoveryFixture(observed_state="terminal"))
        fixture = FaultRecoveryFixture("unused", None)
        stopped = self.coordinator.stop(resumed, "new stop", fixture)
        self.assertEqual(stopped.value["recovery"]["stop"]["instruction"], "new stop")
        self.assertEqual(fixture.counts["remove_prefix"], 1)
        self.assertGreater(fixture.counts["cancel"], 0)
        self.preserved(snapshot.value, stopped.value, "stop")
        self.reload(stopped)

    def test_truthful_stop_proof_still_gates_validation_persist_reload_and_resume(self):
        from delivery_pilot.interim import InterimError
        cases = [("observation", value) for value in ("active", "queued", "unknown")]
        cases += [("cancellation", value) for value in ("queued", "uncertain")]
        cases += [(field, timestamp) for field in ("stop-time", "observation-time", "resume-time") for timestamp in ("2026-09-19Z", "2026-09-19T00:00:00+01:00")]
        for kind, value in cases:
            with self.subTest(kind=kind, value=value):
                # Restore the test seed at the raw seam: normal reload must
                # refuse the preceding deliberately corrupted checkpoint.
                current = self.store._store.read()
                if current is not None:
                    raw = self.store._store.write(current.commit_sha, current.digest, self.seed.value)
                    self.store._store.push("origin", current.commit_sha, raw.commit_sha)
                stopped = self.coordinator.stop(self.store.reload(self.approved), "proof stop", RecoveryFixture(observed_state="terminal"))
                corrupt = deepcopy(stopped.value)
                recovery = corrupt["recovery"]
                if kind == "observation":
                    recovery["observations"][0]["receipt"]["worker_state"] = value
                elif kind == "cancellation":
                    recovery["stop"]["cancellations"][0]["receipt"]["state"] = value
                elif kind == "stop-time":
                    recovery["stop"]["intent_at"] = value
                elif kind == "observation-time":
                    recovery["observations"][0]["observed_at"] = value
                else:
                    recovery["resume"] = {"instruction": "resume", "resumed_at": value}
                with self.assertRaises(InterimError):
                    validate_record(corrupt)
                with self.assertRaises(InterimError):
                    self.store.persist(stopped, corrupt)
                self.assertEqual(self.store.reload(self.approved).commit_sha, stopped.commit_sha)
                fixture = FaultRecoveryFixture("unused", None)
                with self.assertRaises(InterimError):
                    self.coordinator.resume(type(stopped)(corrupt, stopped.digest, stopped.commit_sha), "resume", fixture)
                self.assertEqual(fixture.trace, [])
                raw = self.store._store.write(stopped.commit_sha, stopped.digest, corrupt)
                self.store._store.push("origin", stopped.commit_sha, raw.commit_sha)
                self.serial += 1
                clone = self.base.clone("boundary-reload-" + str(self.serial))
                with self.assertRaises(InterimCheckpointError):
                    self.base.store(clone).reload(self.approved)

    def test_stop_retry_retains_known_owned_targets_when_inventory_later_disappears(self):
        snapshot = self.start("stop")
        owned = [RecoveryTests.owned(operation, "active") for operation in snapshot.value["usage"]["operations"]]
        interrupted = self.coordinator.stop(snapshot, "original stop", FaultRecoveryFixture("cancel", self.raises(TimeoutError()), owned=owned))
        self.assertEqual(interrupted.value["recovery"]["status"], "uncertain")
        # A forged completion of just the attempted cancellation cannot erase
        # the other owned workers from the portable stopped proof either.
        from delivery_pilot.interim import InterimError
        corrupt = deepcopy(interrupted.value)
        recovery = corrupt["recovery"]; recovery["status"] = "stopped"; recovery["stop"]["uncertainty"] = None
        attempted = {item["operation_id"] for item in recovery["stop"]["cancellations"]}
        for cancellation in recovery["stop"]["cancellations"]:
            cancellation["state"] = cancellation["receipt"]["state"] = "cancelled"
        for observation in recovery["observations"]:
            if observation["operation_id"] in attempted:
                observation["state"] = observation["receipt"]["worker_state"] = "terminal"
        with self.assertRaises(InterimError):
            validate_record(corrupt)
        self.reload(interrupted)
        actor = InterimRecoveryCoordinator(self.base.store(self.base.root / ("boundary-reload-" + str(self.serial))), self.clock)
        fixture = FaultRecoveryFixture("unused", None)
        stopped = actor.stop(interrupted, "explicit retry", fixture)
        self.assertEqual(stopped.value["recovery"]["status"], "stopped")
        self.assertEqual({item["operation_id"] for item in stopped.value["recovery"]["stop"]["cancellations"]}, {item["operation_id"] for item in owned})
        self.assertTrue(all(item["state"] == "terminal" for item in stopped.value["recovery"]["observations"]))
        self.preserved(snapshot.value, stopped.value, "stop")
        self.reload(stopped)

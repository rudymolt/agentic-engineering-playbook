from __future__ import annotations

import sys
import os
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import unittest

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.canonical import digest  # noqa: E402
from delivery_pilot.interim import InterimError, initial_record, validate_record  # noqa: E402
from delivery_pilot.interim_coordinator import InterimFixtureCoordinator  # noqa: E402
from delivery_pilot.interim_repair_coordinator import InterimRepairCoordinator  # noqa: E402
from delivery_pilot.interim import InterimCheckpointStore  # noqa: E402
from delivery_pilot.interim import InterimCheckpointError  # noqa: E402
from delivery_pilot.interim_disposition import ObservationFailure  # noqa: E402
from delivery_pilot.interim_advance import advance_once  # noqa: E402
import test_interim as interim_tests  # noqa: E402
from test_interim import approval  # noqa: E402
from test_interim_coordinator import Fixture  # noqa: E402


class RepairFixture:
    def __init__(self, outcome: str = "pass", progress: bool = False, actionable: bool = True, distinct: bool = False, criteria_outcomes=None):
        self.outcome, self.progress, self.actionable, self.distinct, self.criteria_outcomes, self.operations = outcome, progress, actionable, distinct, criteria_outcomes, []

    def _runtime(self, operation):
        route = "diagnosis" if operation["phase"] == "diagnosis" else "build" if operation["phase"] == "repair" else "verify"
        chosen = operation.get("route", {"model": "gpt-5.6-terra" if route != "verify" else "gpt-5.6-sol", "effort": "high" if route != "verify" else "medium"})
        return {**chosen, "runner": route + "-runner", "permissions": "read-only"}

    def send(self, operation):
        self.operations.append(deepcopy(operation))
        observation = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        suffix = "-" + str(operation["repair_attempt"]) if self.distinct else ""
        evidence = [{"id": operation["phase"] + "-evidence" + suffix, "command": operation["phase"] + "-command", "result": "pass", "artifact_id": "artifact-" + operation["phase"] + suffix}]
        if operation["phase"] == "diagnosis":
            diagnosis = {"id": operation["purpose"], "operation_id": operation["id"], "criteria": operation["task"]["criteria"], "revisions": {"head": "a" * 40, "base": "b" * 40}, "execution_evidence": evidence, "prior_hypotheses": operation.get("prior_hypotheses", []), "conclusion": {"cause": "reproduced bounded defect"}, "next_experiment": {"id": "experiment-" + str(operation["repair_attempt"]), "approach": "change-one-bounded-cause-" + str(operation["repair_attempt"]), "finding_id": "finding-1"}, "actionable": self.actionable}
            if not self.actionable:
                diagnosis["blocker"] = "required fixture capability unavailable"
            return {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": True, "runtime": self._runtime(operation), "diagnosis": diagnosis, "elapsed_seconds": 1}
        if operation["phase"] == "repair":
            if self.outcome == "incomplete":
                return {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": False, "runtime": self._runtime(operation), "execution_evidence": evidence, "elapsed_seconds": 1}
            return self.worker(operation, observation, {"head": "c" * 40, "base": "b" * 40}, "build", "pass", evidence)
        result = self.worker(operation, observation, operation["candidate"], "verify", self.outcome, evidence)
        if self.progress:
            result["progress"] = [{"id": "progress-" + str(operation["repair_attempt"]), "cycle_id": "cycle-" + str(operation["repair_attempt"]), "criterion_id": "AC01", "finding_id": "finding-1", "before": "failure-observation", "after": "changed-observation-" + str(operation["repair_attempt"]), "verification_operation_id": operation["id"], "evidence": evidence}]
        return result

    def worker(self, operation, observation, candidate, phase, verdict, execution_evidence):
        artifact = "artifact-" + operation["phase"]
        command = operation["task"]["commands"][phase][0]
        criteria = self.criteria_outcomes or {criterion: ("pass" if verdict == "pass" else "fail") for criterion in operation["task"]["criteria"]}
        result = {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": True, "candidate": candidate, "criteria": criteria, "executed_checks": list(operation["task"]["criteria"]), "runtime": self._runtime(operation), "artifacts": [artifact], "tools": list(operation["task"]["commands"][phase]), "wall_time_seconds": 1, "elapsed_seconds": 1, "host_counters": {"tokens": None, "cost": None}, "evidence": {"artifact": {"id": artifact, "task_id": operation["task"]["id"], "operation_id": operation["id"], "head": candidate["head"], "base": candidate["base"]}, "commands": [{"command": command, "result": "pass", "artifact_id": artifact, "operation_id": operation["id"]}], "checks": [{"criterion_id": criterion, "command": command, "result": "pass", "artifact_id": artifact, "operation_id": operation["id"]} for criterion in operation["task"]["criteria"]]}, "fresh_context": phase == "verify", "builder_transcript": False, "verdict": verdict, "nonblocking_findings": [{"id": "retained"}], "execution_evidence": execution_evidence}
        return result


class EscalatedFixture(RepairFixture):
    def preflight_escalated(self, operation):
        return {"session_id": operation["session_id"], **operation["route"]}

    def confirm_escalated(self, operation):
        return {"session_id": operation["session_id"], **operation["route"]}

    def send(self, operation):
        result = super().send(operation)
        if "escalated_slot" in operation:
            result["diagnosis"] = {"id": operation["purpose"], "operation_id": operation["id"],
                                   "criteria": operation["task"]["criteria"], "revisions": {"head": "a" * 40, "base": "b" * 40},
                                   "execution_evidence": [{"id": "escalated-evidence", "command": "unit", "result": "pass", "artifact_id": "artifact-escalated"}],
                                   "prior_hypotheses": operation["prior_hypotheses"], "conclusion": {"cause": "missing setup"},
                                   "next_experiment": {"id": operation["purpose"], "approach": "fix approved setup " + str(operation["escalated_slot"]), "finding_id": "finding-1"},
                                   "actionable": True}
        return result


class RepairPolicyTests(unittest.TestCase):
    def test_escalated_no_candidate_spends_slot_and_next_hypothesis_needs_second(self):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        snapshot = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        snapshot = coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture("incomplete"), RepairFixture())
        self.assertEqual(snapshot.value["repair"]["status"], "escalation-ready")
        self.assertEqual(len(snapshot.value["repair"]["escalated_slots"]), 1)
        snapshot = coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        self.assertEqual(snapshot.value["repair"]["status"], "completed")
        self.assertEqual(len(snapshot.value["repair"]["escalated_slots"]), 2)
        self.assertEqual(len([op for op in snapshot.value["usage"]["operations"] if op["phase"] == "repair-verify"]), 1)

    def test_prepared_escalated_session_resumes_same_operation_after_crash(self):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        snapshot = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        class Crash(EscalatedFixture):
            def send(self, operation):
                raise SystemExit("simulated process loss before message dispatch")
        with self.assertRaises(SystemExit):
            coordinator.escalate_once(snapshot, "TASK-413", self.task(), Crash(), RepairFixture())
        reloaded = self.store(self.second).reload(initial_record(approved))
        pending = next(op for op in reloaded.value["usage"]["operations"] if op.get("escalated_slot"))
        self.assertEqual(pending["status"], "intent")
        self.assertIn("route_preflight", pending)
        self.assertNotIn("send_admission", pending)
        resumed = InterimRepairCoordinator(self.store(self.second), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc)).repair_once(
            reloaded, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        self.assertEqual(resumed.value["repair"]["status"], "completed")
        self.assertEqual(resumed.value["repair"]["escalated_slots"], [pending["id"]])
        self.assertEqual(len([op for op in resumed.value["usage"]["operations"] if op.get("escalated_slot")]), 1)

    def test_idle_session_crash_before_preflight_checkpoint_reconciles_exact_uuid(self):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        snapshot = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        class CrashBeforeMarker(EscalatedFixture):
            def preflight_escalated(self, operation):
                raise SystemExit("simulated process loss after exact idle session creation")
        with self.assertRaises(SystemExit):
            coordinator.escalate_once(snapshot, "TASK-413", self.task(), CrashBeforeMarker(), RepairFixture())
        reloaded = self.store(self.second).reload(initial_record(approved))
        pending = next(op for op in reloaded.value["usage"]["operations"] if op.get("escalated_slot"))
        self.assertEqual(pending["status"], "intent")
        self.assertNotIn("route_preflight", pending)
        self.assertNotIn("receipt", pending)
        self.assertNotIn("send_admission", pending)
        self.assertEqual(validate_record(reloaded.value)["repair"]["escalated_slots"], [pending["id"]])
        resumed = InterimRepairCoordinator(self.store(self.second), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc)).repair_once(
            reloaded, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        self.assertEqual(resumed.value["repair"]["status"], "completed")
        self.assertEqual(resumed.value["repair"]["escalated_slots"], [pending["id"]])

    def test_escalated_diagnosis_and_fix_share_one_reserved_operation(self):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        snapshot = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        self.assertEqual(snapshot.value["repair"]["status"], "escalation-ready")
        snapshot = coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        self.assertEqual(snapshot.value["repair"]["status"], "completed")
        self.assertEqual(len(snapshot.value["repair"]["escalated_slots"]), 1)
        self.assertEqual(len([op for op in snapshot.value["usage"]["operations"] if op.get("escalated_slot")]), 1)
        self.assertEqual(next(op for op in snapshot.value["usage"]["operations"] if op.get("escalated_slot"))["route_preflight"]["model"], "gpt-6-astra")
        self.assertEqual(snapshot.value["repair"]["cycles"][-1]["outcome"], "pass")

    def test_completed_standalone_escalation_replay_refuses_missing_preflight(self):
        approved, store, coordinator, snapshot = self.ready_escalation()
        completed = coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        recorded = store.reload(initial_record(approved)).value
        self.assertEqual(recorded["repair"]["status"], "completed")
        self.assertNotIn("monitoring", recorded)
        corrupted = deepcopy(recorded)
        operation = next(item for item in corrupted["usage"]["operations"] if item.get("escalated_slot"))
        self.assertIn("route_preflight", operation)
        self.assertNotIn("send_admission", operation)
        operation.pop("route_preflight")
        with self.assertRaisesRegex(InterimError, "preflight"):
            validate_record(corrupted)

    def test_completed_monitored_escalation_replay_refuses_missing_preflight(self):
        approved, store, coordinator, snapshot = self.ready_escalation(monitored=True)
        coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        recorded = store.reload(initial_record(approved)).value
        self.assertEqual(recorded["repair"]["status"], "completed")
        self.assertIn("monitoring", recorded)
        corrupted = deepcopy(recorded)
        operation = next(item for item in corrupted["usage"]["operations"] if item.get("escalated_slot"))
        self.assertIn("route_preflight", operation)
        operation.pop("route_preflight")
        with self.assertRaisesRegex(InterimError, "preflight"):
            validate_record(corrupted)

    def test_no_candidate_escalated_receipt_replay_refuses_missing_preflight(self):
        approved, store, coordinator, snapshot = self.ready_escalation()
        coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture("incomplete"), RepairFixture())
        recorded = store.reload(initial_record(approved)).value
        operation = next(item for item in recorded["usage"]["operations"] if item.get("escalated_slot"))
        self.assertEqual(recorded["repair"]["status"], "escalation-ready")
        self.assertFalse(operation["receipt"]["task_success"])
        self.assertEqual(len(recorded["repair"]["escalated_slots"]), 1)
        corrupted = deepcopy(recorded)
        next(item for item in corrupted["usage"]["operations"] if item.get("escalated_slot")).pop("route_preflight")
        with self.assertRaisesRegex(InterimError, "preflight"):
            validate_record(corrupted)

    def test_three_cumulative_ordinary_failures_enter_first_reserved_escalated_cycle(self):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"},
                                         "trigger": 3, "scope": "approved-slice",
                                         "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        snapshot = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        for attempt in range(3):
            snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("fail"), RepairFixture("fail"))
            if attempt < 2:
                self.assertEqual(snapshot.value["repair"]["status"], "repair-ready")
        self.assertEqual(snapshot.value["repair"]["status"], "escalation-ready")
        self.assertEqual(len(snapshot.value["repair"]["cycles"]), 3)
        self.assertEqual(snapshot.value["repair"]["escalated_slots"], [])
        self.assertEqual(self.store(self.second).reload(initial_record(approved)).value["repair"]["status"], "escalation-ready")

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name); self.remote = self.root / "remote.git"
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.remote_maintenance = None
        if getattr(self, "maintenance_loose_threshold", None) is not None:
            from checkpoint_fixture_support import OwnedRemoteMaintenance
            self.remote_maintenance = OwnedRemoteMaintenance(self.temp, self.remote, self.git,
                                                            threshold=self.maintenance_loose_threshold)
            self.remote_maintenance.configure()
        self.first, self.second = self.clone("first"), self.clone("second")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def clone(self, name: str) -> Path:
        if self.remote_maintenance is not None:
            self.remote_maintenance.before_clone()
        path = self.root / name
        try:
            self.git("clone", "-q", "--no-local", str(self.remote), str(path), cwd=self.root)
        except subprocess.CalledProcessError as exc:
            stderr = "".join(char for char in (exc.stderr or "").strip() if char.isprintable() or char == "\n")
            raise AssertionError(f"Git fixture clone failed: {stderr or '<empty stderr>'}") from exc
        self.git("config", "user.name", "Interim Repair Test", cwd=path)
        self.git("config", "user.email", "repair@example.invalid", cwd=path)
        return path

    def approval(self) -> dict:
        remote_url = self.git("remote", "get-url", "origin", cwd=self.first).stdout.strip()
        return approval(remote_url, remote_url)

    def store(self, repository: Path) -> InterimCheckpointStore:
        return InterimCheckpointStore(repository, "origin", self.approval()["checkpoint"]["ref"])

    def task(self, criteria=None):
        return {"id": "build-task-413", "slice_id": "TASK-413", "attempt": 1, "candidate_ref": "candidate-task-413", "base": "b" * 40, "criteria": criteria or ["AC01"], "runtimes": {"build": {"runner": "build-runner", "permissions": "read-only"}, "verify": {"runner": "verify-runner", "permissions": "read-only"}}, "commands": {"build": ["unit"], "verify": ["unit"], "qa": ["qa-command"], "ci": ["ci-command"]}, "limits": {"max_artifacts": 2, "max_tools": 2, "wall_time_seconds": 60}}

    def s2_approval(self, task=None):
        approved = self.approval()
        approved["forecast"] = {"work_units": 3, "verification_units": 1, "likely_repair_units": 1, "final_handback_units": 1}
        task = task or self.task()
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)}]
        return approved

    def ready_escalation(self, *, allowance=2, hard_limits="none", monitored=False):
        approved = self.s2_approval()
        approved["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"}, "trigger": 1,
                                         "scope": "approved-slice", "authority": "diagnose-and-implement", "cycles_per_slice": allowance}
        approved["hard_limits"] = hard_limits
        store = self.store(self.first)
        if monitored:
            store.monitored("11111111-1111-4111-8111-111111111111", dispatch_emitter=lambda _where: None)
        snapshot = store.create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        snapshot = InterimFixtureCoordinator(store).run_one(snapshot, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(store, clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        snapshot = coordinator.open(snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture())
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        return approved, store, coordinator, snapshot

    def test_escalation_exhausts_two_reserved_no_candidate_slots(self):
        approved, store, coordinator, snapshot = self.ready_escalation()
        for expected in ("escalation-ready", "stuck"):
            snapshot = coordinator.escalate_once(snapshot, "TASK-413", self.task(), EscalatedFixture("incomplete"), RepairFixture())
            self.assertEqual(snapshot.value["repair"]["status"], expected)
        self.assertEqual(len(snapshot.value["repair"]["escalated_slots"]), 2)
        self.assertEqual(len([op for op in snapshot.value["usage"]["operations"] if op.get("escalated_slot")]), 2)
        self.assertEqual(store.reload(initial_record(approved)).value["repair"]["escalated_slots"], snapshot.value["repair"]["escalated_slots"])

    def test_escalated_route_mismatch_reports_stuck_without_worker_message(self):
        _, _, coordinator, snapshot = self.ready_escalation()
        class Mismatch(EscalatedFixture):
            def preflight_escalated(self, operation):
                return {"session_id": operation["session_id"], "model": "gpt-6-sol", "effort": "high"}
        host = Mismatch()
        stopped = coordinator.escalate_once(snapshot, "TASK-413", self.task(), host, RepairFixture())
        self.assertEqual(stopped.value["repair"]["status"], "stuck")
        self.assertEqual(host.operations, [])
        self.assertEqual(len(stopped.value["repair"]["escalated_slots"]), 1)
        pending = next(op for op in stopped.value["usage"]["operations"] if op.get("escalated_slot"))
        self.assertEqual(pending["status"], "intent")
        self.assertNotIn("route_preflight", pending)
        self.assertEqual(validate_record(stopped.value)["repair"]["escalated_slots"], [pending["id"]])

    def test_selected_dispatch_cap_refuses_escalation_before_new_slot(self):
        _, _, coordinator, snapshot = self.ready_escalation(hard_limits={"dispatch_max": 4})
        host = EscalatedFixture()
        stopped = coordinator.escalate_once(snapshot, "TASK-413", self.task(), host, RepairFixture())
        self.assertEqual(stopped.value["repair"]["escalated_slots"], [])
        self.assertEqual(host.operations, [])
        self.assertIn("selected dispatch cap", stopped.value["state"]["handback"]["reason"])

    def test_ambiguous_idle_preflight_rechecks_same_reserved_id_at_backup_cadence(self):
        approved, store, coordinator, snapshot = self.ready_escalation(monitored=True)
        class Ambiguous(EscalatedFixture):
            def preflight_escalated(self, operation):
                raise ObservationFailure("uncertain-effect")
        host = Ambiguous()
        waiting = coordinator.escalate_once(snapshot, "TASK-413", self.task(), host, RepairFixture())
        pending = next(op for op in waiting.value["usage"]["operations"] if op.get("escalated_slot"))
        self.assertEqual(waiting.value["repair"]["status"], "waiting-repair")
        self.assertEqual(waiting.value["recovery_disposition"]["active"]["count"], 1)
        self.assertEqual(host.operations, [])
        reloaded = self.store(self.second).reload(initial_record(approved))
        resumed = InterimRepairCoordinator(self.store(self.second), clock=lambda: datetime(2026, 9, 19, 0, 16, tzinfo=timezone.utc)).repair_once(
            reloaded, "TASK-413", self.task(), EscalatedFixture(), RepairFixture())
        self.assertEqual(resumed.value["repair"]["status"], "completed")
        self.assertEqual(resumed.value["repair"]["escalated_slots"], [pending["id"]])

    def test_stop_during_idle_preflight_wins_final_admission_without_message(self):
        approved, store, coordinator, snapshot = self.ready_escalation(monitored=True)
        class StopDuringPreflight(EscalatedFixture):
            def preflight_escalated(self, operation):
                current = store.reload(initial_record(approved))
                projected = deepcopy(current.value)
                projected["recovery"] = {"status": "stopping", "wakes": [], "observations": [],
                                         "stop": {"intent_at": "2026-09-19T00:00:00Z", "instruction": "Stop",
                                                  "prefix_removed": False, "cancellations": [], "uncertainty": None}, "resume": None}
                store.persist(current, projected)
                return super().preflight_escalated(operation)
        host = StopDuringPreflight()
        with self.assertRaises(InterimCheckpointError):
            coordinator.escalate_once(snapshot, "TASK-413", self.task(), host, RepairFixture())
        final = store.reload(initial_record(approved)).value
        self.assertEqual(final["recovery"]["status"], "stopping")
        self.assertEqual(len(final["repair"]["escalated_slots"]), 1)
        self.assertEqual(host.operations, [])

    def test_three_unusable_fresh_verifiers_exhaust_same_sha_without_new_astra_slot(self):
        approved, store, coordinator, snapshot = self.ready_escalation(monitored=True)
        class Errors(EscalatedFixture):
            def __init__(self):
                super().__init__()
                self.verifies = 0
            def send(self, operation):
                if operation["phase"] == "repair-verify":
                    self.verifies += 1
                    return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                            "transport": "accepted", "worker_state": "error", "terminal_turn": False, "elapsed_seconds": 0}
                return super().send(operation)
            def reconcile_failed(self, operation, record, repository):
                candidate = operation["candidate"]
                return {"observation": {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")},
                        "ceased": True, "candidate": candidate, "branch_head": candidate["head"], "pr": None,
                        "candidate_work": {"paths": [], "digest": "sha256:" + "a" * 64, "head": candidate["head"]}, "effects_complete": True}
            def observe_coordinator(self, operation):
                return Fixture({}).observe_coordinator(operation)
        host = Errors()
        snapshot = coordinator.escalate_once(snapshot, "TASK-413", self.task(), host, host)
        self.assertEqual(snapshot.value["state"]["next_action"], "worker-failed")
        tasks = {"TASK-413": self.task()}
        outcomes = []
        for _ in range(10):
            outcomes.append(advance_once(store, initial_record(approved), tasks, host)["outcome"])
            current = store.reload(initial_record(approved)).value
            if current["repair"]["status"] == "stuck":
                break
        self.assertEqual(current["repair"]["status"], "stuck", outcomes)
        self.assertEqual(host.verifies, 3)
        self.assertEqual(len(current["repair"]["escalated_slots"]), 1)
        self.assertEqual(len([op for op in current["usage"]["operations"] if op["phase"] == "repair-verify"]), 3)
        self.assertNotEqual(current["state"]["next_action"], "repair-complete")



    def result(self, phase="build", candidate=None):
        candidate = candidate or {"head": "a" * 40, "base": "b" * 40}
        route = self.approval()["routes"]["verify" if phase == "verify" else "build"]
        return {"transport": "accepted", "terminal_turn": True, "task_success": True, "candidate": candidate, "criteria": {"AC01": "pass"}, "executed_checks": ["AC01"], "runtime": {"model": route["model"], "effort": route["effort"], "runner": phase + "-runner", "permissions": "read-only"}, "fresh_context": phase == "verify", "builder_transcript": False, "verdict": "pass", "nonblocking_findings": [{"id": "N1"}], "artifacts": ["artifact"], "tools": ["unit"], "wall_time_seconds": 1, "elapsed_seconds": 1, "host_counters": {"tokens": None, "cost": None}}

    def failed_s2(self, task=None):
        task = task or self.task()
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval(task)))
        failed = self.result(); failed["task_success"] = False
        return InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", task, Fixture(failed), Fixture(self.result("verify")))

    def finding(self):
        evidence = [{"id": "opening-evidence", "command": "unit", "result": "pass", "artifact_id": "artifact-opening"}]
        return {"id": "finding-1", "criterion_id": "AC01", "summary": "reproducible bounded failure", "reversible": True, "scope": "in-scope", "external_effect": False, "requirement_changed": False, "capability": "available", "evidence": evidence}, evidence

    def open_and_diagnose(self):
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        return coordinator, coordinator.diagnose(opened, "TASK-413", self.task(), RepairFixture())

    def test_table_driven_repair_policy_boundaries(self):
        cases = [
            ("initial-build-verify-do-not-consume-cycle", "pass", False, "completed", 1),
            ("incomplete-repair-counts-without-fake-verify", "incomplete", False, "repair-ready", 1),
            ("failing-verify-without-independent-progress-remains-eligible", "fail", False, "repair-ready", 1),
            ("failing-verify-with-independent-progress-needs-new-diagnosis", "fail", True, "diagnosis-required", 1),
        ]
        for name, outcome, progress, status, cycles in cases:
            with self.subTest(name=name):
                self.tearDown(); self.setUp()
                coordinator, diagnosed = self.open_and_diagnose()
                final = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture(outcome, progress), RepairFixture(outcome, progress))
                self.assertEqual(final.value["repair"]["status"], status)
                self.assertEqual(len(final.value["repair"]["cycles"]), cycles)
                self.assertEqual(final.value["repair"]["cycles"][0]["attempt"], 1)
                if outcome == "incomplete":
                    self.assertIsNone(final.value["repair"]["cycles"][0]["verify_operation_id"])
                    self.assertEqual([item["phase"] for item in final.value["usage"]["operations"]].count("repair-verify"), 0)

    def test_repeated_progress_scope_escape_and_unactionable_diagnosis_hand_back(self):
        coordinator, diagnosed = self.open_and_diagnose()
        first = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("fail", True), RepairFixture("fail", True))
        self.assertEqual(first.value["repair"]["status"], "diagnosis-required")
        second = coordinator.diagnose(first, "TASK-413", self.task(), RepairFixture())
        # Same evidence cannot be counted again; a failed cycle with it stops.
        repeated = RepairFixture("fail", True)
        stopped = coordinator.repair_once(second, "TASK-413", self.task(), repeated, repeated)
        self.assertEqual(stopped.value["repair"]["status"], "repair-ready")

        escaped = deepcopy(stopped.value)
        escaped["repair"]["opening"]["finding"]["scope"] = "out-of-scope"
        with self.assertRaisesRegex(InterimError, "eligible reversible"):
            validate_record(escaped)

        self.tearDown(); self.setUp()
        coordinator = InterimRepairCoordinator(self.store(self.first), clock=lambda: datetime(2026, 9, 19, tzinfo=timezone.utc))
        finding, evidence = self.finding()
        opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        unavailable = coordinator.diagnose(opened, "TASK-413", self.task(), RepairFixture(actionable=False))
        self.assertEqual(unavailable.value["repair"]["status"], "handback")
        self.assertEqual(len(unavailable.value["repair"]["cycles"]), 0)

    def test_reforecast_survives_clean_reload_and_no_cap_does_not_stop(self):
        coordinator, diagnosed = self.open_and_diagnose()
        final = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("pass"), RepairFixture("pass"))
        operation_id = final.value["repair"]["cycles"][0]["verify_operation_id"]
        revised = coordinator.revise_forecast(final, {"work_units": 99, "verification_units": 99, "likely_repair_units": 99, "final_handback_units": 1}, operation_id, "verified repair evidence exceeded the initial estimate")
        self.assertEqual(revised.value["approval"]["hard_limits"], "none")
        self.assertGreaterEqual(len(revised.value["forecasts"]["revised"]), 2)
        reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
        self.assertEqual(reloaded.value["forecasts"], revised.value["forecasts"])

    def test_repair_portable_validation_refuses_rewritten_or_repeated_progress(self):
        coordinator, diagnosed = self.open_and_diagnose()
        final = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("fail", True), RepairFixture("fail", True))
        corrupt = deepcopy(final.value)
        corrupt["repair"]["progress"].append(deepcopy(corrupt["repair"]["progress"][0]))
        with self.assertRaisesRegex(InterimError, "credited twice"):
            validate_record(corrupt)
        corrupt = deepcopy(final.value)
        operation = next(item for item in corrupt["usage"]["operations"] if item["phase"] == "repair")
        operation["purpose"] = "same-looking-rewrite"
        with self.assertRaisesRegex(InterimError, "purpose|identity"):
            validate_record(corrupt)

    def test_three_different_unsuccessful_cycles_require_a_fresh_changed_diagnosis(self):
        coordinator, snapshot = self.open_and_diagnose()
        for attempt in range(1, 4):
            with self.subTest(attempt=attempt):
                snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("fail", True, distinct=True), RepairFixture("fail", True, distinct=True))
                self.assertEqual(snapshot.value["repair"]["status"], "diagnosis-required")
                if attempt < 3:
                    snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture(distinct=True))
                    self.assertEqual(snapshot.value["repair"]["status"], "repair-ready")
        # The third differing failure still requires a newly observed diagnosis.
        refreshed = coordinator.diagnose(snapshot, "TASK-413", self.task(), RepairFixture(distinct=True))
        self.assertEqual(refreshed.value["repair"]["status"], "repair-ready")
        self.assertEqual(len(refreshed.value["repair"]["cycles"]), 3)
        self.assertEqual(len(refreshed.value["repair"]["diagnoses"]), 4)

    def test_selected_cap_blocks_diagnosis_and_final_review_blocker_uses_same_policy(self):
        approved = self.s2_approval(); approved["hard_limits"] = {"dispatch_max": 2}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        failed_snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(failed_snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        diagnosis = RepairFixture()
        stopped = coordinator.diagnose(opened, "TASK-413", self.task(), diagnosis)
        self.assertEqual(stopped.value["repair"]["status"], "handback")
        self.assertEqual(diagnosis.operations, [])

        self.tearDown(); self.setUp()
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        pr_ready = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(pr_ready, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        diagnosed = coordinator.diagnose(opened, "TASK-413", self.task(), RepairFixture())
        self.assertEqual(diagnosed.value["repair"]["status"], "repair-ready")

    def test_repair_consuming_final_dispatch_slot_never_sends_fresh_verify(self):
        approved = self.s2_approval(); approved["hard_limits"] = {"dispatch_max": 4}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        failed = self.result(); failed["task_success"] = False
        failed_snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(failed_snapshot, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        diagnosed = coordinator.diagnose(opened, "TASK-413", self.task(), RepairFixture())
        verify = RepairFixture()
        stopped = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("pass"), verify)
        self.assertEqual(len(stopped.value["usage"]["launches"]), 4)
        self.assertEqual([item["phase"] for item in stopped.value["usage"]["operations"]].count("repair-verify"), 0)
        self.assertEqual(stopped.value["repair"]["cycles"][-1]["outcome"], "incomplete")
        self.assertEqual(verify.operations, [])

    def test_repair_receipts_reuse_full_worker_contract_and_bind_base(self):
        class BadRuntime(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] in {"repair", "repair-verify"}:
                    result["runtime"]["runner"] = "wrong-runner"; result["runtime"]["permissions"] = "danger-full-access"
                return result

        class BadVerify(BadRuntime):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "repair-verify":
                    result["runtime"] = self._runtime(operation); result["fresh_context"] = False
                return result

        class BadBase(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "repair":
                    result["candidate"]["base"] = "d" * 40
                    result["evidence"]["artifact"]["base"] = "d" * 40
                return result

        for adapter, verify, label in ((BadRuntime("pass"), RepairFixture("pass"), "runtime"), (BadBase("pass"), RepairFixture("pass"), "base"), (RepairFixture("pass"), BadVerify("pass"), "fresh")):
            with self.subTest(label=label):
                self.tearDown(); self.setUp()
                coordinator, diagnosed = self.open_and_diagnose()
                stopped = coordinator.repair_once(diagnosed, "TASK-413", self.task(), adapter, verify)
                self.assertNotEqual(stopped.value["repair"]["status"], "completed")
                self.assertEqual(stopped.value["state"]["next_action"], "handback")

    def test_fresh_failing_verify_retains_mixed_complete_approved_criteria(self):
        task = self.task(["AC01", "AC02"])
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval(task)))
        failed = self.result(); failed["task_success"] = False
        failed_snapshot = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", task, Fixture(failed), Fixture(self.result("verify")))
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(failed_snapshot, "TASK-413", task, finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        diagnosed = coordinator.diagnose(opened, "TASK-413", task, RepairFixture())
        outcomes = {"AC01": "fail", "AC02": "pass"}
        stopped = coordinator.repair_once(diagnosed, "TASK-413", task, RepairFixture("pass"), RepairFixture("fail", criteria_outcomes=outcomes))
        receipt = next(item for item in stopped.value["usage"]["operations"] if item["phase"] == "repair-verify")["receipt"]
        self.assertEqual(receipt["criteria"], outcomes)
        self.assertEqual(stopped.value["repair"]["cycles"][-1]["outcome"], "fail")
        self.assertEqual(stopped.value["repair"]["status"], "repair-ready")
        reloaded = self.store(self.second).reload(initial_record(self.s2_approval(task)))
        persisted = next(item for item in reloaded.value["usage"]["operations"] if item["phase"] == "repair-verify")
        self.assertEqual(persisted["receipt"]["criteria"], outcomes)

    def test_correlated_unusable_results_keep_raw_receipt_charge_and_no_resend(self):
        class BadDiagnosis(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "diagnosis":
                    result["diagnosis"]["operation_id"] = "unrelated"
                return result

        class BadRepair(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "repair":
                    result["runtime"]["runner"] = "unapproved-runner"
                return result

        class BadVerify(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "repair-verify":
                    result["fresh_context"] = False
                return result

        for phase, diagnosis_adapter, repair_adapter, verify_adapter in (
            ("diagnosis", BadDiagnosis(), None, None),
            ("repair", RepairFixture(), BadRepair(), RepairFixture()),
            ("repair-verify", RepairFixture(), RepairFixture(), BadVerify()),
        ):
            with self.subTest(phase=phase):
                self.tearDown(); self.setUp()
                coordinator = InterimRepairCoordinator(self.store(self.first))
                finding, evidence = self.finding()
                opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
                diagnosed = coordinator.diagnose(opened, "TASK-413", self.task(), diagnosis_adapter)
                stopped = diagnosed if phase == "diagnosis" else coordinator.repair_once(diagnosed, "TASK-413", self.task(), repair_adapter, verify_adapter)
                operation = next(item for item in stopped.value["usage"]["operations"] if item["phase"] == phase)
                charge = next(item for item in stopped.value["usage"]["charges"] if item["operation_id"] == operation["id"])
                self.assertEqual((operation["status"], charge["status"]), ("result-unusable", "observed"))
                self.assertIn("receipt", operation)
                self.assertEqual(operation["elapsed_seconds"], 1)
                self.assertIn("Error:", operation["validation_error"])
                self.assertEqual(stopped.value["state"]["next_action"], "handback")
                reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
                persisted = next(item for item in reloaded.value["usage"]["operations"] if item["id"] == operation["id"])
                self.assertEqual(persisted["receipt"], operation["receipt"])

    def test_late_policy_failures_keep_correlated_diagnosis_and_verify_receipts(self):
        class UnactionableMalformedDiagnosis(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "diagnosis":
                    result["diagnosis"]["criteria"] = []
                return result

        class UnapprovedProgress(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "repair-verify":
                    result["progress"] = [{"id": "unapproved-progress", "cycle_id": "cycle-1", "criterion_id": "AC-unapproved", "finding_id": "finding-1", "before": "before", "after": "after", "verification_operation_id": operation["id"], "evidence": result["execution_evidence"]}]
                return result

        # A terminal, correlated unactionable diagnosis fails only when the
        # policy projects it into retained diagnosis history.
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        diagnosis = coordinator.diagnose(opened, "TASK-413", self.task(), UnactionableMalformedDiagnosis(actionable=False))
        self._assert_late_unusable_and_reloaded(diagnosis, "diagnosis")

        # Fresh Verify itself is S2-valid; only caller-supplied progress names
        # an unapproved criterion when the repair policy validates it.
        self.tearDown(); self.setUp()
        coordinator, diagnosed = self.open_and_diagnose()
        verify = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("pass"), UnapprovedProgress("fail"))
        self._assert_late_unusable_and_reloaded(verify, "repair-verify")
        raw = next(item for item in verify.value["usage"]["operations"] if item["phase"] == "repair-verify")["receipt"]
        self.assertEqual(raw["progress"][0]["criterion_id"], "AC-unapproved")

    def _assert_late_unusable_and_reloaded(self, snapshot, phase):
        operation = next(item for item in snapshot.value["usage"]["operations"] if item["phase"] == phase)
        charge = next(item for item in snapshot.value["usage"]["charges"] if item["operation_id"] == operation["id"])
        self.assertEqual((operation["status"], charge["status"]), ("result-unusable", "observed"))
        self.assertIn("receipt", operation)
        self.assertEqual(operation["elapsed_seconds"], 1)
        self.assertRegex(operation["validation_error"], r"^[A-Za-z]+Error: .+")
        self.assertIn("will not be resent", snapshot.value["state"]["handback"]["reason"])
        reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
        persisted = next(item for item in reloaded.value["usage"]["operations"] if item["id"] == operation["id"])
        self.assertEqual(persisted["receipt"], operation["receipt"])
        self.assertEqual(persisted["validation_error"], operation["validation_error"])

    def test_post_diagnosis_no_progress_allows_two_cycles_then_sticks_on_third(self):
        coordinator, snapshot = self.open_and_diagnose()
        for attempt, expected in ((1, "repair-ready"), (2, "repair-ready"), (3, "stuck")):
            snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), RepairFixture("fail", distinct=True), RepairFixture("fail", distinct=True))
            self.assertEqual(snapshot.value["repair"]["status"], expected)
            self.assertEqual(snapshot.value["repair"]["batch"]["no_progress"], attempt)
        self.assertEqual(len(snapshot.value["repair"]["cycles"]), 3)

    def test_forecast_revises_before_continuation_and_rejects_zero_remaining_work(self):
        coordinator, diagnosed = self.open_and_diagnose()
        # Diagnosis evidence raises the estimate before the first repair send;
        # the initial work capacity is already consumed by coordinator/Build/diagnosis.
        before = len(diagnosed.value["forecasts"]["revised"])
        incomplete = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("incomplete"), RepairFixture())
        self.assertGreaterEqual(len(incomplete.value["forecasts"]["revised"]), before)
        latest = next(item["id"] for item in reversed(incomplete.value["usage"]["operations"]) if item.get("receipt"))
        with self.assertRaisesRegex(Exception, "reforecast"):
            coordinator.revise_forecast(incomplete, {"work_units": 9, "verification_units": 0, "likely_repair_units": 0, "final_handback_units": 0}, latest, "zero remaining required work")

    def test_unavailable_fresh_verify_keeps_resumable_intent_without_spending_cycle(self):
        class TimeoutVerify(RepairFixture):
            def send(self, operation):
                if operation["phase"] == "repair-verify":
                    raise TimeoutError("injected verify timeout")
                return super().send(operation)

        coordinator, diagnosed = self.open_and_diagnose()
        stopped = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("pass"), TimeoutVerify("pass"))
        self.assertEqual(stopped.value["repair"]["status"], "waiting-repair-verify")
        self.assertEqual(stopped.value["repair"]["cycles"], [])
        self.assertEqual(stopped.value["repair"]["batch"]["no_progress"], 0)
        pending = next(item for item in stopped.value["usage"]["operations"] if item["phase"] == "repair-verify")
        self.assertEqual(pending["status"], "intent")
        self.assertNotIn("receipt", pending)
        reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
        self.assertEqual(reloaded.value["repair"]["cycles"], stopped.value["repair"]["cycles"])

    def test_unactionable_diagnosis_keeps_observed_receipt_charge_and_history(self):
        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        stopped = coordinator.diagnose(opened, "TASK-413", self.task(), RepairFixture(actionable=False))
        operation = stopped.value["usage"]["operations"][-1]
        charge = next(item for item in stopped.value["usage"]["charges"] if item["operation_id"] == operation["id"])
        self.assertEqual(operation["status"], "result")
        self.assertIn("receipt", operation)
        self.assertEqual(operation["elapsed_seconds"], 1)
        self.assertEqual(charge["status"], "observed")
        self.assertEqual(stopped.value["repair"]["diagnoses"][-1]["actionable"], False)

    def test_unusable_diagnosis_keeps_observed_receipt_without_a_retry(self):
        class Unusable(RepairFixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "diagnosis":
                    result["diagnosis"]["criteria"] = []
                return result

        coordinator = InterimRepairCoordinator(self.store(self.first))
        finding, evidence = self.finding()
        opened = coordinator.open(self.failed_s2(), "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        stopped = coordinator.diagnose(opened, "TASK-413", self.task(), Unusable())
        operation = stopped.value["usage"]["operations"][-1]
        charge = next(item for item in stopped.value["usage"]["charges"] if item["operation_id"] == operation["id"])
        self.assertEqual((operation["status"], charge["status"]), ("result-unusable", "observed"))
        self.assertIn("receipt", operation)
        self.assertEqual(stopped.value["repair"]["diagnoses"], [])
        self.assertIn("unusable", stopped.value["state"]["handback"]["reason"])

    def test_forecast_revisions_are_complete_current_and_above_consumption(self):
        coordinator, diagnosed = self.open_and_diagnose()
        final = coordinator.repair_once(diagnosed, "TASK-413", self.task(), RepairFixture("pass"), RepairFixture("pass"))
        self.assertTrue(final.value["forecasts"]["revised"])
        self.assertEqual(set(final.value["forecasts"]["initial"]), {"work_units", "verification_units", "likely_repair_units", "final_handback_units"})
        last = final.value["repair"]["cycles"][0]["verify_operation_id"]
        with self.assertRaisesRegex(Exception, "reforecast"):
            coordinator.revise_forecast(final, {"work_units": 0, "verification_units": 0, "likely_repair_units": 0, "final_handback_units": 0}, last, "below retained use")
        old = final.value["usage"]["operations"][-2]["id"]
        with self.assertRaisesRegex(Exception, "reforecast"):
            coordinator.revise_forecast(final, {"work_units": 9, "verification_units": 9, "likely_repair_units": 9, "final_handback_units": 1}, old, "stale worker evidence")


class CloneTransportTests(unittest.TestCase):
    """A clean checkpoint clone must not copy unrelated source object entries."""

    def test_fixture_helpers_reject_missing_or_invalid_remote(self):
        for fixture_type in (interim_tests.InterimCheckpointTests, RepairPolicyTests):
            fixture = fixture_type("run")
            fixture.setUp()
            try:
                for name in ("missing.git", "invalid.git"):
                    with self.subTest(helper=fixture_type.__name__, remote=name):
                        remote = fixture.root / name
                        if name == "invalid.git":
                            remote.mkdir()
                        fixture.remote = remote
                        with self.assertRaisesRegex(AssertionError, "Git fixture clone failed"):
                            fixture.clone("refused-" + name)
            finally:
                fixture.tearDown()

    def test_both_fixture_helpers_reload_exact_checkpoint_without_copying_source_objects(self):
        for fixture_type in (interim_tests.InterimCheckpointTests, RepairPolicyTests):
            with self.subTest(helper=fixture_type.__name__):
                fixture = fixture_type("run")
                fixture.setUp()
                try:
                    approved = initial_record(fixture.approval())
                    published = fixture.store(fixture.first).create_and_publish(approved)
                    # An irrelevant source object entry is enough to make the
                    # local-copy path fail. Transport reads reachable objects.
                    os.symlink(fixture.root / "removed-object", fixture.remote / "objects" / "stale-extra")
                    with self.assertRaises(subprocess.CalledProcessError) as local:
                        fixture.git("clone", "-q", str(fixture.remote), str(fixture.root / "local-copy"), cwd=fixture.root)
                    self.assertIn("symlink", local.exception.stderr)
                    clone = fixture.clone("clean-reload")
                    self.assertNotEqual(clone / ".git", fixture.first / ".git")
                    reloaded = fixture.store(clone).reload(approved)
                    self.assertEqual(reloaded.commit_sha, published.commit_sha)
                    self.assertEqual(reloaded.value, published.value)
                finally:
                    fixture.tearDown()

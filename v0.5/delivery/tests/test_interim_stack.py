from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import json
from copy import deepcopy
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim import InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, initial_record, validate_record  # noqa: E402
from delivery_pilot.interim_stack import InterimStackCoordinator, RoutineStackConflict, StackPolicyError  # noqa: E402
from delivery_pilot.interim_recovery import InterimRecoveryCoordinator  # noqa: E402
from delivery_pilot.interim_coordinator import InterimFixtureCoordinator  # noqa: E402
from delivery_pilot.canonical import digest  # noqa: E402
from delivery_pilot.interim_identity import operation_identities  # noqa: E402
from test_interim import approval  # noqa: E402


A, B, C, D = (char * 40 for char in "abcd")


class StackFixture:
    """Mocked PR observations; the temporary Git remote belongs to the checkpoint."""
    def __init__(self) -> None:
        self.observations: dict[str, dict] = {}
        self.applied: list[dict] = []
        self.timeout = False
        self.routine_conflict = False
        self.routine_conflict_detail = "cleanly reparable fixture conflict"
        self.restacked_candidate: dict | None = None
        self.bad_reconcile = False

    def receipt(self, operation: dict) -> dict:
        candidate = self.restacked_candidate if operation["kind"] == "restack" and self.restacked_candidate is not None else operation["candidate"]
        return {"operation_id": operation["id"], "candidate": deepcopy(candidate), "pr": {"url": "https://example.invalid/" + operation["slice_id"], "head": candidate["head"], "base": candidate["base"], "state": "open"}, "effect": operation["kind"]}

    def apply(self, operation: dict) -> dict:
        self.applied.append(deepcopy(operation))
        if self.routine_conflict:
            raise RoutineStackConflict(self.routine_conflict_detail)
        if self.timeout:
            raise TimeoutError("ambiguous provider response")
        return self.receipt(operation)

    def reconcile(self, operation: dict) -> dict:
        receipt = self.receipt(operation)
        if self.bad_reconcile:
            receipt["candidate"]["base"] = D
            receipt["pr"]["base"] = D
        return receipt

    def observe(self, slice_id: str, branch: str) -> dict:
        if slice_id not in self.observations:
            raise OSError("no current mocked PR observation")
        return deepcopy(self.observations[slice_id])


class InterimStackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name); self.remote = self.root / "remote.git"
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.first, self.second = self.clone("first"), self.clone("second")
        remote_url = self.git("remote", "get-url", "origin", cwd=self.first).stdout.strip()
        self.approval = approval(remote_url, remote_url)
        self.approval["run_id"] = "run-task-417"
        control = "refs/heads/delivery-control/issue-run-task-417"
        self.approval["repository"]["control_ref"] = self.approval["checkpoint"]["ref"] = control
        self.approval["slices"] = [
            {"id": "S4", "dependencies": [], "mode": "AFK"},
            {"id": "S5", "dependencies": ["S4"], "mode": "AFK"},
            {"id": "S6", "dependencies": ["S5"], "mode": "HITL"},
        ]
        task_bases = {"S4": B, "S5": A, "S6": C}
        self.task_specs = {
            slice_id: {"id": "verify-" + slice_id, "slice_id": slice_id, "attempt": 1, "candidate_ref": "candidate-" + slice_id, "base": task_bases[slice_id], "criteria": ["AC04"], "runtimes": {"build": {"runner": "build-runner", "permissions": "read-only"}, "verify": {"runner": "verify-runner", "permissions": "read-only"}}, "commands": {"build": ["build-unit"], "verify": ["unit"], "qa": ["qa-unit"], "ci": ["ci-unit"]}, "limits": {"max_artifacts": 1, "max_tools": 1, "wall_time_seconds": 60}}
            for slice_id in ("S4", "S5", "S6")
        }
        self.approval["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": self.approval["tracker"]["spec_revision"], "digest": digest(task)} for task in self.task_specs.values()]
        self.store = InterimCheckpointStore(self.first, "origin", control)
        self.snapshot = self.store.create_and_publish(initial_record(self.approval))
        self.coordinator = InterimStackCoordinator(self.store)
        self.snapshot = self.coordinator.initialise(self.snapshot, {"S4": "slice/s4", "S5": "slice/s5", "S6": "slice/s6"})
        self.adapter = StackFixture()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def clone(self, name: str) -> Path:
        path = self.root / name
        self.git("clone", "-q", str(self.remote), str(path), cwd=self.root)
        self.git("config", "user.name", "Stack Test", cwd=path); self.git("config", "user.email", "stack@example.invalid", cwd=path)
        return path

    @staticmethod
    def observation(head: str, base: str, state: str = "open", environment: str | None = None, restack_base: str | None = None) -> dict:
        result = {"candidate": {"head": head, "base": base}, "pr": {"url": "https://example.invalid/pr", "head": head, "base": base, "state": state}, "verification_environment_digest": environment or "sha256:" + "d" * 64}
        if restack_base is not None:
            result["restack_base"] = restack_base
        return result

    @staticmethod
    def review(candidate: dict, operation: dict, environment: str, findings=None) -> dict:
        findings = findings or []
        binding = digest({"candidate": candidate, "runtime": operation["receipt"]["runtime"], "artifact_id": operation["receipt"]["evidence"]["artifact"]["id"], "operation_id": operation["id"], "verification_environment_digest": environment})
        return {"candidate": deepcopy(candidate), "verdict": "pass", "fresh_context": True, "verify_operation_id": operation["id"], "verification_environment_digest": environment, "binding_digest": binding, "findings": findings}

    def attach_verify(self, slice_id: str, candidate: dict, findings) -> dict:
        suffix = str(len(self.snapshot.value["usage"]["operations"]) + 1)
        task = deepcopy(self.task_specs[slice_id])
        restack_operation_id = None
        if candidate["base"] != task["base"]:
            restack = next((item for item in self.snapshot.value["stack"]["operations"] if item["kind"] == "restack" and item["slice_id"] == slice_id and item["status"] == "result" and item["target_base"] == candidate["base"] and item["receipt"]["candidate"] == candidate), None)
            self.assertIsNotNone(restack, "changed-base Verify needs its completed durable restack")
            restack_operation_id = restack["id"]
        operation_id = "op-" + digest({"run": self.snapshot.value["approval"]["run_id"], "slice": slice_id, "task": task["id"], "attempt": task["attempt"], "candidate": candidate, "phase": "stack-verify"})[7:23]
        artifact = "verify-artifact-" + slice_id + "-" + suffix
        runtime = {"model": "gpt-5.6-sol", "effort": "medium", "runner": "verify-runner", "permissions": "read-only"}
        observation = {"id": operation_id, **operation_identities(self.snapshot.value["approval"]["run_id"], operation_id, "stack-verify")}
        operation = {"id": operation_id, "slice": slice_id, "phase": "stack-verify", "task": task, "candidate": deepcopy(candidate), "criteria": deepcopy(task["criteria"]), **observation, "status": "result", "issued_at": "2026-09-20T07:00:00Z", "elapsed_seconds": 1, "receipt": {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": True, "candidate": deepcopy(candidate), "criteria": {"AC04": "pass"}, "executed_checks": ["AC04"], "runtime": runtime, "artifacts": [artifact], "tools": ["unit"], "wall_time_seconds": 1, "host_counters": {"tokens": None, "cost": None}, "fresh_context": True, "builder_transcript": False, "verdict": "pass", "nonblocking_findings": deepcopy(findings), "evidence": {"artifact": {"id": artifact, "task_id": task["id"], "operation_id": operation_id, "head": candidate["head"], "base": candidate["base"]}, "commands": [{"command": "unit", "result": "pass", "artifact_id": artifact, "operation_id": operation_id}], "checks": [{"criterion_id": "AC04", "command": "unit", "result": "pass", "artifact_id": artifact, "operation_id": operation_id}]}}}
        if restack_operation_id is not None:
            operation["restack_operation_id"] = restack_operation_id
        record = deepcopy(self.snapshot.value); record["usage"]["operations"].append(operation)
        record["usage"]["launches"].append({"operation_id": operation_id, "phase": "stack-verify", "issued_at": operation["issued_at"]})
        record["usage"]["charges"].append({"operation_id": operation_id, "work_units": 1, "status": "observed", "charged_at": operation["issued_at"]})
        self.snapshot = self.coordinator.store.persist(self.snapshot, record)
        return operation

    def observe_accept(self, slice_id: str, head: str, base: str, findings=None) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, slice_id, self.observation(head, base))
        entry = next(item for item in self.snapshot.value["stack"]["slices"] if item["id"] == slice_id)
        findings = findings or []; operation = self.attach_verify(slice_id, entry["candidate"], findings)
        self.snapshot = self.coordinator.accept_review(self.snapshot, slice_id, self.review(entry["candidate"], operation, entry["verification_environment_digest"], findings))

    @staticmethod
    def final_operation_id(record: dict, kind: str, candidates: list[dict]) -> str:
        return "stack-final-" + digest({"run": record["approval"]["run_id"], "kind": kind, "candidates": candidates})[7:23]

    def attach_final_receipts(self, coordinator: InterimStackCoordinator, snapshot, verdict="pass", findings=None):
        """Record terminal final observations before passing only their IDs to finalise."""
        findings = findings or []
        record = deepcopy(snapshot.value); entries = record["stack"]["slices"]
        candidates = [{"slice_id": entry["id"], "candidate": entry["candidate"]} for entry in entries]
        operation_ids = {}
        for kind in ("final-qa", "final-ci"):
            operation_id = self.final_operation_id(record, kind, candidates); phase = "stack-" + kind
            observation = {"id": operation_id, **operation_identities(record["approval"]["run_id"], operation_id, phase)}
            check_kind = kind.removeprefix("final-")
            artifacts, checks = [], []
            for entry, candidate in zip(entries, candidates):
                verify = next(item for item in record["usage"]["operations"] if item["id"] == entry["review"]["verify_operation_id"])
                task = verify["task"]; artifact_id = kind + "-artifact-" + entry["id"]
                artifacts.append({"id": artifact_id, "slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "operation_id": operation_id})
                checks.extend({"slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "command": command, "result": "pass", "artifact_id": artifact_id, "operation_id": operation_id} for command in task["commands"][check_kind])
            receipt = {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": True, "operation_id": operation_id, "artifacts": artifacts, "checks": checks}
            record["usage"]["operations"].append({"id": operation_id, "slice": "stack", "phase": phase, **observation, "status": "result", "issued_at": "2026-09-20T08:00:00Z", "elapsed_seconds": 1, "receipt": receipt})
            record["usage"]["launches"].append({"operation_id": operation_id, "phase": phase, "issued_at": "2026-09-20T08:00:00Z"})
            record["usage"]["charges"].append({"operation_id": operation_id, "work_units": 1, "status": "observed", "charged_at": "2026-09-20T08:00:00Z"})
            operation_ids[check_kind] = operation_id
        operation_id = self.final_operation_id(record, "cross-slice-review", candidates); phase = "stack-final-review"
        observation = {"id": operation_id, **operation_identities(record["approval"]["run_id"], operation_id, phase)}
        runtime = {"model": "gpt-5.6-sol", "effort": "medium", "runner": "verify-runner", "permissions": "read-only"}
        inputs, checks = [], []
        for entry, candidate in zip(entries, candidates):
            verify = next(item for item in record["usage"]["operations"] if item["id"] == entry["review"]["verify_operation_id"])
            task, artifact = verify["task"], verify["receipt"]["evidence"]["artifact"]
            inputs.append({"slice_id": entry["id"], "candidate": candidate["candidate"], "verify_operation_id": verify["id"], "task_id": task["id"], "task_digest": digest(task), "artifact_id": artifact["id"]})
            checks.extend({"slice_id": entry["id"], "task_id": task["id"], "task_digest": digest(task), "candidate": candidate["candidate"], "criterion_id": criterion, "command": task["commands"]["verify"][0], "result": verdict, "artifact_id": "final-review-artifact", "operation_id": operation_id} for criterion in task["criteria"])
        environment = "sha256:" + "e" * 64
        binding = digest({"candidates": candidates, "runtime": runtime, "artifact_id": "final-review-artifact", "operation_id": operation_id, "verification_environment_digest": environment, "inputs": inputs, "checks": checks})
        receipt = {"observation": observation, "transport": "accepted", "terminal_turn": True, "task_success": True, "verdict": verdict, "fresh_context": True, "candidates": candidates, "runtime": runtime, "artifact": {"id": "final-review-artifact", "operation_id": operation_id, "candidates": candidates}, "operation_id": operation_id, "verification_environment_digest": environment, "binding_digest": binding, "findings": deepcopy(findings), "inputs": inputs, "checks": checks}
        record["usage"]["operations"].append({"id": operation_id, "slice": "stack", "phase": phase, **observation, "status": "result", "issued_at": "2026-09-20T08:00:00Z", "elapsed_seconds": 1, "receipt": receipt})
        record["usage"]["launches"].append({"operation_id": operation_id, "phase": phase, "issued_at": "2026-09-20T08:00:00Z"})
        record["usage"]["charges"].append({"operation_id": operation_id, "work_units": 1, "status": "observed", "charged_at": "2026-09-20T08:00:00Z"})
        operation_ids["review"] = operation_id
        return coordinator.store.persist(snapshot, record), {"qa_operation_id": operation_ids["qa"], "ci_operation_id": operation_ids["ci"], "review_operation_id": operation_ids["review"]}

    def test_unmerged_accepted_predecessor_opens_dependency_frontier_and_preserves_findings(self) -> None:
        self.assertEqual(self.coordinator.frontier(self.snapshot)["slice_id"], "S4")
        self.observe_accept("S4", A, B, [{"id": "nonblocking"}])
        frontier = self.coordinator.frontier(self.snapshot)
        self.assertEqual(frontier, {"action": "dispatch", "slice_id": "S5", "base": A})
        s4 = self.snapshot.value["stack"]["slices"][0]
        self.assertTrue(s4["accepted"]); self.assertFalse(s4["merged"])
        self.assertEqual(s4["shipment"], "unshipped"); self.assertEqual(s4["findings"], [{"id": "nonblocking"}])

    def test_frontier_refuses_hitl_and_never_skips_unapproved_scope(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        result = self.coordinator.frontier(self.snapshot)
        self.assertEqual(result["action"], "handback")
        self.assertEqual(result["slice_id"], "S6")

    def test_stack_intent_reloads_from_clean_clone_and_reconciles_without_duplicate_effect(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        self.adapter.timeout = True
        self.snapshot = self.coordinator.stack_action(self.snapshot, "open-pr", "S4", self.adapter)
        operation = self.snapshot.value["stack"]["operations"][0]
        self.assertEqual(operation["status"], "reconcile-required")
        self.assertEqual(len(self.adapter.applied), 1)
        # A second request cannot replay an uncertain provider effect.
        self.snapshot = self.coordinator.stack_action(self.snapshot, "open-pr", "S4", self.adapter)
        self.assertEqual(len(self.adapter.applied), 1)
        second_store = InterimCheckpointStore(self.second, "origin", self.approval["checkpoint"]["ref"])
        reloaded = second_store.reload(self.snapshot.value)
        self.adapter.timeout = False
        final = InterimStackCoordinator(second_store).reconcile(reloaded, self.adapter)
        self.assertEqual(final.value["stack"]["operations"][0]["status"], "result")
        self.assertEqual(final.value["stack"]["operations"][0]["receipt"]["operation_id"], operation["id"])

    def test_external_merge_clean_restack_and_changed_candidate_or_base_invalidate_review(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D), "S5": self.observation(C, A)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        s4 = self.snapshot.value["stack"]["slices"][0]
        self.assertTrue(s4["merged"]); self.assertTrue(s4["accepted"])
        self.assertEqual(self.coordinator.frontier(self.snapshot), {"action": "restack", "slice_id": "S5", "base": D})
        self.assertFalse(self.snapshot.value["stack"]["slices"][1]["accepted"])
        self.adapter.restacked_candidate = {"head": B, "base": D}
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["operations"][-1]["receipt"]["candidate"], {"head": B, "base": D})
        s5 = self.snapshot.value["stack"]["slices"][1]
        self.assertIsNone(s5["review"]); self.assertFalse(s5["accepted"])
        with self.assertRaisesRegex(StackPolicyError, "merged branch"):
            self.coordinator.stack_action(self.snapshot, "restack", "S4", self.adapter)

    def test_merged_predecessor_uses_current_base_and_stale_successor_reloads_as_routine_restack(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D), "S5": self.observation(C, A)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        second_store = InterimCheckpointStore(self.second, "origin", self.approval["checkpoint"]["ref"])
        self.snapshot = second_store.reload(self.snapshot.value); self.coordinator = InterimStackCoordinator(second_store)
        s5 = self.snapshot.value["stack"]["slices"][1]
        self.assertEqual(s5["candidate"], {"head": C, "base": A})
        self.assertIsNone(s5["review"]); self.assertFalse(s5["accepted"])
        self.assertEqual(self.coordinator.frontier(self.snapshot), {"action": "restack", "slice_id": "S5", "base": D})
        self.adapter.restacked_candidate = {"head": B, "base": D}
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["slices"][1]["candidate"], {"head": B, "base": D})

    def test_merged_predecessor_dispatches_only_a_new_successor_on_current_base_and_hands_back_without_it(self) -> None:
        self.observe_accept("S4", A, B)
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        self.assertEqual(self.coordinator.frontier(self.snapshot), {"action": "dispatch", "slice_id": "S5", "base": D})
        self.adapter.observations = {"S4": self.observation(A, B, "merged")}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        result = self.coordinator.frontier(self.snapshot)
        self.assertEqual(result["action"], "handback")
        self.assertIn("current observed post-merge base", result["reason"])

    def test_ambiguous_reconcile_has_durable_handback(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        self.adapter.timeout = True
        self.snapshot = self.coordinator.stack_action(self.snapshot, "open-pr", "S4", self.adapter)
        self.adapter.timeout = False; self.adapter.bad_reconcile = True
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["operations"][0]["status"], "reconcile-required")
        self.assertEqual(self.snapshot.value["state"]["next_action"], "handback")
        self.assertIn("ambiguous effect", self.snapshot.value["state"]["handback"]["reason"])

    def test_routine_restack_conflict_enters_bounded_repair_before_effect(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.routine_conflict = True
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        operation = self.snapshot.value["stack"]["operations"][0]
        self.assertEqual(operation["status"], "routine-repair")
        self.assertEqual(operation["conflict"]["attempt"], 1)
        self.assertEqual(self.snapshot.value["state"]["next_action"], "stack-repair")
        self.adapter.routine_conflict = False
        self.snapshot = self.coordinator.repair_restack(self.snapshot, "S5", self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["operations"][0]["status"], "result")

    def test_restack_receipt_must_prove_durable_observed_target_base(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D), "S5": self.observation(C, A)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        self.adapter.restacked_candidate = {"head": B, "base": A}  # old base, not observed merge target D
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        operation = self.snapshot.value["stack"]["operations"][-1]
        self.assertEqual(operation["target_base"], D)
        self.assertEqual(operation["status"], "reconcile-required")
        self.assertIn("ambiguous effect", self.snapshot.value["state"]["handback"]["reason"])

    def test_changed_base_stack_verify_derives_only_from_completed_restack_and_survives_reload(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        old_verify_id = self.snapshot.value["stack"]["slices"][1]["review"]["verify_operation_id"]
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D), "S5": self.observation(C, A)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        self.adapter.restacked_candidate = {"head": B, "base": D}
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        second_store = InterimCheckpointStore(self.second, "origin", self.approval["checkpoint"]["ref"])
        self.snapshot = second_store.reload(self.snapshot.value); self.coordinator = InterimStackCoordinator(second_store)
        candidate = self.snapshot.value["stack"]["slices"][1]["candidate"]
        verify = self.attach_verify("S5", candidate, [{"id": "fresh"}])
        self.assertNotEqual(verify["id"], old_verify_id)
        self.assertIn("restack_operation_id", verify)
        self.snapshot = self.coordinator.accept_review(self.snapshot, "S5", self.review(candidate, verify, self.snapshot.value["stack"]["slices"][1]["verification_environment_digest"], [{"id": "fresh"}]))
        self.assertTrue(self.snapshot.value["stack"]["slices"][1]["accepted"])

    def test_changed_base_stack_verify_rejects_forged_restack_receipt_target_task_or_candidate(self) -> None:
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.observations = {"S4": self.observation(A, B, "merged", restack_base=D), "S5": self.observation(C, A)}
        self.snapshot = self.coordinator.reconcile(self.snapshot, self.adapter)
        self.adapter.restacked_candidate = {"head": B, "base": D}
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        candidate = self.snapshot.value["stack"]["slices"][1]["candidate"]
        self.attach_verify("S5", candidate, [])

        def reject(mutator) -> None:
            record = deepcopy(self.snapshot.value)
            mutator(record)
            with self.assertRaises(InterimError):
                self.coordinator.store.persist(self.snapshot, record)

        reject(lambda record: record["usage"]["operations"][-1].update({"restack_operation_id": "stack-forged"}))
        def forge_correlated_restack_id(record):
            restack = next(item for item in record["stack"]["operations"] if item["kind"] == "restack" and item["slice_id"] == "S5")
            restack["id"] = "stack-caller-selected"
            restack["receipt"]["operation_id"] = "stack-caller-selected"
            record["usage"]["operations"][-1]["restack_operation_id"] = "stack-caller-selected"
        reject(forge_correlated_restack_id)
        def forge_historical_candidate(record):
            restack = next(item for item in record["stack"]["operations"] if item["kind"] == "restack" and item["slice_id"] == "S5")
            restack["candidate"] = {"head": D, "base": B}
        reject(forge_historical_candidate)
        reject(lambda record: next(item for item in record["stack"]["operations"] if item["kind"] == "restack").update({"target_base": A}))
        def forge_task(record):
            record["usage"]["operations"][-1]["task"]["attempt"] = 99
        reject(forge_task)
        def forge_candidate(record):
            operation = record["usage"]["operations"][-1]
            operation["candidate"]["base"] = A
            operation["receipt"]["candidate"]["base"] = A
            operation["receipt"]["evidence"]["artifact"]["base"] = A
        reject(forge_candidate)

    def test_routine_conflict_checkpoint_is_sanitized_before_and_after_repair_reload(self) -> None:
        sentinel = "Authorization: Bearer SECRET_TEST_VALUE"
        self.observe_accept("S4", A, B); self.observe_accept("S5", C, A)
        self.adapter.routine_conflict = True; self.adapter.routine_conflict_detail = sentinel
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["operations"][-1]["conflict"]["detail"], "routine in-scope restack conflict")
        self.assertNotIn(sentinel, json.dumps(self.snapshot.value, sort_keys=True))
        second_store = InterimCheckpointStore(self.second, "origin", self.approval["checkpoint"]["ref"])
        self.snapshot = second_store.reload(self.snapshot.value); self.coordinator = InterimStackCoordinator(second_store)
        self.assertNotIn(sentinel, json.dumps(self.snapshot.value, sort_keys=True))
        self.adapter.routine_conflict_detail = sentinel + " RETRY"
        self.snapshot = self.coordinator.repair_restack(self.snapshot, "S5", self.adapter)
        self.assertEqual(self.snapshot.value["stack"]["operations"][-1]["conflict"]["detail"], "routine in-scope restack conflict")
        self.assertNotIn(sentinel, json.dumps(self.snapshot.value, sort_keys=True))

    def test_review_requires_correlated_verify_route_and_current_environment(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        entry = self.snapshot.value["stack"]["slices"][0]
        operation = self.attach_verify("S4", entry["candidate"], [])
        record = deepcopy(self.snapshot.value); record["usage"]["operations"][-1]["receipt"]["runtime"]["model"] = "wrong-model"
        with self.assertRaisesRegex(InterimError, "runtime differs"):
            self.coordinator.store.persist(self.snapshot, record)
        # A correct accepted review becomes stale when only the observed
        # verification environment changes, without changing head/base.
        self.snapshot = self.coordinator.accept_review(self.snapshot, "S4", self.review(entry["candidate"], operation, entry["verification_environment_digest"]))
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B, environment="sha256:" + "f" * 64))
        self.assertFalse(self.snapshot.value["stack"]["slices"][0]["accepted"])

    def test_stack_verify_refuses_an_operation_without_an_approved_task_reference(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        entry = self.snapshot.value["stack"]["slices"][0]
        self.attach_verify("S4", entry["candidate"], [])
        record = deepcopy(self.snapshot.value)
        operation = record["usage"]["operations"][-1]
        operation["task"]["id"] = "forged-unapproved-task"
        with self.assertRaisesRegex(InterimError, "immutable approval"):
            self.coordinator.store.persist(self.snapshot, record)

    def test_stack_verify_refuses_an_operation_with_an_incorrect_task_digest(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        entry = self.snapshot.value["stack"]["slices"][0]
        self.attach_verify("S4", entry["candidate"], [])
        record = deepcopy(self.snapshot.value)
        operation = record["usage"]["operations"][-1]
        operation["task"]["limits"]["wall_time_seconds"] = 59
        with self.assertRaisesRegex(InterimError, "immutable approval"):
            self.coordinator.store.persist(self.snapshot, record)

    def test_every_stack_verify_entry_requires_deterministic_identity_and_full_task_shape(self) -> None:
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(A, B))
        entry = self.snapshot.value["stack"]["slices"][0]
        self.attach_verify("S4", entry["candidate"], [])
        record = deepcopy(self.snapshot.value)
        operation = record["usage"]["operations"][-1]
        operation["session_id"] = "forged-session"; operation["receipt"]["observation"]["session_id"] = "forged-session"
        with self.assertRaisesRegex(InterimError, "session/message/turn identity"):
            self.coordinator.store.persist(self.snapshot, record)
        # A task can have a matching approval digest yet still cannot shed the
        # full S2 build/Verify/QA/CI bounded-task shape.
        record = deepcopy(self.snapshot.value)
        operation = record["usage"]["operations"][-1]
        del operation["task"]["commands"]["qa"]
        reference = next(item for item in record["approval"]["tasks"] if item["id"] == operation["task"]["id"])
        reference["digest"] = digest(operation["task"])
        record["approval_digest"] = digest(record["approval"])
        with self.assertRaisesRegex(InterimError, "bounded task command identities"):
            self.coordinator.store.persist(self.snapshot, record)

    def test_real_s2_verify_ledger_is_accepted_and_forged_standalone_review_is_rejected(self) -> None:
        from test_interim_coordinator import CoordinatorTests, Fixture
        case = CoordinatorTests(); case.first = self.first
        approved = case.s2_approval(); approved["run_id"] = "run-s2-stack-link"
        control = "refs/heads/delivery-control/issue-run-s2-stack-link"
        approved["repository"]["control_ref"] = approved["checkpoint"]["ref"] = control
        store = InterimCheckpointStore(self.first, "origin", control)
        original = store.create_and_publish(initial_record(approved))
        completed = InterimFixtureCoordinator(store).run_one(original, "TASK-413", case.task(), Fixture(case.result()), Fixture(case.result("verify")))
        coordinator = InterimStackCoordinator(store)
        completed = coordinator.initialise(completed, {"TASK-413": "slice/task-413", "TASK-419": "slice/task-419"})
        completed = coordinator.observe_slice(completed, "TASK-413", self.observation(A, B))
        verify = next(item for item in completed.value["usage"]["operations"] if item["phase"] == "verify")
        entry = completed.value["stack"]["slices"][0]
        accepted = coordinator.accept_review(completed, "TASK-413", self.review(entry["candidate"], verify, entry["verification_environment_digest"], [{"id": "N1"}]))
        self.assertTrue(accepted.value["stack"]["slices"][0]["accepted"])
        forged = self.review(entry["candidate"], verify, entry["verification_environment_digest"])
        forged["verify_operation_id"] = "not-a-ledger-operation"
        with self.assertRaisesRegex(StackPolicyError, "durable accepted Verify"):
            coordinator.accept_review(completed, "TASK-413", forged)

    def test_final_current_evidence_requires_fresh_review_and_never_claims_shipment(self) -> None:
        self.observe_accept("S4", A, B, [{"id": "retained"}]); self.observe_accept("S5", C, A)
        candidates = [{"slice_id": "S4", "candidate": {"head": A, "base": B}}, {"slice_id": "S5", "candidate": {"head": C, "base": A}}, {"slice_id": "S6", "candidate": None}]
        # S6 remains HITL, so full-stack evidence correctly refuses before a false ready claim.
        stale_runtime = {"model": "gpt-5.6-sol", "effort": "medium", "runner": "verify-runner", "permissions": "read-only"}
        stale = {"qa": [], "ci": [], "review": {"verdict": "pass", "fresh_context": False, "candidates": candidates, "runtime": stale_runtime, "artifact_id": "final-artifact", "operation_id": "final-operation", "verification_environment_digest": "sha256:" + "e" * 64, "binding_digest": digest({"candidates": candidates, "runtime": stale_runtime, "artifact_id": "final-artifact", "operation_id": "final-operation", "verification_environment_digest": "sha256:" + "e" * 64}), "findings": []}}
        with self.assertRaisesRegex(StackPolicyError, "accepted current"):
            self.coordinator.finalise(self.snapshot, stale)
        # For a fixture that represents the approved all-AFK stack, make S6 AFK
        # before initial checkpoint publication instead of bypassing the frontier.
        self.assertEqual(validate_record(self.snapshot.value)["stack"]["slices"][0]["shipment"], "unshipped")

    def test_final_rejects_stale_ci_retains_findings_and_routes_blocker_to_s3(self) -> None:
        def accepted_fixture(name: str):
            approved = deepcopy(self.approval); approved["slices"][2]["mode"] = "AFK"
            approved["run_id"] = "run-task-417-final-" + name
            ref = "refs/heads/delivery-control/issue-run-task-417-final-" + name
            approved["repository"]["control_ref"] = approved["checkpoint"]["ref"] = ref
            store = InterimCheckpointStore(self.first, "origin", ref)
            snapshot = store.create_and_publish(initial_record(approved))
            coordinator = InterimStackCoordinator(store); snapshot = coordinator.initialise(snapshot, {"S4": "s4", "S5": "s5", "S6": "s6"})
            for slice_id, head, base in (("S4", A, B), ("S5", C, A), ("S6", D, C)):
                snapshot = coordinator.observe_slice(snapshot, slice_id, self.observation(head, base))
                candidate = next(item for item in snapshot.value["stack"]["slices"] if item["id"] == slice_id)["candidate"]
                self.snapshot, self.coordinator = snapshot, coordinator
                operation = self.attach_verify(slice_id, candidate, [{"id": slice_id + "-finding"}]); snapshot = self.snapshot
                environment = next(item for item in snapshot.value["stack"]["slices"] if item["id"] == slice_id)["verification_environment_digest"]
                snapshot = coordinator.accept_review(snapshot, slice_id, self.review(candidate, operation, environment, [{"id": slice_id + "-finding"}]))
            return store, coordinator, snapshot

        # A perfect receipt reference cannot advance if its operation and the
        # matching launch/charge are absent from an otherwise valid copied ledger.
        _, missing_coordinator, missing_base = accepted_fixture("missing")
        recorded, evidence = self.attach_final_receipts(missing_coordinator, missing_base, findings=[{"id": "final-nonblocking"}])
        copied = deepcopy(recorded.value); missing_id = evidence["ci_operation_id"]
        copied["usage"]["operations"] = [item for item in copied["usage"]["operations"] if item["id"] != missing_id]
        copied["usage"]["launches"] = [item for item in copied["usage"]["launches"] if item["operation_id"] != missing_id]
        copied["usage"]["charges"] = [item for item in copied["usage"]["charges"] if item["operation_id"] != missing_id]
        missing_snapshot = InterimCheckpointSnapshot(copied, recorded.digest, recorded.commit_sha)
        with self.assertRaisesRegex(StackPolicyError, "existing correlated ledger operation"):
            missing_coordinator.finalise(missing_snapshot, evidence)
        stale = deepcopy(recorded.value)
        stale_ci = next(item for item in stale["usage"]["operations"] if item["id"] == evidence["ci_operation_id"])
        stale_ci["receipt"]["checks"][0]["candidate"] = {"head": B, "base": B}
        with self.assertRaisesRegex(StackPolicyError, "complete approved current-head commands"):
            missing_coordinator.finalise(InterimCheckpointSnapshot(stale, recorded.digest, recorded.commit_sha), evidence)
        forged_review = deepcopy(recorded.value)
        review_operation = next(item for item in forged_review["usage"]["operations"] if item["id"] == evidence["review_operation_id"])
        review_operation["receipt"]["inputs"][0]["artifact_id"] = "forged-final-input"
        with self.assertRaisesRegex(StackPolicyError, "accepted Verify evidence"):
            missing_coordinator.finalise(InterimCheckpointSnapshot(forged_review, recorded.digest, recorded.commit_sha), evidence)

        # Blocker and pass use independent approved checkpoint refs, so their
        # deterministic operation IDs never race or duplicate in one ledger.
        _, blocker_coordinator, blocker_base = accepted_fixture("blocker")
        blocker_snapshot, blocker = self.attach_final_receipts(blocker_coordinator, blocker_base, verdict="blocker", findings=[{"id": "B-final"}])
        blocked = blocker_coordinator.finalise(blocker_snapshot, blocker)
        self.assertEqual(blocked.value["stack"]["final"]["outcome"], "s3-repair-policy")
        # A fresh final pass produces only review-ready; every slice remains unshipped.
        store, ready_coordinator, ready_base = accepted_fixture("pass")
        ready_snapshot, evidence = self.attach_final_receipts(ready_coordinator, ready_base, findings=[{"id": "final-nonblocking"}])
        ready = ready_coordinator.finalise(ready_snapshot, evidence)
        self.assertEqual(ready.value["stack"]["final"]["outcome"], "review-ready")
        self.assertEqual(ready.value["state"]["handback"]["shipment"], "unshipped")
        self.assertTrue(all(item["shipment"] == "unshipped" for item in ready.value["stack"]["slices"]))
        self.assertTrue(InterimRecoveryCoordinator(store)._terminal(ready.value))

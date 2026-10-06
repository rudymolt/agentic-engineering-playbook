"""Queued Conductor CLI payloads drive the real durable policy, without host effects."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
import unittest

import test_interim_repair as repair_tests
from test_interim_repair import RepairFixture
from control_ref_test_support import memoized_control_refs
from delivery_pilot.interim import initial_record
from delivery_pilot.interim_conductor_host import ConductorHostAdapter
from delivery_pilot.interim_repair_coordinator import InterimRepairCoordinator

WORKSPACE = "11111111-1111-4111-8111-111111111111"


class QueuedConductor:
    def __init__(self, approval, result, store=None):
        self.sent, self.polls, self.terminal = [], [], False
        self.result, self.store, self.approved = result, store, approval
        self.adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes=approval["routes"], command=self.command)

    def command(self, argv):
        if argv[:2] == ["session", "create"]:
            session = argv[argv.index("--session-id") + 1]
            operation = next(op for op in self.adapter.operations.values() if op["session_id"] == session)
            if self.store:
                durable = self.store.reload(initial_record(self.approved)).value
                assert any(op["id"] == operation["id"] and op["status"] == "intent" for op in durable["usage"]["operations"])
            assert operation["id"] not in self.sent, "a durable operation was resent"
            self.sent.append(operation["id"])
            return {"id": session, "deepLink": "conductor://session", "initialMessage": {"messageId": operation["message_id"], "state": "queued"}}
        operation = next(op for op in self.adapter.operations.values() if op["session_id"] == argv[2])
        self.polls.append(operation["id"])
        if argv[:2] == ["session", "status"]:
            return {"workspaceId": WORKSPACE, "sessionId": operation["session_id"], "status": "idle" if self.terminal and operation["phase"] != "coordinator" else "working", "updatedAt": "2026-09-20T00:00:00Z"}
        if argv[:2] == ["session", "cancel"]:
            return {"workspaceId": WORKSPACE, "sessionId": operation["session_id"], "status": "idle"}
        assert argv[:2] == ["session", "message"], argv
        records = [{"id": str(uuid4()), "sessionId": operation["session_id"], "type": "userMessage", "content": {"id": operation["message_id"], "state": "sent", "turnId": operation["message_id"]}}]
        if self.terminal:
            result = self.result(deepcopy(operation))
            for event in ({"type": "item.completed", "item": {"type": "agentMessage", "phase": "final_answer", "text": json.dumps(result)}}, {"type": "turn.completed"}):
                records.append({"id": str(uuid4()), "sessionId": operation["session_id"], "type": "agent", "content": {"turnId": operation["message_id"], "userMessageId": operation["message_id"], "rawPayload": {"event": event}}})
        return {"data": records, "hasMore": False}

    def reload(self, snapshot):
        self.adapter = ConductorHostAdapter(WORKSPACE, agent="codex", routes=snapshot.value["approval"]["routes"], command=self.command)
        self.adapter.load_checkpoint(snapshot.value)
        return self.adapter


import test_interim_coordinator as ordinary_tests
from delivery_pilot.interim_coordinator import InterimFixtureCoordinator, InterimDispatchError
from delivery_pilot.interim import validate_record, InterimError


class OrdinaryHostContinuationTests(unittest.TestCase):
    for _name in ("setUp", "tearDown", "git", "clone", "approval", "store", "task", "result"):
        locals()[_name] = getattr(ordinary_tests.CoordinatorTests, _name)

    def test_queued_ordinary_deadline_cancellation_is_durable_before_host_effect(self):
        approved = self.approval()
        approved["coordinator"]["session_id"] = str(uuid4())
        task = self.task()
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)}]
        approved["hard_limits"] = {"deadline_at": "2026-09-20T18:00:00Z"}
        original = initial_record(approved)
        store = self.store(self.first)
        snapshot = store.create_and_publish(original)
        now = [datetime(2026, 9, 20, 17, 0, tzinfo=timezone.utc)]
        coordinator = InterimFixtureCoordinator(store, clock=lambda: now[0])
        host = QueuedConductor(approved, lambda op: None)
        snapshot = coordinator.run_frontier(snapshot, {task["slice_id"]: task}, host.adapter, host.adapter)
        sent = deepcopy(snapshot.value["usage"]["operations"][-1])
        self.assertEqual(sent["status"], "reconcile-required")
        cancel_calls = []
        command = host.command
        def observed_cancel(argv):
            if argv[:2] == ["session", "cancel"]:
                durable = self.store(self.second).reload(original).value
                operation = next(op for op in durable["usage"]["operations"] if op["id"] == sent["id"])
                self.assertEqual(operation["status"], "cancellation-uncertain")
                self.assertEqual(operation["cancellation_intent"]["reason"], "selected deadline reached")
                self.assertEqual(operation["cancellation"]["state"], "uncertain")
                self.assertEqual(operation["receipt"]["observation"], sent["receipt"]["observation"])
                cancel_calls.append(operation["id"])
            return command(argv)
        host.adapter.command = observed_cancel
        now[0] = datetime(2026, 9, 20, 18, 1, tzinfo=timezone.utc)
        snapshot = coordinator.run_frontier(snapshot, {task["slice_id"]: task}, host.adapter, host.adapter)
        self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "unfinished-cancelled")
        self.assertEqual(cancel_calls, [sent["id"]])
        self.assertEqual(host.sent, [sent["id"]])

    def test_two_dependent_slices_queue_reload_and_restack_in_one_checkpoint(self):
        self.two_slice_run()

    def test_repaired_first_slice_admits_second_queued_build_without_rewriting_failure(self):
        self.two_slice_run(repair_first=True)

    def test_two_dependent_repaired_slices_survive_checkpoint_restart(self):
        self.two_slice_run(repair_first=True, repair_second=True)

    def two_slice_run(self, repair_first=False, repair_second=False):
        approved = self.approval()
        approved["forecast"] = {"work_units": 3, "verification_units": 1, "likely_repair_units": 1, "final_handback_units": 1}
        first_head, second_head, restacked_head = ("c", "d", "e") if repair_first else ("a", "c", "d")
        approved["coordinator"]["session_id"] = str(uuid4())
        approved["slices"][1]["mode"] = "AFK"
        first_task = self.task()
        second_task = deepcopy(first_task)
        second_task.update(id="build-task-419", slice_id="TASK-419", candidate_ref="candidate-task-419")
        tasks = {task["slice_id"]: task for task in (first_task, second_task)}
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)} for task in tasks.values()]
        original = initial_record(approved)
        store = self.store(self.first)
        snapshot = store.create_and_publish(original)
        coordinator = InterimFixtureCoordinator(store)
        def result(op):
            if op["phase"] in {"diagnosis", "repair", "repair-verify"}:
                receipt = RepairFixture().send(op)
                if repair_second and op["slice"] == "TASK-419":
                    if op["phase"] == "diagnosis":
                        receipt["diagnosis"]["revisions"] = deepcopy(op["repair_context"]["revisions"])
                    elif op["phase"] == "repair":
                        candidate = {"head": "e" * 40, "base": "b" * 40}
                        receipt["candidate"] = candidate
                        receipt["evidence"]["artifact"].update(head=candidate["head"], base=candidate["base"])
                return receipt
            phase = "verify" if op["phase"] == "stack-verify" else op["phase"]
            candidate = op.get("candidate", {"head": ("a" if op["slice"] == "TASK-413" else second_head) * 40, "base": op["task"]["base"]})
            receipt = ordinary_tests.Fixture(self.result(phase, candidate)).send({**op, "phase": phase})
            if op["phase"] == "verify" and ((repair_first and op["slice"] == "TASK-413") or (repair_second and op["slice"] == "TASK-419")):
                receipt.update(task_success=True, verdict="fail", criteria={"AC01": "fail"})
                receipt.pop("handoff")
            return receipt
        host = QueuedConductor(approved, result, store)
        with self.assertRaisesRegex(InterimDispatchError, "dependency"):
            coordinator.run_one(snapshot, "TASK-419", second_task, host.adapter, host.adapter)
        self.assertEqual(host.sent, [])
        for slice_id, task in tasks.items():
            host.terminal = False
            snapshot = coordinator.run_frontier(snapshot, tasks, host.reload(snapshot), host.adapter)
            self.assertEqual(snapshot.value["usage"]["operations"][-1]["phase"], "build")
            self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "reconcile-required")
            # Reload from the remote into a clean independent checkout at each
            # phase boundary; adapters must reconstruct IDs from the ledger.
            store = self.store(self.second if slice_id == "TASK-413" else self.first)
            snapshot = store.reload(original)
            coordinator = InterimFixtureCoordinator(store)
            host.terminal = True
            snapshot = coordinator.run_frontier(snapshot, tasks, host.reload(snapshot), host.adapter)
            snapshot = coordinator.run_frontier(snapshot, tasks, host.reload(snapshot), host.adapter)
            self.assertEqual(snapshot.value["usage"]["operations"][-1]["phase"], "verify")
            self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "reconcile-required")
            snapshot = coordinator.run_frontier(snapshot, tasks, host.reload(snapshot), host.adapter)
            snapshot = coordinator.run_frontier(snapshot, tasks, host.reload(snapshot), host.adapter)
            if (repair_first and slice_id == "TASK-413") or (repair_second and slice_id == "TASK-419"):
                self.assertEqual(snapshot.value["state"]["next_action"], "handback")
                failed_verify = deepcopy(snapshot.value["usage"]["operations"][-1])
                repair = InterimRepairCoordinator(store)
                finding, evidence = repair_tests.RepairPolicyTests.finding(self)
                for item in evidence:
                    item["artifact_id"] = failed_verify["receipt"]["evidence"]["artifact"]["id"]
                opening = failed_verify["receipt"]["candidate"]
                snapshot = repair.open(snapshot, slice_id, task, finding, opening, evidence)
                if slice_id == "TASK-413":
                    with self.assertRaisesRegex(InterimDispatchError, "dependency"):
                        coordinator.run_one(snapshot, "TASK-419", second_task, host.adapter, host.adapter)
                for _ in range(2):
                    snapshot = repair.diagnose(snapshot, slice_id, task, host.reload(snapshot))
                for attempt in range(3):
                    self.assertIn(snapshot.value["repair"]["status"], {"repair-ready", "waiting-repair", "waiting-repair-verify", "repair-verify-ready"}, (slice_id, attempt, snapshot.value["repair"]["status"]))
                    snapshot = repair.repair_once(snapshot, slice_id, task, host.reload(snapshot), host.adapter)
                self.assertEqual(snapshot.value["repair"]["status"], "completed")
                if repair_second and slice_id == "TASK-419":
                    from delivery_pilot.interim_semantics import accepted_slice_candidate
                    reloaded = self.store(self.first).reload(original).value
                    self.assertEqual(accepted_slice_candidate(reloaded, "TASK-413"), {"head": "c" * 40, "base": "b" * 40})
                    self.assertEqual(accepted_slice_candidate(reloaded, "TASK-419"), {"head": "e" * 40, "base": "b" * 40})
                self.assertEqual(next(op for op in snapshot.value["usage"]["operations"] if op["id"] == failed_verify["id"]), failed_verify)
                # A completed repair never invents its failed ordinary antecedent.
                from delivery_pilot.interim_semantics import accepted_slice_candidate, SemanticError
                for mutation in (() if repair_second else ("success", "missing", "candidate", "task", "evidence", "incomplete")):
                    with self.subTest(invalid_repair_antecedent=mutation):
                        corrupt = deepcopy(snapshot.value)
                        ordinary_verify = next(op for op in corrupt["usage"]["operations"] if op["id"] == failed_verify["id"])
                        if mutation == "success":
                            ordinary_verify["receipt"].update(verdict="pass", criteria={"AC01": "pass"})
                        elif mutation == "missing":
                            corrupt["usage"]["operations"].remove(ordinary_verify)
                        elif mutation == "candidate":
                            ordinary_verify["receipt"]["candidate"]["head"] = "f" * 40
                        elif mutation == "task":
                            ordinary_verify["task"] = deepcopy(second_task)
                        elif mutation == "evidence":
                            corrupt["repair"]["opening"]["execution_evidence"][0]["artifact_id"] = "unrelated"
                        else:
                            ordinary_verify["receipt"]["task_success"] = False
                        with self.assertRaises(SemanticError):
                            accepted_slice_candidate(corrupt, slice_id)
                        before_sends = list(host.sent)
                        with self.assertRaises(InterimDispatchError):
                            coordinator.run_one(SimpleNamespace(value=corrupt), "TASK-419", second_task, host.adapter, host.adapter)
                        self.assertEqual(host.sent, before_sends)
            else:
                self.assertEqual(snapshot.value["state"]["next_action"], "pr-ready")
                self.assertEqual(snapshot.value["state"]["slice_id"], slice_id)
        if repair_second:
            self.assertEqual(len(snapshot.value["usage"]["charges"]), len(snapshot.value["usage"]["operations"]))
            return
        self.assertEqual(len(host.sent), 7 if repair_first else 4)
        ordinary = [op for op in snapshot.value["usage"]["operations"] if op["phase"] in {"coordinator", "build", "verify"}]
        self.assertEqual([op["phase"] for op in ordinary], ["coordinator", "build", "verify", "build", "verify"])
        self.assertEqual([op["task"]["base"] for op in ordinary], ["b" * 40] * 5)
        corrupt = deepcopy(snapshot.value)
        del corrupt["state"]["slice_id"]
        with self.assertRaisesRegex(InterimError, "unambiguous"):
            validate_record(corrupt)
        corrupt = deepcopy(snapshot.value)
        corrupt["state"]["slice_id"] = "TASK-413"
        with self.assertRaisesRegex(InterimError, "differs|not success|accepting|failed"):
            validate_record(corrupt)
        if not repair_first:
            corrupt = deepcopy(snapshot.value)
            operations = corrupt["usage"]["operations"]
            operations[:] = [operations[0], operations[1], operations[3], operations[4], operations[2]]
            with self.assertRaisesRegex(InterimError, "dependency"):
                validate_record(corrupt)
        stack = InterimStackCoordinator(store)
        snapshot = stack.initialise(snapshot, {slice_id: "slice/" + slice_id for slice_id in tasks})
        def observation(head, base):
            return {"candidate": {"head": head, "base": base}, "pr": {"url": "https://example.invalid/" + head, "head": head, "base": base, "state": "open"}, "verification_environment_digest": "sha256:" + "e" * 64}
        snapshot = stack.observe_slice(snapshot, "TASK-413", observation(first_head * 40, "b" * 40))
        for _ in range(2):
            snapshot = stack.verify_slice(snapshot, "TASK-413", first_task, host.reload(snapshot))
        snapshot = stack.observe_slice(snapshot, "TASK-419", observation(second_head * 40, "b" * 40))
        self.assertEqual(stack.frontier(snapshot), {"action": "restack", "slice_id": "TASK-419", "base": first_head * 40})
        with self.assertRaisesRegex(ValueError, "restack"):
            stack.verify_slice(snapshot, "TASK-419", second_task, host.adapter)
        restack = stack_tests.StackFixture()
        restack.restacked_candidate = {"head": restacked_head * 40, "base": first_head * 40}
        snapshot = stack.stack_action(snapshot, "restack", "TASK-419", restack)
        for _ in range(2):
            snapshot = stack.verify_slice(snapshot, "TASK-419", second_task, host.reload(snapshot))
        self.assertTrue(all(entry["accepted"] for entry in snapshot.value["stack"]["slices"]))
        self.assertEqual(stack.frontier(snapshot), {"action": "final-review"})
        self.assertEqual(len(host.sent), 9 if repair_first else 6)
        self.assertEqual(len(host.sent), len(set(host.sent)))
        self.assertEqual(snapshot.value["approval_digest"], original["approval_digest"])


class RepairHostContinuationTests(unittest.TestCase):
    # Reuse the durable Git fixture, without inheriting its test cases.
    for _name in ("setUp", "tearDown", "git", "clone", "approval", "store", "task", "s2_approval", "result", "failed_s2", "finding"):
        locals()[_name] = getattr(repair_tests.RepairPolicyTests, _name)

    def opened(self, clock=None):
        store = self.store(self.first)
        if clock is None:
            failed = self.failed_s2()
            coordinator = InterimRepairCoordinator(store)
        else:
            initial = store.create_and_publish(initial_record(self.s2_approval()))
            failure = self.result(); failure["task_success"] = False
            failed = InterimFixtureCoordinator(store, clock=clock).run_one(
                initial, "TASK-413", self.task(), ordinary_tests.Fixture(failure), ordinary_tests.Fixture(self.result("verify")))
            coordinator = InterimRepairCoordinator(store, clock=clock)
        finding, evidence = self.finding()
        snapshot = coordinator.open(failed, "TASK-413", self.task(), finding, {"head": "a" * 40, "base": "b" * 40}, evidence)
        return coordinator, snapshot

    def test_queued_diagnosis_repair_and_verify_resume_same_ids_after_reload(self):
        coordinator, snapshot = self.opened()
        host = QueuedConductor(snapshot.value["approval"], RepairFixture().send, self.store(self.second))
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "waiting-diagnosis")
        self.assertEqual(snapshot.value["repair"]["diagnoses"], [])
        host.terminal = True
        snapshot = self.store(self.second).reload(initial_record(self.s2_approval()))
        coordinator = InterimRepairCoordinator(self.store(self.second))
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.reload(snapshot))
        self.assertEqual(snapshot.value["repair"]["status"], "repair-ready")
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.adapter, host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "waiting-repair")
        self.assertEqual(snapshot.value["repair"]["batch"]["no_progress"], 0)
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.reload(snapshot), host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "waiting-repair-verify")
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.reload(snapshot), host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "completed")
        self.assertEqual(len(host.sent), 3)
        self.assertEqual(len(snapshot.value["repair"]["cycles"]), 1)
        self.assertTrue(all(charge["status"] == "observed" for charge in snapshot.value["usage"]["charges"]))

    def test_queued_polling_does_not_spend_stagnation_or_send_again(self):
        coordinator, snapshot = self.opened()
        host = QueuedConductor(snapshot.value["approval"], RepairFixture().send)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        for _ in range(4):
            snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.reload(snapshot))
        self.assertEqual(len(host.sent), 1)
        self.assertEqual(snapshot.value["repair"]["batch"]["no_progress"], 0)
        self.assertEqual(snapshot.value["repair"]["status"], "waiting-diagnosis")

    def s2_approval(self, task=None):
        approved = repair_tests.RepairPolicyTests.s2_approval(self, task)
        approved["hard_limits"] = getattr(self, "selected_limits", "none")
        return approved

    @memoized_control_refs
    def test_async_three_failure_diagnosis_and_stagnation_with_and_without_caps(self):
        for limits in ("none", {"dispatch_max": 30}):
            for progress in (False, True):
                with self.subTest(limits=limits, progress=progress):
                    self.tearDown(); self.setUp()
                    self.selected_limits = limits
                    coordinator, snapshot = self.opened()
                    host = QueuedConductor(snapshot.value["approval"], RepairFixture("fail", progress=progress, distinct=True).send)
                    host.terminal = True
                    for attempt in range(3):
                        if snapshot.value["repair"]["status"] == "diagnosis-required":
                            snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
                            snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.reload(snapshot))
                        for _ in range(3):
                            snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.reload(snapshot), host.adapter)
                        self.assertEqual(len(snapshot.value["repair"]["cycles"]), attempt + 1)
                    self.assertEqual(snapshot.value["repair"]["status"], "diagnosis-required" if progress else "stuck")
                    self.assertEqual(snapshot.value["repair"]["batch"]["no_progress"], 0 if progress else 3)
                    if progress:
                        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
                        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.reload(snapshot))
                        self.assertEqual(len(snapshot.value["repair"]["diagnoses"]), 4)
                    self.assertEqual(len(host.sent), len(set(host.sent)))
                    if limits == "none":
                        self.assertTrue(snapshot.value["forecasts"]["revised"])

    def test_selected_cap_settles_last_repair_but_never_dispatches_verify(self):
        self.selected_limits = {"dispatch_max": 4}
        coordinator, snapshot = self.opened()
        host = QueuedConductor(snapshot.value["approval"], RepairFixture().send)
        host.terminal = True
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.adapter, host.adapter)
        snapshot = coordinator.repair_once(snapshot, "TASK-413", self.task(), host.adapter, host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "handback")
        self.assertEqual(len(host.sent), 2)
        self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "result")
        self.assertNotIn("repair-verify", [op["phase"] for op in snapshot.value["usage"]["operations"]])

    def test_ambiguous_send_reconciles_original_intent_without_repeat(self):
        coordinator, snapshot = self.opened()
        host = QueuedConductor(snapshot.value["approval"], RepairFixture().send)
        class LostReceipt:
            def send(self, operation):
                host.adapter.send(operation)
                raise TimeoutError("receipt lost after send")
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), LostReceipt())
        self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "intent")
        host.terminal = True
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.reload(snapshot))
        self.assertEqual(snapshot.value["repair"]["status"], "repair-ready")
        self.assertEqual(len(host.sent), 1)


    def test_selected_deadline_records_cancellation_before_effect(self):
        self.selected_limits = {"deadline_at": "2026-09-20T21:00:00Z"}
        coordinator, snapshot = self.opened(clock=lambda: datetime(2026, 9, 20, 20, tzinfo=timezone.utc))
        host = QueuedConductor(snapshot.value["approval"], RepairFixture().send)
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        coordinator.clock = lambda: datetime(2026, 9, 20, 21, tzinfo=timezone.utc)
        original_command = host.command
        cancellations = []
        def command(argv):
            if argv[:2] == ["session", "cancel"]:
                durable = self.store(self.second).reload(initial_record(self.s2_approval())).value
                operation = durable["usage"]["operations"][-1]
                self.assertIn("cancellation_intent", operation)
                self.assertEqual(operation["status"], "cancellation-uncertain")
                cancellations.append(operation["id"])
            return original_command(argv)
        host.adapter.command = command
        snapshot = coordinator.diagnose(snapshot, "TASK-413", self.task(), host.adapter)
        self.assertEqual(snapshot.value["repair"]["status"], "handback")
        self.assertEqual(snapshot.value["usage"]["operations"][-1]["status"], "unfinished-cancelled")
        self.assertEqual(len(cancellations), 1)
        self.assertEqual(snapshot.value["repair"]["cycles"], [])


import test_interim_stack as stack_tests
from delivery_pilot.interim_stack import InterimStackCoordinator
from delivery_pilot.interim import InterimCheckpointStore
from delivery_pilot.canonical import digest
from types import SimpleNamespace


class StackHostContinuationTests(unittest.TestCase):
    for _name in ("setUp", "tearDown", "git", "clone", "observation", "review", "attach_verify", "observe_accept", "final_operation_id", "attach_final_receipts"):
        locals()[_name] = stack_tests.InterimStackTests.__dict__[_name]

    def worker_result(self, operation):
        observation = {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        return RepairFixture().worker(operation, observation, operation["candidate"], "verify", "pass", [])

    def test_stack_verify_dispatches_approved_route_and_accepts_only_terminal_result(self):
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B))
        host = QueuedConductor(self.approval, self.worker_result, self.store)
        self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.adapter)
        self.assertFalse(self.snapshot.value["stack"]["slices"][0]["accepted"])
        operation = self.snapshot.value["usage"]["operations"][-1]
        self.assertEqual(operation["phase"], "stack-verify")
        self.assertEqual(operation["status"], "reconcile-required")
        host.terminal = True
        store = InterimCheckpointStore(self.second, "origin", self.approval["checkpoint"]["ref"])
        self.snapshot = store.reload(initial_record(self.approval))
        coordinator = InterimStackCoordinator(store)
        self.snapshot = coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.reload(self.snapshot))
        self.assertTrue(self.snapshot.value["stack"]["slices"][0]["accepted"])
        self.assertEqual(len(host.sent), 1)
        self.assertEqual(self.snapshot.value["stack"]["slices"][0]["findings"], [{"id": "retained"}])

    def test_final_qa_ci_and_review_are_sent_once_and_reloaded_between_phases(self):
        self.observe_accept("S4", stack_tests.A, stack_tests.B)
        self.observe_accept("S5", stack_tests.C, stack_tests.A)
        self.observe_accept("S6", stack_tests.D, stack_tests.C)
        capture = SimpleNamespace(store=SimpleNamespace(persist=lambda snapshot, record: SimpleNamespace(value=record)))
        generated, evidence = self.attach_final_receipts(capture, self.snapshot)
        results = {op["phase"]: op["receipt"] for op in generated.value["usage"]["operations"] if op["phase"].startswith("stack-final-")}
        def final_result(op):
            old_id = results[op["phase"]]["operation_id"]
            result = json.loads(json.dumps(results[op["phase"]]).replace(old_id, op["id"]))
            result["observation"] = {key: op[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
            if op["phase"] == "stack-final-review":
                result["binding_digest"] = digest({"candidates": result["candidates"], "runtime": result["runtime"], "artifact_id": result["artifact"]["id"], "operation_id": op["id"], "verification_environment_digest": result["verification_environment_digest"], "inputs": result["inputs"], "checks": result["checks"]})
            result.update(runtime={"model": "gpt-5.6-sol", "effort": "medium", "runner": "verify-runner", "permissions": "read-only"}, wall_time_seconds=1, tools=["unit"])
            return result
        host = QueuedConductor(self.approval, final_result)
        host.terminal = True
        for _ in range(4):
            self.snapshot = self.coordinator.final_review(self.snapshot, host.reload(self.snapshot))
        self.assertEqual(self.snapshot.value["state"]["next_action"], "review-ready")
        self.assertEqual(len(host.sent), 3)
        self.assertEqual(set(self.snapshot.value["stack"]["final"]["evidence"].values()), set(host.sent))
        self.snapshot = self.coordinator.final_review(self.snapshot, host.adapter)
        self.assertEqual(len(host.sent), 3)


    def test_external_merge_restack_dispatches_new_verify_for_exact_candidate(self):
        host = QueuedConductor(self.approval, self.worker_result)
        host.terminal = True
        for slice_id, head, base in (("S4", stack_tests.A, stack_tests.B), ("S5", stack_tests.C, stack_tests.A)):
            self.snapshot = self.coordinator.observe_slice(self.snapshot, slice_id, self.observation(head, base))
            for _ in range(2):
                self.snapshot = self.coordinator.verify_slice(self.snapshot, slice_id, self.task_specs[slice_id], host.adapter)
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B, "merged", restack_base=stack_tests.D))
        self.assertFalse(self.snapshot.value["stack"]["slices"][1]["accepted"])
        with self.assertRaisesRegex(ValueError, "restack"):
            self.coordinator.verify_slice(self.snapshot, "S5", self.task_specs["S5"], host.adapter)
        self.adapter.restacked_candidate = {"head": "e" * 40, "base": stack_tests.D}
        self.snapshot = self.coordinator.stack_action(self.snapshot, "restack", "S5", self.adapter)
        self.assertFalse(self.snapshot.value["stack"]["slices"][1]["accepted"])
        for _ in range(2):
            self.snapshot = self.coordinator.verify_slice(self.snapshot, "S5", self.task_specs["S5"], host.reload(self.snapshot))
        entry = self.snapshot.value["stack"]["slices"][1]
        self.assertTrue(entry["accepted"])
        self.assertEqual(entry["review"]["candidate"], {"head": "e" * 40, "base": stack_tests.D})
        self.assertEqual(len(host.sent), 3)
        operation = self.snapshot.value["usage"]["operations"][-1]
        self.assertEqual(operation["restack_operation_id"], self.snapshot.value["stack"]["operations"][-1]["id"])

    def test_pending_stale_verify_is_settled_before_current_revision_dispatch(self):
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B))
        host = QueuedConductor(self.approval, self.worker_result)
        self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.adapter)
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.C, stack_tests.B))
        host.terminal = True
        self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.reload(self.snapshot))
        self.assertFalse(self.snapshot.value["stack"]["slices"][0]["accepted"])
        self.assertEqual(len(host.sent), 1)
        for _ in range(2):
            self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.reload(self.snapshot))
        self.assertEqual(self.snapshot.value["stack"]["slices"][0]["review"]["candidate"]["head"], stack_tests.C)
        self.assertEqual(len(host.sent), 2)

    def test_same_candidate_environment_change_needs_a_fresh_operation(self):
        host = QueuedConductor(self.approval, self.worker_result)
        host.terminal = True
        for environment in ("sha256:" + "a" * 64, "sha256:" + "b" * 64):
            self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B, environment=environment))
            for _ in range(2):
                self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.reload(self.snapshot))
        self.assertEqual(len(host.sent), 2)
        self.assertTrue(self.snapshot.value["stack"]["slices"][0]["accepted"])

    def test_wrong_candidate_result_is_retained_as_unusable_without_resend(self):
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B))
        def wrong_candidate(operation):
            result = self.worker_result(operation)
            result["candidate"]["head"] = stack_tests.D
            return result
        host = QueuedConductor(self.approval, wrong_candidate)
        host.terminal = True
        for _ in range(3):
            self.snapshot = self.coordinator.verify_slice(self.snapshot, "S4", self.task_specs["S4"], host.adapter)
        operation = self.snapshot.value["usage"]["operations"][-1]
        self.assertEqual(operation["status"], "result-unusable")
        self.assertEqual(operation["receipt"]["candidate"]["head"], stack_tests.D)
        self.assertFalse(self.snapshot.value["stack"]["slices"][0]["accepted"])
        self.assertEqual(len(host.sent), 1)

    def test_hitl_slice_never_dispatches_an_unapproved_verify(self):
        host = QueuedConductor(self.approval, self.worker_result)
        with self.assertRaisesRegex(ValueError, "AFK"):
            self.coordinator.verify_slice(self.snapshot, "S6", self.task_specs["S6"], host.adapter)
        self.assertEqual(host.sent, [])


    def test_out_of_order_multi_hop_dependency_reviews_are_all_invalidated(self):
        self.approval["slices"].reverse()
        self.approval["run_id"] += "-reversed"
        control = self.approval["checkpoint"]["ref"] + "-reversed"
        self.approval["checkpoint"]["ref"] = self.approval["repository"]["control_ref"] = control
        self.store = InterimCheckpointStore(self.first, "origin", control)
        self.snapshot = self.store.create_and_publish(initial_record(self.approval))
        self.coordinator = InterimStackCoordinator(self.store)
        self.snapshot = self.coordinator.initialise(self.snapshot, {"S4": "slice/s4", "S5": "slice/s5", "S6": "slice/s6"})
        self.observe_accept("S4", stack_tests.A, stack_tests.B)
        self.observe_accept("S5", stack_tests.C, stack_tests.A)
        self.observe_accept("S6", stack_tests.D, stack_tests.C)
        self.snapshot = self.coordinator.observe_slice(self.snapshot, "S4", self.observation(stack_tests.A, stack_tests.B, "merged", restack_base="e" * 40))
        entries = {item["id"]: item for item in self.snapshot.value["stack"]["slices"]}
        self.assertTrue(entries["S4"]["accepted"])
        for name in ("S5", "S6"):
            self.assertFalse(entries[name]["accepted"])
            self.assertIsNone(entries[name]["review"])
        self.assertIsNone(self.snapshot.value["stack"]["final"])

from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim import InterimCheckpointError, InterimCheckpointSnapshot, InterimCheckpointStore, InterimError, initial_record, validate_record  # noqa: E402
from delivery_pilot.interim_coordinator import InterimDispatchError, InterimFixtureCoordinator, _success, _handoff  # noqa: E402
from delivery_pilot.canonical import digest  # noqa: E402
from delivery_pilot.interim_identity import operation_identities  # noqa: E402
from test_interim import InterimCheckpointFixture  # noqa: E402
from control_ref_test_support import memoized_control_refs  # noqa: E402


MISSING = object()


def receipt_change(path, value=MISSING):
    def mutate(receipt):
        parent = receipt
        for key in path[:-1]:
            parent = parent[key]
        if value is MISSING:
            del parent[path[-1]]
        else:
            parent[path[-1]] = deepcopy(value)
    return mutate


def worker_mutations(phase):
    """Acceptance predicates, independently expressed as malformed observations."""
    cases = []
    required = [(name,) for name in (
        "transport", "terminal_turn", "task_success", "observation", "candidate", "criteria",
        "executed_checks", "runtime", "artifacts", "tools", "wall_time_seconds", "host_counters", "evidence")]
    fields = {
        ("observation",): ("id", "session_id", "message_id", "terminal_turn_id"),
        ("candidate",): ("head", "base"),
        ("runtime",): ("model", "effort", "runner", "permissions"),
        ("host_counters",): ("tokens", "cost"),
        ("evidence",): ("artifact", "commands", "checks"),
        ("evidence", "artifact"): ("id", "task_id", "operation_id", "head", "base"),
        ("evidence", "commands", 0): ("command", "result", "artifact_id", "operation_id"),
        ("evidence", "checks", 0): ("criterion_id", "command", "result", "artifact_id", "operation_id"),
    }
    for parent, names in fields.items():
        for name in names:
            path = parent + (name,)
            required.append(path)
            cases.append(("wrong-" + "-".join(map(str, path)), receipt_change(path, "unrelated")))
    if phase == "verify":
        required += [(name,) for name in ("fresh_context", "builder_transcript", "verdict")]
    for path in required:
        cases.append(("missing-" + "-".join(map(str, path)), receipt_change(path)))
    values = {
        "transport": ["rejected", [], None], "terminal_turn": [False, 1], "task_success": [False, 1],
        "candidate": [None, {}, {"head": "a" * 40, "base": "b" * 40, "extra": True}],
        "criteria": [None, {}, {"AC01": "fail"}, {"AC01": "pass", "extra": "pass"}],
        "executed_checks": [[], ["AC01", "AC01"], ["AC01", "extra"], [{}], "AC01"],
        "runtime": [None, {}, {"model": "unknown"}],
        "artifacts": [[], ["artifact", "artifact"], ["artifact", {}], ["artifact", "two", "three"]],
        "tools": [[], ["unit", "unit"], ["unit", "extra"], ["unit", {}], ["unit", "two", "three"]],
        "wall_time_seconds": [-1, 61, True, 1.5, None],
        "host_counters": [None, {"tokens": 0, "cost": None}, {"tokens": None, "cost": 0}],
        "evidence": [None, {}, {"extra": True}],
    }
    if phase == "verify":
        values.update(fresh_context=[False, 1, None], builder_transcript=[True, 0, None], verdict=["blocked", "uncertain", None])
    for field, variants in values.items():
        for index, value in enumerate(variants):
            cases.append((f"invalid-{field}-{index}", receipt_change((field,), value)))
    for name in ("commands", "checks"):
        for label, value in (("empty", []), ("malformed", [None]), ("not-list", {})):
            cases.append((f"{name}-{label}", receipt_change(("evidence", name), value)))
        def extra(receipt, name=name):
            receipt["evidence"][name][0]["extra"] = "unapproved"
        def duplicate(receipt, name=name):
            receipt["evidence"][name].append(deepcopy(receipt["evidence"][name][0]))
        def failed_extra(receipt, name=name):
            receipt["evidence"][name].append(dict(receipt["evidence"][name][0], result="fail"))
        cases += [(f"{name}-extra-field", extra), (f"{name}-duplicate", duplicate), (f"{name}-failed-extra", failed_extra)]
    cases.append(("unhashable-check-command", receipt_change(("evidence", "checks", 0, "command"), {})))
    return cases


def handoff_mutations():
    cases = [("missing-handoff", receipt_change(("handoff",))),
             ("malformed-handoff", receipt_change(("handoff",), None))]
    fields = {
        ("handoff",): ("qa", "ci", "final_review", "pr"),
        ("handoff", "qa", 0): ("status", "head", "command", "result", "artifact_id", "operation_id"),
        ("handoff", "ci", 0): ("status", "head", "command", "result", "artifact_id", "operation_id"),
        ("handoff", "final_review"): ("verdict", "candidate", "fresh_context", "runtime", "artifact_id", "operation_id", "criteria"),
        ("handoff", "pr"): ("url", "head", "base", "state", "operation_id", "artifact_id", "merge"),
    }
    for parent, names in fields.items():
        for name in names:
            path = parent + (name,)
            label = "-".join(map(str, path))
            cases.append(("missing-" + label, receipt_change(path)))
            cases.append(("wrong-" + label, receipt_change(path, "" if name == "url" else "unrelated")))
    for name in ("qa", "ci"):
        cases.append((name + "-empty", receipt_change(("handoff", name), [])))
        def duplicate(receipt, name=name):
            receipt["handoff"][name].append(deepcopy(receipt["handoff"][name][0]))
        def failed_extra(receipt, name=name):
            receipt["handoff"][name].append(dict(receipt["handoff"][name][0], result="fail"))
        cases += [(name + "-duplicate", duplicate), (name + "-failed-extra", failed_extra)]
    cases += [("pr-nonstring-url", receipt_change(("handoff", "pr", "url"), 1)),
              ("review-nonboolean-fresh", receipt_change(("handoff", "final_review", "fresh_context"), 1)),
              ("review-stale-runtime", receipt_change(("handoff", "final_review", "runtime"), {"model": "stale"})),
              ("review-stale-base", receipt_change(("handoff", "final_review", "candidate"), {"head": "a" * 40, "base": "f" * 40}))]
    return cases


class Fixture:
    def __init__(self, result): self.result, self.operations = result, []
    def send(self, operation):
        self.operations.append(operation)
        result = deepcopy(self.result)
        result["observation"] = {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
        if "candidate" in result:
            artifact_id = result["artifacts"][0]
            command = result["tools"][0]
            result["evidence"] = {"artifact": {"id": artifact_id, "task_id": operation["task"]["id"], "operation_id": operation["id"], "head": result["candidate"]["head"], "base": result["candidate"]["base"]}, "commands": [{"command": command, "result": "pass", "artifact_id": artifact_id, "operation_id": operation["id"]}], "checks": [{"criterion_id": criterion, "command": command, "result": "pass", "artifact_id": artifact_id, "operation_id": operation["id"]} for criterion in operation["task"]["criteria"]]}
            if operation["phase"] == "verify":
                result["handoff"] = {"qa": [{"status": "pass", "head": result["candidate"]["head"], "command": command, "result": "pass", "artifact_id": artifact_id, "operation_id": operation["id"]} for command in operation["task"]["commands"]["qa"]], "ci": [{"status": "pass", "head": result["candidate"]["head"], "command": command, "result": "pass", "artifact_id": artifact_id, "operation_id": operation["id"]} for command in operation["task"]["commands"]["ci"]], "final_review": {"verdict": "pass", "candidate": result["candidate"], "fresh_context": True, "runtime": result["runtime"], "artifact_id": artifact_id, "operation_id": operation["id"], "criteria": list(operation["task"]["criteria"])}, "pr": {"url": "https://example.invalid/pr/1", "head": result["candidate"]["head"], "base": result["candidate"]["base"], "state": "open", "operation_id": operation["id"], "artifact_id": artifact_id, "merge": "unavailable"}}
        return result
    def reconcile(self, operation): return self.send(operation)
    def cancel(self, operation): return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "state": "cancelled"}
    def observe_coordinator(self, operation):
        return {"observation": {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}, "current_coordinator": operation["session_id"], "state": "active", "elapsed_seconds": 0}


class CoordinatorTests(InterimCheckpointFixture):
    # This fixture performs only synchronous writes and clones.
    maintenance_loose_threshold = 512

    def assert_receipt_parity(self, cases, phase="verify", handoff=False):
        store = self.store(self.first)
        approved = initial_record(self.s2_approval())
        original = store.create_and_publish(approved)
        final = InterimFixtureCoordinator(store).run_one(
            original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        operation = next(item for item in final.value["usage"]["operations"] if item["phase"] == phase)

        def inject(value):
            # Only disposable Git fixtures bypass validation, to model corrupt
            # publications from an older adapter. Never touch the source repo.
            current = store._store.read()
            written = store._store.write(current.commit_sha, current.digest, value)
            store._store.push("origin", current.commit_sha, written.commit_sha)
            return InterimCheckpointSnapshot(value, digest(value), written.commit_sha)

        for name, mutate in cases:
            bad = deepcopy(operation["receipt"])
            mutate(bad)
            with self.subTest(case=name, phase=phase, boundary="transition-contract"):
                with self.assertRaises(InterimDispatchError):
                    if handoff:
                        _handoff(bad.get("handoff"), operation["receipt"]["candidate"], operation,
                                 self.task(), "artifact", operation["receipt"]["runtime"])
                    else:
                        _success(bad, operation, phase.title(), final.value["approval"]["routes"][phase],
                                 self.task(), operation["receipt"]["candidate"] if phase == "verify" else None)

            corrupt = deepcopy(final.value)
            next(item for item in corrupt["usage"]["operations"] if item["phase"] == phase)["receipt"] = bad
            if handoff:
                # Keep the state copy consistent, so the handoff contract itself
                # must refuse the receipt, rather than just detecting copy drift.
                corrupt["state"]["handback"]["evidence"] = deepcopy(bad.get("handoff"))
            current = inject(final.value)
            with self.subTest(case=name, phase=phase, boundary="persist"):
                with self.assertRaises(InterimError):
                    store.persist(current, corrupt)
            invalid = inject(corrupt)
            with self.subTest(case=name, phase=phase, boundary="clean-clone-reload"):
                clone = self.clone("parity-" + phase + "-" + name)
                with self.assertRaises(InterimCheckpointError):
                    self.store(clone).reload(approved)
            with self.subTest(case=name, phase=phase, boundary="corrupt-entry-zero-sends"):
                build, verify = Fixture(self.result()), Fixture(self.result("verify"))
                with self.assertRaises(InterimDispatchError):
                    InterimFixtureCoordinator(store).run_one(invalid, "TASK-413", self.task(), build, verify)
                self.assertEqual((build.operations, verify.operations), ([], []))

            class Mutated(Fixture):
                def send(self, intent):
                    receipt = super().send(intent)
                    mutate(receipt)
                    return receipt

            current = inject(approved)
            build = Mutated(self.result()) if phase == "build" else Fixture(self.result())
            verify = Mutated(self.result("verify")) if phase == "verify" else Fixture(self.result("verify"))
            with self.subTest(case=name, phase=phase, boundary="new-receipt-durable-handback"):
                stopped = InterimFixtureCoordinator(store).run_one(current, "TASK-413", self.task(), build, verify)
                self.assertEqual(stopped.value["state"]["next_action"], "handback")
                self.assertTrue(stopped.value["state"]["handback"]["reason"])
                reloaded = self.store(self.second).reload(approved)
                self.assertEqual(reloaded.value, stopped.value)
                self.assertEqual(len(build.operations), 1)
                self.assertEqual(len(verify.operations), int(phase == "verify"))

    @memoized_control_refs
    def test_receipt_acceptance_parity_diagnosed_cases(self):
        self.assert_receipt_parity([
            ("not-fresh", lambda r: r.update(fresh_context=False)),
            ("missing-fresh", lambda r: r.pop("fresh_context")),
            ("builder-transcript", lambda r: r.update(builder_transcript=True)),
            ("blocked", lambda r: r.update(verdict="blocked")),
            ("wall-over-limit", lambda r: r.update(wall_time_seconds=1000)),
            ("artifacts-over-limit", lambda r: r.update(artifacts=["artifact", "extra", "third"])),
            ("duplicate-check", lambda r: r["evidence"]["checks"].append(deepcopy(r["evidence"]["checks"][0]))),
            ("extra-failed-command", lambda r: r["evidence"]["commands"].append(dict(r["evidence"]["commands"][0], result="fail"))),
        ])

    @memoized_control_refs
    def test_worker_acceptance_parity_build_matrix(self):
        self.assert_receipt_parity(worker_mutations("build"), phase="build")

    @memoized_control_refs
    def test_worker_acceptance_parity_verify_matrix(self):
        self.assert_receipt_parity(worker_mutations("verify"))

    @memoized_control_refs
    def test_handoff_acceptance_parity_matrix(self):
        self.assert_receipt_parity(handoff_mutations(), handoff=True)

    @memoized_control_refs
    def test_operation_binding_parity_matrix(self):
        store = self.store(self.first)
        approved = initial_record(self.s2_approval())
        original = store.create_and_publish(approved)
        final = InterimFixtureCoordinator(store).run_one(
            original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        cases = []
        for index, phase in enumerate(("coordinator", "build", "verify")):
            for name in ("id", "session_id", "message_id", "terminal_turn_id", "slice", "phase", "task", "receipt"):
                path = ("usage", "operations", index, name)
                cases.append((phase + "-missing-" + name, receipt_change(path)))
            for name in ("id", "attempt", "base", "criteria", "runtimes", "limits"):
                cases.append((phase + "-task-" + name, receipt_change(("usage", "operations", index, "task", name), "stale")))
        cases += [
            ("missing-verify-candidate", receipt_change(("usage", "operations", 2, "candidate"))),
            ("stale-verify-candidate", receipt_change(("usage", "operations", 2, "candidate"), {"head": "f" * 40, "base": "b" * 40})),
            ("missing-verify-criteria", receipt_change(("usage", "operations", 2, "criteria"))),
            ("stale-verify-criteria", receipt_change(("usage", "operations", 2, "criteria"), ["other"])),
            ("missing-state-action", receipt_change(("state", "next_action"))),
            ("missing-charges", receipt_change(("usage", "charges"))),
            ("missing-launches", receipt_change(("usage", "launches"))),
            ("stale-route", receipt_change(("approval", "routes", "verify", "model"), "other")),
            ("operation-order", lambda r: r["usage"]["operations"].reverse()),
        ]
        def stale_verify_before_pr_ready(record):
            # Rewrite only Verify's internally correlated observation. The
            # accepted Build remains the authority for the review candidate.
            operation = record["usage"]["operations"][2]
            receipt = operation["receipt"]
            candidate = {"head": "f" * 40, "base": "b" * 40}
            old_id = operation["id"]
            operation["candidate"] = deepcopy(candidate)
            task = operation["task"]
            operation["id"] = "op-" + digest({"run": record["approval"]["run_id"], "slice": task["slice_id"], "task": task["id"], "attempt": task["attempt"], "candidate": candidate["head"], "phase": "verify"})[7:23]
            operation.update(session_id="verify-" + operation["id"], message_id="message-" + operation["id"], terminal_turn_id="terminal-" + operation["id"])
            receipt["observation"] = {key: operation[key] for key in ("id", "session_id", "message_id", "terminal_turn_id")}
            receipt["candidate"] = deepcopy(candidate)
            receipt["evidence"]["artifact"].update(head=candidate["head"], operation_id=operation["id"])
            for item in receipt["evidence"]["commands"] + receipt["evidence"]["checks"]:
                item["operation_id"] = operation["id"]
            for item in record["usage"]["launches"] + record["usage"]["charges"]:
                if item["operation_id"] == old_id:
                    item["operation_id"] = operation["id"]
            record["state"].update(next_action="verify", review=None, handback=None)
        cases.append(("stale-verify-intermediate", stale_verify_before_pr_ready))
        def coordinator_as_worker(record):
            operation = record["usage"]["operations"][0]
            operation["status"] = "result"
            operation["receipt"].update(transport="accepted", terminal_turn=True, task_success=True)
        cases.append(("coordinator-as-worker", coordinator_as_worker))
        for name, mutate in cases:
            corrupt = deepcopy(final.value)
            mutate(corrupt)
            with self.subTest(case=name, boundary="persist"), self.assertRaises(InterimError):
                store.persist(final, corrupt)
            current = store._store.read()
            injected = store._store.write(current.commit_sha, current.digest, corrupt)
            store._store.push("origin", current.commit_sha, injected.commit_sha)
            with self.subTest(case=name, boundary="clean-clone-reload"):
                clone = self.clone("binding-" + name)
                with self.assertRaises(InterimCheckpointError):
                    self.store(clone).reload(approved)
            with self.subTest(case=name, boundary="transition-zero-sends"):
                build, verify = Fixture(self.result()), Fixture(self.result("verify"))
                invalid = InterimCheckpointSnapshot(corrupt, digest(corrupt), injected.commit_sha)
                with self.assertRaises(InterimDispatchError):
                    InterimFixtureCoordinator(store).run_one(invalid, "TASK-413", self.task(), build, verify)
                self.assertEqual((build.operations, verify.operations), ([], []))
            current = store._store.read()
            restored = store._store.write(current.commit_sha, current.digest, final.value)
            store._store.push("origin", current.commit_sha, restored.commit_sha)
            final = InterimCheckpointSnapshot(final.value, digest(final.value), restored.commit_sha)

    def test_bad_reconciled_receipt_preserves_durable_incomplete_handback(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        timeout = self.result("verify")
        timeout.update(transport="unknown", terminal_turn=False, task_success=False)
        build, verify = Fixture(self.result()), Fixture(timeout)
        coordinator = InterimFixtureCoordinator(self.store(self.first))
        pending = coordinator.run_one(original, "TASK-413", self.task(), build, verify)
        operation = pending.value["usage"]["operations"][-1]
        verify.result = self.result("verify")
        verify.result["fresh_context"] = False
        stopped = coordinator.reconcile_pending(pending, operation["id"], verify)
        self.assertEqual(stopped.value["state"]["next_action"], "handback")
        self.assertEqual(stopped.value["usage"], pending.value["usage"])
        self.assertEqual(self.store(self.second).reload(initial_record(self.s2_approval())).value, stopped.value)
        self.assertEqual([item["id"] for item in verify.operations], [operation["id"], operation["id"]])

    def test_acceptance_parity_positive_at_task_bounds_retains_findings(self):
        task = self.task()
        task["criteria"].append("AC02")
        for name in task["commands"]:
            task["commands"][name].append(name + "-second")
        approved = self.approval()
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)}]
        initial = initial_record(approved)
        store = self.store(self.first)
        original = store.create_and_publish(initial)
        test = self

        class Complete(Fixture):
            def send(self, operation):
                durable = test.store(test.second).reload(initial)
                intended = next(item for item in durable.value["usage"]["operations"] if item["id"] == operation["id"])
                test.assertEqual(intended["status"], "intent")
                result = super().send(operation)
                result["evidence"]["commands"] = [dict(result["evidence"]["commands"][0], command=command) for command in result["tools"]]
                return result

        results = []
        for phase in ("build", "verify"):
            result = self.result(phase)
            result.update(criteria={"AC01": "pass", "AC02": "pass"}, executed_checks=["AC01", "AC02"],
                          tools=task["commands"][phase], artifacts=["artifact", "supplement"], wall_time_seconds=60)
            results.append(Complete(result))
        final = InterimFixtureCoordinator(store).run_one(original, "TASK-413", task, *results)
        self.assertEqual(final.value["state"]["next_action"], "pr-ready")
        republished = store.persist(final, final.value)
        reloaded = self.store(self.clone("positive-parity")).reload(initial)
        self.assertEqual(reloaded.commit_sha, republished.commit_sha)
        self.assertEqual(reloaded.value["state"]["review"], {"findings": [{"id": "N1"}], "verdict": "pass"})
        self.assertEqual(len(reloaded.value["usage"]["charges"]), 3)

    def task(self):
        return {"id": "build-task-413", "slice_id": "TASK-413", "attempt": 1, "candidate_ref": "candidate-task-413", "base": "b" * 40, "criteria": ["AC01"], "runtimes": {"build": {"runner": "build-runner", "permissions": "read-only"}, "verify": {"runner": "verify-runner", "permissions": "read-only"}}, "commands": {"build": ["unit"], "verify": ["unit"], "qa": ["qa-command"], "ci": ["ci-command"]}, "limits": {"max_artifacts": 2, "max_tools": 2, "wall_time_seconds": 60}}

    def s2_approval(self):
        approved = self.approval()
        task = self.task()
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)}]
        return approved

    def result(self, phase="build", candidate=None):
        candidate = candidate or {"head": "a" * 40, "base": "b" * 40}
        route = self.approval()["routes"]["verify" if phase == "verify" else "build"]
        result = {"transport": "accepted", "terminal_turn": True, "task_success": True, "candidate": candidate, "criteria": {"AC01": "pass"}, "executed_checks": ["AC01"], "runtime": {"model": route["model"], "effort": route["effort"], "runner": phase + "-runner", "permissions": "read-only"}, "fresh_context": phase == "verify", "builder_transcript": False, "verdict": "pass", "nonblocking_findings": [{"id": "N1"}], "artifacts": ["artifact"], "tools": ["unit"], "wall_time_seconds": 1, "elapsed_seconds": 1, "host_counters": {"tokens": None, "cost": None}}
        return result

    def test_checkpointed_fixture_requires_fresh_verify_and_never_merges(self):
        record = initial_record(self.s2_approval())
        original = self.store(self.first).create_and_publish(record)
        build, verify = Fixture(self.result()), Fixture(self.result("verify"))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), build, verify)
        self.assertEqual(final.value["state"]["next_action"], "pr-ready")
        self.assertEqual(final.value["state"]["handback"]["merge"], "unavailable")
        self.assertEqual(len(final.value["usage"]["launches"]), 3)
        self.assertEqual(build.operations[0]["id"], final.value["usage"]["operations"][1]["id"])
        self.assertEqual(final.value["state"]["review"]["findings"], [{"id": "N1"}])

    def test_idle_or_terminal_without_success_hands_back_after_persisting_receipt(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        bad = self.result(); bad["task_success"] = False
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(bad), Fixture(self.result("verify")))
        self.assertEqual(final.value["state"]["next_action"], "handback")
        self.assertEqual(final.value["usage"]["operations"][1]["receipt"]["transport"], "accepted")

    def test_selected_cap_stops_before_verify_and_unknown_cost_stays_null(self):
        approved = self.s2_approval(); approved["hard_limits"] = {"dispatch_max": 2}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        self.assertEqual(final.value["state"]["next_action"], "handback")
        self.assertEqual(final.value["usage"]["host_counters"], {"tokens": None, "cost": None})

    def test_pending_operation_reconciles_same_durable_id_without_resend(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        task = self.task()
        coordinator = InterimFixtureCoordinator(self.store(self.first))
        record = deepcopy(original.value)
        operation_id = "op-" + digest({"run": "run-task-413", "slice": task["slice_id"], "task": task["id"], "attempt": task["attempt"], "candidate": task["candidate_ref"], "phase": "build"})[7:23]
        operation = {"id": operation_id, "slice": "TASK-413", "phase": "build", "task": task, **operation_identities(record["approval"]["run_id"], operation_id, "build"), "status": "intent", "issued_at": "2026-09-19T16:00:00Z", "elapsed_seconds": 0}
        record["usage"]["operations"].append(operation)
        record["usage"]["launches"].append({"operation_id": operation_id, "phase": "build", "issued_at": operation["issued_at"]})
        record["usage"]["charges"].append({"operation_id": operation_id, "work_units": 1, "status": "pending", "charged_at": operation["issued_at"]})
        pending = self.store(self.first).persist(original, record)
        adapter = Fixture(self.result())
        reconciled = coordinator.reconcile_pending(pending, operation_id, adapter)
        self.assertEqual(reconciled.value["usage"]["operations"][0]["status"], "reconciled")
        self.assertEqual(adapter.operations[0]["id"], operation_id)

    def test_deadline_crossing_cancels_a_nonterminal_modeled_operation(self):
        approved = self.s2_approval(); approved["hard_limits"] = {"deadline_at": "2026-09-19T18:00:00Z", "dispatch_max": 3}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        pending = self.result(); pending["terminal_turn"] = False; pending["task_success"] = False
        times = iter((datetime(2026, 9, 19, 17, 58, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, 30, tzinfo=timezone.utc), datetime(2026, 9, 19, 18, 1, tzinfo=timezone.utc)))
        test = self
        class DurableCancel(Fixture):
            def cancel(self, operation):
                durable = test.store(test.second).reload(initial_record(approved)).value
                current = next(op for op in durable["usage"]["operations"] if op["id"] == operation["id"])
                test.assertEqual(current["status"], "cancellation-uncertain")
                test.assertEqual(current["cancellation_intent"]["reason"], "selected deadline reached")
                test.assertEqual(current["cancellation"]["state"], "uncertain")
                test.assertEqual(current["receipt"], operation["receipt"])
                for identity in ("id", "session_id", "message_id", "terminal_turn_id"):
                    test.assertEqual(current[identity], operation[identity])
                return super().cancel(operation)
        final = InterimFixtureCoordinator(self.store(self.first), clock=lambda: next(times)).run_one(original, "TASK-413", self.task(), DurableCancel(pending), Fixture(self.result("verify")))
        self.assertEqual(final.value["state"]["handback"]["reason"], "selected deadline reached; cancellation observed for unfinished operation")
        self.assertEqual(final.value["usage"]["operations"][1]["status"], "unfinished-cancelled")

    def test_timeout_reconciles_and_resumes_without_a_second_build_send(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        timeout = self.result(); timeout["transport"] = "timeout"; timeout["terminal_turn"] = False; timeout["task_success"] = False
        build, verify = Fixture(timeout), Fixture(self.result("verify"))
        coordinator = InterimFixtureCoordinator(self.store(self.first))
        pending = coordinator.run_one(original, "TASK-413", self.task(), build, verify)
        self.assertEqual(pending.value["usage"]["operations"][1]["status"], "reconcile-required")
        build.result = self.result()
        reconciled = coordinator.reconcile_pending(pending, build.operations[0]["id"], build)
        final = coordinator.run_one(reconciled, "TASK-413", self.task(), build, verify)
        self.assertEqual(final.value["state"]["next_action"], "pr-ready")
        self.assertEqual(len(build.operations), 2)  # original send plus same-ID reconcile, never a new Build

    def test_verify_timeout_reconciles_and_resumes_without_replacing_either_operation(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        timeout = self.result("verify"); timeout["transport"] = "unknown"; timeout["terminal_turn"] = False; timeout["task_success"] = False
        build, verify = Fixture(self.result()), Fixture(timeout)
        coordinator = InterimFixtureCoordinator(self.store(self.first))
        pending = coordinator.run_one(original, "TASK-413", self.task(), build, verify)
        verify_operation = pending.value["usage"]["operations"][-1]
        self.assertEqual(verify_operation["status"], "reconcile-required")
        verify.result = self.result("verify")
        reconciled = coordinator.reconcile_pending(pending, verify_operation["id"], verify)
        final = coordinator.run_one(reconciled, "TASK-413", self.task(), build, verify)
        self.assertEqual(final.value["state"]["next_action"], "pr-ready")
        self.assertEqual(len(build.operations), 1)
        self.assertEqual([item["id"] for item in verify.operations], [verify_operation["id"], verify_operation["id"]])

    def test_corrupted_s2_ledger_and_unbound_task_refuse_before_dispatch(self):
        record = initial_record(self.s2_approval())
        record["forecasts"]["revised"].append({"anything": "forged"})
        with self.assertRaisesRegex(InterimError, "revised forecast"):
            validate_record(record)
        record = initial_record(self.s2_approval())
        record["usage"]["launches"].append({"operation_id": "missing", "phase": "build", "issued_at": "2026-09-19T16:00:00Z"})
        with self.assertRaisesRegex(InterimError, "launch ledger"):
            validate_record(record)
        unbound = self.task(); unbound["attempt"] = 2
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        with self.assertRaisesRegex(InterimError, "not bound"):
            InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", unbound, Fixture(self.result()), Fixture(self.result("verify")))

    def test_forged_evidence_and_wrong_coordinator_observation_hand_back_before_build(self):
        class Forged(Fixture):
            def send(self, operation):
                result = super().send(operation)
                result["evidence"]["artifact"]["operation_id"] = "other-operation"
                return result

        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        forged = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Forged(self.result()), Fixture(self.result("verify")))
        self.assertEqual(forged.value["state"]["next_action"], "handback")
        self.assertIn("receipt is corrupt", forged.value["state"]["handback"]["reason"])

        class OtherCoordinator(Fixture):
            def observe_coordinator(self, operation):
                result = super().observe_coordinator(operation)
                result["current_coordinator"] = "plausible-second-coordinator"
                return result

        reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
        wrong = OtherCoordinator(self.result())
        refused = InterimFixtureCoordinator(self.store(self.second)).run_one(reloaded, "TASK-413", self.task(), wrong, Fixture(self.result("verify")))
        self.assertEqual(refused.value["state"]["next_action"], "handback")
        self.assertIn("current coordinator", refused.value["state"]["handback"]["reason"])
        self.assertEqual(wrong.operations, [])

    def test_outcome_only_handoff_cannot_be_pr_ready(self):
        class OutcomeOnly(Fixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "verify":
                    result["handoff"] = {"qa": {"status": "pass", "head": result["candidate"]["head"]}, "ci": {"status": "pass", "head": result["candidate"]["head"]}, "final_review": {"verdict": "pass", "candidate": result["candidate"]}, "pr": {"url": "https://example.invalid/pr/forged", "head": result["candidate"]["head"], "base": result["candidate"]["base"], "merge": "unavailable"}}
                return result

        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(self.result()), OutcomeOnly(self.result("verify")))
        self.assertEqual(final.value["state"]["next_action"], "handback")
        self.assertIn("qa evidence", final.value["state"]["handback"]["reason"])

    def test_load_rejects_linked_launch_phase_and_every_receipt_identity_mismatch(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        corrupted = deepcopy(final.value)
        corrupted["usage"]["launches"][0]["phase"] = "build"
        with self.assertRaisesRegex(InterimError, "launch ledger"):
            validate_record(corrupted)
        verify = next(item for item in final.value["usage"]["operations"] if item["phase"] == "verify")
        for field in ("id", "session_id", "message_id", "terminal_turn_id"):
            corrupted = deepcopy(final.value)
            receipt = next(item for item in corrupted["usage"]["operations"] if item["phase"] == "verify")["receipt"]
            receipt["observation"][field] = "unrelated-" + field
            with self.subTest(field=field), self.assertRaisesRegex(InterimError, "not correlated"):
                validate_record(corrupted)

    def test_every_approved_qa_ci_command_requires_one_bound_result(self):
        task = self.task()
        task["commands"]["qa"].append("qa-second-required")
        task["commands"]["ci"].append("ci-second-required")
        approved = self.approval()
        approved["tasks"] = [{"id": task["id"], "slice_id": task["slice_id"], "spec_revision": approved["tracker"]["spec_revision"], "digest": digest(task)}]

        class Partial(Fixture):
            def send(self, operation):
                result = super().send(operation)
                if operation["phase"] == "verify":
                    result["handoff"]["qa"] = result["handoff"]["qa"][:1]
                    result["handoff"]["ci"] = result["handoff"]["ci"][:1]
                return result

        original = self.store(self.first).create_and_publish(initial_record(approved))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(original, "TASK-413", task, Fixture(self.result()), Partial(self.result("verify")))
        self.assertEqual(final.value["state"]["next_action"], "handback")
        self.assertIn("incomplete", final.value["state"]["handback"]["reason"])

    def test_deadline_wrong_cancellation_receipt_persists_uncertain_handback(self):
        class WrongCancel(Fixture):
            def cancel(self, operation):
                result = super().cancel(operation)
                result["observation"]["message_id"] = "unrelated-message"
                return result

        approved = self.s2_approval(); approved["hard_limits"] = {"deadline_at": "2026-09-19T18:00:00Z", "dispatch_max": 3}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        pending = self.result(); pending["terminal_turn"] = False; pending["task_success"] = False
        times = iter((datetime(2026, 9, 19, 17, 58, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, 30, tzinfo=timezone.utc), datetime(2026, 9, 19, 18, 1, tzinfo=timezone.utc)))
        final = InterimFixtureCoordinator(self.store(self.first), clock=lambda: next(times)).run_one(original, "TASK-413", self.task(), WrongCancel(pending), Fixture(self.result("verify")))
        operation = final.value["usage"]["operations"][1]
        self.assertEqual(operation["status"], "cancellation-uncertain")
        self.assertEqual(operation["receipt"]["terminal_turn"], False)
        self.assertEqual(operation["cancellation"]["state"], "uncertain")
        self.assertIn("cancellation uncertain", final.value["state"]["handback"]["reason"])

    def test_deadline_cancel_transport_failure_persists_uncertain_handback(self):
        class FailingCancel(Fixture):
            def cancel(self, operation):
                raise TimeoutError("adapter cancellation timed out")

        approved = self.s2_approval(); approved["hard_limits"] = {"deadline_at": "2026-09-19T18:00:00Z", "dispatch_max": 3}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        pending = self.result(); pending["terminal_turn"] = False; pending["task_success"] = False
        times = iter((datetime(2026, 9, 19, 17, 58, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, 30, tzinfo=timezone.utc), datetime(2026, 9, 19, 18, 1, tzinfo=timezone.utc)))
        final = InterimFixtureCoordinator(self.store(self.first), clock=lambda: next(times)).run_one(original, "TASK-413", self.task(), FailingCancel(pending), Fixture(self.result("verify")))
        self.assertEqual(final.value["usage"]["operations"][1]["status"], "cancellation-uncertain")
        self.assertIn("adapter cancellation timed out", final.value["state"]["handback"]["reason"])

    def test_deadline_missing_cancellation_receipt_persists_uncertain_handback(self):
        class MissingCancel(Fixture):
            def cancel(self, operation):
                return {}

        approved = self.s2_approval(); approved["hard_limits"] = {"deadline_at": "2026-09-19T18:00:00Z", "dispatch_max": 3}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        pending = self.result(); pending["terminal_turn"] = False; pending["task_success"] = False
        times = iter((datetime(2026, 9, 19, 17, 58, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, 30, tzinfo=timezone.utc), datetime(2026, 9, 19, 18, 1, tzinfo=timezone.utc)))
        final = InterimFixtureCoordinator(self.store(self.first), clock=lambda: next(times)).run_one(original, "TASK-413", self.task(), MissingCancel(pending), Fixture(self.result("verify")))
        self.assertEqual(final.value["usage"]["operations"][1]["status"], "cancellation-uncertain")
        self.assertIn("adapter observation is not correlated", final.value["state"]["handback"]["reason"])

    def test_deadline_ambiguous_cancellation_state_persists_uncertain_handback(self):
        class AmbiguousCancel(Fixture):
            def cancel(self, operation):
                result = super().cancel(operation)
                result["state"] = "pending"
                return result

        approved = self.s2_approval(); approved["hard_limits"] = {"deadline_at": "2026-09-19T18:00:00Z", "dispatch_max": 3}
        original = self.store(self.first).create_and_publish(initial_record(approved))
        pending = self.result(); pending["terminal_turn"] = False; pending["task_success"] = False
        times = iter((datetime(2026, 9, 19, 17, 58, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, tzinfo=timezone.utc), datetime(2026, 9, 19, 17, 59, 30, tzinfo=timezone.utc), datetime(2026, 9, 19, 18, 1, tzinfo=timezone.utc)))
        final = InterimFixtureCoordinator(self.store(self.first), clock=lambda: next(times)).run_one(original, "TASK-413", self.task(), AmbiguousCancel(pending), Fixture(self.result("verify")))
        self.assertEqual(final.value["usage"]["operations"][1]["status"], "cancellation-uncertain")
        self.assertIn("missing terminal cancellation state", final.value["state"]["handback"]["reason"])

    def test_portable_semantics_rejects_identity_phase_and_pr_ready_rewrites(self):
        store = self.store(self.first)
        original = store.create_and_publish(initial_record(self.s2_approval()))
        final = InterimFixtureCoordinator(store).run_one(original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        build = next(item for item in final.value["usage"]["operations"] if item["phase"] == "build")

        rewritten = deepcopy(final.value)
        changed = next(item for item in rewritten["usage"]["operations"] if item["phase"] == "build")
        changed["id"] = "op-" + "f" * 16
        changed["session_id"] = "build-" + changed["id"]
        changed["message_id"] = "message-" + changed["id"]
        changed["terminal_turn_id"] = "terminal-" + changed["id"]
        changed["receipt"]["observation"] = {name: changed[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        for launch in rewritten["usage"]["launches"]:
            if launch["operation_id"] == build["id"]: launch["operation_id"] = changed["id"]
        for charge in rewritten["usage"]["charges"]:
            if charge["operation_id"] == build["id"]: charge["operation_id"] = changed["id"]
        with self.assertRaisesRegex(InterimError, "derived"):
            validate_record(rewritten)
        with self.assertRaises(InterimError):
            store.persist(final, rewritten)

        coherent = deepcopy(final.value)
        changed = next(item for item in coherent["usage"]["operations"] if item["phase"] == "build")
        old_id, changed["id"] = changed["id"], "op-" + "e" * 16
        changed["session_id"] = "build-" + changed["id"]
        changed["message_id"] = "message-" + changed["id"]
        changed["terminal_turn_id"] = "terminal-" + changed["id"]
        changed["receipt"]["observation"] = {name: changed[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        evidence = changed["receipt"]["evidence"]
        evidence["artifact"]["operation_id"] = changed["id"]
        for item in evidence["commands"] + evidence["checks"]: item["operation_id"] = changed["id"]
        for launch in coherent["usage"]["launches"]:
            if launch["operation_id"] == old_id: launch["operation_id"] = changed["id"]
        for charge in coherent["usage"]["charges"]:
            if charge["operation_id"] == old_id: charge["operation_id"] = changed["id"]
        with self.assertRaisesRegex(InterimError, "derived"):
            validate_record(coherent)

        phase_rewritten = deepcopy(final.value)
        changed = next(item for item in phase_rewritten["usage"]["operations"] if item["phase"] == "build")
        changed["phase"] = "verify"
        next(item for item in phase_rewritten["usage"]["launches"] if item["operation_id"] == changed["id"])["phase"] = "verify"
        with self.assertRaisesRegex(InterimError, "purpose|Verify"):
            validate_record(phase_rewritten)

        forged_state = deepcopy(final.value)
        forged_state["state"] = {"next_action": "pr-ready", "candidate": {"head": "f" * 40, "base": "b" * 40}, "review": {"verdict": "pass", "findings": []}, "handback": {"outcome": "pr-ready", "merge": "unavailable", "evidence": {}}}
        with self.assertRaisesRegex(InterimError, "candidate|review|evidence"):
            validate_record(forged_state)
        forged_review = deepcopy(final.value)
        forged_review["state"]["review"]["findings"] = []
        with self.assertRaisesRegex(InterimError, "review"):
            validate_record(forged_review)

    def test_corrupt_remote_reload_and_public_entry_refuse_without_sends(self):
        store = self.store(self.first)
        original = store.create_and_publish(initial_record(self.s2_approval()))
        final = InterimFixtureCoordinator(store).run_one(original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify")))
        corrupt = deepcopy(final.value)
        corrupt["state"]["candidate"]["head"] = "f" * 40
        # Test-only lower-level write simulates an old/corrupt remote publication.
        injected = store._store.write(final.commit_sha, final.digest, corrupt)
        store._store.push("origin", final.commit_sha, injected.commit_sha)
        with self.assertRaisesRegex(InterimCheckpointError, "corrupt"):
            self.store(self.second).reload(initial_record(self.s2_approval()))
        build = Fixture(self.result())
        invalid = InterimCheckpointSnapshot(corrupt, digest(corrupt), final.commit_sha)
        with self.assertRaisesRegex(InterimDispatchError, "corrupt checkpoint"):
            InterimFixtureCoordinator(store).run_one(invalid, "TASK-413", self.task(), build, Fixture(self.result("verify")))
        self.assertEqual(build.operations, [])

    def test_pr_ready_semantics_reload_from_a_clean_clone(self):
        original = self.store(self.first).create_and_publish(initial_record(self.s2_approval()))
        final = InterimFixtureCoordinator(self.store(self.first)).run_one(
            original, "TASK-413", self.task(), Fixture(self.result()), Fixture(self.result("verify"))
        )
        reloaded = self.store(self.second).reload(initial_record(self.s2_approval()))
        self.assertEqual(reloaded.commit_sha, final.commit_sha)
        self.assertEqual(reloaded.value["state"]["next_action"], "pr-ready")

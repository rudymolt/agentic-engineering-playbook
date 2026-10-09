from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import os
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch


PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.interim import (  # noqa: E402
    InterimCheckpointError,
    InterimCheckpointStore,
    InterimError,
    initial_record,
    preflight,
    validate_record,
)
from delivery_pilot.continuation import ContinuationError, initial_state  # noqa: E402
from delivery_pilot.canonical import canonical_bytes, digest  # noqa: E402


def approval(fetch_url: str = "https://example.invalid/approved.git", push_url: str = "https://example.invalid/approved.git") -> dict:
    return {
        "kind": "interim-run-approval",
        "version": 1,
        "approval_id": "approval-task-413",
        "source_event_id": "human-approval-task-413",
        "run_id": "run-task-413",
        "repository": {
            "remote": "origin", "fetch_url": fetch_url, "push_url": push_url,
            "control_ref": "refs/heads/delivery-control/issue-run-task-413",
        },
        "tracker": {"id": "TASK-413", "spec_revision": "sha256:" + "a" * 64},
        "slices": [{"id": "TASK-413", "dependencies": [], "mode": "AFK"}, {"id": "TASK-419", "dependencies": ["TASK-413"], "mode": "HITL"}],
        "implementation_paths": ["v0.5/delivery/src/delivery_pilot/interim.py", "v0.5/delivery/tests/test_interim.py"],
        "workspaces": {"coordinator": ".context/coordinator-run-task-413", "candidate": ".context/candidate-run-task-413"},
        "coordinator": {"session_id": "coordinator-1"},
        "routes": {
            "build": {"model": "gpt-5.6-terra", "effort": "high", "fallback": None},
            "verify": {"model": "gpt-5.6-sol", "effort": "medium", "fallback": "same-runner-human-override"},
            "diagnosis": {"model": "gpt-5.6-terra", "effort": "high", "fallback": None},
            "escalated_verify": {"model": "gpt-6.1-sol", "effort": "high", "fallback": None},
        },
        "forecast": {"work_units": 1, "verification_units": 1},
        "progress_checkpoint_policy": "worker-result-and-forecast-exceeded",
        "hard_limits": "none",
        "maximum_action": "open-pr",
        "checkpoint": {"ref": "refs/heads/delivery-control/issue-run-task-413"},
        "whole_run_stop": "disable-coordinator-watchdog-cancel-known-workers-and-checkpoint",
    }


class InterimApprovalTests(unittest.TestCase):
    def test_frozen_public_base_history_is_readable_without_byte_rewrites(self) -> None:
        fixture = PACK / "tests/fixtures/legacy-escalated-history.json"
        original = fixture.read_bytes()
        record = json.loads(original)
        approved_bytes = canonical_bytes(record["approval"])
        validated = validate_record(record)
        self.assertEqual(fixture.read_bytes(), original)
        self.assertEqual(canonical_bytes(validated["approval"]), approved_bytes)
        operations = [item for item in record["usage"]["operations"] if "escalated_verify" in item]
        self.assertTrue(operations)
        from delivery_pilot.interim_routes import route_for_operation, configured_route
        for operation in operations:
            self.assertEqual(operation["route"], {"model": "gpt-6-sol", "effort": "high"})
            self.assertEqual(route_for_operation(record["approval"], operation), operation["route"])
            self.assertEqual(configured_route(record["approval"]["routes"], operation), operation["route"])
            for forged_route in ({"model": "gpt-6.1-sol", "effort": "high"}, {"model": "gpt-6-sol", "effort": "medium"}):
                forged = deepcopy(record)
                next(item for item in forged["usage"]["operations"] if item["id"] == operation["id"])["route"] = forged_route
                with self.assertRaises(InterimError):
                    validate_record(forged)

    def test_new_verify_seed_is_explicit_and_immutable_not_inferred_from_operations(self) -> None:
        from delivery_pilot.interim_routes import route_for_operation, configured_route
        selected = approval()
        operation = {"phase": "repair-verify", "escalated_verify": "repair-1"}
        expected = {"model": "gpt-6.1-sol", "effort": "high"}
        record = initial_record(selected)
        self.assertEqual(route_for_operation(selected, operation), expected)
        self.assertEqual(configured_route(selected["routes"], operation), expected)
        changed = deepcopy(record)
        del changed["approval"]["routes"]["escalated_verify"]
        with self.assertRaisesRegex(InterimError, "immutable"):
            validate_record(changed)
        for model, effort in (("gpt-6.1-sol", "medium"), ("arbitrary-model", "high"), ("gpt-6-sol", "high")):
            bad = deepcopy(selected)
            bad["routes"]["escalated_verify"].update(model=model, effort=effort)
            with self.assertRaises(InterimError):
                initial_record(bad)

    def test_explicit_escalation_policy_is_immutable_and_legacy_has_no_authority(self) -> None:
        selected = approval()
        selected["escalation_policy"] = {"route": {"model": "gpt-6-astra", "effort": "high"},
                                         "trigger": 3, "scope": "approved-slice",
                                         "authority": "diagnose-and-implement", "cycles_per_slice": 2}
        record = initial_record(selected)
        self.assertEqual(record["approval"]["escalation_policy"], selected["escalation_policy"])
        self.assertNotIn("escalation_policy", initial_record(approval())["approval"])
        changed = deepcopy(record)
        changed["approval"]["escalation_policy"]["cycles_per_slice"] = 1
        with self.assertRaisesRegex(InterimError, "immutable"):
            validate_record(changed)
        bad = deepcopy(selected)
        bad["escalation_policy"]["authority"] = "unbounded"
        with self.assertRaises(InterimError):
            initial_record(bad)

    def test_optional_limit_exception_is_scoped_in_each_required_process_surface(self) -> None:
        edition = PACK.parent
        for relative in ("00-foundations.md", "AGENT-DIGEST.md", "10-process/07-implementation-tdd.md"):
            with self.subTest(relative=relative):
                text = (edition / relative).read_text()
                self.assertIn("hard_limits: none", text)
                self.assertIn("three-no-progress", text)
                self.assertIn("checkpoint-only", text)
                self.assertIn("dispatch-unavailable", text)

    def test_preflight_binds_complete_immutable_approval_without_dispatch(self) -> None:
        record = initial_record(approval())
        result = preflight(record, ["TASK-413"])
        self.assertEqual(result["action"], "checkpoint")
        self.assertEqual(result["run_id"], "run-task-413")
        self.assertEqual(record["approval"]["hard_limits"], "none")
        self.assertEqual(record["usage"], {"operations": [], "launches": [], "host_counters": {"tokens": None, "cost": None}})

    def test_none_is_explicit_and_human_selected_limits_are_not_forecasts(self) -> None:
        missing = approval()
        del missing["hard_limits"]
        with self.assertRaisesRegex(InterimError, "hard_limits"):
            initial_record(missing)
        selected = approval()
        selected["hard_limits"] = {"deadline_at": "2026-09-19T17:01:42Z", "dispatch_max": 4}
        record = initial_record(selected)
        self.assertEqual(record["approval"]["hard_limits"], selected["hard_limits"])
        record["forecasts"]["initial"]["work_units"] = 99
        with self.assertRaisesRegex(InterimError, "forecast"):
            preflight(record, ["TASK-413"])

    def test_preflight_refuses_unapproved_hitl_scope_and_changed_paths(self) -> None:
        record = initial_record(approval())
        with self.assertRaisesRegex(InterimError, "HITL"):
            preflight(record, ["TASK-419"])
        changed = initial_record(approval())
        changed["approval"]["implementation_paths"] = ["other/file.py"]
        with self.assertRaisesRegex(InterimError, "immutable"):
            preflight(changed, ["TASK-413"])
        out_of_scope = approval()
        out_of_scope["repository"]["control_ref"] = out_of_scope["checkpoint"]["ref"] = "refs/heads/main"
        with self.assertRaisesRegex(InterimError, "run-specific"):
            initial_record(out_of_scope)

    def test_approval_rejects_cycles_duplicate_requests_bad_timestamps_refs_and_overlapping_workspaces(self) -> None:
        self_dependent = approval()
        self_dependent["slices"][0]["dependencies"] = ["TASK-413"]
        with self.assertRaisesRegex(InterimError, "self"):
            initial_record(self_dependent)
        cyclic = approval()
        cyclic["slices"][1]["dependencies"] = ["TASK-413"]
        cyclic["slices"][0]["dependencies"] = ["TASK-419"]
        with self.assertRaisesRegex(InterimError, "acyclic"):
            initial_record(cyclic)
        invalid_deadline = approval()
        invalid_deadline["hard_limits"] = {"deadline_at": "Z"}
        with self.assertRaisesRegex(InterimError, "UTC timestamp"):
            initial_record(invalid_deadline)
        invalid_ref = approval()
        invalid_ref["repository"]["control_ref"] = invalid_ref["checkpoint"]["ref"] = "refs/heads/delivery-control/issue-"
        with self.assertRaisesRegex(InterimError, "run-specific"):
            initial_record(invalid_ref)
        wrong_run_ref = approval()
        wrong_run_ref["run_id"] = "different-run"
        with self.assertRaisesRegex(InterimError, "run-specific"):
            initial_record(wrong_run_ref)
        overlapping = approval()
        overlapping["workspaces"]["candidate"] = ".context/coordinator-run-task-413/child"
        with self.assertRaisesRegex(InterimError, "overlap"):
            initial_record(overlapping)
        with self.assertRaisesRegex(InterimError, "unique"):
            preflight(initial_record(approval()), ["TASK-413", "TASK-413"])

    def test_interim_record_is_not_a_protected_envelope(self) -> None:
        with self.assertRaises(ContinuationError):
            initial_state(initial_record(approval()))


class InterimCheckpointFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.git("init", "--bare", str(self.remote), cwd=self.root)
        self.first = self.clone("first")
        self.second = self.clone("second")

    def approval(self) -> dict:
        remote_url = self.git("remote", "get-url", "origin", cwd=self.first).stdout.strip()
        return approval(remote_url, remote_url)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    def clone(self, name: str) -> Path:
        path = self.root / name
        try:
            self.git("clone", "-q", "--no-local", str(self.remote), str(path), cwd=self.root)
        except subprocess.CalledProcessError as exc:
            raise AssertionError(f"Git fixture clone failed: {exc.stderr.strip()}") from exc
        self.git("config", "user.name", "Interim Test", cwd=path)
        self.git("config", "user.email", "interim@example.invalid", cwd=path)
        return path

    def store(self, repository: Path) -> InterimCheckpointStore:
        return InterimCheckpointStore(repository, "origin", self.approval()["checkpoint"]["ref"])


class InterimCheckpointTests(InterimCheckpointFixture):
    def test_persist_uses_one_local_snapshot_and_keeps_remote_cas(self) -> None:
        store = self.store(self.first)
        created = store.create_and_publish(initial_record(self.approval()))
        with patch.object(store._store, "read", wraps=store._store.read) as read:
            updated = store.persist(created, deepcopy(created.value))
            self.assertEqual(1, read.call_count)
        self.assertNotEqual(created.commit_sha, updated.commit_sha)
        with self.assertRaisesRegex(InterimCheckpointError, "moved"):
            store.persist(created, deepcopy(created.value))

    def test_adapter_refuses_a_remote_not_bound_by_approval(self) -> None:
        wrong_remote = InterimCheckpointStore(self.first, "other", self.approval()["checkpoint"]["ref"])
        with self.assertRaisesRegex(InterimCheckpointError, "immutable approval"):
            wrong_remote.create_and_publish(initial_record(self.approval()))

    def test_publish_then_reload_from_clean_clone(self) -> None:
        approved = initial_record(self.approval())
        created = self.store(self.first).create_and_publish(approved)
        reloaded = self.store(self.second).reload(approved)
        self.assertEqual(reloaded.commit_sha, created.commit_sha)
        self.assertEqual(reloaded.value["approval"]["run_id"], "run-task-413")

    def test_stale_writer_is_refused_without_remote_overwrite(self) -> None:
        first = self.store(self.first)
        approved = initial_record(self.approval())
        original = first.create_and_publish(approved)
        second = self.store(self.second)
        second_current = second.reload(approved)
        updated = dict(second_current.value)
        updated["state"] = {"next_action": "wait-for-verify"}
        second.persist(second_current, updated)
        stale = dict(original.value)
        stale["state"] = {"next_action": "stale-write"}
        with self.assertRaisesRegex(InterimCheckpointError, "moved"):
            first.persist(original, stale)
        self.assertEqual(self.store(self.first).remote_commit(), self.store(self.second).remote_commit())

    def test_ambiguous_publish_reads_back_intended_remote_commit(self) -> None:
        store = self.store(self.first)
        record = initial_record(self.approval())
        original_push = store._store.push

        def pushed_then_ambiguous(*args: object, **kwargs: object) -> None:
            original_push(*args, **kwargs)
            raise RuntimeError("transport response lost")

        with patch.object(store._store, "push", side_effect=pushed_then_ambiguous):
            published = store.create_and_publish(record)
        self.assertTrue(published.reconciled)
        self.assertEqual(store.remote_commit(), published.commit_sha)

    def test_repository_url_change_and_approval_amendment_are_refused(self) -> None:
        approved = initial_record(self.approval())
        store = self.store(self.first)
        original = store.create_and_publish(approved)
        substituted = self.root / "substituted.git"
        self.git("init", "--bare", str(substituted), cwd=self.root)
        self.git("remote", "set-url", "origin", str(substituted), cwd=self.first)
        with self.assertRaisesRegex(InterimCheckpointError, "repository identity"):
            store.persist(original, deepcopy(original.value))
        self.git("remote", "set-url", "origin", str(self.remote), cwd=self.first)
        self.git("remote", "set-url", "--push", "origin", str(substituted), cwd=self.first)
        with self.assertRaisesRegex(InterimCheckpointError, "repository identity"):
            store.persist(original, deepcopy(original.value))
        self.git("remote", "set-url", "--push", "origin", str(self.remote), cwd=self.first)
        changed = deepcopy(original.value)
        changed["approval"]["hard_limits"] = {"dispatch_max": 900}
        changed["approval_digest"] = digest(changed["approval"])
        forged = replace(original, value=changed)
        with self.assertRaisesRegex(InterimCheckpointError, "self-consistent|amendment"):
            store.persist(forged, changed)

    def test_second_pushurl_is_refused_before_either_remote_receives_checkpoint(self) -> None:
        approved = initial_record(self.approval())
        unapproved = self.root / "unapproved.git"
        self.git("init", "--bare", str(unapproved), cwd=self.root)
        self.git("remote", "set-url", "--add", "--push", "origin", str(self.remote), cwd=self.first)
        self.git("remote", "set-url", "--add", "--push", "origin", str(unapproved), cwd=self.first)
        with self.assertRaisesRegex(InterimCheckpointError, "exactly one"):
            self.store(self.first).create_and_publish(approved)
        control_ref = approved["approval"]["checkpoint"]["ref"]
        for remote in (self.remote, unapproved):
            result = subprocess.run(["git", "--git-dir", str(remote), "rev-parse", "--verify", control_ref], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(0, result.returncode)

    def test_documented_cli_validates_preflights_publishes_reloads_and_refuses_readably(self) -> None:
        record = initial_record(self.approval())
        record_path = self.root / "record.json"
        approval_path = self.root / "approval.json"
        record_path.write_bytes(canonical_bytes(record))
        approval_path.write_bytes(canonical_bytes(record["approval"]))
        environment = {**os.environ, "PYTHONPATH": str(PACK / "src")}

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([sys.executable, "-m", "delivery_pilot.interim", *args], cwd=self.root, env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        self.assertIn("advance", run("--help").stdout)
        self.assertEqual(0, run("validate", "--approval", str(approval_path)).returncode)
        preflight_result = run("preflight", "--record", str(record_path), "--slice", "TASK-413")
        self.assertEqual(0, preflight_result.returncode)
        self.assertIn('"worker_dispatch":"unavailable"', preflight_result.stdout)
        self.assertEqual(0, run("publish", "--repository", str(self.first), "--record", str(record_path)).returncode)
        self.assertEqual(0, run("reload", "--repository", str(self.second), "--record", str(record_path)).returncode)
        refusal = run("preflight", "--record", str(self.root / "missing.json"), "--slice", "TASK-413")
        self.assertEqual(2, refusal.returncode)
        self.assertIn("interim refusal:", refusal.stderr)
        missing_repository = run("publish", "--repository", str(self.root / "absent"), "--record", str(record_path))
        self.assertEqual(2, missing_repository.returncode)
        self.assertIn("interim refusal:", missing_repository.stderr)
        self.assertNotIn("Traceback", missing_repository.stderr)

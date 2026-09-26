from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))

from delivery_pilot.canonical import canonical_bytes, digest  # noqa: E402
from test_core import envelope  # noqa: E402

LIFECYCLE_SPEC = importlib.util.spec_from_file_location(
    "v04_delivery_lifecycle", PACK / "scripts/lifecycle.py"
)
LIFECYCLE = importlib.util.module_from_spec(LIFECYCLE_SPEC)
assert LIFECYCLE_SPEC.loader is not None
LIFECYCLE_SPEC.loader.exec_module(LIFECYCLE)


class PackLifecycleTests(unittest.TestCase):
    def run_lifecycle(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(PACK / "scripts" / "lifecycle.py"), *args],
            cwd=PACK.parent,
            text=True,
            capture_output=True,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def test_install_verify_double_install_and_uninstall_preserve_unrelated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            unrelated = project / ".agents" / "skills" / "ai-playbook-deliver" / "user-note.txt"
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text("keep me\n")
            installed = self.run_lifecycle("install", "--project", str(project))
            skill = unrelated.parent / "SKILL.md"
            self.assertTrue(skill.exists())
            self.assertIn("/ai-playbook-deliver", skill.read_text())
            activation = json.loads(installed.stdout)["activation_receipt"]
            self.assertTrue(activation["discoverable"])
            smoke = subprocess.run(
                [sys.executable, str(unrelated.parent / "scripts" / "deliver.py"), "preflight", "--project", str(project)],
                text=True, capture_output=True,
            )
            self.assertEqual(2, smoke.returncode)
            self.assertEqual("blocked", json.loads(smoke.stdout)["outcome"])
            first = (unrelated.parent / "manifest-lock.yml").read_bytes()
            self.run_lifecycle("install", "--project", str(project))
            self.assertEqual(first, (unrelated.parent / "manifest-lock.yml").read_bytes())
            self.run_lifecycle("verify", "--project", str(project))
            self.run_lifecycle("uninstall", "--project", str(project))
            self.assertEqual("keep me\n", unrelated.read_text())
            self.assertFalse(skill.exists())

    def test_partial_install_is_recovered_and_modified_owned_file_blocks_uninstall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            root = project / ".agents" / "skills" / "ai-playbook-deliver"
            root.mkdir(parents=True)
            (root / "install-state.json").write_text(json.dumps({"status": "installing"}))
            self.run_lifecycle("install", "--project", str(project))
            (root / "SKILL.md").write_text("changed by project\n")
            self.run_lifecycle("uninstall", "--project", str(project), expected=2)
            self.assertTrue((root / "SKILL.md").exists())

    def test_uninstall_parent_swap_fails_closed_without_deleting_outside(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            project = workspace / "project"
            project.mkdir()
            LIFECYCLE.install(project)
            outside = workspace / "outside"
            outside.mkdir()
            swapped: dict[str, Path] = {}

            def swap_parent(relative: str) -> None:
                target = project / relative
                parent = target.parent
                detached = parent.with_name(parent.name + "-validated")
                sentinel = outside / target.name
                sentinel.write_text("outside sentinel\n")
                parent.rename(detached)
                parent.symlink_to(outside, target_is_directory=True)
                swapped.update(detached=detached, target=target, sentinel=sentinel)

            with self.assertRaisesRegex(
                LIFECYCLE.LifecycleError,
                "parent is missing, a symlink, or not a directory",
            ):
                LIFECYCLE.uninstall(project, before_unlink=swap_parent)

            self.assertEqual("outside sentinel\n", swapped["sentinel"].read_text())
            self.assertTrue((swapped["detached"] / swapped["target"].name).exists())

    def test_uninstall_requires_exact_current_owned_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            LIFECYCLE.install(project)
            root = project / ".agents/skills/ai-playbook-deliver"
            unowned = root / "project-note.txt"
            unowned.write_text("preserve me\n")
            lock_path = root / "manifest-lock.yml"
            lock = json.loads(lock_path.read_text())
            lock["owned_files"].append({
                "path": "project-note.txt",
                "digest": "sha256:" + hashlib.sha256(unowned.read_bytes()).hexdigest(),
            })
            lock_path.write_bytes(canonical_bytes(lock) + b"\n")

            with self.assertRaisesRegex(
                LIFECYCLE.LifecycleError,
                "does not match the current owned-file registry",
            ):
                LIFECYCLE.uninstall(project)

            self.assertEqual("preserve me\n", unowned.read_text())

    def test_migration_requires_matching_parity_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.run_lifecycle("install", "--project", str(project))
            receipt = project / "parity.json"
            receipt.write_text(json.dumps({"schema_version": 1, "pilot_pack_digest": "wrong", "semantic_parity": True}))
            self.run_lifecycle("migrate", "--project", str(project), "--parity-receipt", str(receipt), expected=2)

    def test_upgrade_replaces_only_verified_owned_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.run_lifecycle("install", "--project", str(project))
            root = project / ".agents" / "skills" / "ai-playbook-deliver"
            unrelated = root / "project-note.txt"
            unrelated.write_text("preserve me\n")
            lock_path = root / "manifest-lock.yml"
            lock = json.loads(lock_path.read_text())
            lock["pack_digest"] = "sha256:" + "1" * 64
            lock_path.write_bytes(canonical_bytes(lock) + b"\n")
            result = self.run_lifecycle("upgrade", "--project", str(project))
            self.assertEqual("upgraded", json.loads(result.stdout)["outcome"])
            self.assertEqual("preserve me\n", unrelated.read_text())
            self.run_lifecycle("verify", "--project", str(project))

            lock = json.loads(lock_path.read_text())
            lock["pack_digest"] = "sha256:" + "2" * 64
            lock_path.write_bytes(canonical_bytes(lock) + b"\n")
            (root / "SKILL.md").write_text("project modification\n")
            blocked = self.run_lifecycle("upgrade", "--project", str(project), expected=2)
            self.assertIn("modified manifest-owned file", blocked.stdout)

    def test_install_refuses_an_unowned_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            skill = project / ".agents" / "skills" / "ai-playbook-deliver" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("pre-existing project skill\n")
            self.run_lifecycle("install", "--project", str(project), expected=2)
            self.assertEqual("pre-existing project skill\n", skill.read_text())

    def test_installed_preflight_accepts_one_nested_approved_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            self.run_lifecycle("install", "--project", str(project))
            planning = project / "planning" / "example"
            planning.mkdir(parents=True)
            observation_contract = {
                "schema_version": 1,
                "contract_id": "observation-contract-1",
                "attempt_id": "attempt-1",
                "mission_id": "mission-1",
                "window_starts_on": "merged_at",
                "window_duration_hours": 24,
                "required_signals": ["real-use-smoke"],
                "raw_evidence_locators": ["github:owner/repo/actions"],
                "defect_classification_route": "tracker:TASK-1",
                "receipt_issuer": "process-attested:linear:TASK-339",
                "declared_at": "2026-08-08T00:00:00Z",
            }
            (planning / "pilot-observation-contract.json").write_bytes(canonical_bytes(observation_contract) + b"\n")
            env = envelope()
            env["observation"]["contract_digest"] = digest(observation_contract)
            (planning / "delivery-envelope.yml").write_bytes(canonical_bytes(env) + b"\n")
            approval = {
                "schema_version": 2,
                "approval_id": "approval-1",
                "envelope_ref": "planning/example/delivery-envelope.yml",
                "envelope_digest": digest(env),
                "actor_id": "human-1",
                "channel": "linear",
                "source_event_id": "event-1",
                "approved_at": "2026-08-08T00:01:00Z",
            }
            (planning / "delivery-approval.json").write_bytes(canonical_bytes(approval) + b"\n")
            result = subprocess.run(
                [sys.executable, str(project / ".agents/skills/ai-playbook-deliver/scripts/deliver.py"), "preflight", "--project", str(project)],
                text=True, capture_output=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual("ready", json.loads(result.stdout)["outcome"])
            self.assertEqual([], list((project / ".agents/skills/ai-playbook-deliver").rglob("__pycache__")))

            skill_root = project / ".agents/skills/ai-playbook-deliver"
            digest_result = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts/deliver.py"),
                    "canonical-digest",
                    "--input", str(planning / "pilot-observation-contract.json"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, digest_result.returncode, digest_result.stdout + digest_result.stderr)
            self.assertEqual(digest(observation_contract), json.loads(digest_result.stdout)["digest"])

            wrapper_env = dict(os.environ, PYTHONPATH=str(skill_root / "runtime"))
            wrapper_result = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts/checker-python.py"),
                    "-c", "import delivery_pilot.canonical; print('safe')",
                ],
                text=True,
                capture_output=True,
                env=wrapper_env,
            )
            self.assertEqual(0, wrapper_result.returncode, wrapper_result.stdout + wrapper_result.stderr)
            self.assertEqual("safe", wrapper_result.stdout.strip())
            self.assertEqual([], list(skill_root.rglob("__pycache__")))

            launcher = json.loads((skill_root / "contracts/generated/examples/launcher.json").read_text())
            launcher_path = planning / "launcher.json"
            launcher_path.write_bytes(canonical_bytes(launcher) + b"\n")
            valid_launcher = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts/deliver.py"),
                    "validate", "--schema", "launcher", "--record", str(launcher_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, valid_launcher.returncode, valid_launcher.stdout + valid_launcher.stderr)
            launcher["execution_policy"]["repository_write_policy"] = "best-effort"
            launcher_path.write_bytes(canonical_bytes(launcher) + b"\n")
            invalid_launcher = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts/deliver.py"),
                    "validate", "--schema", "launcher", "--record", str(launcher_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(2, invalid_launcher.returncode, invalid_launcher.stdout + invalid_launcher.stderr)
            self.assertEqual("blocked", json.loads(invalid_launcher.stdout)["outcome"])

            launcher_v3 = json.loads((skill_root / "contracts/generated/examples/launcher-v3.json").read_text())
            launcher_v3_path = planning / "launcher-v3.json"
            launcher_v3_path.write_bytes(canonical_bytes(launcher_v3) + b"\n")
            for command in (
                ["validate", "--schema", "launcher-v3", "--record", str(launcher_v3_path)],
                ["validate-launcher", "--tier", "A", "--record", str(launcher_v3_path)],
            ):
                result = subprocess.run(
                    [sys.executable, str(skill_root / "scripts/deliver.py"), *command],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual("valid", json.loads(result.stdout)["outcome"])
            for field, value in (
                ("python_bytecode_control", "env-only"),
                ("repository_temp_policy", "inside-checkout"),
                ("repository_write_policy", "best-effort"),
                ("transient_write_monitor", "disabled"),
                ("macos_mach_lookup_allowlist", []),
                ("macos_mach_lookup_allowlist", ["com.apple.FSEvents", "com.apple.unapproved"]),
                ("seatbelt_profile_digest", "not-a-digest"),
            ):
                changed = json.loads(json.dumps(launcher_v3))
                changed["execution_policy"][field] = value
                launcher_v3_path.write_bytes(canonical_bytes(changed) + b"\n")
                for command in (
                    ["validate", "--schema", "launcher-v3", "--record", str(launcher_v3_path)],
                    ["validate-launcher", "--tier", "A", "--record", str(launcher_v3_path)],
                ):
                    result = subprocess.run(
                        [sys.executable, str(skill_root / "scripts/deliver.py"), *command],
                        text=True,
                        capture_output=True,
                    )
                    with self.subTest(field=field, command=command[0]):
                        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                        self.assertEqual("blocked", json.loads(result.stdout)["outcome"])

            launcher_v4 = json.loads((skill_root / "contracts/generated/examples/launcher-v4.json").read_text())
            launcher_v4_path = planning / "launcher-v4.json"
            launcher_v4_path.write_bytes(canonical_bytes(launcher_v4) + b"\n")
            for command in (
                ["validate", "--schema", "launcher-v4", "--record", str(launcher_v4_path)],
                ["validate-launcher", "--tier", "A", "--record", str(launcher_v4_path)],
            ):
                result = subprocess.run(
                    [sys.executable, str(skill_root / "scripts/deliver.py"), *command],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual("valid", json.loads(result.stdout)["outcome"])
            lifecycle = json.loads((skill_root / "contracts/generated/examples/checker-session-lifecycle.json").read_text())
            lifecycle_path = planning / "checker-session-lifecycle.json"
            lifecycle_path.write_bytes(canonical_bytes(lifecycle) + b"\n")
            for command in (
                ["validate", "--schema", "checker-session-lifecycle", "--record", str(lifecycle_path)],
                ["validate-checker-lifecycle", "--launcher", str(launcher_v4_path), "--lifecycle", str(lifecycle_path)],
            ):
                result = subprocess.run(
                    [sys.executable, str(skill_root / "scripts/deliver.py"), *command],
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual("valid", json.loads(result.stdout)["outcome"])
            changed_lifecycle = json.loads(json.dumps(lifecycle))
            changed_lifecycle["last_command_completed_at"] = "2026-08-08T00:01:00Z"
            lifecycle_path.write_bytes(canonical_bytes(changed_lifecycle) + b"\n")
            result = subprocess.run(
                [
                    sys.executable,
                    str(skill_root / "scripts/deliver.py"),
                    "validate-checker-lifecycle",
                    "--launcher",
                    str(launcher_v4_path),
                    "--lifecycle",
                    str(lifecycle_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(2, result.returncode, result.stdout + result.stderr)
            self.assertEqual("blocked", json.loads(result.stdout)["outcome"])
            invalid_v4_records = []
            changed = json.loads(json.dumps(launcher_v4))
            changed["execution_policy"]["repository_write_policy"] = "forbidden"
            invalid_v4_records.append(("policy", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["end_ref"] = "refs/conductor-checkpoints/session-other-turn-t1-end"
            invalid_v4_records.append(("session-ref", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["turn_id"] = "other-turn"
            invalid_v4_records.append(("turn-ref", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["checkout"]["end_index_digest"] = "sha256:" + "1" * 64
            invalid_v4_records.append(("index-drift", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["actor_email"] = "agent@example.com"
            invalid_v4_records.append(("actor", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["start_commit"] = "not-an-object"
            invalid_v4_records.append(("commit", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["end_tree"] = "other-tree"
            invalid_v4_records.append(("checkpoint-tree", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["start_created_at"] = "2026-08-08T00:02:00Z"
            invalid_v4_records.append(("chronology", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["provider_checkpoints"]["extra"] = "forbidden"
            invalid_v4_records.append(("extra-field", changed))
            changed = json.loads(json.dumps(launcher_v4))
            del changed["provider_checkpoints"]["metadata_digest"]
            invalid_v4_records.append(("missing-field", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["candidate"]["tree_sha"] = "other-tree"
            invalid_v4_records.append(("candidate-tree", changed))
            changed = json.loads(json.dumps(launcher_v4))
            changed["termination_state"] = "cancelled"
            invalid_v4_records.append(("termination", changed))
            for label, changed in invalid_v4_records:
                launcher_v4_path.write_bytes(canonical_bytes(changed) + b"\n")
                for command in (
                    ["validate", "--schema", "launcher-v4", "--record", str(launcher_v4_path)],
                    ["validate-launcher", "--tier", "A", "--record", str(launcher_v4_path)],
                ):
                    result = subprocess.run(
                        [sys.executable, str(skill_root / "scripts/deliver.py"), *command],
                        text=True,
                        capture_output=True,
                    )
                    with self.subTest(label=label, command=command[0]):
                        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                        self.assertEqual("blocked", json.loads(result.stdout)["outcome"])
            self.assertTrue((skill_root / "scripts/checker-launcher-v3.py").exists())
            self.assertTrue((skill_root / "scripts/checker-monitor.py").exists())
            self.assertEqual([], list(skill_root.rglob("__pycache__")))

            attempt = {
                "schema_version": 3,
                "attempt_id": observation_contract["attempt_id"],
                "mission_id": observation_contract["mission_id"],
                "feature": "example",
                "project": "sample-project",
                "tier": "A",
                "venue": "local",
                "envelope_digest": digest(env),
                "observation_contract_ref": env["observation"]["contract_ref"],
                "observation_contract_digest": digest(observation_contract),
                "test_manifest_digest": "sha256:" + "1" * 64,
                "registered_at": "2026-08-08T00:02:00Z",
            }
            attempt_path = planning / "pilot-attempt.json"
            attempt_path.write_bytes(canonical_bytes(attempt) + b"\n")
            registration = subprocess.run(
                [
                    sys.executable,
                    str(project / ".agents/skills/ai-playbook-deliver/scripts/deliver.py"),
                    "register-attempt",
                    "--input", str(attempt_path),
                    "--contract", str(planning / "pilot-observation-contract.json"),
                    "--envelope", str(planning / "delivery-envelope.yml"),
                    "--approval", str(planning / "delivery-approval.json"),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, registration.returncode, registration.stdout + registration.stderr)
            self.assertEqual("registered", json.loads(registration.stdout)["outcome"])

            registered_attempt = json.loads(registration.stdout)["receipt"]
            attempt_path.write_bytes(canonical_bytes(registered_attempt) + b"\n")
            host_event = {
                "event": "merged_at",
                "subject_id": "merge-sha",
                "occurred_at": "2026-08-08T01:00:00Z",
                "evidence_locator": "github:owner/repo/commit/merge-sha",
            }
            observation = {
                "schema_version": 4,
                "observation_id": "observation-1",
                "attempt_id": registered_attempt["attempt_id"],
                "observation_contract_digest": digest(observation_contract),
                "merged_sha_or_release_id": "merge-sha",
                "window_started_at": host_event["occurred_at"],
                "window_ended_at": "2026-08-09T01:00:00Z",
                "signals": [{"id": "real-use-smoke", "result": "pass"}],
                "raw_evidence_locators": [
                    "github:owner/repo/actions",
                    host_event["evidence_locator"],
                ],
                "defect_adjudications": [],
                "host_events": [host_event],
                "receipt_issuer": observation_contract["receipt_issuer"],
                "observed_at": "2026-08-09T01:00:00Z",
                "host_proof": {
                    "provider": "github",
                    "event_digest": digest(host_event),
                    "evidence_locator": host_event["evidence_locator"],
                },
            }
            observation_path = planning / "pilot-observation.json"
            observation_path.write_bytes(canonical_bytes(observation) + b"\n")
            validation = subprocess.run(
                [
                    sys.executable,
                    str(project / ".agents/skills/ai-playbook-deliver/scripts/deliver.py"),
                    "validate-observation",
                    "--observation", str(observation_path),
                    "--contract", str(planning / "pilot-observation-contract.json"),
                    "--attempt", str(attempt_path),
                ],
                text=True,
                capture_output=True,
            )
            self.assertEqual(0, validation.returncode, validation.stdout + validation.stderr)
            self.assertEqual("valid", json.loads(validation.stdout)["outcome"])

            env["observation"]["contract_digest"] = "sha256:" + "0" * 64
            (planning / "delivery-envelope.yml").write_bytes(canonical_bytes(env) + b"\n")
            approval["envelope_digest"] = digest(env)
            (planning / "delivery-approval.json").write_bytes(canonical_bytes(approval) + b"\n")
            stale = subprocess.run(
                [sys.executable, str(project / ".agents/skills/ai-playbook-deliver/scripts/deliver.py"), "preflight", "--project", str(project)],
                text=True, capture_output=True,
            )
            self.assertEqual(2, stale.returncode)
            self.assertIn("stale observation contract digest", stale.stdout)


if __name__ == "__main__":
    unittest.main()

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import template_base
from verification_harness_fixture import create

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]


class VerificationHarnessFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.root = create(self.project)
        self.cli = self.project / "fixture-app" / "cli.py"
        self.evidence = self.root / "evidence"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("VERIFY_", "FIXTURE_"))}
        self.env.update(VERIFY_HARNESS_AUTH="fixture-test-authorized",
                        VERIFY_EVIDENCE_DIR=str(self.evidence),
                        PYTHONDONTWRITEBYTECODE="1")

    def run_script(self, path, *args, env=None):
        return subprocess.run([sys.executable, str(path), *args],
                              cwd=self.root, env=self.env if env is None else env,
                              text=True, capture_output=True)

    def doctor(self, expected=0, env=None):
        result = self.run_script(self.root / "doctor.py", env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def drive(self, feature="create-note", expected=0, env=None):
        result = self.run_script(self.root / "drive.py", feature, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        artifact = Path(json.loads(result.stdout)["artifact"])
        self.assertTrue(artifact.is_file())
        return artifact, json.loads(artifact.read_text())

    def test_public_application_commands_persist_and_reject_state(self):
        state = self.project / "notes.json"
        created = self.run_script(self.cli, "--state", str(state), "create", "fixture note")
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(json.loads(state.read_text()), ["fixture note"])
        listed = self.run_script(self.cli, "--state", str(state), "list")
        self.assertEqual(json.loads(listed.stdout), {"notes": ["fixture note"]})
        rejected = self.run_script(self.cli, "--state", str(state), "create", "")
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(json.loads(state.read_text()), ["fixture note"])

    def test_doctor_observes_target_identity_revision_auth_and_readiness_without_repair(self):
        instance = self.cli.with_name("instance.json")
        baseline = instance.read_text()
        self.evidence.mkdir()
        unrelated = self.evidence / ".doctor-probe"
        unrelated.write_text("preserve")
        for field, value in (("instance", "wrong-app"), ("revision", "wrong-build"), ("ready", False)):
            with self.subTest(field=field):
                changed = {**json.loads(baseline), field: value}
                instance.write_text(json.dumps(changed))
                before = instance.read_bytes()
                # Caller assertions cannot make the wrong target pass.
                result = self.doctor(2, {**self.env, "VERIFY_HARNESS_INSTANCE": "fixture-app",
                                        "VERIFY_HARNESS_REVISION": "fixture-app-revision-1"})
                self.assertIn(field, result.stderr)
                self.assertEqual(instance.read_bytes(), before)
                instance.write_text(baseline)
        self.doctor(2, {**self.env, "VERIFY_HARNESS_AUTH": ""})
        ready = self.doctor()
        self.assertTrue(json.loads(ready.stdout)["observed"]["authorized"])
        self.assertEqual(instance.read_text(), baseline)
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertEqual(list(self.evidence.iterdir()), [unrelated])
        self.assertFalse((self.root / ".runs").exists())

    def test_doctor_command_error_and_blocked_evidence_are_distinct(self):
        instance = self.cli.with_name("instance.json")
        baseline = instance.read_text()
        instance.write_text("invalid json")
        self.doctor(1)
        instance.write_text(baseline)
        occupied = self.project / "occupied"
        occupied.write_text("preserve")
        result = self.doctor(2, {**self.env, "VERIFY_EVIDENCE_DIR": str(occupied)})
        self.assertIn("evidence", result.stderr)
        self.assertEqual(occupied.read_text(), "preserve")
        self.cli.unlink()
        self.doctor(2)

    def test_missing_driver_blocks_readiness(self):
        (self.root / "drive.py").unlink()
        self.doctor(2)

    def test_three_mapped_behaviors_observe_real_effects_and_cleanup(self):
        self.doctor()
        expected = {
            "create-note": {"notes": ["fixture note"]},
            "list-notes": {"notes": ["fixture note", "second note"]},
            "reject-broken": {"rejection": {"error": "note must not be empty"},
                              "remaining": {"notes": ["fixture note"]}},
        }
        for feature, effect in expected.items():
            with self.subTest(feature=feature):
                artifact, record = self.drive(feature)
                self.assertEqual(record["effect"], effect)
                self.assertTrue(record["owned_state_removed"])
                self.assertEqual(record["revision"], "fixture-app-revision-1")
                self.assertTrue(record["commands"])
                self.assertIn(artifact.name, (self.root / "features" / f"{feature}.md").read_text())
                self.assertEqual(self.run_script(self.root / "cleanup.py").returncode, 0)
                self.assertTrue(artifact.is_file())
        self.assertFalse((self.root / ".owned-run").exists())
        self.assertEqual(list((self.root / ".runs").iterdir()), [])

    def test_application_fault_fails_behavior_despite_readiness_and_retains_partial_commands(self):
        broken = {**self.env, "FIXTURE_BEHAVIOR_BROKEN": "1"}
        self.doctor(env=broken)
        state = self.project / "fault-notes.json"
        created = self.run_script(self.cli, "--state", str(state), "create", "lost", env=broken)
        self.assertEqual(created.returncode, 0)
        # Observe the fault outside the harness too: create acknowledged a lost write.
        listed = self.run_script(self.cli, "--state", str(state), "list", env=broken)
        self.assertEqual(json.loads(listed.stdout), {"notes": []})
        artifact, record = self.drive(expected=1, env=broken)
        self.assertEqual(record["observation"], "failed")
        self.assertIn("behavior mismatch", record["error"])
        self.assertEqual(json.loads(record["commands"][-1]["stdout"]), {"notes": []})
        self.assertTrue(record["owned_state_removed"])
        self.doctor()  # AC20: recheck readiness, then confirm restored state before continuation.
        self.assertEqual(self.run_script(self.root / "cleanup.py").returncode, 0)
        self.drive()
        self.assertTrue(artifact.is_file())

    def test_repeat_runs_and_intervening_failure_preserve_history_and_refresh_latest_record(self):
        first, first_record = self.drive()
        first_bytes = first.read_bytes()
        entry = self.root / "features" / "create-note.md"
        entry.write_text(entry.read_text() + "\nProject-owned customization survives.\n")
        first_entry = entry.read_bytes()
        failed, failure = self.drive(expected=1, env={**self.env, "FIXTURE_BEHAVIOR_BROKEN": "1"})
        self.assertEqual(entry.read_bytes(), first_entry)
        self.doctor()
        self.assertEqual(self.run_script(self.root / "cleanup.py").returncode, 0)
        second, second_record = self.drive()
        third, third_record = self.drive()
        self.assertEqual(len({first.name, failed.name, second.name, third.name}), 4)
        self.assertEqual(first.read_bytes(), first_bytes)
        self.assertEqual(json.loads(failed.read_text())["observation"], "failed")
        self.assertNotEqual(first_record["run_id"], second_record["run_id"])
        self.assertIn(third_record["run_id"], entry.read_text())
        self.assertNotIn(second_record["run_id"], entry.read_text())
        self.assertIn("Project-owned customization survives.", entry.read_text())
        self.assertEqual(entry.read_text().count("**Last verification:**"), 1)
        match = re.search(r"\[run artifact\]\((.+)\)", entry.read_text())
        self.assertEqual((entry.parent / match.group(1)).resolve(), third)
        self.assertEqual(len(list(self.evidence.glob("*.json"))), 4)

    def test_unknown_owned_resources_and_unrelated_files_are_preserved(self):
        marker = self.root / ".owned-run"
        marker.write_text("not this run")
        unrelated = self.project / "unrelated-resource.txt"
        unrelated.write_text("preserve")
        artifact, record = self.drive(expected=1)
        self.assertEqual(marker.read_text(), "not this run")
        self.assertEqual(unrelated.read_text(), "preserve")
        self.assertEqual(self.run_script(self.root / "cleanup.py").returncode, 2)
        self.assertTrue(artifact.is_file())
        self.assertEqual(record["observation"], "failed")

    def test_map_write_failure_cleans_owned_state_and_retains_failure(self):
        entry = self.root / "features" / "create-note.md"
        entry.unlink()
        entry.mkdir()  # Operational failure after application behavior succeeds.
        artifact, record = self.drive(expected=1)
        self.assertIn("map update failed", record["error"])
        self.assertTrue(record["owned_state_removed"])
        self.assertTrue(entry.is_dir())
        self.assertEqual(self.run_script(self.root / "cleanup.py").returncode, 0)
        self.assertEqual(json.loads(artifact.read_text())["observation"], "failed")

    def test_help_bad_arguments_and_missing_evidence(self):
        for script in ("doctor.py", "drive.py", "cleanup.py"):
            self.assertEqual(self.run_script(self.root / script, "--help").returncode, 0)
            self.assertEqual(self.run_script(self.root / script, "unexpected").returncode, 1)
        env = {key: value for key, value in self.env.items() if key != "VERIFY_EVIDENCE_DIR"}
        result = self.run_script(self.root / "drive.py", "create-note", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("VERIFY_EVIDENCE_DIR", result.stderr)
        self.doctor(2, env)

    def test_conflict_preflight_preserves_all_existing_files_and_safe_names(self):
        before = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        create(self.project)  # Unchanged generation converges.
        self.assertEqual(before, {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()})
        skill = self.root / "SKILL.md"
        skill.write_text("custom")
        before = {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(ValueError, "customized"):
            create(self.project)
        self.assertEqual(before, {path: path.read_bytes() for path in self.project.rglob("*") if path.is_file()})
        with self.assertRaisesRegex(ValueError, "safe lowercase"):
            create(self.project, "../outside")

    def test_generated_launch_and_drive_instructions_execute_from_project_root(self):
        root = create(self.project, "other-fixture")
        skill = (root / "SKILL.md").read_text()
        launch = re.search(r"```bash\n(.*?)```", skill, flags=re.S).group(1)
        result = subprocess.run(
            ["bash", "-c", launch + "\npython3 doctor.py && python3 drive.py create-note && python3 cleanup.py"],
            cwd=self.project, env=self.env, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifacts = list((root / "evidence").glob("*.json"))
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(json.loads(artifacts[0].read_text())["instance"], "other-fixture")

    def assert_installed_maintenance_authority_links(self):
        skill = self.project / ".agents/skills/ai-playbook-maintain-verification-harness/SKILL.md"
        links = dict(re.findall(r"\[([^]]+)\]\(([^)]+)\)", skill.read_text()))
        for label, relative in (
            ("stage-08 review", "10-process/08-review.md"),
            ("stage-09 QA", "10-process/09-qa.md"),
            ("the document lifecycle", "30-document-lifecycle.md"),
        ):
            with self.subTest(authority=label):
                resolved = (skill.parent / links[label]).resolve()
                self.assertEqual(resolved, REPO / "v0.5" / relative)
                self.assertTrue(resolved.is_file(), resolved)

    def test_actual_twice_bootstrap_and_upgrade_preserve_custom_generated_harness(self):
        bootstrap = [
            sys.executable, str(SCRIPTS / "bootstrap-project.py"), str(self.project),
            "--playbook-path", str(REPO), "--project-name", "Controlled Fixture",
            "--ui", "no", "--ci", "copy", "--apply",
        ]
        for attempt in range(2):
            if attempt == 1:
                skill = self.root / "SKILL.md"
                skill.write_text(skill.read_text() + "\nCustom project instructions.\n")
                helper = self.root / "drive.py"
                helper.write_text(helper.read_text() + "\n# Project customization.\n")
                cadence = self.project / "playbook-cadences.yml"
                original_cadence = cadence.read_text()
                tuned_cadence = original_cadence.replace("nudge_threshold: 7", "nudge_threshold: 9")
                self.assertNotEqual(original_cadence, tuned_cadence)
                cadence.write_text(tuned_cadence)
                cadence_bytes = cadence.read_bytes()
                self.drive()
            before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
            result = subprocess.run(bootstrap, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_installed_maintenance_authority_links()
            self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        installed = self.project / ".agents" / "skills" / "ai-playbook-verification-harness" / "SKILL.md"
        self.assertEqual(installed.read_bytes(),
                         (REPO / "v0.5" / "skills" / "ai-playbook-verification-harness" / "SKILL.md").read_bytes())
        maintenance = self.project / ".agents" / "skills" / "ai-playbook-maintain-verification-harness" / "SKILL.md"
        self.assertEqual(maintenance.read_text(),
                         (REPO / "v0.5" / "skills" / "ai-playbook-maintain-verification-harness" / "SKILL.md")
                         .read_text().replace("{playbook-path}", str(REPO)))
        # Model the previously distributed relative-link version and its pristine
        # base in this disposable consumer, so upgrade must actually refresh it.
        relative = str(maintenance.relative_to(self.project))
        legacy = maintenance.read_text().replace(str(REPO / "v0.5") + "/", "../../")
        maintenance.write_text(legacy)
        (self.project / template_base.BASE_DIR / relative).write_text(legacy)
        state_path = self.project / ".playbook-state.yml"
        state = state_path.read_text()
        provenance = template_base.read_provenance(state)
        entry = provenance["files"][relative]
        provenance["files"][relative] = template_base.provenance_entry(
            entry["template"], entry["version"], legacy)
        state_path.write_text(template_base.upsert_provenance(state, provenance))
        for attempt in range(2):
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "upgrade-project.py"), str(self.project), "--apply-safe"],
                text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assert_installed_maintenance_authority_links()
            self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
            self.assertEqual(cadence.read_bytes(), cadence_bytes)
        # The customized driver still works after real distribution.
        self.doctor()
        self.drive("list-notes")


if __name__ == "__main__":
    unittest.main()

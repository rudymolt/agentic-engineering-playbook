"""Public bootstrap/upgrade and Git visibility of retained Apply evidence."""

import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest

from playbook_config import Configuration
import test_public_upgrade_transition as transition


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "v0.5" / "scripts"
NOW = "2026-10-08T12:00:00Z"


def discover(request):
    return {"request_id": request["request_id"], "checked_at": request["started_at"],
            "authority": "host-reported-selection", "revision": "test-fixture",
            "routes": [
                {"model_id": "gpt-6.1-sol", "runner": "codex", "reasoning": "high", "roles": ["planning", "verification"]},
                {"model_id": "gpt-6.1-sol", "runner": "codex", "reasoning": "medium", "roles": ["implementation"]},
                {"model_id": "gpt-6-astra", "runner": "codex", "reasoning": "high", "roles": ["escalated_repair"]},
                {"model_id": "fixture-plan", "runner": "codex", "reasoning": "high", "roles": ["planning"]},
                {"model_id": "fixture-build", "runner": "codex", "reasoning": "medium", "roles": ["implementation"]},
            ]}


class ApplyRecoveryGitignoreTests(unittest.TestCase):
    def bootstrap(self, project, apply=True, playbook_root=ROOT):
        command = [sys.executable, str(SCRIPTS / "bootstrap-project.py"), str(project),
                   "--playbook-path", str(playbook_root), "--project-name", "Example Project",
                   "--ui", "no", "--ci", "copy"]
        if apply:
            command.append("--apply")
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def git(self, project, *args):
        return subprocess.run(["git", "-C", str(project), *args],
                              capture_output=True, text=True, check=False)

    def artifacts(self, project):
        return {path.name: path.read_bytes() if path.is_file() else None
                for path in project.glob(".playbook-config-*")}

    def assert_visibility(self, project):
        artifacts = self.artifacts(project)
        self.assertTrue(artifacts)
        self.assertTrue(any(name.endswith(".receipt") for name in artifacts))
        for name in artifacts:
            self.assertEqual(self.git(project, "check-ignore", "-q", name).returncode, 0, name)
        for name in (".playbook-config.json", ".playbook-config.lock",
                     ".playbook-config.recovery", ".playbook-config.pair",
                     "unrelated.receipt", "unrelated.receipt.complete/proof",
                     "nested/.playbook-config-evidence"):
            self.assertEqual(self.git(project, "check-ignore", "-q", name).returncode, 1, name)
        self.assertEqual(self.git(project, "add", ".playbook-config.json").returncode, 0)
        self.assertEqual(self.git(project, "ls-files", "--", ".playbook-config.json").stdout.strip(),
                         ".playbook-config.json")

    def edit(self, service, label, role, model):
        editor = service.reply(service.read(), "Edit " + label)
        choices = editor["role_alternatives"][role]
        index = next(i for i, choice in enumerate(choices) if choice["model_id"] == model)
        return service.reply(editor, str(index + 1))

    def test_bootstrap_and_old_project_upgrade_hide_real_apply_evidence(self):
        for mode in ("bootstrap", "upgrade"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                if mode == "bootstrap":
                    project = Path(tmp) / "project"
                    project.mkdir()
                    result = self.bootstrap(project)
                else:
                    project, _ = transition.PublicTransitionTest().fixture(Path(tmp))
                    (project / ".gitignore").write_text(".playbook-routing/\n")
                if mode == "bootstrap":
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("manual review:", result.stdout)
                self.assertEqual(self.git(project, "init", "-q").returncode, 0)
                service = Configuration(project, discover, lambda: NOW)
                self.assertEqual(service.reply(service.read(), "Apply")["state"], "applied")
                self.assertEqual(service.read()["state"], "decision_required")
                self.assertEqual(service.reply(self.edit(service, "Plan", "planning", "fixture-plan"),
                                              "Apply")["state"], "applied")
                self.assertEqual(service.resolve("planning")["choice"]["model_id"], "fixture-plan")
                artifacts = self.artifacts(project)
                self.assertEqual(sum(name.endswith(".receipt.complete") for name in artifacts), 2)
                receipts = [json.loads(data) for name, data in artifacts.items() if name.endswith(".receipt")]
                self.assertTrue(any(receipt["previous"] is not None for receipt in receipts))
                if mode == "upgrade":
                    # Migrate an old project that already holds successful Apply evidence.
                    saved = (project / ".playbook-config.json").read_bytes()
                    result = transition.PublicTransitionTest().run_upgrade(project)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn("manual review:", result.stdout)
                    self.assertEqual((project / ".playbook-config.json").read_bytes(), saved)
                    self.assertEqual(self.artifacts(project), artifacts)
                    self.assertEqual(service.read()["state"], "decision_required")
                self.assert_visibility(project)
                # Managed updates must leave all retained evidence intact, including seals.
                update = self.bootstrap(project) if mode == "bootstrap" else transition.PublicTransitionTest().run_upgrade(project)
                self.assertEqual(update.returncode, 0, update.stderr)
                self.assertEqual(self.artifacts(project), artifacts)
                before = transition.PublicTransitionTest.snapshot(project)
                repeat = self.bootstrap(project) if mode == "bootstrap" else transition.PublicTransitionTest().run_upgrade(project)
                self.assertEqual(repeat.returncode, 0, repeat.stderr)
                self.assertEqual(transition.PublicTransitionTest.snapshot(project), before)
                # Exercise completion conflict and receipt reconciliation with ignores installed.
                external = (project / ".playbook-config.json").read_bytes()
                def conflict(point):
                    if point == "before_completion":
                        (project / ".playbook-config.json").write_bytes(external)
                service.checkpoint = conflict
                result = service.reply(self.edit(service, "Build", "implementation", "fixture-build"), "Apply")
                self.assertEqual(result["state"], "recovery_required")
                self.assertEqual((project / ".playbook-config.json").read_bytes(), external)
                self.assertTrue(list(project.glob(".playbook-config-*.receipt.conflict")))
                self.assert_visibility(project)
                (project / ".playbook-config.lock").unlink()
                (project / ".playbook-config.recovery").unlink()
                retained = self.artifacts(project)
                self.assertEqual(Configuration(project, discover, lambda: NOW).read()["state"], "recovery_required")
                self.assertEqual(self.artifacts(project), retained)

    def test_managed_entries_preserve_user_bytes_and_are_idempotent(self):
        for mode in ("bootstrap", "upgrade"):
            for original in (b"# user rules  \ncustom/", b"# user rules\n.playbook-routing/\n\n  \n",
                             b"/.playbook-config-*\ncustom/", b"custom/\n.playbook-routing/\n/.playbook-config-*",
                             b"", b"  ", b"# user rules\r\ncustom/\r\n"):
                with self.subTest(mode=mode, original=original), tempfile.TemporaryDirectory() as tmp:
                    if mode == "bootstrap":
                        project = Path(tmp) / "project"
                        project.mkdir()
                        run = self.bootstrap
                    else:
                        project, _ = transition.PublicTransitionTest().fixture(Path(tmp))
                        run = transition.PublicTransitionTest().run_upgrade
                    ignore = project / ".gitignore"
                    ignore.write_bytes(original)
                    result = run(project)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    entries = original.splitlines()
                    missing = [rule for rule in (b".playbook-routing/", b"/.playbook-config-*") if rule not in entries]
                    expected = original
                    if missing:
                        expected += (b"\n" if original and not original.endswith(b"\n") else b"")
                        expected += b"\n".join(missing) + b"\n"
                    self.assertEqual(ignore.read_bytes(), expected)
                    before = transition.PublicTransitionTest.snapshot(project)
                    repeated = run(project)
                    self.assertEqual(repeated.returncode, 0, repeated.stderr)
                    self.assertNotIn("changed: " + str(ignore), repeated.stdout)
                    self.assertEqual(transition.PublicTransitionTest.snapshot(project), before)

    def test_bootstrap_preview_reports_each_managed_rule_without_writes(self):
        for original, routing, recovery in (
            (b"custom/", "add .playbook-routing/", "add /.playbook-config-*"),
            (b".playbook-routing/\n", ".playbook-routing/ already ignored", "add /.playbook-config-*"),
            (b"/.playbook-config-*\n", "add .playbook-routing/", "/.playbook-config-* already ignored"),
            (b".playbook-routing/\n/.playbook-config-*", ".playbook-routing/ already ignored", "/.playbook-config-* already ignored"),
        ):
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                (project / ".gitignore").write_bytes(original)
                before = transition.PublicTransitionTest.snapshot(project)
                result = self.bootstrap(project, apply=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Gitignore: " + routing, result.stdout)
                self.assertIn("Gitignore: " + recovery, result.stdout)
                self.assertEqual(transition.PublicTransitionTest.snapshot(project), before)

    def test_upgrade_without_apply_safe_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = transition.PublicTransitionTest().fixture(Path(tmp))
            before = transition.PublicTransitionTest.snapshot(project)
            result = subprocess.run([sys.executable, str(SCRIPTS / "upgrade-project.py"), str(project)],
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("no changes made", result.stderr)
            self.assertEqual(transition.PublicTransitionTest.snapshot(project), before)

    def test_git_rule_boundaries_do_not_split_user_comments(self):
        for mode in ("bootstrap", "upgrade"):
            for separator in ("\r", "\v", "\u0085", "\u2028"):
                with self.subTest(mode=mode, separator=separator), tempfile.TemporaryDirectory() as tmp:
                    if mode == "bootstrap":
                        project = Path(tmp) / "project"
                        project.mkdir()
                        run = self.bootstrap
                    else:
                        project, _ = transition.PublicTransitionTest().fixture(Path(tmp))
                        run = transition.PublicTransitionTest().run_upgrade
                    original = ("# user note" + separator + ".playbook-routing/\n"
                                "# user note" + separator + "/.playbook-config-*\n").encode()
                    ignore = project / ".gitignore"
                    ignore.write_bytes(original)
                    if mode == "bootstrap":
                        preview = self.bootstrap(project, apply=False)
                        self.assertIn("Gitignore: add .playbook-routing/", preview.stdout)
                        self.assertIn("Gitignore: add /.playbook-config-*", preview.stdout)
                        self.assertEqual(ignore.read_bytes(), original)
                    result = run(project)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(ignore.read_bytes(), original + b".playbook-routing/\n/.playbook-config-*\n")
                    self.assertEqual(self.git(project, "init", "-q").returncode, 0)
                    self.assertEqual(self.git(project, "check-ignore", "-q", ".playbook-config-evidence").returncode, 0)
                    self.assertEqual(self.git(project, "check-ignore", "-q", ".playbook-routing/evidence").returncode, 0)
                    repeated = run(project)
                    self.assertEqual(repeated.returncode, 0, repeated.stderr)
                    self.assertNotIn("changed: " + str(ignore), repeated.stdout)
                    self.assertEqual(ignore.read_bytes(), original + b".playbook-routing/\n/.playbook-config-*\n")

    def test_ignore_repeat_is_unchanged_when_unrelated_skill_bytecode_appears(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            shutil.copytree(ROOT / "v0.5", source / "v0.5",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            project = root / "project"
            first = self.bootstrap(project, playbook_root=source)
            self.assertEqual(first.returncode, 0, first.stderr)
            ignore = project / ".gitignore"
            before = (ignore.read_bytes(), ignore.stat().st_mtime_ns)
            # Another verification shard can create this cache between public calls.
            py_compile.compile(str(source / "v0.5/skills/ship-release/scripts/check-release-state.py"),
                               doraise=True)
            repeated = self.bootstrap(project, playbook_root=source)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertNotIn("changed: " + str(ignore), repeated.stdout)
            self.assertEqual((ignore.read_bytes(), ignore.stat().st_mtime_ns), before)


if __name__ == "__main__":
    unittest.main()

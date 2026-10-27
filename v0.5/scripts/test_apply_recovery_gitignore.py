"""Public bootstrap/upgrade and Git visibility of retained Apply evidence."""

import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import time
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
    def bootstrap(self, project, apply=True, playbook_root=ROOT, environment=None):
        command = [sys.executable, str(playbook_root / "v0.5/scripts/bootstrap-project.py"), str(project),
                   "--playbook-path", str(playbook_root), "--project-name", "Example Project",
                   "--ui", "no", "--ci", "copy"]
        if apply:
            command.append("--apply")
        return subprocess.run(command, capture_output=True, text=True, check=False,
                              env=environment, timeout=45)

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
            home = root / 'home'
            home.mkdir()
            environment = {**os.environ, 'HOME': str(home), 'GIT_CONFIG_NOSYSTEM': '1',
                           'GIT_CONFIG_GLOBAL': os.devnull}
            for variable in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX'):
                environment.pop(variable, None)
            first = self.bootstrap(project, playbook_root=source, environment=environment)
            self.assertEqual(first.returncode, 0, first.stderr)
            ignore = project / ".gitignore"
            before = (ignore.read_bytes(), ignore.stat().st_mtime_ns)
            whole_project = {p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                             for p in project.rglob('*') if p.is_file()}
            unchanged = self.bootstrap(project, playbook_root=source, environment=environment)
            self.assertEqual(unchanged.returncode, 0, unchanged.stdout + unchanged.stderr)
            self.assertEqual({p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                              for p in project.rglob('*') if p.is_file()}, whole_project)
            # Another verification shard can create this cache between public calls.
            py_compile.compile(str(source / "v0.5/skills/ship-release/scripts/check-release-state.py"),
                               doraise=True)
            time.sleep(1.1)  # State recomputation must not hide within the same clock tick.
            repeated = self.bootstrap(project, playbook_root=source, environment=environment)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertNotIn("changed: " + str(ignore), repeated.stdout)
            self.assertEqual((ignore.read_bytes(), ignore.stat().st_mtime_ns), before)
            after = {p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                     for p in project.rglob('*') if p.is_file()}
            differences = {str(name): ['bytes', 'mode', 'mtime'][index]
                           for name in set(after) & set(whole_project)
                           for index in range(3) if after[name][index] != whole_project[name][index]}
            self.maxDiff = 300
            self.assertEqual(after, whole_project, repr(differences))


    def test_pending_delivery_marker_blocks_until_explicit_supported_repair(self):
        for with_lock in (True, False):
            with self.subTest(with_lock=with_lock), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, project, home = root / 'source', root / 'project', root / 'home'
                home.mkdir()
                shutil.copytree(ROOT / 'v0.5', source / 'v0.5',
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                environment = {**os.environ, 'HOME': str(home), 'GIT_CONFIG_NOSYSTEM': '1',
                               'GIT_CONFIG_GLOBAL': os.devnull}
                first = self.bootstrap(project, playbook_root=source, environment=environment)
                self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
                delivery = project / '.agents/skills/ai-playbook-deliver'
                lock = delivery / 'manifest-lock.yml'
                manifest = json.loads(lock.read_text())
                pending = delivery / 'install-state.json'
                pending.write_text(json.dumps({'status': 'installing', 'pack_digest': manifest['pack_digest']}))
                if not with_lock:
                    lock.unlink()
                state = project / '.playbook-state.yml'
                state.write_text(state.read_text().replace('playbook_version: V0.5.0', 'playbook_version: null'))
                before = {p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                          for p in project.rglob('*') if p.is_file()}
                blocked = self.bootstrap(project, playbook_root=source, environment=environment)
                self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
                self.assertIn('install-state.json', blocked.stdout)
                self.assertIn('playbook_version: null', state.read_text())
                self.assertEqual({p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                                  for p in project.rglob('*') if p.is_file()}, before)
                repair = subprocess.run([sys.executable, str(source / 'v0.5/delivery/scripts/lifecycle.py'),
                                         'install', '--project', str(project)], env=environment,
                                        capture_output=True, text=True, timeout=45)
                self.assertEqual(repair.returncode, 0, repair.stdout + repair.stderr)
                self.assertFalse(pending.exists())
                completed = self.bootstrap(project, playbook_root=source, environment=environment)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                repaired = {p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                            for p in project.rglob('*') if p.is_file()}
                repeated = self.bootstrap(project, playbook_root=source, environment=environment)
                self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
                self.assertEqual({p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                                  for p in project.rglob('*') if p.is_file()}, repaired)


    def test_delivery_verification_refuses_drift_without_touching_consumer_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, original, home = root / 'source', root / 'original', root / 'home'
            home.mkdir()
            shutil.copytree(ROOT / 'v0.5', source / 'v0.5',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            environment = {**os.environ, 'HOME': str(home), 'GIT_CONFIG_NOSYSTEM': '1',
                           'GIT_CONFIG_GLOBAL': os.devnull}
            first = self.bootstrap(original, playbook_root=source, environment=environment)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            for case in ('edited', 'partial', 'stale', 'owned-registry', 'source-manifest'):
                with self.subTest(case=case):
                    project = root / case
                    shutil.copytree(original, project)
                    delivery = project / '.agents/skills/ai-playbook-deliver'
                    (delivery / 'user-owned.txt').write_text('Preserve this unrelated content\n')
                    lock = delivery / 'manifest-lock.yml'
                    if case == 'edited':
                        skill = delivery / 'SKILL.md'
                        skill.write_bytes(skill.read_bytes() + b'\nProject-owned delivery edit\n')
                        expected = 'installed file mismatch'
                    elif case == 'partial':
                        (delivery / 'agents/openai.yaml').unlink()
                        expected = 'installed file mismatch'
                    elif case in ('stale', 'owned-registry'):
                        record = json.loads(lock.read_text())
                        if case == 'stale':
                            record['pack_digest'] = 'sha256:' + '0' * 64
                            expected = 'installed pack digest is stale'
                        else:
                            record['owned_files'].pop()
                            expected = 'owned-file registry'
                        lock.write_text(json.dumps(record))
                    else:
                        material = source / 'v0.5/delivery/src/delivery_pilot/canonical.py'
                        material.write_bytes(material.read_bytes() + b'\n# Fixture source drift\n')
                        expected = 'source manifest mismatch'
                    before = {p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                              for p in project.rglob('*') if p.is_file()}
                    blocked = self.bootstrap(project, playbook_root=source, environment=environment)
                    self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
                    self.assertIn('delivery verify blocked', blocked.stdout)
                    self.assertIn(expected, blocked.stdout)
                    self.assertEqual({p.relative_to(project): (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
                                      for p in project.rglob('*') if p.is_file()}, before)


if __name__ == "__main__":
    unittest.main()

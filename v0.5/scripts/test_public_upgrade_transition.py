from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
import template_base  # noqa: E402


class PublicTransitionTest(unittest.TestCase):
    def fixture(self, directory: Path) -> tuple[Path, Path]:
        project = directory / "project"
        project.mkdir()
        old_root = directory / "old-playbook"
        templates = ROOT / "v0.5" / "templates"
        for name in (".playbook-state.yml", "playbook-cadences.yml"):
            text = template_base.render((templates / name).read_text(), old_root, "Example Project")
            text = text.replace("/v0.5/", "/v0.4/")
            if name == ".playbook-state.yml":
                text = text.replace("playbook_version: null", "playbook_version: V0.4.2", 1)
                text = re.sub(r"(?m)^playbook_release(?:_[a-z_]+)?:.*\n", "", text)
            (project / name).write_text(text)
        bases = {
            "CLAUDE.md": f"The full playbook V0.4 is at `{old_root}/v0.4/`.\n",
            "AGENTS.md": f"Read `{old_root}/v0.4/AGENT-DIGEST.md` first.\n",
        }
        record = {"schema": 1, "project_name": "Example Project", "files": {}}
        for name, text in bases.items():
            (project / name).write_text(text)
            base = project / ".playbook-base" / name
            base.parent.mkdir(parents=True, exist_ok=True)
            base.write_text(text)
            record["files"][name] = template_base.provenance_entry(
                f"v0.4/templates/{name}", "V0.4.2", text
            )
        state = project / ".playbook-state.yml"
        state.write_text(template_base.upsert_provenance(state.read_text(), record))
        return project, old_root

    def run_upgrade(self, project: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "upgrade-project.py"), str(project), "--apply-safe"],
            check=False, capture_output=True, text=True,
        )

    @staticmethod
    def snapshot(project: Path) -> dict[str, str]:
        return {
            str(path.relative_to(project)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in project.rglob("*") if path.is_file() and "__pycache__" not in path.parts
        }

    def bootstrap(self, project: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "bootstrap-project.py"), str(project),
             "--playbook-path", str(ROOT), "--project-name", "Example Project",
             "--ui", "no", "--ci", "copy", "--apply"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pristine_bootstrap_installs_checkpoint_estimates_and_replays(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.bootstrap(project)
            governance = (project / "CLAUDE.md").read_text()
            self.assertIn("250 aggregate tool calls per substantive slice", governance)
            self.assertIn("separate 300-call estimate for broad final verification", governance)
            self.assertIn("300-minute multi-slice forecast", governance)
            self.assertIn("neither ceilings nor minimum consumption targets", governance)
            self.assertIn("max-retry: 3", governance)
            self.assertIn("no-progress halt: 3", governance)
            before = self.snapshot(project)
            self.bootstrap(project)
            self.assertEqual(before, self.snapshot(project))
            upgraded = self.run_upgrade(project)
            self.assertEqual(upgraded.returncode, 0, upgraded.stdout + upgraded.stderr)
            self.assertEqual(before, self.snapshot(project))

    def test_bootstrap_preserves_existing_budget_instructions_and_withholds_stamp(self):
        for rule in ("Hard cap: 60 calls; stop at 60.", "Budget: 60 calls."):
            with self.subTest(rule=rule), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / "project"
                project.mkdir()
                claude = project / "CLAUDE.md"
                claude.write_text("# Project instructions\n\n" + rule + "\n")
                original = claude.read_bytes()
                command = [sys.executable, str(SCRIPT_DIR / "bootstrap-project.py"), str(project),
                           "--playbook-path", str(ROOT), "--project-name", "Example Project",
                           "--ui", "no", "--ci", "copy"]
                before = self.snapshot(project)
                preview = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
                self.assertEqual(before, self.snapshot(project))
                applied = subprocess.run(command + ["--apply"], capture_output=True, text=True)
                self.assertEqual(applied.returncode, 2, applied.stdout + applied.stderr)
                self.assertRegex(applied.stdout, r"manual review: .*CLAUDE\.md: preserve existing content")
                self.assertEqual(original, claude.read_bytes())
                self.assertIn("playbook_version: null", (project / ".playbook-state.yml").read_text())

    def checkpoint_fixture(self, project: Path, rule: str | None = None) -> None:
        """A recorded older template plus an optional project-owned override."""
        self.bootstrap(project)
        claude = project / "CLAUDE.md"
        current = claude.read_text()
        old_line = "    - productive-work budget: estimate from the verification plan before the run; for browser-heavy UI work, start near 60 tool calls and tune from evidence"
        base = re.sub(r"(?m)^    - productive-work estimate:.*$", old_line, current)
        self.assertNotEqual(base, current)
        (project / ".playbook-base" / "CLAUDE.md").write_text(base)
        claude.write_text((base if rule is None else base.replace(old_line, "    - " + rule))
                          + "\nProject rule: preserve release notes.\n")
        state_path = project / ".playbook-state.yml"
        state = state_path.read_text()
        record = template_base.read_provenance(state)
        record["files"]["CLAUDE.md"] = template_base.provenance_entry(
            "v0.5/templates/CLAUDE.md", "V0.5.0", base
        )
        state = template_base.upsert_provenance(state, record)
        state = state.replace("playbook_release: null", "playbook_release: v0.5.1")
        state = state.replace("playbook_release_tag_object: null", 'playbook_release_tag_object: "' + "1" * 40 + '"')
        state = state.replace("playbook_release_commit: null", 'playbook_release_commit: "' + "2" * 40 + '"')
        state_path.write_text(state)

    def test_inherited_estimate_upgrades_through_public_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            self.checkpoint_fixture(project)
            claude = project / "CLAUDE.md"
            result = self.run_upgrade(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("250 aggregate tool calls", claude.read_text())
            self.assertIn("Project rule: preserve release notes.", claude.read_text())
            before = self.snapshot(project)
            result = self.run_upgrade(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(before, self.snapshot(project))

    def test_hard_stop_and_ambiguous_customizations_require_review_then_replay(self):
        for rule, retain in (
            ("hard cap: 60 tool calls; stop and ask for extension at 60.", True),
            ("budget: 60 tool calls; stop when exhausted.", False),
        ):
            with self.subTest(rule=rule), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / "project"
                self.checkpoint_fixture(project, rule)
                before = self.snapshot(project)
                preview = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "upgrade-project.py"), str(project), "--plan"],
                    capture_output=True, text=True,
                )
                self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
                self.assertEqual(before, self.snapshot(project))
                claude = project / "CLAUDE.md"
                original = claude.read_bytes()
                result = self.run_upgrade(project)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn("CLAUDE.md: template change conflicts", result.stdout)
                self.assertEqual(original, claude.read_bytes())
                state = (project / ".playbook-state.yml").read_text()
                self.assertIn("playbook_version: V0.5.0", state)
                self.assertIn("playbook_release: v0.5.1", state)
                self.assertIn('playbook_release_tag_object: "' + "1" * 40 + '"', state)
                self.assertIn('playbook_release_commit: "' + "2" * 40 + '"', state)
                # This fixture represents the owner's reviewed choice, not an
                # automatic interpretation of project prose by the helper.
                if retain:
                    claude.write_text(claude.read_text().replace(rule, "Owner deliberately retains " + rule))
                else:
                    claude.write_text(claude.read_text().replace(
                        rule, "ordinary estimate: 250 calls per substantive slice; separate 300 calls "
                        "for broad final verification; productive authorized work continues."
                    ) + "\nOwner reviewed conversion to ordinary estimates.\n")
                accepted = claude.read_bytes()
                adopted = subprocess.run(
                    [sys.executable, str(SCRIPT_DIR / "upgrade-project.py"), str(project),
                     "--apply-safe", "--adopt-current", "CLAUDE.md"],
                    capture_output=True, text=True,
                )
                self.assertEqual(adopted.returncode, 0, adopted.stdout + adopted.stderr)
                self.assertEqual(accepted, claude.read_bytes())
                self.assertIn("Project rule: preserve release notes.", claude.read_text())
                self.assertIn("max-retry: 3", claude.read_text())
                self.assertIn("no-progress halt: 3", claude.read_text())
                before = self.snapshot(project)
                replay = self.run_upgrade(project)
                self.assertEqual(replay.returncode, 0, replay.stdout + replay.stderr)
                self.assertEqual(before, self.snapshot(project))

    def test_retargets_old_checkout_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, old_root = self.fixture(Path(tmp))
            first = self.run_upgrade(project)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertNotIn("manual review:", first.stdout)
            state = (project / ".playbook-state.yml").read_text()
            self.assertIn("playbook_version: V0.5.0", state)
            self.assertIn("playbook_release: null", state)
            self.assertIn("playbook_release_tag_object: null", state)
            self.assertIn("playbook_release_commit: null", state)
            for name in ("CLAUDE.md", "AGENTS.md", ".playbook-state.yml", "playbook-cadences.yml"):
                text = (project / name).read_text()
                self.assertNotIn(str(old_root), text, name)
                self.assertIn(str(ROOT), text, name)
            before = self.snapshot(project)
            second = self.run_upgrade(project)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(before, self.snapshot(project))

    def test_helper_preserves_custom_defaults_and_retained_sibling(self):
        from test_bootstrap_project import upgrade_project

        with tempfile.TemporaryDirectory() as tmp:
            project, _ = self.fixture(Path(tmp))
            state_path = project / ".playbook-state.yml"
            custom = upgrade_project.PRE_V061_MODEL_DEFAULTS.replace("runner: codex", "runner: opencode", 1)
            sibling = "  # Retain this unrelated routing map\n  retained_defaults:\n" + upgrade_project.PRE_V061_MODEL_DEFAULTS + "\n"
            history = "\nselected_routes:\n" + upgrade_project.PRE_V061_MODEL_DEFAULTS + "\n"
            state_path.write_text(state_path.read_text().replace(upgrade_project.CURRENT_MODEL_DEFAULTS, custom)
                                  .replace("  allowed_runners:", sibling + "  allowed_runners:") + history)
            first = self.run_upgrade(project)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertNotIn("manual review:", first.stdout)
            state = state_path.read_text()
            self.assertIn("  defaults:\n" + custom, state)
            self.assertIn(sibling, state)
            self.assertTrue(state.endswith(history))
            before = self.snapshot(project)
            second = self.run_upgrade(project)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(before, self.snapshot(project))

    def test_conflict_preserves_old_stamp_and_project_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = self.fixture(Path(tmp))
            claude = project / "CLAUDE.md"
            claude.write_text(claude.read_text().replace("The full playbook", "Project-specific playbook", 1))
            result = self.run_upgrade(project)
            self.assertIn("manual review:", result.stdout)
            self.assertIn("playbook_version: V0.4.2", (project / ".playbook-state.yml").read_text())
            self.assertIn("playbook_release: null", (project / ".playbook-state.yml").read_text())
            self.assertIn("Project-specific playbook", claude.read_text())


if __name__ == "__main__":
    unittest.main()

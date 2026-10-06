import hashlib
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

    def test_retargets_old_checkout_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, old_root = self.fixture(Path(tmp))
            first = self.run_upgrade(project)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertNotIn("manual review:", first.stdout)
            state = (project / ".playbook-state.yml").read_text()
            self.assertIn("playbook_version: V0.5.0", state)
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
            self.assertIn("Project-specific playbook", claude.read_text())


if __name__ == "__main__":
    unittest.main()

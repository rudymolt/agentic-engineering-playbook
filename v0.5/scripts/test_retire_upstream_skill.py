from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "v0.5" / "scripts" / "retire-upstream-skill.py"
RETIRED_NAME = "retire-me"
RETIRED_COMMAND = f"/{RETIRED_NAME}"


def load_module():
    spec = importlib.util.spec_from_file_location("retire_upstream_skill", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tree(base: Path) -> Path:
    root = base / "repo"
    shutil.copytree(ROOT / "v0.5", root / "v0.5")
    shutil.copy2(ROOT / ".playbook-maintenance.yml", root / ".playbook-maintenance.yml")
    shutil.copytree(ROOT / "analysis", root / "analysis")
    shutil.copy2(ROOT / "STATUS.md", root / "STATUS.md")

    registry_path = root / "v0.5" / "upstream-skills.json"
    registry = json.loads(registry_path.read_text())
    for raw in registry["skills"].values():
        raw["lanes"] = []
    registry["skills"][RETIRED_NAME] = {
        "package": "pstack",
        "status": "current",
        "invocation": "user",
        "tier": "accelerated",
        "lanes": ["spec_and_slices"],
        "stages": ["04"],
        "previous_names": [],
    }
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")
    (root / "v0.5" / "10-process" / "04-demo.md").write_text(f"Keep `{RETIRED_COMMAND}` visible.\n")
    (root / "analysis" / "retire-note.md").write_text(f"Ignore `{RETIRED_COMMAND}` here.\n")
    return root


class RetireUpstreamSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_refusal_is_fail_closed_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

            with self.assertRaisesRegex(self.module.RetirementBlocked, "spec_and_slices") as raised:
                self.module.apply(root, name=RETIRED_NAME, removed_in="V0.5.1", apply=False, accept_manual_route=False)

            self.assertIn("Write the required sections", str(raised.exception))
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_refusal_cli_exits_two_and_emits_the_manual_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            original_root = self.module.ROOT
            output = io.StringIO()
            try:
                self.module.ROOT = root
                with contextlib.redirect_stdout(output):
                    exit_code = self.module.main([RETIRED_NAME, "--removed-in", "V0.5.1"])
            finally:
                self.module.ROOT = original_root
            self.assertEqual(exit_code, 2)
            self.assertIn("spec_and_slices", output.getvalue())
            self.assertIn("Write the required sections", output.getvalue())

    def test_override_marks_removed_runs_generators_and_reports_remaining_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))

            report = self.module.apply(root, name=RETIRED_NAME, removed_in="V0.5.1", apply=True, accept_manual_route=True)

            registry = json.loads((root / "v0.5" / "upstream-skills.json").read_text())
            self.assertEqual(registry["skills"][RETIRED_NAME]["status"], "removed")
            self.assertEqual(registry["skills"][RETIRED_NAME]["removed_in"], "V0.5.1")
            self.assertIn(Path("v0.5/upstream-skills.json"), report.files)
            self.assertIn(Path("v0.5/CHANGELOG.md"), report.files)
            self.assertEqual(report.mentions, [(Path("v0.5/10-process/04-demo.md"), 1)])
            draft = (root / "v0.5" / "CHANGELOG.md").read_text()
            self.assertIn("**Files touched:**", draft)
            self.assertIn("`v0.5/upstream-skills.json`", draft)
            self.assertIn("*Why:* [Human fill in why before committing.]", draft)
            self.assertIn("maintainer-host §6.4 replay counts pending", draft)
            self.assertIn(RETIRED_COMMAND, (root / "v0.5" / "10-process" / "04-demo.md").read_text())
            self.assertIn(RETIRED_COMMAND, (root / "analysis" / "retire-note.md").read_text())


if __name__ == "__main__":
    unittest.main()

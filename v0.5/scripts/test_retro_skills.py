"""Verify independent retro discovery and installation without replacing gstack."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import upstream_registry
from test_bootstrap_project import bootstrap_project, upgrade_project

ROOT = Path(__file__).resolve().parents[2]


class RetroSkillsTest(unittest.TestCase):
    def test_distinct_commands_and_pinned_reference(self):
        registry = upstream_registry.load()
        for host, expected in {
            "claude": ("/retro", "/matt-retro"),
            "codex": ("$gstack-retro", "$matt-retro"),
        }.items():
            self.assertEqual(tuple(registry.harness_name(name, host)
                                   for name in ("retro", "matt-retro")), expected)
        skill = registry.skills["matt-retro"]
        self.assertEqual(skill.invocation, "user")
        self.assertTrue(skill.install_by_default)
        receipt = json.loads((ROOT / "analysis/2026-10-08-matt-migration-sources.json").read_text())
        source = next(s for s in receipt["skills"] if s["skill"] == "retro")
        reference = ROOT / "v0.5/skills/matt-retro/references/upstream-retro.md"
        self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(),
                         source["files_sha256"]["SKILL.md"])
        self.assertEqual(skill.provenance["commit"], receipt["commit"])

    def test_bootstrap_and_upgrade_preserve_both_customized_retros(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            gstack = project / ".agents/skills/gstack-retro/SKILL.md"
            gstack.parent.mkdir(parents=True)
            gstack.write_text("Existing customized gstack retro\n")
            bootstrap_project.bootstrap_project(project, ROOT, project_name="Retro test", ui="no", ci="copy")
            matt = project / ".agents/skills/matt-retro/SKILL.md"
            reference = matt.parent / "references/upstream-retro.md"
            self.assertTrue(reference.is_file())
            self.assertFalse((project / ".agents/skills/retro").exists())
            custom = matt.read_text() + "\nProject-specific retro note.\n"
            matt.write_text(custom)
            upgrade_project.upgrade_project(project)
            self.assertEqual(matt.read_text(), custom)
            self.assertEqual(gstack.read_text(), "Existing customized gstack retro\n")
            self.assertEqual(reference.read_bytes(),
                             (ROOT / "v0.5/skills/matt-retro/references/upstream-retro.md").read_bytes())


if __name__ == "__main__":
    unittest.main()

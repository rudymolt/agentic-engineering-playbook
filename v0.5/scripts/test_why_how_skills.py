"""Structural packaging checks for why/how; no agent-behavior validation.

These checks establish registry, attribution, stage-reference, and metadata
contracts only. Instructional coherence requires independent scenario review;
passing here does not prove compliance with AC08's evidence boundaries.
"""

import importlib.util
import unittest
from pathlib import Path

import upstream_registry


ROOT = Path(__file__).resolve().parents[1]
PSTACK_COMMIT = "93b00b89ef425a9c1bac0d0b317dfc49c930ac99"


class WhyHowSkillPackagingTests(unittest.TestCase):
    def test_registry_declares_default_installation_and_pinned_provenance(self) -> None:
        registry = upstream_registry.load()
        expected = {
            "ai-playbook-why": {
                "stages": ("02", "06", "08", "11"),
                "source": "pstack/skills/why/SKILL.md",
            },
            "ai-playbook-how": {
                "stages": ("06", "08", "11"),
                "source": "pstack/skills/how/SKILL.md",
            },
        }
        for name, contract in expected.items():
            with self.subTest(name=name):
                skill = registry.skills[name]
                self.assertEqual(skill.package, "playbook")
                self.assertEqual(skill.invocation, "model")
                self.assertEqual(skill.tier, "core")
                self.assertTrue(skill.install_by_default)
                self.assertEqual(skill.stages, contract["stages"])
                self.assertEqual(skill.provenance["package"], "pstack")
                self.assertEqual(skill.provenance["commit"], PSTACK_COMMIT)
                self.assertEqual(skill.provenance["source"], contract["source"])
                notice = (ROOT / "skills" / name / "NOTICE").read_text()
                self.assertIn(PSTACK_COMMIT, notice)
                self.assertIn(contract["source"], notice)
                self.assertIn("MIT License", notice)

    def test_stages_reference_the_expected_skill_commands(self) -> None:
        pointers = {
            "02-context-and-adrs.md": ("/ai-playbook-why",),
            "06-architecture.md": ("/ai-playbook-why", "/ai-playbook-how"),
            "08-review.md": ("/ai-playbook-why", "/ai-playbook-how"),
            "11-debug.md": ("/ai-playbook-why", "/ai-playbook-how"),
        }
        for stage, skills in pointers.items():
            text = (ROOT / "10-process" / stage).read_text()
            for skill in skills:
                with self.subTest(stage=stage, skill=skill):
                    self.assertIn(skill, text)

    def test_codex_metadata_has_the_required_picker_contract(self) -> None:
        script = Path(__file__).with_name("check-skill-metadata.py")
        spec = importlib.util.spec_from_file_location("check_skill_metadata", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(), [])


if __name__ == "__main__":
    unittest.main()

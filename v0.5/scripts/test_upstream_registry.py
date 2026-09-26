from __future__ import annotations

import importlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import upstream_registry as ur

ROOT = Path(__file__).resolve().parents[1]
PREREQS = ROOT / "10-process" / "00-prereqs.md"
MANIFEST = ROOT / "upstream-integrations.json"


def synthetic(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "packages": {
            "up": {
                "kind": "upstream", "source": "https://example.com/up",
                "adoption_level": "accelerator",
                "pin": {"kind": "tag", "value": "v1.0.0", "commit": "abcdef0123456"},
                "install": {"method": "skills-cli", "roots": [".agents/skills"]},
                "harness_name_pattern": {"claude": "/{name}", "codex": "$up-{name}"},
            },
            "playbook": {"kind": "local", "source": "v0.5/skills"},
        },
        "skills": {
            "alpha": {"package": "up", "invocation": "user", "lanes": ["spec_and_slices"],
                      "stages": ["03"], "upstream_path": "skills/eng/alpha",
                      "previous_names": [{"name": "old-alpha", "upstream_version": "v0.9.0"}],
                      "manifest_key": "alpha"},
            "old-alpha": {"package": "up", "invocation": "user", "status": "removed",
                          "removed_in": "V0.4.1"},
            "helper": {"package": "playbook", "invocation": "model", "install_by_default": True},
        },
    }
    payload.update(overrides)
    return payload


def write(tmp: Path, payload: dict) -> Path:
    path = tmp / "upstream-skills.json"
    path.write_text(json.dumps(payload))
    return path


class RealRegistryTests(unittest.TestCase):
    def test_real_registry_loads(self) -> None:
        registry = ur.load()
        self.assertIn("mattpocock-skills", registry.packages)
        self.assertIn("gstack", registry.packages)
        self.assertIn("playbook", registry.packages)

    def test_check_a_round_trips_stage_00(self) -> None:
        registry = ur.load()
        text = PREREQS.read_text()
        block = re.search(r"```\n(\.claude/skills/.*?)```", text, re.S)
        assert block
        expected = block.group(1).split()
        self.assertEqual(registry.check_a_paths("mattpocock-skills"), expected)

    def test_check_b_round_trips_stage_00(self) -> None:
        registry = ur.load()
        text = PREREQS.read_text()
        block = re.search(r"```\n(/office-hours.*?)```", text, re.S)
        assert block
        expected = sorted(block.group(1).split())
        self.assertEqual(sorted(registry.check_b_commands("gstack")), expected)

    def test_manifest_cross_validates(self) -> None:
        registry = ur.load()
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(ur.manifest_problems(registry, manifest), [])

    def test_local_default_skills_match_managed_skills(self) -> None:
        import template_base

        registry = ur.load()
        self.assertEqual(registry.local_default_skills(), sorted(template_base.MANAGED_SKILLS))
        self.assertTrue(template_base.MANAGED_SKILLS)
        for name in template_base.MANAGED_SKILLS:
            self.assertTrue((ROOT / "skills" / name / "SKILL.md").is_file(), name)

    def test_managed_skills_are_derived_from_registry_at_import(self) -> None:
        import template_base

        payload = synthetic()
        payload["skills"] = {
            "dynamic-default": {
                "package": "playbook",
                "invocation": "model",
                "install_by_default": True,
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            registry = ur.load(write(Path(tmp), payload))
        try:
            with mock.patch.object(ur, "load", return_value=registry):
                reloaded = importlib.reload(template_base)
            self.assertEqual(reloaded.MANAGED_SKILLS, ("dynamic-default",))
        finally:
            importlib.reload(template_base)


class SyntheticRegistryTests(unittest.TestCase):
    def load(self, payload: dict) -> ur.Registry:
        with tempfile.TemporaryDirectory() as tmp:
            return ur.load(write(Path(tmp), payload))

    def test_queries(self) -> None:
        registry = self.load(synthetic())
        self.assertEqual(registry.current_names(), {"alpha", "helper"})
        self.assertEqual(registry.previous_name_map(), {"old-alpha": "alpha"})
        self.assertEqual(registry.removed_names(), {"old-alpha"})
        self.assertEqual(registry.manifest_keys(), {"alpha": "alpha"})
        self.assertEqual(registry.local_default_skills(), ["helper"])
        self.assertEqual(registry.check_a_paths("up"), [".claude/skills/skills/eng/alpha/SKILL.md"])
        self.assertEqual(registry.check_b_commands("up"), ["/alpha"])
        self.assertEqual(registry.harness_name("alpha", "codex"), "$up-alpha")
        self.assertEqual(registry.harness_name("alpha", "claude"), "/alpha")

    def test_rejects_unknown_lane(self) -> None:
        payload = synthetic()
        payload["skills"]["alpha"]["lanes"] = ["nope"]
        with self.assertRaisesRegex(ur.RegistryError, "unknown lanes"):
            self.load(payload)

    def test_rejects_local_skill_without_default_flag(self) -> None:
        payload = synthetic()
        del payload["skills"]["helper"]["install_by_default"]
        with self.assertRaisesRegex(ur.RegistryError, "install_by_default"):
            self.load(payload)

    def test_rejects_previous_name_that_is_still_current(self) -> None:
        payload = synthetic()
        payload["skills"]["old-alpha"] = {"package": "up", "invocation": "user"}
        with self.assertRaisesRegex(ur.RegistryError, "still a current skill"):
            self.load(payload)

    def test_rejects_duplicate_manifest_key(self) -> None:
        payload = synthetic()
        payload["skills"]["beta"] = {"package": "up", "invocation": "user", "manifest_key": "alpha"}
        with self.assertRaisesRegex(ur.RegistryError, "claimed by both"):
            self.load(payload)

    def test_rejects_accelerator_without_install(self) -> None:
        payload = synthetic()
        payload["packages"]["up"]["install"] = {"method": "none"}
        with self.assertRaisesRegex(ur.RegistryError, "install method"):
            self.load(payload)

    def test_manifest_problems(self) -> None:
        registry = self.load(synthetic())
        manifest = {"integrations": {"alpha": {"upstream": "example.com/up"}, "gamma": {}}}
        problems = ur.manifest_problems(registry, manifest)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("gamma", problems[0])
        manifest = {"integrations": {"alpha": {"upstream": "somewhere-else"}}}
        self.assertTrue(any("does not match" in p for p in ur.manifest_problems(registry, manifest)))


if __name__ == "__main__":
    unittest.main()

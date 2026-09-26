from __future__ import annotations

import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("check-upstream-drift.py")
SPEC = importlib.util.spec_from_file_location("check_upstream_drift", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpstreamDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture_root = Path(directory.name)
        self.registry = self.write_registry_fixture()
        self.manifest = self.write_manifest_fixture()

    def write_registry_fixture(self) -> Path:
        path = self.fixture_root / "upstream-skills.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "packages": {
                "mattpocock-skills": {
                    "kind": "upstream",
                    "source": "https://github.com/mattpocock/skills",
                    "adoption_level": "accelerator",
                    "pin": {"kind": "tag", "value": "v9.9.9", "commit": "abcdef0123456"},
                    "install": {"method": "skills-cli"},
                    "harness_name_pattern": {"claude": "/{name}"},
                },
                "gstack": {
                    "kind": "upstream",
                    "source": "https://github.com/garrytan/gstack",
                    "adoption_level": "accelerator",
                    "pin": {"kind": "commit+version", "value": "8.8.8", "commit": "123456789abcd"},
                    "install": {"method": "git-checkout"},
                    "harness_name_pattern": {"claude": "/{name}"},
                },
            },
            "skills": {
                "review": {
                    "package": "mattpocock-skills",
                    "invocation": "user",
                    "manifest_key": "review",
                },
            },
        }))
        return path

    @staticmethod
    def manifest_entry(upstream: str) -> dict[str, object]:
        return {
            "upstream": upstream,
            "tested_version": "v9.9.9",
            "tested_source_sha256": "0" * 64,
            "embedded_compatible": False,
            "compatible_mode": "none",
            "embedded_invocation": None,
            "adapter": "manual route",
            "compatibility_evidence": "synthetic fixture",
            "required_outputs": ["report"],
            "permitted_side_effects": ["repository reads"],
            "prohibited_side_effects": ["edits"],
            "fallback": "manual: fixture",
            "last_verified": "2026-01-01",
        }

    def write_manifest_fixture(self, integrations: dict[str, dict[str, object]] | None = None) -> Path:
        path = self.fixture_root / "upstream-integrations.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "integrations": integrations or {"review": self.manifest_entry("mattpocock/skills")},
        }))
        return path

    def write_state(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / ".playbook-maintenance.yml"
        if "\nupstreams:" not in text:
            text += (
                "\nupstreams:\n"
                "  matt_pocock_skills: v9.9.9\n"
                "  gstack: 8.8.8 (1234567)\n"
            )
        path.write_text(text)
        return path

    def check(self, state: Path, as_of: dt.date, *, manifest: Path | None = None) -> list[str]:
        return MODULE.check(
            state,
            as_of,
            registry=self.registry,
            manifest=self.manifest if manifest is None else manifest,
        )

    def test_current_state_passes_before_due_date(self) -> None:
        path = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        self.assertEqual(self.check(path, dt.date(2026, 8, 8)), [])

    def test_due_state_names_the_procedure_and_owner(self) -> None:
        path = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        problems = self.check(path, dt.date(2026, 8, 9))
        self.assertEqual(len(problems), 1)
        self.assertIn("maintainer", problems[0])
        self.assertIn("MAINTENANCE.md", problems[0])

    def test_invalid_order_fails(self) -> None:
        path = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-08-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        self.assertTrue(any("later" in problem for problem in self.check(path, dt.date(2026, 8, 1))))

    def test_missing_integration_manifest_fails_the_drift_check(self) -> None:
        state = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        missing = state.parent / "missing-integrations.json"
        problems = self.check(state, dt.date(2026, 8, 1), manifest=missing)
        self.assertTrue(any("integration manifest" in problem for problem in problems))

    def test_malformed_integration_manifest_fails_the_drift_check(self) -> None:
        state = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        manifest = self.fixture_root / "malformed-integrations.json"
        manifest.write_text('{"schema_version": 1, "integrations": {"review": {}}}')
        problems = self.check(state, dt.date(2026, 8, 1), manifest=manifest)
        self.assertTrue(any("missing required fields" in problem for problem in problems))

    def test_registry_manifest_mismatch_fails_the_drift_check(self) -> None:
        state = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
        )
        self.write_manifest_fixture({"other": self.manifest_entry("mattpocock/skills")})
        problems = self.check(state, dt.date(2026, 8, 1))
        self.assertTrue(any("manifest entry 'other'" in problem for problem in problems))
        self.assertTrue(any("registry skill 'review'" in problem for problem in problems))

    def test_registry_pin_mismatch_fails_the_drift_check(self) -> None:
        state = self.write_state(
            "owner: maintainer\nprocedure: MAINTENANCE.md\nlast_verified: 2026-07-09\n"
            "next_due: 2026-08-09\ncadence: monthly\n"
            "upstreams:\n  matt_pocock_skills: v0.0.0\n  gstack: 0.0.0 (0000000)\n"
        )
        problems = self.check(state, dt.date(2026, 8, 1))
        self.assertIn(
            "upstreams.matt_pocock_skills 'v0.0.0' does not match registry 'v9.9.9'",
            problems,
        )
        self.assertIn(
            "upstreams.gstack '0.0.0 (0000000)' does not match registry '8.8.8 (1234567)'",
            problems,
        )


if __name__ == "__main__":
    unittest.main()

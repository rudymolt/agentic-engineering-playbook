from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import upstream_registry as ur

MODULE_PATH = Path(__file__).with_name("audit-upstream-installed.py")
SPEC = importlib.util.spec_from_file_location("audit_upstream_installed", MODULE_PATH)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def manifest_entry(digest: str, upstream: str, fallback: str) -> dict:
    return {
        "upstream": upstream, "tested_version": "v1.0.0", "tested_source_sha256": digest,
        "embedded_compatible": False, "compatible_mode": "none", "embedded_invocation": None,
        "adapter": "stage 08", "compatibility_evidence": "not report-only",
        "required_outputs": ["findings"], "permitted_side_effects": ["reads"],
        "prohibited_side_effects": ["edits"], "fallback": fallback, "last_verified": "2026-08-01",
    }


class ProbeTests(unittest.TestCase):
    def build(self, tmp: Path) -> tuple[ur.Registry, Path, Path, Path]:
        home = tmp / "home"
        (home / ".agents" / "skills" / "alpha").mkdir(parents=True)
        (home / ".agents" / "skills" / "alpha" / "SKILL.md").write_text("alpha instructions v2\n")
        (home / ".agents" / "skills" / "stray").mkdir()
        (home / ".agents" / "skills" / "stray" / "SKILL.md").write_text("stray\n")
        (home / ".agents" / "skills" / "old-alpha").mkdir()
        (home / ".agents" / "skills" / "old-alpha" / "SKILL.md").write_text("old copy\n")
        (home / ".agents" / ".skill-lock.json").write_text(json.dumps({
            "version": 3,
            "skills": {
                "alpha": {"source": "example/up", "skillFolderHash": "aaa", "updatedAt": "2026-08-01T00:00:00Z"},
                "stray": {"source": "example/up", "skillFolderHash": "bbb", "updatedAt": "2026-08-02T00:00:00Z"},
                "old-alpha": {"source": "example/up", "skillFolderHash": "ddd", "updatedAt": "2026-07-01T00:00:00Z"},
                "other": {"source": "someone/else", "skillFolderHash": "ccc", "updatedAt": "2026-08-03T00:00:00Z"},
            },
        }))
        checkout = tmp / "gs"
        (checkout / "beta").mkdir(parents=True)
        (checkout / "beta" / "SKILL.md").write_text("beta instructions\n")
        (checkout / "VERSION").write_text("2.0.0\n")
        beta_digest = hashlib.sha256((checkout / "beta" / "SKILL.md").read_bytes()).hexdigest()
        manifest = tmp / "upstream-integrations.json"
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "integrations": {
                "alpha": manifest_entry("0" * 64, "example/up", "manual: stage 08"),
                "beta": manifest_entry(beta_digest, "example/gs", "manual: stage 09"),
            },
        }))
        registry_path = tmp / "upstream-skills.json"
        registry_path.write_text(json.dumps({
            "schema_version": 1,
            "packages": {
                "up": {"kind": "upstream", "source": "https://github.com/example/up",
                       "adoption_level": "accelerator",
                       "pin": {"kind": "tag", "value": "v1.0.0", "commit": "abcdef0123456"},
                       "install": {"method": "skills-cli", "lock_file": "~/.agents/.skill-lock.json"}},
                "gs": {"kind": "upstream", "source": "https://github.com/example/gs",
                       "adoption_level": "accelerator",
                       "pin": {"kind": "commit+version", "value": "1.0.0", "commit": "1234567abcdef"},
                       "install": {"method": "git-checkout", "checkout": str(checkout), "version_file": "VERSION"}},
                "playbook": {"kind": "local", "source": "v0.5/skills"},
            },
            "skills": {
                "alpha": {"package": "up", "invocation": "user", "manifest_key": "alpha",
                          "previous_names": [{"name": "old-alpha", "upstream_version": "v0.9.0"}]},
                "gone": {"package": "up", "invocation": "user", "status": "removed", "removed_in": "V0.4.1"},
                "beta": {"package": "gs", "invocation": "model", "manifest_key": "beta"},
                "missing": {"package": "gs", "invocation": "model"},
                "helper": {"package": "playbook", "invocation": "model", "install_by_default": True},
            },
            "borrowed_ideas": [{"package": "gs", "id": "skip-with-reason"}],
        }))
        return ur.load(registry_path), manifest, home, checkout

    def test_probe_reports_packages_skills_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry, manifest, home, checkout = self.build(Path(tmp))
            report = PROBE.probe(registry, manifest, home)
            statuses = {pkg["name"]: pkg["status"] for pkg in report["packages"]}
            self.assertIn("installed via skills CLI", statuses["up"])
            self.assertIn("2026-08-02", statuses["up"])
            self.assertIn("VERSION 2.0.0", statuses["gs"])
            self.assertIn("differs from pin 1.0.0", statuses["gs"])
            self.assertIn("not applicable", statuses["playbook"])

            up_rows = {row["name"]: row for row in report["skills"]["up"]}
            self.assertTrue(up_rows["alpha"]["installed"])
            self.assertEqual(up_rows["alpha"]["lock_hash"], "aaa")
            self.assertEqual(report["unregistered"]["up"], ["stray"])
            self.assertEqual(report["stale_renamed"]["up"], ["old-alpha → alpha"])
            gs_rows = {row["name"]: row for row in report["skills"]["gs"]}
            self.assertFalse(gs_rows["missing"]["installed"])
            self.assertEqual(gs_rows["missing"]["note"], "not installed")

            verdicts = {row["key"]: row for row in report["manifest"]}
            self.assertEqual(verdicts["alpha"]["status"], "drifted")
            self.assertEqual(verdicts["beta"]["status"], "incompatible")
            self.assertEqual(verdicts["beta"]["actual"], verdicts["beta"]["expected"])
            self.assertEqual(report["manifest_problems"], [])
            self.assertEqual(report["borrowed_ideas"][0]["id"], "skip-with-reason")

    def test_markdown_render_and_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry, manifest, home, checkout = self.build(Path(tmp))
            text = PROBE.render_markdown(PROBE.probe(registry, manifest, home))
            self.assertIn("| alpha | v1.0.0 |", text)
            self.assertIn("**drifted**", text)
            self.assertIn("Installed but not in the registry", text)
            self.assertIn("stray", text)
            self.assertIn("Stale copies of renamed skills still installed: old-alpha → alpha", text)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = PROBE.main([
                    "--registry", str(Path(tmp) / "upstream-skills.json"),
                    "--manifest", str(manifest), "--home", str(home), "--json",
                ])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(buffer.getvalue())["manifest_problems"], [])

    def test_missing_checkout_and_lock_are_reported_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry, manifest, home, checkout = self.build(Path(tmp))
            empty_home = Path(tmp) / "empty"
            empty_home.mkdir()
            report = PROBE.probe(registry, manifest, empty_home, {"gs": Path(tmp) / "nowhere"})
            statuses = {pkg["name"]: pkg["status"] for pkg in report["packages"]}
            self.assertIn("lock file not found", statuses["up"])
            self.assertEqual(statuses["gs"], "checkout not found")
            self.assertTrue(all(row["status"] == "missing" for row in report["manifest"]))


if __name__ == "__main__":
    unittest.main()

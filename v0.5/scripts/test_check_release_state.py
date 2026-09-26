import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_SCRIPT = SCRIPT_DIR.parent / "skills" / "ship-release" / "scripts" / "check-release-state.py"
spec = importlib.util.spec_from_file_location("check_release_state", SKILL_SCRIPT)
crs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
# dataclasses with deferred annotations resolve through sys.modules on 3.14+
sys.modules["check_release_state"] = crs
spec.loader.exec_module(crs)


CHANGELOG = """# Playbook CHANGELOG

## V0.3.36 — 2026-07-12

Current release notes.

## V0.3.35 — 2026-07-10

Previous release notes.
"""


def make_root(tmp: Path, changelog: str = CHANGELOG, summary_dates=()) -> Path:
    root = tmp / "repo"
    (root / "v0.5").mkdir(parents=True)
    (root / "v0.5" / "CHANGELOG.md").write_text(changelog)
    (root / "bench" / "results").mkdir(parents=True)
    for date in summary_dates:
        run_dir = root / "bench" / "results" / f"{date}-120000"
        run_dir.mkdir()
        (run_dir / "SUMMARY.md").write_text("# Benchmark summary\n")
    return root


class BenchEvidenceTest(unittest.TestCase):
    def check(self, root: Path, acknowledged: bool = False):
        warnings = []
        checks = crs.check_bench_evidence(root, acknowledged, warnings)
        return checks, warnings

    def test_repo_without_bench_dir_is_not_applicable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            (root / "bench" / "results").rmdir()
            (root / "bench").rmdir()
            checks, warnings = self.check(root)
            self.assertFalse(checks["applicable"])
            self.assertEqual(warnings, [])

    def test_fresh_evidence_is_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), summary_dates=["2026-07-11"])
            checks, warnings = self.check(root)
            self.assertEqual(checks["newest_summary_date"], "2026-07-11")
            self.assertEqual(checks["previous_release"], "V0.3.35 (2026-07-10)")
            self.assertEqual(warnings, [])

    def test_stale_evidence_warns_with_remedy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), summary_dates=["2026-07-01"])
            checks, warnings = self.check(root)
            self.assertEqual(len(warnings), 1)
            self.assertEqual(warnings[0].category, "bench_evidence_stale")
            self.assertIn("newer than V0.3.35 (2026-07-10)", warnings[0].message)
            self.assertIn("--no-bench", warnings[0].detail)

    def test_missing_evidence_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), summary_dates=[])
            _, warnings = self.check(root)
            self.assertEqual(len(warnings), 1)
            self.assertIn("absent", warnings[0].message)

    def test_no_bench_flag_acknowledges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), summary_dates=[])
            checks, warnings = self.check(root, acknowledged=True)
            self.assertTrue(checks["acknowledged"])
            self.assertEqual(warnings, [])

    def test_uncommitted_summary_does_not_satisfy_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), summary_dates=["2026-07-01"])
            __import__("subprocess").run(["git", "init", "-q"], cwd=root, check=True)
            __import__("subprocess").run(["git", "add", "."], cwd=root, check=True)
            __import__("subprocess").run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            local = root / "bench" / "results" / "2026-07-11-120000"
            local.mkdir()
            (local / "SUMMARY.md").write_text("# local mock result\n")

            checks, warnings = self.check(root)

            self.assertEqual(checks["newest_summary_date"], "2026-07-01")
            self.assertEqual(len(warnings), 1)

    def test_first_release_has_nothing_to_compare(self):
        first_only = "# Playbook CHANGELOG\n\n## V0.3.1 — 2026-07-01\n\nFirst.\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp), changelog=first_only, summary_dates=[])
            checks, warnings = self.check(root)
            self.assertIsNone(checks["previous_release"])
            self.assertEqual(warnings, [])

    def test_warnings_render_without_blocking_ok_verdict(self):
        result = {
            "profile": "playbook-v0.5", "tag": "v0.4.36", "title": "V0.3.36",
            "bench": {"applicable": True, "newest_summary_date": None,
                      "previous_release": "V0.3.35 (2026-07-10)", "acknowledged": False},
            "warnings": [{"category": "bench_evidence_stale",
                          "message": "no benchmark evidence newer than V0.3.35 (2026-07-10)",
                          "detail": "run bench or pass --no-bench"}],
            "problems": [],
        }
        text = crs.render_text(result)
        self.assertIn("Warnings (non-blocking):", text)
        self.assertIn("bench_evidence_stale", text)
        self.assertIn("OK: release state matches", text)


if __name__ == "__main__":
    unittest.main()

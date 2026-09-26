import subprocess
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import upstream_registry


SCRIPT = Path(__file__).resolve().parent / "generate-status.py"
PLAYBOOK_ROOT = SCRIPT.parents[1]

CHANGELOG = """# Playbook CHANGELOG

## V0.3.36 — 2026-07-12

Current release summary.

## V0.3.35 — 2026-07-10

Previous release summary.

## V0.3.34 — 2026-07-08

Third release summary.
"""

MAINTENANCE = """last_verified: 2026-07-09
next_due: 2026-08-09
cadence: monthly

upstreams:
  gstack: rolling
  codex_docs: 2026-07-09
"""

SUMMARY = """# Benchmark summary

Generated 2026-07-11T12:00:00+00:00 · 10 completed run(s) · Runner: codex · comparisons are within-model only

## Model: gpt-5.4

| Task | Condition | Runs | Pass | Err | Skip |
|---|---|---|---|---|---|
| T1 | v03 | 5 | 4/5 | 0 | 0 |
| T2 | v03 | 5 | 5/5 | 0 | 0 |
"""


def make_root(base: Path) -> Path:
    root = base / "repo"
    (root / "v0.5").mkdir(parents=True)
    (root / "v0.5" / "CHANGELOG.md").write_text(CHANGELOG)
    shutil.copy2(PLAYBOOK_ROOT / "upstream-skills.json", root / "v0.5" / "upstream-skills.json")
    (root / ".playbook-maintenance.yml").write_text(MAINTENANCE)
    (root / "analysis").mkdir()
    (root / "analysis" / "STATUS.md").write_text(
        "# Analysis status\n\n## Active\n\n"
        "- [`open-plan.md`](open-plan.md) — Open plan.\n\n"
        "## Reference\n\n- [`evidence.md`](evidence.md) — Evidence.\n"
    )
    run = root / "bench" / "results" / "2026-07-11-120000"
    run.mkdir(parents=True)
    (run / "SUMMARY.md").write_text(SUMMARY)
    return root


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


class GenerateStatusCliTest(unittest.TestCase):
    def test_generate_reports_release_maintenance_benchmark_and_active_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))

            completed = run_cli(root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            dashboard = (root / "STATUS.md").read_text()
            self.assertIn("**V0.3.36** — 2026-07-12. Current release summary.", dashboard)
            self.assertIn("Last verified 2026-07-09; next due 2026-08-09", dashboard)
            self.assertIn("Runner: codex; models: gpt-5.4", dashboard)
            self.assertIn("9/10 passed (90.0%)", dashboard)
            self.assertIn("Current for this release cycle", dashboard)
            self.assertIn("Gate health is evaluated when this command runs", dashboard)
            self.assertIn("## Upstream packages", dashboard)
            self.assertIn("| Package | Level | Pin | Verified | Skills named |", dashboard)
            self.assertIn("[`open-plan.md`](analysis/open-plan.md)", dashboard)
            self.assertNotIn("evidence.md", dashboard)

    def test_upstream_package_rows_render_each_pin_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))

            completed = run_cli(root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            dashboard = (root / "STATUS.md").read_text()
            registry = upstream_registry.load()
            matt_pin = registry.packages["mattpocock-skills"].pin
            gstack_pin = registry.packages["gstack"].pin
            pstack_pin = registry.packages["pstack"].pin
            self.assertIn(
                f"| mattpocock-skills | accelerator | {matt_pin['value']} | {matt_pin['verified']} | 20 |",
                dashboard,
            )
            self.assertIn(
                f"| gstack | accelerator | {gstack_pin['value']} ({gstack_pin['commit'][:7]}) | {gstack_pin['verified']} | 35 |",
                dashboard,
            )
            self.assertIn(
                f"| pstack | source | {pstack_pin['commit']} | {pstack_pin['verified']} | 0 |",
                dashboard,
            )
        self.assertIn(
            f"| playbook | local | — | — | {len(registry.skills_for('playbook'))} |",
            dashboard,
        )

    def test_check_detects_manual_edit_and_regeneration_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            self.assertEqual(run_cli(root).returncode, 0)
            generated = (root / "STATUS.md").read_text()

            self.assertEqual(run_cli(root, "--check").returncode, 0)
            (root / "STATUS.md").write_text(generated + "manual edit\n")
            stale = run_cli(root, "--check")
            self.assertEqual(stale.returncode, 1)
            self.assertIn("stale or hand-edited", stale.stdout)

            self.assertEqual(run_cli(root).returncode, 0)
            self.assertEqual((root / "STATUS.md").read_text(), generated)

    def test_uncommitted_benchmark_run_does_not_replace_release_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-qm", "fixture"],
                cwd=root,
                check=True,
            )
            local_run = root / "bench" / "results" / "2026-07-14-120000"
            local_run.mkdir()
            (local_run / "SUMMARY.md").write_text(SUMMARY.replace("gpt-5.4", "mock"))

            completed = run_cli(root)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            dashboard = (root / "STATUS.md").read_text()
            self.assertIn("`2026-07-11-120000`", dashboard)
            self.assertNotIn("`2026-07-14-120000`", dashboard)
            self.assertNotIn("models: mock", dashboard)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for delivery CI path classification."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from delivery_ci_scope import classify, git_changed_paths


class DeliveryCiScopeTests(unittest.TestCase):
    def test_readme_and_playbook_docs_skip_delivery(self) -> None:
        decision = classify(["README.md", "v0.5/CHANGELOG.md", "v0.5/MANIFEST.json"])

        self.assertFalse(decision.run_delivery)
        self.assertEqual(decision.reason, "no delivery runtime files changed")

    def test_delivery_runtime_change_runs_delivery(self) -> None:
        decision = classify(["README.md", "v0.5/delivery/src/delivery_pilot/state.py"])

        self.assertTrue(decision.run_delivery)
        self.assertEqual(decision.reason, "delivery runtime files changed")

    def test_workflow_change_runs_delivery(self) -> None:
        decision = classify([".github/workflows/playbook-maintenance.yml"])

        self.assertTrue(decision.run_delivery)
        self.assertEqual(decision.reason, "CI workflow changed")

    def test_classifier_change_runs_delivery(self) -> None:
        decision = classify(["v0.5/scripts/delivery_ci_scope.py"])

        self.assertTrue(decision.run_delivery)
        self.assertEqual(decision.reason, "delivery CI classifier changed")

    def test_git_diff_keeps_source_path_when_delivery_file_moves_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            source = repo / "v0.5/delivery/runtime.py"
            source.parent.mkdir(parents=True)
            source.write_text("runtime = True\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "base"],
                cwd=repo,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            destination = repo / "elsewhere/runtime.py"
            destination.parent.mkdir(parents=True)
            source.rename(destination)
            subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "move"],
                cwd=repo,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

            decision = classify(git_changed_paths(base, head, repo))

        self.assertTrue(decision.run_delivery)
        self.assertEqual(decision.reason, "delivery runtime files changed")

    def test_git_diff_preserves_non_ascii_delivery_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "base"],
                cwd=repo,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            source = repo / "v0.5/delivery/café.py"
            source.parent.mkdir(parents=True)
            source.write_text("runtime = True\n")
            subprocess.run(["git", "add", "."], cwd=repo, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "unicode path"],
                cwd=repo,
                check=True,
            )
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=repo, check=True,
                capture_output=True, text=True,
            ).stdout.strip()

            decision = classify(git_changed_paths(base, head, repo))

        self.assertTrue(decision.run_delivery)
        self.assertEqual(decision.reason, "delivery runtime files changed")


if __name__ == "__main__":
    unittest.main()

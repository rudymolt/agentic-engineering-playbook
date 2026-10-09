#!/usr/bin/env python3
"""Tests for the conservative editorial PR check scope."""

from __future__ import annotations

import unittest

from edition_ci_scope import classify


class EditionCiScopeTests(unittest.TestCase):
    def test_editorial_release_metadata_uses_focused_checks(self) -> None:
        decision = classify(["README.md", "v0.5/CHANGELOG.md", "v0.5/MANIFEST.json"])

        self.assertFalse(decision.run_full)

    def test_agent_and_process_docs_keep_full_suite(self) -> None:
        for path in (
            "AGENTS.md",
            "v0.5/README.md",
            "v0.5/AGENT-DIGEST.md",
            "v0.5/10-process/10-ship-and-deploy.md",
            "v0.5/skills/ship-release/PLAYBOOK-PROFILE.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify(["README.md", path]).run_full)

    def test_workflow_classifier_and_unknown_paths_keep_full_suite(self) -> None:
        for path in (
            ".github/workflows/playbook-ci.yml",
            "v0.5/scripts/edition_ci_scope.py",
            "v0.5/templates/AGENTS.md",
            "NOTICE",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify([path]).run_full)

    def test_empty_change_set_fails_closed(self) -> None:
        self.assertTrue(classify([]).run_full)


if __name__ == "__main__":
    unittest.main()

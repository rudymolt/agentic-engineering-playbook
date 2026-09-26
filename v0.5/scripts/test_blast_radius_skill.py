"""Distribution and real-code evidence checks for the blast-radius skill.

The controlled probe executes the production bootstrap command. It is not an
agent-behavior test: a passing probe proves only that this registry revision
installs this source skill into a fresh project.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import upstream_registry


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
SKILL = "ai-playbook-blast-radius"
PSTACK_COMMIT = "93b00b89ef425a9c1bac0d0b317dfc49c930ac99"


def bootstrap_presence_check(playbook: Path, project: Path) -> subprocess.CompletedProcess[str]:
    """Run the production bootstrap and make its installed-skill output observable."""

    bootstrap = playbook / "v0.5" / "scripts" / "bootstrap-project.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(bootstrap),
            str(project),
            "--playbook-path",
            str(playbook),
            "--project-name",
            "Blast Radius Fixture",
            "--ui",
            "no",
            "--ci",
            "copy",
            "--apply",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        return completed
    installed = project / ".agents" / "skills" / SKILL / "SKILL.md"
    return subprocess.CompletedProcess(
        completed.args,
        0 if installed.is_file() else 1,
        completed.stdout,
        completed.stderr + ("" if installed.is_file() else f"missing installed skill: {installed}\n"),
    )


class BlastRadiusSkillTests(unittest.TestCase):
    def test_registry_and_notice_declare_default_distribution_with_pinned_provenance(self) -> None:
        skill = upstream_registry.load().skills[SKILL]
        self.assertEqual(skill.package, "playbook")
        self.assertEqual(skill.invocation, "model")
        self.assertEqual(skill.tier, "core")
        self.assertEqual(skill.lanes, ("independent_verification",))
        self.assertEqual(skill.stages, ("08",))
        self.assertTrue(skill.install_by_default)
        self.assertEqual(
            skill.provenance,
            {
                "package": "pstack",
                "commit": PSTACK_COMMIT,
                "source": "pstack/skills/blast-radius/SKILL.md",
            },
        )
        notice = (ROOT / "skills" / SKILL / "NOTICE").read_text()
        self.assertIn(PSTACK_COMMIT, notice)
        self.assertIn("pstack/skills/blast-radius/SKILL.md", notice)
        self.assertIn("MIT License", notice)

    def test_real_bootstrap_passes_for_default_distribution_and_fails_loudly_when_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            supported = bootstrap_presence_check(REPOSITORY, workspace / "supported-project")
            self.assertEqual(supported.returncode, 0, supported.stdout + supported.stderr)

            changed_playbook = workspace / "changed-playbook"
            shutil.copytree(ROOT, changed_playbook / "v0.5")
            registry_path = changed_playbook / "v0.5" / "upstream-skills.json"
            registry = json.loads(registry_path.read_text())
            registry["skills"][SKILL]["install_by_default"] = False
            registry_path.write_text(json.dumps(registry, indent=2) + "\n")

            counterexample = bootstrap_presence_check(changed_playbook, workspace / "false-project")
            self.assertEqual(counterexample.returncode, 1, counterexample.stdout + counterexample.stderr)
            self.assertIn("missing installed skill", counterexample.stderr)

    def test_codex_metadata_checker_accepts_the_source_skill(self) -> None:
        script = Path(__file__).with_name("check-skill-metadata.py")
        spec = importlib.util.spec_from_file_location("check_skill_metadata", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.check(), [])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "v0.5" / "scripts" / "rename-upstream-skill.py"
OLD_NAME = "old-name"
NEW_NAME = "new-name"
OLD_COMMAND = f"/{OLD_NAME}"
NEW_COMMAND = f"/{NEW_NAME}"


def load_module():
    spec = importlib.util.spec_from_file_location("rename_upstream_skill", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_tree(base: Path) -> Path:
    root = base / "repo"
    shutil.copytree(ROOT / "v0.5", root / "v0.5")
    shutil.copy2(ROOT / ".playbook-maintenance.yml", root / ".playbook-maintenance.yml")
    shutil.copytree(ROOT / "analysis", root / "analysis")
    shutil.copy2(ROOT / "STATUS.md", root / "STATUS.md")
    (root / ".agents").mkdir()
    (root / ".playbook-base").mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "sentinel").write_text("must not enter staging\n")

    registry_path = root / "v0.5" / "upstream-skills.json"
    registry = json.loads(registry_path.read_text())
    registry["skills"][OLD_NAME] = {
        "package": "pstack",
        "status": "current",
        "invocation": "user",
        "tier": "accelerated",
        "lanes": [],
        "stages": ["07"],
        "upstream_path": f"engineering/{OLD_NAME}",
        "previous_names": [],
    }
    registry_path.write_text(json.dumps(registry, indent=2) + "\n")

    (root / "v0.5" / "10-process" / "07-demo.md").write_text(
        f"Use `{OLD_COMMAND}` first. Later `{OLD_COMMAND}` remains documented.\n"
    )
    (root / "v0.5" / "91-demo-track.md").write_text(f"Track `{OLD_COMMAND}`.\n")
    (root / "v0.5" / "ordinary.md").write_text(
        f"`{OLD_COMMAND}` changes, but `/{OLD_NAME}s` does not.\n"
    )
    (root / "v0.5" / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md").write_text(
        f"Keep `{OLD_COMMAND}` here.\n"
    )
    (root / "analysis" / "rename-note.md").write_text(f"Keep `{OLD_COMMAND}` here.\n")
    (root / ".agents" / "note.md").write_text(f"Keep `{OLD_COMMAND}` here.\n")
    (root / ".playbook-base" / "note.md").write_text(f"Keep `{OLD_COMMAND}` here.\n")
    changelog = root / "v0.5" / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace(
        "## Unreleased\n", f"## Unreleased\n\nKeep `{OLD_COMMAND}` in historical changelog prose.\n", 1
    ))
    return root


class RenameUpstreamSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_dry_run_writes_nothing_and_reports_the_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}

            report = self.module.apply(root, old=OLD_NAME, new=NEW_NAME, upstream_version="v9.9.9", apply=False)

            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)
            self.assertIn("--- v0.5/upstream-skills.json", report.diff)
            self.assertIn(Path("v0.5/10-process/07-demo.md"), report.files)
            self.assertIn(Path("v0.5/91-demo-track.md"), report.files)

    def test_staging_excludes_git_and_unrelated_trees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            work, temporary = self.module.staged(
                root, old=OLD_NAME, new=NEW_NAME, upstream_version="v9.9.9"
            )
            try:
                self.assertFalse((work / ".git").exists())
                self.assertFalse((work / ".agents").exists())
                self.assertFalse((work / ".playbook-base").exists())
                self.assertFalse((work / "analysis" / "rename-note.md").exists())
                self.assertTrue((work / "analysis" / "STATUS.md").is_file())
            finally:
                temporary.cleanup()

    def test_context_marks_the_renamed_source_not_an_earlier_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            stage_path = root / "v0.5" / "10-process" / "07-demo.md"
            stage_path.write_text(f"Existing {NEW_COMMAND} comes first; rename {OLD_COMMAND} here.\n")

            self.module.apply(root, old=OLD_NAME, new=NEW_NAME, upstream_version="v9.9.9", apply=True)

            self.assertEqual(
                stage_path.read_text(),
                f"Existing {NEW_COMMAND} comes first; rename `{NEW_COMMAND}` (formerly `{OLD_COMMAND}`) here.\n",
            )

    def test_context_preserves_unquoted_and_backtick_delimiters(self) -> None:
        cases = (
            (f"Invoke {OLD_COMMAND} now.\n", f"Invoke `{NEW_COMMAND}` (formerly `{OLD_COMMAND}`) now.\n"),
            (f"Invoke `{OLD_COMMAND}` now.\n", f"Invoke `{NEW_COMMAND}` (formerly `{OLD_COMMAND}`) now.\n"),
            (f"Invoke ``{OLD_COMMAND}`` now.\n", f"Invoke ``{NEW_COMMAND}`` (formerly `{OLD_COMMAND}`) now.\n"),
        )
        for source, expected in cases:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                root = make_tree(Path(tmp))
                stage_path = root / "v0.5" / "10-process" / "07-demo.md"
                stage_path.write_text(source)

                self.module.apply(root, old=OLD_NAME, new=NEW_NAME, upstream_version="v9.9.9", apply=True)

                self.assertEqual(stage_path.read_text(), expected)

    def test_generated_only_stage_mention_keeps_context_outside_generated_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))
            renamed = "auto-planner"

            self.module.apply(root, old="autoplan", new=renamed, upstream_version="v9.9.9", apply=True)

            prereqs = (root / "v0.5" / "10-process" / "00-prereqs.md").read_text()
            context = f"`/{renamed}` (formerly `/autoplan`)"
            self.assertIn(context, prereqs)
            generated_opening = prereqs.index("<!-- generated: upstream/check-b -->")
            generated_command = prereqs.index(f"/{renamed}", generated_opening)
            self.assertLess(
                prereqs.index(context),
                generated_command,
            )
            check = subprocess.run(
                [
                    sys.executable,
                    str(root / "v0.5" / "scripts" / "generate-upstream-inventory.py"),
                    "--check",
                    "--root",
                    str(root),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_apply_has_exact_scope_and_inserts_formerly_at_first_stage_and_track_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = make_tree(Path(tmp))

            report = self.module.apply(root, old=OLD_NAME, new=NEW_NAME, upstream_version="v9.9.9", apply=True)

            self.assertEqual(
                set(report.files),
                {
                    Path("STATUS.md"),
                    Path("v0.5/10-process/07-demo.md"),
                    Path("v0.5/91-demo-track.md"),
                    Path("v0.5/CHANGELOG.md"),
                    Path("v0.5/ordinary.md"),
                    Path("v0.5/upstream-skills.json"),
                },
            )
            stage = (root / "v0.5" / "10-process" / "07-demo.md").read_text()
            self.assertEqual(
                stage.splitlines()[0],
                f"Use `{NEW_COMMAND}` (formerly `{OLD_COMMAND}`) first. Later `{NEW_COMMAND}` remains documented.",
            )
            self.assertNotIn("``", stage)
            self.assertIn(f"Later `{NEW_COMMAND}` remains", stage)
            self.assertIn(f"`{NEW_COMMAND}` (formerly `{OLD_COMMAND}`)", (root / "v0.5" / "91-demo-track.md").read_text())
            self.assertIn(f"`{NEW_COMMAND}` changes, but `/{OLD_NAME}s` does not", (root / "v0.5" / "ordinary.md").read_text())

            registry = json.loads((root / "v0.5" / "upstream-skills.json").read_text())
            self.assertNotIn(OLD_NAME, registry["skills"])
            renamed = registry["skills"][NEW_NAME]
            self.assertEqual(renamed["name"], NEW_NAME)
            self.assertEqual(renamed["upstream_path"], f"engineering/{NEW_NAME}")
            self.assertEqual(renamed["previous_names"][-1], {"name": OLD_NAME, "upstream_version": "v9.9.9"})
            draft = (root / "v0.5" / "CHANGELOG.md").read_text()
            self.assertIn("**Files touched:**", draft)
            self.assertIn("`v0.5/10-process/07-demo.md`", draft)
            self.assertIn("*Why:* [Human fill in why before committing.]", draft)
            self.assertIn("maintainer-host §6.4 replay counts pending", draft)

            for relative in [
                Path("analysis/rename-note.md"),
                Path(".agents/note.md"),
                Path(".playbook-base/note.md"),
                Path("v0.5/skills/ai-playbook-upgrade-project/MIGRATIONS.md"),
            ]:
                self.assertIn(OLD_COMMAND, (root / relative).read_text(), relative)

    def test_cli_exits_zero_when_head_closes_the_dry_run_pipe(self) -> None:
        producer = subprocess.Popen(
            [
                sys.executable, str(SCRIPT), "--from", "/to-tickets", "--to", "/to-work-items",
                "--upstream-version", "v9.9.9",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert producer.stdout is not None
        head = subprocess.run(["head", "-n", "1"], stdin=producer.stdout, text=True, capture_output=True, check=False)
        producer.stdout.close()
        _, stderr = producer.communicate()
        self.assertEqual(head.returncode, 0)
        self.assertEqual(producer.returncode, 0, stderr)


if __name__ == "__main__":
    unittest.main()

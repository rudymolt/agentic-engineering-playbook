import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("check_links", SCRIPT_DIR / "check-links.py")
check_links = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_links)

NO_PLACEHOLDERS = frozenset()


def make_repo(tmp: Path) -> Path:
    """Minimal synthetic tree covering every reference kind the checker scans."""
    root = tmp / "repo"
    (root / "v0.5" / "templates").mkdir(parents=True)
    (root / "v0.5" / "templates" / "planning-template").mkdir()
    (root / "v0.5" / "skills" / "demo").mkdir(parents=True)
    (root / "bench").mkdir()

    (root / "README.md").write_text(
        "# Repo\n\nSee [the guide](v0.5/guide.md) and [external](https://example.com).\n"
    )
    (root / "index.html").write_text(
        '<html><body><a href="v0.5/guide.md">guide</a>'
        '<a href="#local-anchor">anchor</a></body></html>\n'
    )
    (root / "v0.5" / "guide.md").write_text("# Guide\n")
    (root / "v0.5" / "templates" / "CLAUDE.md").write_text("# CLAUDE template\n")
    (root / "v0.5" / "templates" / "planning-template" / "STATUS.md").write_text("0 active\n")
    (root / "v0.5" / "skills" / "demo" / "SKILL.md").write_text(
        "# Demo skill\n\nRead `CLAUDE.md` and `planning/STATUS.md` in the project. "
        "Templated paths like `{playbook-path}/v0.5/guide.md` are skipped.\n"
    )
    return root


class CheckLinksTest(unittest.TestCase):
    def check(self, root: Path, placeholders=NO_PLACEHOLDERS):
        return check_links.check_repo(root, placeholders=placeholders)

    def test_clean_tree_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            problems, files, refs = self.check(root)
            self.assertEqual(problems, [])
            self.assertGreaterEqual(files, 5)
            self.assertGreaterEqual(refs, 4)

    def test_broken_markdown_link_reports_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "README.md").write_text("line one\n\nSee [gone](v0.5/missing.md).\n")
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("README.md:3: broken link 'v0.5/missing.md' (missing)", problems[0])

    def test_broken_html_src_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "index.html").write_text('<img src="assets/ghost.png">\n')
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("broken link 'assets/ghost.png'", problems[0])

    def test_anchor_only_and_external_targets_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "guide.md").write_text(
                "[a](#section) [b](https://example.com/x.md) [c](mailto:x@y.z)\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(problems, [])

    def test_renamed_template_breaks_skill_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "templates" / "CLAUDE.md").unlink()
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("file reference 'CLAUDE.md' resolves to nothing", problems[0])

    def test_planning_prefix_resolves_against_planning_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "templates" / "planning-template" / "STATUS.md").unlink()
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("'planning/STATUS.md'", problems[0])

    def test_agents_skills_prefix_resolves_to_skill_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "skills" / "demo" / "scripts").mkdir()
            (root / "v0.5" / "skills" / "demo" / "scripts" / "helper.py").write_text("pass\n")
            skill = root / "v0.5" / "skills" / "demo" / "SKILL.md"
            skill.write_text(
                skill.read_text()
                + "Installed at `.agents/skills/demo/scripts/helper.py`.\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(problems, [])

            (root / "v0.5" / "skills" / "demo" / "scripts" / "helper.py").unlink()
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("'.agents/skills/demo/scripts/helper.py'", problems[0])

    def test_prose_backtick_reference_into_real_dir_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "stage.md").write_text(
                "Use `templates/ghost.md` as the structure.\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("stage.md:1: file reference 'templates/ghost.md'", problems[0])

    def test_prose_reference_to_hypothetical_tree_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "stage.md").write_text(
                "Projects keep ADRs in `docs/adr/NNNN-short-title.md`, results in\n"
                "`meettrack/results.py`, and absolute examples like `/tables/customers.md`.\n"
                "Bare names such as `CLAUDE.md` are fine in prose too.\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(problems, [])

    def test_changelog_prose_references_are_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "v0.5" / "CHANGELOG.md").write_text(
                "## V0.0.1\n\n- Renamed `templates/old-name.md` to `templates/CLAUDE.md`.\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(problems, [])

    def test_placeholder_must_stay_missing_and_referenced(self):
        placeholders = frozenset({"XXXX-example.md"})
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            guide = root / "v0.5" / "guide.md"

            # referenced + missing: clean
            guide.write_text("Copy [the pattern](XXXX-example.md).\n")
            problems, _, _ = self.check(root, placeholders)
            self.assertEqual(problems, [])

            # placeholder became a real file: fails
            (root / "v0.5" / "XXXX-example.md").write_text("now real\n")
            problems, _, _ = self.check(root, placeholders)
            self.assertEqual(len(problems), 1)
            self.assertIn("now matches a real file", problems[0])

            # no longer referenced anywhere: fails as stale allowlist
            (root / "v0.5" / "XXXX-example.md").unlink()
            guide.write_text("No links here.\n")
            problems, _, _ = self.check(root, placeholders)
            self.assertEqual(len(problems), 1)
            self.assertIn("no longer referenced anywhere", problems[0])

    def test_excluded_trees_are_not_scanned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "bench" / "results").mkdir()
            (root / "bench" / "results" / "SUMMARY.md").write_text("[gone](nope.md)\n")
            (root / "analysis").mkdir()
            (root / "analysis" / "old-plan.md").write_text("[gone](nope.md)\n")
            (root / "v0.1").mkdir()
            (root / "v0.1" / "README.md").write_text("[gone](nope.md)\n")
            problems, _, _ = self.check(root)
            self.assertEqual(problems, [])

    def test_real_repo_is_clean(self):
        problems, files, refs = check_links.check_repo(check_links.ROOT)
        self.assertEqual(problems, [], problems)
        self.assertGreater(files, 100)
        self.assertGreater(refs, 200)


    def test_project_layout_heads_never_anchor_at_repo_root(self):
        """The repository runs its own playbook, so a real planning/ and docs/
        exist at the root. Playbook prose using those heads describes a target
        project and stays skipped; other root trees still anchor and are
        checked."""
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp))
            (root / "planning").mkdir()
            (root / "docs").mkdir()
            (root / "analysis").mkdir()
            (root / "v0.5" / "guide.md").write_text(
                "# Guide\n\nOpen `planning/example/spec.md`, then `docs/adr/0009-x.md`, "
                "then `analysis/missing-note.md`.\n"
            )
            problems, _, _ = self.check(root)
            self.assertEqual(len(problems), 1, problems)
            self.assertIn("analysis/missing-note.md", problems[0])


if __name__ == "__main__":
    unittest.main()

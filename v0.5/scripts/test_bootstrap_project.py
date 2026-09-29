import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PLAYBOOK_ROOT = SCRIPT_DIR.parents[1]
spec = importlib.util.spec_from_file_location("bootstrap_project", SCRIPT_DIR / "bootstrap-project.py")
bootstrap_project = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bootstrap_project)
upgrade_spec = importlib.util.spec_from_file_location(
    "upgrade_project_for_bootstrap", SCRIPT_DIR / "upgrade-project.py"
)
upgrade_project = importlib.util.module_from_spec(upgrade_spec)
assert upgrade_spec.loader is not None
upgrade_spec.loader.exec_module(upgrade_project)


class BootstrapProjectTest(unittest.TestCase):
    def test_full_non_ui_project_is_bootstrapped_and_second_run_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "new-project"
            project.mkdir()

            first = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="New Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 10),
            )

            state = (project / ".playbook-state.yml").read_text()
            self.assertIn(
                f"playbook_version: {bootstrap_project.current_version(PLAYBOOK_ROOT)}", state
            )
            self.assertIn("planning: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }", state)
            self.assertIn("implementation: { model_id: gpt-6.1-sol, runner: codex, reasoning: medium }", state)
            self.assertIn("verification: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }", state)
            self.assertIn("escalated_repair: { model_id: gpt-6-astra, runner: codex, reasoning: high,", state)
            self.assertIn("no_ui: true", state)
            self.assertIn("prereqs_required: true", state)
            self.assertIn("retro: 2026-07-10", state)
            self.assertIn("learnings_refresh: 2026-07-10", state)
            self.assertIn("kitchen_sink_drift_audit: null", state)
            self.assertIn("verification_harness_path: null", state)
            self.assertIn("verification_map_maintenance: false", state)
            self.assertIn("verification_harness_binding: null", state)
            self.assertIn("verification_map_enabled: null", state)
            self.assertIn("verification_map_maintenance: null", state)
            self.assertIn("computed_at:", state)
            self.assertNotIn("computed_at: null", state)
            self.assertTrue((project / "planning" / "STATUS.md").exists())
            self.assertTrue((project / "archive" / "STATUS.md").exists())
            self.assertTrue((project / "ci-gates.md").exists())
            self.assertIn("Time-to-merge (med/max)", (project / "retro-template.md").read_text())
            self.assertIn("Observational eval baseline", (project / "field-report.md").read_text())
            self.assertIn(".playbook-routing/", (project / ".gitignore").read_text())
            claude = (project / "CLAUDE.md").read_text()
            self.assertIn(str(PLAYBOOK_ROOT), claude)
            self.assertIn("Playbook version:** V0.5", claude)
            self.assertIn("The full playbook V0.5", claude)
            self.assertNotIn("{path-to-playbook}", claude)
            self.assertNotIn("{playbook-path}", (project / "AGENTS.md").read_text())
            self.assertTrue((project / ".agents" / "skills" / "whats-next" / "SKILL.md").exists())
            self.assertTrue(
                (project / ".agents" / "skills" / "ai-playbook-design-review" / "SKILL.md").exists()
            )
            self.assertTrue(first.changed_files)
            self.assertEqual(first.manual_reviews, [])
            playbook_root_bytes = str(PLAYBOOK_ROOT).encode()
            planning_readme = (project / "planning" / "README.md").read_bytes()
            cadences = (project / "playbook-cadences.yml").read_bytes()
            self.assertEqual(planning_readme.count(playbook_root_bytes), 1)
            self.assertEqual(cadences.count(playbook_root_bytes), 1)
            self.assertNotIn(b"v0.4/", planning_readme)
            self.assertNotIn(b"v0.4/", cadences)

            before = {
                path.relative_to(project): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            }
            second = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="New Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 11),
            )
            after = {
                path.relative_to(project): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            }

            self.assertEqual(second.changed_files, [])
            self.assertEqual(second.manual_reviews, [])
            self.assertEqual(before, after)

    def test_cli_plan_is_read_only_and_lists_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "planned-project"
            project.mkdir()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "bootstrap-project.py"),
                    str(project),
                    "--playbook-path",
                    str(PLAYBOOK_ROOT),
                    "--project-name",
                    "Planned Project",
                    "--ui",
                    "no",
                    "--ci",
                    "copy",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("create: CLAUDE.md", completed.stdout)
            self.assertIn("UI: no UI", completed.stdout)
            self.assertIn("Optional skills (not installed): none", completed.stdout)
            self.assertIn("Gitignore: add .playbook-routing/", completed.stdout)
            self.assertEqual(list(project.iterdir()), [])

    def test_existing_project_content_is_preserved_and_blocks_certification(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "existing-project"
            project.mkdir()
            claude = project / "CLAUDE.md"
            claude.write_text("# Existing contract\n\nNever replace this.\n")

            report = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="Existing Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 10),
            )

            self.assertEqual(claude.read_text(), "# Existing contract\n\nNever replace this.\n")
            self.assertTrue(any("CLAUDE.md" in review for review in report.manual_reviews))
            blocked_state = (project / ".playbook-state.yml").read_text()
            self.assertIn("playbook_version: null", blocked_state)
            self.assertIn("retro: 2026-07-10", blocked_state)
            self.assertIn("learnings_refresh: 2026-07-10", blocked_state)

            merged = (PLAYBOOK_ROOT / "v0.5" / "templates" / "CLAUDE.md").read_text()
            merged = merged.replace("{path-to-playbook}", str(PLAYBOOK_ROOT))
            merged = merged.replace("{project name}", "Existing Project")
            claude.write_text(merged + "\n## Existing project rule\n\nNever replace this.\n")

            completed = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="Existing Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 20),
            )

            self.assertEqual(completed.manual_reviews, [])
            self.assertIn("Never replace this.", claude.read_text())
            completed_state = (project / ".playbook-state.yml").read_text()
            self.assertIn(
                f"playbook_version: {bootstrap_project.current_version(PLAYBOOK_ROOT)}",
                completed_state,
            )
            self.assertIn("retro: 2026-07-10", completed_state)
            self.assertIn("learnings_refresh: 2026-07-10", completed_state)

    def test_ui_defaults_and_existing_ci_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "ui-project"
            project.mkdir()
            ci = project / "ci-gates.md"
            ci.write_text("# Existing CI mapping\n")

            report = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="UI Project",
                ui="defaults",
                ci="existing",
                today=date(2026, 7, 10),
            )

            self.assertEqual(ci.read_text(), "# Existing CI mapping\n")
            self.assertTrue((project / "DESIGN-GLOSSARY.md").exists())
            self.assertTrue((project / "ui-kitchen-sink.html").exists())
            self.assertTrue((project / "frontend-design-language-guide.html").exists())
            state = (project / ".playbook-state.yml").read_text()
            self.assertIn("no_ui: false", state)
            self.assertIn("kitchen_sink_drift_audit: 2026-07-10", state)
            self.assertIn("implementation: { model_id: gpt-6.1-sol, runner: codex, reasoning: medium }", state)
            self.assertIn("verification: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }", state)
            self.assertEqual(report.manual_reviews, [])


class ModelDefaultsUpgradeTest(unittest.TestCase):
    def state(self):
        return (PLAYBOOK_ROOT / "v0.5" / "templates" / ".playbook-state.yml").read_text()

    def test_shipped_defaults_upgrade_without_changing_selected_routes(self):
        for old_defaults in (upgrade_project.PRE_V038_MODEL_DEFAULTS,
                             upgrade_project.V038_MODEL_DEFAULTS,
                             upgrade_project.PRE_V061_MODEL_DEFAULTS):
            with self.subTest(defaults=old_defaults):
                history = "\nselected_routes:\n" + old_defaults + "\n"
                original = self.state().replace(upgrade_project.CURRENT_MODEL_DEFAULTS, old_defaults) + history
                migrated = upgrade_project.migrate_state(original, upgrade_project.UpgradeReport(), 0)
                self.assertIn(upgrade_project.CURRENT_MODEL_DEFAULTS, migrated)
                self.assertTrue(migrated.endswith(history))
                self.assertIn("escalated_repair: { model_id: gpt-6-astra, runner: codex, reasoning: high,", migrated)
                self.assertEqual(migrated, upgrade_project.migrate_state(migrated, upgrade_project.UpgradeReport(), 0))

    def test_customized_defaults_and_historical_default_tuple_are_preserved(self):
        custom = upgrade_project.PRE_V061_MODEL_DEFAULTS.replace("runner: codex", "runner: opencode", 1)
        for old_defaults in (upgrade_project.PRE_V038_MODEL_DEFAULTS,
                             upgrade_project.V038_MODEL_DEFAULTS,
                             upgrade_project.PRE_V061_MODEL_DEFAULTS):
            with self.subTest(defaults=old_defaults):
                history = "\nselected_routes:\n" + old_defaults + "\n"
                original = self.state().replace(upgrade_project.CURRENT_MODEL_DEFAULTS, custom) + history
                migrated = upgrade_project.migrate_state(original, upgrade_project.UpgradeReport(), 0)
                self.assertIn(custom, migrated)
                self.assertTrue(migrated.endswith(history))


class BootstrapProvenanceTest(unittest.TestCase):
    def test_fresh_bootstrap_records_bases_and_provenance_matching_installed_files(self):
        sys.path.insert(0, str(SCRIPT_DIR))
        import template_base

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "new-project"
            project.mkdir()
            report = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="New Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 19),
            )
            self.assertEqual(report.manual_reviews, [])

            state = (project / ".playbook-state.yml").read_text()
            record = template_base.read_provenance(state)
            self.assertEqual(record["project_name"], "New Project")
            expected_managed = {
                relative
                for relative in template_base.managed_files(PLAYBOOK_ROOT)
                if (project / relative).exists()
            }
            self.assertEqual(set(record["files"]), expected_managed)
            for relative in sorted(expected_managed):
                base_path = project / template_base.BASE_DIR / relative
                self.assertTrue(base_path.exists(), relative)
                # fresh install: base snapshot and installed file are identical,
                # and the recorded hash matches the snapshot
                self.assertEqual(base_path.read_text(), (project / relative).read_text(), relative)
                self.assertEqual(
                    record["files"][relative]["base_sha256"],
                    template_base.sha256_text(base_path.read_text()),
                    relative,
                )
            self.assertTrue((project / template_base.BASE_DIR / "README.md").exists())

    def test_fresh_bootstrap_is_already_current_for_same_day_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "new-project"
            project.mkdir()
            bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name="New Project",
                ui="no",
                ci="copy",
                today=date(2026, 7, 19),
            )

            report = upgrade_project.upgrade_project(project, date(2026, 7, 19))

            self.assertEqual(report.changed_files, [])
            self.assertEqual(report.manual_reviews, [])
            self.assertIn(
                f"playbook_version: {upgrade_project.CURRENT_VERSION}",
                (project / ".playbook-state.yml").read_text(),
            )

    def test_project_name_with_yaml_punctuation_round_trips_safely(self):
        sys.path.insert(0, str(SCRIPT_DIR))
        import playbook_state
        import template_base

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "new-project"
            project.mkdir()
            report = bootstrap_project.bootstrap_project(
                project,
                PLAYBOOK_ROOT,
                project_name='Research: Alpha #1 "quoted"',
                ui="no",
                ci="copy",
                today=date(2026, 7, 19),
            )

            state = (project / ".playbook-state.yml").read_text()
            self.assertEqual(report.manual_reviews, [])
            self.assertIn('project_name: "Research: Alpha #1 \\"quoted\\""', state)
            self.assertEqual(
                template_base.read_provenance(state)["project_name"],
                'Research: Alpha #1 "quoted"',
            )
            self.assertEqual(
                [problem for problem in playbook_state.validate_state(state)
                 if not problem.advisory],
                [],
            )

    def test_project_name_with_control_character_is_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "new-project"

            with self.assertRaisesRegex(ValueError, "single line"):
                bootstrap_project.bootstrap_project(
                    project,
                    PLAYBOOK_ROOT,
                    project_name="Alpha\nmalicious: true",
                    ui="no",
                    ci="copy",
                    today=date(2026, 7, 19),
                )

            self.assertFalse(project.exists())


if __name__ == "__main__":
    unittest.main()

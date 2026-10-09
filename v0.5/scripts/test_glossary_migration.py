"""Exercise data preservation, failure boundaries and interrupted domain renames."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import template_base
import glossary_migration


class GlossaryMigrationTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name)
        self.base = "# CONTEXT.md — Example\n\n> The domain glossary for this project.\n"
        self.custom = self.base + "\n### Customer\n\nAn organisation that purchases a subscription.\n"
        (self.project / "CONTEXT.md").write_text(self.custom)
        (self.project / ".playbook-base").mkdir()
        (self.project / ".playbook-base/CONTEXT.md").write_text(self.base)
        self.state = template_base.upsert_provenance(
            "playbook_version: V0.5.0\nprereqs_required: false\ncustom_setting: keep\n",
            {"schema": 1, "project_name": "Example", "files": {
                "CONTEXT.md": template_base.provenance_entry(
                    "v0.5/templates/CONTEXT.md", "V0.5.0", self.base)}})
        (self.project / ".playbook-state.yml").write_text(self.state)

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes()
                for p in self.project.rglob("*") if p.is_file()}

    def test_rename_preserves_custom_terms_base_and_unrelated_state(self):
        glossary_migration.migrate(self.project)
        self.assertFalse((self.project / "CONTEXT.md").exists())
        self.assertEqual((self.project / "GLOSSARY.md").read_text(), self.custom)
        self.assertEqual((self.project / ".playbook-base/GLOSSARY.md").read_text(), self.base)
        state = (self.project / ".playbook-state.yml").read_text()
        self.assertIn("custom_setting: keep", state)
        self.assertIn("prereqs_required: true", state)
        record = template_base.read_provenance(state)
        self.assertNotIn("CONTEXT.md", record["files"])
        self.assertEqual(record["files"]["GLOSSARY.md"]["base_sha256"], template_base.sha256_text(self.base))
        before = self.snapshot()
        self.assertEqual(glossary_migration.migrate(self.project), [])
        self.assertEqual(self.snapshot(), before)

    def test_plan_is_read_only(self):
        before = self.snapshot()
        self.assertTrue(glossary_migration.migrate(self.project, apply=False))
        self.assertEqual(self.snapshot(), before)

    def test_ambiguous_sources_block_without_writes(self):
        for kind in ("collision", "edited-base", "missing-base", "map", "symlink", "unowned"):
            with self.subTest(kind=kind):
                with tempfile.TemporaryDirectory() as directory:
                    import shutil
                    project = Path(directory) / "project"
                    shutil.copytree(self.project, project)
                    if kind == "collision":
                        (project / "GLOSSARY.md").write_text("already owned")
                    elif kind == "edited-base":
                        (project / ".playbook-base/CONTEXT.md").write_text("edited")
                    elif kind == "missing-base":
                        (project / ".playbook-base/CONTEXT.md").unlink()
                    elif kind == "map":
                        (project / "CONTEXT-MAP.md").write_text("[Ordering](ordering/CONTEXT.md)")
                    elif kind == "symlink":
                        (project / "CONTEXT.md").unlink()
                        (project / "CONTEXT.md").symlink_to(self.project / "CONTEXT.md")
                    else:
                        (project / ".playbook-state.yml").write_text("playbook_version: V0.5.0\n")
                    with self.assertRaises(glossary_migration.MigrationReview):
                        glossary_migration.migrate(project)
                    self.assertFalse((project / glossary_migration.JOURNAL).exists())

    def test_recovery_after_every_write_boundary(self):
        import shutil
        original = glossary_migration.write_value
        for boundary in range(1, 7):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                shutil.copytree(self.project, project)
                count = 0
                def interrupt(path, value):
                    nonlocal count
                    original(path, value)
                    count += 1
                    if count == boundary:
                        raise OSError("simulated interruption")
                with patch.object(glossary_migration, "write_value", side_effect=interrupt):
                    with self.assertRaises(OSError):
                        glossary_migration.migrate(project)
                glossary_migration.migrate(project)
                self.assertEqual((project / "GLOSSARY.md").read_text(), self.custom)
                self.assertFalse((project / glossary_migration.JOURNAL).exists())
                self.assertEqual(glossary_migration.migrate(project), [])

    def test_interrupted_recovery_preserves_new_local_edits(self):
        original = glossary_migration.write_value
        def interrupt(path, value):
            original(path, value)
            raise OSError("simulated interruption")
        with patch.object(glossary_migration, "write_value", side_effect=interrupt):
            with self.assertRaises(OSError):
                glossary_migration.migrate(self.project)
        (self.project / "GLOSSARY.md").write_text("new local edit")
        before = self.snapshot()
        with self.assertRaises(glossary_migration.MigrationReview):
            glossary_migration.migrate(self.project)
        self.assertEqual(self.snapshot(), before)

    def test_explicit_adoption_of_reviewed_manual_rename(self):
        (self.project / "CONTEXT.md").rename(self.project / "GLOSSARY.md")
        with self.assertRaises(glossary_migration.MigrationReview):
            glossary_migration.migrate(self.project)
        glossary_migration.migrate(self.project, accept_renamed=True)
        self.assertEqual((self.project / "GLOSSARY.md").read_text(), self.custom)
        self.assertEqual(glossary_migration.migrate(self.project), [])

    def test_reviewed_root_glossary_can_remain_a_map_member(self):
        (self.project / "CONTEXT.md").rename(self.project / "GLOSSARY.md")
        mapping = "[Shared](GLOSSARY.md)\n"
        (self.project / "GLOSSARY-MAP.md").write_text(mapping)
        with self.assertRaises(glossary_migration.MigrationReview):
            glossary_migration.migrate(self.project)
        glossary_migration.migrate(self.project, accept_renamed=True)
        self.assertEqual((self.project / "GLOSSARY-MAP.md").read_text(), mapping)
        self.assertEqual((self.project / "GLOSSARY.md").read_text(), self.custom)

    def test_recovery_blocks_domain_maps_added_during_interruption(self):
        original = glossary_migration.write_value
        def interrupt(path, value):
            original(path, value)
            raise OSError("interrupted after journal creation")
        with patch.object(glossary_migration, "write_value", side_effect=interrupt):
            with self.assertRaises(OSError):
                glossary_migration.migrate(self.project)
        for name in ("CONTEXT-MAP.md", "GLOSSARY-MAP.md"):
            with self.subTest(name=name):
                path = self.project / name
                path.write_text("[Root](CONTEXT.md)\n")
                before = self.snapshot()
                with self.assertRaises(glossary_migration.MigrationReview):
                    glossary_migration.migrate(self.project)
                self.assertEqual(self.snapshot(), before)
                path.unlink()


class UpgradeIntegrationTest(unittest.TestCase):
    def load(self, filename):
        path = Path(__file__).parent / filename
        spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_bootstrap_upgrade_custom_glossary_and_idempotence(self):
        bootstrap = self.load("bootstrap-project.py")
        upgrade = self.load("upgrade-project.py")
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            bootstrap.bootstrap_project(project, root, project_name="Example", ui="no", ci="copy")
            # Recreate the legacy glossary and its pristine, recorded base.
            state_path = project / ".playbook-state.yml"
            record = template_base.read_provenance(state_path.read_text())
            for name in ("GLOSSARY.md", ".playbook-base/GLOSSARY.md"):
                p = project / name
                legacy = p.read_text().replace("GLOSSARY.md", "CONTEXT.md")
                p.unlink()
                (project / name.replace("GLOSSARY.md", "CONTEXT.md")).write_text(legacy)
            record["files"]["CONTEXT.md"] = record["files"].pop("GLOSSARY.md")
            entry = record["files"]["CONTEXT.md"]
            entry["template"] = "v0.5/templates/CONTEXT.md"
            entry["base_sha256"] = template_base.sha256_bytes((project / ".playbook-base/CONTEXT.md").read_bytes())
            state_path.write_text(template_base.upsert_provenance(state_path.read_text(), record))
            with (project / "CONTEXT.md").open("a") as stream:
                stream.write("\n### Subscriber\nA customer with an active subscription.\n")
            result = upgrade.upgrade_project(project)
            self.assertEqual(result.manual_reviews, [])
            self.assertIn("A customer with an active subscription.", (project / "GLOSSARY.md").read_text())
            self.assertNotIn("CONTEXT.md", (project / "GLOSSARY.md").read_text())
            self.assertFalse((project / "CONTEXT.md").exists())
            self.assertEqual(upgrade.upgrade_project(project).changed_files, [])

    def test_bootstrap_refuses_competing_glossary(self):
        bootstrap = self.load("bootstrap-project.py")
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "CONTEXT.md").write_text("User vocabulary")
            result = bootstrap.bootstrap_project(project, root, project_name="Example", ui="no", ci="copy")
            self.assertTrue(result.manual_reviews)
            self.assertEqual(list(project.iterdir()), [project / "CONTEXT.md"])

    def test_reviewed_mapped_project_preserves_domain_boundaries(self):
        bootstrap = self.load("bootstrap-project.py")
        upgrade = self.load("upgrade-project.py")
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            bootstrap.bootstrap_project(project, root, project_name="Example", ui="no", ci="copy")
            # The owner adopted a mapped layout; these docs have no managed base.
            state_path = project / ".playbook-state.yml"
            record = template_base.read_provenance(state_path.read_text())
            del record["files"]["GLOSSARY.md"]
            state_path.write_text(template_base.upsert_provenance(state_path.read_text(), record))
            (project / "GLOSSARY.md").unlink()
            (project / ".playbook-base/GLOSSARY.md").unlink()
            (project / "ordering").mkdir()
            (project / "ordering/CONTEXT.md").write_text("### Order\nAn accepted purchase.\n")
            (project / "CONTEXT-MAP.md").write_text("[Ordering](ordering/CONTEXT.md)\n")
            result = upgrade.upgrade_project(project)
            self.assertTrue(result.manual_reviews)
            self.assertFalse(result.changed_files)
            # Perform the documented tier-3 content/link review, then retry.
            (project / "ordering/CONTEXT.md").rename(project / "ordering/GLOSSARY.md")
            (project / "CONTEXT-MAP.md").unlink()
            (project / "GLOSSARY-MAP.md").write_text("[Ordering](ordering/GLOSSARY.md)\n")
            for name in ("AGENTS.md", "CLAUDE.md"):
                p = project / name
                p.write_text(p.read_text().replace("`GLOSSARY.md`", "`GLOSSARY-MAP.md`"))
            result = upgrade.upgrade_project(project)
            self.assertEqual(result.manual_reviews, [])
            self.assertFalse((project / "GLOSSARY.md").exists())
            self.assertEqual((project / "ordering/GLOSSARY.md").read_text(), "### Order\nAn accepted purchase.\n")
            self.assertEqual(upgrade.upgrade_project(project).changed_files, [])


if __name__ == "__main__":
    unittest.main()

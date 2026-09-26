import importlib.util
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[1]
SPEC = importlib.util.spec_from_file_location("compute_status", SCRIPT_DIR / "compute-status.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


class PublicStatusTest(unittest.TestCase):
    def project(self, directory: Path) -> Path:
        project = directory / "project"
        project.mkdir()
        for name in (".playbook-state.yml", "playbook-cadences.yml"):
            shutil.copyfile(ROOT / "v0.5" / "templates" / name, project / name)
        return project

    def test_fresh_v05_project_has_current_empty_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.project(Path(tmp))
            MODULE.recompute_project(project, NOW)
            status = MODULE.parse_status_block((project / ".playbook-state.yml").read_text())
            self.assertEqual(status["features_by_stage"]["sliced"], 0)
            self.assertEqual(status["overdue"], [])
            self.assertTrue(MODULE.check_project(project, NOW)[0])

    def test_sliced_public_feature_is_visible_and_stale_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.project(Path(tmp))
            state = project / ".playbook-state.yml"
            text = state.read_text().replace("  slices_open: 0", "  slices_open: 1")
            text = text.replace("active_features: []", "active_features:\n  - slug: public-example\n    status: sliced\n    opened: 2026-09-26\n    slices: 1\n    slices_open: 1")
            state.write_text(text)
            MODULE.recompute_project(project, NOW)
            status = MODULE.parse_status_block(state.read_text())
            self.assertEqual(status["features_by_stage"]["sliced"], 1)
            self.assertTrue(MODULE.check_project(project, NOW)[0])
            state.write_text(state.read_text().replace('  headline: "nothing overdue;', '  headline: "stale;', 1))
            self.assertFalse(MODULE.check_project(project, NOW)[0])


if __name__ == "__main__":
    unittest.main()

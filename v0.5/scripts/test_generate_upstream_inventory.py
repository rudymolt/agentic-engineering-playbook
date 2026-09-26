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
SCRIPT = ROOT / "v0.5" / "scripts" / "generate-upstream-inventory.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_upstream_inventory", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GenerateUpstreamInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def test_check_on_real_tree_has_no_drift(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(self.module.apply(ROOT, check=True), [])

    def test_apply_rewrites_only_drifted_region(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            shutil.copytree(ROOT / "v0.5", root / "v0.5")
            shutil.copy2(ROOT / ".playbook-maintenance.yml", root / ".playbook-maintenance.yml")

            registry = root / "v0.5" / "upstream-skills.json"
            payload = json.loads(registry.read_text())
            payload["skills"]["proof-skill"] = {
                "package": "playbook",
                "status": "current",
                "invocation": "model",
                "tier": "core",
                "lanes": [],
                "stages": [],
                "install_by_default": False,
                "previous_names": [],
                "provenance": None,
            }
            registry.write_text(json.dumps(payload, indent=2) + "\n")

            prereqs = root / "v0.5" / "10-process" / "00-prereqs.md"
            before = prereqs.read_text()
            readme = root / "v0.5" / "skills" / "README.md"
            before_readme = readme.read_text()
            checked = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root), "--check"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(checked.returncode, 1, checked.stdout + checked.stderr)
            self.assertIn("local-skills", checked.stdout)
            self.assertEqual(self.module.apply(root, check=False), ["local-skills"])
            after_readme = readme.read_text()
            self.assertIn("  proof-skill, model", after_readme)
            self.assertEqual(prereqs.read_text(), before)
            opening = "<!-- generated: upstream/local-skills -->"
            closing = "<!-- /generated: upstream/local-skills -->"
            self.assertEqual(
                before_readme[:before_readme.index(opening) + len(opening)],
                after_readme[:after_readme.index(opening) + len(opening)],
            )
            self.assertEqual(
                before_readme[before_readme.index(closing):],
                after_readme[after_readme.index(closing):],
            )

    def test_replace_region_rejects_missing_or_duplicate_markers(self) -> None:
        with self.assertRaises(self.module.RegionError):
            self.module.replace_region("no markers\n", "check-a", "body")
        duplicated = "\n".join([
            "<!-- generated: upstream/check-a -->", "old", "<!-- /generated: upstream/check-a -->",
            "<!-- generated: upstream/check-a -->", "old", "<!-- /generated: upstream/check-a -->",
        ])
        with self.assertRaises(self.module.RegionError):
            self.module.replace_region(duplicated, "check-a", "body")

    def test_provenance_includes_versioned_gstack_pin_after_slice_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upstream-skills.json"
            payload = json.loads((ROOT / "v0.5" / "upstream-skills.json").read_text())
            payload["packages"]["gstack"]["pin"] = {
                "kind": "commit+version",
                "value": "1.62.0.0",
                "commit": "d078622b73539fc1a7a27e709861e9b6b058ae98",
                "verified": "2026-09-08",
            }
            path.write_text(json.dumps(payload))
            registry = self.module.upstream_registry.load(path)
            manifest = self.module.load_compatibility_manifest(
                ROOT / "v0.5" / "upstream-integrations.json"
            )
            provenance = self.module.render_regions(
                registry, self.module.inventory_values(registry, manifest)
            )["provenance"]
            self.assertIn(
                "The gstack inventory was last verified on 2026-09-08 against the "
                "installed checkout at 1.62.0.0 (d078622).",
                provenance,
            )


if __name__ == "__main__":
    unittest.main()

"""Reusable legacy routes through Configure and the bootstrap seed boundary."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from bootstrap_seed import apply_seed, preview_seed
from playbook_config import Configuration, ConfigError, ROLES, encoded


NOW = "2026-10-01T12:00:00Z"
METADATA = {"provider": "observed-provider", "label": "Observed route", "thinking": True}


class BootstrapSeedRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "existing"
        self.project.mkdir()
        self.runtime = (
            "model_routing:\n  defaults:\n"
            "    escalated_repair: {model_id: gpt-6.1-sol, runner: codex, reasoning: high, "
            "trigger_unsuccessful_repairs: 5, cycles_per_slice: 2, scope: approved_slice, "
            "authority: diagnose_and_implement}\n"
            "pending_model_routes: [{status: approved}]\nactive_features: [{routing: retained}]\n"
            "history: {failures: 9}\n"
        ).encode()
        (self.project / ".playbook-state.yml").write_bytes(self.runtime)
        (self.project / "approval.json").write_bytes(b'{"approved":true}\n')
        self.local = self.root / "personal"
        self.local.mkdir()
        (self.local / "preferences.json").write_bytes(encoded({
            "schema_version": 1, "presentation": "guided", "billing": "unknown"}))
        self.routes = [{"model_id": "gpt-6.1-sol", "runner": "codex", "reasoning": reasoning,
                        "roles": list(ROLES), **METADATA} for reasoning in ("medium", "high")]
        self.service = Configuration(self.project, self.discover, lambda: NOW,
                                     preferences_dir=self.local, context={"goal": "Fixture"})

    def discover(self, request):
        return {"request_id": request["request_id"], "checked_at": request["started_at"],
                "authority": "host-reported-selection", "revision": "fixture-1",
                "routes": deepcopy(self.routes)}

    def save(self, preset):
        proposal = self.service.read()
        self.assertEqual(proposal["unavailable_roles"], [])
        proposal = self.service.reply(proposal, "Save preset Focus" if preset else "Save defaults")
        result = self.service.reply(proposal, "Apply preference")
        self.assertEqual(result["state"], "proposal_ready", result)
        self.assertFalse(result.get("launched", False))
        personal = json.loads((self.local / "preferences.json").read_text())
        return personal["presets"]["Focus"] if preset else personal["defaults"]

    def target(self, name):
        target = self.root / name
        target.mkdir()
        return target

    def preview(self, target, preset):
        return preview_seed(target, self.local, self.discover, lambda: NOW, "Focus" if preset else None)

    def apply(self, target, preview):
        state = target / ".playbook-state.yml"
        state.write_bytes(self.runtime)
        info = target.stat()
        identity = {"resolved": str(target.resolve()), "device": info.st_dev, "inode": info.st_ino}
        try:
            apply_seed(target, self.local, self.discover, preview, lambda: NOW, project_identity=identity)
        finally:
            self.assertEqual(state.read_bytes(), self.runtime)

    def intact(self, personal):
        self.assertEqual((self.local / "preferences.json").read_bytes(), personal)
        self.assertEqual((self.project / ".playbook-state.yml").read_bytes(), self.runtime)
        self.assertEqual((self.project / "approval.json").read_bytes(), b'{"approved":true}\n')
        self.assertFalse((self.project / ".playbook-config.json").exists())

    def test_saved_defaults_and_named_presets_seed_without_enrichment(self):
        for preset in (False, True):
            for metadata in ({}, METADATA):
                with self.subTest(preset=preset, metadata=metadata):
                    for route in self.routes:
                        for key in METADATA:
                            route.pop(key, None)
                        route.update(metadata)
                    saved = self.save(preset)
                    personal = (self.local / "preferences.json").read_bytes()
                    target = self.target(f"new-{preset}-{bool(metadata)}")
                    preview = self.preview(target, preset)
                    self.assertEqual(preview["after"], saved)
                    self.assertFalse((target / ".playbook-config.json").exists())
                    self.apply(target, preview)
                    self.assertEqual(json.loads((target / ".playbook-config.json").read_text()), saved)
                    for choice in saved["models"].values():
                        for key in METADATA:
                            self.assertNotIn(key, choice)
                    self.assertEqual(saved["models"]["escalated_repair"]["trigger_unsuccessful_repairs"], 5)
                    self.assertEqual(saved["models"]["escalated_repair"]["cycles_per_slice"], 2)
                    self.intact(personal)

    def test_saved_optional_identity_constraints_require_exact_match(self):
        for preset in (False, True):
            self.save(preset)
            path = self.local / "preferences.json"
            preferences = json.loads(path.read_text())
            candidate = preferences["presets"]["Focus"] if preset else preferences["defaults"]
            candidate["models"]["implementation"].update(METADATA)
            path.write_bytes(encoded(preferences))
            personal = path.read_bytes()
            target = self.target(f"explicit-{preset}")
            preview = self.preview(target, preset)
            self.apply(target, preview)
            self.assertEqual(json.loads((target / ".playbook-config.json").read_text()), candidate)
            for key in METADATA:
                for missing in (False, True):
                    with self.subTest(preset=preset, key=key, missing=missing):
                        routes = deepcopy(self.routes)
                        for route in self.routes:
                            if missing:
                                route.pop(key)
                            else:
                                route[key] = False if key == "thinking" else "different"
                        rejected = self.target(f"reject-{preset}-{key}-{missing}")
                        with self.assertRaises(ConfigError):
                            self.preview(rejected, preset)
                        self.assertEqual(list(rejected.iterdir()), [])
                        self.routes = routes
                        self.intact(personal)

    def test_cli_preview_and_approved_publication_preserve_reusable_values(self):
        adapter = self.root / "adapter.py"
        adapter.write_text(
            "import json,sys\nrequest=json.load(sys.stdin)\n"
            "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
            "'authority':'host-reported-selection','revision':'fixture-1','routes':"
            + repr(self.routes) + "},sys.stdout)\n")
        for preset in (False, True):
            with self.subTest(preset=preset):
                saved = self.save(preset)
                personal = (self.local / "preferences.json").read_bytes()
                target = self.root / f"cli-{preset}"
                command = [sys.executable, str(Path(__file__).with_name("bootstrap-project.py")),
                           str(target), "--playbook-path", str(Path(__file__).resolve().parents[2]),
                           "--project-name", "Fixture", "--ui", "no", "--ci", "copy",
                           "--preferences-dir", str(self.local), "--discovery-command",
                           json.dumps([sys.executable, str(adapter)]), "--now", NOW]
                if preset:
                    command += ["--preset", "Focus"]
                plan = subprocess.run(command, text=True, capture_output=True)
                self.assertEqual(plan.returncode, 0, plan.stdout + plan.stderr)
                preview = json.loads(plan.stdout[plan.stdout.index('{\n'):])
                self.assertEqual(preview["after"], saved)
                self.assertFalse(target.exists())
                denied = subprocess.run([*command, "--apply"], text=True, capture_output=True)
                self.assertEqual(denied.returncode, 2, denied.stdout + denied.stderr)
                self.assertFalse(target.exists())
                applied = subprocess.run([*command, "--apply", "--seed-revision", preview["seed_revision"]],
                                         text=True, capture_output=True)
                self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
                self.assertEqual(json.loads((target / ".playbook-config.json").read_text()), saved)
                self.intact(personal)

    def test_missing_ambiguous_and_unadmitted_routes_block_preview_and_apply(self):
        for preset in (False, True):
            self.save(preset)
            personal = (self.local / "preferences.json").read_bytes()
            original = deepcopy(self.routes)
            for failure in ("missing", "ambiguous", "role"):
                with self.subTest(preset=preset, failure=failure):
                    target = self.target(f"drift-{preset}-{failure}")
                    preview = self.preview(target, preset)
                    if failure == "missing":
                        self.routes = []
                    elif failure == "ambiguous":
                        self.routes.append({**self.routes[0], "provider": "other-provider"})
                    else:
                        for route in self.routes:
                            route["roles"] = ["planning"]
                    with self.assertRaises(ConfigError):
                        self.preview(target, preset)
                    self.assertFalse((target / ".playbook-config.json").exists())
                    with self.assertRaises(ConfigError):
                        self.apply(target, preview)
                    self.assertFalse((target / ".playbook-config.json").exists())
                    self.routes = deepcopy(original)
                    self.intact(personal)

    def test_drift_during_staging_invalidates_publication(self):
        for preset in (False, True):
            self.save(preset)
            personal = (self.local / "preferences.json").read_bytes()
            target = self.target(f"staging-{preset}")
            preview = self.preview(target, preset)
            original_routes = deepcopy(self.routes)
            initialize = Configuration.__init__

            def drift(point):
                if point == "before_replace":
                    self.routes.append({**self.routes[0], "label": "Second route"})

            def instrument(instance, *args, **kwargs):
                initialize(instance, *args, **kwargs)
                instance.checkpoint = drift

            with patch.object(Configuration, "__init__", instrument):
                with self.assertRaises(ConfigError):
                    self.apply(target, preview)
            self.assertFalse((target / ".playbook-config.json").exists())
            self.routes = original_routes
            self.intact(personal)


if __name__ == "__main__":
    unittest.main()

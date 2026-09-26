from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check-upstream-compatibility.py")
SPEC = importlib.util.spec_from_file_location("check_upstream_compatibility", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class UpstreamCompatibilityTests(unittest.TestCase):
    UNKNOWN_FALLBACK = "manual: stage 08 sample review"

    def fixture(self, *, compatible: bool = True) -> tuple[Path, Path]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        source = root / "SKILL.md"
        source.write_text("tested upstream instructions\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest = root / "upstream-integrations.json"
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "integrations": {
                        "sample-review": {
                            "upstream": "example/upstream",
            "tested_version": "v9.9.9",
                            "tested_source_sha256": digest,
                            "embedded_compatible": compatible,
                            "compatible_mode": "report-only" if compatible else "none",
                            "embedded_invocation": "/sample-review --report-only" if compatible else None,
                            "adapter": "/ai-playbook-sample-review",
                            "compatibility_evidence": "Official report-only entry point inspected.",
                            "required_outputs": ["evidence", "verdict"],
                            "permitted_side_effects": ["repository reads"],
                            "prohibited_side_effects": ["product edits", "commits"],
                            "fallback": "manual: stage 08 sample review",
                            "last_verified": "2026-08-01",
                        }
                    },
                }
            )
        )
        return manifest, source

    def test_exact_declared_report_only_source_is_compatible(self) -> None:
        manifest, source = self.fixture()
        decision = MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)
        self.assertEqual(decision.status, "compatible")
        self.assertTrue(decision.may_invoke)
        self.assertEqual(decision.embedded_invocation, "/sample-review --report-only")
        self.assertEqual(decision.fallback, "manual: stage 08 sample review")

    def test_known_incompatible_source_falls_back_even_when_hash_matches(self) -> None:
        manifest, source = self.fixture(compatible=False)
        decision = MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)
        self.assertEqual(decision.status, "incompatible")
        self.assertFalse(decision.may_invoke)
        self.assertEqual(decision.fallback, "manual: stage 08 sample review")

    def test_source_drift_fails_closed(self) -> None:
        manifest, source = self.fixture()
        source.write_text("changed upstream instructions\n")
        decision = MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)
        self.assertEqual(decision.status, "drifted")
        self.assertFalse(decision.may_invoke)
        self.assertIn("outside tested source", decision.reason)

    def test_unknown_integration_fails_closed_to_general_manual_route(self) -> None:
        manifest, source = self.fixture()
        decision = MODULE.evaluate("unknown-review", source, self.UNKNOWN_FALLBACK, manifest)
        self.assertEqual(decision.status, "unknown")
        self.assertFalse(decision.may_invoke)
        self.assertEqual(decision.fallback, self.UNKNOWN_FALLBACK)

    def test_missing_required_contract_field_is_manifest_error(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        del payload["integrations"]["sample-review"]["prohibited_side_effects"]
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "prohibited_side_effects"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_compatible_source_requires_an_explicit_embedded_invocation(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        payload["integrations"]["sample-review"]["embedded_invocation"] = None
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "embedded_invocation"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_empty_fallback_is_manifest_error(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        payload["integrations"]["sample-review"]["fallback"] = ""
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "fallback"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_empty_compatible_invocation_is_manifest_error(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        payload["integrations"]["sample-review"]["embedded_invocation"] = ""
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "embedded_invocation"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_digest_must_be_hex(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        payload["integrations"]["sample-review"]["tested_source_sha256"] = "z" * 64
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "SHA-256"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_last_verified_must_be_iso_date(self) -> None:
        manifest, source = self.fixture()
        payload = json.loads(manifest.read_text())
        payload["integrations"]["sample-review"]["last_verified"] = "yesterday"
        manifest.write_text(json.dumps(payload))
        with self.assertRaisesRegex(MODULE.ManifestError, "last_verified"):
            MODULE.evaluate("sample-review", source, self.UNKNOWN_FALLBACK, manifest)

    def test_live_matt_code_review_is_not_embedded_compatible(self) -> None:
        manifest = Path(__file__).resolve().parents[1] / "upstream-integrations.json"
        payload = MODULE.load_manifest(manifest)
        entry = payload["integrations"]["code-review"]
        self.assertFalse(entry["embedded_compatible"])
        self.assertEqual(entry["compatible_mode"], "none")
        self.assertIsNone(entry["embedded_invocation"])

    def test_live_matt_implement_wrapper_is_not_embedded_compatible(self) -> None:
        manifest = Path(__file__).resolve().parents[1] / "upstream-integrations.json"
        payload = MODULE.load_manifest(manifest)
        entry = payload["integrations"]["implement"]
        self.assertFalse(entry["embedded_compatible"])
        self.assertIn("nested incompatible reviewer", entry["prohibited_side_effects"])


if __name__ == "__main__":
    unittest.main()

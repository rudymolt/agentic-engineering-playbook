import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from verification_harness_fixture import create
from verification_harness_maintenance_fixture import accept_maintenance, audit, correct, verify_corrected


class VerificationHarnessMaintenanceFixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        self.root = create(self.project)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith(("VERIFY_", "FIXTURE_"))}
        self.env.update(VERIFY_HARNESS_AUTH="fixture-test-authorized",
                        VERIFY_EVIDENCE_DIR=str(self.root / "evidence"),
                        PYTHONDONTWRITEBYTECODE="1")

    def test_complete_real_source_and_live_coverage_is_clean_and_retains_all_entries(self):
        before = {path: path.read_bytes() for path in (self.root / "features").glob("*.md")}
        result = audit(self.root, environment=self.env)
        self.assertEqual(result["outcome"], "clean", result)
        self.assertEqual(result["covered"], ["create-note", "list-notes", "reject-broken"])
        self.assertEqual(len(result["evidence"]), 3)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        for locator in result["evidence"]:
            self.assertEqual(json.loads((self.root / locator).read_text())["observation"], "passed")

    def test_empty_duplicate_orphan_and_inaccessible_maps_are_blocked_not_clean(self):
        index = self.root / "features" / "README.md"
        baseline = index.read_text()
        cases = {
            "empty": "# Fixture feature map\n\nCoverage: none.\n",
            "duplicate": baseline + "- [create-note again](create-note.md)\n",
            "orphan": baseline.replace("- [list-notes](list-notes.md)\n", ""),
            "inaccessible": baseline.replace("create-note.md", "missing.md"),
        }
        for name, contents in cases.items():
            with self.subTest(name=name):
                index.write_text(contents)
                result = audit(self.root, environment=self.env)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertEqual(result["covered"], [])
                index.write_text(baseline)

    def test_unsupported_or_malformed_declared_drive_blocks_each_entry_without_map_writes(self):
        for feature in ("create-note", "list-notes", "reject-broken"):
            entry = self.root / f"features/{feature}.md"
            baseline = entry.read_text()
            for command in ("python3 drive.py nonexistent", "python3 drive.py",
                            "python3 drive.py create-note extra", "python3 ../drive.py create-note"):
                with self.subTest(feature=feature, command=command):
                    entry.write_text(baseline.replace(f"python3 drive.py {feature}", command))
                    before = {p: p.read_bytes() for p in (self.root / "features").glob("*.md")}
                    result = audit(self.root, environment=self.env)
                    self.assertEqual(result["outcome"], "blocked", result)
                    self.assertIn(feature, result["coverage_gaps"])
                    self.assertIn("Drive", result["reason"])
                    self.assertEqual(result["covered"], [])
                    self.assertEqual(result["evidence"], [])
                    self.assertEqual({p: p.read_bytes() for p in before}, before)
                    self.assertFalse((self.root / "evidence").exists())
            entry.write_text(baseline)

    def test_contradictory_missing_or_duplicate_expected_observation_blocks(self):
        entry = self.root / "features/create-note.md"
        baseline = entry.read_text()
        expected = next(p for p in baseline.split("\n\n") if p.startswith("**Expected"))
        for replacement in (
            expected.replace("create a note, then observe it through a separate list process",
                             "create a note, then observe an empty list because creation does not persist"),
            "", expected + "\n\n" + expected,
        ):
            with self.subTest(replacement=replacement):
                entry.write_text(baseline.replace(expected, replacement))
                before = entry.read_bytes()
                result = audit(self.root, environment=self.env)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertIn("create-note", result["coverage_gaps"])
                self.assertIn("Expected observation and effects", result["reason"])
                self.assertEqual(result["evidence"], [])
                self.assertEqual(entry.read_bytes(), before)

    def test_continuation_paragraphs_cannot_escape_declared_recipe_validation(self):
        for feature in ("create-note", "list-notes", "reject-broken"):
            entry = self.root / f"features/{feature}.md"
            baseline = entry.read_text()
            for marker, continuation in (
                ("**Expected observation and effects:**",
                 "Then run `python3 drive.py nonexistent` as a required second Drive step."),
                ("**Limitations:**",
                 "The expected final list is empty because creation does not persist."),
                ("**Expected observation and effects:**",
                 "**Extra step:** run `python3 drive.py nonexistent`."),
            ):
                with self.subTest(feature=feature, continuation=continuation):
                    entry.write_text(baseline.replace(marker, continuation + "\n\n" + marker))
                    before = entry.read_bytes()
                    result = audit(self.root, environment=self.env)
                    self.assertEqual(result["outcome"], "blocked", result)
                    self.assertIn(feature, result["coverage_gaps"])
                    self.assertEqual(result["evidence"], [])
                    self.assertEqual(entry.read_bytes(), before)
            entry.write_text(baseline)

    def test_valid_declared_report_only_recipe_proves_persisted_effect_and_accepts(self):
        entry = self.root / "features/create-note.md"
        entry.write_text(entry.read_text().replace("drive.py create-note`", "drive.py create-note --report-only`"))
        before = entry.read_bytes()
        result = audit(self.root, environment=self.env)
        self.assertEqual(result["outcome"], "clean", result)
        self.assertEqual(entry.read_bytes(), before)
        record = json.loads((self.root / result["evidence"][0]).read_text())
        self.assertEqual(record["effect"], {"notes": ["fixture note"]})
        self.assertEqual(record["observation"], "passed")
        self.assertTrue(record["owned_state_removed"])
        self.assertEqual(accept_maintenance(self.root, result, authorized=True)["outcome"], "clean")

    def test_invalid_mapping_survives_correction_but_cannot_gain_reproof_or_acceptance_credit(self):
        entry = self.root / "features/create-note.md"
        baseline = entry.read_text()
        for invalid in (
            baseline.replace("drive.py create-note", "drive.py nonexistent"),
            baseline.replace("create a note, then observe it through a separate list process",
                             "create a note, then observe an empty list because creation does not persist"),
            baseline.replace("**Expected observation and effects:**",
                             "Then run `python3 drive.py nonexistent` as a required second Drive step.\n\n"
                             "**Expected observation and effects:**"),
            baseline.replace("**Limitations:**",
                             "The expected final list is empty because creation does not persist.\n\n"
                             "**Limitations:**"),
        ):
            with self.subTest(invalid=invalid):
                entry.write_text(invalid.replace("fixture-app/cli.py", "fixture-app/legacy-cli.py"))
                initial = audit(self.root, environment=self.env, reviewer="first")
                correction = correct(self.root, initial, authorized=True)
                self.assertEqual(correction["outcome"], "pending", correction)
                before = entry.read_bytes()
                verified = verify_corrected(self.root, correction, environment=self.env, reviewer="fresh")
                self.assertEqual(verified["outcome"], "blocked", verified)
                self.assertIn("create-note", verified["coverage_gaps"])
                self.assertEqual(accept_maintenance(self.root, verified, authorized=True)["outcome"], "blocked")
                self.assertEqual(entry.read_bytes(), before)

    def test_acceptance_revalidates_declared_mapping_even_with_matching_report_hash(self):
        report = audit(self.root, environment=self.env)
        entry = self.root / "features/create-note.md"
        baseline = entry.read_text()
        for invalid in (
            baseline.replace("drive.py create-note", "drive.py nonexistent"),
            baseline.replace("**Expected observation and effects:**",
                             "Then run `python3 drive.py nonexistent`.\n\n**Expected observation and effects:**"),
            baseline.replace("**Limitations:**",
                             "Creation does not persist; the expected list is empty.\n\n**Limitations:**"),
        ):
            with self.subTest(invalid=invalid):
                entry.write_text(invalid)
                # Model a legacy false-clean report whose hash includes the bad recipe.
                report["map_sha256"]["create-note"] = hashlib.sha256(entry.read_bytes()).hexdigest()
                before = {p: p.read_bytes() for p in (self.root / "features").glob("*.md")}
                result = accept_maintenance(self.root, report, authorized=True)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertIn("create-note", result["coverage_gaps"])
                self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_acceptance_binds_execution_inputs_before_any_map_write(self):
        for corrected in (False, True):
            with self.subTest(corrected=corrected):
                if corrected:
                    entry = self.root / "features/create-note.md"
                    entry.write_text(entry.read_text().replace("cli.py", "legacy-cli.py"))
                    initial = audit(self.root, environment=self.env, reviewer="first")
                    correction = correct(self.root, initial, authorized=True)
                    report = verify_corrected(self.root, correction, environment=self.env, reviewer="fresh")
                else:
                    report = audit(self.root, environment=self.env)
                self.assertEqual(report["outcome"], "changed" if corrected else "clean", report)
                before = {p: p.read_bytes() for p in (self.root / "features").glob("*.md")}
                inputs = [self.root / name for name in ("drive.py", "doctor.py", "target.json")]
                inputs += [self.project / "fixture-app" / name for name in ("cli.py", "instance.json")]
                for path in inputs:
                    baseline = path.read_bytes()
                    for contents in (baseline + b"\n", None):
                        with self.subTest(input=path.name, missing=contents is None):
                            if contents is None:
                                path.unlink()
                            else:
                                path.write_bytes(contents)
                            rejected = accept_maintenance(self.root, report, authorized=True)
                            self.assertEqual(rejected["outcome"], "blocked", rejected)
                            self.assertEqual({p: p.read_bytes() for p in before}, before)
                            path.write_bytes(baseline)
                # Old reports without execution binding must also fail closed.
                unbound = {key: value for key, value in report.items() if key != "execution_sha256"}
                self.assertEqual(accept_maintenance(self.root, unbound, authorized=True)["outcome"], "blocked")
                self.assertEqual({p: p.read_bytes() for p in before}, before)
                accepted = accept_maintenance(self.root, report, authorized=True)
                self.assertEqual(accepted["outcome"], report["outcome"], accepted)
                self.assertEqual(set(accepted["maintenance_records_updated"]), set(report["covered"]))
                for path in before:
                    if path.name != "README.md":
                        self.assertIn("**Last verification:** revision=", path.read_text())

    def test_acceptance_rejects_evidence_whose_effect_contradicts_the_map(self):
        report = audit(self.root, environment=self.env)
        artifact = self.root / report["evidence"][0]
        record = json.loads(artifact.read_text())
        record["effect"] = {"notes": []}
        artifact.write_text(json.dumps(record))
        before = {p: p.read_bytes() for p in (self.root / "features").glob("*.md")}
        result = accept_maintenance(self.root, report, authorized=True)
        self.assertEqual(result["outcome"], "blocked", result)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_skipped_live_source_or_failed_evidence_cannot_be_clean(self):
        for kwargs in (
            {"run_live": False},
            {"inspect_source": False},
            {"evidence_destination": self.project / "not-a-directory"},
        ):
            with self.subTest(kwargs=kwargs):
                result = audit(self.root, environment=self.env, **kwargs)
                self.assertEqual(result["outcome"], "blocked", result)

    def test_public_export_command_is_a_named_unmapped_coverage_gap(self):
        app = self.project / "fixture-app/cli.py"
        app.write_text(app.read_text().replace(
            '    args = parser.parse_args()',
            '    commands.add_parser("export", help="export persisted notes")\n'
            '    args = parser.parse_args()'))
        result = audit(self.root, environment=self.env)
        self.assertEqual(result["outcome"], "blocked", result)
        self.assertIn("export", result["coverage_gaps"])
        self.assertEqual(result["public_entry_points"], ["create", "export", "list", "status"])

    def test_intentional_route_change_is_map_drift_until_authorized_correction_and_fresh_reproof(self):
        entry = self.root / "features" / "create-note.md"
        entry.write_text(entry.read_text().replace("fixture-app/cli.py", "fixture-app/legacy-cli.py"))
        original = audit(self.root, environment=self.env, reviewer="first-inspector")
        self.assertEqual(original["outcome"], "blocked")
        self.assertIn("create-note", original["map_drift"])
        denied = correct(self.root, original, authorized=False)
        self.assertEqual(denied["outcome"], "blocked")
        self.assertIn("legacy-cli.py", entry.read_text())
        corrected = correct(self.root, original, authorized=True)
        self.assertEqual(corrected["outcome"], "pending")
        self.assertEqual(corrected["verification"], "reproof-required")
        self.assertEqual(verify_corrected(self.root, corrected, environment=self.env,
                                          reviewer="first-inspector")["outcome"], "blocked")
        self.assertNotIn("**Last verification:** [run artifact]", entry.read_text())
        before_reproof = entry.read_bytes()
        verified = verify_corrected(self.root, corrected, environment=self.env,
                                    reviewer="fresh-fixture-verifier")
        self.assertEqual(verified["outcome"], "changed", verified)
        self.assertEqual(entry.read_bytes(), before_reproof)
        self.assertIn("fixture-app/cli.py", entry.read_text())
        from verification_harness_maintenance_fixture import accept_maintenance
        denied = accept_maintenance(self.root, verified, authorized=False)
        self.assertEqual(denied["outcome"], "blocked")
        self.assertEqual(entry.read_bytes(), before_reproof)
        accepted = accept_maintenance(self.root, verified, authorized=True)
        self.assertEqual(accepted["outcome"], "changed", accepted)
        self.assertIn("**Last verification:** revision=", entry.read_text())
        self.assertIn("[run artifact]", entry.read_text())

    def test_removed_corrected_entry_cannot_receive_terminal_changed(self):
        entry = self.root / "features/create-note.md"
        entry.write_text(entry.read_text().replace("cli.py", "legacy-cli.py"))
        original = audit(self.root, environment=self.env, reviewer="first")
        correction = correct(self.root, original, authorized=True)
        entry.unlink()
        index = self.root / "features/README.md"
        index.write_text(index.read_text().replace("- [create-note](create-note.md)\n", ""))
        result = verify_corrected(self.root, correction, environment=self.env, reviewer="fresh")
        self.assertEqual(result["outcome"], "blocked", result)

    def test_changed_final_report_retains_fresh_independent_verification(self):
        entry = self.root / "features/create-note.md"
        entry.write_text(entry.read_text().replace("cli.py", "legacy-cli.py"))
        original = audit(self.root, environment=self.env, reviewer="first")
        correction = correct(self.root, original, authorized=True)
        result = verify_corrected(self.root, correction, environment=self.env, reviewer="fresh")
        self.assertEqual(result["outcome"], "changed", result)
        retained = json.loads((self.root / result["report"]).read_text())
        self.assertEqual(retained["outcome"], "changed")
        self.assertEqual(retained["reviewer"], "fresh")
        self.assertTrue(set(correction["corrected_paths"]).issubset(retained["covered"]))

    def test_product_regression_is_a_markdown_defect_and_never_a_map_correction(self):
        entry = self.root / "features" / "create-note.md"
        before = entry.read_bytes()
        result = audit(self.root, environment={**self.env, "FIXTURE_BEHAVIOR_BROKEN": "1"})
        self.assertEqual(result["outcome"], "blocked", result)
        self.assertTrue(result["defects"])
        defect = self.root / result["defects"][0]
        self.assertTrue(defect.is_file())
        self.assertIn("Product regression", defect.read_text())
        self.assertEqual(entry.read_bytes(), before)

    def test_correction_scope_rejects_product_paths_and_retains_partial_evidence_after_failure_cleanup(self):
        report = {"map_drift": [], "harness_drift": ["../fixture-app/cli.py"], "reviewer": "first"}
        blocked = correct(self.root, report, authorized=True)
        self.assertEqual(blocked["outcome"], "blocked")
        self.assertIn("outside", blocked["reason"])
        failed = audit(self.root, environment={**self.env, "FIXTURE_BEHAVIOR_BROKEN": "1"})
        self.assertEqual(failed["outcome"], "blocked")
        self.assertTrue(list((self.root / "evidence").glob("*.json")))
        self.assertFalse((self.root / ".owned-run").exists())
        self.assertEqual(list((self.root / ".runs").iterdir()), [])

    def test_unsafe_map_and_correction_targets_are_rejected_before_any_writes(self):
        index = self.root / "features" / "README.md"
        baseline = index.read_text()
        outside = self.project / "outside.md"
        outside.write_text("fixture-app/legacy-cli.py\n")
        entry = self.root / "features" / "create-note.md"
        entry.write_text(entry.read_text().replace("cli.py", "legacy-cli.py"))
        before = entry.read_bytes()
        for bad_id in ("../../../../outside", str(outside.with_suffix("")), "../features/create-note"):
            with self.subTest(bad_id=bad_id):
                index.write_text(baseline + f"- [{bad_id}]({bad_id}.md)\n")
                result = audit(self.root, environment=self.env)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertFalse((self.root / "reports").exists())
                index.write_text(baseline)
                result = correct(self.root, {"map_drift": ["create-note", bad_id]}, authorized=True)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertEqual(entry.read_bytes(), before)
                self.assertEqual(outside.read_text(), "fixture-app/legacy-cli.py\n")
        entry.unlink()
        entry.symlink_to(outside)
        self.assertEqual(audit(self.root, environment=self.env)["outcome"], "blocked")
        self.assertEqual(correct(self.root, {"map_drift": ["create-note"]}, authorized=True)["outcome"], "blocked")
        self.assertFalse((self.root / "reports").exists())
        self.assertEqual(outside.read_text(), "fixture-app/legacy-cli.py\n")

    def test_unsafe_or_malformed_index_bullets_cannot_be_silently_omitted(self):
        index = self.root / "features/README.md"
        baseline = index.read_text()
        for bullet in ("- [../../../../outside](../../../../outside.md)  ",
                       "  * [../../../../outside](../../../../outside.md)",
                       "- [broken](unfinished", "+ [extra][reference]"):
            with self.subTest(bullet=bullet):
                index.write_text(baseline + bullet + "\n")
                result = audit(self.root, environment=self.env)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertFalse((self.root / "reports").exists())

    def test_driver_without_report_only_compatibility_blocks_before_map_mutation(self):
        driver = self.root / "drive.py"
        driver.write_text(driver.read_text().replace(" and not report_only", ""))
        before = {path: path.read_bytes() for path in (self.root / "features").glob("*.md")}
        result = audit(self.root, environment=self.env)
        self.assertEqual(result["outcome"], "blocked", result)
        self.assertEqual(result["harness_drift"], ["drive.py"])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((self.root / "evidence").exists())

    def test_unproven_or_already_resolved_drift_cannot_invalidate_map_records(self):
        entry = self.root / "features/create-note.md"
        before = entry.read_bytes()
        result = correct(self.root, {"map_drift": ["create-note"], "reviewer": "invented"}, authorized=True)
        self.assertEqual(result["outcome"], "blocked", result)
        self.assertEqual(entry.read_bytes(), before)

    def test_report_only_dependency_drift_cannot_mutate_map(self):
        entry = self.root / "features/create-note.md"
        before = entry.read_bytes()
        for script in (self.root / "doctor.py", self.project / "fixture-app/cli.py"):
            with self.subTest(script=script.name):
                baseline = script.read_text()
                script.write_text(baseline.replace("from pathlib import Path", "from pathlib import Path\n"
                    f"Path({str(entry)!r}).write_text('mutated by dependency')"))
                result = audit(self.root, environment=self.env)
                self.assertEqual(result["outcome"], "blocked", result)
                self.assertEqual(entry.read_bytes(), before)
                script.write_text(baseline)


if __name__ == "__main__":
    unittest.main()

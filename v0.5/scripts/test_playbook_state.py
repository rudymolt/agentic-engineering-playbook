import unittest
from datetime import datetime, timezone

import playbook_state as ps


STATE = """schema_version: 3
playbook_version: "V0.3.36"   # stamped by upgrade
counters:
  slices_since_last_architecture_review: 4   # reset at review
  quoted: "a # not a comment"
pending_model_routes:
  - request_title: "CSV export"
    status: selected
    linked_wayfinder: null
empty_list: []
"""


class TypedLayerTest(unittest.TestCase):
    def test_scalar_types(self):
        self.assertEqual(ps.parse_scalar("7"), 7)
        self.assertEqual(ps.parse_scalar("-2.5"), -2.5)
        self.assertIs(ps.parse_scalar("true"), True)
        self.assertIs(ps.parse_scalar("false # off"), False)
        self.assertIsNone(ps.parse_scalar("~"))
        self.assertEqual(ps.parse_scalar("[]"), [])
        self.assertEqual(ps.parse_scalar('"true"'), "true")
        self.assertEqual(ps.parse_scalar('"a \\" b"'), 'a " b')

    def test_inline_comment_stripping_is_quote_aware(self):
        self.assertEqual(ps.strip_inline_comment("plain # comment"), "plain")
        self.assertEqual(ps.strip_inline_comment('"kept # inside"'), '"kept # inside"')

    def test_top_level_map(self):
        counters = ps.parse_top_level_map(STATE, "counters")
        self.assertEqual(counters["slices_since_last_architecture_review"], 4)
        self.assertEqual(counters["quoted"], "a # not a comment")

    def test_top_level_list_typed(self):
        routes = ps.parse_top_level_list(STATE, "pending_model_routes")
        self.assertEqual(routes, [{"request_title": "CSV export",
                                   "status": "selected", "linked_wayfinder": None}])
        self.assertEqual(ps.parse_top_level_list(STATE, "empty_list"), [])
        self.assertEqual(ps.parse_top_level_list(STATE, "absent"), [])

    def test_parse_datetime_forms(self):
        self.assertEqual(ps.parse_datetime("2026-07-14T12:00:00Z"),
                         datetime(2026, 7, 14, 12, tzinfo=timezone.utc))
        self.assertEqual(ps.parse_datetime("2026-07-14"),
                         datetime(2026, 7, 14, tzinfo=timezone.utc))
        self.assertIsNone(ps.parse_datetime("not-a-date"))
        self.assertIsNone(ps.parse_datetime(None))

    def test_quote_yaml_string_round_trips_through_parse_scalar(self):
        original = 'headline with "quotes" and \\ backslash'
        self.assertEqual(ps.parse_scalar(ps.quote_yaml_string(original)), original)


class RawLayerTest(unittest.TestCase):
    def test_typed_list_parser_keeps_fields_with_inline_comments(self):
        # Regression for the drift phase 2 removed: the migrator's old raw
        # parser silently dropped any field whose line contained '#'.
        typed = ps.parse_top_level_list(
            'block:\n  - kept: yes\n    note: value  # comment\n', "block")
        self.assertEqual(typed, [{"kept": "yes", "note": "value"}])

    def test_scalar_read_and_replace(self):
        self.assertEqual(ps.top_level_scalar_value(STATE, "schema_version"), "3")
        self.assertEqual(ps.top_level_scalar_value(STATE, "playbook_version"), '"V0.3.36"')
        replaced = ps.replace_top_level_scalar(STATE, "schema_version", "4")
        self.assertIn("schema_version: 4\n", replaced)
        self.assertEqual(ps.replace_top_level_scalar(STATE, "absent", "x"), STATE)

    def test_insertion_helpers(self):
        text, ok = ps.insert_before("a\ncounters:\n", "counters:\n", "new: 1\n")
        self.assertTrue(ok)
        self.assertEqual(text, "a\nnew: 1\ncounters:\n")
        text, ok = ps.insert_after_line("key: 1\nend: 2", r"^key: 1$", "added: 3")
        self.assertTrue(ok)
        self.assertEqual(text, "key: 1\nadded: 3\nend: 2")
        # idempotent: an already-present line reports success without change
        text, ok = ps.insert_after_line("key: 1\nadded: 3", r"^key: 1$", "added: 3")
        self.assertTrue(ok)
        self.assertEqual(text, "key: 1\nadded: 3")


TEMPLATE_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "templates"


class ValidateStateTest(unittest.TestCase):
    def problems(self, text):
        return [p for p in ps.validate_state(text) if not p.advisory]

    def test_current_template_validates_clean(self):
        text = (TEMPLATE_DIR / ".playbook-state.yml").read_text()
        self.assertEqual(self.problems(text), [])

    def test_type_errors_carry_line_and_remedy(self):
        text = ("schema_version: 3\n"
                "counters:\n"
                "  slices_open: three\n")
        problems = ps.validate_state(text)
        counter = [p for p in problems if p.path == "counters.slices_open"]
        self.assertEqual(len(counter), 1)
        self.assertEqual(counter[0].line, 3)
        self.assertIn("'three'", counter[0].message)
        self.assertIn("integer", counter[0].remedy)

    def test_schema3_missing_required_key_is_reported(self):
        text = "schema_version: 3\ncounters:\n  slices_open: 0\n"
        paths = {p.path for p in self.problems(text)}
        self.assertIn("pending_closeouts", paths)

    def test_schema2_state_skips_required_key_checks(self):
        text = "schema_version: 2\ncounters:\n  slices_open: 0\n"
        self.assertEqual(self.problems(text), [])

    def test_unknown_custom_fields_are_never_reported(self):
        text = ("schema_version: 2\n"
                "my_custom_block:\n"
                "  anything: goes\n"
                "decisions:\n"
                "  no_ui: true\n"
                "  custom_choice: whatever\n")
        self.assertEqual(self.problems(text), [])

    def test_enum_and_entry_field_checks(self):
        text = ("schema_version: 2\n"
                "decisions:\n"
                "  technical_decisions: always\n"
                "pending_closeouts:\n"
                "  - feature_slug: export\n"
                "    doc_close: started\n"
                "active_features:\n"
                "  - slug: export\n")
        paths = {p.path for p in self.problems(text)}
        self.assertIn("decisions.technical_decisions", paths)
        self.assertIn("pending_closeouts[0].doc_close", paths)
        self.assertIn("active_features[0].status", paths)

    def test_template_provenance_requires_known_typed_fields_with_line_numbers(self):
        text = ("schema_version: 2\n"
                "template_provenance:\n"
                "  schema: one\n"
                "  project_name: Demo\n"
                "  unexpected: true\n"
                "  files:\n"
                "    CLAUDE.md:\n"
                "      template: v0.5/templates/CLAUDE.md\n"
                "      version: nope\n"
                "      base_sha256: short\n"
                "      bogus: true\n"
                "    AGENTS.md:\n"
                "      version: V0.3.41\n"
                "      base_sha256: " + "a" * 64 + "\n")

        problems = self.problems(text)
        paths = {problem.path for problem in problems}
        self.assertIn("template_provenance.schema", paths)
        self.assertIn("template_provenance.unexpected", paths)
        self.assertIn("template_provenance.files[CLAUDE.md].version", paths)
        self.assertIn("template_provenance.files[CLAUDE.md].base_sha256", paths)
        self.assertIn("template_provenance.files[CLAUDE.md].bogus", paths)
        self.assertIn("template_provenance.files[AGENTS.md].template", paths)
        self.assertTrue(all(problem.line is not None for problem in problems))

    def test_template_provenance_rejects_malformed_project_name_and_nesting(self):
        text = ("schema_version: 2\n"
                "template_provenance:\n"
                "  schema: 1\n"
                "  project_name: \"unterminated\n"
                "    CLAUDE.md:\n"
                "      template: v0.5/templates/CLAUDE.md\n"
                "      version: V0.3.41\n"
                "      base_sha256: " + "a" * 64 + "\n"
                "  files:\n")

        rendered = [problem.render() for problem in self.problems(text)]
        self.assertTrue(any("project_name" in problem and "quoted" in problem
                            for problem in rendered))
        self.assertTrue(any("before template_provenance.files" in problem
                            for problem in rendered))

    def test_managed_paths_must_be_canonical_portable_and_traversal_free(self):
        invalid = (
            "", ".", "./CONTEXT.md", "planning//README.md", "planning/../CONTEXT.md",
            "../outside.txt", "/tmp/outside.txt", "C:/outside.txt", r"..\outside.txt",
            "planning/", "harness#shadow", "harness\nshadow", "harness\tshadow",
            "harness:shadow", " harness", "harness ", '"harness"', "[harness]",
        )
        for relative in invalid:
            with self.subTest(relative=relative):
                self.assertFalse(ps.is_canonical_relative_path(relative))
        self.assertTrue(ps.is_canonical_relative_path("planning/README.md"))
        self.assertTrue(ps.is_canonical_relative_path("planning/harness with spaces"))

        text = ("schema_version: 3\n"
                "template_provenance:\n"
                "  schema: 1\n"
                "  files:\n"
                "    ../outside.txt:\n"
                "      template: v0.5/templates/../outside.md\n"
                "      version: V0.5.0\n"
                "      base_sha256: " + "a" * 64 + "\n")
        rendered = [problem.render() for problem in self.problems(text)]
        self.assertTrue(any("unsafe managed path" in problem for problem in rendered))
        self.assertTrue(any("unsafe template path" in problem for problem in rendered))

    def test_verification_map_state_fields_are_typed_and_path_safe(self):
        valid = (
            "schema_version: 3\nstatus: {}\nplaybook_version: V0.5.0\ndecisions:\n"
            "  verification_harness_path: .verification-harness\n"
            "  verification_map_maintenance: false\n"
            "  verification_harness_binding: .verification-harness\ncounters: {}\nlast_run:\n"
            "  verification_map_enabled: null\n  verification_map_maintenance: null\n"
            "pending_closeouts: []\npending_model_routes: []\ndelivery_missions: []\n"
            "active_wayfinding_maps: []\nactive_features: []\nprereqs_required: true\n"
        )
        self.assertEqual([p for p in self.problems(valid) if not p.advisory], [])
        invalid = valid.replace(".verification-harness", "../unsafe").replace(
            "verification_map_maintenance: false", "verification_map_maintenance: maybe"
        ).replace("verification_map_enabled: null", "verification_map_enabled: yesterday")
        rendered = [problem.render() for problem in self.problems(invalid)]
        self.assertTrue(any("decisions.verification_harness_path" in problem for problem in rendered))
        self.assertTrue(any("decisions.verification_map_maintenance" in problem for problem in rendered))
        self.assertTrue(any("decisions.verification_harness_binding" in problem for problem in rendered))
        self.assertTrue(any("last_run.verification_map_enabled" in problem for problem in rendered))


class ValidateCadencesTest(unittest.TestCase):
    def test_current_template_validates_clean(self):
        text = (TEMPLATE_DIR / "playbook-cadences.yml").read_text()
        self.assertEqual([p for p in ps.validate_cadences(text) if not p.advisory], [])

    def test_bad_type_duplicate_id_and_threshold_order(self):
        text = ("cadences:\n"
                "  - id: a\n"
                "    type: countdown\n"
                "  - id: a\n"
                "    type: count\n"
                "    counter: slices_open\n"
                "    nudge_threshold: 9\n"
                "    insist_threshold: 3\n")
        rendered = [p.render() for p in ps.validate_cadences(text)]
        self.assertTrue(any("expected count, time, or event" in r for r in rendered))
        self.assertTrue(any("duplicate" in r for r in rendered))
        self.assertTrue(any("nudge must fire at or before insist" in r for r in rendered))

    def test_severity_on_count_cadence_is_advisory(self):
        text = ("cadences:\n"
                "  - id: a\n"
                "    type: count\n"
                "    counter: slices_open\n"
                "    severity: insist\n")
        problems = ps.validate_cadences(text)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].advisory)

    def test_event_cadence_needs_severity_and_trigger(self):
        text = "cadences:\n  - id: e\n    type: event\n"
        paths = {p.path for p in ps.validate_cadences(text)}
        self.assertIn("cadences[0] (e).severity", paths)
        self.assertIn("cadences[0] (e).trigger", paths)


if __name__ == "__main__":
    unittest.main()

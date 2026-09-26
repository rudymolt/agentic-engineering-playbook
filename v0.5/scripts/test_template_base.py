import unittest
from pathlib import Path

import template_base


STATE = """schema_version: 3
playbook_version: V0.3.40
counters:
  slices_shipped_total: 3
"""


class RenderTest(unittest.TestCase):
    def test_render_substitutes_paths_and_project_name(self):
        text = "root {playbook-path} alt {path-to-playbook} name {project name}"
        rendered = template_base.render(text, Path("/opt/playbook"), "Demo")
        self.assertEqual(rendered, "root /opt/playbook alt /opt/playbook name Demo")

    def test_render_resolves_current_and_legacy_skill_placeholders(self):
        rendered = template_base.render(
            "current {skill:to-tickets}; legacy {skill:to-issues}",
            Path("/opt/playbook"),
            "Demo",
        )
        self.assertEqual(rendered, "current /to-tickets; legacy /to-tickets")

    def test_render_rejects_unknown_skill_placeholder(self):
        with self.assertRaisesRegex(ValueError, "unknown skill placeholder.*not-a-skill"):
            template_base.render("{skill:not-a-skill}", Path("/opt/playbook"), "Demo")


class Merge3Test(unittest.TestCase):
    def test_non_overlapping_edits_merge_cleanly(self):
        base = "one\ntwo\nthree\nfour\nfive\n"
        ours = "one\nCUSTOM two\nthree\nfour\nfive\n"
        theirs = "one\ntwo\nthree\nfour\nNEW five\n"
        merged, conflicted = template_base.merge3(base, ours, theirs)
        self.assertFalse(conflicted)
        self.assertEqual(merged, "one\nCUSTOM two\nthree\nfour\nNEW five\n")

    def test_overlapping_edits_conflict(self):
        base = "one\ntwo\nthree\n"
        ours = "one\nOURS\nthree\n"
        theirs = "one\nTHEIRS\nthree\n"
        merged, conflicted = template_base.merge3(base, ours, theirs)
        self.assertTrue(conflicted)
        self.assertIn("<<<<<<<", merged)


class ProvenanceTest(unittest.TestCase):
    def test_round_trip_preserves_entries_and_sorts_deterministically(self):
        record = {
            "schema": 1,
            "project_name": "Demo",
            "files": {
                "CLAUDE.md": {
                    "template": "v0.5/templates/CLAUDE.md",
                    "version": "V0.3.41",
                    "base_sha256": "a" * 64,
                },
                ".agents/skills/whats-next/SKILL.md": {
                    "template": "v0.5/skills/whats-next/SKILL.md",
                    "version": "V0.3.41",
                    "base_sha256": "b" * 64,
                },
            },
        }
        state = template_base.upsert_provenance(STATE, record)
        parsed = template_base.read_provenance(state)
        self.assertEqual(parsed["project_name"], "Demo")
        self.assertEqual(parsed["files"], record["files"])
        self.assertLess(
            state.index(".agents/skills/whats-next/SKILL.md"), state.index("CLAUDE.md:")
        )

    def test_upsert_replaces_an_existing_block_without_touching_other_content(self):
        first_entry = {
            "template": "v0.5/templates/CLAUDE.md",
            "version": "V0.3.40",
            "base_sha256": "a" * 64,
        }
        second_entry = {
            "template": "v0.5/templates/CLAUDE.md",
            "version": "V0.3.41",
            "base_sha256": "b" * 64,
        }
        first = template_base.upsert_provenance(
            STATE, {"schema": 1, "files": {"CLAUDE.md": first_entry}}
        )
        second = template_base.upsert_provenance(
            first + "# keep this top-level human comment\ntrailing_key: kept\n",
            {"schema": 1, "files": {"CLAUDE.md": second_entry}},
        )
        self.assertEqual(second.count("template_provenance:"), 1)
        self.assertIn("version: V0.3.41", second)
        self.assertNotIn("version: V0.3.40\n", second.split("template_provenance:")[1])
        self.assertIn("slices_shipped_total: 3", second)
        self.assertIn("# keep this top-level human comment", second)
        self.assertIn("trailing_key: kept", second)

    def test_absent_block_reads_as_empty(self):
        self.assertEqual(template_base.read_provenance(STATE), {})

    def test_malformed_block_raises(self):
        broken = STATE + "template_provenance:\n  schema: 9\n"
        with self.assertRaises(ValueError):
            template_base.read_provenance(broken)

    def test_invalid_entry_shape_raises_before_merge(self):
        broken = (STATE + "template_provenance:\n"
                  "  schema: 1\n"
                  "  project_name: Demo\n"
                  "  files:\n"
                  "    CLAUDE.md:\n"
                  "      template: v0.5/templates/CLAUDE.md\n"
                  "      version: nope\n"
                  "      base_sha256: short\n")
        with self.assertRaisesRegex(ValueError, "line .*version"):
            template_base.read_provenance(broken)

    def test_inline_or_duplicate_block_is_rejected_before_upsert(self):
        inline = STATE + "template_provenance: {}\n"
        with self.assertRaisesRegex(ValueError, "template_provenance"):
            template_base.read_provenance(inline)
        with self.assertRaisesRegex(ValueError, "template_provenance"):
            template_base.upsert_provenance(
                inline, {"schema": 1, "project_name": "Demo", "files": {}}
            )

        valid = template_base.upsert_provenance(
            STATE, {"schema": 1, "project_name": "Demo", "files": {}}
        )
        duplicate = valid + "template_provenance:\n  schema: 1\n  files:\n"
        with self.assertRaisesRegex(ValueError, "duplicate template_provenance"):
            template_base.read_provenance(duplicate)
        self.assertTrue(any(
            "duplicate" in problem.message
            for problem in template_base.validate_template_provenance(duplicate)
        ))

        nested_duplicates = (STATE + "template_provenance:\n"
                             "  schema: 1\n"
                             "  schema: 1\n"
                             "  files:\n"
                             "    CLAUDE.md:\n"
                             "      template: v0.5/templates/CLAUDE.md\n"
                             "      template: v0.5/templates/CLAUDE.md\n"
                             "      version: V0.3.41\n"
                             "      base_sha256: " + "a" * 64 + "\n"
                             "    CLAUDE.md:\n"
                             "      template: v0.5/templates/CLAUDE.md\n"
                             "      version: V0.3.41\n"
                             "      base_sha256: " + "a" * 64 + "\n")
        nested_problems = template_base.validate_template_provenance(nested_duplicates)
        self.assertEqual(
            sum("duplicate" in problem.message for problem in nested_problems), 3
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            template_base.read_provenance(nested_duplicates)


class ManagedFilesTest(unittest.TestCase):
    def test_registry_covers_root_templates_and_installed_skills(self):
        playbook_root = Path(__file__).resolve().parents[2]
        mapping = template_base.managed_files(playbook_root)
        self.assertEqual(mapping["CLAUDE.md"], "v0.5/templates/CLAUDE.md")
        self.assertEqual(
            mapping[".agents/skills/whats-next/SKILL.md"], "v0.5/skills/whats-next/SKILL.md"
        )
        self.assertNotIn(".playbook-state.yml", mapping)
        self.assertNotIn("playbook-cadences.yml", mapping)
        self.assertNotIn("planning/STATUS.md", mapping)


if __name__ == "__main__":
    unittest.main()

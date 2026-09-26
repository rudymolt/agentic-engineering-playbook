import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("check-skill-metadata.py")
spec = importlib.util.spec_from_file_location("check_skill_metadata", SCRIPT)
check_skill_metadata = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(check_skill_metadata)


class SkillMetadataTest(unittest.TestCase):
    def skill(self, *, disabled: str | None = None, heading: str = "## Guardrails") -> str:
        disabled_line = "" if disabled is None else f"disable-model-invocation: {disabled}\n"
        return (
            "---\n"
            "name: sample\n"
            "description: Route a sample branch when its explicit trigger appears.\n"
            f"{disabled_line}"
            "---\n\n"
            "## Procedure\n\n1. Do the work. Completion criterion: evidence exists.\n\n"
            f"{heading}\n"
        )

    def test_model_invoked_omits_disable_flag(self):
        self.assertEqual(
            check_skill_metadata.validate_skill_text("sample", self.skill(), "model"),
            [],
        )
        self.assertIn(
            "model-invoked skill must omit disable-model-invocation",
            check_skill_metadata.validate_skill_text("sample", self.skill(disabled="true"), "model")[0],
        )

    def test_user_invoked_requires_disable_flag(self):
        self.assertEqual(
            check_skill_metadata.validate_skill_text("sample", self.skill(disabled="true"), "user"),
            [],
        )
        self.assertIn(
            "user-invoked skill must set disable-model-invocation: true",
            check_skill_metadata.validate_skill_text("sample", self.skill(), "user")[0],
        )

    def test_negative_guardrail_heading_is_rejected(self):
        problems = check_skill_metadata.validate_skill_text(
            "sample",
            self.skill(heading="## Things this skill must not do"),
            "model",
        )
        self.assertTrue(any("positive Guardrails" in problem for problem in problems))

    def test_each_procedure_step_needs_a_completion_criterion(self):
        text = self.skill().replace("Completion criterion: evidence exists.", "Done.")
        problems = check_skill_metadata.validate_skill_text("sample", text, "model")
        self.assertTrue(any("missing a completion criterion" in problem for problem in problems))

    def test_heading_steps_ignore_nested_numbered_lists(self):
        text = self.skill().replace(
            "1. Do the work. Completion criterion: evidence exists.",
            "### Step 1 — Rank\n\n1. First\n2. Second\n\nCompletion criterion: ranking exists.",
        )
        self.assertEqual(check_skill_metadata.validate_skill_text("sample", text, "model"), [])

    def test_contract_parser_is_exact(self):
        index = "local_skills[2]{name,invocation}:\n  one, model\n  two, user\n"
        self.assertEqual(
            check_skill_metadata.invocation_contract(index),
            {"one": "model", "two": "user"},
        )

    def test_live_contract_must_match_registry(self):
        index = (SCRIPT.parents[1] / "skills" / "README.md").read_text()
        expected = check_skill_metadata.registry_contract()
        self.assertEqual(check_skill_metadata.invocation_contract(index), expected)

    def test_live_skill_requires_openai_discovery_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "sample"
            skill.mkdir()
            (skill / "SKILL.md").write_text(self.skill())
            index = root / "README.md"
            index.write_text("local_skills[1]{name,invocation}:\n  sample, model\n")
            problems = check_skill_metadata.check(root, index)
            self.assertTrue(any("agents/openai.yaml" in problem for problem in problems))

    def test_openai_default_prompt_names_the_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skill = root / "sample"
            agents = skill / "agents"
            agents.mkdir(parents=True)
            (skill / "SKILL.md").write_text(self.skill())
            (agents / "openai.yaml").write_text(
                'interface:\n  display_name: "Sample"\n'
                '  short_description: "Run the sample workflow safely"\n'
                '  default_prompt: "Run this workflow."\n'
            )
            index = root / "README.md"
            index.write_text("local_skills[1]{name,invocation}:\n  sample, model\n")
            problems = check_skill_metadata.check(root, index)
            self.assertTrue(any("$sample" in problem for problem in problems))

    def test_codex_metadata_is_required_and_matches_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "sample"
            agents_dir = skill_dir / "agents"
            agents_dir.mkdir(parents=True)
            metadata = agents_dir / "openai.yaml"
            metadata.write_text(
                "interface:\n"
                '  display_name: "Sample"\n'
                '  short_description: "Run the sample skill"\n'
                '  default_prompt: "Use $sample to run the sample skill."\n'
            )

            self.assertEqual(
                check_skill_metadata.validate_codex_metadata("sample", skill_dir, "model"),
                [],
            )
            self.assertTrue(
                any(
                    "allow_implicit_invocation" in problem
                    for problem in check_skill_metadata.validate_codex_metadata(
                        "sample", skill_dir, "user"
                    )
                )
            )

            metadata.write_text(
                "interface:\n"
                '  display_name: "Sample"\n'
                '  short_description: "Run the sample skill"\n'
                '  default_prompt: "Use $sample to run the sample skill."\n'
                "policy:\n"
                "  allow_implicit_invocation: false\n"
            )
            self.assertEqual(
                check_skill_metadata.validate_codex_metadata("sample", skill_dir, "user"),
                [],
            )
            self.assertTrue(
                any(
                    "must omit" in problem
                    for problem in check_skill_metadata.validate_codex_metadata(
                        "sample", skill_dir, "model"
                    )
                )
            )

            metadata.write_text(
                "interface:\n"
                '  display_name: "Sample"\n'
                '  short_description: "Run the sample skill"\n'
                '  default_prompt: "Use $sample to run the sample skill."\n'
                "allow_implicit_invocation: false\n"
            )
            self.assertTrue(
                any(
                    "must set Codex policy" in problem
                    for problem in check_skill_metadata.validate_codex_metadata(
                        "sample", skill_dir, "user"
                    )
                )
            )

            metadata.write_text(
                "interface:\n"
                '  display_name: "Sample"\n'
                '  short_description: "Run the sample skill"\n'
                '  default_prompt: "Use $sample to run the sample skill."\n'
                "policy:\n"
                "  allow_implicit_invocation: true\n"
            )
            self.assertTrue(
                any(
                    "must omit" in problem
                    for problem in check_skill_metadata.validate_codex_metadata(
                        "sample", skill_dir, "model"
                    )
                )
            )

    def test_codex_metadata_requires_picker_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "sample"
            agents_dir = skill_dir / "agents"
            agents_dir.mkdir(parents=True)
            (agents_dir / "openai.yaml").write_text("interface:\n")

            problems = check_skill_metadata.validate_codex_metadata(
                "sample", skill_dir, "model"
            )
            self.assertTrue(any("display_name" in problem for problem in problems))
            self.assertTrue(any("short_description" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()

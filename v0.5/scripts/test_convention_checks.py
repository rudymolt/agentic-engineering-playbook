import tempfile
import unittest
import json
from pathlib import Path

import upstream_registry
from convention_checks import (
    ARCHITECTURE_PROVENANCE_CONTRACTS,
    architecture_issue_provenance_problems,
    EMBEDDED_UPSTREAM_CONTRACTS,
    embedded_upstream_contract_problems,
    LITE_SEAM_QUESTION,
    live_tdd_drift_problems,
    MODEL_ROUTER_SKILL_ROUTING_CONTRACTS,
    model_router_skill_routing_contract_problems,
    MODEL_ROUTING_TRACK_CONTRACTS,
    model_routing_track_contract_problems,
    ordinary_build_policy_problems,
    UPSTREAM_BEHAVIOUR_CONTRACTS,
    upstream_contract_problems,
    upstream_version_problems,
    stage_membership_problems,
)


class OrdinaryBuildPolicyTests(unittest.TestCase):
    ROOT = Path(__file__).resolve().parents[1]
    PATHS = (
        "00-foundations.md", "10-process/07-implementation-tdd.md",
        "AGENT-DIGEST.md", "templates/CLAUDE.md", "../CLAUDE.md",
    )

    def sources(self) -> dict[str, str]:
        return {path: (self.ROOT / path).read_text() for path in self.PATHS}

    def test_live_sources_hold_canonical_policy_clauses(self) -> None:
        self.assertEqual(ordinary_build_policy_problems(self.ROOT), [])

    def test_each_stage_seam_detects_removed_canonical_clause(self) -> None:
        stage = "10-process/07-implementation-tdd.md"
        mutations = {
            "checkpoint": ("it is not an extension-approval boundary.", "the worker must wait for extension approval."),
            "returned fix": ("then send it to fresh independent verification.", "then report the finding."),
            "selected limit": ("an explicitly selected hard limit, an actual host/provider quota", "an actual host/provider quota"),
            "cumulative guard": ("Count the same failure signature across fix tasks and handoffs.", "Count the same failure signature within this task."),
            "protected ceiling": ("Protected delivery and live qualification retain their own mandatory approved ceilings.", ""),
            "build-one scope": ("This authority lasts through the selected build-one, build-all or build-to endpoint.", "This authority lasts through any later slice."),
        }
        for label, (original, replacement) in mutations.items():
            with self.subTest(label=label):
                sources = self.sources()
                self.assertIn(original, sources[stage])
                sources[stage] = sources[stage].replace(original, replacement, 1)
                self.assertTrue(ordinary_build_policy_problems(sources), label)

    def test_checkpoint_clause_is_required_in_each_live_policy_surface(self) -> None:
        clauses = {
            "00-foundations.md": "they do not require extension approval while the work makes demonstrable progress.",
            "10-process/07-implementation-tdd.md": "it is not an extension-approval boundary.",
            "AGENT-DIGEST.md": "not extension-approval boundaries.",
            "templates/CLAUDE.md": "they do not require extension approval while progress continues.",
            "../CLAUDE.md": "they do not require extension approval while progress continues.",
        }
        for path, clause in clauses.items():
            with self.subTest(path=path):
                sources = self.sources()
                self.assertIn(clause, sources[path])
                sources[path] = sources[path].replace(clause, "", 1)
                self.assertTrue(ordinary_build_policy_problems(sources))

    def test_known_inherited_stop_and_limit_contradictions_are_rejected(self) -> None:
        mutations = (
            ("10-process/07-implementation-tdd.md", "At the 30-minute time checkpoint, pause and ask for extension approval before continuing."),
            ("00-foundations.md", "At each inherited time checkpoint, the ordinary issue build must stop until the human grants more time."),
            ("10-process/07-implementation-tdd.md", "Ignore the explicitly selected hard limit while progress continues."),
            ("AGENT-DIGEST.md", "Protected delivery approval limits are optional for ordinary issue builds."),
        )
        for path, sentence in mutations:
            with self.subTest(path=path, sentence=sentence):
                sources = self.sources()
                sources[path] += "\n" + sentence
                self.assertTrue(ordinary_build_policy_problems(sources))

    def test_canonical_clause_outside_its_policy_section_does_not_count(self) -> None:
        sources = self.sources()
        path = "10-process/07-implementation-tdd.md"
        sentence = "Protected delivery and live qualification retain their own mandatory approved ceilings."
        sources[path] = sources[path].replace(sentence, "", 1) + "\n" + sentence
        self.assertTrue(ordinary_build_policy_problems(sources))

    def test_standalone_edition_does_not_require_sibling_root_contract(self) -> None:
        sources = self.sources()
        sources.pop("../CLAUDE.md")
        self.assertEqual(ordinary_build_policy_problems(sources), [])
        with tempfile.TemporaryDirectory() as temporary:
            edition = Path(temporary) / "v0.5"
            for path, content in sources.items():
                target = edition / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
            (edition.parent / "CLAUDE.md").write_text("# Unrelated project contract\n")
            self.assertEqual(ordinary_build_policy_problems(edition), [])


class LiveTddDriftTests(unittest.TestCase):
    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "70-lite-mode.md").write_text(LITE_SEAM_QUESTION)
        (root / "CHANGELOG.md").write_text("# Changelog\n")
        return root

    def check(self, root: Path) -> list[str]:
        return live_tdd_drift_problems(root, root / "CHANGELOG.md")

    def test_current_contract_passes(self) -> None:
        root = self.root()
        (root / "guide.html").write_text("Red, then green. Refactor during review.")
        self.assertEqual(self.check(root), [])

    def test_stale_tdd_phrase_is_rejected_across_live_surface_types(self) -> None:
        stale_phrases = (
            "Red, green, refactor",
            "RED → GREEN → REFACTOR",
            "red -> green -> refactor",
            "red, then green, then tidy-up",
            "failing test → code → green → refactor",
        )
        for suffix in ("md", "html", "js"):
            for phrase in stale_phrases:
                with self.subTest(suffix=suffix, phrase=phrase):
                    root = self.root()
                    (root / f"surface.{suffix}").write_text(phrase)
                    problems = self.check(root)
                    self.assertTrue(
                        any("stale pre-v1.1 TDD loop" in problem for problem in problems)
                    )

    def test_migration_history_may_quote_historical_wording(self) -> None:
        root = self.root()
        migration = root / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md"
        migration.parent.mkdir(parents=True)
        migration.write_text("Historical contract: RED → GREEN → REFACTOR")
        self.assertEqual(self.check(root), [])

    def test_legacy_process_route_is_rejected(self) -> None:
        root = self.root()
        (root / "guide.md").write_text("../processes/matt-pocock-inspired/AI-ENGINEERING-PROCESS.md")
        self.assertTrue(any("legacy pre-v1.0" in problem for problem in self.check(root)))

    def test_lite_mode_must_confirm_the_test_seam(self) -> None:
        root = self.root()
        (root / "70-lite-mode.md").write_text("How will we know it works?")
        self.assertTrue(any("confirm the public test seam" in problem for problem in self.check(root)))

    def test_missing_lite_mode_is_reported_as_missing_seam_contract(self) -> None:
        root = self.root()
        (root / "70-lite-mode.md").unlink()
        self.assertTrue(any("confirm the public test seam" in problem for problem in self.check(root)))

    def test_changelog_may_quote_historical_wording(self) -> None:
        root = self.root()
        (root / "CHANGELOG.md").write_text("Fixed: Red, green, refactor")
        self.assertEqual(self.check(root), [])


class ArchitectureIssueProvenanceTests(unittest.TestCase):
    STAGE_CONTRACT = """### Tracker provenance for findings

- Add `Source skill: /improve-codebase-architecture` to the issue body.
- Create or reuse the tracker label `source:improve-codebase-architecture` and apply it to every umbrella issue, slice, or follow-up directly produced from this review.
- Carry both markers into stage 04 or any later ticket split. Do not apply the label merely because an independently created issue is architecture-related.
- If the tracker has no labels, the source line is the required fallback. Before closing the review, query the created issues and verify that each direct descendant carries the available marker.
"""
    BREAKDOWN_CONTRACT = """### Preserve source metadata

When the approved input came from stage 06's architecture review, every published umbrella, slice, and direct follow-up preserves both markers:

- `Source skill: /improve-codebase-architecture` in the issue body.
- Tracker label `source:improve-codebase-architecture` when labels are supported.

Propagate the markers through later re-slicing. Do not infer them for merely related architecture work created from another review or request.
"""

    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        process = root / "10-process"
        process.mkdir()
        return root

    def test_stage_and_breakdown_keep_the_origin_contract(self) -> None:
        root = self.root()
        (root / "10-process" / "06-architecture.md").write_text(self.STAGE_CONTRACT)
        (root / "10-process" / "04-breakdown.md").write_text(self.BREAKDOWN_CONTRACT)
        self.assertEqual(architecture_issue_provenance_problems(root), [])

    def test_each_missing_contract_clause_is_rejected(self) -> None:
        fixtures = {
            Path("10-process/06-architecture.md"): self.STAGE_CONTRACT,
            Path("10-process/04-breakdown.md"): self.BREAKDOWN_CONTRACT,
        }
        for relative, contracts in ARCHITECTURE_PROVENANCE_CONTRACTS.items():
            for contract in contracts:
                with self.subTest(relative=str(relative), contract=contract):
                    root = self.root()
                    for fixture_path, text in fixtures.items():
                        (root / fixture_path).write_text(text)
                    path = root / relative
                    path.write_text(path.read_text().replace(contract, ""))
                    problems = architecture_issue_provenance_problems(root)
                    self.assertTrue(
                        any(str(relative) in problem and repr(contract) in problem for problem in problems)
                    )


class EmbeddedUpstreamContractTests(unittest.TestCase):
    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for relative, contracts in EMBEDDED_UPSTREAM_CONTRACTS.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(contracts))
        return root

    def test_complete_embedded_contract_passes(self) -> None:
        self.assertEqual(embedded_upstream_contract_problems(self.root()), [])

    def test_each_missing_contract_clause_is_rejected(self) -> None:
        for relative, contracts in EMBEDDED_UPSTREAM_CONTRACTS.items():
            for contract in contracts:
                with self.subTest(relative=str(relative), contract=contract):
                    root = self.root()
                    path = root / relative
                    path.write_text(path.read_text().replace(contract, ""))
                    problems = embedded_upstream_contract_problems(root)
                    self.assertTrue(
                        any(str(relative) in problem and repr(contract) in problem for problem in problems)
                    )

    def test_adapter_rejects_transaction_owning_commands(self) -> None:
        for command in ("git commit", "git stash", "git push"):
            with self.subTest(command=command):
                root = self.root()
                skill = root / "skills" / "ai-playbook-design-review" / "SKILL.md"
                skill.write_text(skill.read_text() + f"\n{command}\n")
                self.assertTrue(
                    any(command in problem for problem in embedded_upstream_contract_problems(root))
                )


class UpstreamContractTests(unittest.TestCase):
    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for _, relative, contracts in UPSTREAM_BEHAVIOUR_CONTRACTS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(contracts))
        (root / "CHANGELOG.md").write_text("# Changelog\n")
        return root

    def registry(self) -> upstream_registry.Registry:
        payload = {
            "schema_version": 1,
            "packages": {
                "mattpocock-skills": {
                    "kind": "upstream", "source": "https://example.com/matt",
                    "adoption_level": "accelerator",
                    "pin": {"kind": "tag", "value": "v9.9.9", "commit": "abcdef0123456"},
                    "install": {"method": "skills-cli"},
                    "harness_name_pattern": {"claude": "/{name}"},
                },
                "playbook": {"kind": "local", "source": "v0.5/skills"},
            },
            "skills": {
                "alpha": {
                    "package": "mattpocock-skills", "invocation": "user",
                    "previous_names": [{"name": "old-alpha", "upstream_version": "v1.1.0"}],
                    "stages": ["03"],
                },
                "old-beta": {
                    "package": "mattpocock-skills", "invocation": "user",
                    "status": "removed", "removed_in": "V0.4.1",
                },
            },
        }
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "upstream-skills.json"
        path.write_text(json.dumps(payload))
        return upstream_registry.load(path)

    def check(self, root: Path) -> list[str]:
        return upstream_contract_problems(root, root / "CHANGELOG.md", self.registry())

    def test_complete_contract_passes(self) -> None:
        self.assertEqual(self.check(self.root()), [])

    def test_active_old_skill_name_is_rejected(self) -> None:
        root = self.root()
        (root / "guide.md").write_text("Use /old-alpha for new work.\n")
        self.assertTrue(any("old-alpha is live" in problem for problem in self.check(root)))

    def test_formerly_context_allows_old_name(self) -> None:
        root = self.root()
        (root / "guide.md").write_text("Use /alpha (formerly /old-alpha).\n")
        self.assertEqual(self.check(root), [])

    def test_missing_route_contract_is_rejected(self) -> None:
        root = self.root()
        path = root / "10-process" / "00-prereqs.md"
        path.write_text(path.read_text().replace("/writing-for-agents", ""))
        self.assertTrue(any("/writing-for-agents" in problem for problem in self.check(root)))

    def test_wrong_matt_version_is_rejected(self) -> None:
        root = self.root()
        (root / "guide.md").write_text("mattpocock/skills v8.8.8\n")
        self.assertTrue(any("v8.8.8" in problem for problem in upstream_version_problems(root, self.registry())))

    def test_skill_named_in_an_undeclared_stage_is_rejected(self) -> None:
        root = self.root()
        process = root / "10-process"
        (process / "03-spec.md").write_text("no route\n")
        (process / "04-breakdown.md").write_text("/alpha\n")
        self.assertTrue(any("undeclared stage 04" in problem for problem in stage_membership_problems(root, self.registry())))

    def test_skill_missing_from_a_declared_stage_is_rejected(self) -> None:
        root = self.root()
        process = root / "10-process"
        (process / "03-spec.md").write_text("no route\n")
        self.assertTrue(any("declared stage 03" in problem for problem in stage_membership_problems(root, self.registry())))


class ModelRoutingTrackContractTests(unittest.TestCase):
    FULL_TEXT = "\n\n".join(MODEL_ROUTING_TRACK_CONTRACTS)

    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / "93-model-routing-track.md").write_text(self.FULL_TEXT)
        return root

    def test_complete_contract_passes(self) -> None:
        self.assertEqual(model_routing_track_contract_problems(self.root()), [])

    def test_missing_track_file_is_rejected(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        problems = model_routing_track_contract_problems(root)
        self.assertTrue(any("model-routing track missing" in problem for problem in problems))

    def test_each_missing_contract_is_rejected(self) -> None:
        for contract in MODEL_ROUTING_TRACK_CONTRACTS:
            with self.subTest(contract=contract):
                root = self.root()
                path = root / "93-model-routing-track.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_routing_track_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))

    def test_verify_runner_preference_contracts_are_required(self) -> None:
        preference_contracts = (
            "## Verify runner preference",
            "Verify prefers a runner other than the Build runner that actually ran",
            "relative to the Build runner that actually ran, never to the default lane table",
            "The Build lane's coverage of stage 07 and returned fixes carries the preference",
            "A project with one available runner reads this same rule and is not interrupted",
        )
        for contract in preference_contracts:
            with self.subTest(contract=contract):
                self.assertIn(contract, MODEL_ROUTING_TRACK_CONTRACTS)
                root = self.root()
                path = root / "93-model-routing-track.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_routing_track_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))

    def test_fallback_and_record_field_contracts_are_required(self) -> None:
        fallback_contracts = (
            "When no different runner is reachable, Verify proceeds on an available runner and records the fallback",
            "the preference never stops the run by itself",
            "it never substitutes a runner silently",
        )
        record_field_contracts = (
            "for Verify selections only: `cross_runner` (`true` or `false`)",
            "`cross_runner_reason` from a closed set — `single_runner_project`, `preferred_runner_unavailable`,",
            "`null` when `cross_runner` is `true`",
        )
        closed_set_contracts = (
            "single_runner_project",
            "preferred_runner_unavailable",
            "human_override",
        )
        for contract in fallback_contracts + record_field_contracts + closed_set_contracts:
            with self.subTest(contract=contract):
                self.assertIn(contract, MODEL_ROUTING_TRACK_CONTRACTS)
                root = self.root()
                path = root / "93-model-routing-track.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_routing_track_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))

    def test_worked_examples_are_required(self) -> None:
        worked_example_contracts = (
            "Worked example: Build actually ran on `claude-code`",
            "prefers a runner other than `claude-code` — for example `codex` — ahead of offering `claude-code` itself",
            "Worked fallback example: a project configures only `claude-code`",
            "records `cross_runner: false` with `cross_runner_reason: single_runner_project`",
        )
        for contract in worked_example_contracts:
            with self.subTest(contract=contract):
                self.assertIn(contract, MODEL_ROUTING_TRACK_CONTRACTS)
                root = self.root()
                path = root / "93-model-routing-track.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_routing_track_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))


class ModelRouterSkillRoutingContractTests(unittest.TestCase):
    FULL_TEXT = "\n\n".join(MODEL_ROUTER_SKILL_ROUTING_CONTRACTS)

    def root(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        skill_dir = root / "skills" / "model-router"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(self.FULL_TEXT)
        return root

    def test_complete_contract_passes(self) -> None:
        self.assertEqual(model_router_skill_routing_contract_problems(self.root()), [])

    def test_missing_skill_file_is_rejected(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        problems = model_router_skill_routing_contract_problems(root)
        self.assertTrue(any("local model-router skill missing" in problem for problem in problems))

    def test_each_missing_contract_is_rejected(self) -> None:
        for contract in MODEL_ROUTER_SKILL_ROUTING_CONTRACTS:
            with self.subTest(contract=contract):
                root = self.root()
                path = root / "skills" / "model-router" / "SKILL.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_router_skill_routing_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))

    def test_step_2_and_step_4_contracts_are_required(self) -> None:
        step_2_contracts = (
            "worker-result envelope's `runner` field is authoritative",
            "read the persisted lane record only when no envelope is available",
            "discovery to prefer a runner other than that one, per `93-model-routing-track.md`'s Verify runner preference",
            "A project with one available runner has no alternate to prefer, so discovery proceeds unchanged",
        )
        step_4_contracts = (
            "For Verify, also persist `cross_runner`",
            "`cross_runner_reason` from `93-model-routing-track.md`'s closed set",
        )
        for contract in step_2_contracts + step_4_contracts:
            with self.subTest(contract=contract):
                self.assertIn(contract, MODEL_ROUTER_SKILL_ROUTING_CONTRACTS)
                root = self.root()
                path = root / "skills" / "model-router" / "SKILL.md"
                path.write_text(self.FULL_TEXT.replace(contract, ""))
                problems = model_router_skill_routing_contract_problems(root)
                self.assertTrue(any(contract in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()

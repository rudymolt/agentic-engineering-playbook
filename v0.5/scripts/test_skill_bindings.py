"""Fixture proof at the public Configure and stage-owned dispatch boundaries."""

import hashlib
import json
import errno
from functools import lru_cache
import os
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

from playbook_config import Configuration, ConfigError
from skill_bindings import JobBindings, JOBS
from test_playbook_config import ConfigurationFixture


@lru_cache(maxsize=1)
def ordinary_dac_denies():
    """Probe the effective process, since non-root users may hold DAC caps."""
    if sys.platform != "linux":
        return False
    with tempfile.TemporaryDirectory() as temporary:
        target = Path(temporary) / "denied"
        target.write_text("fixture")
        target.chmod(0)
        try:
            result = subprocess.run(
                [sys.executable, "-c", "from pathlib import Path; import sys; "
                 "Path(sys.argv[1]).read_bytes()", str(target)], capture_output=True)
            return result.returncode != 0 and b"PermissionError" in result.stderr
        finally:
            target.chmod(0o600)


def dac_isolation_available():
    return sys.platform == "linux" and (ordinary_dac_denies() or shutil.which("setpriv") is not None)


def dac_isolation_command(command):
    # Some non-root containers also hold a DAC override capability.
    if not ordinary_dac_denies():
        return ["setpriv", "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all", *command]
    return command


def qualified_qa(project):
    route = ".agents/skills/verify-fixture"
    directory = project / route
    directory.mkdir(parents=True)
    source = directory / "SKILL.md"
    source.write_text("existing independently qualified project route\n")
    state = project / ".playbook-state.yml"
    original = state.read_text() if state.exists() else ""
    state.write_text(original + f"decisions:\n  verification_harness_path: {route}\n"
                     f"  verification_harness_binding: {route}\n  verification_map_maintenance: false\n")
    observed = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "verdict": "pass", "independent": True,
                "lifecycle": ["Launch", "Doctor", "Drive", "Evidence", "Cleanup"],
                "outputs": JOBS["application_qa"]["outputs"], "effects": JOBS["application_qa"]["effects"]}
    evidence = project / "qa-proof.json"
    evidence.write_text(json.dumps(observed))
    proof = {"contract_version": 1, "owner": "09", "route": route,
             "source_sha256": observed["source_sha256"], "evidence": "qa-proof.json",
             "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(), "mode": "project-report-only"}
    record = project / ".playbook-qa-eligibility.json"
    record.write_text(json.dumps(proof))
    return route, source, record, proof


class BindingTests(ConfigurationFixture):
    def setUp(self):
        super().setUp()
        self.bindings = JobBindings(self.project)
        self.service = Configuration(self.project, self.discover, lambda: "2026-09-29T12:00:00Z",
                                     bindings=self.bindings)

    def test_live_inventory_is_fresh_between_reads_and_shared_within_each_read(self):
        with patch.object(self.bindings, "_installed", wraps=self.bindings._installed) as scan:
            first = self.service.read()
            self.assertEqual("decision_required", first["state"])
            self.assertEqual(1, scan.call_count)
            second = self.service.read()
            self.assertEqual("decision_required", second["state"])
            self.assertEqual(2, scan.call_count)
            self.bindings.options("code_review")
            self.assertEqual(3, scan.call_count)

    def pick(self, proposal, job, ids):
        editor = self.service.reply(proposal, "Edit skills " + job)
        indexes = [str(next(index + 1 for index, choice in enumerate(editor["skill_options"])
                           if choice["binding"]["source_id"] == identity)) for identity in ids]
        return self.service.reply(editor, "Choose " + ",".join(indexes))

    def preview_bindings(self):
        proposal = self.preview()
        return self.pick(proposal, "alignment", ["playbook:alignment-context", "playbook:alignment-decisions"])

    def test_saved_composition_reaches_owner_without_changing_customisations(self):
        custom = self.project / "custom.md"
        custom.write_text("intentional project customisation\n")
        preview = self.preview_bindings()
        self.assertEqual(preview["state"], "proposal_ready")
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        reopened = self.service.read()
        self.assertEqual(reopened["skill_before"], preview["skill_after"])
        calls = []
        result = self.service.dispatch_job("alignment", "01", lambda route: calls.append(route))
        self.assertEqual([route["source_id"] for route in calls],
                         ["playbook:alignment-context", "playbook:alignment-decisions"])
        self.assertEqual(result["owner"], "01")
        self.assertIn("human confirmation", result["retained_authority"])
        self.assertEqual(self.state.read_bytes(), self.runtime)
        self.assertEqual(custom.read_text(), "intentional project customisation\n")
        self.assertEqual(json.loads(self.approval.read_text())["routes"]["build"]["model"], "approved")
        saved = json.loads((self.project / ".playbook-config.json").read_text())
        self.assertNotIn(str(self.project), json.dumps(saved))
        with self.assertRaises(ConfigError):
            self.service.dispatch_job("alignment", "07", lambda route: self.fail("wrong owner"))

    def test_source_labels_in_proposal_editor_and_changes(self):
        proposal = self.preview()
        self.assertTrue(all(row["after"] for row in proposal["skill_proposal"]))
        editor = self.service.reply(proposal, "Edit skills implementation")
        self.assertTrue(all(choice["label"].startswith("(Playbook ") for choice in editor["skill_options"]))
        preview = self.pick(proposal, "implementation", ["playbook:implementation-adapter"])
        self.assertIn("(Playbook adapter)", next(row for row in preview["skill_changes"]
                                               if row["job"] == "implementation")["after"][0])
        self.assertEqual(self.service.reply(self.service.reply(editor, "Choose 999"), "Back"), editor)

    def test_job_fallbacks_retain_all_stage_obligations(self):
        proposal = self.preview()
        for job in JOBS:
            proposal = self.pick(proposal, job, ["playbook:" + job + "-manual"])
        self.assertEqual(self.service.reply(proposal, "Apply")["state"], "applied")
        for job, contract in JOBS.items():
            calls = []
            result = self.service.dispatch_job(job, contract["owner"], lambda route: calls.append(route))
            self.assertEqual(calls[0]["form"], "manual")
            self.assertIn("permission boundaries", result["retained_authority"])
            self.assertEqual(result["contract_version"], 1)
        editor = self.service.reply(self.service.read(), "Edit skills specification")
        self.assertEqual(self.service.reply(editor, "Choose 1,2")["state"], "blocked")

    def test_unknown_and_newer_contracts_block_without_writes(self):
        self.assertEqual(self.service.reply(self.preview_bindings(), "Apply")["state"], "applied")
        destination = self.project / ".playbook-config.json"
        saved = json.loads(destination.read_text())
        for mutation in ("version", "source", "path"):
            candidate = json.loads(json.dumps(saved))
            if mutation == "version":
                candidate["skills"]["contract_version"] = 2
            elif mutation == "source":
                candidate["skills"]["jobs"]["alignment"][0]["source_id"] = "unknown:skill"
            else:
                candidate["skills"]["jobs"]["alignment"][0]["path"] = str(self.project)
            destination.write_text(json.dumps(candidate))
            with self.assertRaises(ConfigError):
                self.service.dispatch_job("alignment", "01", lambda route: self.fail("unverified invocation"))

    def stage_entry(self, job, owner, approved_binding=None):
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "job-route"]
        request = {"job": job, "owner": owner}
        if approved_binding is not None:
            request["approved_binding"] = approved_binding
        result = subprocess.run(command, input=json.dumps(request),
                                capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def test_public_stage_entries_consume_each_saved_binding(self):
        preview = self.preview_bindings()
        for job in ("specification", "implementation", "code_review"):
            preview = self.pick(preview, job, ["playbook:" + job + "-adapter"])
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        before = {str(path.relative_to(self.project)): path.read_bytes()
                  for path in self.project.rglob("*") if path.is_file()}
        for job, contract in JOBS.items():
            with self.subTest(job=job):
                code, entry = self.stage_entry(job, contract["owner"])
                self.assertEqual(code, 0)
                self.assertTrue(entry["configured"])
                self.assertEqual([route["binding"] for route in entry["routes"]], preview["skill_after"]["jobs"][job])
                self.assertEqual(entry["contract"], contract)
                self.assertEqual(entry["owner"], contract["owner"])
                self.assertFalse(entry["launched"])
                instructions = Path(__file__).parent.parent / "10-process" / contract["stage"]
                text = instructions.read_text()
                self.assertIn(json.dumps({"job": job, "owner": contract["owner"]}, separators=(",", ":")), text)
                self.assertIn("job-route", text)
                self.assertIn("stage " + contract["owner"], entry["routes"][0]["invocation"])
                self.assertIn("permission boundaries", entry["retained_authority"])
        code, blocked = self.stage_entry("implementation", "08")
        self.assertEqual(code, 2)
        self.assertEqual(blocked["state"], "blocked")
        self.assertEqual(before, {str(path.relative_to(self.project)): path.read_bytes()
                                 for path in self.project.rglob("*") if path.is_file()})

    def test_cli_source_drift_blocks_instead_of_invoking_a_default(self):
        self.assertEqual(self.service.reply(self.preview_bindings(), "Apply")["state"], "applied")
        destination = self.project / ".playbook-config.json"
        config = json.loads(destination.read_text())
        config["skills"]["jobs"]["alignment"][0]["source_sha256"] = "0" * 64
        destination.write_text(json.dumps(config))
        code, result = self.stage_entry("alignment", "01")
        self.assertEqual(code, 2)
        self.assertEqual(result["state"], "blocked")
        self.assertFalse(result["launched"])
        reloaded = self.service.read()
        self.assertIn("blocked", reloaded["skill_proposal"][0]["after"][0])
        fixed = self.pick(reloaded, "alignment", ["playbook:alignment-manual"])
        self.assertEqual(self.service.reply(fixed, "Apply")["state"], "applied")
        code, result = self.stage_entry("alignment", "01")
        self.assertEqual(code, 0)
        self.assertEqual(result["routes"][0]["form"], "manual")

    def test_saved_project_qa_reaches_public_stage_entry_without_creating_harness(self):
        route, source, record, proof = qualified_qa(self.project)
        before = {str(path.relative_to(self.project)): path.read_bytes()
                  for path in self.project.rglob("*") if path.is_file()}
        preview = self.pick(self.preview(), "application_qa", ["project:" + route])
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        self.assertEqual(self.service.read()["skill_before"], preview["skill_after"])
        code, entry = self.stage_entry("application_qa", "09")
        self.assertEqual(code, 0)
        self.assertEqual(entry["routes"][0]["invocation"], route + "/SKILL.md")
        self.assertEqual(entry["routes"][0]["label"], "(Project route) " + route)
        for locator, contents in before.items():
            self.assertEqual((self.project / locator).read_bytes(), contents)
        self.assertEqual(len(list(self.project.glob(".agents/skills/*"))), 1)
        source.write_text("drifted selected project QA source\n")
        code, blocked = self.stage_entry("application_qa", "09")
        self.assertEqual(code, 2)
        self.assertEqual(blocked["state"], "blocked")

    def test_public_entry_retains_approved_execution_binding_over_new_default(self):
        preview = self.preview_bindings()
        approved = json.loads(json.dumps(preview["skill_after"]))
        preview = self.pick(preview, "implementation", ["playbook:implementation-adapter"])
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        code, entry = self.stage_entry("implementation", "07", approved)
        self.assertEqual(code, 0)
        self.assertEqual(entry["origin"], "approved execution")
        self.assertEqual(entry["routes"][0]["form"], "manual")
        code, new = self.stage_entry("implementation", "07")
        self.assertEqual(new["routes"][0]["form"], "adapter")
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def save_qa_selection(self):
        route, source, record, proof = qualified_qa(self.project)
        preview = self.pick(self.preview(), "application_qa", ["project:" + route])
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        destination = self.project / ".playbook-config.json"
        return source, record, self.project / proof["evidence"], destination.read_bytes()

    def assert_private_qa_rejection(self, result, saved, artifact, error_class):
        text = json.dumps(result)
        self.assertNotIn(str(self.project), text)
        self.assertNotIn("private-diagnostic-token", text)
        rejection = next(item for item in result["skill_rejections"]
                         if item["source_id"] == "project:application_qa")
        self.assertIn(artifact, rejection["reason"])
        self.assertIn(error_class, rejection["reason"])
        self.assertIn("stage 09", rejection["reason"])
        self.assertIn("explicitly", rejection["reason"])
        self.assertEqual(result["state"], "decision_required")
        qa_row = next(row for row in result["skill_proposal"] if row["job"] == "application_qa")
        self.assertIn("unresolved/blocked", qa_row["after"][0])
        self.assertFalse(result["launched"])
        self.assertEqual((self.project / ".playbook-config.json").read_bytes(), saved)

    def test_qa_read_and_fingerprint_errors_are_private_at_configure_seam(self):
        source, record, evidence, saved = self.save_qa_selection()
        for target, artifact, seam in ((record, "eligibility record", "read_text"),
                                       (evidence, "retained evidence", "read_text"),
                                       (source, "skill source", "read_bytes"),
                                       (record, "eligibility record", "read_bytes"),
                                       (evidence, "retained evidence", "read_bytes")):
            for error_type in (PermissionError, FileNotFoundError, OSError):
                with self.subTest(artifact=artifact, seam=seam, error=error_type.__name__):
                    original = getattr(Path, seam)

                    def denied(path, *args, **kwargs):
                        if path == target:
                            raise error_type(errno.EIO, "private-diagnostic-token", str(target))
                        return original(path, *args, **kwargs)

                    with patch.object(Path, seam, denied):
                        result = self.service.read()
                        self.assert_private_qa_rejection(result, saved, artifact, error_type.__name__)
                        with self.assertRaisesRegex(ConfigError, "unresolved"):
                            self.service.dispatch_job("application_qa", "09")
                        self.assertEqual(self.service.reply(result, "Apply")["state"], "blocked")
                    self.assertEqual((self.project / ".playbook-config.json").read_bytes(), saved)

    def test_qa_invalid_record_diagnostics_do_not_echo_untrusted_keys(self):
        source, record, evidence, saved = self.save_qa_selection()
        record.write_text(json.dumps({str(self.project): 1})[:-1] + "," +
                          json.dumps(str(self.project)) + ":2}")
        self.assert_private_qa_rejection(self.service.read(), saved, "eligibility record", "invalid qualification")

    @unittest.skipUnless(dac_isolation_available(), "requires Linux DAC isolation")
    def test_cli_unreadable_qa_artifacts_are_private(self):
        source, record, evidence, saved = self.save_qa_selection()
        adapter = ("import json,sys; request=json.load(sys.stdin); "
                   "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-1',"
                   "'routes':[{'model_id':'available-build','runner':'codex','reasoning':'medium',"
                   "'roles':['implementation']}]},sys.stdout)")
        command = dac_isolation_command([
            sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
            "--project", str(self.project), "--discovery-command",
            json.dumps([sys.executable, "-c", adapter]), "read"])
        for target, artifact in ((record, "eligibility record"), (evidence, "retained evidence"),
                                 (source, "skill source")):
            with self.subTest(artifact=artifact):
                mode = target.stat().st_mode
                target.chmod(0)
                try:
                    result = subprocess.run(command, input="{}", capture_output=True, text=True,
                                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn(str(self.project), result.stderr)
                    self.assert_private_qa_rejection(json.loads(result.stdout), saved, artifact, "PermissionError")
                finally:
                    target.chmod(mode)

    def test_upstream_provenance_on_all_surfaces_and_changed_source_blocks_apply(self):
        source = self.project / "review-source.md"
        source.write_text("fixture exact independently audited report-only source\n")
        entry = json.loads((Path(__file__).parent.parent / "upstream-integrations.json").read_text())["integrations"]["code-review"]
        entry.update(embedded_compatible=True, compatible_mode="report-only", embedded_invocation="/code-review --report-only",
                     tested_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        manifest = self.project / "compatibility.json"
        manifest.write_text(json.dumps({"schema_version": 1, "integrations": {"code-review": entry}}))
        self.service.bindings = JobBindings(self.project, installed={"mattpocock-skills:code-review": [source]}, manifest=manifest)
        preview = self.pick(self.preview(), "code_review", ["mattpocock-skills:code-review"])
        for surface in ("skill_proposal", "skill_changes"):
            self.assertEqual(next(row for row in preview[surface] if row["job"] == "code_review")["after"], ["(Matt Pocock) code-review"])
        editor = self.service.reply(preview, "Edit skills code review")
        self.assertEqual(editor["skill_options"][-1]["provenance"]["kind"], "unmodified-upstream")
        source.write_text("changed selected source\n")
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "blocked")
        self.assertFalse((self.project / ".playbook-config.json").exists())


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.source = self.project / "review.md"
        self.source.write_text("fixture exact reviewed source\n")
        self.manifest = self.project / "integrations.json"
        self.entry = {
            "upstream": "mattpocock/skills", "tested_version": "fixture",
            "tested_source_sha256": hashlib.sha256(self.source.read_bytes()).hexdigest(),
            "embedded_compatible": True, "compatible_mode": "report-only",
            "embedded_invocation": "/code-review --report-only", "adapter": "stage 08",
            "compatibility_evidence": "fixture bounded contract audit", "last_verified": "2026-09-29",
            "required_outputs": JOBS["code_review"]["outputs"],
            "permitted_side_effects": JOBS["code_review"]["effects"],
            "prohibited_side_effects": ["product or source edits", "commits", "configuration changes", "self-upgrade"],
            "fallback": "manual: stage 08",
        }
        self.write_manifest()

    def write_manifest(self):
        self.manifest.write_text(json.dumps({"schema_version": 1, "integrations": {"code-review": self.entry}}))

    def catalog(self, installed=None):
        return JobBindings(self.project, installed=installed or {"mattpocock-skills:code-review": [self.source]},
                           manifest=self.manifest)

    def test_exact_eligible_source_and_changed_fingerprint(self):
        bindings = self.catalog()
        choice = next(choice for choice in bindings.options("code_review")
                      if choice["binding"]["source_id"] == "mattpocock-skills:code-review")
        self.assertEqual(choice["label"], "(Matt Pocock) code-review")
        saved = bindings.defaults()
        saved["jobs"]["code_review"] = [choice["binding"]]
        calls = []
        bindings.dispatch(saved, "code_review", "08", lambda route: calls.append(route))
        self.assertEqual(calls[0]["invocation"], "/code-review --report-only")
        self.source.write_text("changed source\n")
        with self.assertRaises(ConfigError):
            bindings.dispatch(saved, "code_review", "08", lambda route: self.fail("source drift bypass"))

    def test_registry_or_installation_never_certifies_contract(self):
        for change in ("incompatible", "outputs", "effects"):
            with self.subTest(change=change):
                if change == "incompatible":
                    self.entry.update(embedded_compatible=False, compatible_mode="none", embedded_invocation=None)
                elif change == "outputs":
                    self.entry.update(embedded_compatible=True, compatible_mode="report-only",
                                      embedded_invocation="/code-review --report-only", required_outputs=["verdict"])
                else:
                    self.entry.update(required_outputs=JOBS["code_review"]["outputs"], permitted_side_effects=["commits"])
                self.write_manifest()
                self.assertFalse(any(choice["binding"]["source_id"] == "mattpocock-skills:code-review"
                                     for choice in self.catalog().options("code_review")))

    def test_source_collision_and_same_name_require_logical_identity(self):
        second = self.project / "second.md"
        second.write_bytes(self.source.read_bytes())
        collided = self.catalog({"mattpocock-skills:code-review": [self.source, second]})
        self.assertFalse(any(choice["binding"]["source_id"] == "mattpocock-skills:code-review"
                             for choice in collided.options("code_review")))
        self.assertIn("collision", json.dumps(collided.rejections))
        unknown = self.catalog({"unknown:code-review": [self.source]})
        self.assertFalse(any(choice["label"] == "(Matt Pocock) code-review"
                             for choice in unknown.options("code_review")))

    def qa_proof(self):
        return qualified_qa(self.project)

    def test_existing_qa_selection_never_creates_or_maintains_harness(self):
        route, source, record, proof = self.qa_proof()
        bindings = self.catalog()
        before = {str(path.relative_to(self.project)): path.read_bytes()
                  for path in self.project.rglob("*") if path.is_file()}
        options = bindings.options("application_qa")
        project = next(option for option in options if option["form"] == "project route")
        saved = bindings.defaults()
        saved["jobs"]["application_qa"] = [project["binding"]]
        calls = []
        result = bindings.dispatch(saved, "application_qa", "09", lambda value: calls.append(value))
        self.assertEqual(calls[0]["invocation"], route + "/SKILL.md")
        self.assertIn("maintenance opt-in", result["retained_authority"])
        after = {str(path.relative_to(self.project)): path.read_bytes()
                 for path in self.project.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        source.write_text("source drift\n")
        with self.assertRaises(ConfigError):
            bindings.dispatch(saved, "application_qa", "09", lambda value: self.fail("QA drift invoked"))

    def test_qa_exact_embedded_checker_cannot_be_bypassed(self):
        route, source, record, proof = self.qa_proof()
        proof.update(mode="embedded-report-only", embedded_source_id="gstack:qa-only")
        record.write_text(json.dumps(proof))
        qa_entry = {**self.entry, "upstream": "garrytan/gstack",
                    "embedded_invocation": "/qa-only --report-only",
                    "required_outputs": JOBS["application_qa"]["outputs"],
                    "permitted_side_effects": JOBS["application_qa"]["effects"]}
        self.manifest.write_text(json.dumps({"schema_version": 1, "integrations": {"qa-only": qa_entry}}))
        bindings = self.catalog({"gstack:qa-only": [self.source]})
        from skill_bindings import COMPATIBILITY
        with patch.object(COMPATIBILITY, "evaluate", wraps=COMPATIBILITY.evaluate) as checker:
            choices = bindings.options("application_qa")
            self.assertTrue(any(option["form"] == "project route" for option in choices))
            self.assertEqual(checker.call_args.args[:2], ("qa-only", self.source))
        saved = bindings.defaults()
        saved["jobs"]["application_qa"] = [choices[-1]["binding"]]
        self.source.write_text("changed embedded source\n")
        with self.assertRaises(ConfigError):
            bindings.dispatch(saved, "application_qa", "09", lambda value: self.fail("checker bypass"))

    def test_stage_owned_qa_proof_not_installation_or_self_description(self):
        route, source, record, proof = self.qa_proof()
        proof["contract_version"] = True
        record.write_text(json.dumps(proof))
        self.assertFalse(any(option["form"] == "project route" for option in self.catalog().options("application_qa")))
        proof["contract_version"] = 1
        proof["mode"] = "upstream-derived-adaptation"
        record.write_text(json.dumps(proof))
        self.assertFalse(any(option["form"] == "project route" for option in self.catalog().options("application_qa")))

    def test_manifest_evidence_changes_invalidate_previous_eligibility(self):
        bindings = self.catalog()
        saved = bindings.defaults()
        saved["jobs"]["code_review"] = [bindings.options("code_review")[-1]["binding"]]
        self.entry["embedded_invocation"] = "/code-review --new-report-mode"
        self.write_manifest()
        with self.assertRaises(ConfigError):
            bindings.dispatch(saved, "code_review", "08", lambda value: self.fail("unreviewed contract invoked"))


if __name__ == "__main__":
    unittest.main()

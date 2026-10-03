"""S5 public Configure and bootstrap reuse boundaries."""

from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from playbook_config import Configuration, ROLES
from skill_bindings import JobBindings, JOBS, AUTHORITY, fingerprint


class PersonalPresetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.local = self.root / "personal"
        self.projects = [self.root / name for name in ("first", "second")]
        for project in self.projects:
            project.mkdir()
            (project / ".playbook-state.yml").write_text(
                "pending_model_routes: [{status: approved}]\nactive_features: [{routing: retained}]\nhistory: untouched\n")
        self.runtime = [(project / ".playbook-state.yml").read_bytes() for project in self.projects]

    def discover(self, request):
        return {"request_id": request["request_id"], "checked_at": request["started_at"],
                "authority": "host-reported-selection", "revision": "fixture-1",
                "routes": [{"model_id": "fixture-model", "runner": "codex", "reasoning": "high", "roles": list(ROLES)}]}

    def service(self, index=0, checkpoint=None):
        return Configuration(self.projects[index], self.discover, lambda: "2026-10-01T12:00:00Z",
                             preferences_dir=self.local, checkpoint=checkpoint)

    def command(self, action, proposal=None, reply=None, index=0, fault=None, custom=None):
        adapter = ("import json,sys; request=json.load(sys.stdin); "
                   "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-1',"
                   "'routes':[{'model_id':'fixture-model','runner':'codex','reasoning':'high',"
                   "'roles':['planning','implementation','verification','escalated_repair']}]},sys.stdout)")
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.projects[index]), "--preferences-dir", str(self.local),
                   "--discovery-command", json.dumps([sys.executable, "-c", adapter]),
                   "--now", "2026-10-01T12:00:00Z", action]
        if custom is not None:
            command[-1:-1] = ["--custom-bindings-dir", str(custom)]
        if fault:
            wrapper = ("import sys,runpy; from pathlib import Path; "
                       "sys.path.insert(0,str(Path(sys.argv[1]).parent)); "
                       "from playbook_config import Configuration; "
                       "original=Configuration.__init__\n"
                       "def initialize(self,*args,**kwargs):\n"
                       " original(self,*args,**kwargs)\n"
                       " def fail(point):\n"
                       "  if point == 'paired_first_written': " +
                       ("__import__('os')._exit(73)\n" if fault == "crash" else "raise OSError('unreviewed credential-bearing text')\n") +
                       " self.checkpoint=fail\n"
                       "Configuration.__init__=initialize\n"
                       "sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name='__main__')")
            command = [sys.executable, "-c", wrapper, *command[1:]]
        request = {} if proposal is None else {"proposal": proposal, "reply": reply}
        result = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        return result, json.loads(result.stdout) if result.stdout.strip() else None

    def draft(self, service):
        proposal = service.reply(service.read(), "Guided")
        for label in ("Plan", "Build", "Verify", "Repair"):
            proposal = service.reply(service.reply(proposal, "Edit " + label), "1")
        return proposal

    def save_preset(self):
        service = self.service()
        proposal = service.reply(self.draft(service), "Save preset Focus")
        self.assertEqual(proposal["step"], "preference_preview")
        result = service.reply(proposal, "Apply preference")
        self.assertEqual(result["state"], "proposal_ready", result)
        return service

    def test_save_load_isolation_and_deliberate_apply(self):
        service = self.save_preset()
        self.assertFalse((self.projects[0] / ".playbook-config.json").exists())
        other = self.service(1)
        proposal = other.read()
        self.assertEqual(proposal["presets"], ["Recommended", "Focus"])
        loaded = other.reply(proposal, "Load preset Focus")
        self.assertEqual(loaded["origins"]["implementation"], "personal preset Focus")
        self.assertEqual(loaded["origin"], "personal preset Focus")
        self.assertEqual(loaded["after"]["implementation"]["model_id"], "fixture-model")
        self.assertFalse((self.projects[1] / ".playbook-config.json").exists())
        self.assertEqual(other.reply(loaded, "Not now")["state"], "unchanged")
        self.assertEqual(other.reply(loaded, "Apply")["state"], "applied")
        saved = (self.projects[1] / ".playbook-config.json").read_text()
        self.assertNotIn("billing", saved)
        self.assertNotIn(str(self.local), saved)
        self.assertFalse((self.projects[0] / ".playbook-config.json").exists())
        for project, runtime in zip(self.projects, self.runtime):
            self.assertEqual((project / ".playbook-state.yml").read_bytes(), runtime)
        self.assertEqual(service.read()["state"], "decision_required")

    def test_combined_apply_has_paired_completion(self):
        service = self.service()
        proposal = service.reply(self.draft(service), "Save defaults")
        proposal = service.reply(proposal, "Billing mixed")
        proposal = service.reply(proposal, "Goal Fixture project")
        result = service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "applied", result)
        self.assertEqual(result["destinations"], proposal["destinations"])
        self.assertEqual(result["paired_completion"]["destinations"], proposal["destinations"])
        self.assertEqual(result["paired_completion"]["protocol"], "paired-1")
        self.assertTrue(result["paired_completion"]["validated"])
        self.assertTrue(result["paired_completion"]["runtime_unchanged"])
        personal = json.loads((self.local / "preferences.json").read_text())
        self.assertEqual(personal["billing"], "mixed")
        self.assertEqual(personal["defaults"]["models"], proposal["after"])
        self.assertEqual(service.read()["state"], "decision_required")

    def test_first_setup_reuse_preserves_unanswered_presentation(self):
        for reply in ("Save preset Unconfirmed", "Save defaults"):
            with self.subTest(reply=reply):
                service = self.service()
                proposal = service.reply(service.read(), "Goal Fixture project")
                self.assertEqual(proposal["questions"]["presentation"], "Guided / Expert")
                proposal = service.reply(proposal, reply)
                self.assertIn("presentation", proposal["missing_context"])
                blocked = service.reply(proposal, "Apply preference")
                self.assertEqual(blocked["state"], "blocked")
                self.assertFalse((self.local / "preferences.json").exists())
                proposal = service.reply(proposal, "Expert")
                self.assertNotIn("presentation", proposal["missing_context"])
                result = service.reply(proposal, "Apply preference")
                self.assertEqual(result["state"], "proposal_ready", result)
                saved = json.loads((self.local / "preferences.json").read_text())
                self.assertEqual(saved["presentation"], "expert")
                self.assertIn("presets" if reply.startswith("Save preset") else "defaults", saved)
                self.assertFalse(service.path.exists())
                (self.local / "preferences.json").unlink()

    def test_cli_paired_completion_reports_exact_local_destination_privately(self):
        _, proposal = self.command("read")
        for label in ("Plan", "Build", "Verify", "Repair"):
            _, proposal = self.command("reply", proposal, "Edit " + label)
            _, proposal = self.command("reply", proposal, "1")
        for reply in ("Expert", "Save defaults", "Billing mixed", "Goal Fixture project"):
            result, proposal = self.command("reply", proposal, reply)
            self.assertEqual(result.returncode, 0, result.stderr)
        result, applied = self.command("reply", proposal, "Apply")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(applied["destinations"], proposal["destinations"])
        self.assertEqual(applied["paired_completion"]["destinations"], proposal["destinations"])
        shared = (self.projects[0] / ".playbook-config.json").read_text()
        self.assertNotIn(str(self.local), shared)
        self.assertNotIn("billing", shared)
        self.assertEqual((self.projects[0] / ".playbook-state.yml").read_bytes(), self.runtime[0])

    def test_rollback_backup_mutation_at_publication_never_becomes_live(self):
        self.save_preset()
        service = self.service()
        self.assertEqual(service.reply(service.reply(service.read(), "Load preset Focus"), "Apply")["state"], "applied")
        previous = service.path.read_bytes()
        changed = b'{"changed_backup":"must not publish"}\n'
        original_link = Configuration._link
        injected = []
        rollback_started = []

        def failure(point):
            if point == "paired_first_written":
                raise OSError("fixture")
            if point == "paired_before_rollback":
                rollback_started.append(True)

        def mutate_backup(store, source, destination):
            if rollback_started and destination == service.path:
                record = json.loads(store._bytes(store.pair))
                with store._open(store.project / record["previous"], "wb") as stream:
                    stream.write(changed)
                injected.append(record)
            return original_link(store, source, destination)

        service = self.service(checkpoint=failure)
        proposal = service.reply(service.reply(service.read(), "Billing api"), "Goal Fixture project")
        with patch.object(Configuration, "_link", mutate_backup):
            result = service.reply(proposal, "Apply")
        self.assertEqual(len(injected), 1)
        self.assertEqual(result["state"], "recovery_required")
        self.assertEqual(service.path.read_bytes(), previous)
        self.assertEqual((service.project / injected[0]["previous"]).read_bytes(), changed)
        self.assertTrue(service.pair.exists())
        self.assertTrue((self.local / ".playbook-config.pair").exists())
        self.assertNotIn(str(self.local), service.pair.read_text())
        self.assertNotIn("billing", service.pair.read_text())
        self.assertNotIn("Prior destinations restored", result["message"])

    def test_rollback_publication_preserves_concurrent_destination(self):
        self.save_preset()
        service = self.service()
        self.assertEqual(service.reply(service.reply(service.read(), "Load preset Focus"), "Apply")["state"], "applied")
        external = b'{"external":"publication-window"}\n'
        original_link = Configuration._link
        rollback_started = []
        injected = []

        def failure(point):
            if point == "paired_first_written":
                raise OSError("fixture")
            if point == "paired_before_rollback":
                rollback_started.append(True)

        def race_destination(store, source, destination):
            if rollback_started and destination == service.path:
                with store._open(destination, "xb") as stream:
                    stream.write(external)
                injected.append(True)
            return original_link(store, source, destination)

        service = self.service(checkpoint=failure)
        proposal = service.reply(service.reply(service.read(), "Billing api"), "Goal Fixture project")
        with patch.object(Configuration, "_link", race_destination):
            result = service.reply(proposal, "Apply")
        self.assertEqual(injected, [True])
        self.assertEqual(result["state"], "recovery_required")
        self.assertEqual(service.path.read_bytes(), external)
        self.assertTrue(service.pair.exists())
        self.assertEqual(self.service().read()["state"], "recovery_required")

    def test_first_write_failure_retains_paired_recovery(self):
        def failure(point):
            if point == "paired_first_written":
                raise OSError("injected failure")
        service = self.service(checkpoint=failure)
        proposal = service.reply(self.draft(service), "Save defaults")
        result = service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "recovery_required", result)
        self.assertIn("restored", result["message"])
        self.assertFalse((self.projects[0] / ".playbook-config.json").exists())
        self.assertFalse((self.local / "preferences.json").exists())
        self.assertEqual(self.service().read()["state"], "recovery_required")
        self.assertTrue(list(self.local.glob("*.pair")))
        self.assertTrue(list(self.projects[0].glob("*.pair")))

    def test_existing_project_restoration_is_exact_and_not_transaction_success(self):
        self.save_preset()
        service = self.service()
        self.assertEqual(service.reply(service.reply(service.read(), "Load preset Focus"), "Apply")["state"], "applied")
        project_before = service.path.read_bytes()
        personal_before = (self.local / "preferences.json").read_bytes()
        def fail(point):
            if point == "paired_first_written":
                raise OSError("fixture")
        service = self.service(checkpoint=fail)
        proposal = service.reply(service.reply(service.read(), "Billing subscription"), "Goal Known context")
        result = service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "recovery_required")
        self.assertIn("restored", result["message"])
        self.assertEqual(service.path.read_bytes(), project_before)
        self.assertEqual((self.local / "preferences.json").read_bytes(), personal_before)
        self.assertEqual(Configuration(self.projects[0], self.discover).read()["state"], "recovery_required")
        self.assertEqual(self.service(1).read()["state"], "recovery_required")

    def test_process_interruption_keeps_both_journals_and_blocks_both_project_readers(self):
        service = self.service()
        proposal = service.reply(self.draft(service), "Save defaults")
        result, _ = self.command("reply", proposal, "Apply", fault="crash")
        self.assertEqual(result.returncode, 73)
        self.assertTrue(service.path.exists())
        self.assertFalse((self.local / "preferences.json").exists())
        self.assertTrue((self.local / ".playbook-config.pair").exists())
        self.assertTrue((self.projects[0] / ".playbook-config.pair").exists())
        self.assertEqual(Configuration(self.projects[0], self.discover).read()["state"], "recovery_required")
        self.assertEqual(self.service(1).read()["state"], "recovery_required")
        self.assertEqual((self.projects[0] / ".playbook-state.yml").read_bytes(), self.runtime[0])

    def test_paired_content_completion_faults_never_report_partial_success(self):
        for point in ("paired_before_completion", "paired_completion_sealed"):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                project.mkdir()
                state = project / ".playbook-state.yml"
                state.write_bytes(self.runtime[0])
                local = Path(directory) / "personal"
                foreign = b'concurrent bytes after both writes\n'
                def fail(actual):
                    if actual == point:
                        (local / "preferences.json").write_bytes(foreign)
                service = Configuration(project, self.discover, lambda: "2026-10-01T12:00:00Z",
                                        preferences_dir=local, checkpoint=fail)
                proposal = service.reply(self.draft(service), "Save defaults")
                result = service.reply(proposal, "Apply")
                self.assertEqual(result["state"], "recovery_required", result)
                self.assertEqual((local / "preferences.json").read_bytes(), foreign)
                self.assertTrue((project / ".playbook-config.pair").exists())
                self.assertTrue((local / ".playbook-config.pair").exists())
                self.assertEqual(state.read_bytes(), self.runtime[0])
                reopened = Configuration(project, self.discover, preferences_dir=local)
                self.assertEqual(reopened.read()["state"], "recovery_required")

    def test_rollback_does_not_restore_changed_previous_evidence(self):
        self.save_preset()
        service = self.service()
        proposal = service.reply(service.read(), "Load preset Focus")
        self.assertEqual(service.reply(proposal, "Apply")["state"], "applied")
        previous = service.path.read_bytes()
        changed = b'changed previous evidence must not become project settings\n'
        def fail(point):
            if point == "paired_first_written":
                journal = json.loads((self.projects[0] / ".playbook-config.pair").read_text())
                (self.projects[0] / journal["previous"]).write_bytes(changed)
                raise OSError("fixture")
        service = self.service(checkpoint=fail)
        proposal = service.reply(service.reply(service.read(), "Billing api"), "Goal Known context")
        result = service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "recovery_required")
        self.assertNotIn("Prior destinations restored", result["message"])
        self.assertEqual(service.path.read_bytes(), previous)
        self.assertTrue(any(path.read_bytes() == changed for path in self.projects[0].glob(".playbook-config-*") if path.is_file()))
        self.assertTrue((self.projects[0] / ".playbook-config.pair").exists())

    def test_pair_directory_retarget_does_not_write_unreviewed_storage(self):
        outside = self.root / "reviewed-storage"
        outside.mkdir()
        unreviewed = self.projects[1] / "unreviewed-storage"
        unreviewed.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        def retarget(point):
            if point == "paired_first_written":
                alias.unlink()
                alias.symlink_to(unreviewed, target_is_directory=True)
        service = Configuration(self.projects[0], self.discover, lambda: "2026-10-01T12:00:00Z",
                                preferences_dir=alias, checkpoint=retarget)
        result = service.reply(service.reply(self.draft(service), "Save defaults"), "Apply")
        self.assertEqual(result["state"], "recovery_required", result)
        self.assertEqual(list(unreviewed.iterdir()), [])
        self.assertTrue((outside / ".playbook-config.pair").exists())
        self.assertTrue((self.projects[0] / ".playbook-config.pair").exists())
        self.assertEqual((self.projects[1] / ".playbook-state.yml").read_bytes(), self.runtime[1])

    def test_concurrent_rollback_edit_survives_and_requires_recovery(self):
        external = b'{"external":"must survive"}\n'
        def failure(point):
            if point == "paired_first_written":
                raise OSError("injected failure")
            if point == "paired_before_rollback":
                (self.projects[0] / ".playbook-config.json").write_bytes(external)
        service = self.service(checkpoint=failure)
        result = service.reply(service.reply(self.draft(service), "Save defaults"), "Apply")
        self.assertEqual(result["state"], "recovery_required", result)
        self.assertIn("concurrent", result["message"])
        self.assertEqual((self.projects[0] / ".playbook-config.json").read_bytes(), external)
        self.assertEqual(self.service().read()["state"], "recovery_required")

    def test_unknown_personal_and_unavailable_preset_require_review(self):
        self.save_preset()
        path = self.local / "preferences.json"
        saved = json.loads(path.read_text())
        invalid = deepcopy(saved)
        invalid["presets"]["Focus"]["surprise"] = True
        path.write_text(json.dumps(invalid))
        self.assertEqual(self.service().read()["state"], "blocked")
        self.assertEqual(json.loads(path.read_text()), invalid)
        saved["presets"]["Focus"]["models"]["implementation"]["model_id"] = "missing-model"
        path.write_text(json.dumps(saved))
        service = self.service()
        loaded = service.reply(service.read(), "Load preset Focus")
        self.assertEqual(loaded["state"], "proposal_ready", loaded)
        result = service.reply(loaded, "Apply")
        self.assertEqual(result["state"], "decision_required", result)
        self.assertIn("unavailable", result["message"])
        self.assertFalse((self.projects[0] / ".playbook-config.json").exists())

    def test_cli_pair_failure_sanitizes_unreviewed_exception_and_retains_evidence(self):
        result, proposal = self.command("read")
        self.assertEqual(result.returncode, 0)
        for label in ("Plan", "Build", "Verify", "Repair"):
            _, proposal = self.command("reply", proposal, "Edit " + label)
            _, proposal = self.command("reply", proposal, "1")
        _, proposal = self.command("reply", proposal, "Guided")
        _, proposal = self.command("reply", proposal, "Save defaults")
        result, failed = self.command("reply", proposal, "Apply", fault=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(failed["state"], "recovery_required")
        self.assertNotIn("credential-bearing", result.stdout + result.stderr)
        self.assertEqual(failed["retained_proposal"]["personal"]["resolved_destination"], str(self.local / "preferences.json"))
        self.assertTrue((self.projects[0] / ".playbook-config.pair").exists())
        self.assertTrue((self.local / ".playbook-config.pair").exists())
        self.assertEqual(self.service(1).read()["state"], "recovery_required")

    def test_presentation_edits_preserve_defaults_presets_and_billing(self):
        service = self.save_preset()
        for billing in ("subscription", "api", "mixed", "unknown"):
            proposal = service.reply(service.read(), "Billing " + billing)
            self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
        before = json.loads((self.local / "preferences.json").read_text())
        proposal = service.reply(service.read(), "Expert")
        self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
        after = json.loads((self.local / "preferences.json").read_text())
        self.assertEqual(after, {**before, "presentation": "expert"})
        self.assertIn("unknown", service.read()["billing"])

    def test_malformed_private_fields_are_not_echoed_in_public_cli_errors(self):
        self.local.mkdir()
        path = self.local / "preferences.json"
        private = "unreviewed-private-binding-store-and-credential"
        for content in (json.dumps({"schema_version": 1, "presentation": "guided", private: "secret"}),
                        '{"' + private + '":1,"' + private + '":2}', b'\xff' + private.encode()):
            with self.subTest(content=type(content).__name__):
                path.write_bytes(content if isinstance(content, bytes) else content.encode())
                before = path.read_bytes()
                result, blocked = self.command("read")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(blocked["state"], "blocked")
                self.assertNotIn(private, result.stdout + result.stderr)
                self.assertEqual(path.read_bytes(), before)

    def test_recommended_is_single_retained_proposal_and_never_a_cost_bundle(self):
        service = self.save_preset()
        proposal = service.read()
        loaded = service.reply(proposal, "Load preset Focus")
        selected = service.reply(loaded, "Recommended")
        self.assertEqual(selected["after"], proposal["before"])
        self.assertEqual(selected["skill_after"], proposal["skill_before"])
        self.assertEqual(selected["presets"].count("Recommended"), 1)
        self.assertIn("unknown", selected["recommended"]["advice"])
        self.assertFalse(service.path.exists())

    def test_pair_restores_existing_bytes_and_retains_captured_concurrent_writer(self):
        service = self.save_preset()
        proposal = service.reply(service.read(), "Load preset Focus")
        self.assertEqual(service.reply(proposal, "Apply")["state"], "applied")
        previous = (self.projects[0] / ".playbook-config.json").read_bytes()
        personal = (self.local / "preferences.json").read_bytes()
        external = b'concurrent writer must remain recoverable\n'
        def fail(point):
            if point == "paired_first_written":
                raise OSError("fixture")
        service = self.service(checkpoint=fail)
        proposal = service.reply(service.read(), "Billing api")
        proposal = service.reply(proposal, "Goal Fixture project")
        rollback = False
        def checkpoint(point):
            nonlocal rollback
            if point == "paired_before_rollback":
                rollback = True
            fail(point)
        service.checkpoint = checkpoint
        original_replace = service._replace
        def concurrent(source, target):
            if rollback and source == service.path and target.name.startswith(".playbook-config-"):
                service.path.write_bytes(external)
            original_replace(source, target)
        with patch.object(service, "_replace", concurrent):
            result = service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "recovery_required", result)
        self.assertEqual(service.path.read_bytes(), external)
        self.assertEqual((self.local / "preferences.json").read_bytes(), personal)
        self.assertTrue(any(path.read_bytes() == previous for path in self.projects[0].glob(".playbook-config-*") if path.is_file()))

    def test_unresolved_custom_preset_is_data_not_eligibility(self):
        self.save_preset()
        path = self.local / "preferences.json"
        preferences = json.loads(path.read_text())
        preferences["presets"]["Focus"]["skills"]["jobs"]["specification"] = [
            {"source_id": "custom:missing-spec", "source_sha256": "a" * 64, "contract_sha256": "b" * 64}]
        path.write_text(json.dumps(preferences))
        service = self.service(1)
        proposal = service.reply(service.read(), "Load preset Focus")
        row = next(row for row in proposal["skill_proposal"] if row["job"] == "specification")
        self.assertIn("unresolved", row["after"][0])
        self.assertEqual(row["origin"], "personal preset Focus")
        self.assertEqual(service.reply(proposal, "Apply")["state"], "blocked")
        self.assertEqual(json.loads(path.read_text()), preferences)
        self.assertFalse(service.path.exists())

    def reusable_skill_fixture(self):
        store = self.root / "custom-store"
        store.mkdir()
        source = store / "SKILL.md"
        source.write_text("fixture source, never executed\n")
        identity = "custom:fixture-spec"
        job = "specification"
        contract = JOBS[job]
        audit = {"contract_version": 1, "source_id": identity, "job": job, "owner": contract["owner"],
                 "source_sha256": fingerprint(source), "inputs": contract["inputs"], "outputs": contract["outputs"],
                 "effects": contract["effects"], "prohibited_effects": contract["prohibited_effects"],
                 "retained_authority": AUTHORITY, "invocation": identity, "form": "single", "report_only": False,
                 "verdict": "pass", "independent": True}
        evidence = store / "evidence"
        evidence.mkdir()
        proof = evidence / "fixture-audit.json"
        proof.write_text(json.dumps(audit, sort_keys=True))
        approval = {"source_id": identity, "job": job, "owner": contract["owner"], "revision": "fixture-1",
                    "evidence_sha256": fingerprint(proof),
                    "resolution_sha256": hashlib.sha256(source.resolve().as_posix().encode()).hexdigest()}
        (store / "approvals.json").write_text(json.dumps({"version": 1, "audits": {"fixture-audit": approval}}))
        (store / "bindings.json").write_text(json.dumps({"version": 1, "sources": {
            identity: {"source": str(source), "audits": {job: "fixture-audit"}}}}))
        return store, source, proof, identity

    def reusable_skill_case(self, cli, action, drift, replace=False):
        store, source, proof, identity = self.reusable_skill_fixture()
        service = Configuration(self.projects[0], self.discover, lambda: "2026-10-01T12:00:00Z",
                                preferences_dir=self.local, bindings=JobBindings(self.projects[0], custom_dir=store))
        # Keep an older unresolved preset inert, including during presentation edits.
        existing = {"schema_version": 1, "presentation": "guided", "presets": {"Older": {
            "schema_version": 1, "adopted": True, "models": service.read()["after"],
            "skills": JobBindings(self.projects[0]).defaults()}}}
        existing["presets"]["Older"]["skills"]["jobs"]["specification"] = [
            {"source_id": "custom:missing-spec", "source_sha256": "a" * 64, "contract_sha256": "b" * 64}]
        if replace:
            previous = deepcopy(existing["presets"]["Older"])
            if action == "Save defaults":
                existing["defaults"] = previous
            else:
                existing["presets"]["Qualified"] = previous
        self.local.mkdir(exist_ok=True)
        personal_path = self.local / "preferences.json"
        personal_path.write_text(json.dumps(existing))
        # An adopted project and extra historical record must survive local saves.
        config = {"schema_version": 1, "adopted": True, "models": service.read()["after"]}
        service.path.write_text(json.dumps(config))
        history = self.projects[0] / "history.json"
        history.write_text('{"approved_binding":"retained"}\n')
        protected = {path: path.read_bytes() for project in self.projects for path in project.rglob("*") if path.is_file()}

        def call(proposal=None, reply=None):
            if not cli:
                return service.read() if proposal is None else service.reply(proposal, reply)
            result, value = self.command("read" if proposal is None else "reply", proposal, reply, custom=store)
            self.assertEqual(result.returncode, 2 if value["state"] == "blocked" else 0, result.stderr)
            self.assertEqual(result.stderr, "")
            return value

        proposal = call()
        editor = call(proposal, "Edit skills specification")
        option = next(index + 1 for index, value in enumerate(editor["skill_options"])
                      if value["binding"]["source_id"] == identity)
        proposal = call(editor, "Choose " + str(option))
        proposal = call(proposal, action)
        personal_before = personal_path.read_bytes()
        if drift == "source":
            source.write_text("changed synthetic source; never executed\n")
        elif drift == "proof":
            audit = json.loads(proof.read_text())
            audit["independent"] = False
            proof.write_text(json.dumps(audit))
        elif drift == "approval":
            approvals_path = store / "approvals.json"
            approvals = json.loads(approvals_path.read_text())
            approvals["audits"]["fixture-audit"]["revision"] = "fixture-2"
            approvals_path.write_text(json.dumps(approvals))
        store_before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
        result = call(proposal, "Apply preference")
        if drift:
            self.assertEqual(result["state"], "blocked", result["message"])
            self.assertNotIn("saved and validated", result["message"])
            self.assertEqual(result["retained_proposal"]["personal"]["after"], proposal["personal"]["after"])
            self.assertEqual(result["retained_proposal"]["skill_after"], proposal["skill_after"])
            self.assertEqual(personal_path.read_bytes(), personal_before)
            # A refreshed editor retains the local draft and requires an explicit choice.
            recovered = call(result, "Edit skills specification")
            self.assertEqual(recovered["personal"]["after"], proposal["personal"]["after"])
            presentation = call(call(), "Expert")
            self.assertEqual(call(presentation, "Apply preference")["state"], "proposal_ready")
        else:
            self.assertEqual(result["state"], "proposal_ready", result)
            saved = json.loads(personal_path.read_text())
            candidate = saved["defaults"] if action == "Save defaults" else saved["presets"]["Qualified"]
            self.assertEqual(candidate["skills"], proposal["skill_after"])
            self.assertEqual(saved["presets"]["Older"], existing["presets"]["Older"])
        self.assertEqual(json.loads(personal_path.read_text())["presets"]["Older"], existing["presets"]["Older"])
        for path, content in protected.items():
            self.assertEqual(path.read_bytes(), content)
        for path, content in store_before.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertFalse(result.get("launched", False))

    def check_reusable_skill_freshness(self, cli):
        for action in ("Save defaults", "Save preset Qualified"):
            for replace in (False, True):
                for drift in ("source", "proof", "approval", None):
                    with self.subTest(action=action, replace=replace, drift=drift):
                        try:
                            self.reusable_skill_case(cli, action, drift, replace)
                        finally:
                            shutil.rmtree(self.root / "custom-store")
                            shutil.rmtree(self.local)

    def test_library_reusable_skill_freshness(self):
        self.check_reusable_skill_freshness(False)

    def test_cli_reusable_skill_freshness(self):
        self.check_reusable_skill_freshness(True)

    def test_older_reusable_bindings_stay_inert_for_unrelated_edits(self):
        store, source, _, identity = self.reusable_skill_fixture()
        service = Configuration(self.projects[0], self.discover, lambda: "2026-10-01T12:00:00Z",
                                preferences_dir=self.local, bindings=JobBindings(self.projects[0], custom_dir=store))
        proposal = self.draft(service)
        editor = service.reply(proposal, "Edit skills specification")
        option = next(index + 1 for index, value in enumerate(editor["skill_options"])
                      if value["binding"]["source_id"] == identity)
        proposal = service.reply(editor, "Choose " + str(option))
        proposal = service.reply(proposal, "Save defaults")
        proposal = service.reply(proposal, "Save preset Qualified")
        self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
        source.write_text("changed synthetic source; never executed\n")
        personal_path = self.local / "preferences.json"
        previous = json.loads(personal_path.read_text())
        for edit in ("Expert", "Billing api", "Save defaults", "Save preset Qualified"):
            proposal = service.reply(service.read(), "Load defaults") if edit.startswith("Save") else service.read()
            proposal = service.reply(proposal, edit)
            self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
            saved = json.loads(personal_path.read_text())
            self.assertEqual(saved["defaults"]["skills"], previous["defaults"]["skills"])
            self.assertEqual(saved["presets"]["Qualified"]["skills"], previous["presets"]["Qualified"]["skills"])
        self.assertFalse(service.path.exists())
        for project, runtime in zip(self.projects, self.runtime):
            self.assertEqual((project / ".playbook-state.yml").read_bytes(), runtime)

    def test_custom_preset_keeps_logical_identity_and_requires_same_local_qualification(self):
        store, source, _, identity = self.reusable_skill_fixture()
        originals = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
        bindings = JobBindings(self.projects[0], custom_dir=store)
        service = Configuration(self.projects[0], self.discover, lambda: "2026-10-01T12:00:00Z",
                                preferences_dir=self.local, bindings=bindings)
        proposal = self.draft(service)
        editor = service.reply(proposal, "Edit skills specification")
        option = next(index + 1 for index, option in enumerate(editor["skill_options"]) if option["binding"]["source_id"] == identity)
        proposal = service.reply(editor, "Choose " + str(option))
        proposal = service.reply(proposal, "Save preset Qualified")
        self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
        missing = self.service(1)
        draft = missing.reply(missing.read(), "Load preset Qualified")
        self.assertEqual(missing.reply(draft, "Apply")["state"], "blocked")
        qualified = Configuration(self.projects[1], self.discover, lambda: "2026-10-01T12:00:00Z",
                                  preferences_dir=self.local, bindings=JobBindings(self.projects[1], custom_dir=store))
        draft = qualified.reply(qualified.read(), "Load preset Qualified")
        self.assertEqual(qualified.reply(draft, "Apply")["state"], "applied")
        saved = qualified.path.read_text()
        self.assertIn(identity, saved)
        self.assertNotIn(str(store), saved)
        self.assertNotIn(str(self.local), saved)
        self.assertNotIn("billing", saved)
        for path, original in originals.items():
            self.assertEqual(path.read_bytes(), original)
        source.write_text("changed source invalidates the old preset qualification\n")
        draft = qualified.reply(qualified.read(), "Load preset Qualified")
        self.assertEqual(qualified.reply(draft, "Apply")["state"], "blocked")
        self.assertEqual(qualified.path.read_text(), saved)

    def bootstrap(self, target, *extra):
        adapter = ("import json,sys; request=json.load(sys.stdin); "
                   "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-1',"
                   "'routes':[{'model_id':'fixture-model','runner':'codex','reasoning':'high',"
                   "'roles':['planning','implementation','verification','escalated_repair']}]},sys.stdout)")
        command = [sys.executable, str(Path(__file__).with_name("bootstrap-project.py")), str(target),
                   "--playbook-path", str(Path(__file__).resolve().parents[2]), "--project-name", "Fixture",
                   "--ui", "no", "--ci", "copy", "--preferences-dir", str(self.local),
                   "--discovery-command", json.dumps([sys.executable, "-c", adapter]),
                   "--now", "2026-10-01T12:00:00Z", *extra]
        return subprocess.run(command, text=True, capture_output=True)

    def test_bootstrap_preview_seed_approval_and_existing_project_isolation(self):
        service = self.save_preset()
        proposal = service.reply(service.reply(service.read(), "Load preset Focus"), "Save defaults")
        self.assertEqual(service.reply(proposal, "Apply preference")["state"], "proposal_ready")
        personal = (self.local / "preferences.json").read_bytes()
        target = self.root / "new-project"
        plan = self.bootstrap(target)
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn("create .playbook-config.json", plan.stdout)
        self.assertIn("personal defaults", plan.stdout)
        preview = json.loads(plan.stdout[plan.stdout.index('{\n'):])
        self.assertFalse(target.exists())
        denied = self.bootstrap(target, "--apply")
        self.assertEqual(denied.returncode, 2)
        self.assertFalse(target.exists())
        applied = self.bootstrap(target, "--apply", "--seed-revision", preview["seed_revision"])
        self.assertEqual(applied.returncode, 0, applied.stderr)
        saved = json.loads((target / ".playbook-config.json").read_text())
        self.assertEqual(saved, preview["after"])
        self.assertNotIn("billing", json.dumps(saved))
        self.assertNotIn(str(self.local), json.dumps(saved))
        self.assertEqual((self.local / "preferences.json").read_bytes(), personal)
        self.assertEqual(self.bootstrap(target, "--apply", "--seed-revision", preview["seed_revision"]).returncode, 2)
        for project, runtime in zip(self.projects, self.runtime):
            self.assertFalse((project / ".playbook-config.json").exists())
            self.assertEqual((project / ".playbook-state.yml").read_bytes(), runtime)

    def test_bootstrap_changed_defaults_rejects_old_approval_before_any_write(self):
        self.save_preset()
        target = self.root / "new-project"
        plan = self.bootstrap(target, "--preset", "Focus")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        preview = json.loads(plan.stdout[plan.stdout.index('{\n'):])
        path = self.local / "preferences.json"
        preferences = json.loads(path.read_text())
        preferences["billing"] = "mixed"
        path.write_text(json.dumps(preferences))
        result = self.bootstrap(target, "--preset", "Focus", "--apply", "--seed-revision", preview["seed_revision"])
        self.assertEqual(result.returncode, 2)
        self.assertFalse(target.exists())

    def test_bootstrap_unresolved_skill_and_unknown_preset_data_block_before_writes(self):
        self.save_preset()
        target = self.root / "new-project"
        path = self.local / "preferences.json"
        preferences = json.loads(path.read_text())
        preferences["presets"]["Focus"]["skills"]["jobs"]["specification"] = [
            {"source_id": "custom:missing-spec", "source_sha256": "a" * 64, "contract_sha256": "b" * 64}]
        path.write_text(json.dumps(preferences))
        before = path.read_bytes()
        blocked = self.bootstrap(target, "--preset", "Focus")
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("local", blocked.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(path.read_bytes(), before)
        preferences["presets"]["Focus"]["private_future_field"] = "unreviewed content"
        path.write_text(json.dumps(preferences))
        before = path.read_bytes()
        blocked = self.bootstrap(target, "--preset", "Focus", "--apply", "--seed-revision", "unapproved")
        self.assertEqual(blocked.returncode, 2)
        self.assertNotIn("unreviewed content", blocked.stdout + blocked.stderr)
        self.assertFalse(target.exists())
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

"""Synthetic retained audits exercise Configure and the stage seam, not live proof."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from playbook_config import Configuration, ConfigError
from skill_bindings import AUTHORITY, JOBS, JobBindings, fingerprint
import test_playbook_config
import test_skill_bindings


class CustomBindingTests(test_playbook_config.ConfigurationTests):
    pick = test_skill_bindings.BindingTests.pick

    def setUp(self):
        super().setUp()
        machines = tempfile.TemporaryDirectory()
        self.addCleanup(machines.cleanup)
        self.machines = Path(machines.name)
        self.local = self.machines / "machine-one-local"
        self.local.mkdir()
        self.source = self.local / "skills" / "SKILL.md"
        self.source.parent.mkdir()
        self.source.write_text("synthetic custom source; never executed\n")
        self.identity = "custom:team-spec"
        self.prepare_audit("specification")
        self.bindings = JobBindings(self.project, custom_dir=self.local)
        self.service = Configuration(self.project, self.discover, lambda: "2026-10-01T12:00:00Z",
                                     bindings=self.bindings)

    def prepare_audit(self, job, identity=None, source=None, local=None):
        identity = identity or self.identity
        source = source or self.source
        local = local or self.local
        contract = JOBS[job]
        invocation = identity + (" --report-only" if job in {"code_review", "application_qa"} else "")
        evidence = {"contract_version": 1, "source_id": identity, "job": job,
                    "owner": contract["owner"], "source_sha256": fingerprint(source),
                    "inputs": contract["inputs"], "outputs": contract["outputs"],
                    "effects": contract["effects"], "prohibited_effects": contract["prohibited_effects"],
                    "retained_authority": AUTHORITY, "invocation": invocation,
                    "form": "project route" if job == "application_qa" else "single",
                    "report_only": job in {"code_review", "application_qa"},
                    "verdict": "pass", "independent": True}
        audit = "fixture-audit"
        (local / "evidence").mkdir(exist_ok=True)
        proof = local / "evidence" / (audit + ".json")
        proof.write_text(json.dumps(evidence, sort_keys=True))
        resolution = source.resolve().as_posix()
        approval = {"source_id": identity, "job": job, "owner": contract["owner"],
                    "revision": "fixture-1", "evidence_sha256": fingerprint(proof),
                    "resolution_sha256": hashlib.sha256(resolution.encode()).hexdigest()}
        (local / "approvals.json").write_text(json.dumps({"version": 1, "audits": {audit: approval}}))
        locator = identity.split(":", 1)[1] if identity.startswith("project:") else str(source)
        (local / "bindings.json").write_text(json.dumps({"version": 1, "sources": {
            identity: {"source": locator, "audits": {job: audit}}}}))
        return proof, evidence

    def stage_entry(self, job="specification", approved=None, local=None):
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "--custom-bindings-dir", str(local or self.local), "job-route"]
        request = {"job": job, "owner": JOBS[job]["owner"]}
        if approved is not None:
            request["approved_binding"] = approved
        completed = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        return completed.returncode, json.loads(completed.stdout)

    def save_custom(self, job="specification", identity=None):
        preview = self.pick(self.preview(), job, [identity or self.identity])
        self.assertEqual(preview["state"], "proposal_ready")
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "applied")
        return preview

    def test_two_machines_same_configuration_distinct_local_resolution(self):
        preview = self.save_custom()
        config = (self.project / ".playbook-config.json").read_bytes()
        second = self.machines / "machine-two"
        second.mkdir()
        (second / ".playbook-config.json").write_bytes(config)
        local = self.machines / "machine-two-local"
        local.mkdir()
        source = local / "different-install" / "SKILL.md"
        source.parent.mkdir()
        source.write_bytes(self.source.read_bytes())
        self.prepare_audit("specification", source=source, local=local)
        other = Configuration(second, self.discover, bindings=JobBindings(second, custom_dir=local))
        self.assertEqual(other.dispatch_job("specification", "03")["routes"][0]["binding"],
                         preview["skill_after"]["jobs"]["specification"][0])
        self.assertEqual((second / ".playbook-config.json").read_bytes(), config)
        self.assertNotIn(str(self.local).encode(), config)
        self.assertNotIn(str(local).encode(), config)
        missing = JobBindings(second, custom_dir=local / "missing")
        with self.assertRaisesRegex(ConfigError, "local binding|unresolved"):
            missing.dispatch(preview["skill_after"], "specification", "03", None)
        self.assertEqual((second / ".playbook-config.json").read_bytes(), config)
        self.assertEqual(self.stage_entry()[0], 0)
        self.assertEqual(self.stage_entry(local=local / "missing")[0], 2)
        self.assertEqual(self.bindings.invocation_source(preview["skill_after"], "specification", "03", self.identity),
                         self.source.resolve())

    def test_custom_labels_round_trip_and_preserved_execution(self):
        state = self.project / ".playbook-state.yml"
        before = state.read_bytes()
        preview = self.save_custom()
        for surface in ("skill_proposal", "skill_changes"):
            row = next(row for row in preview[surface] if row["job"] == "specification")
            self.assertEqual(row["after"], ["(Custom) team-spec"])
        editor = self.service.reply(self.service.read(), "Edit skills specification")
        self.assertIn("(Custom) team-spec", [choice["label"] for choice in editor["skill_options"]])
        self.assertEqual(self.service.read()["skill_before"], preview["skill_after"])
        self.assertEqual(state.read_bytes(), before)
        approved = deepcopy(preview["skill_after"])
        replacement = self.pick(self.preview(), "specification", ["playbook:specification-manual"])
        self.assertEqual(self.service.reply(replacement, "Apply")["state"], "applied")
        code, result = self.stage_entry(approved=approved)
        self.assertEqual(code, 0)
        self.assertEqual(result["origin"], "approved execution")
        self.assertIn("permission boundaries", result["retained_authority"])
        self.assertNotIn(str(self.local), json.dumps(result))
        self.assertEqual(state.read_bytes(), before)

    def test_no_self_declared_or_forged_evidence(self):
        preview = self.save_custom()
        proof = self.local / "evidence/fixture-audit.json"
        original = proof.read_bytes()
        approvals = self.local / "approvals.json"
        original_approvals = approvals.read_bytes()
        for mutation in ("absent approval", "forged evidence", "missing evidence", "self declaration"):
            with self.subTest(mutation=mutation):
                proof.write_bytes(original)
                approvals.write_bytes(original_approvals)
                if mutation == "absent approval":
                    approvals.unlink()
                elif mutation == "missing evidence":
                    proof.unlink()
                elif mutation == "forged evidence":
                    proof.write_text(json.dumps({"independent": True, "verdict": "pass"}))
                else:
                    self.source.write_text("name: specification\nindependent: true\nverdict: pass\n")
                code, result = self.stage_entry(approved=preview["skill_after"])
                self.assertEqual(code, 2)
                self.assertIn("manual: stage 03", result["message"])
                self.assertNotIn(str(self.local), json.dumps(result))
                discovery = self.service.read()
                self.assertNotIn(self.identity, [option["binding"]["source_id"]
                                                for option in discovery["skill_alternatives"]["specification"]])
                self.assertTrue(discovery["skill_rejections"])

    def test_exact_contract_and_local_changes_invalidate_discovery_and_stage(self):
        preview = self.save_custom()
        saved = preview["skill_after"]
        proof = self.local / "evidence/fixture-audit.json"
        original = proof.read_bytes()
        for field, value in (("inputs", []), ("outputs", []), ("effects", ["commits"]),
                             ("owner", "08"), ("invocation", "custom:other"),
                             ("retained_authority", []), ("form", "manual"),
                             ("prohibited_effects", []), ("independent", False)):
            with self.subTest(field=field):
                evidence = json.loads(original)
                evidence[field] = value
                proof.write_text(json.dumps(evidence))
                approvals = json.loads((self.local / "approvals.json").read_text())
                approvals["audits"]["fixture-audit"]["evidence_sha256"] = fingerprint(proof)
                (self.local / "approvals.json").write_text(json.dumps(approvals))
                self.assertEqual(self.stage_entry(approved=saved)[0], 2)
                self.assertFalse(any(option["binding"]["source_id"] == self.identity
                                     for option in self.service.read()["skill_alternatives"]["specification"]))
        self.prepare_audit("specification")
        duplicate = self.local / "copy.md"
        duplicate.write_bytes(self.source.read_bytes())
        bindings = json.loads((self.local / "bindings.json").read_text())
        bindings["sources"][self.identity]["source"] = str(duplicate)
        (self.local / "bindings.json").write_text(json.dumps(bindings))
        self.assertEqual(self.stage_entry(approved=saved)[0], 2)
        self.prepare_audit("specification")
        self.source.write_text("changed source\n")
        self.assertEqual(self.stage_entry(approved=saved)[0], 2)
        with self.assertRaises(ConfigError):
            self.bindings.invocation_source(saved, "specification", "03", self.identity)
        row = next(row for row in self.service.read()["skill_proposal"] if row["job"] == "specification")
        self.assertIn("blocked", row["after"][0])

    def test_project_relative_source_and_qa_owned_selection(self):
        source = self.project / "team-skills/spec/SKILL.md"
        source.parent.mkdir(parents=True)
        source.write_bytes(self.source.read_bytes())
        identity = "project:team-skills/spec/SKILL.md"
        self.prepare_audit("specification", identity=identity, source=source)
        self.save_custom(identity=identity)
        (self.local / "bindings.json").unlink()
        self.assertEqual(self.stage_entry()[0], 0)
        saved = self.service.read()["skill_before"]
        self.assertEqual(self.bindings.invocation_source(saved, "specification", "03", identity), source)
        reset = self.pick(self.preview(), "specification", ["playbook:specification-manual"])
        self.assertEqual(self.service.reply(reset, "Apply")["state"], "applied")
        route, source, _, _ = test_skill_bindings.qualified_qa(self.project)
        self.prepare_audit("application_qa", identity="custom:team-qa", source=source)
        self.save_custom("application_qa", "custom:team-qa")
        self.assertEqual(self.stage_entry("application_qa")[0], 0)
        (self.project / ".playbook-qa-eligibility.json").unlink()
        self.assertEqual(self.stage_entry("application_qa")[0], 2)
        self.assertTrue(source.exists())

    def test_proof_drift_blocks_pending_apply_without_writes(self):
        preview = self.pick(self.preview(), "specification", [self.identity])
        proof = self.local / "evidence/fixture-audit.json"
        proof.write_text(proof.read_text() + "\n")
        result = self.service.reply(preview, "Apply")
        self.assertEqual(result["state"], "blocked")
        self.assertFalse((self.project / ".playbook-config.json").exists())
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_custom_copies_and_colliding_installs_cannot_claim_upstream_attribution(self):
        proof, evidence = self.prepare_audit("code_review")
        entry = {
            "upstream": "mattpocock/skills", "tested_version": "fixture",
            "tested_source_sha256": fingerprint(self.source), "embedded_compatible": True,
            "compatible_mode": "report-only", "embedded_invocation": "/code-review --report-only",
            "adapter": "stage 08", "compatibility_evidence": "synthetic bounded audit",
            "last_verified": "2026-10-01", "required_outputs": JOBS["code_review"]["outputs"],
            "permitted_side_effects": JOBS["code_review"]["effects"],
            "prohibited_side_effects": ["product or source edits", "commits", "configuration changes", "self-upgrade"],
            "fallback": "manual: stage 08",
        }
        manifest = self.local / "compatibility.json"
        manifest.write_text(json.dumps({"schema_version": 1, "integrations": {"code-review": entry}}))
        evidence["embedded_source_id"] = "mattpocock-skills:code-review"
        proof.write_text(json.dumps(evidence))
        approvals = json.loads((self.local / "approvals.json").read_text())
        approvals["audits"]["fixture-audit"]["evidence_sha256"] = fingerprint(proof)
        (self.local / "approvals.json").write_text(json.dumps(approvals))
        self.bindings.manifest = manifest
        installed = self.local / "installed.md"
        installed.write_bytes(self.source.read_bytes())
        for paths in ([installed], [installed, self.source], [self.source]):
            with self.subTest(paths=len(paths)):
                self.bindings.installed = {"mattpocock-skills:code-review": paths}
                self.bindings.live_inventory = False
                choices = self.service.read()["skill_alternatives"]["code_review"]
                self.assertFalse(any(option["binding"]["source_id"] == self.identity for option in choices))
                self.assertEqual(any(option["binding"]["source_id"] == "mattpocock-skills:code-review"
                                     for option in choices), len(paths) == 1)

    def test_requalification_revision_and_wrong_owner_do_not_reuse_eligibility(self):
        preview = self.save_custom()
        approvals = json.loads((self.local / "approvals.json").read_text())
        approvals["audits"]["fixture-audit"]["revision"] = "fixture-2"
        (self.local / "approvals.json").write_text(json.dumps(approvals))
        self.assertEqual(self.stage_entry(approved=preview["skill_after"])[0], 2)
        with self.assertRaisesRegex(ConfigError, "owning stage"):
            self.service.dispatch_job("specification", "07")
        self.assertFalse(any(option["binding"] == preview["skill_after"]["jobs"]["specification"][0]
                             for option in self.service.read()["skill_alternatives"]["specification"]))

    def test_untrusted_project_audits_and_private_locators_are_not_shareable(self):
        with self.assertRaisesRegex(ConfigError, "outside the shareable project"):
            JobBindings(self.project, custom_dir=self.project / "local-store")
        code, result = self.stage_entry(local=self.project / "local-store")
        self.assertEqual(code, 2)
        self.assertIn("external --custom-bindings-dir", result["message"])
        self.assertFalse((self.project / "local-store").exists())
        alias = self.local / "project-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertEqual(self.stage_entry(local=alias)[0], 2)
        self.assertEqual(self.state.read_bytes(), self.runtime)
        inventory = json.loads((self.local / "bindings.json").read_text())
        inventory["sources"] = {"custom:" + str(self.source): inventory["sources"][self.identity]}
        (self.local / "bindings.json").write_text(json.dumps(inventory))
        proposal = self.service.read()
        self.assertNotIn(str(self.source), json.dumps(proposal))
        self.assertTrue(proposal["skill_rejections"])

    def test_store_retarget_and_audit_links_into_project_block_without_writes(self):
        preview = self.pick(self.preview(), "specification", [self.identity])
        proof = self.local / "evidence/fixture-audit.json"
        project_proof = self.project / "not-trusted-proof.json"
        project_proof.write_bytes(proof.read_bytes())
        proof.unlink()
        proof.symlink_to(project_proof)
        self.assertEqual(self.service.reply(preview, "Apply")["state"], "blocked")
        self.assertFalse((self.project / ".playbook-config.json").exists())
        alias = self.local / "local-alias"
        alias.symlink_to(self.local, target_is_directory=True)
        bindings = JobBindings(self.project, custom_dir=alias)
        alias.unlink()
        alias.symlink_to(self.project, target_is_directory=True)
        self.assertFalse(any(option["binding"]["source_id"] == self.identity
                             for option in bindings.options("specification")))

    def test_all_five_jobs_use_exact_s3_contract_without_launch(self):
        for job in JOBS:
            with self.subTest(job=job):
                source = self.source
                if job == "application_qa":
                    _, source, _, _ = test_skill_bindings.qualified_qa(self.project)
                self.prepare_audit(job, source=source)
                preview = self.save_custom(job)
                code, result = self.stage_entry(job)
                self.assertEqual(code, 0)
                self.assertFalse(result["launched"])
                self.assertEqual(result["contract"], JOBS[job])
                self.assertEqual(result["retained_authority"], AUTHORITY)
                self.assertEqual(result["routes"][0]["binding"], preview["skill_after"]["jobs"][job][0])
                consumed = []

                def stage_reader(route):
                    resolved = self.bindings.invocation_source(preview["skill_after"], job,
                                                              JOBS[job]["owner"], route["source_id"])
                    consumed.append((resolved, resolved.read_bytes()))

                boundary = self.service.dispatch_job(job, JOBS[job]["owner"], invoke=stage_reader)
                self.assertEqual(consumed, [(source.resolve(), source.read_bytes())])
                self.assertNotIn(str(self.local), json.dumps(boundary))
                reset = self.pick(self.preview(), job, [f"playbook:{job}-manual"])
                self.assertEqual(self.service.reply(reset, "Apply")["state"], "applied")
                guidance = (Path(__file__).parent.parent / "10-process" / JOBS[job]["stage"]).read_text()
                self.assertIn(f'catalog.invocation_source(saved, "{job}", "{JOBS[job]["owner"]}"', guidance)

    def test_public_stage_callback_rechecks_source_before_skill_reader(self):
        preview = self.save_custom()
        consumed = []

        def stage_reader(route):
            self.source.write_text("changed between descriptor and host reader\n")
            resolved = self.bindings.invocation_source(preview["skill_after"], "specification", "03", route["source_id"])
            consumed.append(resolved.read_bytes())

        with self.assertRaises(ConfigError):
            self.service.dispatch_job("specification", "03", invoke=stage_reader)
        self.assertEqual(consumed, [])
        self.assertEqual(self.state.read_bytes(), self.runtime)

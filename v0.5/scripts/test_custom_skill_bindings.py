"""Synthetic retained audits exercise Configure and the stage seam, not live proof."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

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

    def privacy_cli(self, action="read", request=None, deny=False, extra=()):
        adapter = ("import json,sys; request=json.load(sys.stdin); "
                   "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-cli',"
                   "'routes':[{'model_id':'available-build','runner':'codex','reasoning':'medium',"
                   "'roles':['implementation']}]},sys.stdout)")
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "--custom-bindings-dir", str(self.local),
                   "--discovery-command", json.dumps([sys.executable, "-c", adapter]), *extra, action]
        if deny:
            command = ["setpriv", "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all"] + command
        result = subprocess.run(command, input=json.dumps(request or {}), text=True, capture_output=True,
                                env=dict(os.environ, HOME=str(self.machines)))
        for private in (str(self.project), str(self.machines), "PRIVATE_FIXTURE_MARKER", "SYNTHETIC_CREDENTIAL",
                        "Traceback", "Symlink loop from"):
            self.assertNotIn(private, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        public = json.loads(result.stdout)
        self.assertFalse(public.get("launched", False))
        return result.returncode, public

    def stored_bytes(self):
        return {path: path.read_bytes() for root in (self.project, self.local)
                for path in root.rglob("*") if path.is_file()}

    def external_cycle(self, pair=False):
        target = self.local / "PRIVATE_FIXTURE_MARKER_SYNTHETIC_CREDENTIAL"
        other = self.local / "cycle-peer"
        target.symlink_to(other if pair else target)
        if pair:
            other.symlink_to(target)
        self.addCleanup(target.unlink, missing_ok=True)
        self.addCleanup(other.unlink, missing_ok=True)
        with self.assertRaises((RuntimeError, OSError)):
            target.resolve()
        return target

    def assert_private_denial(self, value):
        text = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        for private in (str(self.project), str(self.machines), "PRIVATE_FIXTURE_MARKER", "SYNTHETIC_CREDENTIAL"):
            self.assertNotIn(private, text)

    def test_cyclic_qa_artifacts_block_public_and_stage_seams_without_rewrites(self):
        route, source, record, proof = test_skill_bindings.qualified_qa(self.project)
        for identity in ("custom:team-qa", "project:" + source.relative_to(self.project).as_posix(),
                         "project:" + route):
            with self.subTest(identity=identity):
                if identity != "project:" + route:
                    self.prepare_audit("application_qa", identity=identity, source=source)
                preview = self.save_custom("application_qa", identity)
                saved = preview["skill_after"]
                for artifact, pair in ((source, False), (source, True), (source.parent, False),
                                       (self.project / proof["evidence"], False), (record, False)):
                    with self.subTest(artifact=artifact.name, pair=pair):
                        before = self.stored_bytes()
                        target = self.external_cycle(pair)
                        backup = artifact.with_name(artifact.name + ".retained")
                        artifact.rename(backup)
                        artifact.symlink_to(target)
                        try:
                            code, public = self.privacy_cli()
                            self.assertEqual(code, 0)
                            self.assertEqual(public["skill_before"], saved)
                            self.assertEqual(public["skill_after"], saved)
                            self.assertIn("stage 09", json.dumps(public["skill_rejections"]))
                            self.assertIn("Restore", json.dumps(public["skill_rejections"]))
                            self.assertFalse(any(row["binding"] == saved["jobs"]["application_qa"][0]
                                                 for row in public["skill_alternatives"]["application_qa"]))
                            for approved in (None, saved):
                                request = {"job": "application_qa", "owner": "09"}
                                if approved is not None:
                                    request["approved_binding"] = approved
                                code, public = self.privacy_cli("job-route", request)
                                self.assertEqual((code, public["state"]), (2, "blocked"))
                                self.assertIn("explicitly", public["message"])
                                readers = []
                                with self.assertRaises(ConfigError) as denied:
                                    self.service.dispatch_job("application_qa", "09", readers.append,
                                                              approved_binding=approved)
                                self.assert_private_denial(denied.exception)
                                self.assertEqual(readers, [])
                            if identity != "project:" + route:
                                with self.assertRaises(ConfigError) as denied:
                                    self.bindings.invocation_source(saved, "application_qa", "09", identity)
                                self.assert_private_denial(denied.exception)
                            code, public = self.privacy_cli("reply", {"proposal": preview, "reply": "Apply"})
                            self.assertEqual((code, public["state"]), (2, "blocked"))
                            self.assertEqual(self.privacy_cli("resolve", {"role": "verification"})[0], 0)
                            self.assertEqual(artifact.readlink(), target)
                        finally:
                            artifact.unlink()
                            backup.rename(artifact)
                            target.unlink()
                            (self.local / "cycle-peer").unlink(missing_ok=True)
                        self.assertEqual(self.stored_bytes(), before)

    def test_cyclic_installed_source_after_catalog_construction_is_portable(self):
        preview = self.save_custom()
        approved = deepcopy(preview["skill_after"])
        approved["jobs"]["code_review"] = [{"source_id": "mattpocock-skills:code-review",
                                             "source_sha256": "0" * 64, "contract_sha256": "0" * 64}]
        before = self.stored_bytes()
        target = self.external_cycle()
        installed = self.project / ".agents/skills/code-review/SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.symlink_to(target)
        try:
            public = self.service.read()
            self.assert_private_denial(public)
            if public["state"] != "blocked":
                # Python 3.11 glob may omit the cyclic leaf; it must remain ineligible.
                self.assertFalse(any(row["binding"] == approved["jobs"]["code_review"][0]
                                     for row in public["skill_alternatives"]["code_review"]))
            readers = []
            with self.assertRaises(ConfigError) as denied:
                self.service.dispatch_job("code_review", "08", readers.append, approved_binding=approved)
            self.assert_private_denial(denied.exception)
            self.assertEqual(readers, [])
            code, public = self.privacy_cli()
            self.assertIn(code, (0, 2))
            code, public = self.privacy_cli("job-route", {"job": "code_review", "owner": "08",
                                                         "approved_binding": approved})
            self.assertEqual((code, public["state"]), (2, "blocked"))
        finally:
            installed.unlink()
        self.assertEqual(self.stored_bytes(), before)

    def test_cyclic_custom_source_at_final_invocation_resolution_blocks_reader(self):
        preview = self.save_custom()
        before = self.stored_bytes()
        target = self.external_cycle()
        original = self.source.read_bytes()
        candidate = self.bindings._custom_candidate
        checks = []
        readers = []

        def drift_after_qualification(*args):
            result = candidate(*args)
            checks.append(result)
            if len(checks) == 2:
                self.source.unlink()
                self.source.symlink_to(target)
            return result

        try:
            with patch.object(self.bindings, "_custom_candidate", side_effect=drift_after_qualification):
                with self.assertRaises(ConfigError) as denied:
                    source = self.bindings.invocation_source(preview["skill_after"], "specification", "03", self.identity)
                    readers.append(source.read_bytes())
            self.assert_private_denial(denied.exception)
            self.assertEqual(len(checks), 2)
            self.assertEqual(readers, [])
            self.assertEqual(self.source.readlink(), target)
        finally:
            self.source.unlink()
            self.source.write_bytes(original)
        self.assertEqual(self.stored_bytes(), before)

    def test_cyclic_personal_directory_is_portable_before_and_after_construction(self):
        preview = self.save_custom()
        before = self.stored_bytes()
        target = self.external_cycle()
        personal = self.local / "personal"
        service = Configuration(self.project, self.discover, preferences_dir=personal)
        personal.symlink_to(target)
        with self.assertRaises(ConfigError) as denied:
            Configuration(self.project, self.discover, preferences_dir=personal)
        self.assert_private_denial(denied.exception)
        public = service.read()
        self.assertEqual(public["state"], "blocked")
        self.assert_private_denial(public)
        self.assertIn("Restore", public["message"])
        for action, request in self.public_actions(preview):
            code, public = self.privacy_cli(action, request, extra=("--preferences-dir", str(personal)))
            self.assertEqual((code, public["state"]), (2, "blocked"))
        self.assertEqual(personal.readlink(), target)
        self.assertEqual(self.stored_bytes(), before)

    def test_unrelated_runtime_error_is_not_a_filesystem_denial(self):
        with patch.object(self.bindings, "_candidate", side_effect=RuntimeError("programmer defect")):
            with self.assertRaisesRegex(RuntimeError, "programmer defect"):
                self.service.read()

    def public_actions(self, preview):
        return (("read", {}), ("resolve", {"role": "implementation"}),
                ("job-route", {"job": "specification", "owner": "03"}),
                ("reply", {"proposal": preview, "reply": "Apply"}))

    def save_public_custom(self):
        code, proposal = self.privacy_cli()
        self.assertEqual(code, 0)
        for reply in ("Edit Build", "1", "Edit skills specification"):
            code, proposal = self.privacy_cli("reply", {"proposal": proposal, "reply": reply})
            self.assertEqual(code, 0)
        number = next(index + 1 for index, row in enumerate(proposal["skill_options"])
                      if row["binding"]["source_id"] == self.identity)
        code, preview = self.privacy_cli("reply", {"proposal": proposal, "reply": "Choose " + str(number)})
        self.assertEqual(code, 0)
        self.assertEqual(self.privacy_cli("reply", {"proposal": preview, "reply": "Apply"})[1]["state"], "applied")
        code, retained = self.privacy_cli()
        self.assertEqual(code, 0)
        self.assertEqual(self.privacy_cli("reply", {"proposal": retained, "reply": "Apply"})[1]["state"], "unchanged")
        return retained

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("setpriv"), "requires Linux DAC isolation")
    def test_cli_denied_store_and_artifacts_preserve_saved_custom_choice(self):
        preview = self.save_public_custom()
        (self.project / "customisation.md").write_text("intentional customisation\n")
        for artifact in (".", "bindings.json", "approvals.json", "evidence", "evidence/fixture-audit.json",
                         "skills/SKILL.md", "project-configuration"):
            with self.subTest(artifact=artifact):
                path = self.project / ".playbook-config.json" if artifact == "project-configuration" else self.local / artifact
                before = self.stored_bytes()
                mode = path.stat().st_mode
                path.chmod(0)
                try:
                    probe = path / ("bindings.json" if artifact == "." else "fixture-audit.json") if path.is_dir() else path
                    denied = subprocess.run(
                        ["setpriv", "--bounding-set=-all", "--inh-caps=-all", "--ambient-caps=-all",
                         sys.executable, "-c", "import pathlib,sys\ntry: pathlib.Path(sys.argv[1]).read_bytes()\n"
                         "except PermissionError: sys.exit(73)\nelse: sys.exit(74)", str(probe)], capture_output=True)
                    self.assertEqual(denied.returncode, 73, "DAC denial must be observed, not assumed")
                    for action, request in self.public_actions(preview):
                        with self.subTest(action=action):
                            code, public = self.privacy_cli(action, request, deny=True)
                            if artifact in {".", "project-configuration"} or action in {"job-route", "reply"}:
                                self.assertEqual((code, public["state"]), (2, "blocked"))
                                self.assertIn("restore", public["message"].lower())
                            elif action == "read":
                                self.assertEqual(code, 0)
                                self.assertEqual(public["skill_before"]["jobs"]["specification"][0]["source_id"], self.identity)
                                self.assertFalse(any(row["binding"]["source_id"] == self.identity
                                                     for row in public["skill_alternatives"]["specification"]))
                            else:
                                self.assertEqual(code, 0)
                                self.assertEqual(public["origin"], "adopted project")
                finally:
                    path.chmod(mode)
                self.assertEqual(self.stored_bytes(), before)

    def test_cli_noncanonical_inventory_keys_all_public_actions(self):
        preview = self.save_public_custom()
        inventory = self.local / "bindings.json"
        approval_file = self.local / "approvals.json"
        original = json.loads(inventory.read_text())
        approvals = json.loads(approval_file.read_text())
        marker = "PRIVATE_FIXTURE_MARKER_SYNTHETIC_CREDENTIAL"
        for locator in ("./" + marker + "/SKILL.md", "skills/./" + marker + "/SKILL.md",
                        marker + "/SKILL.md/", marker + "/.", ".", "./", marker + "//SKILL.md",
                        "skills/../" + marker + "/SKILL.md", "/" + marker + "/SKILL.md",
                        marker + "\\SKILL.md", marker + "/SKILL.md\n"):
            for origin in ("inventory", "approvals"):
                with self.subTest(locator_shape=locator.replace(marker, "marker"), origin=origin):
                    identity = "project:" + locator
                    local = deepcopy(original)
                    audits = deepcopy(approvals)
                    if origin == "inventory":
                        local["sources"] = {identity: {"source": locator, "audits": {"specification": "fixture-audit"}}}
                    else:
                        local["sources"] = {}
                        audits["audits"]["fixture-audit"]["source_id"] = identity
                    inventory.write_text(json.dumps(local))
                    approval_file.write_text(json.dumps(audits))
                    before = self.stored_bytes()
                    for action, request in self.public_actions(preview):
                        with self.subTest(action=action):
                            code, public = self.privacy_cli(action, request)
                            if action == "read":
                                self.assertEqual(code, 0)
                                rejections = [row for row in public["skill_rejections"]
                                              if row["source_id"].startswith(("custom:", "project:"))]
                                self.assertEqual({row["source_id"] for row in rejections}, {"custom:unresolved"})
                                self.assertIn("restore the local binding", json.dumps(rejections))
                                self.assertEqual(public["skill_before"], preview["skill_after"])
                                self.assertFalse(any(row["binding"]["source_id"] == identity
                                                     for rows in public["skill_alternatives"].values() for row in rows))
                            elif action == "resolve":
                                self.assertEqual(code, 0)
                                self.assertEqual(public["origin"], "adopted project")
                            else:
                                self.assertEqual((code, public["state"]), (2, "blocked"))
                                self.assertIn("explicitly", public["message"])
                            self.assertEqual(self.stored_bytes(), before)

    def test_cli_canonical_project_components_remain_eligible(self):
        for locator in (".agents/skills/team-spec.v1/SKILL.md", "skills/team_spec-1/SKILL.md",
                        "skills/.hidden/SKILL.md", "skills/team./SKILL.md"):
            with self.subTest(locator=locator):
                source = self.project / locator
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(self.source.read_bytes())
                identity = "project:" + locator
                self.prepare_audit("specification", identity=identity, source=source)
                code, public = self.privacy_cli()
                self.assertEqual(code, 0)
                self.assertTrue(any(row["binding"]["source_id"] == identity
                                    for row in public["skill_alternatives"]["specification"]))

    def test_cli_rejected_custom_aliases_and_unknown_inventory_namespaces(self):
        preview = self.save_public_custom()
        inventory = self.local / "bindings.json"
        original = json.loads(inventory.read_text())
        for identity in ("custom:./PRIVATE_FIXTURE_MARKER", "custom:team/./PRIVATE_FIXTURE_MARKER",
                         "custom:PRIVATE_FIXTURE_MARKER/", "unknown:PRIVATE_FIXTURE_MARKER",
                         "playbook:PRIVATE_FIXTURE_MARKER", "gstack:PRIVATE_FIXTURE_MARKER"):
            with self.subTest(namespace=identity.split(":", 1)[0]):
                local = deepcopy(original)
                local["sources"][identity] = local["sources"].pop(self.identity)
                inventory.write_text(json.dumps(local))
                before = self.stored_bytes()
                for action, request in self.public_actions(preview):
                    with self.subTest(action=action):
                        code, public = self.privacy_cli(action, request)
                        if action == "read":
                            self.assertEqual(code, 0)
                            self.assertIn("custom:unresolved", {row["source_id"] for row in public["skill_rejections"]})
                            self.assertIn("restore the local binding", json.dumps(public["skill_rejections"]))
                        elif action == "resolve":
                            self.assertEqual(code, 0)
                        else:
                            self.assertEqual((code, public["state"]), (2, "blocked"))
                        self.assertEqual(self.stored_bytes(), before)

    def test_all_identity_publication_uses_the_saved_canonical_predicate(self):
        for identity in ("project:team..private", "custom:team//private", "custom:/private",
                         "custom:credential@private", None):
            with self.subTest(identity=identity):
                self.bindings._reject(identity, "restore local inventory")
                self.assertEqual(self.bindings.rejections[-1]["source_id"], "custom:unresolved")
                with self.assertRaises(ConfigError):
                    self.bindings._candidate(identity, self.source, "single", "fixture", "fixture")
        for identity in ("custom:team-spec", "project:team/skill.v1/SKILL.md"):
            self.bindings._reject(identity, "restore exact source")
            self.assertEqual(self.bindings.rejections[-1]["source_id"], identity)
            candidate = self.bindings._candidate(identity, self.source, "single", "fixture", "fixture")
            self.assertEqual(candidate["binding"]["source_id"], identity)

    def test_cli_rejected_inventory_identity_is_canonical_and_private(self):
        inventory = self.local / "bindings.json"
        original = json.loads(inventory.read_text())
        for identity in ("custom:.." + str(self.machines) + "/PRIVATE_FIXTURE_MARKER",
                         "project:.." + str(self.project) + "/PRIVATE_FIXTURE_MARKER",
                         "custom:team//PRIVATE_FIXTURE_MARKER", "custom:/PRIVATE_FIXTURE_MARKER",
                         "custom:token@PRIVATE_FIXTURE_MARKER"):
            with self.subTest(identity_kind=identity.split(":", 1)[0]):
                local = deepcopy(original)
                local["sources"][identity] = local["sources"].pop(self.identity)
                inventory.write_text(json.dumps(local))
                before = self.stored_bytes()
                code, public = self.privacy_cli()
                self.assertEqual(code, 0)
                self.assertEqual(public["state"], "decision_required")
                self.assertTrue(public["skill_rejections"])
                self.assertEqual({row["source_id"] for row in public["skill_rejections"]
                                  if row["source_id"].startswith(("custom:", "project:"))},
                                 {"custom:unresolved"})
                self.assertIn("restore the local binding", json.dumps(public["skill_rejections"]))
                self.assertFalse(any(row["binding"]["source_id"] == identity
                                     for rows in public["skill_alternatives"].values() for row in rows))
                self.assertEqual(self.stored_bytes(), before)

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("setpriv"), "requires Linux DAC isolation")
    def test_cli_denied_saved_qa_selection_state_blocks_without_changes(self):
        _, source, _, _ = test_skill_bindings.qualified_qa(self.project)
        for identity in ("custom:team-qa", "project:" + source.relative_to(self.project).as_posix()):
            with self.subTest(identity_kind=identity.split(":", 1)[0]):
                self.prepare_audit("application_qa", identity=identity, source=source)
                preview = self.save_custom("application_qa", identity)
                before = self.stored_bytes()
                mode = self.state.stat().st_mode
                self.state.chmod(0)
                try:
                    for action, request in (("read", {}), ("resolve", {"role": "verification"}),
                                            ("job-route", {"job": "application_qa", "owner": "09"}),
                                            ("reply", {"proposal": preview, "reply": "Apply"})):
                        code, public = self.privacy_cli(action, request, deny=True)
                        self.assertEqual(code, 2)
                        self.assertEqual(public["state"], "blocked")
                        self.assertIn("PermissionError", public["message"])
                        self.assertIn("restore", public["message"].lower())
                        self.assertIn("selection state", public["message"])
                finally:
                    self.state.chmod(mode)
                self.assertEqual(self.stored_bytes(), before)

    def test_snapshot_state_io_and_parser_errors_have_portable_recovery(self):
        original = self.service._bytes
        for error in (PermissionError(str(self.project)), OSError(str(self.machines)),
                      UnicodeError("PRIVATE_FIXTURE_MARKER")):
            def denied(path):
                if path == self.state:
                    raise error
                return original(path)
            with self.subTest(error_class=type(error).__name__), patch.object(self.service, "_bytes", denied):
                public = self.service.read()
                self.assertEqual(public["state"], "blocked")
                self.assertNotIn(str(self.project), json.dumps(public))
                self.assertNotIn(str(self.machines), json.dumps(public))
                self.assertNotIn("PRIVATE_FIXTURE_MARKER", json.dumps(public))
                self.assertIn(type(error).__name__, public["message"])
                self.assertIn("restore", public["message"].lower())
        with patch("playbook_config.legacy_routing", side_effect=ConfigError("PRIVATE_FIXTURE_MARKER")):
            public = self.service.read()
            self.assertEqual(public["state"], "blocked")
            self.assertNotIn("PRIVATE_FIXTURE_MARKER", json.dumps(public))
            self.assertIn("restore", public["message"].lower())

    def test_cli_legacy_state_parser_text_and_invalid_encoding_are_private(self):
        for contents in (b"model_routing:\n  PRIVATE_FIXTURE_MARKER: 1\n  PRIVATE_FIXTURE_MARKER: 2\n",
                         b"model_routing:\n\xff"):
            with self.subTest(encoding_valid=contents.isascii()):
                self.state.write_bytes(contents)
                before = self.stored_bytes()
                code, public = self.privacy_cli()
                self.assertEqual(code, 2)
                self.assertEqual(public["state"], "blocked")
                self.assertIn("selection state", public["message"])
                self.assertIn("restore", public["message"].lower())
                self.assertEqual(self.stored_bytes(), before)

    def test_sensitive_hardlinks_block_discovery_apply_and_retained_invocation(self):
        for artifact in ("bindings.json", "approvals.json", "evidence/fixture-audit.json"):
            with self.subTest(artifact=artifact):
                preview = self.pick(self.preview(), "specification", [self.identity])
                path = self.local / artifact
                alias = self.project / "private-alias.json"
                before = path.read_bytes()
                os.link(path, alias)
                try:
                    proposal = self.service.read()
                    self.assertFalse(any(option["binding"]["source_id"] == self.identity
                                         for option in proposal["skill_alternatives"]["specification"]))
                    self.assertIn("single-link", json.dumps(proposal["skill_rejections"]))
                    self.assertEqual(self.service.reply(preview, "Apply")["state"], "blocked")
                    code, result = self.stage_entry(approved=preview["skill_after"])
                    self.assertEqual(code, 2)
                    with self.assertRaises(ConfigError):
                        self.bindings.invocation_source(preview["skill_after"], "specification", "03", self.identity)
                    for public in (proposal, result):
                        self.assertNotIn(str(self.local), json.dumps(public))
                        self.assertNotIn(str(self.project), json.dumps(public))
                    self.assertEqual(path.read_bytes(), before)
                    self.assertEqual(alias.read_bytes(), before)
                    self.assertFalse((self.project / ".playbook-config.json").exists())
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                finally:
                    alias.unlink()
                self.assertTrue(any(option["binding"]["source_id"] == self.identity
                                    for option in self.service.read()["skill_alternatives"]["specification"]))

    def test_saved_custom_selection_blocks_after_sensitive_hardlink(self):
        preview = self.save_custom()
        config = self.project / ".playbook-config.json"
        before = config.read_bytes()
        for artifact in ("bindings.json", "approvals.json", "evidence/fixture-audit.json"):
            with self.subTest(artifact=artifact):
                alias = self.project / "private-alias.json"
                os.link(self.local / artifact, alias)
                try:
                    self.assertEqual(self.stage_entry()[0], 2)
                    self.assertEqual(self.stage_entry(approved=preview["skill_after"])[0], 2)
                    with self.assertRaises(ConfigError):
                        self.service.dispatch_job("specification", "03")
                    self.assertEqual(config.read_bytes(), before)
                finally:
                    alias.unlink()

    def test_missing_installed_source_has_portable_diagnostic(self):
        missing = self.machines / "private-install/code-review/SKILL.md"
        self.service.bindings = JobBindings(self.project, custom_dir=self.local,
                                           installed={"mattpocock-skills:code-review": [missing]})
        proposal = self.service.read()
        self.assertIn("FileNotFoundError", json.dumps(proposal["skill_rejections"]))
        self.assertNotIn(str(self.machines), json.dumps(proposal))

    def test_cli_nonfile_installed_source_has_portable_diagnostic(self):
        home = self.machines / "fixture-home"
        source = home / ".agents/skills/code-review/SKILL.md"
        source.mkdir(parents=True)
        adapter = ("import json,sys; request=json.load(sys.stdin); "
                   "json.dump({'request_id':request['request_id'],'checked_at':request['started_at'],"
                   "'authority':'host-reported-selection','revision':'fixture-cli',"
                   "'routes':[{'model_id':'available-build','runner':'codex','reasoning':'medium',"
                   "'roles':['implementation']}]},sys.stdout)")
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "--custom-bindings-dir", str(self.local),
                   "--discovery-command", json.dumps([sys.executable, "-c", adapter]), "read"]
        completed = subprocess.run(command, input="{}", text=True, capture_output=True,
                                   env=dict(os.environ, HOME=str(home)))
        self.assertEqual(completed.returncode, 0)
        proposal = json.loads(completed.stdout)
        self.assertIn("IsADirectoryError", json.dumps(proposal["skill_rejections"]))
        self.assertNotIn(str(self.machines), completed.stdout)
        saved = deepcopy(proposal["skill_before"])
        saved["jobs"]["code_review"] = [{"source_id": "mattpocock-skills:code-review",
                                         "source_sha256": "0" * 64, "contract_sha256": "0" * 64}]
        request = {"job": "code_review", "owner": "08", "approved_binding": saved}
        completed = subprocess.run(command[:-1] + ["job-route"], input=json.dumps(request),
                                   text=True, capture_output=True, env=dict(os.environ, HOME=str(home)))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["state"], "blocked")
        self.assertNotIn(str(home), completed.stdout)
        self.assertNotIn(str(self.local), completed.stdout)

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

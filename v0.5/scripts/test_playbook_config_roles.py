"""S2 conversation behaviours at the public configuration boundary."""

from copy import deepcopy
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from playbook_config import ConfigError, Configuration, ROLES


class RoleConversationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "project"
        self.project.mkdir()
        self.state = self.project / ".playbook-state.yml"
        self.runtime = (
            "model_routing:\n  defaults:\n"
            "    escalated_repair: {model_id: custom-repair, runner: codex, reasoning: high, "
            "trigger_unsuccessful_repairs: 5, cycles_per_slice: 1, scope: approved_slice, "
            "authority: diagnose_and_implement}\n"
            "pending_model_routes: [{route_id: pending, status: selected}]\n"
            "active_features: [{slug: active, routing: immutable}]\n"
            "last_run: {history: untouched}\n"
        ).encode()
        self.state.write_bytes(self.runtime)
        self.approval = self.project / "approval.json"
        self.approval.write_bytes(b'{"approved":true}\n')
        self.routes = [
            {"model_id": "fixture-model", "runner": "codex", "reasoning": "medium", "roles": list(ROLES)},
            {"model_id": "fixture-model", "runner": "codex", "reasoning": "high", "roles": list(ROLES)},
            {"model_id": "fixture-model", "runner": "conductor", "reasoning": "high", "roles": list(ROLES)},
            {"model_id": "fixture-other", "runner": "codex", "reasoning": "high", "roles": ["planning"]},
        ]
        self.coordinator = None
        self.service = Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z")

    def discover(self, request):
        return {"request_id": request["request_id"], "checked_at": request["started_at"],
                "authority": "host-reported-selection", "revision": "fixture-1", "routes": deepcopy(self.routes),
                "coordinator": deepcopy(self.coordinator)}

    def test_all_roles_typed_edits_preserve_other_drafts_and_runtime(self):
        proposal = self.service.read()
        original = deepcopy(proposal["before"])
        for label, role in zip(("Plan", "Build", "Verify", "Repair"), ROLES):
            with self.subTest(role=role):
                previous = deepcopy(proposal["after"])
                editor = self.service.reply(proposal, "Edit " + label)
                proposal = self.service.reply(editor, "1")
                self.assertEqual(proposal["state"], "proposal_ready")
                self.assertEqual(proposal["after"][role]["model_id"], "fixture-model")
                for other in ROLES:
                    if other != role:
                        self.assertEqual(proposal["after"][other], previous[other])
                self.assertEqual(proposal["before"], original)
        self.assertEqual(proposal["after"]["escalated_repair"]["trigger_unsuccessful_repairs"], 5)
        self.assertEqual(proposal["after"]["escalated_repair"]["cycles_per_slice"], 1)
        self.assertFalse((self.project / ".playbook-config.json").exists())
        result = self.service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "applied")
        self.assertFalse(result["launched"])
        saved = json.loads((self.project / ".playbook-config.json").read_text())
        self.assertEqual(saved["models"], proposal["after"])
        self.assertEqual(self.state.read_bytes(), self.runtime)
        self.assertEqual(self.approval.read_bytes(), b'{"approved":true}\n')

    def test_component_editor_has_typed_role_model_runner_reasoning_choices(self):
        for index, role in enumerate(ROLES):
            with self.subTest(role=role):
                proposal = self.service.read()
                proposal = self.service.reply(proposal, "Edit")
                proposal = self.service.reply(proposal, str(index + 1))
                proposal = self.service.reply(proposal, "Pick model")
                self.assertEqual(proposal["step"], "model")
                self.assertEqual(proposal["options"][0], "fixture-model")
                proposal = self.service.reply(proposal, "1")
                self.assertEqual(proposal["step"], "runner")
                self.assertEqual(proposal["options"], ["codex", "conductor"])
                proposal = self.service.reply(proposal, "1")
                self.assertEqual(proposal["step"], "reasoning")
                self.assertEqual(proposal["options"], ["medium", "high"])
                proposal = self.service.reply(proposal, "2")
                self.assertEqual(proposal["state"], "proposal_ready")
                self.assertEqual(proposal["after"][role]["reasoning"], "high")
                self.assertEqual(self.service.reply(proposal, "Apply")["state"], "applied")

    def test_local_preference_is_previewed_saved_separately_and_skips_known_questions(self):
        local = Path(self.temporary.name) / "personal"
        self.coordinator = {"model_id": "observed-only", "runner": "codex", "reasoning": "high"}
        service = Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z",
                                preferences_dir=local, context={"goal": "Known project", "billing": "unknown"})
        proposal = service.read()
        self.assertEqual(proposal["missing_context"], ["presentation"])
        self.assertTrue(proposal["coordinator"]["observed"])
        self.assertEqual(proposal["qa"]["inherits"], "verification")
        preview = service.reply(proposal, "Expert")
        self.assertEqual(preview["step"], "preference_preview")
        self.assertEqual(preview["personal"]["after"], {"schema_version": 1, "presentation": "expert"})
        self.assertEqual(preview["personal"]["destination"], str(local / "preferences.json"))
        self.assertFalse(local.exists())
        self.assertFalse((self.project / ".playbook-config.json").exists())
        self.assertEqual(service.reply(preview, "Not now")["state"], "unchanged")
        self.assertFalse(local.exists())
        result = service.reply(preview, "Apply preference")
        self.assertEqual(result["state"], "proposal_ready")
        self.assertEqual(result["presentation"], "expert")
        self.assertEqual(result["missing_context"], [])
        self.assertFalse((self.project / ".playbook-config.json").exists())
        self.assertEqual(json.loads((local / "preferences.json").read_text()), preview["personal"]["after"])
        reopened = service.read()
        self.assertEqual(reopened["presentation"], "expert")
        self.assertEqual(reopened["missing_context"], [])
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_missing_context_is_session_only_and_bootstrap_is_not_repeated(self):
        local = Path(self.temporary.name) / "personal"
        self.state.unlink()
        service = Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z",
                                preferences_dir=local, context={})
        proposal = service.read()
        self.assertEqual(proposal["bootstrap"]["required"], True)
        proposal = service.reply(proposal, "Goal A small project")
        proposal = service.reply(proposal, "Billing unknown")
        self.assertEqual(proposal["missing_context"], ["presentation"])
        preview = service.reply(proposal, "Guided")
        proposal = service.reply(preview, "Apply preference")
        self.assertEqual(proposal["context"], {"goal": "A small project", "billing": "unknown"})
        self.assertEqual(proposal["missing_context"], [])
        self.assertEqual(service.reply(proposal, "Apply")["state"], "blocked")
        self.assertFalse(self.state.exists())
        self.assertFalse((self.project / ".playbook-config.json").exists())

    def personal_service(self, directory, checkpoint=None, **kwargs):
        return Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z", checkpoint,
                             preferences_dir=directory, context={"goal": "Known project", "billing": "unknown"}, **kwargs)

    def test_guided_and_expert_save_identical_project_settings(self):
        results = []
        for mode in ("Guided", "Expert"):
            with self.subTest(mode=mode):
                destination = self.project / ".playbook-config.json"
                destination.unlink(missing_ok=True)
                service = self.personal_service(Path(self.temporary.name) / mode)
                draft = service.reply(service.read(), "Edit Plan")
                draft = service.reply(draft, "1")
                selected = deepcopy(draft["after"])
                draft = service.reply(draft, mode)
                draft = service.reply(draft, "Apply preference")
                self.assertEqual(draft["after"], selected)
                self.assertEqual(draft["presentation"], mode.lower())
                self.assertEqual(service.reply(draft, "Apply")["state"], "applied")
                results.append(destination.read_bytes())
        self.assertEqual(results[0], results[1])

    def test_explain_all_roles_is_read_only_and_qa_coordinator_are_not_editable(self):
        proposal = self.service.read()
        for role in ("Plan", "Build", "Verify", "Repair"):
            with self.subTest(role=role):
                explanation = self.service.reply(proposal, "Explain " + role)
                self.assertEqual(explanation["after"], proposal["after"])
                self.assertEqual(explanation["explanation"]["choice"], proposal["after"][ROLES[("Plan", "Build", "Verify", "Repair").index(role)]])
                self.assertIn("unknown", explanation["explanation"]["limitations"])
                self.assertFalse((self.project / ".playbook-config.json").exists())
        for label in ("QA", "Coordinator"):
            self.assertEqual(self.service.reply(proposal, "Edit " + label)["state"], "blocked")
        preview = self.service.reply(self.service.reply(proposal, "Edit Verify"), "2")
        self.assertEqual(preview["qa"]["choice"], preview["after"]["verification"])
        self.assertEqual(preview["coordinator"], proposal["coordinator"])

    def test_every_edited_role_rechecks_availability_and_constraints(self):
        for label, role in zip(("Plan", "Build", "Verify", "Repair"), ROLES):
            with self.subTest(role=role):
                draft = self.service.reply(self.service.reply(self.service.read(), "Edit " + label), "1")
                original_routes = deepcopy(self.routes)
                self.routes[0]["roles"].remove(role)
                result = self.service.reply(draft, "Apply")
                self.assertEqual(result["state"], "blocked")
                self.assertIn("unavailable", result["message"])
                self.assertFalse((self.project / ".playbook-config.json").exists())
                self.routes = original_routes
        draft = self.service.reply(self.service.reply(self.service.read(), "Edit Repair"), "1")
        draft["after"]["escalated_repair"]["cycles_per_slice"] = 2
        self.assertEqual(self.service.reply(draft, "Apply")["state"], "blocked")
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_personal_conflict_cannot_overwrite_or_partially_save_project(self):
        local = Path(self.temporary.name) / "personal"
        service = self.personal_service(local)
        draft = service.reply(service.read(), "Expert")
        local.mkdir()
        current = b'{"schema_version": 1, "presentation": "guided"}\n'
        (local / "preferences.json").write_bytes(current)
        result = service.reply(draft, "Apply preference")
        self.assertEqual(result["state"], "blocked")
        self.assertEqual((local / "preferences.json").read_bytes(), current)
        self.assertFalse((self.project / ".playbook-config.json").exists())

    def test_local_save_uses_retained_completion_recovery_at_storage_failures(self):
        for point in ("staged", "before_replace", "committed", "before_completion"):
            with self.subTest(point=point):
                local = Path(self.temporary.name) / point

                def fail(checkpoint):
                    if checkpoint == point:
                        raise OSError("injected local storage failure")

                service = self.personal_service(local, fail)
                draft = service.reply(service.read(), "Expert")
                result = service.reply(draft, "Apply preference")
                if point in {"committed", "before_completion"}:
                    self.assertEqual(result["state"], "recovery_required")
                    self.assertTrue((local / ".playbook-config.recovery").exists())
                    self.assertTrue((local / ".playbook-config.lock").exists())
                    reader = self.personal_service(local)
                    self.assertEqual(reader.read()["state"], "recovery_required")
                    marker = json.loads((local / ".playbook-config.recovery").read_text())
                    self.assertEqual(marker["destination"], "preferences.json")
                    self.assertEqual(json.loads((local / marker["attempted"]).read_text())["presentation"], "expert")
                else:
                    self.assertEqual(result["state"], "blocked")
                    self.assertFalse((local / "preferences.json").exists())
                    self.assertFalse((local / ".playbook-config.lock").exists())
                self.assertFalse((self.project / ".playbook-config.json").exists())
                self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_local_completion_conflict_keeps_concurrent_bytes_and_blocks_readers(self):
        local = Path(self.temporary.name) / "personal"
        external = b'{"schema_version": 1, "presentation": "guided"}\n'

        def conflict(point):
            if point == "before_completion":
                (local / "preferences.json").write_bytes(external)

        service = self.personal_service(local, conflict)
        result = service.reply(service.reply(service.read(), "Expert"), "Apply preference")
        self.assertEqual(result["state"], "recovery_required")
        self.assertEqual((local / "preferences.json").read_bytes(), external)
        (local / ".playbook-config.lock").unlink()
        (local / ".playbook-config.recovery").unlink()
        self.assertEqual(self.personal_service(local).read()["state"], "recovery_required")
        self.assertTrue(list(local.glob("*.receipt.conflict")))

    def test_invalid_personal_values_and_project_local_destination_block_without_rewrite(self):
        local = Path(self.temporary.name) / "personal"
        local.mkdir()
        for value in ('{', '{"schema_version":2,"presentation":"guided"}',
                      '{"schema_version":1,"presentation":"expert","billing":"unknown"}',
                      '{"schema_version":1,"presentation":"guided","presentation":"expert"}'):
            with self.subTest(value=value):
                (local / "preferences.json").write_text(value)
                self.assertEqual(self.personal_service(local).read()["state"], "blocked")
                self.assertEqual((local / "preferences.json").read_text(), value)
        from playbook_config import ConfigError
        with self.assertRaises(ConfigError):
            self.personal_service(self.project / "local")

    def test_helper_completes_typed_edit_with_local_preference(self):
        adapter = Path(self.temporary.name) / "adapter.py"
        adapter.write_text(
            "import json, sys\nrequest = json.load(sys.stdin)\n"
            "print(json.dumps({'request_id': request['request_id'], 'checked_at': request['started_at'], "
            "'authority': 'host-reported-selection', 'revision': 'fixture-1', 'routes': " + repr(self.routes) + "}))\n"
        )
        local = Path(self.temporary.name) / "personal"
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "--preferences-dir", str(local),
                   "--discovery-command", json.dumps([sys.executable, str(adapter)]),
                   "--now", "2026-09-30T12:00:00Z"]

        def run(action, request):
            result = subprocess.run(command + [action], input=json.dumps(request), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

        draft = run("read", {"context": {"goal": "Known project", "billing": "unknown"}})
        for reply in ("Edit Repair", "Pick model", "1", "1", "2", "Expert", "Apply preference", "Apply"):
            draft = run("reply", {"proposal": draft, "reply": reply})
        self.assertEqual(draft["state"], "applied")
        self.assertFalse(draft["launched"])
        self.assertEqual(json.loads((local / "preferences.json").read_text())["presentation"], "expert")

    def test_invalid_editor_reply_and_back_preserve_unrelated_drafts(self):
        draft = self.service.reply(self.service.reply(self.service.read(), "Edit Plan"), "2")
        selected = deepcopy(draft["after"])
        editor = self.service.reply(draft, "Edit Repair")
        result = self.service.reply(editor, "999")
        self.assertEqual(result["state"], "blocked")
        restored = self.service.reply(result, "Back")
        self.assertEqual(restored["after"], selected)
        self.assertEqual(restored["step"], "edit")
        result = self.service.reply(restored, "1")
        self.assertEqual(result["after"]["planning"], selected["planning"])
        blocked = self.service.reply(self.service.reply(result, "Edit Verify"), "999")
        build_editor = self.service.reply(blocked, "Edit Build")
        self.assertEqual(build_editor["after"], result["after"])
        blocked = self.service.reply(build_editor, "999")
        role_editor = self.service.reply(blocked, "Edit")
        self.assertEqual(role_editor["after"], result["after"])
        self.assertEqual(self.service.reply(result, "Apply")["state"], "applied")

    def test_recovery_keeps_all_role_drafts_without_allowing_writes(self):
        for boundary in ("api", "cli"):
            for checkpoint in ("committed", "before_completion"):
                with self.subTest(boundary=boundary, checkpoint=checkpoint), tempfile.TemporaryDirectory() as directory:
                    local = Path(directory) / "personal"
                    fault = Path(directory) / "inject"
                    fault.touch()

                    def fail(point):
                        if point == checkpoint and fault.exists():
                            raise OSError("fixture local durability failure")

                    service = self.personal_service(local, fail)
                    adapter = Path(directory) / "adapter.py"
                    adapter.write_text(
                        "import json, sys\nrequest = json.load(sys.stdin)\n"
                        "print(json.dumps({'request_id': request['request_id'], 'checked_at': request['started_at'], "
                        "'authority': 'host-reported-selection', 'revision': 'fixture-1', 'routes': "
                        + repr(self.routes) + "}))\n"
                    )
                    wrapper = (
                        "import runpy, sys\nfrom pathlib import Path\n"
                        "sys.path.insert(0, str(Path(sys.argv[1]).parent))\n"
                        "from playbook_config import Configuration\n"
                        "original = Configuration.__init__\n"
                        "def fail(point):\n"
                        "    if point == " + repr(checkpoint) + " and Path(" + repr(str(fault)) + ").exists():\n"
                        "        raise OSError('fixture local durability failure')\n"
                        "def initialize(self, *args, **kwargs):\n"
                        "    original(self, *args, **kwargs)\n"
                        "    if self.preferences is not None:\n"
                        "        self.preferences.checkpoint = fail\n"
                        "Configuration.__init__ = initialize\n"
                        "sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')\n"
                    )
                    command = [sys.executable, "-c", wrapper, str(Path(__file__).with_name("configure-playbook.py")),
                               "--project", str(self.project), "--preferences-dir", str(local),
                               "--discovery-command", json.dumps([sys.executable, str(adapter)]),
                               "--now", "2026-09-30T12:00:00Z"]

                    def run(action, proposal=None, reply=None):
                        if boundary == "api":
                            return service.read() if action == "read" else service.reply(proposal, reply)
                        request = {"context": {"goal": "Known project", "billing": "unknown"}}
                        if action == "reply":
                            request.update(proposal=proposal, reply=reply)
                        completed = subprocess.run(command + [action], input=json.dumps(request),
                                                   text=True, capture_output=True)
                        result = json.loads(completed.stdout)
                        self.assertEqual(completed.returncode, 2 if result["state"] in {"blocked", "recovery_required"} else 0,
                                         completed.stderr)
                        return result

                    draft = run("read")
                    for label in ("Plan", "Build", "Verify", "Repair"):
                        draft = run("reply", run("reply", draft, "Edit " + label), "2")
                    draft = run("reply", draft, "Expert")
                    selected = deepcopy(draft["after"])
                    result = run("reply", draft, "Apply preference")
                    self.assertEqual(result["state"], "recovery_required")
                    self.assertEqual(result["retained_proposal"], draft)
                    self.assertEqual(run("read")["state"], "recovery_required")
                    saved = {path.name: path.read_bytes() for path in local.iterdir() if path.is_file()}
                    for reply in ("Apply", "Apply preference", "Reload", "invalid"):
                        result = run("reply", result, reply)
                        self.assertIn(result["state"], {"blocked", "recovery_required"})
                        self.assertEqual(result["retained_proposal"]["after"], selected)
                    for reply in ("Back", "Edit", "Edit Build"):
                        restored = run("reply", result, reply)
                        self.assertEqual(restored["after"], selected)
                        self.assertIn(run("reply", restored, "Apply")["state"], {"blocked", "recovery_required"})
                        self.assertEqual(run("reply", run("reply", restored, "Expert"), "Apply preference")["state"], "recovery_required")
                    self.assertEqual({path.name: path.read_bytes() for path in local.iterdir() if path.is_file()}, saved)
                    self.assertFalse((self.project / ".playbook-config.json").exists())
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                    for path in local.iterdir():
                        path.rmdir() if path.is_dir() else path.unlink()
                    fault.unlink()
                    restored = run("reply", run("reply", result, "Back"), "Apply preference")
                    self.assertEqual(restored["after"], selected)
                    self.assertEqual(run("reply", restored, "Apply")["state"], "applied")
                    (self.project / ".playbook-config.json").unlink()

    def test_project_save_recovery_and_invalid_replies_keep_sealed_draft(self):
        def fail(point):
            if point == "before_completion":
                raise OSError("fixture project durability failure")

        service = Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z", fail)
        draft = service.read()
        for label in ("Plan", "Build", "Verify", "Repair"):
            draft = service.reply(service.reply(draft, "Edit " + label), "2")
        result = service.reply(draft, "Apply")
        self.assertEqual(result["state"], "recovery_required")
        self.assertEqual(result["retained_proposal"], draft)
        for reply in (None, "Apply", "Reload", "invalid"):
            result = service.reply(result, reply)
            self.assertEqual(result["state"], "recovery_required")
            self.assertEqual(result["retained_proposal"], draft)
        restored = service.reply(result, "Edit Verify")
        self.assertEqual(restored["after"], draft["after"])
        self.assertEqual(service.reply(restored, "Apply")["state"], "recovery_required")
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_pending_recovery_in_either_directory_blocks_both_public_writes(self):
        for boundary in ("api", "cli"):
            for origin in ("project", "local"):
                for marker in (".playbook-config.recovery", ".playbook-config.lock",
                               ".playbook-config-unfinished.receipt"):
                    for existing_local in (False, True):
                        with self.subTest(boundary=boundary, origin=origin, marker=marker,
                                          existing_local=existing_local), tempfile.TemporaryDirectory() as temporary:
                            root = Path(temporary)
                            project = root / "project"
                            local = root / "personal"
                            project.mkdir()
                            (project / ".playbook-state.yml").write_bytes(self.runtime)
                            if existing_local:
                                local.mkdir()
                                (local / "preferences.json").write_text(
                                    '{"schema_version":1,"presentation":"guided"}\n')
                            service = Configuration(project, self.discover,
                                                    lambda: "2026-09-30T12:00:00Z",
                                                    preferences_dir=local,
                                                    context={"goal": "Known", "billing": "unknown"})
                            adapter = root / "adapter.py"
                            adapter.write_text(
                                "import json, sys\nrequest = json.load(sys.stdin)\n"
                                "print(json.dumps({'request_id': request['request_id'], "
                                "'checked_at': request['started_at'], "
                                "'authority': 'host-reported-selection', 'revision': 'fixture-1', "
                                "'coordinator': None, 'routes': " + repr(self.routes) + "}))\n")
                            command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                                       "--project", str(project), "--preferences-dir", str(local),
                                       "--discovery-command", json.dumps([sys.executable, str(adapter)]),
                                       "--now", "2026-09-30T12:00:00Z"]

                            def run(action, proposal=None, reply=None):
                                if boundary == "api":
                                    return service.read() if action == "read" else service.reply(proposal, reply)
                                request = {"context": {"goal": "Known", "billing": "unknown"}}
                                if action == "reply":
                                    request.update(proposal=proposal, reply=reply)
                                completed = subprocess.run(command + [action], input=json.dumps(request),
                                                           text=True, capture_output=True)
                                result = json.loads(completed.stdout)
                                self.assertEqual(completed.returncode,
                                                 2 if result["state"] in {"blocked", "recovery_required"} else 0,
                                                 completed.stderr)
                                return result

                            def files():
                                return {str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
                                        for directory in (project, local) if directory.exists()
                                        for path in (directory, *directory.rglob("*"))}

                            draft = run("read")
                            draft = run("reply", run("reply", draft, "Edit Build"), "2")
                            draft = run("reply", draft, "Expert")
                            destination = project if origin == "project" else local
                            destination.mkdir(exist_ok=True)
                            pending = destination / marker
                            pending.write_text("{}\n")
                            before = files()
                            result = run("reply", draft, "Apply")
                            self.assertIn(result["state"], {"blocked", "recovery_required"})
                            self.assertEqual(result["retained_proposal"], draft)
                            restored = run("reply", result, "Back")
                            preview = run("reply", restored, "Expert")
                            result = run("reply", preview, "Apply preference")
                            self.assertIn(result["state"], {"blocked", "recovery_required"})
                            self.assertIn("reconcile", result["message"].lower())
                            self.assertEqual(result["retained_proposal"], preview)
                            self.assertEqual(files(), before)
                            pending.unlink()
                            restored = run("reply", result, "Back")
                            saved = run("reply", restored, "Apply preference")
                            self.assertEqual(saved["state"], "proposal_ready")
                            self.assertEqual(saved["after"], draft["after"])
                            self.assertEqual(run("reply", saved, "Apply")["state"], "applied")
                            self.assertEqual(json.loads((local / "preferences.json").read_text())["presentation"],
                                             "expert")
                            self.assertEqual(json.loads((project / ".playbook-config.json").read_text())["models"],
                                             draft["after"])
                            self.assertEqual((project / ".playbook-state.yml").read_bytes(), self.runtime)

    def cross_store_save(self, boundary, destination, point, artifact, existing, concurrent=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            local = root / "personal"
            project.mkdir()
            local.mkdir()
            (project / ".playbook-state.yml").write_bytes(self.runtime)
            fault = root / "fault.json"
            injection = (
                "def inject(point):\n"
                "    if not fault.exists(): return\n"
                "    settings = json.loads(fault.read_text())\n"
                "    if point != settings['point']: return\n"
                "    marker = Path(settings['marker'])\n"
                "    marker.write_text(json.dumps(settings['content']) + '\\n')\n"
                "    if settings['conflict']: marker.with_name(marker.name + '.conflict').mkdir(exist_ok=True)\n"
                "    if settings['concurrent']: Path(settings['destination']).write_bytes(b'external concurrent bytes\\n')\n"
                "def install_completion(store):\n"
                "    original_check = store._receipt_conflicts\n"
                "    original_bytes = store._bytes\n"
                "    completing_now = False\n"
                "    def read_bytes(path):\n"
                "        data = original_bytes(path)\n"
                "        if completing_now and path == store.state_path: inject('completion_last_read')\n"
                "        return data\n"
                "    def check(receipt, marker, completing=False):\n"
                "        nonlocal completing_now\n"
                "        completing_now = completing\n"
                "        try:\n"
                "            if completing: inject('completion_entry')\n"
                "            return original_check(receipt, marker, completing=completing)\n"
                "        finally:\n"
                "            completing_now = False\n"
                "    store._bytes = read_bytes\n"
                "    store._receipt_conflicts = check\n"
            )
            namespace = {"fault": fault, "json": json, "Path": Path}
            exec(injection, namespace)
            service = Configuration(project, self.discover, lambda: "2026-09-30T12:00:00Z",
                                    namespace["inject"], preferences_dir=local,
                                    context={"goal": "Known", "billing": "unknown"})
            for store in (service, service.preferences):
                namespace["install_completion"](store)
            adapter = root / "adapter.py"
            adapter.write_text(
                "import json, sys\nrequest = json.load(sys.stdin)\n"
                "print(json.dumps({'request_id': request['request_id'], 'checked_at': request['started_at'], "
                "'authority': 'host-reported-selection', 'revision': 'fixture-1', 'coordinator': None, "
                "'routes': " + repr(self.routes) + "}))\n")
            wrapper = (
                "import json, runpy, sys\nfrom pathlib import Path\n"
                "sys.path.insert(0, str(Path(sys.argv[1]).parent))\n"
                "from playbook_config import Configuration\n"
                "fault = Path(" + repr(str(fault)) + ")\n" + injection +
                "original = Configuration.__init__\n"
                "def initialize(self, *args, **kwargs):\n"
                "    original(self, *args, **kwargs)\n"
                "    self.checkpoint = inject\n"
                "    install_completion(self)\n"
                "    if self.preferences is not None: self.preferences.checkpoint = inject\n"
                "Configuration.__init__ = initialize\n"
                "sys.argv = sys.argv[1:]\nrunpy.run_path(sys.argv[0], run_name='__main__')\n")
            command = [sys.executable, "-c", wrapper, str(Path(__file__).with_name("configure-playbook.py")),
                       "--project", str(project), "--preferences-dir", str(local),
                       "--discovery-command", json.dumps([sys.executable, str(adapter)]),
                       "--now", "2026-09-30T12:00:00Z"]

            def run(action, proposal=None, reply=None):
                if boundary == "api":
                    return service.read() if action == "read" else service.reply(proposal, reply)
                request = {"context": {"goal": "Known", "billing": "unknown"}}
                if action == "reply":
                    request.update(proposal=proposal, reply=reply)
                completed = subprocess.run(command + [action], input=json.dumps(request),
                                           text=True, capture_output=True)
                self.assertEqual(completed.stderr, "")
                result = json.loads(completed.stdout)
                self.assertEqual(completed.returncode,
                                 2 if result["state"] in {"blocked", "recovery_required"} else 0)
                return result

            if existing or destination == "project":
                (local / "preferences.json").write_text('{"schema_version":1,"presentation":"guided"}\n')
            if existing:
                seed = run("read")
                for label in ("Plan", "Build", "Verify", "Repair"):
                    seed = run("reply", run("reply", seed, "Edit " + label), "1")
                seeded = run("reply", seed, "Apply")
                self.assertEqual(seeded["state"], "applied", seeded)
            draft = run("read")
            for label in ("Plan", "Build", "Verify", "Repair"):
                draft = run("reply", run("reply", draft, "Edit " + label), "2")
            proposal = run("reply", draft, "Expert") if destination == "local" else draft
            target = local / "preferences.json" if destination == "local" else project / ".playbook-config.json"
            other = project if destination == "local" else local
            before = target.read_bytes() if target.exists() else None
            receipt = artifact in {"unfinished", "conflict"}
            marker = other / (".playbook-config-pending.receipt" if receipt else ".playbook-config." + artifact)
            content = {"destination": ".playbook-config.json" if destination == "local" else "preferences.json",
                       "completion_protocol": 3} if receipt else {}
            fault.write_text(json.dumps({"point": point, "marker": str(marker), "content": content,
                                         "conflict": artifact == "conflict", "concurrent": concurrent,
                                         "destination": str(target)}))
            result = run("reply", proposal, "Apply preference" if destination == "local" else "Apply")
            self.assertEqual(result["state"], "recovery_required", result)
            self.assertEqual(result["retained_proposal"], proposal)
            self.assertTrue(marker.exists())
            self.assertIn(run("read")["state"], {"blocked", "recovery_required"})
            observed = target.read_bytes() if target.exists() else None
            if point in {"staged", "before_replace", "before_publish"}:
                self.assertEqual(observed, before)
            else:
                self.assertTrue((target.parent / ".playbook-config.recovery").exists())
                self.assertTrue((target.parent / ".playbook-config.lock").exists())
                journal = json.loads((target.parent / ".playbook-config.recovery").read_text())
                attempted = (target.parent / journal["attempted"]).read_bytes()
                self.assertEqual(json.loads(attempted)["presentation"] if destination == "local"
                                 else json.loads(attempted)["models"], "expert" if destination == "local" else draft["after"])
                self.assertEqual(observed, b"external concurrent bytes\n" if concurrent else attempted)
                if before is not None:
                    self.assertEqual((target.parent / journal["captured"]).read_bytes(), before)
                if point in {"before_completion", "completion_entry", "completion_last_read"}:
                    self.assertTrue(list(target.parent.glob("*.receipt.conflict")))
                    self.assertFalse(any(path.name.endswith(".complete") for path in target.parent.glob("*.receipt*")
                                         if path.name.startswith(journal["attempted"])))
            retained_files = {path: path.read_bytes() for directory in (project, local)
                              for path in directory.iterdir() if path.is_file()}
            restored = run("reply", result, "Back")
            self.assertEqual(restored["after"], draft["after"])
            edited = run("reply", result, "Edit Verify")
            self.assertEqual(edited["after"], draft["after"])
            for reply in ("Apply", "Apply preference"):
                preview = run("reply", restored, "Expert") if reply == "Apply preference" else restored
                blocked = run("reply", preview, reply)
                self.assertIn(blocked["state"], {"blocked", "recovery_required"})
                self.assertEqual(blocked["retained_proposal"]["after"], draft["after"])
            self.assertEqual({path: path.read_bytes() for directory in (project, local)
                              for path in directory.iterdir() if path.is_file()}, retained_files)
            fault.unlink()
            for directory in (project, local):
                for path in directory.glob(".playbook-config*"):
                    if path.name == ".playbook-config.json":
                        continue
                    path.rmdir() if path.is_dir() else path.unlink()
            if before is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(before)
            self.assertEqual(run("read")["state"], "decision_required")
            resumed = run("reply", result, "Back")
            self.assertEqual(resumed["after"], draft["after"])
            if destination == "local":
                resumed = run("reply", resumed, "Apply preference")
                self.assertEqual(resumed["state"], "proposal_ready")
                self.assertEqual(json.loads(target.read_text())["presentation"], "expert")
            self.assertEqual(run("reply", resumed, "Apply")["state"], "applied")
            self.assertEqual(json.loads((project / ".playbook-config.json").read_text())["models"], draft["after"])
            self.assertEqual((project / ".playbook-state.yml").read_bytes(), self.runtime)

    def test_recovery_arising_before_publication_blocks_both_public_saves(self):
        for boundary in ("api", "cli"):
            for destination in ("local", "project"):
                for point in ("staged", "before_replace", "before_publish"):
                    for artifact in ("lock", "recovery", "unfinished", "conflict"):
                        for existing in (False, True):
                            with self.subTest(boundary=boundary, destination=destination, point=point,
                                              artifact=artifact, existing=existing):
                                self.cross_store_save(boundary, destination, point, artifact, existing)

    def test_recovery_arising_after_publication_retains_evidence_and_concurrent_bytes(self):
        for boundary in ("api", "cli"):
            for destination in ("local", "project"):
                for point in ("committed", "before_completion"):
                    for artifact in ("lock", "recovery", "unfinished", "conflict"):
                        for concurrent in (False, True):
                            with self.subTest(boundary=boundary, destination=destination, point=point,
                                              artifact=artifact, concurrent=concurrent):
                                self.cross_store_save(boundary, destination, point, artifact, True, concurrent)

    def test_paired_recovery_at_final_content_check_blocks_both_public_saves(self):
        for boundary in ("api", "cli"):
            for destination in ("local", "project"):
                for point in ("completion_entry", "completion_last_read"):
                    for artifact in ("lock", "recovery", "unfinished", "conflict"):
                        with self.subTest(boundary=boundary, destination=destination, point=point,
                                          artifact=artifact):
                            self.cross_store_save(boundary, destination, point, artifact, True)

    def test_final_check_recovery_preserves_concurrent_bytes_and_absent_previous(self):
        for boundary in ("api", "cli"):
            for destination in ("local", "project"):
                for point in ("completion_entry", "completion_last_read"):
                    for existing in (False, True):
                        with self.subTest(boundary=boundary, destination=destination, point=point,
                                          existing=existing):
                            self.cross_store_save(boundary, destination, point, "recovery", existing,
                                                  concurrent=True)

    def test_shared_save_boundary_guards_both_stores_before_mutation(self):
        local = Path(self.temporary.name) / "personal"
        service = self.personal_service(local)
        draft = service.reply(service.read(), "Expert")
        marker = self.project / ".playbook-config.recovery"
        marker.write_text("{}\n")
        with self.assertRaisesRegex(ConfigError, "reconcile"):
            service.preferences._save(draft["personal"]["after"], draft["personal"]["inputs"],
                                      draft["discovery"], create_directory=True)
        self.assertFalse(local.exists())
        self.assertFalse(service.lock.exists())
        marker.unlink()
        local.mkdir()
        (local / ".playbook-config.recovery").write_text("{}\n")
        with self.assertRaisesRegex(ConfigError, "reconcile"):
            service._save({"schema_version": 1, "adopted": True, "models": draft["after"]},
                          draft["inputs"], draft["discovery"])
        self.assertFalse(service.lock.exists())
        self.assertFalse(service.path.exists())
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_local_post_completion_edits_remain_valid_and_explanations_do_not_launch(self):
        local = Path(self.temporary.name) / "personal"
        service = self.personal_service(local)
        draft = service.reply(service.reply(service.read(), "Guided"), "Apply preference")
        self.assertEqual(draft["presentation"], "guided")
        (local / "preferences.json").write_text('{"schema_version":1,"presentation":"expert"}\n')
        self.assertEqual(service.read()["presentation"], "expert")
        result = service.reply(draft, "Apply")
        self.assertEqual(result["state"], "blocked")
        self.assertFalse((self.project / ".playbook-config.json").exists())


if __name__ == "__main__":
    unittest.main()

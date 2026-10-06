"""Public save identity and typed numeric recovery regressions."""
import json
import runpy
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from playbook_config import Configuration
import test_playbook_config_roles as fixtures


class RepairBoundaryTests(unittest.TestCase):
    setUp = fixtures.RoleConversationTests.setUp
    discover = fixtures.RoleConversationTests.discover

    def service_for(self, personal):
        return Configuration(self.project, self.discover, lambda: "2026-09-30T12:00:00Z",
                             preferences_dir=Path(self.temporary.name) / "personal" if personal else None,
                             context={"goal": "Known project", "billing": "unknown"})

    def cli(self, proposal, reply, personal, point=None):
        adapter = Path(self.temporary.name) / "adapter.py"
        adapter.write_text("import json,sys\nr=json.load(sys.stdin)\nprint(json.dumps(dict("
                           "request_id=r['request_id'],checked_at=r['started_at'],"
                           "authority='host-reported-selection',revision='fixture-1',routes="
                           + repr(self.routes) + ",coordinator=None)))\n")
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(self.project), "--now", "2026-09-30T12:00:00Z",
                   "--discovery-command", json.dumps([sys.executable, str(adapter)])]
        if personal:
            command += ["--preferences-dir", str(Path(self.temporary.name) / "personal")]
        if point:
            command = [sys.executable, __file__, "--move-wrapper", point, *command[1:]]
        result = subprocess.run([*command, "reply"], input=json.dumps({"proposal": proposal, "reply": reply}),
                                text=True, capture_output=True)
        self.assertEqual(result.stderr, "")
        response = json.loads(result.stdout)
        self.assertEqual(result.returncode, 2 if response["state"] in {"blocked", "recovery_required"} else 0)
        return response

    def assert_retained(self, result, proposal):
        self.assertIn(result["state"], ("blocked", "recovery_required"))
        self.assertEqual(result["retained_proposal"]["after"], proposal["after"])
        self.assertEqual(result["retained_proposal"]["proposal_revision"], proposal["proposal_revision"])

    def test_unpaired_directory_guard_keeps_private_paths_out_of_wire_proposals(self):
        service = self.service_for(False)
        proposal = service.read()
        for result in (proposal, self.cli(proposal, "Edit Build", False),
                       self.cli(proposal, "Choose ²", False)):
            wire = json.dumps(result)
            self.assertNotIn(str(self.project), wire)
            self.assertNotIn(str(self.project.resolve()), wire)
            self.assertNotIn(str(Path(self.temporary.name)), wire)
        self.assertEqual(service.reply(proposal, "Apply")["state"], "applied")
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_identical_replacement_after_preview_api_and_cli(self):
        for personal in (False, True):
            for surface in ("api", "cli"):
                with self.subTest(personal=personal, surface=surface):
                    self.setUp()
                    service = self.service_for(personal)
                    proposal = service.read()
                    original = self.project.with_name("displaced")
                    self.project.rename(original)
                    shutil.copytree(original, self.project)
                    result = service.reply(proposal, "Apply") if surface == "api" else self.cli(proposal, "Apply", personal)
                    self.assert_retained(result, proposal)
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                    self.assertEqual(list(self.project.glob(".playbook-config*")), [])
                    self.assertEqual(list(original.glob(".playbook-config*")), [])
                    shutil.rmtree(self.project)
                    original.rename(self.project)

    def test_directory_change_during_save_preserves_concurrent_bytes_and_locks(self):
        for personal in (False, True):
            for point in ("staged", "before_publish", "committed", "before_completion"):
                with self.subTest(personal=personal, point=point):
                    self.setUp()
                    service = self.service_for(personal)
                    proposal = service.read()
                    if personal:
                        proposal = service.reply(proposal, "Expert")  # Exercise paired project/personal publication.
                    original = self.project.with_name("displaced")
                    concurrent = b'{"concurrent":"retained"}\n'
                    def move(current):
                        if current == point:
                            self.project.rename(original)
                            shutil.copytree(original, self.project)
                            # External replacement has its own bytes and no owned transaction artifacts.
                            for path in self.project.glob(".playbook-config*"):
                                if path.is_dir():
                                    shutil.rmtree(path)
                                else:
                                    path.unlink()
                            (self.project / ".playbook-config.json").write_bytes(concurrent)
                    service.checkpoint = move
                    result = service.reply(proposal, "Apply")
                    self.assert_retained(result, proposal)
                    self.assertEqual((self.project / ".playbook-config.json").read_bytes(), concurrent)
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                    self.assertFalse((self.project / ".playbook-config.lock").exists())
                    if not personal and point in {"staged", "before_publish"}:
                        self.assertFalse((original / ".playbook-config.lock").exists())
                        self.assertEqual(list(original.glob(".playbook-config*")), [])
                    else:
                        self.assertEqual(result["state"], "recovery_required")
                        self.assertTrue((original / ".playbook-config.recovery").exists()
                                        or (original / ".playbook-config.pair").exists())
                    shutil.rmtree(self.project)
                    original.rename(self.project)
                    # Each case has an independent project and personal destination.
                    for path in self.project.glob(".playbook-config*"):
                        shutil.rmtree(path) if path.is_dir() else path.unlink()
                    local = Path(self.temporary.name) / "personal"
                    if local.exists():
                        shutil.rmtree(local)

    def test_completion_sealed_directory_change_requires_recovery(self):
        service = self.service_for(False)
        proposal = service.read()
        original = self.project.with_name("displaced")
        def move(point):
            if point == "completion_sealed":
                self.project.rename(original)
                self.project.mkdir()
                self.state.write_bytes(self.runtime)
                (self.project / ".playbook-config.json").write_bytes(b'concurrent')
        service.checkpoint = move
        result = service.reply(proposal, "Apply")
        self.assert_retained(result, proposal)
        self.assertEqual(result["state"], "recovery_required")
        self.assertEqual((self.project / ".playbook-config.json").read_bytes(), b'concurrent')
        self.assertTrue((original / ".playbook-config.recovery").exists())
        self.assertTrue((original / ".playbook-config.lock").exists())
        self.assertFalse((self.project / ".playbook-config.lock").exists())

    def test_cli_save_time_directory_changes_keep_replacement_bytes(self):
        for personal in (False, True):
            for point in ("staged", "committed", "completion_sealed"):
                with self.subTest(personal=personal, point=point):
                    self.setUp()
                    service = self.service_for(personal)
                    proposal = service.read()
                    if personal:
                        proposal = service.reply(proposal, "Expert")
                    result = self.cli(proposal, "Apply", personal, point)
                    self.assert_retained(result, proposal)
                    self.assertEqual((self.project / ".playbook-config.json").read_bytes(),
                                     b'{"concurrent":"retained"}\n')
                    original = self.project.with_name("displaced")
                    self.assertEqual((original / ".playbook-state.yml").read_bytes(), self.runtime)
                    self.assertFalse((self.project / ".playbook-config.lock").exists())
                    if not personal and point == "staged":
                        self.assertEqual(list(original.glob(".playbook-config*")), [])
                    else:
                        self.assertEqual(result["state"], "recovery_required")
                        self.assertTrue((original / ".playbook-config.recovery").exists()
                                        or (original / ".playbook-config.pair").exists())

    def test_project_open_operations_cannot_redirect_owned_files(self):
        for operation in ("lock", "stage", "publish"):
            with self.subTest(operation=operation):
                self.setUp()
                service = self.service_for(False)
                proposal = service.read()
                original = self.project.with_name("displaced")
                fired = False
                def move():
                    nonlocal fired
                    if not fired:
                        fired = True
                        self.project.rename(original)
                        self.project.mkdir()
                        self.state.write_bytes(self.runtime)
                        (self.project / ".playbook-config.json").write_bytes(b'concurrent')
                original_open = service._open
                def open_file(path, mode):
                    if (operation == "lock" and path == service.lock
                            or operation == "stage" and path.name.startswith(".playbook-config-")):
                        move()
                    return original_open(path, mode)
                original_link = service._link
                def link(source, destination):
                    if operation == "publish" and destination == service.path:
                        move()
                    return original_link(source, destination)
                service._open = open_file
                service._link = link
                result = service.reply(proposal, "Apply")
                self.assertTrue(fired)
                self.assert_retained(result, proposal)
                self.assertEqual((self.project / ".playbook-config.json").read_bytes(), b'concurrent')
                self.assertFalse((self.project / ".playbook-config.lock").exists())
                if operation != "publish":
                    self.assertEqual(list(original.glob(".playbook-config*")), [])
                else:
                    self.assertEqual(result["state"], "recovery_required")
                    self.assertTrue((original / ".playbook-config.recovery").exists())

    def test_alias_retarget_and_missing_project_require_new_preview(self):
        service = self.service_for(False)
        proposal = service.read()
        original = self.project.with_name("displaced")
        self.project.rename(original)
        self.assert_retained(service.reply(proposal, "Apply"), proposal)
        self.project.symlink_to(original, target_is_directory=True)
        self.assert_retained(service.reply(proposal, "Apply"), proposal)
        fresh = service.read()
        self.assertEqual(service.reply(fresh, "Apply")["state"], "applied")
        self.assertFalse((original / ".playbook-config.lock").exists())

    def test_numeric_errors_retain_every_nested_editor_api_and_cli(self):
        local = Path(self.temporary.name) / "personal"
        local.mkdir()
        personal_bytes = b'{"schema_version":1,"presentation":"guided","billing":"unknown"}\n'
        (local / "preferences.json").write_bytes(personal_bytes)
        service = self.service_for(True)
        base = service.read()
        role = service.reply(base, "Edit")
        edit = service.reply(base, "Edit Build")
        model = service.reply(edit, "Pick model")
        runner = service.reply(model, "1")
        reasoning = service.reply(runner, "1")
        skill = service.reply(base, "Edit skills alignment")
        # Two observed identities sharing model/runner/reasoning expose the final identity choice.
        self.routes[0]["provider"] = "fixture-one"
        self.routes.append({**self.routes[0], "provider": "fixture-two"})
        identity = service.reply(service.reply(service.reply(service.reply(service.reply(
            service.read(), "Edit Build"), "Pick model"), "1"), "1"), "1")
        self.assertEqual(identity["step"], "identity")
        for editor in (role, edit, model, runner, reasoning, identity, skill):
            for raw in ("²", "1" * 5000, "１２", "0", "-1", *(["1,²", "1," + "1" * 5000] if editor["step"] == "skill" else [])):
                for surface in ("api", "cli"):
                    with self.subTest(step=editor["step"], kind=raw if len(raw) < 10 else "oversize", surface=surface):
                        reply = "Choose " + raw if editor["step"] == "skill" else raw
                        result = service.reply(editor, reply) if surface == "api" else self.cli(editor, reply, True)
                        self.assert_retained(result, editor)
                        self.assertNotIn(str(self.temporary.name), result["message"])
                        self.assertNotIn(raw, result["message"])
                        self.assertEqual(service.reply(result, "Back")["after"], editor["after"])
        for editor in (role, edit, model, runner, reasoning, identity, skill):
            for raw in ("1", "１", "١", "0001"):
                reply = "Choose " + raw if editor["step"] == "skill" else raw
                for surface in ("api", "cli"):
                    result = service.reply(editor, reply) if surface == "api" else self.cli(editor, reply, True)
                    self.assertNotIn(result["state"], ("blocked", "recovery_required"))
        self.assertEqual(self.state.read_bytes(), self.runtime)
        self.assertEqual(self.approval.read_bytes(), b'{"approved":true}\n')
        self.assertFalse((self.project / ".playbook-config.json").exists())
        self.assertEqual((local / "preferences.json").read_bytes(), personal_bytes)
        self.assertEqual(list(local.iterdir()), [local / "preferences.json"])


if __name__ == "__main__" and sys.argv[1:2] == ["--move-wrapper"]:
    point = sys.argv[2]
    script = sys.argv[3]
    sys.argv = sys.argv[3:]
    original_init = Configuration.__init__
    def init(service, *args, **kwargs):
        original_init(service, *args, **kwargs)
        fired = False
        def move(current):
            nonlocal fired
            if current == point and not fired:
                fired = True
                project = service.project
                original = project.with_name("displaced")
                project.rename(original)
                project.mkdir()
                (project / ".playbook-state.yml").write_bytes((original / ".playbook-state.yml").read_bytes())
                (project / ".playbook-config.json").write_bytes(b'{"concurrent":"retained"}\n')
        service.checkpoint = move
    Configuration.__init__ = init
    runpy.run_path(script, run_name="__main__")

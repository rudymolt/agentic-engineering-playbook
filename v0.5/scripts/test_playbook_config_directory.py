"""Personal storage isolation through typed API and CLI conversations."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_playbook_config_roles as fixtures
from playbook_config import Configuration


def install_retarget(service, alias, target, point):
    fired = False

    def retarget():
        nonlocal fired
        if not fired:
            fired = True
            alias.unlink()
            alias.symlink_to(target, target_is_directory=True)

    service.preferences.checkpoint = lambda current: retarget() if current == point else None
    if point == "paired_project_staged":
        def project_checkpoint(current):
            if current == "staged":
                (alias / ".playbook-config.recovery").write_text("{}\n")
                retarget()

        service.checkpoint = project_checkpoint
    if point in {"lock_open", "stage_open"}:
        original = service.preferences._open

        def open_file(path, mode):
            if (point == "lock_open" and path == service.preferences.lock
                    or point == "stage_open" and path.name.startswith(".playbook-config-")):
                retarget()
            return original(path, mode)

        service.preferences._open = open_file
    if point == "publication_link":
        original = service.preferences._link

        def link(source, destination):
            if destination == service.preferences.path:
                retarget()
            return original(source, destination)

        service.preferences._link = link
    if point in {"journal_durable", "capture_durable", "receipt_durable"}:
        original = service.preferences._sync_directory

        def sync():
            original()
            store = service.preferences
            if (point == "journal_durable" and store._exists(store.recovery) and store._exists(store.path)
                    or point == "capture_durable" and store._exists(store.recovery) and not store._exists(store.path)
                    or point == "receipt_durable" and not store._exists(store.recovery)):
                retarget()

        service.preferences._sync_directory = sync
    if point == "seal_mkdir":
        original = service.preferences._mkdir

        def mkdir(path, exist_ok=False):
            if path.name.endswith(".complete"):
                retarget()
            return original(path, exist_ok=exist_ok)

        service.preferences._mkdir = mkdir


class PersonalDirectoryTests(unittest.TestCase):
    setUp = fixtures.RoleConversationTests.setUp
    discover = fixtures.RoleConversationTests.discover

    def conversation(self, surface, directory, project=None, fault=None):
        project = project or self.project
        context = {"goal": "Known project", "billing": "unknown"}
        service = Configuration(project, self.discover, lambda: "2026-09-30T12:00:00Z",
                                preferences_dir=directory, context=context)
        if surface == "api":
            if fault:
                install_retarget(service, *fault)
            return lambda proposal=None, reply=None: service.read() if proposal is None else service.reply(proposal, reply)
        adapter = Path(self.temporary.name) / "adapter.py"
        adapter.write_text(
            "import json,sys\nr=json.load(sys.stdin)\n"
            "print(json.dumps(dict(request_id=r['request_id'],checked_at=r['started_at'],"
            "authority='host-reported-selection',revision='fixture-1',routes=" + repr(self.routes) + ")))\n")
        command = [sys.executable, str(Path(__file__).with_name("configure-playbook.py")),
                   "--project", str(project), "--preferences-dir", str(directory),
                   "--now", "2026-09-30T12:00:00Z", "--discovery-command",
                   json.dumps([sys.executable, str(adapter)])]
        if fault:
            command = [sys.executable, __file__, "--fault-wrapper", json.dumps([str(value) for value in fault]), *command[1:]]

        def invoke(proposal=None, reply=None):
            request = {"context": context} if proposal is None else {"proposal": proposal, "reply": reply}
            result = subprocess.run([*command, "read" if proposal is None else "reply"],
                                    input=json.dumps(request), text=True, capture_output=True)
            response = json.loads(result.stdout)
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.returncode, 2 if response["state"] in {"blocked", "recovery_required"} else 0)
            return response

        return invoke

    def preview(self, invoke):
        draft = invoke(invoke(), "Edit Plan")
        draft = invoke(draft, "1")
        return invoke(draft, "Expert")

    def test_retarget_before_apply_keeps_draft_and_never_changes_destination(self):
        for surface in ("api", "cli"):
            for inside in (True, False):
                with self.subTest(surface=surface, inside=inside):
                    root = Path(self.temporary.name) / (surface + str(inside))
                    root.mkdir()
                    outside = root / "outside"
                    outside.mkdir()
                    target = (self.project if inside else root) / ("target-" + root.name)
                    target.mkdir()
                    alias = root / "alias"
                    alias.symlink_to(outside, target_is_directory=True)
                    invoke = self.conversation(surface, alias)
                    preview = self.preview(invoke)
                    alias.unlink()
                    alias.symlink_to(target, target_is_directory=True)
                    result = invoke(preview, "Apply preference")
                    self.assertIn(result["state"], ("blocked", "recovery_required"))
                    self.assertEqual(list(target.iterdir()), [])
                    self.assertEqual(list(outside.iterdir()), [])
                    self.assertEqual(result["retained_proposal"]["after"], preview["after"])
                    self.assertEqual(invoke(result, "Back")["after"], preview["after"])

    def test_retarget_at_save_checkpoints_keeps_artifacts_outside_project(self):
        for surface in ("api", "cli"):
            for point in ("staged", "before_replace", "journal_durable", "capture_durable",
                          "before_publish", "committed", "receipt_durable", "before_completion"):
                with self.subTest(surface=surface, point=point):
                    self.check_save_retarget(surface, point)

    def test_retarget_inside_storage_operations_uses_opened_directory(self):
        for surface in ("api", "cli"):
            for point in ("lock_open", "stage_open", "publication_link", "seal_mkdir"):
                with self.subTest(surface=surface, point=point):
                    self.check_save_retarget(surface, point)

    def check_save_retarget(self, surface, point):
        root = Path(self.temporary.name) / (surface + point)
        root.mkdir()
        outside = root / "outside"
        outside.mkdir()
        previous = b'{"schema_version":1,"presentation":"guided"}\n'
        (outside / "preferences.json").write_bytes(previous)
        target = self.project / root.name
        target.mkdir()
        alias = root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        invoke = self.conversation(surface, alias, fault=(alias, target, point))
        preview = self.preview(invoke)
        result = invoke(preview, "Apply preference")
        self.assertEqual(alias.resolve(), target)
        self.assertIn(result["state"], ("blocked", "recovery_required"))
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(result["retained_proposal"]["after"], preview["after"])
        self.assertEqual(self.state.read_bytes(), self.runtime)
        if point == "seal_mkdir":
            self.assertIn("Personal save completed at", result["message"])
            self.assertEqual(json.loads((outside / "preferences.json").read_text())["presentation"], "expert")
            self.assertTrue(list(outside.glob("*.receipt.complete")))
            self.assertFalse((outside / ".playbook-config.recovery").exists())
            self.assertFalse((outside / ".playbook-config.lock").exists())
        elif point in ("capture_durable", "before_publish", "committed", "receipt_durable", "before_completion", "publication_link"):
            self.assertEqual(result["state"], "recovery_required")
            marker = json.loads((outside / ".playbook-config.recovery").read_text())
            self.assertEqual((outside / marker["previous"]).read_bytes(), previous)
            self.assertEqual((outside / marker["captured"]).read_bytes(), previous)
            self.assertEqual(json.loads((outside / marker["attempted"]).read_text())["presentation"], "expert")
            alias.unlink()
            alias.symlink_to(outside, target_is_directory=True)
            self.assertEqual(invoke()["state"], "recovery_required")
        else:
            self.assertEqual((outside / "preferences.json").read_bytes(), previous)
            self.assertEqual(sorted(path.name for path in outside.iterdir()), ["preferences.json"])

    def test_normal_alias_and_new_nested_directory_save_outside_project(self):
        for surface in ("api", "cli"):
            root = Path(self.temporary.name) / surface
            root.mkdir()
            alias = Path(self.temporary.name) / (surface + "-alias")
            alias.symlink_to(root, target_is_directory=True)
            project_alias = Path(self.temporary.name) / (surface + "-project")
            project_alias.symlink_to(self.project, target_is_directory=True)
            for local in (alias, alias / "new" / "nested"):
                with self.subTest(surface=surface, local=local.name):
                    invoke = self.conversation(surface, local, project=project_alias)
                    preview = self.preview(invoke)
                    self.assertEqual(preview["personal"]["destination"], str(local / "preferences.json"))
                    self.assertEqual(preview["personal"]["resolved_destination"], str(local.resolve() / "preferences.json"))
                    result = invoke(preview, "Apply preference")
                    self.assertEqual(result["state"], "proposal_ready", result)
                    self.assertEqual(json.loads((local / "preferences.json").read_text())["presentation"], "expert")
                    self.assertEqual(invoke()["presentation"], "expert")
            self.assertEqual(sorted(path.name for path in self.project.iterdir()), [".playbook-state.yml", "approval.json"])

    def test_project_alias_retarget_requires_new_preview(self):
        for surface in ("api", "cli"):
            root = Path(self.temporary.name) / surface
            root.mkdir()
            outside = root / "personal"
            outside.mkdir()
            (root / ".playbook-state.yml").write_bytes(self.runtime)
            alias = Path(self.temporary.name) / (surface + "-project")
            alias.symlink_to(self.project, target_is_directory=True)
            invoke = self.conversation(surface, outside, project=alias)
            preview = self.preview(invoke)
            alias.unlink()
            alias.symlink_to(root, target_is_directory=True)
            result = invoke(preview, "Apply preference")
            self.assertIn(result["state"], ("blocked", "recovery_required"))
            self.assertEqual(list(outside.iterdir()), [])

    def test_same_path_replacement_requires_explicit_new_preview(self):
        for surface in ("api", "cli"):
            local = Path(self.temporary.name) / surface
            local.mkdir()
            invoke = self.conversation(surface, local)
            preview = self.preview(invoke)
            local.rename(local.with_name(surface + "-old"))
            local.mkdir()
            result = invoke(preview, "Apply preference")
            self.assertEqual(result["state"], "blocked")
            self.assertEqual(list(local.iterdir()), [])
            restored = invoke(result, "Back")
            self.assertIn("Directory identity changed", restored["message"])
            refreshed = invoke(restored, "Expert")
            self.assertEqual(refreshed["after"], preview["after"])
            self.assertEqual(invoke(refreshed, "Apply preference")["state"], "proposal_ready")

    def test_new_directory_creation_stays_at_reviewed_ancestor(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        target = self.project / "shared"
        target.mkdir()
        alias = Path(self.temporary.name) / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        invoke = self.conversation("api", alias / "new" / "nested")
        preview = self.preview(invoke)
        original = os.mkdir
        fired = False

        def mkdir(path, *args, **kwargs):
            nonlocal fired
            if not fired and path == "new":
                fired = True
                alias.unlink()
                alias.symlink_to(target, target_is_directory=True)
            return original(path, *args, **kwargs)

        with patch("playbook_config.os.mkdir", side_effect=mkdir):
            result = invoke(preview, "Apply preference")
        self.assertTrue(fired)
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(list(target.iterdir()), [])
        self.assertTrue((outside / "new" / "nested").is_dir())
        self.assertEqual(list(outside.rglob("preferences.json")), [])
        self.assertEqual(list(outside.rglob(".playbook-config*")), [])

    def test_exclusive_staging_failure_preserves_existing_file(self):
        local = Path(self.temporary.name) / "personal"
        local.mkdir()
        existing = local / ".playbook-config-collision"
        existing.write_bytes(b"external retained bytes\n")
        invoke = self.conversation("api", local)
        preview = self.preview(invoke)
        with patch("playbook_config.uuid.uuid4") as identifier:
            identifier.return_value.hex = "collision"
            result = invoke(preview, "Apply preference")
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(existing.read_bytes(), b"external retained bytes\n")
        self.assertEqual(sorted(path.name for path in local.iterdir()), [existing.name])

    def test_project_save_cannot_hide_paired_recovery_by_retargeting_alias(self):
        for surface in ("api", "cli"):
            root = Path(self.temporary.name) / surface
            root.mkdir()
            outside = root / "outside"
            outside.mkdir()
            (outside / "preferences.json").write_text('{"schema_version":1,"presentation":"guided"}\n')
            target = root / "replacement"
            target.mkdir()
            alias = root / "alias"
            alias.symlink_to(outside, target_is_directory=True)
            invoke = self.conversation(surface, alias, fault=(alias, target, "paired_project_staged"))
            draft = invoke(invoke(invoke(), "Edit Plan"), "1")
            result = invoke(draft, "Apply")
            self.assertEqual(alias.resolve(), target)
            self.assertIn(result["state"], ("blocked", "recovery_required"))
            self.assertEqual(result["retained_proposal"]["after"], draft["after"])
            self.assertTrue((outside / ".playbook-config.recovery").exists())
            self.assertFalse((self.project / ".playbook-config.json").exists())
            self.assertEqual(list(target.iterdir()), [])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fault-wrapper":
        alias, target, point = json.loads(sys.argv[2])
        original = Configuration.__init__

        def initialize(self, *args, **kwargs):
            original(self, *args, **kwargs)
            if self.preferences is not None:
                install_retarget(self, Path(alias), Path(target), point)

        Configuration.__init__ = initialize
        sys.argv = sys.argv[3:]
        runpy.run_path(sys.argv[0], run_name="__main__")
    else:
        unittest.main()

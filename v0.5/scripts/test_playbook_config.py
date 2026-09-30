"""Temporary-project tests at the public configuration boundary."""

import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import Mock, patch

from playbook_config import Configuration, ConfigError


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.state = self.project / ".playbook-state.yml"
        self.state.write_text(
            "schema_version: 3\nmodel_routing:\n  policy: gated\n"
            "  defaults:\n"
            "    planning: { model_id: custom-plan, runner: cursor, reasoning: max }\n"
            "    implementation: { model_id: custom-build, runner: opencode, reasoning: low }\n"
            "    verification: { model_id: custom-verify, runner: claude-code, reasoning: high }\n"
            "    escalated_repair: { model_id: custom-repair, runner: codex, reasoning: xhigh, trigger_unsuccessful_repairs: 5, cycles_per_slice: 1, scope: approved_slice, authority: diagnose_and_implement }\n"
            "  allowed_runners: [codex, cursor, opencode, claude-code]\n"
            "pending_model_routes: [{route_id: keep-me, status: selected}]\n"
            "active_features: [{slug: active, routing: immutable}]\n"
            "last_run: {history: untouched}\n"
        )
        self.runtime = self.state.read_bytes()
        self.approval = self.project / "approval.json"
        self.approval.write_bytes(b'{"routes":{"build":{"model":"approved","effort":"high"}}}\n')
        self.discovery = {
            "revision": "fixture-1",
            "checked_at": "2026-09-29T12:00:00Z",
            "authority": "host-reported-selection",
            "routes": [{"model_id": "available-build", "runner": "codex", "reasoning": "medium", "roles": ["implementation"]}],
        }
        self.service = Configuration(self.project, self.discover, lambda: "2026-09-29T12:00:00Z")

    def discover(self, request):
        return {**self.discovery, "request_id": request["request_id"], "checked_at": request["started_at"]}

    def test_typed_edit_adopts_all_roles_and_next_lane_reads_it(self):
        proposal = self.service.read()
        self.assertEqual(proposal["state"], "decision_required")
        self.assertEqual(proposal["origin"], "legacy project")
        self.assertEqual(proposal["before"]["implementation"]["runner"], "opencode")
        editor = self.service.reply(proposal, "edit Build")
        preview = self.service.reply(editor, "1")
        self.assertEqual(preview["state"], "proposal_ready")
        self.assertEqual(preview["destination"], ".playbook-config.json")
        self.assertTrue(preview["migration"])
        self.assertEqual(preview["after"]["planning"], {"model_id": "custom-plan", "runner": "cursor", "reasoning": "max"})
        self.assertEqual(preview["after"]["escalated_repair"]["trigger_unsuccessful_repairs"], 5)
        self.assertEqual(self.service.reply(preview, "Not now")["state"], "unchanged")
        self.assertFalse((self.project / ".playbook-config.json").exists())
        applied = self.service.reply(preview, "Apply")
        self.assertEqual(applied["state"], "applied")
        self.assertFalse(applied["launched"])
        self.assertEqual(self.service.resolve("implementation"), {
            "origin": "adopted project", "choice": {"model_id": "available-build", "runner": "codex", "reasoning": "medium"},
        })
        self.assertEqual(self.service.resolve("implementation", {"model_id": "approved", "runner": "cursor", "reasoning": "high"})["origin"], "feature")
        saved = (self.project / ".playbook-config.json").read_bytes()
        self.assertEqual(json.loads(saved)["schema_version"], 1)
        self.assertEqual(self.service.reply(self.service.read(), "Apply")["state"], "unchanged")
        self.assertEqual((self.project / ".playbook-config.json").read_bytes(), saved)
        self.assertEqual(self.state.read_bytes(), self.runtime)
        self.assertEqual(self.approval.read_bytes(), b'{"routes":{"build":{"model":"approved","effort":"high"}}}\n')

    def preview(self):
        return self.service.reply(self.service.reply(self.service.read(), "Edit Build"), "1")

    def test_invalid_duplicate_and_newer_adoption_never_falls_back(self):
        for contents in ('{', '{"schema_version":1,"schema_version":1}', '{"schema_version":2}', '{"schema_version":true}', '{"schema_version":1,"adopted":false,"models":{}}'):
            with self.subTest(contents=contents):
                destination = self.project / ".playbook-config.json"
                destination.write_text(contents)
                self.assertEqual(self.service.read()["state"], "blocked")
                with self.assertRaises(ConfigError):
                    self.service.resolve("implementation")
                self.assertEqual(destination.read_text(), contents)

    def test_invalid_and_duplicate_legacy_preferences_block_adoption(self):
        for contents in (
            self.runtime.decode().replace("model_routing:\n", "model_routing:\nmodel_routing:\n"),
            self.runtime.decode().replace("runner: opencode", "runner: opencode, runner: codex"),
            self.runtime.decode().replace("model_id: custom-build", "model_id: null"),
            self.runtime.decode().replace("    verification:", "    unknown_role:"),
            self.runtime.decode().replace("cycles_per_slice: 1", "cycles_per_slice: false"),
        ):
            with self.subTest(contents=contents):
                self.state.write_text(contents)
                self.assertEqual(self.service.read()["state"], "blocked")
                self.assertFalse((self.project / ".playbook-config.json").exists())

    def test_block_mapping_import_and_per_role_origins(self):
        self.state.write_text("model_routing:\n  defaults:\n    implementation:\n      model_id: custom-build\n      runner: opencode\n      reasoning: low\n")
        proposal = self.service.read()
        self.assertEqual(proposal["origins"]["implementation"], "legacy project")
        self.assertEqual(proposal["origins"]["planning"], "edition")
        self.assertEqual(proposal["before"]["implementation"]["model_id"], "custom-build")

    def test_availability_change_blocks_apply_and_explains_edit_route(self):
        proposal = self.preview()
        self.discovery["routes"] = []
        result = self.service.reply(proposal, "Apply")
        self.assertEqual(result["state"], "blocked")
        self.assertIn("unavailable", result["message"])
        self.assertIn("Edit Build", result["choices"])
        self.assertFalse((self.project / ".playbook-config.json").exists())
        self.assertEqual(self.state.read_bytes(), self.runtime)

    def test_discovery_authority_and_freshness_and_duplicate_routes(self):
        for update in (
            {"authority": "model-self-description"},
            {"checked_at": "2026-09-27T12:00:00Z"},
            {"checked_at": "2026-09-30T12:00:00Z"},
            {"routes": self.discovery["routes"] * 2},
            {"routes": [{"model_id": "x; execute", "runner": "codex", "reasoning": "high", "roles": ["implementation"]}]},
        ):
            with self.subTest(update=update):
                service = Configuration(self.project, lambda request: {**self.discover(request), **update}, self.service.clock)
                self.assertEqual(service.read()["state"], "blocked")

    def test_concurrent_state_config_and_discovery_inputs_require_new_preview(self):
        for changed in ("state", "config", "discovery", "refreshed_check_time"):
            with self.subTest(changed=changed):
                self.setUp()
                self.service.clock = lambda: "2026-09-29T12:05:00Z"
                proposal = self.preview()
                if changed == "state":
                    self.state.write_bytes(self.runtime + b"other: concurrent\n")
                elif changed == "config":
                    (self.project / ".playbook-config.json").write_text('{"schema_version":2}')
                elif changed == "discovery":
                    self.discovery["revision"] = "fixture-2"
                else:
                    self.discovery["checked_at"] = "2026-09-29T12:01:00Z"
                before = {path.name: path.read_bytes() for path in self.project.iterdir()}
                result = self.service.reply(proposal, "Apply")
                if changed == "refreshed_check_time":
                    self.assertEqual(result["state"], "applied")
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                else:
                    self.assertEqual(result["state"], "blocked")
                    self.assertEqual({path.name: path.read_bytes() for path in self.project.iterdir()}, before)

    def test_tampered_proposal_and_role_constraints_are_rejected(self):
        for mutation in ("planning", "implementation"):
            with self.subTest(mutation=mutation):
                proposal = self.preview()
                proposal["after"][mutation]["cycles_per_slice"] = 99
                self.assertEqual(self.service.apply(proposal)["state"], "blocked")
                self.assertFalse((self.project / ".playbook-config.json").exists())

    def test_stage_commit_validation_and_rollback_failures(self):
        for failure in ("staged", "before_replace", "committed"):
            for adopted in (False, True):
                with self.subTest(failure=failure, adopted=adopted):
                    self.setUp()
                    if adopted:
                        self.assertEqual(self.service.apply(self.preview())["state"], "applied")
                    destination = self.project / ".playbook-config.json"
                    original = destination.read_bytes() if adopted else None

                    def checkpoint(point):
                        if point == failure:
                            raise OSError("injected " + failure)

                    service = Configuration(self.project, self.discover, self.service.clock, checkpoint=checkpoint)
                    proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
                    if adopted:
                        self.discovery["routes"].append({"model_id": "second-build", "runner": "cursor", "reasoning": "max", "roles": ["implementation"]})
                        proposal = service.reply(service.reply(service.read(), "Edit Build"), "2")
                    result = service.apply(proposal)
                    self.assertEqual(result["state"], "recovery_required" if failure == "committed" else "blocked")
                    self.assertIn("injected", result["message"])
                    if failure != "committed":
                        self.assertEqual(destination.read_bytes() if destination.exists() else None, original)
                    else:
                        marker = json.loads((self.project / ".playbook-config.recovery").read_text())
                        retained = (self.project / marker["previous"]).read_bytes() if marker["previous"] else None
                        self.assertEqual(retained, original)
                    self.assertEqual(self.state.read_bytes(), self.runtime)
                    self.assertEqual((self.project / ".playbook-config.lock").exists(), failure == "committed")

    def test_failed_rollback_blocks_readers_and_retains_recoverable_previous_bytes(self):
        self.assertEqual(self.service.apply(self.preview())["state"], "applied")
        previous = (self.project / ".playbook-config.json").read_bytes()
        self.discovery["routes"].append({"model_id": "second-build", "runner": "cursor", "reasoning": "max", "roles": ["implementation"]})

        def checkpoint(point):
            if point in {"committed", "rollback"}:
                raise OSError("injected " + point)

        service = Configuration(self.project, self.discover, self.service.clock, checkpoint=checkpoint)
        proposal = service.reply(service.reply(service.read(), "Edit Build"), "2")
        self.assertEqual(service.apply(proposal)["state"], "recovery_required")
        self.assertEqual(service.read()["state"], "recovery_required")
        with self.assertRaises(ConfigError):
            service.resolve("implementation")
        marker = json.loads((self.project / ".playbook-config.recovery").read_text())
        self.assertEqual((self.project / marker["previous"]).read_bytes(), previous)

    def test_concurrent_edit_during_failure_is_not_overwritten(self):
        concurrent = b'{"schema_version":2,"concurrent":true}\n'

        def checkpoint(point):
            if point == "committed":
                (self.project / ".playbook-config.json").write_bytes(concurrent)
                raise OSError("injected concurrent edit")

        service = Configuration(self.project, self.discover, self.service.clock, checkpoint=checkpoint)
        proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
        self.assertEqual(service.apply(proposal)["state"], "recovery_required")
        self.assertEqual((self.project / ".playbook-config.json").read_bytes(), concurrent)

    def test_concurrent_change_immediately_before_commit_is_not_overwritten(self):
        concurrent = b'{"schema_version":2}\n'

        def checkpoint(point):
            if point == "before_replace":
                (self.project / ".playbook-config.json").write_bytes(concurrent)

        service = Configuration(self.project, self.discover, self.service.clock, checkpoint=checkpoint)
        self.assertEqual(service.apply(self.preview())["state"], "blocked")
        self.assertEqual((self.project / ".playbook-config.json").read_bytes(), concurrent)

    def test_lock_excludes_another_editor_and_preference_reader(self):
        (self.project / ".playbook-config.lock").write_text("other transaction")
        self.assertEqual(self.service.read()["state"], "blocked")
        with self.assertRaises(ConfigError):
            self.service.resolve("implementation")
        self.assertEqual((self.project / ".playbook-config.lock").read_text(), "other transaction")

    def test_external_edit_in_final_discovery_never_reports_applied(self):
        for adopted in (False, True):
            with self.subTest(adopted=adopted):
                self.setUp()
                if adopted:
                    self.service.apply(self.preview())
                    self.discovery["routes"][0]["model_id"] = "next-build"
                previous = self.service.path.read_bytes() if adopted else None
                external = json.dumps({"schema_version": 1, "adopted": True, "models": self.service.read()["before"]}).encode()
                calls = 0

                def discover(request):
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        self.service.path.write_bytes(external)
                    return self.discover(request)

                service = Configuration(self.project, discover, self.service.clock)
                proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
                result = service.apply(proposal)
                self.assertNotEqual(result["state"], "applied")
                self.assertEqual(service.path.read_bytes(), external)
                if adopted:
                    self.assertEqual(result["state"], "recovery_required")
                    self.assertEqual(service.read()["state"], "recovery_required")
                    marker = json.loads(service.recovery.read_text())
                    self.assertEqual((self.project / marker["previous"]).read_bytes(), previous)
                    self.assertEqual((self.project / marker["captured"]).read_bytes(), external)

    def test_external_edit_at_publication_is_not_clobbered(self):
        for adopted in (False, True):
            with self.subTest(adopted=adopted):
                self.setUp()
                if adopted:
                    self.service.apply(self.preview())
                    self.discovery["routes"][0]["model_id"] = "next-build"
                external = b'{"external": "publication-window"}\n'

                def checkpoint(point):
                    if point == "before_publish":
                        self.service.path.write_bytes(external)

                service = Configuration(self.project, self.discover, self.service.clock, checkpoint)
                proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
                self.assertNotEqual(service.apply(proposal)["state"], "applied")
                self.assertEqual(service.path.read_bytes(), external)

    def test_post_commit_recovery_observation_cannot_destroy_external_edits(self):
        for adopted in (False, True):
            with self.subTest(adopted=adopted):
                self.setUp()
                if adopted:
                    self.service.apply(self.preview())
                    self.discovery["routes"][0]["model_id"] = "next-build"
                previous = self.service.path.read_bytes() if adopted else None
                rolling_back = False
                external = b'{"external": "rollback-window"}\n'

                def checkpoint(point):
                    nonlocal rolling_back
                    if point == "committed":
                        raise OSError("post-commit failure")
                    if point == "rollback":
                        rolling_back = True

                service = Configuration(self.project, self.discover, self.service.clock, checkpoint)
                original_bytes = service._bytes

                def observe(path):
                    nonlocal rolling_back
                    observed = original_bytes(path)
                    if rolling_back and path == service.path:
                        rolling_back = False
                        path.write_bytes(external)
                    return observed

                service._bytes = observe
                proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
                self.assertEqual(service.apply(proposal)["state"], "recovery_required")
                self.assertEqual(service.path.read_bytes(), external)
                marker = json.loads(service.recovery.read_text())
                retained = (self.project / marker["previous"]).read_bytes() if marker["previous"] else None
                self.assertEqual(retained, previous)
                self.assertTrue((self.project / marker["attempted"]).exists())
                self.assertEqual(service.read()["state"], "recovery_required")
                with self.assertRaises(ConfigError):
                    service.resolve("implementation")

    def test_open_external_writer_keeps_its_captured_inode_and_receipt(self):
        self.service.apply(self.preview())
        self.discovery["routes"][0]["model_id"] = "next-build"
        with self.service.path.open("r+b") as external_stream:
            def checkpoint(point):
                if point == "committed":
                    external_stream.write(b"external retained inode")
                    external_stream.flush()

            service = Configuration(self.project, self.discover, self.service.clock, checkpoint)
            proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
            result = service.apply(proposal)
            self.assertEqual(result["state"], "recovery_required")
            marker = json.loads(service.recovery.read_text())
            self.assertTrue((self.project / marker["captured"]).read_bytes().startswith(b"external retained inode"))

    def test_completed_receipt_retains_inodes_for_late_external_writers(self):
        self.service.apply(self.preview())
        self.discovery["routes"][0]["model_id"] = "next-build"
        with self.service.path.open("r+b") as external_stream:
            self.assertEqual(self.service.apply(self.preview())["state"], "applied")
            external_stream.write(b"late external edit")
            external_stream.flush()
        receipts = [json.loads(path.read_text()) for path in self.project.glob(".playbook-config-*.receipt")]
        latest = next(receipt for receipt in receipts if receipt["previous"] is not None)
        self.assertTrue((self.project / latest["captured"]).read_bytes().startswith(b"late external edit"))
        self.assertTrue((self.project / latest["attempted"]).exists())
        self.assertEqual(self.service.resolve("implementation")["choice"]["model_id"], "next-build")

    def test_completion_promotion_conflicts_retain_evidence_and_block_all_readers(self):
        for adopted, captured_writer in ((False, False), (True, False), (True, True)):
            with self.subTest(adopted=adopted, captured_writer=captured_writer):
                self.setUp()
                if adopted:
                    self.assertEqual(self.service.apply(self.preview())["state"], "applied")
                    self.discovery["routes"][0]["model_id"] = "next-build"
                previous = self.service.path.read_bytes() if adopted else None
                proposal = self.preview()
                attempted = json.dumps({"schema_version": 1, "adopted": True, "models": proposal["after"]}, indent=2, sort_keys=True).encode() + b"\n"
                external = json.loads(previous) if adopted else json.loads(json.dumps({"schema_version": 1, "adopted": True, "models": proposal["before"]}))
                external["models"]["implementation"]["model_id"] = "external-build"
                external_bytes = json.dumps(external).encode()
                writer = self.service.path.open("r+b") if captured_writer else None
                if writer:
                    self.addCleanup(writer.close)
                original_replace = os.replace

                def replace(source, destination):
                    if source == self.service.recovery:
                        if writer:
                            writer.seek(0)
                            writer.write(external_bytes)
                            writer.truncate()
                            writer.flush()
                            os.fsync(writer.fileno())
                        else:
                            self.service.path.write_bytes(external_bytes)
                    return original_replace(source, destination)

                with patch("playbook_config.os.replace", side_effect=replace):
                    result = self.service.apply(proposal)
                self.assertEqual(result["state"], "recovery_required")
                marker = json.loads(self.service.recovery.read_text())
                self.assertEqual((self.project / marker["attempted"]).read_bytes(), attempted)
                if adopted:
                    self.assertEqual((self.project / marker["previous"]).read_bytes(), previous)
                    self.assertEqual((self.project / marker["captured"]).read_bytes(), external_bytes if writer else previous)
                if not writer:
                    self.assertEqual(self.service.path.read_bytes(), external_bytes)
                self.service.recovery.unlink()
                self.service.lock.unlink()
                self.assertEqual(self.service.read()["state"], "recovery_required")
                for role in ("planning", "implementation", "verification", "escalated_repair"):
                    with self.assertRaises(ConfigError):
                        self.service.resolve(role)
                fresh = Configuration(self.project, self.discover, self.service.clock)
                self.assertEqual(fresh.read()["state"], "recovery_required")
                result = subprocess.run([sys.executable, str(Path(__file__).with_name("configure-playbook.py")), "--project", str(self.project), "resolve"],
                                        input='{"role":"implementation"}', text=True, capture_output=True)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(json.loads(result.stdout)["state"], "recovery_required")

    def test_completion_seal_is_the_boundary_not_journal_promotion(self):
        for point in ("before_seal", "after_seal"):
            with self.subTest(point=point):
                self.setUp()
                proposal = self.preview()
                external = json.loads(json.dumps({"schema_version": 1, "adopted": True, "models": proposal["after"]}))
                external["models"]["implementation"]["model_id"] = "future-build"
                external_bytes = json.dumps(external).encode()
                original_mkdir = Path.mkdir
                original_barrier = self.service._completion_clock_barrier

                def mkdir(path, *args, **kwargs):
                    if path.name.endswith(".receipt.complete") and point == "before_seal":
                        self.service.path.write_bytes(external_bytes)
                    return original_mkdir(path, *args, **kwargs)

                def barrier(seal):
                    original_barrier(seal)
                    if point == "after_seal":
                        self.service.path.write_bytes(external_bytes)

                with patch("playbook_config.Path.mkdir", new=mkdir), patch.object(self.service, "_completion_clock_barrier", side_effect=barrier):
                    result = self.service.apply(proposal)
                self.assertEqual(self.service.path.read_bytes(), external_bytes)
                self.assertEqual(result["state"], "recovery_required" if point == "before_seal" else "applied")
                if point == "after_seal":
                    self.assertEqual(self.service.resolve("implementation")["choice"]["model_id"], "future-build")
                else:
                    self.service.recovery.unlink()
                    self.service.lock.unlink()
                    self.assertEqual(self.service.read()["state"], "recovery_required")

    def test_pending_receipt_without_markers_and_legacy_receipt_conflict_are_actionable(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                self.setUp()
                self.assertEqual(self.service.apply(self.preview())["state"], "applied")
                receipt = next(self.project.glob(".playbook-config-*.receipt"))
                marker = json.loads(receipt.read_text())
                receipt.with_name(receipt.name + ".complete").rmdir()
                if legacy:
                    self.service.path.write_bytes(b"external before legacy promotion")
                    marker.pop("completion_protocol")
                    receipt.write_text(json.dumps(marker))
                self.assertEqual(self.service.read()["state"], "recovery_required")
                with self.assertRaises(ConfigError):
                    self.service.resolve("implementation")

    def test_legitimate_edits_after_completed_apply_do_not_poison_future_reads(self):
        self.assertEqual(self.service.apply(self.preview())["state"], "applied")
        edited = json.loads(self.service.path.read_text())
        edited["models"]["implementation"]["model_id"] = "external-future-build"
        self.service.path.write_text(json.dumps(edited))
        self.assertEqual(self.service.resolve("implementation")["choice"]["model_id"], "external-future-build")
        self.assertEqual(self.service.apply(self.preview())["state"], "applied")
        self.assertEqual(self.service.resolve("implementation")["choice"]["model_id"], "available-build")

    def test_legacy_completed_receipt_captured_conflict_is_not_ignored(self):
        self.assertEqual(self.service.apply(self.preview())["state"], "applied")
        self.discovery["routes"][0]["model_id"] = "next-build"
        with self.service.path.open("r+b") as writer:
            self.assertEqual(self.service.apply(self.preview())["state"], "applied")
            receipt = next(path for path in self.project.glob(".playbook-config-*.receipt") if json.loads(path.read_text())["captured"])
            marker = json.loads(receipt.read_text())
            writer.write(b"unresolved legacy captured choice")
            writer.flush()
            os.fsync(writer.fileno())
            marker.pop("completion_protocol")
            receipt.write_text(json.dumps(marker))
            receipt.with_name(receipt.name + ".complete").rmdir()
        self.assertEqual(self.service.read()["state"], "recovery_required")
        with self.assertRaises(ConfigError):
            self.service.resolve("implementation")

    def test_directory_sync_failure_after_seal_stays_unresolved_without_lock(self):
        original_sync = self.service._sync_directory

        def sync():
            if list(self.project.glob(".playbook-config-*.receipt.complete")):
                raise OSError("injected completion durability failure")
            original_sync()

        proposal = self.preview()
        with patch.object(self.service, "_sync_directory", side_effect=sync):
            self.assertEqual(self.service.apply(proposal)["state"], "recovery_required")
        self.service.recovery.unlink()
        self.service.lock.unlink()
        self.assertEqual(self.service.read()["state"], "recovery_required")
        with self.assertRaises(ConfigError):
            self.service.resolve("implementation")

    def test_nonadvancing_completion_clock_cannot_certify_success(self):
        original_stage = self.service._stage
        probe = Mock()
        probe.stat.return_value.st_ctime_ns = 0

        def stage(contents):
            return probe if contents == b"" else original_stage(contents)

        proposal = self.preview()
        with patch.object(self.service, "_stage", side_effect=stage), patch("playbook_config.os.utime"), patch("playbook_config.time.sleep"):
            self.assertEqual(self.service.apply(proposal)["state"], "recovery_required")
        self.service.recovery.unlink()
        self.service.lock.unlink()
        self.assertEqual(self.service.read()["state"], "recovery_required")

    def test_displaced_publication_open_inode_write_is_also_a_completion_conflict(self):
        writer = None
        proposal = self.preview()
        original_replace = os.replace

        def checkpoint(point):
            nonlocal writer
            if point == "committed":
                writer = self.service.path.open("r+b")
                self.addCleanup(writer.close)

        def replace(source, destination):
            if source == self.service.recovery:
                expected = self.service.path.read_bytes()
                displaced = self.project / "external-displaced.json"
                original_replace(self.service.path, displaced)
                self.service.path.write_bytes(expected)
                writer.seek(0)
                writer.write(b"external displaced publication choice")
                writer.truncate()
                writer.flush()
                os.fsync(writer.fileno())
            return original_replace(source, destination)

        self.service.checkpoint = checkpoint
        with patch("playbook_config.os.replace", side_effect=replace):
            self.assertEqual(self.service.apply(proposal)["state"], "recovery_required")
        marker = json.loads(self.service.recovery.read_text())
        self.assertEqual((self.project / marker["published"]).read_bytes(), b"external displaced publication choice")
        self.assertEqual((self.project / marker["attempted"]).read_bytes(), self.service.path.read_bytes())
        self.assertEqual(self.service.read()["state"], "recovery_required")

    def test_readers_reject_the_capture_publication_gap(self):
        self.service.apply(self.preview())
        self.discovery["routes"][0]["model_id"] = "next-build"

        def checkpoint(point):
            if point == "before_publish":
                self.assertFalse(self.service.path.exists())
                self.assertEqual(self.service.read()["state"], "recovery_required")
                with self.assertRaises(ConfigError):
                    self.service.resolve("implementation")

        service = Configuration(self.project, self.discover, self.service.clock, checkpoint)
        proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
        self.assertEqual(service.apply(proposal)["state"], "applied")

    def test_receipt_sync_failure_restores_durable_recovery_evidence(self):
        self.service.apply(self.preview())
        self.discovery["routes"][0]["model_id"] = "next-build"
        original_sync = self.service._sync_directory

        def sync():
            if not self.service.recovery.exists() and self.service.lock.exists():
                raise OSError("receipt sync failure")
            original_sync()

        proposal = self.preview()
        with patch.object(self.service, "_sync_directory", side_effect=sync):
            self.assertEqual(self.service.apply(proposal)["state"], "recovery_required")
        marker = json.loads(self.service.recovery.read_text())
        self.assertTrue((self.project / marker["previous"]).exists())
        self.assertTrue((self.project / marker["attempted"]).exists())
        self.assertEqual(self.service.read()["state"], "recovery_required")

    def test_external_edit_after_observation_is_atomically_captured(self):
        self.service.apply(self.preview())
        self.discovery["routes"][0]["model_id"] = "next-build"
        external = b'{"external": "capture-window"}\n'
        original_replace = os.replace

        def replace(source, destination):
            if source == self.service.path:
                source.write_bytes(external)
            return original_replace(source, destination)

        proposal = self.preview()
        with patch("playbook_config.os.replace", side_effect=replace):
            self.assertEqual(self.service.apply(proposal)["state"], "recovery_required")
        self.assertEqual(self.service.path.read_bytes(), external)

    def test_cached_discovery_and_replayed_response_are_not_current_access(self):
        for cached_at in ("2026-09-28T13:00:00Z", "2026-09-29T11:59:59Z"):
            service = Configuration(self.project, lambda request: {**self.discover(request), "checked_at": cached_at}, self.service.clock)
            self.assertEqual(service.read()["state"], "blocked")
        captured = None

        def replay(request):
            nonlocal captured
            if captured is None:
                captured = self.discover(request)
            return captured

        service = Configuration(self.project, replay, self.service.clock)
        proposal = service.reply(service.reply(service.read(), "Edit Build"), "1")
        self.assertEqual(service.apply(proposal)["state"], "blocked")
        self.assertFalse(service.path.exists())

    def test_discovery_contract_bounds_each_observation_with_clock(self):
        ticks = iter(("2026-09-29T12:00:00Z", "2026-09-29T12:00:02Z"))

        def discover(request):
            self.assertEqual(request["purpose"], "current-availability")
            self.assertEqual(request["roles"], ["planning", "implementation", "verification", "escalated_repair"])
            return {**self.discover(request), "checked_at": "2026-09-29T12:00:01Z"}

        service = Configuration(self.project, discover, lambda: next(ticks))
        self.assertEqual(service.read()["state"], "decision_required")

    def test_file_only_helper_refuses_cached_availability(self):
        discovery_file = self.project / "discovery.json"
        discovery_file.write_text(json.dumps(self.discovery))
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("configure-playbook.py")), "--project", str(self.project), "--discovery", str(discovery_file), "read"], input="{}", text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("fresh authoritative recheck", json.loads(result.stdout)["message"])

    def test_edition_and_explicit_feature_precedence_without_launch(self):
        self.state.unlink()
        self.assertEqual(self.service.resolve("implementation")["choice"]["model_id"], "gpt-6.1-sol")
        self.assertEqual(self.service.resolve("implementation")["origin"], "edition")
        self.assertEqual(self.service.resolve("implementation", {"model_id": "override", "runner": "opencode", "reasoning": "max"})["choice"]["model_id"], "override")

    def test_command_chat_demo_and_existing_router_reader(self):
        helper = Path(__file__).with_name("configure-playbook.py")
        discovery_file = self.project / "discovery.json"
        discovery_file.write_text(json.dumps(self.discovery))
        adapter = self.project / "adapter.py"
        adapter.write_text("import json, sys\nfrom pathlib import Path\nrequest = json.load(sys.stdin)\nevidence = json.loads(Path(sys.argv[1]).read_text())\nevidence.update(request_id=request['request_id'], checked_at=request['started_at'])\nprint(json.dumps(evidence))\n")

        def command(action, payload=None):
            result = subprocess.run([sys.executable, str(helper), "--project", str(self.project), "--discovery-command", json.dumps([sys.executable, str(adapter), str(discovery_file)]), "--now", "2026-09-29T12:00:00Z", action], input=json.dumps(payload or {}), text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)

        proposal = command("read")
        editor = command("reply", {"proposal": proposal, "reply": "Edit Build"})
        preview = command("reply", {"proposal": editor, "reply": "1"})
        self.assertEqual(command("reply", {"proposal": preview, "reply": "Apply"})["state"], "applied")
        self.assertEqual(command("resolve", {"role": "implementation"})["choice"]["model_id"], "available-build")
        discovery_file.unlink()
        result = subprocess.run([sys.executable, str(helper), "--project", str(self.project), "resolve"], input='{"role":"implementation"}', text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["origin"], "adopted project")


if __name__ == "__main__":
    unittest.main()

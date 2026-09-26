from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


PACK = Path(__file__).resolve().parents[1]
LINUX = sys.platform.startswith("linux")


def load_monitor_module():
    path = PACK / "skill" / "scripts" / "checker-monitor.py"
    spec = importlib.util.spec_from_file_location("checker_monitor_under_test", path)
    if spec is None or spec.loader is None:
        raise AssertionError("unable to load checker monitor")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CheckerMonitorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repository)], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.name", "Checker Test"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "config", "user.email", "checker@example.com"], check=True)
        (self.repository / "tracked.txt").write_text("frozen\n")
        subprocess.run(["git", "-C", str(self.repository), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repository), "commit", "-qm", "frozen"], check=True)
        self.script = self.root / "checker-monitor.py"
        shutil.copyfile(PACK / "skill" / "scripts" / "checker-monitor.py", self.script)
        self.wrapper = PACK / "skill" / "scripts" / "checker-python.py"
        self.script.chmod(0o600)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_monitor(self, *args: str, expected: int = 0) -> dict[str, object]:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, str(self.wrapper), str(self.script), *args],
            text=True,
            capture_output=True,
            env=env,
            timeout=15,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        self.assertEqual("", result.stderr)
        return json.loads(result.stdout)

    @unittest.skipUnless(LINUX, "Launcher V4 monitor requires Linux inotify")
    def test_non_executable_helper_starts_only_after_first_probe_and_stops_cleanly(self) -> None:
        evidence = self.root / "evidence-clean"
        started = self.run_monitor(
            "start",
            "--repository", str(self.repository),
            "--evidence-dir", str(evidence),
            "--interval-ms", "25",
        )
        self.assertEqual("started", started["outcome"])
        self.assertEqual("linux-fanotify-pid", started["git_writer_attribution_backend"])
        self.assertGreaterEqual(started["checks"], 1)
        self.assertFalse(os.access(self.script, os.X_OK))

        time.sleep(0.08)
        stopped = self.run_monitor("stop", "--evidence-dir", str(evidence))
        self.assertEqual("pass", stopped["outcome"])
        self.assertGreaterEqual(stopped["checks"], 2)
        self.assertEqual(0, stopped["violation_count"])
        self.assertEqual("linux-fanotify-pid", stopped["git_writer_attribution_backend"])
        self.assertTrue((evidence / "monitor-outcome.json").exists())
        self.assertGreater((evidence / "monitor-events.jsonl").stat().st_size, 0)
        events = [json.loads(line) for line in (evidence / "monitor-events.jsonl").read_text().splitlines()]
        self.assertEqual(list(range(1, len(events) + 1)), [event["sequence"] for event in events])

    @unittest.skipUnless(LINUX, "Launcher V4 monitor requires Linux inotify")
    def test_transient_write_invalidates_even_when_removed_before_stop(self) -> None:
        evidence = self.root / "evidence-mutation"
        self.run_monitor(
            "start",
            "--repository", str(self.repository),
            "--evidence-dir", str(evidence),
            "--interval-ms", "25",
        )

        transient = self.repository / "transient.txt"
        transient.write_text("must be observed\n")
        deadline = time.monotonic() + 5
        outcome_path = evidence / "monitor-outcome.json"
        while not outcome_path.exists() and time.monotonic() < deadline:
            time.sleep(0.025)
        transient.unlink()
        self.assertTrue(outcome_path.exists(), "monitor did not observe the transient write")

        stopped = self.run_monitor("stop", "--evidence-dir", str(evidence), expected=2)
        self.assertEqual("blocked", stopped["outcome"])
        self.assertEqual("transient-mutation-observed", stopped["reason"])
        self.assertGreaterEqual(stopped["monitor"]["violation_count"], 1)

    @unittest.skipUnless(LINUX, "Launcher V4 monitor requires Linux inotify")
    def test_sub_interval_create_remove_is_event_detected(self) -> None:
        evidence = self.root / "evidence-sub-interval"
        started = self.run_monitor(
            "start",
            "--repository", str(self.repository),
            "--evidence-dir", str(evidence),
            "--interval-ms", "1000",
        )
        self.assertEqual("linux-inotify", started["monitor_backend"])
        self.assertEqual(1, started["checks"])

        transient = self.repository / "short-lived.txt"
        transient.write_text("short\n")
        transient.unlink()
        deadline = time.monotonic() + 5
        outcome_path = evidence / "monitor-outcome.json"
        while not outcome_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        stopped = self.run_monitor("stop", "--evidence-dir", str(evidence), expected=2)
        self.assertEqual("transient-mutation-observed", stopped["reason"])
        self.assertGreaterEqual(stopped["monitor"]["event_count"], 2)

    @unittest.skipUnless(LINUX, "Launcher V4 monitor requires Linux inotify")
    def test_git_index_lock_records_kernel_writer_attribution(self) -> None:
        evidence = self.root / "evidence-index-lock"
        started = self.run_monitor(
            "start",
            "--repository", str(self.repository),
            "--evidence-dir", str(evidence),
            "--interval-ms", "1000",
        )
        self.assertEqual("linux-fanotify-pid", started["git_writer_attribution_backend"])

        writer = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import pathlib,time; "
                    f"path=pathlib.Path({str(self.repository / '.git' / 'index.lock')!r}); "
                    "handle=path.open('wb'); handle.write(b'probe\\n'); handle.flush(); "
                    "time.sleep(0.25); handle.close()"
                ),
            ],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        deadline = time.monotonic() + 5
        outcome_path = evidence / "monitor-outcome.json"
        while not outcome_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        writer.wait(timeout=5)
        self.assertTrue(outcome_path.exists(), "monitor did not observe the Git lock")

        stopped = self.run_monitor("stop", "--evidence-dir", str(evidence), expected=2)
        self.assertEqual("transient-mutation-observed", stopped["reason"])
        lock_events = [
            event
            for event in stopped["monitor"]["invalidating_events"]
            if event["path"] == str(self.repository / ".git" / "index.lock")
        ]
        self.assertGreaterEqual(len(lock_events), 1)
        attribution = lock_events[0]["git_writer_attribution"]
        self.assertEqual("attributed", attribution["status"])
        self.assertEqual("linux-fanotify-pid", attribution["backend"])
        self.assertEqual(writer.pid, attribution["writer_pid"])
        self.assertEqual("external-process", attribution["actor_kind"])
        self.assertRegex(attribution["command_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("command", attribution)

    def test_evidence_directory_must_be_outside_repository(self) -> None:
        blocked = self.run_monitor(
            "start",
            "--repository", str(self.repository),
            "--evidence-dir", str(self.repository / ".context" / "monitor"),
            expected=2,
        )
        self.assertEqual("blocked", blocked["outcome"])
        self.assertIn("outside", blocked["required_actions"][0])

    def test_direct_python_invocation_is_rejected(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(self.script),
                "start",
                "--repository", str(self.repository),
                "--evidence-dir", str(self.root / "direct-evidence"),
            ],
            text=True,
            capture_output=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        blocked = json.loads(result.stdout)
        self.assertEqual("blocked", blocked["outcome"])
        self.assertIn("checker-python.py", blocked["required_actions"][0])

    def test_overflow_and_lost_watch_events_invalidate(self) -> None:
        module = load_monitor_module()
        watcher = module.InotifyWatcher.__new__(module.InotifyWatcher)
        watcher.fd = 41
        watcher.repository = self.repository
        watcher.git_dir = self.repository / ".git"
        watcher.paths = {7: self.repository}
        overflow = module.INOTIFY_EVENT.pack(-1, module.IN_Q_OVERFLOW, 0, 0)
        ignored = module.INOTIFY_EVENT.pack(7, module.IN_IGNORED, 0, 0)
        with mock.patch.object(module.os, "read", side_effect=[overflow + ignored, BlockingIOError()]):
            events = watcher.read_events()
        self.assertEqual(2, len(events))
        self.assertTrue(all(event["invalidating"] for event in events))

    def test_monitor_owned_writer_identity_is_explicit_and_redacted(self) -> None:
        module = load_monitor_module()
        attributor = module.GitWriterAttributor.__new__(module.GitWriterAttributor)
        attributor.monitor_processes = {
            os.getpid(): {
                "monitor_role": "source-fingerprint",
                "registered_at_monotonic": time.monotonic(),
                "process_start_ticks": None,
            },
        }
        writer = attributor._writer(os.getpid())
        self.assertEqual("attributed", writer["status"])
        self.assertEqual("monitor-owned", writer["actor_kind"])
        self.assertEqual("source-fingerprint", writer["monitor_role"])
        self.assertEqual(os.getpid(), writer["writer_pid"])
        self.assertRegex(writer["command_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(writer["executable_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertNotIn("command", writer)

    def test_fanotify_overflow_fails_closed(self) -> None:
        module = load_monitor_module()
        attributor = module.GitWriterAttributor.__new__(module.GitWriterAttributor)
        attributor.fd = 43
        overflow = module.FANOTIFY_EVENT.pack(
            module.FANOTIFY_EVENT.size,
            module.FANOTIFY_METADATA_VERSION,
            0,
            module.FANOTIFY_EVENT.size,
            module.FAN_Q_OVERFLOW,
            -1,
            0,
        )
        with mock.patch.object(module.os, "read", return_value=overflow):
            with self.assertRaisesRegex(module.MonitorError, "attribution queue overflow"):
                attributor.read_events()

    def test_malformed_event_buffer_fails_closed(self) -> None:
        module = load_monitor_module()
        watcher = module.InotifyWatcher.__new__(module.InotifyWatcher)
        watcher.fd = 42
        watcher.repository = self.repository
        watcher.git_dir = self.repository / ".git"
        watcher.paths = {7: self.repository}
        malformed = module.INOTIFY_EVENT.pack(7, module.IN_CREATE, 0, 8) + b"x"
        with mock.patch.object(module.os, "read", return_value=malformed):
            with self.assertRaisesRegex(module.MonitorError, "malformed inotify event name"):
                watcher.read_events()

    def test_unsupported_platform_is_rejected(self) -> None:
        module = load_monitor_module()
        evidence = self.root / "unsupported-evidence"
        with (
            mock.patch.dict(os.environ, {
                "AI_PLAYBOOK_CHECKER_PYTHON_WRAPPER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }),
            mock.patch.object(module, "require_python_policy"),
            mock.patch.object(module.platform, "system", return_value="Darwin"),
        ):
            with self.assertRaisesRegex(module.MonitorError, "requires Linux inotify"):
                module.start(self.repository, evidence, 100, 1)


if __name__ == "__main__":
    unittest.main()

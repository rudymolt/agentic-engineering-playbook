#!/usr/bin/env python3
"""Measure delivery tests, including setup/cleanup, in fresh repeat processes.

Use --output .context/runtime.json to retain local evidence without publishing
failure diagnostics. Run identical commands on the baseline and candidate.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import io
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import runpy
import shlex
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / "v0.5"
SETS = runpy.run_path(str(ROOT / "delivery/scripts/verify.py"))["SETS"]


class GitDiagnostics:
    """Observe the real run seam; retain no arguments, URLs or captured output."""

    def __init__(self):
        self.samples = []
        self.sample_lock = threading.Lock()
        self.test = None
        self.subtest = None
        self.subtest_serial = 0

    @staticmethod
    def category(command):
        if not isinstance(command, (list, tuple)) or not command:
            return None
        try:
            executable = os.fsdecode(command[0])
        except (TypeError, ValueError):
            return None
        if Path(executable).name != "git":
            return None
        index = 1
        while index < len(command):
            try:
                arg = os.fsdecode(command[index])
            except (TypeError, ValueError):
                return "other"
            if arg in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env"):
                index += 2
            elif arg.startswith("-"):
                index += 1
            else:
                # Unknown commands are counted without publishing arbitrary text.
                return arg if arg in {"push", "clone", "fetch", "ls-remote", "init", "config",
                                      "remote", "rev-parse", "update-ref", "show", "log", "repack",
                                      "check-ref-format", "hash-object", "cat-file", "commit-tree",
                                      "write-tree", "read-tree", "add", "commit", "status", "diff"} else "other"
        return "other"

    def phase(self):
        phase = "test" if self.test is not None else "module"
        frame = sys._getframe(1)
        while frame is not None:
            name = frame.f_code.co_name
            if name in ("failed_s2", "build_seed") and frame.f_code.co_filename.endswith(("test_interim_repair.py", "checkpoint_seed_support.py")):
                return "seed-construction"
            if name == "setUpClass":
                phase = "class-setup"
            elif name in ("tearDownClass", "doClassCleanups"):
                phase = "class-cleanup"
            elif name == "setUp":
                phase = "setup"
            elif name in ("tearDown", "doCleanups"):
                phase = "cleanup"
            frame = frame.f_back
        return phase

    def identity(self):
        class_id = self.test.rsplit(".", 1)[0] if self.test else None
        case_id = f"subtest-{self.subtest}" if self.subtest is not None else None
        frame = sys._getframe(1)
        while frame is not None:
            cls = frame.f_locals.get("cls")
            if class_id is None and isinstance(cls, type) and issubclass(cls, unittest.TestCase):
                class_id = cls.__module__ + "." + cls.__qualname__
            # These two existing loops publish between subTest blocks. Map all
            # their calls to the original ordered case inventory without logging
            # case names, parameters, mutation values or frame contents.
            if (Path(frame.f_code.co_filename).name == "test_interim_coordinator.py" and
                    frame.f_code.co_name in ("assert_receipt_parity", "test_operation_binding_parity_matrix")):
                name = frame.f_locals.get("name")
                cases = frame.f_locals.get("cases", ())
                for index, entry in enumerate(cases, 1):
                    if isinstance(name, str) and isinstance(entry, tuple) and entry[0] == name:
                        case_id = f"{frame.f_code.co_name}:case-{index}"
                        break
            frame = frame.f_back
        return {"class_id": class_id, "case_id": case_id}

    @contextmanager
    def installed(self):
        real_run = subprocess.run
        real_subtest = unittest.TestCase.subTest
        observer = self

        def run(*args, **kwargs):
            command = args[0] if args else kwargs.get("args")
            category = observer.category(command)
            if category is None:
                return real_run(*args, **kwargs)
            sample = {"category": category,
                      "phase": observer.phase(), "test_id": observer.test,
                      "subtest": observer.subtest, **observer.identity()}
            # Protect observation ordering only; real Git calls remain concurrent.
            with observer.sample_lock:
                sample["sequence"] = len(observer.samples) + 1
                observer.samples.append(sample)
            started = time.perf_counter()
            try:
                result = real_run(*args, **kwargs)
                sample["returncode"] = result.returncode
                return result
            except subprocess.CalledProcessError as exc:
                sample["returncode"] = exc.returncode
                raise
            except BaseException:
                sample["raised"] = True
                raise
            finally:
                sample["seconds"] = time.perf_counter() - started

        @contextmanager
        def subtest(test, *args, **kwargs):
            previous = observer.subtest
            observer.subtest_serial += 1
            observer.subtest = observer.subtest_serial
            try:
                with real_subtest(test, *args, **kwargs):
                    yield
            finally:
                observer.subtest = previous

        with mock.patch.object(subprocess, "run", run), mock.patch.object(unittest.TestCase, "subTest", subtest):
            yield


def worker(pattern: str, tests: list[str], diagnostics: bool = False, group: str = "delivery") -> dict:
    os.chdir(ROOT)
    directory = "delivery/tests" if group == "delivery" else "scripts"
    sys.path.insert(0, str(ROOT / directory))
    observer = GitDiagnostics()
    rows = []

    class TimedResult(unittest.TextTestResult):
        def startTest(self, test):
            observer.test = test.id()
            observer.subtest_serial = 0
            self.started = time.perf_counter()
            super().startTest(test)

        def stopTest(self, test):
            failed = any(item[0] == test for item in self.failures + self.errors)
            skipped = any(item[0] == test for item in self.skipped)
            # Include failing subtests in the parent outcome.
            failed = failed or any(getattr(item[0], "test_case", None) == test
                                   for item in self.failures + self.errors)
            rows.append({"id": test.id(), "seconds": time.perf_counter() - self.started,
                         "outcome": "failed" if failed else "skipped" if skipped else
                         "unexpected-success" if test in self.unexpectedSuccesses else
                         "expected-failure" if any(item[0] == test for item in self.expectedFailures) else "passed"})
            super().stopTest(test)
            observer.test = None

    started = time.perf_counter()
    # Install before imports so proxies and saved subprocess references see it.
    with observer.installed() if diagnostics else nullcontext():
        suite = (unittest.defaultTestLoader.loadTestsFromNames(tests) if tests else
                 unittest.defaultTestLoader.discover(directory, pattern=pattern))
        discovered = suite.countTestCases()
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=TimedResult).run(suite)
    measured = {"seconds": time.perf_counter() - started, "successful": result.wasSuccessful() and discovered > 0,
            "discovered": discovered,
            "tests": rows, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped)}
    if discovered == 0:
        measured["selection_error"] = "empty-selection"
    if diagnostics:
        measured["git_samples"] = observer.samples
        measured["git_counts"] = {category: sum(s["category"] == category for s in observer.samples)
                                  for category in sorted({"push", "clone", "fetch", "ls-remote"} |
                                                         {s["category"] for s in observer.samples})}
    return measured


def serial_verifier(selected: str, env: dict) -> dict:
    """Time the actual verifier, attributing its flushed command boundaries."""
    command = [sys.executable, str(ROOT / "delivery/scripts/verify.py"), "--set", selected, "--jobs", "1"]
    started = time.perf_counter()
    boundaries = []
    previous = None
    previous_started = None
    with subprocess.Popen(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT) as process:
        for line in process.stdout:
            if not (line.startswith("$ ") or line.startswith("V0.5 delivery ")):
                continue
            now = time.perf_counter()
            if previous is not None:
                boundaries.append({"pattern": previous, "wall_seconds": now - previous_started})
            previous = None
            if line.startswith("$ "):
                parts = shlex.split(line[2:])
                previous = parts[parts.index("-p") + 1] if "-p" in parts else "generated-file-check"
                previous_started = now
        returncode = process.wait()
    ended = time.perf_counter()
    if previous is not None:
        boundaries.append({"pattern": previous, "wall_seconds": ended - previous_started})
    return {"wall_seconds": ended - started, "returncode": returncode, "steps": boundaries,
            "attribution": "elapsed between flushed verifier command headers; overhead retained"}


def os_identity() -> dict:
    facts = platform.freedesktop_os_release() if sys.platform == "linux" else {"NAME": platform.system()}
    return {key: facts[key] for key in ("ID", "VERSION_ID", "NAME", "VERSION", "PRETTY_NAME") if key in facts}


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT.parent, help="repository checkout to measure")
    parser.add_argument("--set", choices=tuple(SETS), default="K4.1")
    parser.add_argument("--test", action="append", default=[], help="exact unittest ID; repeatable")
    parser.add_argument("--pattern", action="append", help="complete file pattern; repeatable")
    parser.add_argument("--group", choices=("delivery", "guidance"), default="delivery")
    parser.add_argument("--git-diagnostics", action="store_true", help="observe real Git calls; not acceptance timing")
    parser.add_argument("--verify-suite", action="store_true", help="also time the complete serial delivery verifier")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    ROOT = args.root.resolve() / "v0.5"
    if args.worker:
        print(json.dumps(worker(args.worker, args.test, args.git_diagnostics, args.group)))
        return 0
    if args.repeat < 1 or args.output is None:
        parser.error("--repeat must be positive and --output is required")
    env = os.environ.copy()
    env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="gc.auto", GIT_CONFIG_VALUE_0="0",
               GIT_CONFIG_KEY_1="maintenance.auto", GIT_CONFIG_VALUE_1="false")
    if args.test and args.pattern:
        parser.error("--test and --pattern cannot be combined")
    if args.verify_suite and (args.test or args.pattern or args.group != "delivery" or args.git_diagnostics):
        parser.error("--verify-suite requires the complete uninstrumented delivery set")
    selected_sets = runpy.run_path(str(ROOT / "delivery/scripts/verify.py"))["SETS"]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    report = {"revision": revision, "dirty": dirty, "python": platform.python_version(),
              "platform": platform.system(), "set": args.set, "selected_tests": args.test,
              "git": subprocess.check_output(["git", "--version"], text=True).strip(),
              "workers": 1, "group": args.group,
              "measurement_mode": "diagnostic" if args.git_diagnostics else "timing",
              "runner": {"os": os_identity(),
                         "machine": platform.machine(), "cpus": os.cpu_count(),
                         "image_os": os.environ.get("ImageOS"), "image_version": os.environ.get("ImageVersion")},
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "privileged": hasattr(os, "geteuid") and os.geteuid() == 0,
              "profiler_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "verifier_sha256": hashlib.sha256((ROOT / "delivery/scripts/verify.py").read_bytes()).hexdigest(),
              "test_sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((ROOT / ("delivery/tests" if args.group == "delivery" else "scripts")).glob("test_*.py"))},
              "repetitions": [], "timing": "perf_counter; setup, method, cleanup included"}
    patterns = (["selected"] if args.test else args.pattern or
                (["test_model_reviewed_guidance.py", "test_model_reviewed_guidance_boundaries.py",
                  "test_model_reviewed_guidance_declarations.py"] if args.group == "guidance" else selected_sets[args.set]))
    report["patterns"] = list(patterns)
    successful = True
    for repeat in range(args.repeat):
        batch = []
        if args.verify_suite:
            verified = serial_verifier(args.set, env)
            report.setdefault("serial_verifier", []).append(verified)
            successful = successful and verified["returncode"] == 0
            print(f"serial verifier: {verified['wall_seconds']:.3f}s; returncode={verified['returncode']}", flush=True)
        for pattern in patterns:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", pattern, "--root", str(ROOT.parent), "--group", args.group]
            if args.git_diagnostics:
                command.append("--git-diagnostics")
            for test in args.test:
                command.extend(["--test", test])
            started = time.perf_counter()
            result = subprocess.run(command, env=env, text=True, capture_output=True, check=True)
            measured = json.loads(result.stdout)
            measured["wall_seconds"] = time.perf_counter() - started
            batch.append({"pattern": pattern, **measured})
            successful = successful and measured["successful"]
            print(f"repeat {repeat + 1}: {pattern}: {measured['seconds']:.3f}s; "
                  f"{len(measured['tests'])} tests; successful={measured['successful']}", flush=True)
        report["repetitions"].append(batch)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())

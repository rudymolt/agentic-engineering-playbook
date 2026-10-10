#!/usr/bin/env python3
"""Measure delivery tests, including setup/cleanup, in fresh repeat processes.

Use --output .context/runtime.json to retain local evidence without publishing
failure diagnostics. Run identical commands on the baseline and candidate.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager, nullcontext
import io
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shlex
import subprocess
import sys
import threading
import tempfile
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


def public_python_sources() -> list[Path]:
    """Bind eligibility to this Git checkout, never ignored filesystem entries."""
    top = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    if top.resolve() != ROOT.parent.resolve():
        return []
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    return [ROOT / name for name in tracked if name.endswith(".py") and
            name.startswith(("delivery/tests/", "delivery/src/", "scripts/")) and
            (ROOT / name).is_file() and (ROOT / name).resolve() == ROOT / name]


def serial_failure_sources() -> tuple[set[str], set[str]]:
    """Index public source identities without importing or executing tests."""
    paths = public_python_sources()
    identities = set()
    sources = {path.relative_to(ROOT).as_posix() for path in paths}
    for path in paths:
        if path.parent != ROOT / "delivery/tests" or not path.name.startswith("test_"):
            continue
        module = path.stem
        identities.update((module, "unittest.loader._FailedTest." + module))
        try:
            tree = ast.parse(path.read_text())
        except (OSError, SyntaxError, UnicodeError):
            continue
        for cls in tree.body:
            if isinstance(cls, ast.ClassDef):
                identities.add(module + "." + cls.name)
                identities.update(module + "." + cls.name + "." + method.name
                                  for method in cls.body if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef))
                                  and method.name.startswith("test_"))
    return identities, sources


SERIAL_STARTUP = '''import importlib.machinery, importlib.util, os, sys
from pathlib import Path
own = Path(__file__).parent.resolve()
search = [entry for entry in sys.path if Path(entry or os.getcwd()).resolve() != own]
prior = importlib.machinery.PathFinder.find_spec("sitecustomize", search)
if prior is not None:
    module = importlib.util.module_from_spec(prior)
    sys.modules["sitecustomize"] = module
    if prior.loader is not None:
        prior.loader.exec_module(module)
spec = importlib.util.spec_from_file_location("_checkpoint_serial_capture", CAPTURE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.startup(os.environ["CHECKPOINT_SERIAL_FAILURE_CONFIG"])
'''


def bounded_output_lines(stream):
    """Drain arbitrary bytes; retain only short lines eligible as headers."""
    pending = bytearray()
    oversized = False
    while chunk := stream.read1(8192):
        pieces = chunk.split(b"\n")
        for index, piece in enumerate(pieces):
            if not oversized:
                if len(pending) + len(piece) <= 1024:
                    pending.extend(piece)
                else:
                    pending.clear()
                    oversized = True
            if index < len(pieces) - 1:
                if not oversized:
                    yield pending.decode("utf-8", errors="replace")
                pending.clear()
                oversized = False
    if pending and not oversized:
        yield pending.decode("utf-8", errors="replace")


def serial_verifier(selected: str, env: dict) -> dict:
    """Time the native verifier; collect failure events without parsing messages."""
    command = [sys.executable, str(ROOT / "delivery/scripts/verify.py"), "--set", selected, "--jobs", "1"]
    started = time.perf_counter()
    known_failures, known_sources = serial_failure_sources()
    boundaries = []
    seen_labels = set()
    previous = None
    previous_started = None
    captured = {}
    with tempfile.TemporaryDirectory(prefix="checkpoint-serial-evidence-") as directory:
        scratch = Path(directory)
        config_path = scratch / "config.json"
        output_path = scratch / "events.json"
        config_path.write_text(json.dumps({"root": str(ROOT.resolve()), "verifier": command[1],
            "owner": str(scratch / "owner"), "output": str(output_path),
            "identities": sorted(known_failures), "sources": sorted(known_sources)}))
        capture_path = Path(__file__).with_name("serial_failure_capture.py").resolve()
        (scratch / "sitecustomize.py").write_text("CAPTURE_PATH = " + repr(str(capture_path)) + "\n" + SERIAL_STARTUP)
        child_env = env.copy()
        child_env["CHECKPOINT_SERIAL_FAILURE_CONFIG"] = str(config_path)
        child_env["PYTHONPATH"] = str(scratch) + (os.pathsep + child_env["PYTHONPATH"] if child_env.get("PYTHONPATH") else "")
        with subprocess.Popen(command, cwd=ROOT, env=child_env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            for line in bounded_output_lines(process.stdout):
                label = None
                if line.startswith("$ "):
                    try:
                        parts = shlex.split(line[2:])
                    except ValueError:
                        continue
                    if parts[1:] == ["delivery/scripts/generate.py", "--check"]:
                        label = "generated-file-check"
                    elif (len(parts) == 9 and parts[1:7] == ["-m", "unittest", "discover", "-s", "delivery/tests", "-p"]
                          and parts[8:] == ["-v"] and "delivery/tests/" + parts[7] in known_sources):
                        label = parts[7]
                    if label is None or label in seen_labels:
                        continue
                    # Canonical serial verification executes each pattern once.
                    # Public source inventory bounds this set and the step list.
                    seen_labels.add(label)
                elif line.strip() != f"V0.5 delivery {selected} checks passed.":
                    continue
                now = time.perf_counter()
                if previous is not None:
                    boundaries.append({"pattern": previous, "wall_seconds": now - previous_started})
                previous = label
                previous_started = now if label is not None else None
            returncode = process.wait()
        if output_path.exists():
            captured = json.loads(output_path.read_text())
    ended = time.perf_counter()
    if previous is not None:
        boundaries.append({"pattern": previous, "wall_seconds": ended - previous_started})
    # Assertion/output text cannot authenticate failed-command attribution.
    # Failed attempts are ineligible for timings; retain native events and exit.
    if returncode:
        boundaries = []
    failed_tests = captured.get("failed_tests", []) if returncode else []
    evidence = {"status": "passed" if returncode == 0 else "identified" if failed_tests else "unknown",
                "command": None,
                "matched_events": captured.get("matched_events", 0),
                "unmatched_events": captured.get("unmatched_events", 0),
                "truncated": captured.get("truncated", False), "capture": "unittest callbacks"}
    return {"wall_seconds": ended - started, "returncode": returncode, "steps": boundaries,
            "failed_tests": failed_tests, "failure_evidence": evidence,
            "attribution": "failed-run command attribution omitted" if returncode else
                           "elapsed between flushed verifier command headers; overhead retained"}


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
                               for p in public_python_sources() if p.parent == ROOT / ("delivery/tests" if args.group == "delivery" else "scripts")
                               and p.name.startswith("test_")},
              "serial_capture_sha256": hashlib.sha256(Path(__file__).with_name("serial_failure_capture.py").read_bytes()).hexdigest(),
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
            if verified["returncode"]:
                # Publish identities/relative locations only, never assertion values,
                # subtest parameters, native arguments or captured failure text.
                print("serial failure evidence: " + json.dumps({**verified["failure_evidence"],
                      "failed_tests": verified["failed_tests"]}), flush=True)
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

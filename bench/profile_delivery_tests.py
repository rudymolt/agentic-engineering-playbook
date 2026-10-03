#!/usr/bin/env python3
"""Measure delivery tests, including setup/cleanup, in fresh repeat processes.

Use --output .context/runtime.json to retain local evidence without publishing
failure diagnostics. Run identical commands on the baseline and candidate.
"""
from __future__ import annotations

import argparse
import io
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1] / "v0.5"
SETS = runpy.run_path(str(ROOT / "delivery/scripts/verify.py"))["SETS"]


def worker(pattern: str, tests: list[str]) -> dict:
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "delivery/tests"))
    suite = (unittest.defaultTestLoader.loadTestsFromNames(tests) if tests else
             unittest.defaultTestLoader.discover("delivery/tests", pattern=pattern))
    rows = []

    class TimedResult(unittest.TextTestResult):
        def startTest(self, test):
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

    started = time.perf_counter()
    result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=TimedResult).run(suite)
    return {"seconds": time.perf_counter() - started, "successful": result.wasSuccessful(),
            "tests": rows, "failures": len(result.failures), "errors": len(result.errors),
            "skipped": len(result.skipped)}


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT.parent, help="repository checkout to measure")
    parser.add_argument("--set", choices=tuple(SETS), default="K4.1")
    parser.add_argument("--test", action="append", default=[], help="exact unittest ID; repeatable")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    ROOT = args.root.resolve() / "v0.5"
    if args.worker:
        print(json.dumps(worker(args.worker, args.test)))
        return 0
    if args.repeat < 1 or args.output is None:
        parser.error("--repeat must be positive and --output is required")
    env = os.environ.copy()
    env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_0="gc.auto", GIT_CONFIG_VALUE_0="0",
               GIT_CONFIG_KEY_1="maintenance.auto", GIT_CONFIG_VALUE_1="false")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    report = {"revision": revision, "dirty": dirty, "python": platform.python_version(),
              "platform": platform.system(), "set": args.set, "selected_tests": args.test,
              "recorded_at": datetime.now(timezone.utc).isoformat(),
              "privileged": hasattr(os, "geteuid") and os.geteuid() == 0,
              "test_sources": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((ROOT / "delivery/tests").glob("*.py"))},
              "repetitions": [], "timing": "perf_counter; setup, method, cleanup included"}
    patterns = ["selected"] if args.test else SETS[args.set]
    successful = True
    for repeat in range(args.repeat):
        batch = []
        for pattern in patterns:
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", pattern, "--root", str(ROOT.parent)]
            for test in args.test:
                command.extend(["--test", test])
            result = subprocess.run(command, env=env, text=True, capture_output=True, check=True)
            measured = json.loads(result.stdout)
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

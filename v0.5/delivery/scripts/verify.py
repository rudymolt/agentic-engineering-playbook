#!/usr/bin/env python3
"""Run the named V0.5 verification set, optionally sharding files in CI."""

from __future__ import annotations

import subprocess
import sys
import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SETS = {
    "A-continuation": ("test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py", "test_interim_recovery.py", "test_interim_stack.py", "test_interim_watchdog.py", "test_interim_monitor.py", "test_interim_conductor_host.py", "test_interim_host_continuation.py"),
    "A-core-local": ("test_core.py", "test_pack_lifecycle.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py", "test_interim_recovery.py", "test_interim_stack.py", "test_interim_watchdog.py", "test_interim_monitor.py", "test_interim_conductor_host.py", "test_interim_host_continuation.py"),
    "A-cloud": ("test_cloud.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py", "test_interim_recovery.py", "test_interim_stack.py", "test_interim_watchdog.py", "test_interim_monitor.py", "test_interim_conductor_host.py", "test_interim_host_continuation.py"),
    "A-complete": ("test_core.py", "test_pack_lifecycle.py", "test_cloud.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py", "test_interim_recovery.py", "test_interim_stack.py", "test_interim_watchdog.py", "test_interim_monitor.py", "test_interim_conductor_host.py", "test_interim_host_continuation.py"),
    "K4.1": ("test_core.py", "test_pack_lifecycle.py", "test_cloud.py", "test_checker_monitor.py", "test_continuation.py", "test_interim.py", "test_interim_coordinator.py", "test_interim_repair.py", "test_interim_recovery.py", "test_interim_stack.py", "test_interim_watchdog.py", "test_interim_monitor.py", "test_interim_conductor_host.py", "test_interim_host_continuation.py"),
}

SETS = {name: (*tests, "test_interim_advance.py") for name, tests in SETS.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=tuple(SETS), default="A-complete")
    parser.add_argument("--jobs", type=int, default=1,
                        help="concurrent unittest file shards (CI only; default: 1)")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        parser.error("--jobs must be between 1 and 4")
    selected = args.set
    commands = [(sys.executable, "delivery/scripts/generate.py", "--check")]
    commands.extend(
        (sys.executable, "-m", "unittest", "discover", "-s", "delivery/tests", "-p", name, "-v")
        for name in SETS[selected]
    )
    # These suites create and destroy many disposable Git repositories. Git's
    # detached auto-maintenance can outlive a command and race fixture cleanup.
    fixture_env = os.environ.copy()
    fixture_env.update({
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "gc.auto",
        "GIT_CONFIG_VALUE_0": "0",
        "GIT_CONFIG_KEY_1": "maintenance.auto",
        "GIT_CONFIG_VALUE_1": "false",
    })
    for command in (commands[:1] if args.jobs > 1 else commands):
        print(f"\n$ {' '.join(command)}", flush=True)
        result = subprocess.run(command, cwd=ROOT, env=fixture_env, check=False)
        if result.returncode:
            return result.returncode
    if args.jobs > 1:
        sys.path.insert(0, str(ROOT / "scripts"))
        from parallel_verification import run_parallel

        result = run_parallel(commands[1:], cwd=ROOT, env=fixture_env, jobs=args.jobs)
        if result:
            return result
    print(f"\nV0.5 delivery {selected} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the canonical playbook release-readiness checks.

--skip-drift omits the monthly upstream-drift cadence check. It exists for the
PR CI gate: an overdue upstream review has a different owner and remedy than a
broken PR, so it must not turn unrelated PRs red. The weekly maintenance cron
and local release runs keep the strict, full set.

--jobs runs the public and delivery unittest files in parallel shards. The
default remains the ordinary single-process release-readiness run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from parallel_verification import run_parallel, test_files


ROOT = Path(__file__).resolve().parents[2]
COMMANDS = (
    (sys.executable, "-m", "unittest", "discover", "-s", "v0.5/scripts", "-p", "test_*.py"),
    (sys.executable, "v0.5/scripts/check-interactive-docs.py"),
    (sys.executable, "v0.5/scripts/check-md-conventions.py"),
    (sys.executable, "v0.5/scripts/check-skill-metadata.py"),
    (sys.executable, "v0.5/scripts/check-links.py"),
    (sys.executable, "v0.5/scripts/check-public-content.py"),
    (sys.executable, "v0.5/scripts/generate-status.py", "--check"),
    (sys.executable, "v0.5/scripts/generate-upstream-inventory.py", "--check"),
    (sys.executable, "v0.5/scripts/generate-manifest.py", "--check"),
    (sys.executable, "v0.5/delivery/scripts/verify.py", "--set", "K4.1"),
    (sys.executable, "v0.5/scripts/check-upstream-drift.py"),
)
DRIFT_COMMAND = "check-upstream-drift.py"
DELIVERY_COMMAND = "v0.5/delivery/scripts/verify.py"


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("V0.5 verification requires Python 3.10 or newer; current interpreter is "
              f"{sys.version_info.major}.{sys.version_info.minor}.")
        return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-drift", action="store_true",
                        help="omit the monthly upstream-drift check (PR CI only)")
    parser.add_argument("--skip-delivery", action="store_true",
                        help="omit privileged delivery checks (split CI job only)")
    parser.add_argument("--jobs", type=int, default=1,
                        help="concurrent public and delivery unittest file shards (default: 1)")
    args = parser.parse_args(argv)
    if not 1 <= args.jobs <= 4:
        parser.error("--jobs must be between 1 and 4")

    for command in COMMANDS:
        if args.skip_drift and command[-1].endswith(DRIFT_COMMAND):
            print(f"\n(skipped {DRIFT_COMMAND} — --skip-drift)", flush=True)
            continue
        if args.skip_delivery and DELIVERY_COMMAND in command:
            print(f"\n(skipped {DELIVERY_COMMAND} — --skip-delivery)", flush=True)
            continue
        if command == COMMANDS[0] and args.jobs > 1:
            files = test_files(ROOT / "v0.5/scripts")
            shards = [(*command[:-1], name) for name in files]
            print(f"\n$ public unittest discovery: {len(files)} file shards, "
                  f"{args.jobs} concurrent jobs", flush=True)
            result = run_parallel(shards, cwd=ROOT, jobs=args.jobs)
            if result:
                return result
            continue
        run_command = (*command, "--jobs", str(args.jobs)) if args.jobs > 1 and DELIVERY_COMMAND in command else command
        print(f"\n$ {' '.join(run_command)}", flush=True)
        completed = subprocess.run(run_command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    print("\nPlaybook release-readiness checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

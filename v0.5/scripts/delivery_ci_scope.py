#!/usr/bin/env python3
"""Classify changed paths for the expensive delivery CI suite."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable


DELIVERY_PREFIX = "v0.5/delivery/"
WORKFLOW_PREFIX = ".github/workflows/"
CLASSIFIER_PATH = "v0.5/scripts/delivery_ci_scope.py"
DELIVERY_CONTRACT_PATHS = {
    "v0.5/00-foundations.md",
    "v0.5/AGENT-DIGEST.md",
    "v0.5/10-process/07-implementation-tdd.md",
}


@dataclass(frozen=True)
class Decision:
    run_delivery: bool
    reason: str


def classify(paths: Iterable[str]) -> Decision:
    changed = {path.strip() for path in paths if path.strip()}
    if any(path.startswith(WORKFLOW_PREFIX) for path in changed):
        return Decision(True, "CI workflow changed")
    if CLASSIFIER_PATH in changed:
        return Decision(True, "delivery CI classifier changed")
    if changed & DELIVERY_CONTRACT_PATHS:
        return Decision(True, "delivery contract surface changed")
    if any(path.startswith(DELIVERY_PREFIX) for path in changed):
        return Decision(True, "delivery runtime files changed")
    return Decision(False, "no delivery runtime files changed")


def git_changed_paths(base: str, head: str, cwd: Path | None = None) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", base, head],
        cwd=cwd,
        check=True,
        capture_output=True,
    )
    return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    if bool(args.base) != bool(args.head):
        parser.error("--base and --head must be supplied together")
    paths = git_changed_paths(args.base, args.head) if args.base else sys.stdin
    decision = classify(paths)
    print(f"run_delivery={'true' if decision.run_delivery else 'false'}")
    print(f"reason={decision.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Select focused PR checks only for a small, editorial-only file set."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import sys
from typing import Iterable

from delivery_ci_scope import git_changed_paths


EDITORIAL_PATHS = frozenset({
    "README.md",
    "STATUS.md",
    "v0.5/CHANGELOG.md",
    "v0.5/MANIFEST.json",
})


@dataclass(frozen=True)
class Decision:
    run_full: bool
    reason: str


def classify(paths: Iterable[str]) -> Decision:
    changed = {path.strip() for path in paths if path.strip()}
    if changed and changed <= EDITORIAL_PATHS:
        return Decision(False, "editorial-only files")
    return Decision(True, "non-editorial or empty change set")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    if bool(args.base) != bool(args.head):
        parser.error("--base and --head must be supplied together")
    paths = git_changed_paths(args.base, args.head) if args.base else sys.stdin
    decision = classify(paths)
    print(f"run_full={'true' if decision.run_full else 'false'}")
    print(f"reason={decision.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Observe leftovers without deleting unknown resources: 0 clean, 1 error, 2 blocked."""
import sys
from pathlib import Path

if sys.argv[1:] == ["--help"]:
    print(__doc__ + " Usage: cleanup.py")
    raise SystemExit(0)
if len(sys.argv) != 1:
    print("error: Cleanup takes no arguments; use --help", file=sys.stderr)
    raise SystemExit(1)
root = Path(__file__).resolve().parent
try:
    if (root / ".owned-run").exists() or any((root / ".runs").glob("*")):
        print("blocked: inspect unknown run marker/state; this command owns nothing to delete", file=sys.stderr)
        raise SystemExit(2)
except OSError as error:
    print(f"error: inspect run resources: {error}", file=sys.stderr)
    raise SystemExit(1)
print("clean: no owned run state remains; evidence retained")

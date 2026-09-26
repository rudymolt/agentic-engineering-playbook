#!/usr/bin/env python3
"""Generate or check the deterministic V0.5 edition manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EDITION = Path(__file__).resolve().parents[1]
OUTPUT = EDITION / "MANIFEST.json"
EXCLUDED_NAMES = {"MANIFEST.json"}
EXCLUDED_PARTS = {"__pycache__"}


def inventory() -> list[dict]:
    entries = []
    for path in sorted(item for item in EDITION.rglob("*") if item.is_file()):
        relative = path.relative_to(EDITION)
        if relative.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix == ".pyc":
            continue
        data = path.read_bytes()
        entries.append({
            "path": relative.as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
        })
    return entries


def render() -> bytes:
    value = {
        "schema_version": 1,
        "edition": "V0.5.0",
        "self_rule": "MANIFEST.json is excluded; every other regular edition file is digest-bound",
        "files": inventory(),
    }
    return json.dumps(value, indent=2, sort_keys=True).encode() + b"\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != expected:
            print("V0.5 MANIFEST.json is stale; regenerate it with generate-manifest.py")
            return 1
        print(f"V0.5 manifest verified: {len(inventory())} digest-bound files.")
        return 0
    OUTPUT.write_bytes(expected)
    print(f"Wrote {OUTPUT} with {len(inventory())} digest-bound files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

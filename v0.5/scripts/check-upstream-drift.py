#!/usr/bin/env python3
"""Fail when the maintainer's monthly upstream comparison is due."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import sys
from pathlib import Path

import playbook_state
import upstream_registry


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE = ROOT / ".playbook-maintenance.yml"
DEFAULT_MANIFEST = ROOT / "v0.5" / "upstream-integrations.json"
DEFAULT_REGISTRY = ROOT / "v0.5" / "upstream-skills.json"
REQUIRED = {"owner", "procedure", "last_verified", "next_due", "cadence"}

COMPATIBILITY_PATH = Path(__file__).with_name("check-upstream-compatibility.py")
COMPATIBILITY_SPEC = importlib.util.spec_from_file_location(
    "upstream_compatibility_for_drift", COMPATIBILITY_PATH
)
assert COMPATIBILITY_SPEC and COMPATIBILITY_SPEC.loader
COMPATIBILITY = importlib.util.module_from_spec(COMPATIBILITY_SPEC)
COMPATIBILITY_SPEC.loader.exec_module(COMPATIBILITY)


def top_level_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        if not raw_line or raw_line[0].isspace() or raw_line.lstrip().startswith("#"):
            continue
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def check(
    path: Path,
    as_of: dt.date,
    *,
    manifest: Path = DEFAULT_MANIFEST,
    registry: Path = DEFAULT_REGISTRY,
) -> list[str]:
    if not path.exists():
        return [f"missing maintenance state: {path}"]
    values = top_level_values(path)
    problems = [f"missing maintenance field: {key}" for key in sorted(REQUIRED - set(values))]
    if problems:
        return problems
    if values["cadence"] != "monthly":
        problems.append("maintenance cadence must be monthly")
    try:
        last_verified = dt.date.fromisoformat(values["last_verified"])
        next_due = dt.date.fromisoformat(values["next_due"])
    except ValueError as exc:
        return [f"maintenance dates must use YYYY-MM-DD: {exc}"]
    if next_due <= last_verified:
        problems.append("next_due must be later than last_verified")
    if as_of >= next_due:
        problems.append(
            f"upstream comparison due {next_due}; owner {values['owner']} must run {values['procedure']} "
            "and advance last_verified/next_due"
        )
    try:
        manifest_payload = COMPATIBILITY.load_manifest(manifest)
    except COMPATIBILITY.ManifestError as error:
        problems.append(f"integration manifest invalid: {error}")
        return problems
    try:
        registry_payload = upstream_registry.load(registry)
    except upstream_registry.RegistryError as error:
        problems.append(f"upstream registry invalid: {error}")
        return problems

    problems.extend(upstream_registry.manifest_problems(registry_payload, manifest_payload))
    upstreams = playbook_state.parse_top_level_map(path.read_text(), "upstreams")
    matt_pin = registry_payload.packages["mattpocock-skills"].pin
    gstack_pin = registry_payload.packages["gstack"].pin
    expected_pins = {
        "matt_pocock_skills": matt_pin["value"],
        "gstack": f"{gstack_pin['value']} ({gstack_pin['commit'][:7]})",
    }
    for name, expected in expected_pins.items():
        if upstreams.get(name) != expected:
            problems.append(
                f"upstreams.{name} {upstreams.get(name)!r} does not match registry {expected!r}"
            )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date.today())
    args = parser.parse_args()
    problems = check(args.state, args.as_of, manifest=args.manifest, registry=args.registry)
    if problems:
        print("Upstream drift cadence check failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Upstream drift cadence current through {top_level_values(args.state)['next_due']}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Generate registry-backed upstream inventory regions deterministically."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import upstream_registry


ROOT = Path(__file__).resolve().parents[2]
REGION_FILES = {
    "check-a": Path("v0.5/10-process/00-prereqs.md"),
    "check-b": Path("v0.5/10-process/00-prereqs.md"),
    "provenance": Path("v0.5/10-process/00-prereqs.md"),
    "local-skills": Path("v0.5/skills/README.md"),
}


class RegionError(ValueError):
    """A generated region is missing or has ambiguous markers."""


def load_compatibility_manifest(path: Path) -> dict:
    """Use the compatibility checker's manifest parser despite its CLI filename."""
    script = Path(__file__).with_name("check-upstream-compatibility.py")
    spec = importlib.util.spec_from_file_location("check_upstream_compatibility", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.load_manifest(path)


def replace_region(text: str, name: str, body: str) -> str:
    """Replace one named generated body while preserving its markers."""
    opening = f"<!-- generated: upstream/{name} -->"
    closing = f"<!-- /generated: upstream/{name} -->"
    if text.count(opening) != 1 or text.count(closing) != 1:
        raise RegionError(f"region {name}: markers must occur exactly once")
    start = text.index(opening) + len(opening)
    end = text.index(closing, start)
    if end < start:
        raise RegionError(f"region {name}: closing marker precedes opening marker")
    return text[:start] + "\n" + body.rstrip() + "\n" + text[end:]


def inventory_values(registry, manifest: dict) -> dict[str, str]:
    matt = registry.packages["mattpocock-skills"].pin
    gstack = registry.packages["gstack"].pin
    integrations = manifest["integrations"]
    return {
        "matt_tag": matt["value"],
        "matt_verified": matt["verified"],
        "gstack_version": gstack.get("value", ""),
        "gstack_commit": gstack["commit"][:7],
        "gstack_verified": gstack["verified"],
        "manifest_verified": ", ".join(sorted({entry["last_verified"] for entry in integrations.values()})),
    }


def render_regions(registry, maintenance_values) -> dict[str, str]:
    """Render every body from registry data and stable maintenance values."""
    command_rows: list[str] = []
    row = ""
    columns = 0
    for command in registry.check_b_commands("gstack"):
        width = max(1, (len(command) + 20) // 21)
        if columns + width > 4:
            command_rows.append(row.rstrip())
            row = ""
            columns = 0
        row += f"{command:<{width * 21}}"
        columns += width
    if row:
        command_rows.append(row.rstrip())
    local_skills = registry.skills_for("playbook")
    values = maintenance_values
    gstack_provenance = f"The gstack inventory was last verified on {values['gstack_verified']}"
    if values["gstack_version"]:
        gstack_provenance += (
            " against the installed checkout at "
            f"{values['gstack_version']} ({values['gstack_commit']})"
        )
    gstack_provenance += "."
    return {
        "check-a": "```\n" + "\n".join(registry.check_a_paths("mattpocock-skills")) + "\n```",
        "check-b": "```\n" + "\n".join(command_rows) + "\n```",
        "provenance": (
            "The Matt Pocock accelerator inventory and behaviour contracts were verified on "
            f"{values['matt_verified']} against the released `mattpocock/skills` "
            f"{values['matt_tag']} tag. This source review does not qualify a host installation. "
            f"{gstack_provenance} "
            "Embedded reviewer source audits are dated "
            f"{values['manifest_verified']}; every inspected upstream workflow currently falls "
            "back to a playbook-owned route. Host capability claims were verified on 2026-07-09 "
            "against the first-party sources linked in `prereqs-capability-profiles.md`. "
            "Maintainers re-check released-source inventory through `../MAINTENANCE.md`."
        ),
        "local-skills": "\n".join([
            f"local_skills[{len(local_skills)}]{{name,invocation}}:",
            *(f"  {skill.name}, {skill.invocation}" for skill in local_skills),
        ]),
    }


def apply(root: Path, *, check: bool) -> list[str]:
    """Return drifted region names and write them only when requested."""
    registry = upstream_registry.load(root / "v0.5/upstream-skills.json")
    manifest = load_compatibility_manifest(root / "v0.5/upstream-integrations.json")
    regions = render_regions(registry, inventory_values(registry, manifest))
    drifted: list[str] = []
    for name, relative in REGION_FILES.items():
        path = root / relative
        existing = path.read_text()
        rendered = replace_region(existing, name, regions[name])
        if rendered != existing:
            drifted.append(name)
            if not check:
                path.write_text(rendered)
    return drifted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated regions drift")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (tests)")
    args = parser.parse_args(argv)
    try:
        drifted = apply(args.root, check=args.check)
    except (OSError, ValueError) as error:
        print(f"Generated inventory failed: {error}")
        return 2
    if args.check and drifted:
        print("Generated inventory drifted: " + ", ".join(drifted))
        return 1
    if drifted:
        print("Updated generated inventory: " + ", ".join(drifted))
    else:
        print("Generated inventory matches its sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

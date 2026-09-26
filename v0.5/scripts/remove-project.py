#!/usr/bin/env python3
"""Remove only unmodified V0.5-managed project files and delivery runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import template_base  # noqa: E402
from playbook_state import is_canonical_relative_path  # noqa: E402


PLAYBOOK_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PLAYBOOK_ROOT / "v0.5" / "delivery" / "scripts"))
from descriptor_delete import DescriptorDeleteError, DescriptorTree  # noqa: E402


class RemovalError(RuntimeError):
    pass


class ManagedRemoval(NamedTuple):
    relative: str
    digest: str


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def registered_contained_target(project: Path, relative: str, registry: dict[str, str]) -> Path:
    """Resolve one provenance key only after syntax, registry, and containment checks."""
    if not is_canonical_relative_path(relative):
        raise RemovalError(f"unsafe non-canonical managed path: {relative!r}")
    if relative not in registry:
        raise RemovalError(f"managed path is absent from the V0.5 registry: {relative}")
    root = project.resolve()
    target = root / relative
    try:
        resolved = target.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise RemovalError(f"cannot safely resolve managed path {relative}: {error}") from error
    if resolved == root or root not in resolved.parents:
        raise RemovalError(f"managed path escapes project containment: {relative}")
    return target


def removable_managed_files(project: Path) -> tuple[list[ManagedRemoval], list[str]]:
    project = project.resolve()
    state_path = project / ".playbook-state.yml"
    if not state_path.exists():
        raise RemovalError(".playbook-state.yml is missing")
    record = template_base.read_provenance(state_path.read_text())
    registry = template_base.managed_files(PLAYBOOK_ROOT)
    removable: list[ManagedRemoval] = []
    preserved: list[str] = []
    for relative, entry in sorted(record.get("files", {}).items()):
        target = registered_contained_target(project, relative, registry)
        if entry.get("template") != registry[relative]:
            raise RemovalError(
                f"managed template does not match the V0.5 registry for {relative}"
            )
        if not target.exists():
            continue
        if entry.get("version") != template_base.CURRENT_VERSION:
            preserved.append(f"{relative}: not owned by {template_base.CURRENT_VERSION}")
            continue
        try:
            actual = sha256_text(target.read_text())
        except UnicodeDecodeError:
            preserved.append(f"{relative}: non-text or modified")
            continue
        if actual != entry.get("base_sha256"):
            preserved.append(f"{relative}: project-modified")
            continue
        removable.append(ManagedRemoval(relative, entry["base_sha256"]))
    return removable, preserved


def remove(
    project: Path,
    *,
    before_managed_unlink: Callable[[str], None] | None = None,
) -> dict:
    project = project.resolve()
    removable, preserved = removable_managed_files(project)
    lifecycle = PLAYBOOK_ROOT / "v0.5" / "delivery" / "scripts" / "lifecycle.py"
    delivery_lock = project / ".agents/skills/ai-playbook-deliver/manifest-lock.yml"
    if delivery_lock.exists():
        completed = subprocess.run(
            [sys.executable, str(lifecycle), "uninstall", "--project", str(project)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RemovalError(completed.stdout.strip() or completed.stderr.strip())

    registry = template_base.managed_files(PLAYBOOK_ROOT)
    try:
        with DescriptorTree(project) as tree:
            for item in sorted(
                removable,
                key=lambda value: len(Path(value.relative).parts),
                reverse=True,
            ):
                registered_contained_target(project, item.relative, registry)
                tree.unlink(
                    item.relative,
                    expected_digest=item.digest,
                    before_unlink=before_managed_unlink,
                )
    except DescriptorDeleteError as error:
        raise RemovalError(str(error)) from error
    return {
        "outcome": "removed",
        "managed_files_removed": len(removable),
        "preserved": preserved,
        "state_preserved": True,
        "delivery_removed": not delivery_lock.exists(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        removable, preserved = removable_managed_files(args.project.resolve())
        if not args.apply:
            print(json.dumps({
                "outcome": "plan",
                "remove": [item.relative for item in removable],
                "preserve": preserved,
                "state_preserved": True,
            }, sort_keys=True))
            return 0
        result = remove(args.project)
    except (OSError, ValueError, RemovalError) as error:
        print(json.dumps({"outcome": "blocked", "error": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

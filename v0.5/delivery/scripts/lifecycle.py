#!/usr/bin/env python3
"""Deterministic install, verify, and removal for V0.5 delivery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


PACK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACK / "src"))
sys.path.insert(0, str(PACK / "scripts"))

from delivery_pilot.canonical import canonical_bytes, digest, load_strict  # noqa: E402
from descriptor_delete import (  # noqa: E402
    DescriptorDeleteError,
    DescriptorTree,
    canonical_parts,
)


SKILL_RELATIVE = Path(".agents/skills/ai-playbook-deliver")
APPROVED_REMOVED_FILES: dict[str, str] = {}


class LifecycleError(RuntimeError):
    pass


def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def source_manifest() -> dict[str, Any]:
    path = PACK / "MANIFEST.yml"
    if not path.exists():
        raise LifecycleError("MANIFEST.yml missing; run scripts/generate.py")
    manifest = load_strict(path.read_bytes())
    for entry in manifest["files"]:
        source = PACK / entry["source"]
        if not source.exists() or sha(source) != entry["digest"]:
            raise LifecycleError(f"source manifest mismatch: {entry['source']}")
    return manifest


def manifest_owned_files(manifest: dict[str, Any]) -> dict[str, str]:
    return {
        entry["install_path"]: entry["digest"]
        for entry in manifest["files"]
        if entry.get("install_path") is not None
    }


def validated_lock_owned_files(
    lock: dict[str, Any],
    *,
    expected: dict[str, str] | None = None,
) -> dict[str, str]:
    entries = lock.get("owned_files")
    if not isinstance(entries, list):
        raise LifecycleError("installed lock has no owned_files list")
    owned: dict[str, str] = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("digest"), str)
            or entry["path"] in owned
        ):
            raise LifecycleError("installed lock has a malformed owned_files entry")
        try:
            canonical_parts(entry["path"])
        except DescriptorDeleteError as error:
            raise LifecycleError(f"unsafe manifest-owned path: {entry['path']!r}") from error
        owned[entry["path"]] = entry["digest"]
    if expected is not None and owned != expected:
        raise LifecycleError("installed lock does not match the current owned-file registry")
    return owned


def owned_parent_directories(paths: dict[str, str]) -> list[str]:
    directories: set[str] = set()
    for relative in paths:
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add((SKILL_RELATIVE / parent).as_posix())
            parent = parent.parent
    return sorted(directories, key=lambda value: len(Path(value).parts), reverse=True)


def descriptor_unlink(
    project: Path,
    relative: str,
    *,
    expected_digest: str | None,
    missing_ok: bool = True,
) -> bool:
    try:
        with DescriptorTree(project) as tree:
            return tree.unlink(
                relative,
                expected_digest=expected_digest,
                missing_ok=missing_ok,
            )
    except DescriptorDeleteError as error:
        raise LifecycleError(str(error)) from error


def install(project: Path) -> dict[str, Any]:
    manifest = source_manifest()
    root = project / SKILL_RELATIVE
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "manifest-lock.yml"
    if lock_path.exists():
        lock = load_strict(lock_path.read_bytes())
        if lock.get("pack_digest") != manifest["pack_digest"]:
            raise LifecycleError("a different V0.5 delivery manifest already owns this skill directory")
        # A repeated install is verification, not permission to overwrite a
        # project-modified manifest-owned file.
        verify(project)
    state = root / "install-state.json"
    state.write_bytes(canonical_bytes({"status": "installing", "pack_digest": manifest["pack_digest"]}) + b"\n")
    owned = []
    for entry in manifest["files"]:
        destination_name = entry.get("install_path")
        if destination_name is None:
            continue
        source = PACK / entry["source"]
        destination = root / destination_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha(destination) != entry["digest"]:
            raise LifecycleError(f"refusing to overwrite existing file: {destination_name}")
        fd, raw_path = tempfile.mkstemp(prefix=destination.name, dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(raw_path, destination)
        finally:
            descriptor_unlink(
                project,
                Path(raw_path).relative_to(project).as_posix(),
                expected_digest=None,
            )
        owned.append({"path": destination_name, "digest": entry["digest"]})
    lock = {
        "schema_version": 1,
        "pack_digest": manifest["pack_digest"],
        "source_manifest": "v0.5/delivery/MANIFEST.yml",
        "owned_files": owned,
    }
    (root / "manifest-lock.yml").write_bytes(canonical_bytes(lock) + b"\n")
    descriptor_unlink(
        project,
        (SKILL_RELATIVE / "install-state.json").as_posix(),
        expected_digest=None,
    )
    activation = {
        "schema_version": 1,
        "skill": "ai-playbook-deliver",
        "command": "/ai-playbook-deliver",
        "skill_ref": (SKILL_RELATIVE / "SKILL.md").as_posix(),
        "pack_digest": manifest["pack_digest"],
        "discoverable": (root / "SKILL.md").exists(),
    }
    return {
        "outcome": "installed",
        "pack_digest": manifest["pack_digest"],
        "skill_root": str(root),
        "files": len(owned),
        "activation_receipt": {**activation, "receipt_digest": digest(activation)},
    }


def upgrade(
    project: Path,
    *,
    before_unlink: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    manifest = source_manifest()
    root, lock = installed_lock(project)
    if lock.get("pack_digest") == manifest["pack_digest"]:
        return {**verify(project), "outcome": "already-current"}

    old_owned = validated_lock_owned_files(lock)
    for relative, expected_digest in old_owned.items():
        path = root / relative
        if not path.exists() or sha(path) != expected_digest:
            raise LifecycleError(f"refusing to upgrade modified manifest-owned file: {relative}")

    new_entries = {
        entry["install_path"]: entry
        for entry in manifest["files"]
        if entry.get("install_path") is not None
    }
    removed_entries = set(old_owned) - set(new_entries)
    for relative in removed_entries:
        if APPROVED_REMOVED_FILES.get(relative) != old_owned[relative]:
            raise LifecycleError(
                f"no approved manifest removal migration for stale owned file: {relative}"
            )
    for relative, entry in new_entries.items():
        destination = root / relative
        if destination.exists() and relative not in old_owned and sha(destination) != entry["digest"]:
            raise LifecycleError(f"refusing to overwrite unowned file during upgrade: {relative}")

    state = root / "install-state.json"
    state.write_bytes(canonical_bytes({
        "status": "upgrading",
        "from_pack_digest": lock.get("pack_digest"),
        "to_pack_digest": manifest["pack_digest"],
    }) + b"\n")
    try:
        with DescriptorTree(project) as tree:
            for relative in sorted(
                removed_entries,
                key=lambda value: len(Path(value).parts),
                reverse=True,
            ):
                tree.unlink(
                    (SKILL_RELATIVE / relative).as_posix(),
                    expected_digest=old_owned[relative],
                    before_unlink=before_unlink,
                )
    except DescriptorDeleteError as error:
        raise LifecycleError(str(error)) from error
    owned = []
    for relative, entry in new_entries.items():
        source = PACK / entry["source"]
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix=destination.name, dir=destination.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(source.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(raw_path, destination)
        finally:
            descriptor_unlink(
                project,
                Path(raw_path).relative_to(project).as_posix(),
                expected_digest=None,
            )
        owned.append({"path": relative, "digest": entry["digest"]})
    new_lock = {
        "schema_version": 1,
        "pack_digest": manifest["pack_digest"],
        "source_manifest": "v0.5/delivery/MANIFEST.yml",
        "owned_files": owned,
    }
    (root / "manifest-lock.yml").write_bytes(canonical_bytes(new_lock) + b"\n")
    descriptor_unlink(
        project,
        (SKILL_RELATIVE / "install-state.json").as_posix(),
        expected_digest=None,
    )
    verified = verify(project)
    return {
        **verified,
        "outcome": "upgraded",
        "from_pack_digest": lock.get("pack_digest"),
        "to_pack_digest": manifest["pack_digest"],
    }


def installed_lock(project: Path) -> tuple[Path, dict[str, Any]]:
    root = project / SKILL_RELATIVE
    lock_path = root / "manifest-lock.yml"
    if not lock_path.exists():
        raise LifecycleError("V0.5 delivery skill is not installed")
    return root, load_strict(lock_path.read_bytes())


def verify(project: Path) -> dict[str, Any]:
    manifest = source_manifest()
    root, lock = installed_lock(project)
    if lock.get("pack_digest") != manifest["pack_digest"]:
        raise LifecycleError("installed pack digest is stale")
    owned = validated_lock_owned_files(lock, expected=manifest_owned_files(manifest))
    for relative, expected_digest in owned.items():
        path = root / relative
        if not path.exists() or sha(path) != expected_digest:
            raise LifecycleError(f"installed file mismatch: {relative}")
    return {"outcome": "verified", "pack_digest": lock["pack_digest"], "files": len(owned)}


def uninstall(
    project: Path,
    *,
    before_unlink: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    manifest = source_manifest()
    root, lock = installed_lock(project)
    if lock.get("pack_digest") != manifest["pack_digest"]:
        raise LifecycleError("installed pack digest is stale")
    owned = validated_lock_owned_files(lock, expected=manifest_owned_files(manifest))
    for relative, expected_digest in owned.items():
        path = root / relative
        if path.exists() and sha(path) != expected_digest:
            raise LifecycleError(f"refusing to remove modified manifest-owned file: {relative}")
    removed = 0
    try:
        with DescriptorTree(project) as tree:
            for relative, expected_digest in sorted(
                owned.items(),
                key=lambda item: len(Path(item[0]).parts),
                reverse=True,
            ):
                if tree.unlink(
                    (SKILL_RELATIVE / relative).as_posix(),
                    expected_digest=expected_digest,
                    missing_ok=True,
                    before_unlink=before_unlink,
                ):
                    removed += 1
            tree.unlink(
                (SKILL_RELATIVE / "manifest-lock.yml").as_posix(),
                expected_digest=sha(root / "manifest-lock.yml"),
            )
            tree.unlink(
                (SKILL_RELATIVE / "install-state.json").as_posix(),
                expected_digest=None,
                missing_ok=True,
            )
            for relative in owned_parent_directories(owned):
                tree.rmdir(relative)
            tree.rmdir(SKILL_RELATIVE.as_posix())
    except DescriptorDeleteError as error:
        raise LifecycleError(str(error)) from error
    return {"outcome": "uninstalled", "files": removed, "unrelated_preserved": root.exists()}


def migrate(project: Path, parity_receipt: Path) -> dict[str, Any]:
    manifest = source_manifest()
    receipt = load_strict(parity_receipt.read_bytes())
    if receipt.get("schema_version") != 1 or receipt.get("pilot_pack_digest") != manifest["pack_digest"] or receipt.get("semantic_parity") is not True:
        raise LifecycleError("V0.5 parity receipt does not bind this pilot pack")
    result = uninstall(project)
    return {**result, "outcome": "migrated", "parity_receipt": str(parity_receipt)}


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser()
    sub = cli.add_subparsers(dest="command", required=True)
    for command in ("install", "verify", "upgrade", "uninstall"):
        child = sub.add_parser(command)
        child.add_argument("--project", type=Path, required=True)
    child = sub.add_parser("migrate")
    child.add_argument("--project", type=Path, required=True)
    child.add_argument("--parity-receipt", type=Path, required=True)
    return cli


def main() -> int:
    args = parser().parse_args()
    try:
        project = args.project.resolve()
        if args.command == "install":
            result = install(project)
        elif args.command == "verify":
            result = verify(project)
        elif args.command == "upgrade":
            result = upgrade(project)
        elif args.command == "uninstall":
            result = uninstall(project)
        else:
            result = migrate(project, args.parity_receipt.resolve())
    except (OSError, ValueError, LifecycleError) as exc:
        print(json.dumps({"outcome": "blocked", "error": str(exc), "error_class": type(exc).__name__}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

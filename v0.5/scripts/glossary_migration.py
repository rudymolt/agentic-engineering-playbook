"""Recoverable, provenance-checked CONTEXT.md rename for managed projects.

User-owned maps and ambiguous files are reviewed through MIGRATIONS.md. This
module never infers domain boundaries or rewrites definitions.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import template_base
from playbook_state import replace_top_level_scalar

JOURNAL = ".playbook-base/.glossary-migration.json"
OLD = "CONTEXT.md"
NEW = "GLOSSARY.md"
STATE = ".playbook-state.yml"


class MigrationReview(ValueError):
    """The migration needs human reconciliation before any further upgrade."""


def read_value(path: Path) -> str | None:
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise MigrationReview(f"{path.name}: symlink requires manual glossary migration")
    if not path.exists():
        return None
    if not path.is_file():
        raise MigrationReview(f"{path.name}: expected a regular file")
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise MigrationReview(f"{path.name}: cannot read UTF-8 migration source") from error


def write_value(path: Path, value: str | None) -> None:
    """Atomic individual writes; the durable journal reconciles the group."""
    if value is None:
        path.unlink(missing_ok=True)
        return
    descriptor, name = tempfile.mkstemp(prefix=".glossary-write-", dir=path.parent)
    scratch = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value.encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            scratch.chmod(path.stat().st_mode & 0o777)
        os.replace(scratch, path)
    finally:
        scratch.unlink(missing_ok=True)


def changes(receipt: dict) -> dict[str, tuple[str | None, str | None]]:
    if set(receipt) != {"schema", "state", "content", "base", "mapping"} or receipt["schema"] != 1:
        raise MigrationReview("glossary recovery journal has an unsupported shape")
    if any(not isinstance(receipt[k], str) for k in ("state", "content", "base")):
        raise MigrationReview("glossary recovery journal has invalid source values")
    if receipt["mapping"] is not None and not isinstance(receipt["mapping"], str):
        raise MigrationReview("glossary recovery journal has an invalid map snapshot")
    record = template_base.read_provenance(receipt["state"])
    files = record.get("files", {})
    entry = files.get(OLD)
    if not entry or NEW in files or entry.get("template") not in {
        "v0.4/templates/CONTEXT.md", "v0.5/templates/CONTEXT.md"
    }:
        raise MigrationReview("CONTEXT.md: missing or ambiguous managed provenance; use the manual migration")
    if template_base.sha256_text(receipt["base"]) != entry.get("base_sha256"):
        raise MigrationReview("CONTEXT.md: pristine base is missing or edited; restore it before migration")
    files[NEW] = files.pop(OLD)
    files[NEW]["template"] = "v0.5/templates/GLOSSARY.md"
    state = template_base.upsert_provenance(receipt["state"], record)
    state = replace_top_level_scalar(state, "prereqs_required", "true")
    # Create destinations before removing originals. State is recoverable even
    # if interruption leaves either both files or only the new one.
    return {
        NEW: (None, receipt["content"]),
        f".playbook-base/{NEW}": (None, receipt["base"]),
        STATE: (receipt["state"], state),
        OLD: (receipt["content"], None),
        f".playbook-base/{OLD}": (receipt["base"], None),
    }


def migrate(project: Path, *, apply: bool = True, accept_renamed: bool = False) -> list[str]:
    """Preview or complete the domain rename; return changed project paths.

    Preflight every destination before any write. A pending journal resumes
    only when every file matches either its recorded before or after bytes.
    Local edits made during interruption are never overwritten.
    """
    journal = project / JOURNAL
    if read_value(project / "CONTEXT-MAP.md") is not None:
        raise MigrationReview("CONTEXT-MAP.md: review and migrate the map, per-context files and links using MIGRATIONS.md")
    mapping = read_value(project / "GLOSSARY-MAP.md")
    raw_journal = read_value(journal)
    if raw_journal is not None:
        try:
            receipt = json.loads(raw_journal)
            if not isinstance(receipt, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError) as error:
            raise MigrationReview("glossary recovery journal is invalid; reconcile it manually") from error
    else:
        state = read_value(project / STATE)
        if state is None:
            raise MigrationReview("missing project state")
        record = template_base.read_provenance(state)
        old = read_value(project / OLD)
        if old is None and OLD not in record.get("files", {}):
            return []
        if (mapping is not None
                and not (old is None and accept_renamed)):
            raise MigrationReview("GLOSSARY-MAP.md: reconcile the recorded root CONTEXT.md with the mapped domain layout before migration")
        adopted = old is None and accept_renamed
        if adopted:
            old = read_value(project / NEW)
        if old is None:
            raise MigrationReview("CONTEXT.md: recorded project glossary is missing; restore it or review the renamed GLOSSARY.md and use --adopt-current GLOSSARY.md")
        for relative in (NEW, f".playbook-base/{NEW}"):
            if read_value(project / relative) is not None and not adopted:
                raise MigrationReview(f"{relative}: destination already exists; reconcile both names manually")
        base = read_value(project / ".playbook-base" / OLD)
        if base is None and adopted:
            base = read_value(project / ".playbook-base" / NEW)
        if base is None:
            raise MigrationReview("CONTEXT.md: pristine base is missing; restore it before migration")
        receipt = {"schema": 1, "state": state, "content": old, "base": base, "mapping": mapping}
    try:
        planned = changes(receipt)
    except ValueError as error:
        raise MigrationReview(str(error)) from error
    if mapping != receipt["mapping"]:
        raise MigrationReview("GLOSSARY-MAP.md: changed during glossary migration; review the map before recovery")
    pending = []
    for relative, (before, after) in planned.items():
        current = read_value(project / relative)
        if current not in (before, after):
            raise MigrationReview(f"{relative}: changed during glossary migration; reconcile with the recovery journal")
        if current != after:
            pending.append(relative)
    if not apply:
        return pending
    if raw_journal is None:
        write_value(journal, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    for relative in pending:
        write_value(project / relative, planned[relative][1])
    journal.unlink()
    return pending

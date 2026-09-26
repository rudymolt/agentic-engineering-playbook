#!/usr/bin/env python3
"""Rename one current upstream skill without writing until ``--apply`` is given."""

from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".html", ".yml", ".json", ".py"}
MIGRATIONS = Path("v0.5/skills/ai-playbook-upgrade-project/MIGRATIONS.md")


class MutationError(ValueError):
    """The requested registry mutation is not safe to stage."""


class MutationReport:
    def __init__(self, files: list[Path], diff: str) -> None:
        self.files = files
        self.diff = diff


def live_surface(relative: Path) -> bool:
    """Whether a file is an eligible prose/code surface for command rewrites."""
    return (
        relative.parts[:1] == ("v0.5",)
        and relative.suffix in TEXT_SUFFIXES
        and relative != Path("v0.5/CHANGELOG.md")
        and relative != MIGRATIONS
        and "analysis" not in relative.parts
        and ".agents" not in relative.parts
        and ".playbook-base" not in relative.parts
    )


def first_mention_context(relative: Path) -> bool:
    name = relative.name
    return (
        len(relative.parts) >= 3
        and relative.parts[0:2] == ("v0.5", "10-process")
        and re.fullmatch(r"[0-9][0-9]-.*\.md", name) is not None
    ) or name.endswith("-track.md")


def command_pattern(name: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9_-])/{re.escape(name)}(?![A-Za-z0-9_-])")


def annotate_renamed_occurrence(text: str, *, start: int, old: str, new: str) -> str:
    """Add legacy context while preserving an equal code-span delimiter run."""
    end = start + len(new) + 1
    left = 0
    while start - left > 0 and text[start - left - 1] == "`":
        left += 1
    right = 0
    while end + right < len(text) and text[end + right] == "`":
        right += 1
    if left and left == right:
        start -= left
        end += right
        delimiter = "`" * left
    else:
        delimiter = "`"
    replacement = f"{delimiter}/{new}{delimiter} (formerly `/{old}`)"
    return text[:start] + replacement + text[end:]


def write_registry(root: Path, *, old: str, new: str, upstream_version: str) -> None:
    path = root / "v0.5/upstream-skills.json"
    payload = json.loads(path.read_text())
    skills = payload.get("skills")
    if not isinstance(skills, dict) or old not in skills:
        raise MutationError(f"current registry skill not found: {old}")
    if new in skills:
        raise MutationError(f"registry skill already exists: {new}")
    raw = skills[old]
    if raw.get("status", "current") != "current":
        raise MutationError(f"registry skill is not current: {old}")

    renamed: dict[str, object] = {}
    for name, entry in skills.items():
        if name != old:
            renamed[name] = entry
            continue
        updated = dict(entry)
        updated["name"] = new
        previous = list(updated.get("previous_names") or [])
        previous.append({"name": old, "upstream_version": upstream_version})
        updated["previous_names"] = previous
        upstream_path = updated.get("upstream_path")
        if isinstance(upstream_path, str) and upstream_path.endswith(f"/{old}"):
            updated["upstream_path"] = f"{upstream_path[:-len(old)]}{new}"
        renamed[new] = updated
    payload["skills"] = renamed
    path.write_text(json.dumps(payload, indent=2) + "\n")


def rewrite_surfaces(root: Path, *, old: str, new: str) -> set[Path]:
    """Rewrite eligible surfaces and return stage/track files needing durable context."""
    pattern = command_pattern(old)
    affected_context_files: set[Path] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not live_surface(relative):
            continue
        text = path.read_text()
        source_match = pattern.search(text)
        if source_match is None:
            continue
        rewritten = pattern.sub(f"/{new}", text)
        if first_mention_context(relative):
            # The first source match has no earlier replacement, so its offset is
            # still exact after substitution even when /new already appears first.
            rewritten = annotate_renamed_occurrence(
                rewritten, start=source_match.start(), old=old, new=new
            )
            affected_context_files.add(relative)
        path.write_text(rewritten)
    return affected_context_files


def non_generated_text(text: str) -> str:
    """Return text outside inventory-generator marker pairs."""
    return re.sub(
        r"<!-- generated: upstream/[^>]+ -->.*?<!-- /generated: upstream/[^>]+ -->",
        "",
        text,
        flags=re.DOTALL,
    )


def ensure_stable_context(
    root: Path, *, affected_context_files: set[Path], old: str, new: str
) -> None:
    """Keep context after generators replace a previously affected region."""
    context = f"`/{new}` (formerly `/{old}`)"
    context_pattern = re.compile(
        rf"(?P<delimiter>`+)/{re.escape(new)}(?P=delimiter) "
        rf"\(formerly `/{re.escape(old)}`\)"
    )
    for relative in sorted(affected_context_files):
        path = root / relative
        text = path.read_text()
        if context_pattern.search(non_generated_text(text)):
            continue
        generated_region = re.compile(
            r"<!-- generated: upstream/[^>]+ -->.*?<!-- /generated: upstream/[^>]+ -->",
            re.DOTALL,
        )
        insertion = f"Renamed upstream command: {context}.\n\n"
        for match in generated_region.finditer(text):
            if command_pattern(new).search(match.group()):
                path.write_text(text[:match.start()] + insertion + text[match.start():])
                break
        else:
            separator = "" if text.endswith("\n") else "\n"
            path.write_text(text + separator + f"\n{insertion}")


def run_generators(root: Path) -> None:
    for script in ("generate-upstream-inventory.py", "generate-status.py"):
        completed = subprocess.run(
            [sys.executable, str(root / "v0.5/scripts" / script), "--root", str(root)],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode:
            raise MutationError(
                f"{script} failed ({completed.returncode}): "
                f"{completed.stdout}{completed.stderr}"
            )


def draft_changelog(root: Path, *, old: str, new: str, files: list[Path]) -> None:
    path = root / "v0.5/CHANGELOG.md"
    text = path.read_text()
    marker = "## Unreleased\n"
    if marker not in text:
        raise MutationError("v0.5/CHANGELOG.md has no Unreleased section")
    draft = (
        "\n### Changed\n\n"
        f"- **Prepared upstream skill rename from `/{old}` to `/{new}`.** "
        "The helper updates the registry, eligible live surfaces, and generated inventories.\n"
        "  **Files touched:**\n"
        + "".join(f"  - `{path}`\n" for path in files)
        + "  *Why:* [Human fill in why before committing.]\n"
        "  *Replay:* maintainer-host §6.4 replay counts pending; human review required.\n"
    )
    path.write_text(text.replace(marker, marker + draft, 1))


def changed_files(before: Path, after: Path) -> tuple[list[Path], str]:
    files: list[Path] = []
    chunks: list[str] = []
    paths = sorted(path.relative_to(after) for path in after.rglob("*") if path.is_file())
    for relative in paths:
        if "__pycache__" in relative.parts or relative.suffix == ".pyc":
            continue
        old_path = before / relative
        new_path = after / relative
        old_bytes = old_path.read_bytes() if old_path.exists() else b""
        new_bytes = new_path.read_bytes() if new_path.exists() else b""
        if old_bytes == new_bytes:
            continue
        old = old_bytes.decode()
        new = new_bytes.decode()
        files.append(relative)
        chunks.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=str(relative), tofile=str(relative),
        ))
    return files, "".join(chunks)


def stage_inputs(root: Path, work: Path) -> None:
    """Copy only the rewrite and generator input set; never stage Git or frozen trees."""
    shutil.copytree(root / "v0.5", work / "v0.5", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for relative in (Path(".playbook-maintenance.yml"), Path("STATUS.md")):
        shutil.copy2(root / relative, work / relative)
    (work / "analysis").mkdir()
    shutil.copy2(root / "analysis/STATUS.md", work / "analysis/STATUS.md")
    source_results = root / "bench/results"
    if source_results.is_dir():
        shutil.copytree(source_results, work / "bench/results", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def staged(root: Path, *, old: str, new: str, upstream_version: str) -> tuple[Path, tempfile.TemporaryDirectory]:
    temporary = tempfile.TemporaryDirectory()
    work = Path(temporary.name) / "repo"
    work.mkdir()
    stage_inputs(root, work)
    write_registry(work, old=old, new=new, upstream_version=upstream_version)
    affected_context_files = rewrite_surfaces(work, old=old, new=new)
    run_generators(work)
    ensure_stable_context(work, affected_context_files=affected_context_files, old=old, new=new)
    files, _ = changed_files(root, work)
    draft_changelog(work, old=old, new=new, files=sorted(files + [Path("v0.5/CHANGELOG.md")]))
    return work, temporary


def apply(root: Path, *, old: str, new: str, upstream_version: str, apply: bool) -> MutationReport:
    """Stage the rename, returning its diff and writing only when requested."""
    old = old.removeprefix("/")
    new = new.removeprefix("/")
    if not old or not new:
        raise MutationError("skill names must be non-empty")
    work, temporary = staged(root, old=old, new=new, upstream_version=upstream_version)
    try:
        files, diff = changed_files(root, work)
        if apply:
            for relative in files:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((work / relative).read_bytes())
        return MutationReport(files, diff)
    finally:
        temporary.cleanup()


def emit_report(report: MutationReport, *, applied: bool) -> bool:
    """Write CLI output without treating a closed downstream pipe as an error."""
    try:
        if report.diff:
            sys.stdout.write(report.diff)
            if not report.diff.endswith("\n"):
                sys.stdout.write("\n")
        sys.stdout.write("Files changed:\n" if applied else "Files that would change:\n")
        for path in report.files:
            sys.stdout.write(f"{path}\n")
        sys.stdout.flush()
    except BrokenPipeError:
        with contextlib.suppress(OSError):
            sys.stdout.close()
        sys.stdout = open(os.devnull, "w")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="old", required=True, metavar="/old")
    parser.add_argument("--to", dest="new", required=True, metavar="/new")
    parser.add_argument("--upstream-version", required=True, metavar="vX.Y.Z")
    parser.add_argument("--apply", action="store_true", help="write the staged changes")
    args = parser.parse_args(argv)
    try:
        report = apply(ROOT, old=args.old, new=args.new, upstream_version=args.upstream_version, apply=args.apply)
    except MutationError as error:
        print(f"Rename refused: {error}")
        return 2
    emit_report(report, applied=args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

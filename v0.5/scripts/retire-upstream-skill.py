#!/usr/bin/env python3
"""Retire one upstream skill with a fail-closed capability-lane check."""

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

import upstream_registry


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".html", ".yml", ".json", ".py"}
MIGRATIONS = Path("v0.5/skills/ai-playbook-upgrade-project/MIGRATIONS.md")
LANE_CAPABILITIES = {
    "repository": "Read, edit, diff, and verify the repository",
    "human_decisions": "Human-owned decisions during alignment",
    "spec_and_slices": "Spec and vertical-slice contracts",
    "implementation_and_diagnosis": "Test-first implementation and diagnosis",
    "independent_verification": "Independent verification at the ladder's required rung",
    "real_environment_qa": "Real-environment QA when the ladder requires it",
    "security": "Security and secret handling",
    "state_lifecycle": "State and document lifecycle",
    "model_routing": "Stage-aware model routing",
}


class MutationError(ValueError):
    """The requested registry mutation is not safe to stage."""


class RetirementBlocked(MutationError):
    """Retiring the skill would remove the only accelerated route for a lane."""


class MutationReport:
    def __init__(self, files: list[Path], diff: str, mentions: list[tuple[Path, int]]) -> None:
        self.files = files
        self.diff = diff
        self.mentions = mentions


def live_surface(relative: Path) -> bool:
    return (
        relative.parts[:1] == ("v0.5",)
        and relative.suffix in TEXT_SUFFIXES
        and relative != Path("v0.5/CHANGELOG.md")
        and relative != MIGRATIONS
        and "analysis" not in relative.parts
        and ".agents" not in relative.parts
        and ".playbook-base" not in relative.parts
    )


def manual_routes(profile: Path) -> dict[str, str]:
    """Read the named manual routes from the stage-00 capability table."""
    rows: dict[str, str] = {}
    for line in profile.read_text().splitlines():
        if not line.startswith("|"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) != 4:
            continue
        for lane, capability in LANE_CAPABILITIES.items():
            if columns[0] == capability:
                rows[lane] = columns[2]
    return rows


def blocked_lanes(root: Path, name: str) -> list[tuple[str, str]]:
    registry = upstream_registry.load(root / "v0.5/upstream-skills.json")
    skill = registry.skills.get(name)
    if skill is None or skill.status != "current":
        raise MutationError(f"current registry skill not found: {name}")
    routes = manual_routes(root / "v0.5/10-process/prereqs-capability-profiles.md")
    blocked: list[tuple[str, str]] = []
    for lane in skill.lanes:
        current = [candidate for candidate in registry.skills.values()
                   if candidate.status == "current" and lane in candidate.lanes]
        if len(current) == 1:
            route = routes.get(lane)
            if route is None:
                raise MutationError(f"manual route unavailable for lane {lane}")
            blocked.append((lane, route))
    return blocked


def retire_registry(root: Path, *, name: str, removed_in: str) -> None:
    path = root / "v0.5/upstream-skills.json"
    payload = json.loads(path.read_text())
    raw = payload["skills"][name]
    raw["status"] = "removed"
    raw["removed_in"] = removed_in
    path.write_text(json.dumps(payload, indent=2) + "\n")


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


def remaining_mentions(root: Path, name: str) -> list[tuple[Path, int]]:
    pattern = re.compile(rf"(?<![A-Za-z0-9_-])/{re.escape(name)}(?![A-Za-z0-9_-])")
    mentions: list[tuple[Path, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if not live_surface(relative):
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                mentions.append((relative, line_number))
    return mentions


def draft_changelog(root: Path, *, name: str, removed_in: str, files: list[Path]) -> None:
    path = root / "v0.5/CHANGELOG.md"
    text = path.read_text()
    marker = "## Unreleased\n"
    if marker not in text:
        raise MutationError("v0.5/CHANGELOG.md has no Unreleased section")
    draft = (
        "\n### Changed\n\n"
        f"- **Prepared retirement of `/{name}` in {removed_in}.** The registry records the "
        "removal and generated inventories omit the retired skill; remaining live prose needs "
        "human review.\n"
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


def staged(root: Path, *, name: str, removed_in: str) -> tuple[Path, tempfile.TemporaryDirectory, list[tuple[Path, int]]]:
    temporary = tempfile.TemporaryDirectory()
    work = Path(temporary.name) / "repo"
    work.mkdir()
    stage_inputs(root, work)
    retire_registry(work, name=name, removed_in=removed_in)
    run_generators(work)
    mentions = remaining_mentions(work, name)
    files, _ = changed_files(root, work)
    draft_changelog(work, name=name, removed_in=removed_in, files=sorted(files + [Path("v0.5/CHANGELOG.md")]))
    return work, temporary, mentions


def apply(root: Path, *, name: str, removed_in: str, apply: bool, accept_manual_route: bool) -> MutationReport:
    """Stage retirement and write it only after an explicit override when needed."""
    name = name.removeprefix("/")
    blocked = blocked_lanes(root, name)
    if blocked and not accept_manual_route:
        details = "; ".join(f"{lane}: {route}" for lane, route in blocked)
        raise RetirementBlocked(f"retirement would leave only a manual route — {details}")
    work, temporary, mentions = staged(root, name=name, removed_in=removed_in)
    try:
        files, diff = changed_files(root, work)
        if apply:
            for relative in files:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((work / relative).read_bytes())
        return MutationReport(files, diff, mentions)
    finally:
        temporary.cleanup()


def emit_report(report: MutationReport, *, applied: bool, name: str) -> bool:
    """Write CLI output without treating a closed downstream pipe as an error."""
    try:
        if report.diff:
            sys.stdout.write(report.diff)
            if not report.diff.endswith("\n"):
                sys.stdout.write("\n")
        sys.stdout.write("Files changed:\n" if applied else "Files that would change:\n")
        for path in report.files:
            sys.stdout.write(f"{path}\n")
        sys.stdout.write(f"Remaining live mentions of /{name}:\n")
        for path, line in report.mentions:
            sys.stdout.write(f"{path}:{line}\n")
        sys.stdout.flush()
    except BrokenPipeError:
        with contextlib.suppress(OSError):
            sys.stdout.close()
        sys.stdout = open(os.devnull, "w")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", metavar="NAME")
    parser.add_argument("--removed-in", required=True, metavar="V0.5.N")
    parser.add_argument("--apply", action="store_true", help="write the staged changes")
    parser.add_argument("--accept-manual-route", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = apply(
            ROOT, name=args.name, removed_in=args.removed_in, apply=args.apply,
            accept_manual_route=args.accept_manual_route,
        )
    except RetirementBlocked as error:
        print(f"Retirement refused: {error}")
        return 2
    except MutationError as error:
        print(f"Retirement failed: {error}")
        return 2
    emit_report(report, applied=args.apply, name=args.name.removeprefix("/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

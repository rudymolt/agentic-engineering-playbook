#!/usr/bin/env python3
"""Safely bootstrap a project with the current V0.5 playbook."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import template_base  # noqa: E402
from playbook_state import validate_cadences, validate_state  # noqa: E402

ROOT_TEMPLATE_FILES = {
    "CLAUDE.md": "CLAUDE.md",
    "AGENTS.md": "AGENTS.md",
    "CONTEXT.md": "CONTEXT.md",
    ".playbook-state.yml": ".playbook-state.yml",
    "playbook-cadences.yml": "playbook-cadences.yml",
    "retro-template.md": "retro-template.md",
    "field-report.md": "field-report.md",
}
DIRECTORY_TEMPLATES = {
    "planning-template": "planning",
    "archive": "archive",
}
UI_TEMPLATE_FILES = (
    "DESIGN-GLOSSARY.md",
    "ui-kitchen-sink.html",
    "frontend-design-language-guide.html",
)
LOCAL_SKILLS = template_base.MANAGED_SKILLS
OPTIONAL_LOCAL_SKILLS = tuple(
    skill.name
    for skill in template_base._registry.load().skills_for("playbook")
    if skill.status == "current" and skill.install_by_default is False
)
DELIVERY_SKILL = Path(".agents/skills/ai-playbook-deliver")


class BootstrapReport:
    def __init__(self) -> None:
        self.changed_files: list[str] = []
        self.manual_reviews: list[str] = []


def current_version(playbook_root: Path) -> str:
    """Return the version implemented by this checkout.

    Bootstrap and upgrade must share one source even while a release entry is
    still headed ``Unreleased``; otherwise a same-checkout bootstrap is born
    stale and its first upgrade rewrites provenance immediately.
    """
    return template_base.CURRENT_VERSION


def resolve_text(data: bytes, playbook_root: Path, project_name: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return template_base.render(text, playbook_root, project_name).encode("utf-8")


def record_write(path: Path, data: bytes, report: BootstrapReport) -> None:
    if path.exists() and path.read_bytes() == data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    value = str(path)
    if value not in report.changed_files:
        report.changed_files.append(value)


def install_file(
    source: Path,
    target: Path,
    playbook_root: Path,
    project_name: str,
    report: BootstrapReport,
) -> None:
    desired = resolve_text(source.read_bytes(), playbook_root, project_name)
    if not target.exists():
        record_write(target, desired, report)
        return
    if target.read_bytes() != desired and not compatible_existing_file(
        target,
        target.read_bytes(),
        playbook_root,
    ):
        report.manual_reviews.append(
            f"{target}: preserve existing content and merge the playbook template explicitly"
        )


def compatible_existing_file(target: Path, data: bytes, playbook_root: Path) -> bool:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    name = target.name
    if name == "CLAUDE.md":
        return all(
            token in text
            for token in (
                "feature request is not a coding instruction",
                str(playbook_root / "v0.5"),
                "**State file:**",
                "**Model routing:**",
            )
        )
    if name == "AGENTS.md":
        return all(
            token in text
            for token in (
                str(playbook_root / "v0.5" / "AGENT-DIGEST.md"),
                str(playbook_root / "v0.5" / "10-process" / "01-align.md"),
                "/whats-next",
            )
        )
    if name == "CONTEXT.md":
        return bool(text.strip())
    if name == "playbook-cadences.yml":
        return "cadences:" in text
    if name in UI_TEMPLATE_FILES:
        return bool(text.strip())
    if name == "README.md" and target.parent.name == "planning":
        return "planning/" in text and "active feature" in text.lower()
    if name == "README.md" and target.parent.name == "archive":
        return "archive/" in text and "agents must not read" in text.lower()
    if name == "STATUS.md" and target.parent.name == "planning":
        return "## Active features" in text
    if name == "STATUS.md" and target.parent.name == "archive":
        return "archived" in text.lower()
    return False


def install_tree(
    source: Path,
    target: Path,
    playbook_root: Path,
    project_name: str,
    report: BootstrapReport,
) -> None:
    for source_file in sorted(path for path in source.rglob("*") if path.is_file()):
        install_file(
            source_file,
            target / source_file.relative_to(source),
            playbook_root,
            project_name,
            report,
        )


def install_delivery_skill(
    project: Path,
    playbook_root: Path,
    report: BootstrapReport,
) -> None:
    """Install the manifest-owned delivery runtime without blending editions."""

    lifecycle = playbook_root / "v0.5" / "delivery" / "scripts" / "lifecycle.py"
    if not lifecycle.is_file():
        raise FileNotFoundError(f"V0.5 delivery lifecycle not found: {lifecycle}")
    lock = project / DELIVERY_SKILL / "manifest-lock.yml"
    existed = lock.exists()
    completed = subprocess.run(
        [sys.executable, str(lifecycle), "install", "--project", str(project)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stdout.strip() or completed.stderr.strip()
        report.manual_reviews.append(
            f"{DELIVERY_SKILL}: manifest-owned delivery install blocked: {detail}"
        )
        return
    if not existed:
        report.changed_files.append(str(lock))


def replace_state_scalar(text: str, key: str, value: str) -> str:
    pattern = rf"(?m)^{re.escape(key)}:\s*[^\n]*(?:\n|$)"
    if not re.search(pattern, text):
        raise ValueError(f"state template is missing required key: {key}")
    return re.sub(pattern, f"{key}: {value}\n", text, count=1)


def replace_nested_state_scalar(text: str, key: str, value: str) -> str:
    pattern = rf"(?m)^  {re.escape(key)}:\s*[^\n]*(?:\n|$)"
    if not re.search(pattern, text):
        raise ValueError(f"state template is missing required key: {key}")
    return re.sub(pattern, f"  {key}: {value}\n", text, count=1)


def replace_null_nested_state_scalar(text: str, key: str, value: str) -> str:
    pattern = rf"(?m)^  {re.escape(key)}:\s*([^\s#]+)"
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"state template is missing required key: {key}")
    if match.group(1) not in {"null", "~"}:
        return text
    return replace_nested_state_scalar(text, key, value)


def state_version(text: str) -> str | None:
    match = re.search(r"(?m)^playbook_version:\s*([^\s#]+)", text)
    return match.group(1) if match else None


def record_base_snapshots(
    project: Path,
    playbook_root: Path,
    project_name: str,
    version: str,
    report: BootstrapReport,
) -> None:
    """Record the pristine rendered base of every managed file present in the
    project, so future upgrades can three-way merge instead of guessing what
    counts as boilerplate. The base is the rendered template even when an
    existing project file was preserved: the divergence *is* the
    customisation the merge must carry forward."""
    entries: dict[str, dict[str, str]] = {}
    for relative, template_relative in template_base.managed_files(playbook_root).items():
        if not (project / relative).exists():
            continue
        rendered = template_base.render(
            (playbook_root / template_relative).read_text(), playbook_root, project_name
        )
        record_write(project / template_base.BASE_DIR / relative, rendered.encode(), report)
        entries[relative] = template_base.provenance_entry(
            template_relative, version, rendered
        )
    if not entries:
        return
    record_write(
        project / template_base.BASE_DIR / "README.md",
        template_base.BASE_README.encode(),
        report,
    )
    state_path = project / ".playbook-state.yml"
    state = state_path.read_text()
    record = {"schema": template_base.PROVENANCE_SCHEMA, "project_name": project_name, "files": entries}
    record_write(state_path, template_base.upsert_provenance(state, record).encode(), report)


def bootstrap_project(
    project: Path,
    playbook_root: Path,
    *,
    project_name: str,
    ui: str,
    ci: str,
    today: date | None = None,
) -> BootstrapReport:
    today = today or date.today()
    if not project_name or re.search(r"[\x00-\x1f\x7f]", project_name):
        raise ValueError("project_name must be a non-empty single line without control characters")
    project = project.resolve()
    playbook_root = playbook_root.resolve()
    templates = playbook_root / "v0.5" / "templates"
    if ui not in {"no", "defaults"}:
        raise ValueError("ui must be 'no' or 'defaults'")
    if ci not in {"copy", "existing"}:
        raise ValueError("ci must be 'copy' or 'existing'")
    if not templates.is_dir():
        raise FileNotFoundError(f"playbook templates not found: {templates}")
    project.mkdir(parents=True, exist_ok=True)
    report = BootstrapReport()
    info = project.stat()
    report.project_identity = {"resolved": str(project), "device": info.st_dev, "inode": info.st_ino}
    version = current_version(playbook_root)

    state_path = project / ".playbook-state.yml"
    existing_state = state_path.read_text() if state_path.exists() else None
    if existing_state is not None and state_version(existing_state) not in {version, "null", None}:
        raise ValueError(
            "project already records another playbook version; use /ai-playbook-upgrade-project"
        )

    for source_name, target_name in ROOT_TEMPLATE_FILES.items():
        if target_name == ".playbook-state.yml" and state_path.exists():
            continue
        install_file(
            templates / source_name,
            project / target_name,
            playbook_root,
            project_name,
            report,
        )
    for source_name, target_name in DIRECTORY_TEMPLATES.items():
        install_tree(
            templates / source_name,
            project / target_name,
            playbook_root,
            project_name,
            report,
        )

    if ui == "defaults":
        for name in UI_TEMPLATE_FILES:
            install_file(templates / name, project / name, playbook_root, project_name, report)

    ci_path = project / "ci-gates.md"
    if ci == "copy":
        install_file(templates / "ci-gates.md", ci_path, playbook_root, project_name, report)
    elif not ci_path.exists():
        report.manual_reviews.append(
            "ci-gates.md: map the project's existing CI gates or record an explicit human deferral"
        )

    for skill_name in LOCAL_SKILLS:
        source = playbook_root / "v0.5" / "skills" / skill_name
        if source.is_dir():
            install_tree(
                source,
                project / ".agents" / "skills" / skill_name,
                playbook_root,
                project_name,
                report,
            )
    install_delivery_skill(project, playbook_root, report)

    gitignore_path = project / ".gitignore"
    gitignore = gitignore_path.read_bytes().decode() if gitignore_path.exists() else ""
    for rule in (".playbook-routing/", "/.playbook-config-*"):
        if not re.search(rf"(?m)^{re.escape(rule)}\r?$", gitignore):
            gitignore += ("\n" if gitignore and not gitignore.endswith("\n") else "") + rule + "\n"
    record_write(gitignore_path, gitignore.encode(), report)

    record_base_snapshots(project, playbook_root, project_name, version, report)

    state = state_path.read_text()
    if state_version(state) == "null":
        state = replace_nested_state_scalar(state, "no_ui", "true" if ui == "no" else "false")
        # Baseline the recurring time cadences at the bootstrap date so they can
        # fire on schedule even before the activity has ever been performed.
        baseline_keys = ["retro", "learnings_refresh"]
        if ui == "defaults":
            baseline_keys.append("kitchen_sink_drift_audit")
        for key in baseline_keys:
            state = replace_null_nested_state_scalar(state, key, today.isoformat())
        if not report.manual_reviews:
            state = replace_state_scalar(state, "playbook_version", version)
            state = replace_state_scalar(state, "last_upgraded", today.isoformat())
        record_write(state_path, state.encode(), report)

    if report.changed_files:
        completed = subprocess.run(
            [
                sys.executable,
                str(playbook_root / "v0.5" / "scripts" / "compute-status.py"),
                str(project),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError("status initialization failed:\n" + completed.stdout + completed.stderr)

    # Schema check before certifying: fresh template installs always pass;
    # this guards the preserve-existing-content paths, where a malformed
    # pre-existing state file must surface as review work, not be stamped over.
    cadences_path = project / "playbook-cadences.yml"
    problems = validate_state(state_path.read_text())
    if cadences_path.exists():
        problems += validate_cadences(cadences_path.read_text())
    report.manual_reviews.extend(
        f"schema: {problem.render()}" for problem in problems if not problem.advisory
    )
    return report


def print_plan(project: Path, playbook_root: Path, *, ui: str, ci: str) -> None:
    templates = playbook_root.resolve() / "v0.5" / "templates"
    if not templates.is_dir():
        raise FileNotFoundError(f"playbook templates not found: {templates}")
    print("Bootstrap plan:")
    for target_name in ROOT_TEMPLATE_FILES.values():
        action = "preserve/review" if (project / target_name).exists() else "create"
        print(f"{action}: {target_name}")
    for target_name in DIRECTORY_TEMPLATES.values():
        action = "merge safely" if (project / target_name).exists() else "create"
        print(f"{action}: {target_name}/")
    print("UI: no UI" if ui == "no" else "UI: copy defaults, then run the design interview")
    if ci == "copy":
        action = "preserve/review" if (project / "ci-gates.md").exists() else "create"
        print(f"CI: {action} ci-gates.md")
    else:
        print("CI: preserve and verify the existing mapping")
    print("Skills: install local skills plus manifest-owned /ai-playbook-deliver under .agents/skills/")
    print("Optional skills (not installed): " + (", ".join(OPTIONAL_LOCAL_SKILLS) or "none"))
    print("Provenance: record pristine template bases under .playbook-base/ (committed, machine-owned)")
    gitignore_path = project / ".gitignore"
    gitignore = gitignore_path.read_bytes().decode() if gitignore_path.exists() else ""
    for rule in (".playbook-routing/", "/.playbook-config-*"):
        if re.search(rf"(?m)^{re.escape(rule)}\r?$", gitignore):
            print(f"Gitignore: {rule} already ignored")
        else:
            print(f"Gitignore: add {rule} to .gitignore")
    print("Finish: initialize status (cadence baselines stamped today), then run stage 00 cold path")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--playbook-path", required=True, type=Path)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--ui", required=True, choices=("no", "defaults"))
    parser.add_argument("--ci", required=True, choices=("copy", "existing"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--preferences-dir", type=Path)
    parser.add_argument("--preset", help="Named personal seed; omission uses saved personal defaults.")
    parser.add_argument("--seed-revision", help="Exact seed_revision from the read-only bootstrap plan; required for seeded Apply.")
    parser.add_argument("--discovery-command", help="JSON argv for the current-availability adapter; no model launch.")
    parser.add_argument("--custom-bindings-dir", type=Path)
    parser.add_argument("--now", help="Fixture clock only.")
    args = parser.parse_args(argv)
    from playbook_config import ConfigError, public_error_message, strict_json
    from bootstrap_seed import apply_seed, preview_seed

    def discover(request):
        command = strict_json(args.discovery_command or "null")
        if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
            raise ConfigError("Personal seeding requires a current-availability adapter JSON argv; preview again after supplying it.")
        result = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        if result.returncode:
            raise ConfigError("Seed discovery failed; restore the adapter and preview again. No substitute.")
        return strict_json(result.stdout)

    clock = (lambda: args.now) if args.now else None
    seed = None
    try:
        if args.preset and args.preferences_dir is None:
            raise ConfigError("A named preset requires an explicit external personal preferences directory.")
        if args.preferences_dir is not None:
            seed = preview_seed(args.project, args.preferences_dir, discover, clock, args.preset, args.custom_bindings_dir)
        if args.apply and seed is not None and args.seed_revision != seed["seed_revision"]:
            raise ConfigError("Seed approval is missing or changed; rerun the read-only bootstrap plan and approve its exact seed_revision.")
    except (ConfigError, OSError, UnicodeError) as error:
        print("bootstrap seed blocked: " + public_error_message(error), file=sys.stderr)
        return 2
    if not args.apply:
        try:
            print_plan(args.project, args.playbook_path, ui=args.ui, ci=args.ci)
            if seed is not None:
                print("Configuration seed (create .playbook-config.json; no personal write):")
                print(json.dumps(seed, sort_keys=True, indent=2))
        except FileNotFoundError as error:
            print(f"bootstrap plan failed: {error}", file=sys.stderr)
            return 1
        return 0
    try:
        report = bootstrap_project(
            args.project,
            args.playbook_path,
            project_name=args.project_name,
            ui=args.ui,
            ci=args.ci,
        )
        if seed is not None:
            if report.manual_reviews:
                raise ConfigError("Bootstrap requires review; personal configuration was not seeded. Preserve partial project changes and resolve reviews first.")
            apply_seed(args.project, args.preferences_dir, discover, seed, clock, args.custom_bindings_dir,
                       report.project_identity)
            report.changed_files.append(str(args.project / ".playbook-config.json"))
    except (OSError, ValueError, RuntimeError) as error:
        print("bootstrap failed: " + public_error_message(error), file=sys.stderr)
        if seed is not None:
            print("Requested seeded setup is incomplete; bootstrap files may already be initialized. Inspect the diff and retained recovery evidence before retrying.", file=sys.stderr)
        else:
            print("No certification completed; safe partial changes may remain, so inspect the diff.", file=sys.stderr)
        return 1
    for changed in report.changed_files:
        print(f"changed: {changed}")
    for review in report.manual_reviews:
        print(f"manual review: {review}")
    if report.manual_reviews:
        print("Safe bootstrap changes applied, but project setup is incomplete.")
        return 2
    print("Playbook files initialized; run stage 00 cold path before feature work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

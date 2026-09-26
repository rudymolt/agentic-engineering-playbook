#!/usr/bin/env python3
"""Create a controlled notes CLI and its project-owned verification route.

This is an isolated fixture, not a universal application-harness generator.
Real projects use the evidence-led skill procedure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TEMPLATES = Path(__file__).with_name("fixtures") / "verification-harness"


def _write_new(path: Path, content: str) -> None:
    if path.exists() and path.read_text() != content:
        raise ValueError(f"refusing to replace customized fixture file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _assert_writable(paths: dict[Path, str]) -> None:
    """Reject every conflicting target before this fixture writes anything."""
    for path, content in paths.items():
        if path.exists() and (not path.is_file() or path.read_text() != content):
            raise ValueError(f"refusing to replace customized fixture file: {path}")


def create(project: Path, app: str = "fixture-app") -> Path:
    """Generate instructions that reuse a separate application's public CLI."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", app):
        raise ValueError("app must be a safe lowercase slug")
    root = project / ".agents" / "skills" / f"verify-{app}"
    files = {
        project / app / "cli.py": (TEMPLATES / "cli.py").read_text(),
        project / app / "instance.json": json.dumps(
            {"instance": app, "revision": f"{app}-revision-1", "ready": True}
        ) + "\n",
        root / "target.json": json.dumps(
            {"cli": f"../../../{app}/cli.py", "instance": app, "revision": f"{app}-revision-1"}
        ) + "\n",
    }
    for script in ("doctor.py", "drive.py", "cleanup.py"):
        files[root / script] = (TEMPLATES / script).read_text()
    files[root / "features" / "README.md"] = (
        "# Fixture feature map\n\n"
        "Coverage: three controlled notes CLI behaviors; fixture only, not PILOT-01.\n"
        "Known omissions: consuming projects, services, UI, and cross-host validation.\n\n"
        "- [create-note](create-note.md)\n- [list-notes](list-notes.md)\n"
        "- [reject-broken](reject-broken.md)\n"
    )
    feature_details = {
        "create-note": ("create a note", "create a note, then observe it through a separate list process"),
        "list-notes": ("list notes", "create two notes, then observe their order through list"),
        "reject-broken": ("reject invalid input", "reject an empty note with exit 1 and observe unchanged state"),
    }
    for feature, (purpose, expected) in feature_details.items():
        files[root / "features" / f"{feature}.md"] = (
            f"# {feature}\n\n**Purpose:** {purpose}.\n\n"
            f"**Entry point:** {app}/cli.py public create/list commands.\n\n"
            "**Prerequisites:** follow Launch and Doctor in [the generated route](../SKILL.md).\n\n"
            f"**Drive:** from the harness directory, `python3 drive.py {feature}`.\n\n"
            f"**Expected observation and effects:** {expected}; each run owns a fresh "
            "notes file, removes that file on exit, and retains command outputs.\n\n"
            "**Limitations:** fixture only; no consuming-project claim.\n\n"
            "**Last verification:** not yet run for this generated project.\n"
        )
    files[root / "SKILL.md"] = (
        f"---\nname: verify-{app}\n"
        "description: Run the selected project-owned controlled notes CLI verification route.\n---\n\n"
        f"# verify-{app}\n\n"
        "## Launch\n\n"
        "From this fixture project's root, enter the harness directory once and "
        "set these variables in the same shell for all steps:\n\n"
        f"```bash\ncd .agents/skills/verify-{app}\n"
        "export VERIFY_HARNESS_AUTH=fixture-test-authorized\n"
        "export VERIFY_EVIDENCE_DIR=evidence\n"
        "```\n\n"
        f"The target is `../../../{app}/cli.py` with identity/revision pinned in "
        "`target.json`. It runs per command; no daemon or network is used. The auth "
        "value is a public test marker, not a credential. Python 3.9+ and local "
        "filesystem access are the only dependencies. Drive reuses the target's "
        "public `create` and `list` commands, each in a separate process.\n\n"
        "## Doctor\n\n"
        "`python3 doctor.py`\n\n"
        "Stable exits: `0` means observed readiness, `1` means command/error failure, "
        "`2` means blocked prerequisites requiring the printed correction. Readiness "
        "is not correctness: Doctor queries the application's `status` command for "
        "identity, revision, auth, and readiness; it does not exercise features. "
        "It never seeds data, repairs configuration, resets state, or kills processes. "
        "Side effects: it may create the evidence directory and writes/deletes a "
        "unique probe there. It prints status to stdout/stderr; no network or "
        "application logging writes occur.\n\n"
        "## Drive\n\n"
        "`python3 drive.py create-note`\n\n"
        "Other mapped commands: `python3 drive.py list-notes` and "
        "`python3 drive.py reject-broken`. Drive checks readiness again, allocates "
        "an exclusive `.owned-run` marker and unique owned `.runs/<run-id>/` state, "
        "invokes the application, verifies persisted effects, and cleans that state "
        "even on failure. Exit `0` is a verified behavior, `1` is failure. One driver "
        "at a time. A pre-existing marker is blocked without deletion.\n\n"
        "After unexpected failure, retain the failed artifact, rerun Doctor, and "
        "restore known test state before continuing: check Cleanup succeeds and "
        "the run's owned state is gone. Investigate an unknown marker instead of "
        "deleting it. Each next Drive starts with fresh isolated empty state. For "
        "the authorized persistence-fault exercise, "
        "`FIXTURE_BEHAVIOR_BROKEN=1 python3 drive.py create-note` must fail despite "
        "healthy Doctor; the one-command environment override ends on return. "
        "Rerun Doctor and Cleanup before a normal Drive.\n\n"
        "## Evidence\n\n"
        "Keep `evidence/<feature>-<run-id>.json` after cleanup: unique success/failure "
        "records retain observed target identity/revision, timestamps, public commands, "
        "exit codes and outputs. Each accepted run replaces only its feature entry's "
        "Last verification line with the latest relative artifact locator. Failures "
        "never grant verification credit or overwrite prior evidence. For report-only "
        "inspection use `python3 drive.py <feature> --report-only`: it retains the "
        "same evidence without editing Last verification. Complete maintenance "
        "record updates belong to separately authorized stage acceptance.\n\n"
        "## Cleanup\n\n"
        "`python3 cleanup.py`\n\n"
        "Confirms no owned marker or run state remains; blocks unknown leftovers "
        "with exit `2`. It deletes nothing. Drive removes only its own isolated "
        "state and marker; application source/configuration, unrelated resources, "
        "and evidence survive. Exit `1` means an invocation/error failure.\n"
    )
    files[root / "agents" / "openai.yaml"] = (
        "interface:\n"
        f"  display_name: Verify {app}\n"
        "  short_description: Run the selected project-owned verification route\n"
        f"  default_prompt: Use $verify-{app} to run the project-owned verification route.\n"
    )
    _assert_writable(files)
    for path, content in files.items():
        _write_new(path, content)
    return root


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--app", default="fixture-app")
    args = parser.parse_args()
    print(create(args.project, args.app))

#!/usr/bin/env python3
"""Link and file-reference integrity checks for the current playbook trees.

Verifies that every relative markdown link, HTML href/src, and backticked file
reference in skill instructions resolves to a real file, so a rename or delete
turns CI red instead of rotting silently.

Scope: the top-level entry files plus v0.5/, bench/, and references/. The
frozen v0.1/ and v0.2/ trees, analysis/ (planning docs, historical by design),
bench/results/, and bench/profiles/ (gitignored built trial-profile trees whose
links resolve at their materialised depth, not from this repo layout) are
excluded. Inline markdown links only — reference-style
`[text]: path` definitions are not used in these trees. Anchor targets
(file.md#section) are checked for the file, not the anchor; v0.5 HTML anchors
are covered by check-interactive-docs.py.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

TOP_LEVEL_FILES = ("README.md", "AGENTS.md", "index.html")
SCAN_TREES = ("v0.5", "bench", "references")
EXCLUDED_DIR_NAMES = {"__pycache__", "node_modules", ".git", "backups"}
EXCLUDED_REL_PREFIXES = (("bench", "results"), ("bench", "profiles"))

# Intentional placeholders (worked examples and patterns, not real files).
# Each entry must remain referenced somewhere AND must not resolve to a real
# file — either violation fails the check, so this list cannot rot.
ALLOWED_PLACEHOLDERS = frozenset({
    "XXXX-short-title.md",
    "0007-caching-strategy.md",
    "components/term.md",
})

# Directory heads that bootstrap creates in a target project. In playbook prose
# they are project-relative, never references into this repository's root.
PROJECT_LAYOUT_HEADS = frozenset({"planning", "archive", "docs", ".agents", ".playbook-base"})

MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_REF_RE = re.compile(r"""(?:href|src)=["']([^"']+)["']""")
SKILL_FILE_RE = re.compile(r"`([A-Za-z0-9_.{}/-]+\.(?:py|md|yml|yaml|html))`")
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "javascript:", "data:", "tel:")


def scan_files(root: Path) -> list[Path]:
    files = [root / name for name in TOP_LEVEL_FILES if (root / name).is_file()]
    for tree in SCAN_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".md", ".html"} or not path.is_file():
                continue
            rel = path.relative_to(root).parts
            if any(part in EXCLUDED_DIR_NAMES for part in rel):
                continue
            if any(rel[: len(prefix)] == prefix for prefix in EXCLUDED_REL_PREFIXES):
                continue
            files.append(path)
    return files


def is_checkable(target: str) -> bool:
    # Leading "/" means site-root-relative (GitHub Pages) or a worked example of
    # an absolute path — neither resolves against the repo tree.
    if not target or target.startswith(("#", "/")) or "{" in target:
        return False
    return not target.lower().startswith(EXTERNAL_PREFIXES)


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def extract_references(path: Path, text: str) -> list[tuple[int, str]]:
    """(line, target) pairs for every checkable reference in the file."""
    if path.suffix == ".md":
        pattern = MD_LINK_RE
    else:
        pattern = HTML_REF_RE
    refs = []
    for match in pattern.finditer(text):
        target = strip_anchor(match.group(1))
        if is_checkable(target):
            refs.append((text.count("\n", 0, match.start()) + 1, target))
    return refs


def skill_reference_candidates(path: Path, target: str, root: Path) -> list[Path]:
    """Resolution candidates for backticked file references in SKILL.md.

    Skills speak about playbook files and about files in the *target project*;
    project-relative names resolve against the templates that create them, so
    a renamed template breaks every skill that mentions it.
    """
    v03 = root / "v0.5"
    templates = v03 / "templates"
    candidates = [
        path.parent / target,
        v03 / target,
        root / target,
        v03 / "scripts" / target,
        templates / target,
    ]
    if target.startswith("planning/"):
        candidates.append(templates / "planning-template" / target[len("planning/"):])
    # `.agents/skills/...` is where bootstrap installs the playbook-local skills
    # in a target project; the sources live under v0.5/skills/.
    if target.startswith(".agents/skills/"):
        candidates.append(v03 / "skills" / target[len(".agents/skills/"):])
    return candidates


def prose_reference_anchored(path: Path, target: str, root: Path) -> bool:
    """True when a prose backtick reference points into a directory that really
    exists (relative to the file, v0.5/, or the repo root) — meaning the full
    path is checkable. References into hypothetical trees (`docs/adr/...`,
    worked-example project layouts like `meettrack/...`) have no such anchor
    and are skipped rather than reported."""
    head = target.split("/", 1)[0]
    if head == "..":
        return True
    if head in PROJECT_LAYOUT_HEADS:
        # The repository runs its own playbook, so it carries a real
        # planning/, archive/, docs/, and .agents/ at the root. Playbook prose
        # that uses those heads describes the *target project's* layout, so the
        # root copy must not turn worked examples into checkable references.
        return any((base / head).is_dir() for base in (path.parent, root / "v0.5"))
    return any((base / head).is_dir() for base in (path.parent, root / "v0.5", root))


def check_repo(root: Path, placeholders: frozenset[str] = ALLOWED_PLACEHOLDERS,
               ) -> tuple[list[str], int, int]:
    """Return (problems, files_scanned, references_checked)."""
    problems: list[str] = []
    checked = 0
    placeholder_referenced: dict[str, bool] = {entry: False for entry in placeholders}
    files = scan_files(root)

    for path in files:
        text = path.read_text(errors="ignore")
        rel = path.relative_to(root)
        for line, target in extract_references(path, text):
            checked += 1
            resolved = (path.parent / target).exists()
            if target in placeholders:
                placeholder_referenced[target] = True
                if resolved:
                    problems.append(
                        f"{rel}:{line}: allowlisted placeholder '{target}' now matches a real "
                        "file — remove it from ALLOWED_PLACEHOLDERS in check-links.py"
                    )
                continue
            if not resolved:
                problems.append(f"{rel}:{line}: broken link '{target}' (missing)")

        # Backticked file references. SKILL.md files are checked strictly,
        # including bare names (skills routinely name target-project files,
        # resolved via the templates that create them). Other markdown is
        # checked only for path-shaped references anchored in a real directory
        # — prose describing hypothetical trees (`docs/adr/...`, fixture
        # project layouts) is skipped, not reported. CHANGELOG.md is exempt:
        # historical entries name files as they were at the time.
        if path.suffix == ".md" and path.name != "CHANGELOG.md":
            is_skill = path.name == "SKILL.md"
            for match in SKILL_FILE_RE.finditer(text):
                target = match.group(1)
                if not is_checkable(target):
                    continue
                if not is_skill and ("/" not in target
                                     or not prose_reference_anchored(path, target, root)):
                    continue
                checked += 1
                if not any(c.exists() for c in skill_reference_candidates(path, target, root)):
                    line = text.count("\n", 0, match.start()) + 1
                    problems.append(
                        f"{rel}:{line}: file reference '{target}' resolves to nothing "
                        "(checked the file's dir, v0.5/, repo root, v0.5/scripts/, v0.5/templates/)"
                    )

    for entry, referenced in sorted(placeholder_referenced.items()):
        if not referenced:
            problems.append(
                f"allowlist: placeholder '{entry}' is no longer referenced anywhere — "
                "remove it from ALLOWED_PLACEHOLDERS in check-links.py"
            )

    return problems, len(files), checked


def main() -> int:
    problems, files_scanned, references_checked = check_repo(ROOT)
    if problems:
        print("Link integrity checks failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(
        f"Link integrity checks passed: {references_checked} references across "
        f"{files_scanned} files, placeholder allowlist current."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

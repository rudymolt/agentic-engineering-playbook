#!/usr/bin/env python3
"""Reject private-edition residue and personal identifiers in the public tree."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKIP_PARTS = {".git", ".context", "__pycache__"}
OLD_EDITIONS = {"v0.1", "v0.2", "v0.3", "v0.4", "delivery-pilot"}
PRIVATE_MARKERS = re.compile(
    r"ru(?:comps|champs|ops)|\brud[-_]?\d+\b|/(?:Users|home)/|"
    + "ai-engineering-playbook" + "-private|" + "rudy" + "molt|" + r"\bto" + "m" + r"\b",
    re.IGNORECASE,
)
EMAIL = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
ALLOWED_EMAILS = {"git@github.com"}
ALLOWED_DOMAINS = {"example.com", "example.invalid", "users.noreply.github.com"}


def problems(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            found.append(f"{relative}: symbolic link requires explicit review")
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            found.append(f"{relative}: non-regular file")
            continue
        if relative.parts[0] in OLD_EDITIONS:
            found.append(f"{relative}: old edition tree")
            continue
        if path.suffix == ".pyc":
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            found.append(f"{relative}: non-text file requires explicit review")
            continue
        for number, line in enumerate(content.splitlines(), 1):
            if PRIVATE_MARKERS.search(line):
                found.append(f"{relative}:{number}: private marker or personal path")
            for match in EMAIL.finditer(line):
                value = match.group(0).lower()
                domain = match.group(2).lower()
                if value not in ALLOWED_EMAILS and domain not in ALLOWED_DOMAINS:
                    found.append(f"{relative}:{number}: non-placeholder email address")
    return found


def main() -> int:
    failures = problems(ROOT)
    if failures:
        print("Public-content checks failed:")
        for failure in failures:
            print("- " + failure)
        return 1
    print("Public-content checks passed: one edition, no private markers, personal paths, or non-placeholder email addresses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Identify an exact published Playbook release without guessing from prose."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


PUBLIC_REPOSITORY = "https://github.com/" + "rudy" + "molt/agentic-engineering-playbook.git"
RELEASE_TAG = re.compile(r"v0\.5\.\d+\Z")
GIT_TIMEOUT_SECONDS = 10


def git_output(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def published_tag_refs(tag: str) -> tuple[str, str] | None:
    """Read the public repository's exact annotated tag object and commit."""
    try:
        completed = subprocess.run(
            [
                "git", "ls-remote", "--tags", PUBLIC_REPOSITORY,
                f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode:
        return None
    refs = {}
    for line in completed.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
            refs[parts[1]] = parts[0]
    tag_object = refs.get(f"refs/tags/{tag}")
    commit = refs.get(f"refs/tags/{tag}^{{}}")
    return (tag_object, commit) if tag_object and commit else None


def clean_checkout_head(playbook_root: Path) -> str | None:
    """Return the HEAD of a clean, whole Playbook checkout."""
    root = playbook_root.resolve()
    if not (root / "v0.5").is_dir():
        return None
    top = git_output(root, "rev-parse", "--show-toplevel")
    if top is None or Path(top).resolve() != root:
        return None
    head = git_output(root, "rev-parse", "HEAD")
    if not head or not re.fullmatch(r"[0-9a-f]{40}", head):
        return None
    # Any local edit makes the checkout's installed bytes differ from the tag.
    if git_output(root, "status", "--porcelain", "--untracked-files=all") != "":
        return None
    return head


def local_checkout_matches_release(
    playbook_root: Path,
    release: str | None,
    tag_object: str | None,
    commit: str | None,
) -> bool:
    """Cheap warm-path drift check; public tag proof stays in the cold path."""
    if (
        release is None or not RELEASE_TAG.fullmatch(release)
        or tag_object is None or not re.fullmatch(r"[0-9a-f]{40}", tag_object)
        or commit is None or not re.fullmatch(r"[0-9a-f]{40}", commit)
    ):
        return False
    head = clean_checkout_head(playbook_root)
    if head != commit:
        return False
    root = playbook_root.resolve()
    return (
        git_output(root, "cat-file", "-t", f"refs/tags/{release}") == "tag"
        and git_output(root, "rev-parse", f"refs/tags/{release}") == tag_object
        and git_output(root, "rev-parse", f"refs/tags/{release}^{{}}") == commit
    )


def verified_release_evidence(playbook_root: Path) -> tuple[str, str, str] | None:
    """Return the release, tag object and commit for a published clean checkout.

    A copied package without independent provenance, an untagged checkout, a
    modified checkout, or an unavailable public tag lookup remains unknown.
    The directory name, changelog heading, and edition stamp are never proof.
    """
    root = playbook_root.resolve()
    head = clean_checkout_head(root)
    if head is None:
        return None
    matches = git_output(root, "tag", "--points-at", "HEAD", "--list", "v0.5.*")
    tags = [tag for tag in (matches or "").splitlines() if RELEASE_TAG.fullmatch(tag)]
    if len(tags) != 1:
        return None
    tag = tags[0]
    if git_output(root, "cat-file", "-t", f"refs/tags/{tag}") != "tag":
        return None
    local_object = git_output(root, "rev-parse", f"refs/tags/{tag}")
    local_commit = git_output(root, "rev-parse", f"refs/tags/{tag}^{{}}")
    published = published_tag_refs(tag)
    if published is None or published != (local_object, local_commit) or local_commit != head:
        return None
    return tag, local_object, head


def verified_release(playbook_root: Path) -> str | None:
    """Return the verified release name, or unknown when proof is unavailable."""
    evidence = verified_release_evidence(playbook_root)
    return evidence[0] if evidence is not None else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playbook_root", type=Path)
    parser.add_argument("--local-check", metavar="RELEASE",
                        help="offline warm-path check that the clean checkout still matches a recorded release")
    parser.add_argument("--tag-object", metavar="SHA", help="recorded verified tag object for --local-check")
    parser.add_argument("--commit", metavar="SHA", help="recorded verified commit for --local-check")
    args = parser.parse_args(argv)
    if args.local_check is not None:
        if local_checkout_matches_release(
            args.playbook_root, args.local_check, args.tag_object, args.commit
        ):
            print(f"Recorded release {args.local_check} still matches this clean checkout.")
            return 0
        print("Recorded release does not match this checkout; run the cold prerequisite path.")
        return 2
    evidence = verified_release_evidence(args.playbook_root)
    if evidence is None:
        print("Installed release: unknown (exact public tag and clean checkout not verified).")
        return 2
    release, tag_object, commit = evidence
    print(
        f"Installed release: {release} (exact public tag and clean checkout verified); "
        f"tag object: {tag_object}; commit: {commit}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

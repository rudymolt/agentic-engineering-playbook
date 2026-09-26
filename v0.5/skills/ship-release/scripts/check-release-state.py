#!/usr/bin/env python3
"""Check GitHub release state for a repo/tag.

Generic mode requires --tag. The playbook-v0.5 profile derives the tag from
the first `## V...` heading in v0.5/CHANGELOG.md and checks the root README
current-release line.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


PLAYBOOK_CHANGELOG_RE = re.compile(r"^##\s+(V\d+\.\d+\.\d+)\b", re.M)
PLAYBOOK_README_RE = re.compile(r"^\*\*Current release:\*\*\s+(V\d+\.\d+\.\d+)\b", re.M)
PLAYBOOK_DATED_HEADING_RE = re.compile(r"^##\s+(V\d+\.\d+\.\d+)\s+—\s+(\d{4}-\d{2}-\d{2})", re.M)


@dataclass
class Problem:
    category: str
    message: str
    detail: Optional[str] = None


def run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], root)


def gh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run(["gh", *args], root)


def read_text(path: Path, problems: List[Problem], category: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.append(Problem(category, f"missing required file: {path}"))
    except OSError as exc:
        problems.append(Problem(category, f"could not read {path}", str(exc)))
    return ""


def first_match(pattern: re.Pattern[str], text: str) -> Optional[str]:
    match = pattern.search(text)
    if not match:
        return None
    return match.group(1)


def git_stdout(root: Path, args: List[str], problems: List[Problem], message: str) -> str:
    proc = git(root, *args)
    if proc.returncode != 0:
        problems.append(Problem("blocking_git_mismatch", message, proc.stderr.strip()))
        return ""
    return proc.stdout.strip()


def infer_playbook(root: Path, problems: List[Problem]) -> Dict[str, Optional[str]]:
    changelog = read_text(root / "v0.5" / "CHANGELOG.md", problems, "docs_mismatch")
    readme = read_text(root / "README.md", problems, "docs_mismatch")

    version = first_match(PLAYBOOK_CHANGELOG_RE, changelog)
    readme_version = first_match(PLAYBOOK_README_RE, readme)

    if not version:
        problems.append(Problem("docs_mismatch", "could not find top V0.5.x changelog heading"))
    if not readme_version:
        problems.append(Problem("docs_mismatch", "could not find README current-release line"))
    if version and readme_version and version != readme_version:
        problems.append(
            Problem(
                "docs_mismatch",
                f"README current release {readme_version} does not match changelog {version}",
            )
        )

    return {
        "version": version,
        "readme_version": readme_version,
        "tag": version.lower() if version else None,
        "title": version,
    }


def discover_origin_head_branch(root: Path) -> Optional[str]:
    proc = git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if proc.returncode != 0:
        return None
    ref = proc.stdout.strip()
    if ref.startswith("origin/"):
        return ref.removeprefix("origin/")
    return ref or None


def check_git_local(
    root: Path,
    tag: Optional[str],
    release_branch: Optional[str],
    require_clean: bool,
    problems: List[Problem],
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}

    checks["git_root"] = git_stdout(root, ["rev-parse", "--show-toplevel"], problems, "not inside a git repository")
    current_branch = git_stdout(root, ["branch", "--show-current"], problems, "could not determine current branch")
    checks["branch"] = current_branch

    discovered_branch = discover_origin_head_branch(root)
    checks["origin_head_branch"] = discovered_branch
    branch_to_check = release_branch or discovered_branch or current_branch
    checks["release_branch"] = branch_to_check

    if branch_to_check and current_branch and current_branch != branch_to_check:
        problems.append(
            Problem(
                "blocking_git_mismatch",
                f"release branch must be {branch_to_check}, got {current_branch}",
            )
        )

    status = git_stdout(root, ["status", "--porcelain"], problems, "could not inspect worktree status")
    checks["dirty"] = bool(status)
    if status and require_clean:
        problems.append(Problem("blocking_git_mismatch", "worktree has uncommitted changes", status))

    status_sb = git_stdout(root, ["status", "-sb"], problems, "could not inspect branch sync state")
    checks["status_sb"] = status_sb
    first_status_line = status_sb.splitlines()[0] if status_sb else ""
    status_reported_unpushed = False
    if "behind" in first_status_line or "diverged" in first_status_line:
        problems.append(Problem("blocking_git_mismatch", "release branch is behind or diverged from upstream", first_status_line))
    elif "ahead" in first_status_line:
        problems.append(Problem("branch_not_pushed", "release branch has commits not pushed upstream", first_status_line))
        status_reported_unpushed = True

    head = git_stdout(root, ["rev-parse", "HEAD"], problems, "could not resolve HEAD")
    checks["head"] = head
    if branch_to_check:
        remote_branch = git(root, "rev-parse", f"origin/{branch_to_check}")
        if remote_branch.returncode == 0:
            remote_branch_sha = remote_branch.stdout.strip()
            checks["origin_branch_commit"] = remote_branch_sha
            if head and remote_branch_sha != head:
                ancestor = git(root, "merge-base", "--is-ancestor", remote_branch_sha, "HEAD")
                category = "branch_not_pushed" if ancestor.returncode == 0 else "blocking_git_mismatch"
                message = (
                    f"HEAD is not pushed to origin/{branch_to_check}"
                    if category == "branch_not_pushed"
                    else f"HEAD has not reconciled origin/{branch_to_check}"
                )
                if not (category == "branch_not_pushed" and status_reported_unpushed):
                    problems.append(Problem(category, message, f"origin/{branch_to_check}={remote_branch_sha} head={head}"))
        else:
            checks["origin_branch_commit"] = None
            problems.append(Problem("branch_not_pushed", f"origin/{branch_to_check} does not exist"))

    if not tag:
        problems.append(Problem("missing_tag", "no release tag was supplied or inferred"))
        return checks

    show_ref = git(root, "show-ref", "--verify", f"refs/tags/{tag}")
    checks["local_tag_exists"] = show_ref.returncode == 0
    if show_ref.returncode != 0:
        problems.append(Problem("missing_tag", f"missing local tag {tag}"))
        return checks

    tag_type = git_stdout(root, ["cat-file", "-t", tag], problems, f"could not inspect tag {tag}")
    checks["local_tag_type"] = tag_type
    if tag_type != "tag":
        problems.append(Problem("tag_mismatch", f"{tag} is not an annotated tag", f"cat-file type: {tag_type}"))

    tag_commit = git_stdout(root, ["rev-parse", f"{tag}^{{}}"], problems, f"could not resolve {tag}")
    checks["local_tag_commit"] = tag_commit
    if head and tag_commit and head != tag_commit:
        problems.append(
            Problem(
                "tag_mismatch",
                f"{tag} does not point at HEAD",
                f"tag={tag_commit} head={head}",
            )
        )

    tags_at_head = git_stdout(root, ["tag", "--points-at", "HEAD"], problems, "could not list tags at HEAD")
    checks["tags_at_head"] = [line for line in tags_at_head.splitlines() if line]
    if tag_commit == head and tag not in checks["tags_at_head"]:
        problems.append(Problem("tag_mismatch", f"{tag} resolves to HEAD but is not listed at HEAD"))

    return checks


def parse_remote_tag(stdout: str, tag: str) -> Dict[str, Optional[str]]:
    exact_ref = f"refs/tags/{tag}"
    peeled_ref = f"{exact_ref}^{{}}"
    exact_sha: Optional[str] = None
    peeled_sha: Optional[str] = None

    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        sha, ref = parts
        if ref == exact_ref:
            exact_sha = sha
        elif ref == peeled_ref:
            peeled_sha = sha

    return {"object": exact_sha, "commit": peeled_sha}


def check_github(
    root: Path,
    tag: Optional[str],
    require_latest: bool,
    allow_prerelease: bool,
    problems: List[Problem],
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {"remote_tag_exists": False, "github_release_exists": False}
    if not tag:
        return checks

    remote = git(root, "ls-remote", "--tags", "origin", tag)
    if remote.returncode != 0:
        problems.append(Problem("github_unavailable", "could not inspect remote tags", remote.stderr.strip()))
    else:
        remote_tag = parse_remote_tag(remote.stdout, tag)
        remote_object = remote_tag["object"]
        remote_commit = remote_tag["commit"]
        checks["remote_tag_exists"] = remote_object is not None or remote_commit is not None
        checks["remote_tag_object"] = remote_object
        checks["remote_tag_commit"] = remote_commit
        if remote_object is None and remote_commit is None:
            problems.append(Problem("missing_tag", f"missing remote tag {tag}"))
        else:
            local_object = git_stdout(root, ["rev-parse", tag], problems, f"could not resolve local tag object {tag}")
            local_commit = git_stdout(root, ["rev-parse", f"{tag}^{{}}"], problems, f"could not resolve local {tag}")
            compare_remote = remote_commit or remote_object
            compare_local = local_commit if remote_commit else local_object
            compare_label = "commit" if remote_commit else "tag object"
            if compare_local and compare_remote and compare_remote != compare_local:
                problems.append(
                    Problem(
                        "tag_mismatch",
                        f"remote tag {tag} points at a different {compare_label}",
                        f"remote={compare_remote} local={compare_local}",
                    )
                )

    view = gh(
        root,
        "release",
        "view",
        tag,
        "--json",
        "tagName,name,isDraft,isPrerelease,url,publishedAt",
    )
    if view.returncode != 0:
        stderr = view.stderr.strip() or view.stdout.strip()
        if "release not found" in stderr.lower():
            problems.append(Problem("missing_github_release", f"missing GitHub Release for {tag}"))
        else:
            problems.append(Problem("github_unavailable", f"could not inspect GitHub Release {tag}", stderr))
        return checks

    try:
        release = json.loads(view.stdout)
    except json.JSONDecodeError as exc:
        problems.append(Problem("github_unavailable", f"could not parse gh release JSON for {tag}", str(exc)))
        return checks

    checks["github_release_exists"] = True
    checks["github_release"] = release
    if release.get("tagName") != tag:
        problems.append(Problem("stale_github_release", f"GitHub Release tagName is not {tag}", str(release.get("tagName"))))
    if release.get("isDraft"):
        problems.append(Problem("stale_github_release", f"GitHub Release {tag} is still a draft"))
    if release.get("isPrerelease") and not allow_prerelease:
        problems.append(Problem("stale_github_release", f"GitHub Release {tag} is marked prerelease"))

    release_list = gh(root, "release", "list", "--limit", "20")
    if release_list.returncode != 0:
        problems.append(Problem("github_unavailable", "could not list GitHub releases", release_list.stderr.strip()))
        return checks

    latest = False
    for line in release_list.stdout.splitlines():
        fields = line.split("\t")
        if tag in fields:
            latest = "Latest" in fields
            break
    checks["github_release_latest"] = latest
    if require_latest and not latest:
        problems.append(Problem("stale_github_release", f"GitHub Release {tag} is not marked Latest"))

    return checks


def committed_benchmark_summaries(root: Path) -> List[Path]:
    """Return committed summaries, falling back to fixture files outside Git."""
    probe = git(root, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0:
        return sorted((root / "bench" / "results").glob("*/SUMMARY.md"))
    tracked = git(root, "ls-tree", "-r", "--name-only", "HEAD", "--", "bench/results")
    if tracked.returncode != 0:
        return []
    return sorted(
        root / name for name in tracked.stdout.splitlines() if name.endswith("/SUMMARY.md")
    )


def check_bench_evidence(root: Path, acknowledged: bool, warnings: List[Problem]) -> Dict[str, Any]:
    """Warn (never block) when no benchmark run is newer than the previous release.

    Phase 3 of the bench harness plan: every release should carry benchmark
    evidence. This starts as a warning with an explicit --no-bench
    acknowledgment; promotion to a blocking check is an earned, later decision.
    """
    checks: Dict[str, Any] = {"applicable": (root / "bench").is_dir()}
    if not checks["applicable"]:
        return checks

    summaries = committed_benchmark_summaries(root)
    newest_run_date = summaries[-1].parent.name[:10] if summaries else None
    checks["newest_summary_date"] = newest_run_date

    try:
        changelog = (root / "v0.5" / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return checks  # missing changelog is already a docs_mismatch problem
    dated = PLAYBOOK_DATED_HEADING_RE.findall(changelog)
    previous = dated[1] if len(dated) > 1 else None
    checks["previous_release"] = f"{previous[0]} ({previous[1]})" if previous else None

    checks["acknowledged"] = acknowledged
    if acknowledged or previous is None:
        return checks

    prev_version, prev_date = previous
    if newest_run_date is None or newest_run_date < prev_date:
        newest_label = newest_run_date or "absent"
        warnings.append(
            Problem(
                "bench_evidence_stale",
                f"no benchmark evidence newer than {prev_version} ({prev_date}); "
                f"newest bench/results SUMMARY.md is {newest_label}",
                "run e.g. `python3 bench/run.py --tasks T1,T2,T3,T4,T5,T6,T7,T8 "
                "--repeats 5 --runner claude --budget 15` and commit its SUMMARY.md, "
                "then compare with bench/compare.py — or acknowledge with --no-bench",
            )
        )
    return checks


def render_text(result: Dict[str, Any]) -> str:
    lines = [
        "GitHub release state",
        f"- Profile: {result.get('profile') or 'generic'}",
        f"- Tag: {result.get('tag') or 'unknown'}",
        f"- Title: {result.get('title') or 'unknown'}",
    ]

    if result.get("profile") == "playbook-v0.5":
        lines.extend(
            [
                f"- Playbook version: {result.get('version') or 'unknown'}",
                f"- README current release: {result.get('readme_version') or 'unknown'}",
            ]
        )

    git_checks = result.get("git", {})
    if git_checks:
        lines.extend(
            [
                f"- Branch: {git_checks.get('branch') or 'unknown'}",
                f"- Release branch: {git_checks.get('release_branch') or 'unknown'}",
                f"- Status: {git_checks.get('status_sb') or 'unknown'}",
                f"- Local tag type: {git_checks.get('local_tag_type') or 'missing'}",
            ]
        )

    github_checks = result.get("github", {})
    release = github_checks.get("github_release") or {}
    if github_checks:
        lines.extend(
            [
                f"- Remote tag: {'present' if github_checks.get('remote_tag_exists') else 'missing'}",
                f"- GitHub release: {release.get('url') or 'missing'}",
                f"- GitHub latest: {github_checks.get('github_release_latest')}",
            ]
        )

    bench_checks = result.get("bench", {})
    if bench_checks.get("applicable"):
        lines.append(
            f"- Bench evidence: newest run {bench_checks.get('newest_summary_date') or 'absent'}"
            f" (previous release {bench_checks.get('previous_release') or 'unknown'})"
            + (" — acknowledged via --no-bench" if bench_checks.get("acknowledged") else "")
        )

    warnings = result.get("warnings", [])
    problems = result.get("problems", [])
    if warnings:
        lines.append("")
        lines.append("Warnings (non-blocking):")
        for warning in warnings:
            lines.append(f"- [{warning['category']}] {warning['message']}")
            if warning.get("detail"):
                lines.append(f"  {warning['detail']}")

    if not problems:
        lines.append("")
        lines.append(f"OK: release state matches {result.get('tag')}.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Problems:")
    for problem in problems:
        lines.append(f"- [{problem['category']}] {problem['message']}")
        if problem.get("detail"):
            lines.append(f"  {problem['detail']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check GitHub release state for a repo/tag.")
    parser.add_argument("--repo-root", default=".", help="Repository root to check.")
    parser.add_argument("--tag", help="Release tag to check, such as v1.2.3.")
    parser.add_argument("--title", help="Release title. Defaults to the tag.")
    parser.add_argument("--branch", help="Release branch. Defaults to origin/HEAD, then current branch.")
    parser.add_argument("--profile", choices=["generic", "playbook-v0.5"], default="generic")
    parser.add_argument("--github", action="store_true", help="Also check origin tags and GitHub Release state.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--allow-dirty", action="store_true", help="Do not fail when the worktree has uncommitted changes.")
    parser.add_argument("--allow-prerelease", action="store_true", help="Do not fail when the GitHub Release is marked prerelease.")
    parser.add_argument("--no-require-latest", action="store_true", help="Do not require the GitHub Release to be marked Latest.")
    parser.add_argument("--no-bench", action="store_true",
                        help="Acknowledge missing benchmark evidence for this release "
                             "(playbook-v0.5 profile; suppresses the non-blocking warning).")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    problems: List[Problem] = []
    warnings: List[Problem] = []

    profile_data: Dict[str, Optional[str]] = {}
    if args.profile == "playbook-v0.5":
        profile_data = infer_playbook(root, problems)

    tag = args.tag or profile_data.get("tag")
    title = args.title or profile_data.get("title") or tag

    result: Dict[str, Any] = {
        "repo_root": str(root),
        "profile": args.profile,
        "tag": tag,
        "title": title,
        **profile_data,
        "git": check_git_local(
            root=root,
            tag=tag,
            release_branch=args.branch,
            require_clean=not args.allow_dirty,
            problems=problems,
        ),
    }

    if args.github:
        result["github"] = check_github(
            root=root,
            tag=tag,
            require_latest=not args.no_require_latest,
            allow_prerelease=args.allow_prerelease,
            problems=problems,
        )

    if args.profile == "playbook-v0.5":
        result["bench"] = check_bench_evidence(root, args.no_bench, warnings)

    result["ok"] = not problems
    result["problems"] = [asdict(problem) for problem in problems]
    result["warnings"] = [asdict(warning) for warning in warnings]

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(render_text(result))

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

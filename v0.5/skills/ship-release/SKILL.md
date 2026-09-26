---
name: ship-release
description: Publish or reconcile a repository version tag and GitHub Release. Use only after the user explicitly asks to cut or publish a release, or to fix drift between version files, tags, and GitHub Releases.
---

# /ship-release

Publishes a GitHub Release for the current repo. It does not replace feature shipping or deployment; it runs when the user wants a repository-level release marker: a version/tag plus a GitHub Release object.

## Release invariant

A release is complete only when all of these are true:

- The release version/tag is known and intentional.
- The release commit is on the release branch, normally the repo's default branch.
- The worktree is clean except for explicit release metadata edits the user has approved.
- The release branch is pushed.
- The tag points at the release commit locally and on `origin`.
- GitHub has a non-draft Release for that tag.
- The Release is marked `Latest` unless the user explicitly asked for a prerelease or non-latest release.
- If the repo has a root `README.md`, that README mentions the current release/tag
  or links to the project's release notes for the current release, unless the user
  explicitly opts out.

If any invariant is false at the end, the release is not shipped.

## Helper script

Use the bundled checker before creating the release and after GitHub changes. It ships next to this skill at `scripts/check-release-state.py` — in a bootstrapped project that is `.agents/skills/ship-release/scripts/check-release-state.py`; in the playbook repository it is `v0.5/skills/ship-release/scripts/check-release-state.py`. Run the copy that exists in the current repo:

```bash
python3 {playbook-path}/v0.5/skills/ship-release/scripts/check-release-state.py --repo-root . --tag v1.2.3
python3 {playbook-path}/v0.5/skills/ship-release/scripts/check-release-state.py --repo-root . --tag v1.2.3 --github
```

Use `--json` when another tool or script needs structured output.

With `--profile playbook-v0.5`, the checker also reports benchmark evidence: it warns
(non-blocking) when no `bench/results/*/SUMMARY.md` is newer than the previous release's
CHANGELOG date. Run the benchmark and commit its summary, or acknowledge the gap
explicitly with `--no-bench`; never leave the warning unaddressed in a release.

If the repository is `ai-engineering-playbook`, read [`PLAYBOOK-PROFILE.md`](PLAYBOOK-PROFILE.md) completely before step 1. Its version source, readiness gate, and documentation rules augment the general procedure below.

## Procedure

1. Resolve the release intent.
   - If the user supplied a version or tag, use it.
   - Else infer a candidate from project convention: `package.json`, `pyproject.toml`, `Cargo.toml`, `VERSION`, `CHANGELOG.md`, or recent tags.
   - If no version is discoverable, propose major/minor/patch based on changes since the last tag and ask before editing. Never invent a version silently.
   - Completion criterion: one intentional version/tag and the evidence used to resolve it are recorded.
2. Resolve release metadata.
   - Determine the release branch. Prefer the repo default branch from `origin/HEAD`; fall back to current branch if the default is unavailable and the user confirms.
   - Identify release notes using this precedence: user-provided notes; top changelog entry or `Unreleased` section; `gh release create --generate-notes`; agent summary of commits since the previous tag.
   - If the repo has a root `README.md`, check whether it mentions the resolved
     release tag/version or has an obvious current-release/release-notes section.
     If not, update the README before tagging so readers can find the release from
     the repo front page.
   - Decide whether the release is latest, prerelease, or non-latest. Default: latest, not prerelease.
   - Completion criterion: release branch, notes source, README treatment, and latest/prerelease state are fixed.
3. Run repo-specific checks.
   - For other repos, run the repo's normal test/lint/release checks when discoverable. If none are discoverable, say so and continue only if the user still wants a release marker.
   - Completion criterion: every discovered required check passes, or the user has explicitly accepted that the repository exposes no checks.
4. Run the local release checker.
   - Pass the resolved tag and release branch.
   - Treat `missing_tag`, `branch_not_pushed`, and `missing_github_release` as expected downstream work during an unreleased run.
   - Stop for dirty worktrees unless the only edits are intentional release metadata changes that should be committed first.
   - Completion criterion: every checker result is either green, expected downstream release work, or a named blocker that stops the procedure.
5. Commit release metadata if needed.
   - Version bumps, changelog edits, and README release-line updates must land in an ordinary commit before tagging.
   - If the root README does not mention the resolved release and no unrelated edits
     exist, add or update a concise current-release section before tagging.
   - Completion criterion: required metadata is on one ordinary commit and the worktree contains no unexplained changes.
6. Reconcile branch state.
   - If the release branch is ahead of `origin/{branch}`, push exactly that branch.
   - If behind or diverged, stop and ask for reconciliation. Never force-push.
   - Completion criterion: the release commit is the pushed tip of the resolved release branch.
7. Reconcile the tag.
   - If the tag is missing locally, create an annotated tag on the release commit: `git tag -a {tag} -m "{title}"`.
   - If the tag exists but does not point at the release commit, stop. Never retag a published or existing release tag.
   - If the tag is lightweight, stop and replace only if it has not been pushed and the user explicitly approves.
   - Push exactly the branch and tag: `git push origin {branch} {tag}`.
   - Completion criterion: an annotated local and remote tag both point at the release commit.
8. Create or update the GitHub Release object.
   - If the release is missing:

```bash
gh release create {tag} --verify-tag --title "{title}" --notes-file {notes_file} --latest
```

   - If the release exists but has stale notes/title/latest state:

```bash
gh release edit {tag} --title "{title}" --notes-file {notes_file} --latest
```

   - For prereleases, use `--prerelease` and normally `--latest=false`.
   - Completion criterion: GitHub has the intended non-draft release object with correct title, notes, prerelease, and latest state.
9. Verify final state.
   - Run `gh release list --limit 5`.
   - Run the checker with `--github`.
   - Final response must include the matched tag and GitHub Release URL.
   - Completion criterion: the `--github` checker is clean and the final tag plus release URL are captured.

## Guardrails

- Preserve published history: use ordinary pushes, keep existing remote tags fixed, and stop on tag/commit disagreement.
- Verify both objects: a pushed tag and a non-draft GitHub Release must exist.
- Resolve the version intentionally from user input or project convention; ask when no candidate is discoverable.
- Publish only from a pushed release commit.
- Surface every failed check and keep the release incomplete until the final `--github` checker pass is clean.

## Output shape

After success:

> **Released {tag}.** `{branch}` is current on origin, the tag points at the release commit locally and remotely, and GitHub Releases shows it here: {url}

If blocked:

> **Release blocked at {step}.** {one-line reason}
>
> `{category}`: {checker message}

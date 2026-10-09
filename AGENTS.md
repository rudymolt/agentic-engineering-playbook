# Agent instructions

The live playbook is [`v0.5/`](v0.5/). Read [`v0.5/AGENT-DIGEST.md`](v0.5/AGENT-DIGEST.md) first and route process work through its stage map. New projects start at [`v0.5/README.md`](v0.5/README.md) and use the bootstrap skill.

This public repository has one edition. Keep release consumers pinned to a tag and make development changes on `main` through review. Preserve third-party notices, update `v0.5/CHANGELOG.md` with a *Why* line for process changes, regenerate manifests, and run `python3 v0.5/scripts/verify-playbook.py` before shipping.

During planning, account for future updates to software, skills, models and settings: define when to check upstream changes, verify compatibility and migrate while preserving user customisations. This is a planning consideration, not a per-turn check.

Do not add personal addresses, machine paths, private-project records, credentials, old edition trees, or historical private repository content. Treat a failed privacy check as a publication blocker.

For maintainer commits, set both Git author and committer to a GitHub `noreply` address in each checkout before committing. Before each public PR merge through GitHub, establish the actual PR target repository and authenticated merging login from GitHub, then compare them with the complete canonical record below. Reuse its human confirmation only when both match exactly, the recorded setting is enabled, and no explicit revocation or disabled-setting report has invalidated it. Repeat merges by that pair need no new setting confirmation; the record has no periodic expiry.

If the record is absent, incomplete, invalidated, or does not match, obtain an affirmative human confirmation that the merging account's “Keep my email addresses private” setting is enabled and record the new confirmation before merging. If the target or login is unknown, establish it before deciding whether to reuse the record. Copied instructions do not authorize reuse for another repository. An explicit revocation or disabled-setting report invalidates the record immediately; reuse requires a fresh affirmative human confirmation recorded here. Changes to public record identifiers require ordinary privacy review.

### Canonical merge privacy confirmation

- Repository: rudymolt/agentic-engineering-playbook
- GitHub login: rudymolt
- Setting: “Keep my email addresses private” enabled
- Confirmed on: 2026-10-09
- Provenance: prior human confirmation recorded before GitHub PR #38; this is a remembered human statement, not live API verification.
- Status: active; no revocation recorded

This record proves neither commit identity nor merge authorization. After every merge, read back every commit newly added to `main` and require `noreply` author and committer addresses. All review, CI and merge gates still apply.

Before calling a PR ready to merge, inspect its review threads and comments. Fix valid findings and verify the updated head; answer stale or incorrect findings with evidence. Resolve each addressed thread, and leave any thread that needs human action clearly identified.

During documentation-only PR iteration, run the relevant focused checks (Markdown, links, public content, and generated files affected by the edit). Save the full `python3 v0.5/scripts/verify-playbook.py` run for the final release candidate before shipping; do not restart it after every small edit.

Keep both required GitHub CI jobs on every PR. The edition job may use focused checks only when all changed paths are editorial release metadata; agent instructions, stage/skill content, templates, scripts, and CI changes run the full suite. A release still needs the full verifier on its final candidate.

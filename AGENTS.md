# Agent instructions

The live playbook is [`v0.5/`](v0.5/). Read [`v0.5/AGENT-DIGEST.md`](v0.5/AGENT-DIGEST.md) first and route process work through its stage map. New projects start at [`v0.5/README.md`](v0.5/README.md) and use the bootstrap skill.

This public repository has one edition. Keep release consumers pinned to a tag and make development changes on `main` through review. Preserve third-party notices, update `v0.5/CHANGELOG.md` with a *Why* line for process changes, regenerate manifests, and run `python3 v0.5/scripts/verify-playbook.py` before shipping.

During planning, account for future updates to software, skills, models and settings: define when to check upstream changes, verify compatibility and migrate while preserving user customisations. This is a planning consideration, not a per-turn check.

Do not add personal addresses, machine paths, private-project records, credentials, old edition trees, or historical private repository content. Treat a failed privacy check as a publication blocker.

For maintainer commits, set both Git author and committer to a GitHub `noreply` address in each checkout before committing. Before merging a public PR through GitHub, confirm that the account's “Keep my email addresses private” setting is enabled; afterward, read back every commit newly added to `main` and require `noreply` author and committer addresses.

Before calling a PR ready to merge, inspect its review threads and comments. Fix valid findings and verify the updated head; answer stale or incorrect findings with evidence. Resolve each addressed thread, and leave any thread that needs human action clearly identified.

During documentation-only PR iteration, run the relevant focused checks (Markdown, links, public content, and generated files affected by the edit). Save the full `python3 v0.5/scripts/verify-playbook.py` run for the final release candidate before shipping; do not restart it after every small edit.

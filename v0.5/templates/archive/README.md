# archive/

> Shipped-feature planning artefacts. **Agents must not read this folder.**
>
> See `{playbook-path}/v0.5/30-document-lifecycle.md` for the full lifecycle policy.

---

## What's in here

Each subfolder is a `{YYYY-MM-DD}-{feature-slug}/` directory moved out of `planning/` at ship. Contents preserve what was in the planning folder at the moment of ship.

## Why archive instead of delete

- Git history covers most archaeology, but full planning narratives are spread across many commits and harder to reconstruct.
- During an incident investigation, a human may want to know what we *thought* we were building, not just what we built.
- The cost is negligible — agents are instructed not to read this folder, so context isn't polluted.

## How to access during an incident

A human reads the folder directly. If an agent needs the content, the human surfaces the specific file by attaching it to the conversation or reading it aloud. The agent does not glob across `archive/` of its own accord.

## Pruning

Periodically (e.g. annually), prune subfolders older than {project-decided period} that haven't been referenced in any incident or retro. This is a deliberate human action, not an automated one.

## What this folder MUST NOT contain

- Anything that should remain readable to agents — promote it to a Tier 3 living doc first (`CLAUDE.md`, `CONTEXT.md`, `docs/adr/`, `docs/releases/`).
- Secrets or credentials — those should never have been in `planning/` in the first place.
- Production data — same.

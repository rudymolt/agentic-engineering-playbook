# 30 · Document lifecycle

> Build-time documents are essential during the build and dangerous afterwards. They read as authoritative but describe what we *thought* we'd build, not what we built. This file defines what lives where, for how long, and what happens at ship.

---

## The three tiers

Every document the playbook generates belongs to one of three tiers, with three different fates.

### Tier 1 — Ephemeral (deleted, or archived out of agent scope)

Build-time scratch: sequencing notes, todo lists, "what to do next" docs, prompt scratchpads, half-finished design explorations, planning-folder content.

**Lives in:** `planning/{feature-slug}/`

**Lifetime:** from stage 01 (alignment) to stage 10 (ship).

**Fate at ship:** moved to `archive/{ship-date}-{feature-slug}/`. The `CLAUDE.md` template instructs agents not to read `archive/`. Humans can spelunk through it for incident archaeology; git history covers most other needs.

### Tier 2 — Decisions (kept forever, in canonical form)

The "we chose X over Y because Z" record, plus rejected alternatives so future-us doesn't re-propose them.

**Lives in:** `docs/adr/NNNN-short-title.md`

**Lifetime:** forever.

**Fate at ship:** any decision in the planning docs that meets the ADR bar (hard to reverse, surprising without context, real trade-off) is **promoted** to an ADR before the planning folder moves to archive.

### Tier 3 — Living docs (kept and maintained)

The present-tense source of truth.

**Lives in:** `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `DESIGN-GLOSSARY.md`, `ui-kitchen-sink.html`, `playbook-cadences.yml`, this playbook itself.

**Lifetime:** as long as the project.

**Fate at ship:** updated. New vocabulary that survived the build moves to `CONTEXT.md`; new design tokens to the kitchen sink; new project-wide rules to `CLAUDE.md`.

---

## The doc-close ritual (runs at stage 10)

Mandatory at ship. Skipping it is how stale planning docs accumulate.

1. Run `git status --short` and note whether doc-close starts from a clean or mixed tree.
2. **Promote surviving decisions to ADRs** at `docs/adr/` (rebuild the ADR index — see `10-process/02-context-and-adrs.md`).
3. **Promote surviving vocabulary to `CONTEXT.md`**, and UI vocabulary to `DESIGN-GLOSSARY.md` / `ui-kitchen-sink.html` when applicable.
4. **Update `CLAUDE.md`** if the build surfaced any project-wide rule.
5. **Update durable source docs** — `docs/README.md`, product specs, design docs, architecture references, completed exec plans — so future agents do not need the planning folder.
   When the project explicitly adopted a verification harness and shipped entry
   points changed, compare the affected feature-map entry and preserve proven
   journey knowledge/evidence before archive. Updating one entry at doc-close is
   not a claim that every mapped journey completed maintenance coverage; use the
   bounded maintenance route for that separate result. Only the owning stage may
   stamp its accepted complete clean/changed audit; doc-close never resets that
   maintenance clock by itself.
6. **Write the release note** (use `/document-release` for the structured version) and update **every current-release pointer** the project keeps — changelog, version file, and any "current release" link in the root README — in the same pass. `/ship-release` must find its release metadata already committed; a pointer discovered missing at the tagging checkpoint becomes an avoidable follow-up PR.
7. **Repo release checkpoint.** If this ship is a versioned milestone, public release, package release, breaking change, installable artifact, or changelog-worthy batch, ask: *"Should I cut a GitHub Release for this repo?"* If yes, commit the release metadata first, then run `/ship-release`.
8. **Ask the retro question** — *"did anything in this build deserve promotion to the playbook itself?"* — and log candidates for stage 12.
9. **Move `planning/{feature-slug}/` to `archive/{ship-date}-{feature-slug}/`** and update both `STATUS.md` files. Agents do not read `archive/`.
10. **Update `.playbook-state.yml`** — set `last_run.doc_close`, set `last_updated`, recompute the `status:` block.
11. Run `git status --short` again and keep doc-close changes in an intentional commit instead of leaving source-of-truth docs as follow-up cleanup.

If this ritual must hand off before archive, use the conditional
[pickup brief](10-process/pickup-brief.md) to point at current durable documents,
the exact branch/revision, and remaining closeout gates. Do not make an archived
planning folder or a private transcript the successor's required source.

Either the user or `/whats-next` will catch a missed doc-close at the next session start.

### One closeout branch, one PR

The merged feature branch is closed scope (stage 07's rule), but the closeout chain is not implementation work — do not open a branch per step either. Run doc-close, its release metadata, and (when stage 12 follows in the same session) the feature retro on **one fresh closeout branch**, shipped as **one PR**. Each extra docs PR is another human merge act for the same feature's paperwork, and the gates that matter — independent verification, production verification — already ran on the feature PR. Only a retro genuinely deferred to a later session (for example, folded into a weekly retro) opens its own branch then.

---

## Why archive and not delete

Pure deletion is too aggressive. It throws away the reasoning along with the noise. Archive gives us the same agent-context outcome (the agent never reads `archive/`) with a cheap insurance policy — a human can read old build narratives during an incident, and the folder is a candidate for periodic prune rather than instant loss.

If a project later wants to switch to delete-on-ship, change one line in `CLAUDE.md` and the doc-close step swaps `mv` for `rm -rf`. The rest of the playbook is unaffected.

---

## What `CLAUDE.md` instructs about archive

Every project's `CLAUDE.md` (templated in `templates/CLAUDE.md`) contains:

```markdown
## Folders agents must not read

- `archive/` — shipped-feature planning artefacts. Anything in here is stale by definition.
- `planning/{slug}/` where the slug is not currently in `active_features` of `.playbook-state.yml`.

If you need archive content for an incident investigation, ask the human to surface the relevant file.
```

This is the rule that makes archive safe. Without it, the agent will glob across `archive/` and pull stale plans into context.

---

## What about long-running features

A feature that spans many weeks doesn't sit in `planning/` indefinitely as a single mound. Break it down:

- **Feature-level docs** stay at `planning/{feature-slug}/`.
- **Per-slice work** lives at `planning/{feature-slug}/slices/{slice-slug}/` and gets archived per slice if useful.
- **Quarterly or longer** — promote the feature folder to `docs/projects/{feature-slug}/` (a Tier 3 living doc) and slim it down to the still-relevant decisions.

The principle: planning content's freshness should be obvious from where it lives.

## What about tracker-resident Wayfinder maps

[`92-wayfinder-track.md`](92-wayfinder-track.md) uses an external tracker map as the canonical pre-spec discovery artifact. While open, mirror only its locator and one-line destination in `.playbook-state.yml → active_wayfinding_maps` and `planning/STATUS.md`; do not duplicate ticket answers into a premature feature folder.

At graduation, promote durable terms/decisions first, create the normal alignment/spec/slice artifacts with a source-map pointer, then clear the open-map mirrors and close the map. The planning folder follows the ordinary tier-1 archive ritual at ship; the closed tracker map remains external decision provenance. A no-build map clears its mirrors without creating a planning folder.

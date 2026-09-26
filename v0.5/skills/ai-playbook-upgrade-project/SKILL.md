---
name: ai-playbook-upgrade-project
description: Upgrade a bootstrapped project to public V0.5 while preserving project content and recorded template bases. Use for same-edition upgrades or a private V0.4-to-public transition.
---

# /ai-playbook-upgrade-project

Upgrade a project without erasing its own decisions or writing a version stamp before certification. Legacy alias: `/upgrade-project`.

## Scope

Read [`MIGRATIONS.md`](MIGRATIONS.md) completely for every upgrade. This public edition supports same-edition V0.5 upgrades and projects already on private V0.4. A project still on V0.3 must first use its private bridge to V0.4; no earlier edition tree or direct V0.3 migration is included here.

## Three safety tiers

| Tier | What | Action |
|---|---|---|
| 1 | New managed files | Install from current templates after showing the plan. |
| 2 | Uncustomised template content | Three-way merge against the recorded pristine base and show the diff. |
| 3 | Project-written content, merge conflict, missing/edited base, or uncertain state | Preserve it, report the exact review needed, and withhold the new version stamp. |

## Procedure

1. Read `playbook_version`, recorded checkout path, and `template_provenance` from the project's `.playbook-state.yml`. Inspect the destination pinned public checkout and the project's working-tree status. Completion criterion: source and target are exact and project files are preserved.
2. Build the read-only plan: classify each new or changed file by tier, identify old checkout path references, and show any manual review. Completion criterion: the user has seen the full plan before writes.
3. For accepted tier 1/2 work, run `python3 {playbook-path}/v0.5/scripts/upgrade-project.py {project-path} --apply-safe` from the pinned public checkout. Any `manual review:` is tier 3, not success. The V0.4 transition retargets managed instructions, state, and cadences to the public checkout; certification refuses old checkout references in those surfaces. Completion criterion: all safe changes are listed and any unresolved review retains the old version stamp.
4. Resolve each tier-3 item with a minimal reviewed edit, then rerun. Use `--adopt-current FILE` only after the project owner has accepted the merged current content. Completion criterion: no unresolved review and no old checkout path in current managed entry files.
5. Require `playbook_version: V0.5.0`, `prereqs_required: true` after a cross-edition transition, and a no-change second run. Run `compute-status.py PROJECT --check` and stage 00's cold path. Completion criterion: project content remains, recorded provenance matches installed files, and status is current.

## Guardrails

- Keep the source checkout available until the project passes the public cold path and its owner chooses to retire the old path.
- Never silently rewrite project-written content or certify a conflicting merge.
- A failed or partial run keeps the prior version stamp; safe changes remain visible for review and rerun.
- Do not claim direct public migration from V0.3 or earlier.

## Output

Report source and target versions/checkouts, tier 1/2 edits, tier-3 reviews, preservation evidence, the second-run result, and the remaining project-owner actions.

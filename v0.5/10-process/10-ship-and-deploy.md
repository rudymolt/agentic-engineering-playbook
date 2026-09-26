# 10 · Ship and deploy

> Matt's process ends at "the code works"; gstack ships it. This stage covers the steps from green-slice to verified-in-production.

**This stage in one breath:** Take the green slice from merge to verified-in-production, then close out the feature's planning docs. Output: shipped, release-noted, doc-closed.

---

## When to run

After stages 07, 08, and 09 are complete for a slice or feature, and the user says ship — or when a stage 07 build loop finishes its final review and the user picks a ship option from the menu below.

Shipping assumes the work was built on a feature branch. If work accidentally happened on `main`, move it to a feature branch before opening the PR, but treat that as recovery rather than the normal workflow.

## The ship menu

When the work is ready to ship (all slices built, final review passed), offer typed options rather than assuming scope:

> Ready to ship. Choose:
>
> - Type **ship PR** — open the pull request and run the full gate check; then you merge in GitHub.
> - Type **deliver to PR** — after an approved envelope, let `/ai-playbook-deliver` own Build → Verify → QA → exact PR handback; it stops before merge.
> - Type **K4.1 merge** — only for an admitted eligible lane with current standing authority; launch a fresh process-attested merge session for the exact PR head.
> - Type **ship and clean up** — open the PR and run the gates; once you've merged, I'll prune merged and gone-remote branches and reconcile `main` so the repo is clean for the next feature.
> - Type **clean up only** — skip shipping; prune merged/gone branches and reconcile `main` now.
> - Type **stop here** — leave everything as-is.

Rules the menu never overrides: **the merge is the human's act unless the exact
PR independently passes an admitted K4.1 fresh-session contract** (gate check
item 2 below); branch pruning checks the host's PR state before deleting
anything Git ancestry alone cannot prove merged (squash merges hide ancestry);
and clean-up touches branches and `main` only — it never archives a live
planning folder, because **doc-close fires on feature ship, not slice ship**
(see the doc-close ritual below).

## The sequence

### 1. `/ship` — Release Engineer

Confirm the feature branch is based on current `main`, run tests, audit coverage, push, open PR.

Commit messages and PR descriptions lead with the value or why, then the what. Never submit a bare file changelog. This reinforces the dependency rule: every new dependency is named and justified in the PR description.

After `/ship` opens the PR, the human project owner reviews and merges it manually in GitHub. See `../50-how-to-write-code-with-ai.html` (interactive HTML — open in a browser) for the human-side workflow.

An agent-authored PR body carries a short structured trail: risk assessment, what was tested (commands/flows), and findings fixed plus how each was verified — not just a summary.

### 2. `/land-and-deploy` — Release Engineer

Merge the PR, wait for CI and deploy, verify production health.

### 3. `/canary` — SRE

Post-deploy monitoring loop. Watches the production signals for the time window your project defines (typically 15–60 minutes after deploy). If anything looks wrong, rolls back.

### 4. `/benchmark` — Performance Engineer

Baseline page-load times and Core Web Vitals. Used at later cadences to detect regression.

## Shipping a migration (schema or data-shape changes)

Promoted from Sample Athletics case-study folklore to rule (V0.2.7):

1. **Backup precedes migration.** A timestamped backup of the affected store is taken before the migration runs — locally and in any shared environment.
2. **The rollback has actually been executed.** Every migration ships with a rollback that has been run against a copy of real(istic) data — written-but-never-run rollbacks are untested code on the worst possible path. Rehearse: apply → roll back → re-apply.
3. **Migration and dependent code ship separately** where the stack allows: the migration lands first (backwards-compatible), the code that requires it second — each individually revertable. A failed migration is then a stage 11 incident with a rehearsed first move, not an improvisation.

## The gate check (before anything ships)

The project's `ci-gates.md` defines the minimum machine-enforced gates for agent-authored PRs (tests, lint/typecheck, dependency advisories, secrets scan, one human approval). Before shipping:

1. Confirm every gate is green, or that the human has recorded an explicit override in the PR (who, why, which gate). A silent skip is a blocked ship.
2. The merge itself is the human's act unless the project explicitly admitted
   K4.1 and a new transcript-free session independently persists an allow
   decision, rechecks host/Mission Control state, and uses the exact expected
   head. Builders and coordinators never merge. K4.1 stops at merge and claims
   no Tier B/C, non-bypass, deploy, or release authority. Never approve your
   own PR or edit CI config to turn a gate green.
3. No `ci-gates.md` in the project? Run the gates manually, record the results in the PR description, and propose bootstrapping the file.
4. Never force-push over remote commits you have not reconciled. A push that would discard commits the run did not incorporate stops and asks.
5. **Preview deployment gate.** When the hosting provider builds a preview deployment per PR (Vercel, Netlify, and similar), verify it before the merge: wait for the preview build, confirm the preview environment is isolated from production (especially database and email/notification secrets), and run a smoke test against the preview URL. No merge until the preview and smoke test pass. Projects without preview deployments record that in the ship notes and rely on the local verification ladder plus post-merge `/canary`.
6. **Overdue architecture cadence.** An insist-level overdue architecture review runs before the merge, not after it (stage 06's timing rule) — deferring it past the merge turns its findings into a follow-up PR. A nudge-level overdue is surfaced but does not block the ship.

## The doc-close ritual (mandatory at this stage)

> **Scope clarification (V0.2.1):** doc-close fires when a **feature** ships — that is when its planning folder closes. Shipping an individual *slice* updates `last_run.ship` and the slice counters but does **not** trigger doc-close; the planning folder stays live while the feature has open slices. (Benchmarked agents reading the raw state files reasonably concluded otherwise; this paragraph and the cadence guard in `playbook-cadences.yml` remove the ambiguity.)

Before `/canary` exits, run the **canonical doc-close ritual** in `../30-document-lifecycle.md` — eleven steps, from the opening `git status --short` to the intentional doc-close commit. The list lives there and only there; this stage adds nothing to it.

Feature closeout is durable work, not a conversational reminder. When the feature reaches production, create or update its `pending_closeouts` entry immediately. Mark `production_verified` after the production check and `doc_close: complete` after the ritual. Leave the entry present for stage 12 even when doc-close completes.

Closeout mechanics: the merged feature branch is closed scope, but do not open a branch per closeout step either. Doc-close, its release metadata, and a same-session stage 12 feature retro share **one fresh closeout branch and one PR** (see the closeout rule in `../30-document-lifecycle.md`). With the ritual's current-release pointers committed in that PR, `/ship-release` tags after a single merge instead of discovering missing metadata afterwards.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
counters:
  features_shipped_total: +1
last_run:
  ship: {ISO timestamp}           # latest slice or feature delivery
  feature_ship: {ISO timestamp}   # set only when the whole feature ships
  doc_close: {ISO timestamp}   # days_since_last_doc_close is derived from this; no stored counter to reset
pending_closeouts:
  - feature_slug: {feature-slug}
    title: {feature title}
    shipped_at: {ISO timestamp}
    production_verified: true
    doc_close: complete
    retro: pending
active_features:
  # remove the shipped feature
```

Return the terminal routing block after recomputing status:

```yaml
playbook_result:
  outcome: complete
  next_stage: 12-retro-and-learn
  required_actions: [feature-retro]
```

This example follows the state block above, where production verification and doc-close are complete. Earlier exits preserve the ordered remainder and route to its first action: `[production-verification, doc-close, feature-retro]`, then `[doc-close, feature-retro]`, then `[feature-retro]`. The coordinator consumes this block before suggesting unrelated work.

---

## Next

- Shipped and verified → open `12-retro-and-learn.md` (runs after every shipped feature)
- Doc-close due → follow `../30-document-lifecycle.md`
- Deploy failed → open `11-debug.md`
- Unsure → run `/whats-next`

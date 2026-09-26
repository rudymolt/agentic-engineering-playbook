---
name: whats-next
description: Route the next playbook stage from project state and cadence evidence. Use when the user asks what to do next, is stuck between stages, or another playbook rule needs an ambient recommendation.
---

# /whats-next

## What this skill produces

A short recommendation in this shape:

> **Next:** {stage name} — {one-line description}
>
> **Why:** {rationale, citing the state or cadence rule that fired}
>
> **What to run:** {specific skill or action — e.g. `/grill-with-docs`, copy a template, etc.}
>
> **Reply:** `yes` to proceed · `defer` to snooze · `skip` to log a dismissal
>
> *(If more than one stage is overdue, list up to 3 in priority order.)*

For an open Wayfinder map, replace the reply line with `Invoke: /wayfinder {locator} when ready`. Do not advertise `yes`, `defer`, or `skip`: the command is user-invoked, and leaving the map open is already the durable deferred state. Stage 12's retro reviews any map open longer than 30 days, so a parked map needs no dismissal counter here.

For a resumable pending Plan route, replace the normal reply line with its exact resume action. Name the saved model and runner. A manual Conductor route shows the handoff path and tells the human which harness/model tab to open; a sidecar route says which runner will resume; a current-tab route says to resume here.

If nothing is overdue, no feature closeout is pending, no pending Plan route exists, no Wayfinder map is open, and no feature is in flight:

> No cadences overdue. No active features. Ready for a new feature — describe it, or run `/office-hours` if you want to challenge the idea first.

## Procedure

### Step 1 — Read project state and check freshness

Read `.playbook-state.yml` from the project root. **It is the only file the fast path needs.**

If it is missing, the project isn't bootstrapped. Tell the user:

> The playbook isn't bootstrapped in this project. Run the bootstrap sequence in `{playbook-path}/v0.5/README.md` first.

Stop the skill.

`.playbook-state.yml` opens with a `status:` block — `headline`, `overdue[]`, `features_by_stage`, `pending_closeouts`, `pending_plan_routes`, `computed_at` — plus the corresponding `pending_closeouts` records, `pending_model_routes`, and a separate `active_wayfinding_maps` list. The tracker remains canonical for Wayfinder; pending routes remain canonical for interrupted pre-feature Plan work. When `{playbook-path}/v0.5/scripts/compute-status.py` is available, run `python3 {playbook-path}/v0.5/scripts/compute-status.py . --check` first; if it reports stale or wrong deterministic state, run it without `--check` before continuing. Hand reconciliation remains the fallback when the project cannot run Python.

**Fast path (fresh status):** if `computed_at` is present and not older than `last_updated`, the block is current. Use `overdue[]`, `pending_closeouts`, `pending_plan_routes`, `pending_model_routes`, `active_wayfinding_maps`, `features_by_stage`, and `active_features` directly from this one file. Run branch hygiene (`git status -sb`) and query the host PR state for the current branch. Skip reading `playbook-cadences.yml`, `planning/`, `archive/`, and `CLAUDE.md`. Proceed to Step 4.

**Full path (stale or missing status):** read the five remaining files before Step 2:

```
playbook-cadences.yml  — cadence rules (thresholds)
planning/              — active features (listing only)
planning/STATUS.md     — active-feature and open-Wayfinder-map pointers
archive/               — shipped count (listing only; never read contents)
CLAUDE.md              — intrusion level setting
```

If any are missing on the full path, treat as an unbootstrapped project (same message above).

Either way, this skill always leaves a fresh `status:` block behind when it finishes.

Completion criterion: the project is reported unbootstrapped, or its status is fresh enough to rank without hidden reconciliation.

### Step 2 — Refresh state from observable signals (stale-status fallback)

Some counters in `.playbook-state.yml` can drift if a stage was completed without updating state. Reconcile:

- `slices_shipped_total` — count commits matching the project's slice-tag convention (`/setup-matt-pocock-skills` configures this) since the timestamp at `last_run.architecture_review`.
- `days_since_last_retro` — diff today's date against `last_run.retro`.
- `days_since_last_doc_close` — diff today's date against `last_run.doc_close`.
- `active_features` — should match the folders in `planning/`. If they disagree, the planning folders are the source of truth.
- `active_wayfinding_maps` — should match `planning/STATUS.md → Open Wayfinder maps`. The tracker locator is canonical; reconcile a missing mirror without treating the map as a feature folder.
- `pending_model_routes` — resumable `selected`, `running`, `waiting_manual`, or `blocked` routes should match `planning/STATUS.md → Pending Plan routes`. `linked_wayfinder` stays linked to its map but does not count as a resumable planner.
- `pending_closeouts` — retain one record per shipped feature until production verification, doc-close, and the feature retro are complete; its count must match `status.pending_closeouts`.
- Branch hygiene — inspect `git status -sb` and host PR state. A dirty/diverged `main`, or a current branch whose PR is merged, is an event signal before recommending implementation.

If anything was stale, update `.playbook-state.yml` before evaluating cadences. Mention the reconciliation briefly in the response (one line).

When invoked from a terminal `playbook_result`, consume its `next_stage` and ordered `required_actions` before evaluating lower-ranked work. Recompute status automatically after the preceding state write. Never discard a required closeout action merely because the prose handoff mentioned another idea.

Completion criterion: observable feature folders, open-map pointers, and the persisted state file agree.

### Step 3 — Evaluate cadences

For each entry in `playbook-cadences.yml`, check whether it's triggered. If `compute-status.py` refreshed the block in Step 1, count and time cadences are already represented there; hand-reconcile them only when the script is unavailable. Event cadences still belong to this skill because they need git context.

**Count cadences** (e.g. `slices_since_last_architecture_review`):

- If `counter < nudge_threshold` — not triggered.
- If `nudge_threshold <= counter < insist_threshold` — fire at severity `nudge`.
- If `counter >= insist_threshold` — fire at severity `insist`.

**Time cadences** (e.g. `days_since_last_retro`):

- Same logic, with day counts.
- `verification-map-drift` is special only in its input guard: it is silent
  unless `decisions.verification_map_maintenance: true` and one canonical
  selected harness path exist and that path matches its explicit persisted
  binding. Its age is the later of the valid enable and accepted complete-audit
  timestamps, measured across UTC day boundaries. An enabled malformed or
  unbound selection, or a missing selected directory, is an actionable status
  error, not a quiet opt-out; route it to stage 09 before any maintenance
  execution. The calculator never runs an audit, creates receipt/transcript
  state, or infers a selection transition.

**Event cadences** (e.g. `pr_touches_auth_or_payments`):

- Check the trigger condition (typically a git diff or file pattern).
- If matched, fire at the configured severity.

Known event triggers:

- `dirty_or_diverged_main` — current branch is `main` and `git status -sb` shows uncommitted changes, ahead, behind, or diverged remote state.
- `current_branch_pr_merged` — the host reports the current branch's PR merged; follow-up implementation requires updated `main` and a fresh branch.
- `git_hotspot_paths` — recent git history shows matching files touched at or above `min_touches` within `since_days`; use this to surface architecture review when churn concentrates in the same files.

Completion criterion: every configured cadence is classified as inactive, `nudge`, or `insist`, with event evidence where required.

### Step 4 — Combine with closeout, pending Plan, Wayfinder, and feature state

In addition to cadences, look at `pending_closeouts`, `pending_model_routes`, `active_wayfinding_maps`, and `active_features`:

- Any pending feature closeout — recommend its next missing action: production verification, doc-close, then feature retro. Never say “ready for new work” while one exists. When doc-close and the feature retro will run in the same session, recommend them as one closeout branch and PR (stage 10's closeout mechanics), not a docs PR per step.

- Any resumable pending Plan route — recommend continuing it as already-started planning work. Show request title, status, selected model/runner, and exact resume action from launch mode and handoff path. Never say “no active work” while one exists.

- Any open Wayfinder map — recommend continuing the oldest listed map by its linked title before proposing new feature work (Step 5 ranks it against in-flight features). `What to run` is `/wayfinder {locator}`; because the skill is user-invoked, surface the command and wait for the human to invoke it.

- Any feature in `status: aligning` — recommend continuing stage 01.
- Any feature in `status: spec-written` (or legacy `prd-written`) and not yet in `status: sliced` — recommend stage 04.
- Any feature in `status: sliced` or `status: in-flight` with `slices_open > 0` — recommend stage 07 on the next slice, surfacing the build choice (**build one** / **build all** / **build to <slice>**) with the open AFK/HITL counts, per stage 07's build-choice section.
- Any feature in `status: ready-to-ship` (all slices complete, not yet shipped) — recommend stage 10, surfacing the ship menu (**ship PR** / **ship and clean up** / **clean up only** / **stop here**).

Completion criterion: every pending route, open map, and active feature contributes its next eligible resume/discovery/stage action or a named blocker.

### Step 5 — Rank and present

Combine the cadence triggers and the feature-state triggers. Rank by:

1. `insist` severity items first.
2. Then a pending feature closeout, oldest shipped first.
3. Then a resumable pending Plan route, oldest listed first. It is already-started planning work, not a new feature.
4. Then active feature-progress items.
5. Then an open Wayfinder map, oldest listed first — only when no active feature is in flight.
6. Then branch-hygiene nudges that would affect new implementation work.
7. Then `nudge` severity cadences whose dismissal count is 0.
8. Then `nudge` cadences with a non-zero dismissal count.

Present the top recommendation in the shape above. If there are more than one, list up to three. A pending Plan recommendation uses its exact resume action and no cadence dismissal replies. For a Wayfinder recommendation, use its narrower `Invoke` line and do not offer the cadence dismissal replies.

If the user replies `defer`, decrement nothing — just note in `.playbook-state.yml` under `dismissals:` with `action: deferred` and the timestamp. The recommendation will fire again in the next session.

If the user replies `skip`, log under `dismissals:` with `action: skipped` and the timestamp. If the same cadence has been skipped three times in a row, the next retro will flag the cadence for review.

If the user replies `yes`, route to the relevant stage file in `10-process/` and follow the procedure there. For a Wayfinder recommendation, show `/wayfinder {locator}` and wait for the human to invoke that user-owned workflow.

Completion criterion: the user receives one evidence-backed recommendation (up to three when tied); pending Plan and Wayfinder recommendations leave an exact resume/invocation command, while any offered accept/defer/skip action is routed or recorded.

## Guardrails

- Treat `archive/` as its status count only; archived contents stay outside routing context.
- Read planning folders only for `active_features`.
- Leave `playbook-cadences.yml` unchanged until a retro tunes it.
- Preserve configured severity: `nudge` informs and `insist` can block.
- After two declines in one conversation, rank the next eligible recommendation.

## A worked example

→ `EXAMPLE.md` in this folder. Read it if the ranking logic is unclear — but do not read it on every invocation.

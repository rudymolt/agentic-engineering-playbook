# 12 · Retro and learn

> The self-improvement loop. Runs weekly and after every shipped feature. This is where lessons promote from session to project to playbook.

**This stage in one breath:** Reflect on the period or the shipped feature and promote lessons from session → project → playbook. Output: retro notes, tuned cadences, promoted learnings.

---

## When to run

- **Weekly** — `days_since_last_retro >= 7` (derived by diffing `last_run.retro` in `.playbook-state.yml` against today).
- **After every shipped feature** — as part of the doc-close ritual in stage 10.
- **When `/whats-next` flags it overdue.**
- **When `learnings-refresh` is due** — the refresh rides the retro.

## What to run

Both retros are independently callable:

| Purpose | Claude command | Codex command |
|---|---|---|
| gstack delivery/team retrospective | `/retro` | `$gstack-retro` |
| Matt Pocock agent-environment retrospective | `/matt-retro` | `$matt-retro` |

Use gstack for the usual weekly or shipped-feature discussion; `/retro global`
provides a weekly view across projects. Offer Matt's command for a deeper look
at session friction, checks, instructions and tooling. The human invokes it;
a stage or another skill must not silently start this explicit-only command.
Either command can run independently; when both are selected for one stage-12
retro, combine their findings into one retro record.

**`/retro` is the facilitator, not the output.** The gstack skill runs the discussion; it knows nothing about this playbook's files. The stage is complete only when the discussion has been written to `planning/retros/{YYYY-MM-DD}.md` using the project's `retro-template.md` — including its §8 checklist, which carries the eval and field-report checks. An agent that runs `/retro` and stops has held a conversation, not run stage 12.

Also: `/learn` (gstack) — captures session-level learnings into the GBrain memory layer. Run at the end of any non-trivial session, before `/handoff`.

Before finishing the retro, audit learning coverage: compare `.playbook-state.yml` shipped-slice and feature counters, git/PR/session evidence, and the current `/learn` entries. Pick one or two shipped slices at random — if you cannot explain what changed and why, your mental map has fallen behind; read them before closing the retro. If the project has substantial shipped work but only a thin learning log, ask the human for 1-3 concrete lessons and capture them before closing the session.

For every retro period that includes shipped slices or independent verification, add the observational eval row from the template. Draft it from git and PR evidence, then let the human correct ambiguous attribution:

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---:|---|---:|---:|
| {start → end} | {n} | {corrected-after-gate slices / shipped slices} | {median / maximum} | {n} | {n} |

- **Rework rate:** the fraction of shipped slices needing correction after they had passed stage 08/09.
- **Time-to-merge:** elapsed time from the slice's first implementation commit to PR merge; report median and maximum. Use feature/branch granularity when slice attribution is unavailable and say so.
- **Verifier catches:** independent stage 08/09 passes with at least one medium-or-higher finding verified by execution; `Catches` is a subset of `Verifier passes`.
- Use `unavailable — {reason}` rather than inventing a value when commit, PR, or verdict evidence is missing. A retro cannot close without either a populated row or that explicit evidence-gap explanation. Periods with no shipped or verified work record `not applicable — no qualifying work`.

These values are observational. Collect a three-period baseline for sample application; introduce no targets, thresholds, or gates until that review. Carry the same row into `field-report.md` whenever a report is filed.

## The retro template

Include an environment-improvement pass, drawing on
[Matt's v1.3.1 retro](https://github.com/mattpocock/skills/blob/v1.3.1/skills/engineering/retro/SKILL.md):
identify navigation friction, missing checks, confusing instructions and wasted
tool calls from actual session evidence. Prefer a deterministic check for a
mechanical mistake; keep judgement calls in review guidance. Propose changes
through this stage's promotion rules rather than editing settings automatically.
For the complete Matt workflow, the independently callable
[`matt-retro` adapter](../skills/matt-retro/SKILL.md) includes the exact pinned
source and license. Bootstrap/upgrade install it under its distinct name.
The bare `/retro` route remains gstack's.

Use `templates/retro-template.md` as the structure. Sections:

1. **What worked.** Specific, ideally with evidence.
2. **What didn't.** Specific, with the underlying reason. Check the failure against the five named anti-patterns:
   - **Nodding** (no independent verification), **Amnesiac** (no persistence), **Manual** (no scheduling), **Blind** (no discovery), **Tangled** (no isolation/handoff).
3. **What we learned.** A short list — each item is a candidate for promotion.
4. **Cadence review.** Were any cadences dismissed this period? Are the thresholds in `playbook-cadences.yml` right?
5. **Learning coverage and observational eval.** Do the captured `/learn` entries reflect the shipped work, and does the retro contain the required eval row or explicit evidence-gap explanation?
6. **Promotion candidates.** Which learnings should become:
   - A new rule in this project's `CLAUDE.md`?
   - A new entry in `GLOSSARY.md`?
   - A new ADR?
   - A change to this playbook?
   - A new skill?

## Promotion rules

A learning earns promotion to the playbook when **any** of:

- It has appeared in three or more projects.
- It would have prevented a real incident.
- It changes a stage's invariants (not just its parameters).

Lower-bar things stay in `CLAUDE.md` or `GLOSSARY.md`. The playbook is the shared bedrock — it should change slowly and deliberately.

## When a cadence is wrong

If the same cadence has been dismissed three times in a row, the retro asks:

- Is the threshold wrong? (e.g. architecture review nudging at 3 slices should actually nudge at 5)
- Is the trigger wrong? (count-based when it should be event-based, or vice versa)
- Is the action wrong? (we should be running a different skill)

Update `playbook-cadences.yml` accordingly. Log the change in `CHANGELOG.md` at the playbook root if it generalises across projects.

## When a Wayfinder map goes stale

An open map is a valid durable deferred state, but not forever by accident. For each entry in `.playbook-state.yml → active_wayfinding_maps` whose `opened` date is more than 30 days old, ask the human for an explicit disposition and record it in the retro note:

- **Continue** — the destination still matters; the next frontier session remains `/wayfinder {locator}` (human-invoked, as always).
- **Defer intentionally** — record the reason on the map and in the retro note; the map stays open and visible.
- **Abandon** — follow the abandoned-or-deferred outcome in [`../92-wayfinder-track.md`](../92-wayfinder-track.md): record the disposition, close the map, and clear both visibility pointers.

This review is the accountability backstop for open maps, which `/whats-next` surfaces without a dismissal counter.

## What this stage produces

- A short markdown retro at `planning/retros/{YYYY-MM-DD}.md` (or merged into the doc-close release note for feature-shipped retros). A feature retro run in the same session as doc-close rides the same closeout branch and PR (stage 10's closeout mechanics); only a retro deferred to a later session opens its own.
- A learning coverage note that names the shipped-work evidence checked and any new lessons captured.
- An observational eval row for periods with shipped slices or independent verification, or an explicit reason the required evidence was unavailable.
- **A field-report decision (v0.5 evidence loop).** Explicitly check the four proof events (independent-verifier catch, budget-ceiling trip, acceptance-criteria refusal, structured escalation) and the friction signals against this period. If any occurred, complete the project's `field-report.md` and copy it to the playbook repo's `analysis/field-reports/{YYYY-MM-DD}-{project-slug}.md`. If none occurred, record "no proof events this period" in the retro — that line is the evidence the check happened.
- Updates to `CLAUDE.md`, `GLOSSARY.md`, `playbook-cadences.yml`, or this playbook if any candidates were promoted.
- Updates to MEMORY.md if any cross-project lessons emerged.
- For every delivery mission, a denominator-preserving disposition:
  qualifying, nonqualifying, cancelled, or externally completed. Keep product
  outcome separate from automated K4.1 qualification; a later human merge
  cannot repair an immutable defective control chain. Record process-attested
  limitations explicitly and never promote them into Tier B/C evidence.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
last_run:
  retro: {ISO timestamp}
pending_closeouts:
  # Set this feature's retro: complete, then remove the entry once production_verified
  # is true and both doc_close and retro are complete. Do not clear another feature's closeout.
```

(`days_since_last_retro` is not a stored counter — `/whats-next` derives it by diffing `last_run.retro` against today. Setting the timestamp is the whole reset.)

For a feature retro, find the matching `pending_closeouts` entry, mark `retro: complete`, and remove it only when `production_verified: true` and `doc_close: complete` too. Recompute status after removal. A weekly retro that does not cover a pending shipped feature must leave that entry visible.

Return `playbook_result` from the process-map terminal contract. Set `next_stage: /whats-next`; list any still-missing production verification, doc-close, or feature retro in `required_actions`. `/whats-next` recomputes status and ranks those actions before planning or new work.

---

## Next

- Retro done, next feature ready → open `01-align.md`
- Lessons worth promoting → follow `../40-self-improvement.md`
- Cadence thresholds felt wrong → tune `playbook-cadences.yml` and log it in the playbook `CHANGELOG.md`
- Unsure → run `/whats-next`

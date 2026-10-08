# Retro — {YYYY-MM-DD} · {scope}

> Scope: {weekly | feature-ship | project-close | other}
> Period covered: {start date} → {end date} (or feature slug)
>
> See `{playbook-path}/v0.5/10-process/12-retro-and-learn.md` for how this fits the loop.
> Match the retro's length to its substance — specific evidence, then stop; no filler
> sections, redundant summaries, or boilerplate. Short honest sections beat padded ones.

---

## 1. What worked

Specific, ideally with evidence (commit hash, slice ID, time saved, bug avoided).

- {…}
- {…}

## 2. What didn't

Specific, with the underlying reason — not just "we ran out of time".

- {…}
- {…}
- Does this failure match one of the five anti-patterns (Nodding / Amnesiac / Manual / Blind / Tangled)?

## 3. What we learned

Each item is a candidate for promotion. Mark candidates with the proposed destination.

- {learning} → {`CLAUDE.md` | `GLOSSARY.md` | new ADR | playbook V0.X | new skill}
- {learning} → {…}

## 4. Cadence review

Pull from `.playbook-state.yml` under `dismissals:`.

| Cadence | Times accepted | Times deferred | Times skipped | Recommendation |
|---|---|---|---|---|
| architecture-review | {N} | {N} | {N} | {keep | tune thresholds | change trigger | retire} |
| retro-weekly | {N} | {N} | {N} | {…} |
| {…} | | | | |

If any cadence was skipped 3+ times in a row, decide:

- Threshold wrong? (e.g. 3–5 should be 5–7)
- Trigger wrong? (count when it should be event, or vice versa)
- Action wrong? (we should run a different skill)

Update `playbook-cadences.yml` accordingly.

## 5. Learning coverage and observational eval

Name the `.playbook-state.yml`, git, PR, review-verdict, and `/learn` evidence checked. Pick one or two shipped slices at random and confirm you can explain what changed and why.

- Learning coverage: {complete | gaps captured below}
- Evidence gaps or newly captured lessons: {none | …}

For a period with shipped slices or independent verification, populate this row. If a required value cannot be recovered, write `unavailable — {reason}` rather than estimating it. If there was no qualifying work, write `not applicable — no qualifying work`.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---:|---|---:|---:|
| {start → end} | {n} | {corrected-after-gate slices / shipped slices} | {median / maximum} | {n} | {n} |

Definitions: rework happens after a slice passed stage 08/09; time-to-merge runs from first implementation commit to PR merge; a catch is a verifier pass with a medium+ finding proven by execution. State when feature/branch granularity replaces slice attribution. These are observational measures only—do not introduce targets or gates before the three-period baseline review.

## 6. Promotion candidates

For each learning marked for promotion above, decide now:

- **Promote to `CLAUDE.md`** — project-wide rule.
- **Promote to `GLOSSARY.md`** — new domain term.
- **Promote to new ADR** — hard-to-reverse decision.
- **Promote to playbook V0.X** — has appeared in 3+ projects, or would have prevented a real incident, or changes a stage's invariants.
- **Promote to new skill** — a procedure that should run identically every time, invoked often, well-defined inputs/outputs.

Log playbook-level promotions in the playbook's `CHANGELOG.md`.

## 7. Field report (v0.5 evidence loop)

Did any proof event happen this period — an independent-verifier catch, a budget-ceiling trip, an acceptance-criteria refusal, or a structured escalation? If yes (or if friction is accumulating), fill in `field-report.md` (template beside this one), copy the observational row from §5, and carry the report back to the playbook repo's `analysis/field-reports/`. The playbook is a copy in this repo; evidence only reaches the maintainer if it is carried back.

## 7b. Decisions and follow-ups

Anything that doesn't fit the above but needs action.

- [ ] {action} — owner: {name}, by: {date}
- [ ] {action} — owner: {name}, by: {date}

## 8. State updates applied

Confirm the following were updated:

- [ ] `.playbook-state.yml` `last_run.retro` set to today (day counters are derived from `last_run` timestamps — nothing else to reset)
- [ ] `playbook-cadences.yml` tuned if needed
- [ ] `CHANGELOG.md` at the playbook root if anything was promoted upward
- [ ] Learning coverage and observational eval checked (§5): row populated, evidence gap explained, or no qualifying work recorded
- [ ] Field report checked (§7): proof events + friction reviewed; if any occurred, `field-report.md` completed with the same eval row and copied to the playbook repo's `analysis/field-reports/`; if none, "no proof events this period" recorded above

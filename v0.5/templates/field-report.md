# Field report — {project name}

> Evidence from a real project running playbook v0.5, for the playbook maintainer. Fill this in at a retro (the retro template links here) or whenever one of the proof events below happens. When complete, copy this file back to the **playbook repo** at `analysis/field-reports/{YYYY-MM-DD}-{project-slug}.md` — the playbook is copied into project repos, so evidence only travels back if a human carries it. Match the report's length to the evidence — cover what happened, then stop; no filler sections, redundant summaries, or boilerplate.

- **Project:** {name / one-line description; private details may be redacted}
- **Playbook version:** {playbook_version from .playbook-state.yml}
- **Period covered:** {start} – {end}
- **Slices shipped this period:** {n}

## Observational eval baseline

Copy this row from the retro. Use `unavailable — {reason}` instead of estimating missing evidence, and state when feature/branch granularity replaces slice attribution.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---:|---|---:|---:|
| {start → end} | {n} | {corrected-after-gate slices / shipped slices} | {median / maximum} | {n} | {n} |

Rework is correction after a slice passed stage 08/09. Time-to-merge runs from first implementation commit to PR merge. A catch is an independent verifier pass with a medium+ finding proven by execution. These values are observational; they create no target or gate before the three-period baseline review.

## Proof events (the evidence the v0.5 autonomy gate is waiting for)

Record each occurrence with a date and one or two sentences. "None" is a valid and useful answer.

### 1. Independent verifier caught a real defect

The implementing agent believed the slice was done; a fresh-context reviewer (stage 08) found a genuine problem, verified by executing. This is the single most important event — it is what proves the checker works outside the lab.

- Date, slice, finding, severity, and how it was verified (command/browser evidence):
- Would self-review plausibly have caught it? (honest guess):

### 2. A run-level ceiling tripped and paused correctly

A run hit a §11 ceiling and **paused with a report** instead of continuing. Qualifying trips are **run-level**: max-iteration, wall-time, or no-progress halt (any billing), or a cost/quota cap (API billing). A max-retry escalation belongs under proof event 4, not here — this event is about the brake stopping a runaway, not a routine retry-then-escalate. A **deliberate drill** (tight ceiling on a real task, provoked to verify the pause-and-report machinery) counts — mark it clearly as a drill.

- Date, which ceiling, what the run was doing, what happened next:

### 3. Acceptance-criteria gate refused a build

The agent declined to start stage 07 because a slice lacked its verification target, and routed back to alignment instead of inventing criteria.

- Date, slice, what was missing:

### 4. Structured escalation instead of thrashing

A blocked loop stopped after its bounded attempts and produced the escalation template (blocker, evidence, attempts, hypothesis, ask).

- Date, what was blocking, whether the escalation was useful:

## Friction (equally important — the anti-bloat signal)

- Gates that produced ceremony rather than value (findings with no substance, evidence bureaucracy on trivial changes, prompts you started ignoring):
- Cadences dismissed repeatedly (from the state file's dismissal log):
- Anything the playbook made *slower* without making it safer:

## Verdict

- **Working as expected?** {yes / partially / no — one paragraph}
- **Recommended playbook action:** {keep the current rule | change it | collect more evidence — name the rule and why}

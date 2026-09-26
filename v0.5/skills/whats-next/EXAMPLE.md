# /whats-next — worked example

> Escape hatch from `SKILL.md`. Read this if the ranking or output format is unclear. Do not read it on every skill invocation.

## Inputs

`.playbook-state.yml`:
```yaml
counters:
  slices_since_last_architecture_review: 4
  slices_shipped_total: 12
last_run:
  retro: 2026-06-23        # 9 days before evaluation — derived days_since_last_retro: 9
  doc_close: 2026-07-02    # evaluation day — derived days_since_last_doc_close: 0
active_features:
  - slug: athlete-results-export
    status: sliced
    slices_open: 2
```

`playbook-cadences.yml`:
```yaml
cadences:
  - id: architecture-review
    type: count
    counter: slices_since_last_architecture_review
    nudge_threshold: 3
    insist_threshold: 6
    action: /improve-codebase-architecture
    rationale: Deep-module drift accumulates fastest in this window.
  - id: retro-weekly
    type: time
    counter: days_since_last_retro
    nudge_threshold: 7
    insist_threshold: 14
    action: /retro
    rationale: Lessons go cold after a week.
```

## Output

> **Next (1 of 2):** Architecture review — `/improve-codebase-architecture`.
>
> **Why:** 4 slices shipped since the last review (nudge threshold: 3, insist: 6). Deep-module drift accumulates fastest in this window.
>
> **What to run:** `/improve-codebase-architecture`
>
> ---
>
> **Next (2 of 2):** Weekly retro — `/retro`.
>
> **Why:** 9 days since last retro (nudge: 7, insist: 14). Lessons go cold after a week.
>
> **What to run:** `/retro`
>
> ---
>
> **In flight:** `athlete-results-export` has 2 slices open. Stage 07 once you've cleared the above.
>
> Reply `yes` to proceed with the architecture review · `defer` to snooze · `skip` to log a dismissal.

## Why this output

- Architecture review fires first: `nudge` (4 slices ≥ nudge threshold 3), dismissed 0 times.
- Retro fires second: `nudge` (9 days ≥ nudge threshold 7), dismissed 0 times.
- Both are `nudge`, neither is `insist` — so work can proceed after acknowledgement.
- The in-flight feature is listed but ranked below both overdue cadences (Step 5 rank order: insist → branch hygiene → undismissed nudge cadences → feature progress).

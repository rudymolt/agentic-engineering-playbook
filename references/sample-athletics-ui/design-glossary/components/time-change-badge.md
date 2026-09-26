# time-change-badge

**One-line definition.** A `time-change-badge` shows a rescheduled time as old → new with the delta.

**Anatomy.** Pill, 1px border + `14%` tint of the status colour, `font-weight: 800`, tabular numerals; struck-through old time in `--text-tertiary`, faded arrow.

**Usage.** On timetable rows whose start time has moved. Replaces low-contrast "[CHANGED] was…" text.

**Variants.** Default amber (`--status-amber`) for small moves; `big` red (`--status-red`) for large moves.

**States.** Static.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do show the computed delta (e.g. `−10 min`).
- Don't use the red `big` variant for routine ±5-minute shifts.

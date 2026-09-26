# entry-status-chip

**One-line definition.** An `entry-status-chip` shows an athlete's competition-entry state — Confirmed (green) or Planned (neutral) — as a compact chip beside the name on the Results table.

**Anatomy.** `.entry-chip` — small inline-flex rounded pill, `font-size: 11px`, `font-weight: 800`, `padding: .05rem .5rem`; neutral border/`--bg-base` fill by default. `.entry-chip.confirmed` switches text to `--status-green` with a faint green border and fill. Colour is always paired with the word ("Confirmed entry" / "Planned entry"), never colour-only.

**Usage.** The Athlete / relay column of the daily Results table, replacing the older grey `result-participant-meta` sub-text. Reflects the competition entry's status, not a result status (use `status` chips for results).

**Variants.** default (neutral = Planned), `confirmed` (green).

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do pair the colour with the word so confirmed/planned is never colour-only.
- Don't use it for result state (completed / DNS / DNF) — that's a `status` chip.

> Note: the `sex-indicator` also has a **bare-symbol variant** — just ♂/♀ (sex-tinted, with a `title`) — for narrow M/F table columns, as used on the Roster.

**Related.** [sex-indicator](sex-indicator.md)

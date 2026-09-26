# place-num

**One-line definition.** A `place-num` is the plain finishing-place number (4th and below) shown in the daily Results table, paired with `medal-icon`s for 1st–3rd.

**Anatomy.** `.place-num` — bold, tabular-figures (`font-variant-numeric: tabular-nums`), `--text-secondary`. No border or fill; lighter than a `place-badge`.

**Usage.** The Place column of the daily Results table and its legend. Distinct from `place-badge`, which is the bordered pill used in the Mission Control Final Placings table; the daily Results table favours the plainer number.

**Variants.** None.

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do use a `medal-icon` for 1st–3rd and `place-num` for 4th+.
- Don't introduce a second numeric-place style; reuse `place-num` (Results) or `place-badge` (Final Placings).

**Related.** [medal-icon](medal-icon.md), [place-badge](place-badge.md)

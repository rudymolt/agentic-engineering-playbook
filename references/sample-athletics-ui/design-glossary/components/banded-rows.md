# banded-rows

**One-line definition.** A `banded-rows` treatment is the zebra-striping + hover applied to table and list rows so each row reads as a distinct band.

**Anatomy.** Odd rows `var(--bg-base)`, even rows `var(--bg-elevated)`; cell borders softened to `color-mix(--border-subtle 55%)`; hover row `rgba(141,27,61,.20)` (burgundy) with a `120ms` background transition.

**Usage.** All multi-row `table` bodies and any `.list-row` group inside a `.stack`. Not for single-row or card layouts.

**Variants.** None — one banding rule applies everywhere for consistency.

**States.** Hover = burgundy active row (declared last so it wins over the band).

**Kitchen-sink anchor.** [#tables](../../sample-athletics-ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do let the band do the separating; keep cell borders faint.
- Don't add a second highlight colour on top of the burgundy hover.

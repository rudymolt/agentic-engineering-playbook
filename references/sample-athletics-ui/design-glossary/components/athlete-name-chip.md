# athlete-name-chip

**One-line definition.** An `athlete-name-chip` is a rounded pill showing one athlete's name, colour-coded by sex.

**Anatomy.** `border-radius: 999px`, 1px `currentColor` border on a `color-mix(currentColor 12%)` fill, `font-weight: 800`, padding `0 var(--space-3)`, `min-height: 26px`.

**Usage.** Inside entry/result previews and dense rows where athletes are referenced. Not for free-text labels.

**Variants.** `male` (`--status-blue`), `female` (`--status-pink`), `count` (`--text-secondary`, e.g. `+3`).

**States.** Static; inherits the row hover. Add a focus ring only if made interactive.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do use the `count` variant to collapse overflow (`+3`).
- Don't encode any meaning other than sex in the colour.

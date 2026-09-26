# place-badge

**One-line definition.** A `place-badge` is a small pill showing a non-medal finishing place (4th–8th).

**Anatomy.** Inline-flex pill, `min-width: 42px`, 1px `--status-blue` border and text, centred. Used in the Final Placings place column for diploma places.

**Usage.** 4th–8th rows/tiles. 1st–3rd use a `medal-icon`, not a badge.

**Variants.** None (medals replace 1st–3rd).

**States.** Static.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do centre the badge in the place column (`.place-centered`).
- Don't number 1st–3rd here; use medals.

**Related.** [medal-icon](medal-icon.md)

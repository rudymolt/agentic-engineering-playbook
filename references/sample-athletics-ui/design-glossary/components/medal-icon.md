# medal-icon

**One-line definition.** A `medal-icon` is a small ribboned-disc icon whose colour encodes a podium place — gold (1st), silver (2nd), bronze (3rd).

**Anatomy.** Inline SVG (`.medal`) sized 14–22px; disc filled with `currentColor`, ribbons as a faint stroke, a base-colour star cut-out. Colour set by `.gold` (`--qatar-gold`), `.silver` (`--silver`), `.bronze` (`--bronze`).

**Usage.** Anywhere a 1st–3rd placement is shown: Final Placings place column, placing tiles, the legend, and "Nth final" result lines. Replaces the numerals 1/2/3. 4th–8th use a `place-badge` instead.

**Variants.** `gold`, `silver`, `bronze`.

**States.** Static. Always carries an `aria-label`/`<title>` so place is not conveyed by colour alone.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do give every medal an `aria-label` ("Gold — 1st").
- Don't use a medal for 4th–8th; those are diplomas, not medals.

**Related.** [place-badge](place-badge.md)

# placing-tile

**One-line definition.** A `placing-tile` is one cell in the 1st–8th medal-count strip showing a place and the team's count at that place.

**Anatomy.** `.placings` is an 8-column grid (4 on narrow); each `.placing` is a bordered, centre-aligned tile with a `.lbl` (place / medal) over a large tabular `.val` count. `g1`/`g2`/`g3` tint the gold/silver/bronze tiles; 1st–3rd labels use a `medal-icon` via `.medal-lbl`.

**Usage.** Team performance summary on Mission Control / Results. Always the full 1st–8th set, even when a count is `-`.

**Variants.** `g1`, `g2`, `g3` (medal tints); plain for 4th–8th.

**States.** Static.

**Kitchen-sink anchor.** [#containers](../../sample-athletics-ui-kitchen-sink.html#containers)

**Do / Don't.**

- Do centre the tile contents.
- Don't drop empty places; show `-` so the podium shape stays readable.

**Related.** [medal-icon](medal-icon.md)

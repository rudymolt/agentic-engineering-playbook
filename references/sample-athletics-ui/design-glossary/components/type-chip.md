# type-chip

**One-line definition.** A `type-chip` is a compact pill marking a record's category (e.g. Athlete / Staff) in a dense table cell.

**Anatomy.** Small inline-flex pill, `font-size: 11px`, `font-weight: 800`, `padding: .1rem .55rem`; neutral by default, `.staff` is gold-tinted (`--qatar-gold`).

**Usage.** Category columns in list tables where a full `pill` would be too heavy. Not for state (use `status`) or athlete sex (use the sex indicator).

**Variants.** default (neutral), `staff` (gold-tinted).

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do keep it compact and reserve the gold tint for one meaningful category.
- Don't use it for status — that's what `status` chips are for.

# tag-input

**One-line definition.** A `tag-input` is a field that holds removable chips plus a free-text entry.

**Anatomy.** Bordered `--bg-input` wrap; each `tag` is an `--accent-muted` chip with a `×` remove button; a borderless `input` flexes to fill.

**Usage.** Multi-value entry such as events or labels. Not for single selection (use `select`).

**Variants.** None.

**States.** Field focus; per-tag remove hover.

**Kitchen-sink anchor.** [#inputs](../../sample-athletics-ui-kitchen-sink.html#inputs)

**Do / Don't.**

- Do give every tag a labelled remove control.
- Don't use it where order is meaningful without drag support.

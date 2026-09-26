# status-legend

**One-line definition.** A `status-legend` is an inline key mapping a status colour to its meaning.

**Anatomy.** Flex row of `leg` items, each a 9px `dot` plus `--text-secondary` label; `gap: var(--space-4)`.

**Usage.** Above or beside any view that relies on status colour (e.g. clock colours). Pairs colour with words for accessibility (WCAG 1.4.1).

**Variants.** None.

**States.** Static.

**Kitchen-sink anchor.** [#feedback](../../sample-athletics-ui-kitchen-sink.html#feedback)

**Do / Don't.**

- Do show a legend wherever colour carries meaning.
- Don't rely on the colour alone without the legend.

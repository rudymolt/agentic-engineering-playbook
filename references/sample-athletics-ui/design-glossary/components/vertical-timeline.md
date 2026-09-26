# vertical-timeline

**One-line definition.** A `vertical-timeline` is a top-to-bottom list of events on a single connecting rail.

**Anatomy.** `vt-item` rows with a left border rail and an absolutely-positioned `vt-dot`; body has bold title over a muted `vt-time`.

**Usage.** Activity/audit history in a panel or drawer. For tabular history prefer a table.

**Variants.** Dot colour: gold (default), `green`, `amber`, `muted`.

**States.** Static; last item drops the rail.

**Kitchen-sink anchor.** [#workflow](../../sample-athletics-ui-kitchen-sink.html#workflow)

**Do / Don't.**

- Do order newest-first or oldest-first consistently.
- Don't use it for large datasets that need sorting/filtering.

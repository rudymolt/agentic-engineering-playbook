# stepper

**One-line definition.** A `stepper` shows progress through an ordered, multi-step flow.

**Anatomy.** Flex row of `step` items (numbered `num` badge + label) joined by thin `bar` connectors.

**Usage.** Import → review → publish style wizards. Not for free navigation between unrelated views (use tabs).

**Variants.** `done` (green check), `active` (burgundy/gold, bold), default (muted, upcoming).

**States.** done / active / upcoming.

**Kitchen-sink anchor.** [#workflow](../../sample-athletics-ui-kitchen-sink.html#workflow)

**Do / Don't.**

- Do mark exactly one step active.
- Don't use a stepper for more than ~5 steps.

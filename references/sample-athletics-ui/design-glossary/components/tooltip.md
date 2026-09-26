# tooltip

**One-line definition.** A `tooltip` reveals a short explanatory string on hover/focus of a dotted-underline term.

**Anatomy.** `.tip` with dotted bottom border; `::after` bubble on `#000`, 1px border, `max-width: 240px`, appears above the term.

**Usage.** Define jargon or clarify a control inline. Keep to one short sentence.

**Variants.** None.

**States.** Shown on `:hover` and `:focus-visible` (keyboard-accessible via `tabindex="0"`).

**Kitchen-sink anchor.** [#overlays](../../sample-athletics-ui-kitchen-sink.html#overlays)

**Do / Don't.**

- Do make the trigger keyboard-focusable.
- Don't put essential, action-critical information only in a tooltip.

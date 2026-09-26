# announcement-banner

**One-line definition.** An `announcement-banner` is a full-width notice with an icon, message, and optional action.

**Anatomy.** Flex row, gold-tinted fill with a 3px gold left border, `--radius-md`; leading badge/icon, body (`strong` + muted `p`), trailing action.

**Usage.** Page- or section-level informational notices. Not for inline form validation (use `message`).

**Variants.** Tone follows status tokens if needed (default gold/info).

**States.** Static; dismiss action optional.

**Kitchen-sink anchor.** [#feedback](../../sample-athletics-ui-kitchen-sink.html#feedback)

**Do / Don't.**

- Do keep it to one message and at most one action.
- Don't stack multiple banners; consolidate.

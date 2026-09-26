# sex-indicator

**One-line definition.** A `sex-indicator` shows an athlete's sex as a gender symbol plus label — `♂ Male` (blue) / `♀ Female` (pink).

**Anatomy.** `.sex` inline-flex; `.sex.male` = `--status-blue`, `.sex.female` = `--status-pink`. Pairs with a sex-tinted `avatar` (`.avatar.male` blue, `.avatar.female` pink). When stacked under a name, indent to align with the name, not the avatar.

**Usage.** Athlete identity blocks and lists (e.g. By Athlete). Distinct from the World Athletics event category code (M/W) used in event names like "M 3000m".

**Variants.** `male`, `female`.

**States.** Static.

**Kitchen-sink anchor.** [#buttons](../../sample-athletics-ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do tint the avatar to match the sex symbol (blue/pink).
- Don't confuse the athlete sex indicator with the event category code (M/W).

**Related.** [avatar](avatar.md)

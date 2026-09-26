# disclosure-row

**One-line definition.** A `disclosure-row` is a `<details>` row that expands to reveal inline controls, with a rotating chevron.

**Anatomy.** Bordered `--radius-lg` container; `summary` grid `16px 1fr auto`; `.chev` rotates 90° on open; open state adds an inset burgundy left rule and a `--bg-base` body.

**Usage.** Schedule/list rows with secondary controls or detail. Replaces always-open inline forms.

**Variants.** None.

**States.** Hover; `[open]` (chevron rotated, left rule); focus ring on `summary`.

**Kitchen-sink anchor.** [#patterns](../../sample-athletics-ui-kitchen-sink.html#patterns)

**Do / Don't.**

- Do keep the most-used row expanded by default if helpful.
- Don't hide a primary action inside a collapsed row.

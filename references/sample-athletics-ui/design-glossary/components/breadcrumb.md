# breadcrumb

**One-line definition.** A `breadcrumb` is a single-line trail of ancestor links ending in the current page.

**Anatomy.** `.crumbs` flex row; links in `--text-secondary` (hover `--text-primary`); `.sep` slashes in `--text-tertiary`; `.here` current item bold in `--text-primary`.

**Usage.** Top of detail pages reached by drilling down (e.g. Roster / Team / Athlete).

**Variants.** None.

**States.** Link hover; current item is non-interactive.

**Kitchen-sink anchor.** [#navigation](../../sample-athletics-ui-kitchen-sink.html#navigation)

**Do / Don't.**

- Do make every segment except the last a link.
- Don't use breadcrumbs as the primary navigation.

# column-filter-menu

**One-line definition.** A `column-filter-menu` is a table-header popover used to sort one column and choose visible values for that column.

**Anatomy.** Opened from a funnel button in a table heading; contains a compact heading, close control, sort actions, optional value-search input, checkbox value list, apply action, and clear-filter action. The menu is fixed-position, clamps inside the viewport, and uses an internally scrolling checkbox list when needed.

**Usage.** Use on explicitly filterable mission-control table columns. Do not use for page-level filters such as roster state, timetable day, hotel, or transport type.

**Variants.** None for v1; columns supply their own display labels, missing-value labels, and sort/filter metadata.

**States.** Closed; open; active-filter trigger; draft checkbox changes before apply; disabled when a column has no filterable values.

**Kitchen-sink anchor.** [#tables](../../sample-athletics-ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do keep table row rendering page-owned while reusing this menu behavior.
- Don't duplicate the same column controls in a separate page filter panel.

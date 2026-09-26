# standard-table-controls

**One-line definition.** `standard-table-controls` are the reusable mission-control table controls for sorting, column filtering, active filter chips, and table reset.

**Anatomy.** A page-owned `table` inside `.table-wrap`; each controlled header uses `.table-header-controls` with a `.table-sort` label and optional `.table-filter-trigger`; active filters render as `.table-filter-chip` rows above the table; `Reset table` clears `tableSort`, `tableDirection`, and `tableFilter.*` route state.

**Usage.** Mission-control tables where operators need sortable or filterable columns. Page-level workflow controls such as roster state, timetable day, hotel, transport type, and date controls stay outside the table headers.

**Variants.** None for v1; pages supply their own columns, display labels, missing-value labels, row markup, and action cells.

**States.** Default; active sort; active column filter; hover/focus on sort/filter controls; disabled filter trigger when a column has no filterable values.

**Kitchen-sink anchor.** [#tables](../../sample-athletics-ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do keep the row renderer local to the page while sharing header/menu primitives.
- Don't introduce a full generic table renderer until multiple screens have converged on the same row and group model.

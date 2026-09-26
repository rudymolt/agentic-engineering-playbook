# Design Glossary — {project name}

> The textual ubiquitous language for this project's UI. Every UI term in use must appear here exactly once, with a precise definition and a link to its live rendering in `ui-kitchen-sink.html`. Interaction-level decisions (which surface to use when) live in `frontend-design-language-guide.html`.
>
> See `{playbook-path}/v0.5/20-frontend-track.md` for how to use, extend, and maintain this file.

---

## How to use this file

- **Read it before any UI work.** Both humans and agents must use only terms defined here when discussing or writing UI code. (Once this glossary is split — see below — read `design-glossary/index.md` first and open only the entries the feature touches.)
- **Add a new entry the first time a new term is needed**, before writing any code that uses it.
- **One term per concept.** No synonyms.
- **Every entry must anchor to a section in `ui-kitchen-sink.html`** so the textual definition can be checked against the visual one.

## Progressive disclosure — single file vs split

This single file is the default and is correct while the glossary is small. Once it grows past a handful of entries (roughly 30, but split sooner if loading the whole file for a one-component task feels wasteful), switch to the **split form** so an agent working on one component loads that entry instead of the entire glossary:

```
design-glossary/
├── index.md                 # read-first index: one line per component (GENERATED — don't hand-edit)
└── components/<term>.md      # one entry per file, same sub-structure as the Entry template below
```

Split and maintain it with the tooling (run from the project root, the folder holding this file):

```bash
python3 {playbook-path}/v0.5/scripts/check-glossary.py split ./DESIGN-GLOSSARY.md ./design-glossary   # one-time
python3 {playbook-path}/v0.5/scripts/check-glossary.py build-index ./design-glossary                  # after editing entries
python3 {playbook-path}/v0.5/scripts/check-glossary.py check ./design-glossary --kitchen-sink ./ui-kitchen-sink.html
```

In the split form, an entry's references to other components ("use a `medal-icon` instead") become bundle-relative `**Related.**` links, which gives navigable links and backlinks for free. `{playbook-path}/references/sample-athletics-ui/design-glossary/` is a worked example; the rationale and context-cost measurement are in `{playbook-path}/analysis/okf-phase0-measurement.md`. The threshold is project-tunable, not a hard rule — small projects keep the single file.

## Entry template

```markdown
### {term}

**One-line definition.** A {term} is a {category} used for {purpose}.

**Anatomy.** {padding, border, radius, typography, colour roles, shadow. Reference CSS variables by name where possible — e.g. "padding `var(--space-3)` horizontal, `var(--space-2)` vertical".}

**Usage.** {Where this term is allowed to appear, and where it is forbidden.}

**Variants.** {primary, secondary, ghost — each with one line on how it differs from the base.}

**States.** {hover, focus, active, disabled, loading.}

**Kitchen-sink anchor.** [#{term-id}](./ui-kitchen-sink.html#{term-id})

**Do / Don't.**

- Do {one short rule}.
- Don't {one short rule}.
```

---

## Terms

This project starts from the Sample Athletics/championship pilot kitchen sink in `ui-kitchen-sink.html`. New UI terms should be added here only when the implementation introduces a reusable surface or state that is not already covered by the baseline.

### Containers

{Add entries here. Suggested starter set:}

- `default-container`
- `elevated-card`
- `panel`
- `empty-state`

### Controls

- `primary-button`
- `secondary-button`
- `ghost-button`
- `primary-pill`
- `status-badge`

### Forms

- `text-input`
- `select`
- `checkbox`
- `radio`
- `validation-error`

### Navigation

- `top-bar`
- `side-nav`
- `tab-strip`
- `breadcrumb`

### Status & feedback

- `info-alert`
- `warning-alert`
- `error-alert`
- `toast-region`

### Overlays

- `modal`
- `drawer`
- `popover`

---

## New components (v2)

> Added in the v2 kitchen-sink refresh, when reusable surfaces appeared that the Sample Athletics baseline did not already cover. Each entry anchors to a live specimen in `ui-kitchen-sink.html`. Colours reference existing tokens only — no new palette was introduced.

### banded-rows

**One-line definition.** A `banded-rows` treatment is the zebra-striping + hover applied to table and list rows so each row reads as a distinct band.

**Anatomy.** Odd rows `var(--bg-base)`, even rows `var(--bg-elevated)`; cell borders softened to `color-mix(--border-subtle 55%)`; hover row `rgba(141,27,61,.20)` (burgundy) with a `120ms` background transition.

**Usage.** All multi-row `table` bodies and any `.list-row` group inside a `.stack`. Not for single-row or card layouts.

**Variants.** None — one banding rule applies everywhere for consistency.

**States.** Hover = burgundy active row (declared last so it wins over the band).

**Kitchen-sink anchor.** [#tables](./ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do let the band do the separating; keep cell borders faint.
- Don't add a second highlight colour on top of the burgundy hover.

### athlete-name-chip

**One-line definition.** An `athlete-name-chip` is a rounded pill showing one athlete's name, colour-coded by sex.

**Anatomy.** `border-radius: 999px`, 1px `currentColor` border on a `color-mix(currentColor 12%)` fill, `font-weight: 800`, padding `0 var(--space-3)`, `min-height: 26px`.

**Usage.** Inside entry/result previews and dense rows where athletes are referenced. Not for free-text labels.

**Variants.** `male` (`--status-blue`), `female` (`--status-pink`), `count` (`--text-secondary`, e.g. `+3`).

**States.** Static; inherits the row hover. Add a focus ring only if made interactive.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do use the `count` variant to collapse overflow (`+3`).
- Don't encode any meaning other than sex in the colour.

### time-change-badge

**One-line definition.** A `time-change-badge` shows a rescheduled time as old → new with the delta.

**Anatomy.** Pill, 1px border + `14%` tint of the status colour, `font-weight: 800`, tabular numerals; struck-through old time in `--text-tertiary`, faded arrow.

**Usage.** On timetable rows whose start time has moved. Replaces low-contrast "[CHANGED] was…" text.

**Variants.** Default amber (`--status-amber`) for small moves; `big` red (`--status-red`) for large moves.

**States.** Static.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do show the computed delta (e.g. `−10 min`).
- Don't use the red `big` variant for routine ±5-minute shifts.

### status-legend

**One-line definition.** A `status-legend` is an inline key mapping a status colour to its meaning.

**Anatomy.** Flex row of `leg` items, each a 9px `dot` plus `--text-secondary` label; `gap: var(--space-4)`.

**Usage.** Above or beside any view that relies on status colour (e.g. clock colours). Pairs colour with words for accessibility (WCAG 1.4.1).

**Variants.** None.

**States.** Static.

**Kitchen-sink anchor.** [#feedback](./ui-kitchen-sink.html#feedback)

**Do / Don't.**

- Do show a legend wherever colour carries meaning.
- Don't rely on the colour alone without the legend.

### event-prep-tile

**One-line definition.** An `event-prep-tile` is a small stacked tile showing a preparation milestone time and its label.

**Anatomy.** Grid tile, `min-width: 74px`, bordered, `--bg-base` fill, bold tabular time over an uppercase `--text-tertiary` label.

**Usage.** In the event-preparation timeline (event, gathering, warm-up, arrive, bus). Not a general metric card.

**Variants.** `bus` (gold-tinted border/fill) for the transport leg.

**States.** Static.

**Kitchen-sink anchor.** [#containers](./ui-kitchen-sink.html#containers)

**Do / Don't.**

- Do keep times left-to-right in chronological order.
- Don't mix unrelated metrics into the row.

### disclosure-row

**One-line definition.** A `disclosure-row` is a `<details>` row that expands to reveal inline controls, with a rotating chevron.

**Anatomy.** Bordered `--radius-lg` container; `summary` grid `16px 1fr auto`; `.chev` rotates 90° on open; open state adds an inset burgundy left rule and a `--bg-base` body.

**Usage.** Schedule/list rows with secondary controls or detail. Replaces always-open inline forms.

**Variants.** None.

**States.** Hover; `[open]` (chevron rotated, left rule); focus ring on `summary`.

**Kitchen-sink anchor.** [#patterns](./ui-kitchen-sink.html#patterns)

**Do / Don't.**

- Do keep the most-used row expanded by default if helpful.
- Don't hide a primary action inside a collapsed row.

### tooltip

**One-line definition.** A `tooltip` reveals a short explanatory string on hover/focus of a dotted-underline term.

**Anatomy.** `.tip` with dotted bottom border; `::after` bubble on `#000`, 1px border, `max-width: 240px`, appears above the term.

**Usage.** Define jargon or clarify a control inline. Keep to one short sentence.

**Variants.** None.

**States.** Shown on `:hover` and `:focus-visible` (keyboard-accessible via `tabindex="0"`).

**Kitchen-sink anchor.** [#overlays](./ui-kitchen-sink.html#overlays)

**Do / Don't.**

- Do make the trigger keyboard-focusable.
- Don't put essential, action-critical information only in a tooltip.

### column-filter-menu

**One-line definition.** A `column-filter-menu` is a table-header popover used to sort one column and choose visible values for that column.

**Anatomy.** Opened from a funnel button in a table heading; contains a compact heading, close control, sort actions, optional value-search input, checkbox value list, apply action, and clear-filter action. The menu is fixed-position, clamps inside the viewport, and uses an internally scrolling checkbox list when needed.

**Usage.** Use on explicitly filterable mission-control table columns. Do not use for page-level filters such as roster state, timetable day, hotel, or transport type.

**Variants.** None for v1; columns supply their own display labels, missing-value labels, and sort/filter metadata.

**States.** Closed; open; active-filter trigger; draft checkbox changes before apply; disabled when a column has no filterable values.

**Kitchen-sink anchor.** [#tables](./ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do keep table row rendering page-owned while reusing this menu behavior.
- Don't duplicate the same column controls in a separate page filter panel.

### standard-table-controls

**One-line definition.** `standard-table-controls` are the reusable mission-control table controls for sorting, column filtering, active filter chips, and table reset.

**Anatomy.** A page-owned `table` inside `.table-wrap`; each controlled header uses `.table-header-controls` with a `.table-sort` label and optional `.table-filter-trigger`; active filters render as `.table-filter-chip` rows above the table; `Reset table` clears `tableSort`, `tableDirection`, and `tableFilter.*` route state.

**Usage.** Mission-control tables where operators need sortable or filterable columns. Page-level workflow controls such as roster state, timetable day, hotel, transport type, and date controls stay outside the table headers.

**Variants.** None for v1; pages supply their own columns, display labels, missing-value labels, row markup, and action cells.

**States.** Default; active sort; active column filter; hover/focus on sort/filter controls; disabled filter trigger when a column has no filterable values.

**Kitchen-sink anchor.** [#tables](./ui-kitchen-sink.html#tables)

**Do / Don't.**

- Do keep the row renderer local to the page while sharing header/menu primitives.
- Don't introduce a full generic table renderer until multiple screens have converged on the same row and group model.

### toast-region

**One-line definition.** A `toast-region` is the app-shell live region that shows transient command feedback after a successful or recoverable action.

**Anatomy.** Fixed bottom-right `.toast-region` with one or more `.toast` messages, `aria-live="polite"` and `aria-atomic="true"`; `.toast` uses `--bg-elevated`, `--shadow-soft`, `--radius-lg`, and status-colour text/border.

**Usage.** Short command feedback such as add, edit, remove, restore, save, or undo completion. Durable validation errors, duplicate warnings, missing data, and instructions must remain inline on the owning screen.

**Variants.** Default success (green); `warning` (amber) for recoverable stale/expired feedback; `error` (red) only when paired with an inline error; `info` (blue) for neutral command feedback.

**States.** Hidden; visible; auto-dismissed. Toasts may be URL-triggered, but cleanup must remove replay parameters after display.

**Kitchen-sink anchor.** [#overlays](./ui-kitchen-sink.html#overlays)

**Do / Don't.**

- Do make toast copy specific enough to confirm what changed.
- Don't use a toast as the only place an operator can read an error or recovery instruction.

### avatar

**One-line definition.** An `avatar` is a small round (or square) badge of an athlete's/person's initials.

**Anatomy.** 34px inline-flex circle, `--accent-muted` fill, gold border/text, `font-weight: 800`. Often paired with an `identity` block (name + muted sub-line).

**Usage.** Identity rows, banners, assignment lists. Initials only — no photo store.

**Variants.** `sq` (rounded-square); colour can be overridden per category (e.g. pink for female).

**States.** Static; inherits hover when inside an interactive row.

**Kitchen-sink anchor.** [#patterns](./ui-kitchen-sink.html#patterns)

**Do / Don't.**

- Do pair the avatar with a visible name (`identity`).
- Don't rely on the avatar alone to identify someone.

### breadcrumb

**One-line definition.** A `breadcrumb` is a single-line trail of ancestor links ending in the current page.

**Anatomy.** `.crumbs` flex row; links in `--text-secondary` (hover `--text-primary`); `.sep` slashes in `--text-tertiary`; `.here` current item bold in `--text-primary`.

**Usage.** Top of detail pages reached by drilling down (e.g. Roster / Team / Athlete).

**Variants.** None.

**States.** Link hover; current item is non-interactive.

**Kitchen-sink anchor.** [#navigation](./ui-kitchen-sink.html#navigation)

**Do / Don't.**

- Do make every segment except the last a link.
- Don't use breadcrumbs as the primary navigation.

### announcement-banner

**One-line definition.** An `announcement-banner` is a full-width notice with an icon, message, and optional action.

**Anatomy.** Flex row, gold-tinted fill with a 3px gold left border, `--radius-md`; leading badge/icon, body (`strong` + muted `p`), trailing action.

**Usage.** Page- or section-level informational notices. Not for inline form validation (use `message`).

**Variants.** Tone follows status tokens if needed (default gold/info).

**States.** Static; dismiss action optional.

**Kitchen-sink anchor.** [#feedback](./ui-kitchen-sink.html#feedback)

**Do / Don't.**

- Do keep it to one message and at most one action.
- Don't stack multiple banners; consolidate.

### tag-input

**One-line definition.** A `tag-input` is a field that holds removable chips plus a free-text entry.

**Anatomy.** Bordered `--bg-input` wrap; each `tag` is an `--accent-muted` chip with a `×` remove button; a borderless `input` flexes to fill.

**Usage.** Multi-value entry such as events or labels. Not for single selection (use `select`).

**Variants.** None.

**States.** Field focus; per-tag remove hover.

**Kitchen-sink anchor.** [#inputs](./ui-kitchen-sink.html#inputs)

**Do / Don't.**

- Do give every tag a labelled remove control.
- Don't use it where order is meaningful without drag support.

### stepper

**One-line definition.** A `stepper` shows progress through an ordered, multi-step flow.

**Anatomy.** Flex row of `step` items (numbered `num` badge + label) joined by thin `bar` connectors.

**Usage.** Import → review → publish style wizards. Not for free navigation between unrelated views (use tabs).

**Variants.** `done` (green check), `active` (burgundy/gold, bold), default (muted, upcoming).

**States.** done / active / upcoming.

**Kitchen-sink anchor.** [#workflow](./ui-kitchen-sink.html#workflow)

**Do / Don't.**

- Do mark exactly one step active.
- Don't use a stepper for more than ~5 steps.

### vertical-timeline

**One-line definition.** A `vertical-timeline` is a top-to-bottom list of events on a single connecting rail.

**Anatomy.** `vt-item` rows with a left border rail and an absolutely-positioned `vt-dot`; body has bold title over a muted `vt-time`.

**Usage.** Activity/audit history in a panel or drawer. For tabular history prefer a table.

**Variants.** Dot colour: gold (default), `green`, `amber`, `muted`.

**States.** Static; last item drops the rail.

**Kitchen-sink anchor.** [#workflow](./ui-kitchen-sink.html#workflow)

**Do / Don't.**

- Do order newest-first or oldest-first consistently.
- Don't use it for large datasets that need sorting/filtering.

### do-dont-guide

**One-line definition.** A `do-dont-guide` is a paired set of green "do" and red "don't" rule blocks.

**Anatomy.** Two-column `guides` grid; each `guide` has a bold marker (`✓`/`✕`) and a short rule; `do` is green-tinted, `dont` red-tinted.

**Usage.** Documenting correct vs incorrect usage of a component, in the glossary or in-app help.

**Variants.** `do`, `dont`.

**States.** Static.

**Kitchen-sink anchor.** [#patterns](./ui-kitchen-sink.html#patterns)

**Do / Don't.**

- Do pair each "don't" with the matching "do".
- Don't write rules longer than one line.

---

## Results & placings components (v2.1)

> Added when the Mission Control / Results retrofit introduced medal and placing surfaces. Anchored to the `#results` section of `ui-kitchen-sink.html`.

### medal-icon

**One-line definition.** A `medal-icon` is a small ribboned-disc icon whose colour encodes a podium place — gold (1st), silver (2nd), bronze (3rd).

**Anatomy.** Inline SVG (`.medal`) sized 14–22px; disc filled with `currentColor`, ribbons as a faint stroke, a base-colour star cut-out. Colour set by `.gold` (`--qatar-gold`), `.silver` (`--silver`), `.bronze` (`--bronze`).

**Usage.** Anywhere a 1st–3rd placement is shown: Final Placings place column, placing tiles, the legend, and "Nth final" result lines. Replaces the numerals 1/2/3. 4th–8th use a `place-badge` instead.

**Variants.** `gold`, `silver`, `bronze`.

**States.** Static. Always carries an `aria-label`/`<title>` so place is not conveyed by colour alone.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do give every medal an `aria-label` ("Gold — 1st").
- Don't use a medal for 4th–8th; those are diplomas, not medals.

### placing-tile

**One-line definition.** A `placing-tile` is one cell in the 1st–8th medal-count strip showing a place and the team's count at that place.

**Anatomy.** `.placings` is an 8-column grid (4 on narrow); each `.placing` is a bordered, centre-aligned tile with a `.lbl` (place / medal) over a large tabular `.val` count. `g1`/`g2`/`g3` tint the gold/silver/bronze tiles; 1st–3rd labels use a `medal-icon` via `.medal-lbl`.

**Usage.** Team performance summary on Mission Control / Results. Always the full 1st–8th set, even when a count is `-`.

**Variants.** `g1`, `g2`, `g3` (medal tints); plain for 4th–8th.

**States.** Static.

**Kitchen-sink anchor.** [#containers](./ui-kitchen-sink.html#containers)

**Do / Don't.**

- Do centre the tile contents.
- Don't drop empty places; show `-` so the podium shape stays readable.

### place-badge

**One-line definition.** A `place-badge` is a small pill showing a non-medal finishing place (4th–8th).

**Anatomy.** Inline-flex pill, `min-width: 42px`, 1px `--status-blue` border and text, centred. Used in the Final Placings place column for diploma places.

**Usage.** 4th–8th rows/tiles. 1st–3rd use a `medal-icon`, not a badge.

**Variants.** None (medals replace 1st–3rd).

**States.** Static.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do centre the badge in the place column (`.place-centered`).
- Don't number 1st–3rd here; use medals.

### place-num

**One-line definition.** A `place-num` is the plain finishing-place number (4th and below) shown in the daily Results table, paired with `medal-icon`s for 1st–3rd.

**Anatomy.** `.place-num` — bold, tabular-figures (`font-variant-numeric: tabular-nums`), `--text-secondary`. No border or fill; lighter than a `place-badge`.

**Usage.** The Place column of the daily Results table and its legend. Distinct from `place-badge`, which is the bordered pill used in the Mission Control Final Placings table; the daily Results table favours the plainer number.

**Variants.** None.

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do use a `medal-icon` for 1st–3rd and `place-num` for 4th+.
- Don't introduce a second numeric-place style; reuse `place-num` (Results) or `place-badge` (Final Placings).

### sex-indicator

**One-line definition.** A `sex-indicator` shows an athlete's sex as a gender symbol plus label — `♂ Male` (blue) / `♀ Female` (pink).

**Anatomy.** `.sex` inline-flex; `.sex.male` = `--status-blue`, `.sex.female` = `--status-pink`. Pairs with a sex-tinted `avatar` (`.avatar.male` blue, `.avatar.female` pink). When stacked under a name, indent to align with the name, not the avatar.

**Usage.** Athlete identity blocks and lists (e.g. By Athlete). Distinct from the World Athletics event category code (M/W) used in event names like "M 3000m".

**Variants.** `male`, `female`.

**States.** Static.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do tint the avatar to match the sex symbol (blue/pink).
- Don't confuse the athlete sex indicator with the event category code (M/W).

### type-chip

**One-line definition.** A `type-chip` is a compact pill marking a record's category (e.g. Athlete / Staff) in a dense table cell.

**Anatomy.** Small inline-flex pill, `font-size: 11px`, `font-weight: 800`, `padding: .1rem .55rem`; neutral by default, `.staff` is gold-tinted (`--qatar-gold`).

**Usage.** Category columns in list tables where a full `pill` would be too heavy. Not for state (use `status`) or athlete sex (use the sex indicator).

**Variants.** default (neutral), `staff` (gold-tinted).

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do keep it compact and reserve the gold tint for one meaningful category.
- Don't use it for status — that's what `status` chips are for.

### entry-status-chip

**One-line definition.** An `entry-status-chip` shows an athlete's competition-entry state — Confirmed (green) or Planned (neutral) — as a compact chip beside the name on the Results table.

**Anatomy.** `.entry-chip` — small inline-flex rounded pill, `font-size: 11px`, `font-weight: 800`, `padding: .05rem .5rem`; neutral border/`--bg-base` fill by default. `.entry-chip.confirmed` switches text to `--status-green` with a faint green border and fill. Colour is always paired with the word ("Confirmed entry" / "Planned entry"), never colour-only.

**Usage.** The Athlete / relay column of the daily Results table, replacing the older grey `result-participant-meta` sub-text. Reflects the competition entry's status, not a result status (use `status` chips for results).

**Variants.** default (neutral = Planned), `confirmed` (green).

**States.** Static; inherits row hover.

**Kitchen-sink anchor.** [#buttons](./ui-kitchen-sink.html#buttons)

**Do / Don't.**

- Do pair the colour with the word so confirmed/planned is never colour-only.
- Don't use it for result state (completed / DNS / DNF) — that's a `status` chip.

> Note: the `sex-indicator` also has a **bare-symbol variant** — just ♂/♀ (sex-tinted, with a `title`) — for narrow M/F table columns, as used on the Roster.

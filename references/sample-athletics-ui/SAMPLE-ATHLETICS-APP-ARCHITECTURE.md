# Sample Athletics-Compatible App Architecture

Status: Source of truth
Last verified: 2026-05-23
Supersedes: None
Superseded by: None
Scope: Architecture compatibility contract for agents building apps that should feel, behave, and integrate like Sample Athletics

This document describes the architecture choices that make the sample athletics operations app compatible with itself across screens, routes, data lanes, local tools, and future sibling apps. Use it as the contract for creating another app that should be directly compatible with Sample Athletics conventions.

"Compatible" means:

- The app looks and behaves like Sample Athletics without inventing a separate design language.
- User-facing dates, country codes, status labels, and workflow terminology follow the same rules.
- API routes return the same success/error shapes and parse list/id inputs the same way.
- Persistence and local data-lane behavior are predictable beside Sample Athletics.
- Future agents can inspect, test, and extend the app using the same mental model.

## Compatibility Tiers

| Tier | Requirement | Anchor |
| --- | --- | --- |
| Visual compatibility | Use the same design tokens, spacing, shell density, controls, and status colors. | `src/app/globals.css`, `src/components/ui/*`, `ui-kitchen-sink.html` |
| Interaction compatibility | Use the same app shell, navigation, tabs, modals, command palette, form behavior, and keyboard posture. | `src/components/layout/*`, `src/lib/keyboard.ts` |
| API compatibility | Use route adapters, shared envelopes, shared list/id parsers, and client error readers. | `src/lib/api/*` |
| Data compatibility | Use canonical stored formats, explicit local data lanes, and backup-before-production-data changes. | `src/lib/db.ts`, `src/lib/data-lane-config.ts`, `src/lib/data-lane.ts` |
| Domain compatibility | Keep domain rules in shared `src/lib` modules and keep routes/screens thin where practical. | `src/lib/athletes/*`, `src/lib/competitions/*`, `src/lib/camps/*`, `src/lib/athletics-results/*` |
| Agent compatibility | Follow the docs map, status labels, verification expectations, and source-of-truth folder split. | `docs/README.md` |

## Stack Choices

Sample Athletics is a local-first Next.js app:

- Next.js App Router under `src/app`.
- React client components for interactive screens and shared UI.
- TypeScript with strict checking and the `@/*` path alias to `src/*`.
- Tailwind v4 tokens declared in `src/app/globals.css`.
- SQLite through `better-sqlite3` with repo-local data files.
- Jest for unit/integration tests and Playwright for e2e/browser checks.
- Lucide icons for UI iconography.
- Framer Motion only where animation behavior is already part of a shared component, such as `Modal`.

Do not introduce a parallel stack for compatible apps unless the app is intentionally outside the Sample Athletics compatibility surface.

## Top-Level Shape

```text
src/app/
  layout.tsx                 Root shell and global font wiring
  globals.css                Theme tokens and base body styling
  page.tsx                   Dashboard route
  <feature>/page.tsx         User-facing pages
  api/<feature>/route.ts     API route adapters

src/components/
  layout/                    AppShell, Sidebar, TopBar, CommandPalette
  ui/                        Shared primitives
  <feature>/                 Screen-level composition

src/lib/
  api/                       Shared API response, param, list, and client-error helpers
  db.ts                      Public SQLite entry point
  db/                        DB initialization, schema, migrations, seeds, inspection
  <feature>.ts               Domain facade or feature entry point
  <feature>/                 Larger domain implementations, policies, read models, workflows

docs/
  product-specs/             Final behavior and acceptance criteria
  design-docs/               Final UI and workflow direction
  references/                Durable architecture and decision context
```

The preferred shape is:

```text
Page or client component
  -> shared UI primitives
  -> screen-specific composition or workflow helper
  -> fetch('/api/...')
  -> API route adapter
  -> domain module in src/lib
  -> db/file/config adapter
```

## Visual Architecture

Use `ui-kitchen-sink.html` as the visual glossary and `src/app/globals.css` as the token source.

Core tokens:

| Role | Token | Value |
| --- | --- | --- |
| Base background | `--color-bg-base` | `#0a0a0b` |
| Surface | `--color-bg-surface` | `#131316` |
| Elevated surface | `--color-bg-elevated` | `#1c1c21` |
| Input background | `--color-bg-input` | `#18181c` |
| Subtle border | `--color-border-subtle` | `#232329` |
| Focus border | `--color-border-focus` | `#8d1b3d` |
| Primary text | `--color-text-primary` | `#edefef` |
| Secondary text | `--color-text-secondary` | `#8b8b8e` |
| Tertiary text | `--color-text-tertiary` | `#5c5c63` |
| brand burgundy | `--color-accent-primary` | `#8d1b3d` |
| brand gold | `--color-qatar-gold` | `#c4922a` |
| Status green | `--color-status-green` | `#45a557` |
| Status amber | `--color-status-amber` | `#e5a31d` |
| Status red | `--color-status-red` | `#e5484d` |
| Status blue | `--color-status-blue` | `#3b82f6` |

UI rules:

- Use a compact dark operational interface, not a marketing landing-page style.
- Keep cards, panels, inputs, and buttons at small radii unless matching an existing Sample Athletics pattern.
- Use `qatar-gold` for page/screen headings and key identity labels.
- Use `accent-primary` for primary actions, active nav rails, active tabs, and selected states.
- Use status colors only for state, not decoration.
- Keep page sections unframed unless they are actual cards, modals, repeated items, or tool surfaces.
- Use Lucide icons when an icon is needed.
- Prefer dense, scan-friendly layouts over decorative compositions.

Shared UI primitives:

| Component | Purpose | Compatibility notes |
| --- | --- | --- |
| `Button` | Primary, secondary, ghost, danger buttons. | Use `buttonClass` and `linkButtonClass` for matching links/actions. |
| `StatusBadge` | Valid, expiring, expired, info labels. | Use for compact state, not explanatory messages. |
| `MetricCard` | Dashboard and operational counts. | Document ID tones have special color treatments. |
| `DataTable` | Bordered table with sortable headers and hover rows. | Keep table sorting predictable and row click behavior explicit. |
| `DateField` | Text input plus calendar picker. | User-facing date input/display must be `DD-MM-YYYY`. |
| `CountrySelect` | Searchable country/nationality picker. | Display World Athletics codes while preserving ISO reference data. |
| `Modal` | Focus-aware modal shell. | Close on overlay click/Escape; keep title/subtitle/header structure. |
| `Tabs` | Horizontal stage/view navigation. | Current component uses buttons, not ARIA `role=tab`. |
| `FormField` | Label, helper, and error wrapper. | Use for compact forms; errors are below helpers. |
| `InlineEdit` | Small inline editing affordance. | Prefer dedicated edit routes for larger mutations. |

## Shell And Navigation

The global shell lives in `AppShell`.

- `src/app/layout.tsx` loads Inter and JetBrains Mono, imports global tokens, and wraps pages in `AppShell`.
- `AppShell` handles sidebar collapse, command palette state, and keyboard shortcuts.
- `Sidebar` owns primary navigation sections: Planning, People, Training, Competitions, Operations.
- `TopBar` owns the Sample Athletics version label, data-lane badge, and command palette trigger.
- `CommandPalette` is a navigation overlay, not a data editor.
- Settings routes use `SettingsShell` instead of the normal sidebar.

Keyboard conventions:

- `Cmd/Ctrl + K`: command palette.
- `[`: collapse or expand the sidebar.
- `g` followed by a route key from `src/lib/keyboard.ts`: quick navigation outside inputs.

Compatible apps should either reuse this shell or intentionally document why a surface is not part of the Sample Athletics app shell.

## API Architecture

Route files should be thin adapters. Many route files now re-export route handlers from `src/lib`:

```ts
export { createAthleteRoute as POST, listAthletesRoute as GET } from '@/lib/athletes/api-routes';
```

Use this pattern for compatible apps:

```text
src/app/api/<resource>/route.ts
  -> parse request and route params
  -> call src/lib/<resource> function
  -> return ok(...) or shared error envelope
```

Shared API rules:

- Return success payloads through `ok(payload, status?)` from `src/lib/api/responses.ts` when practical.
- Return errors as:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human readable message",
    "details": {}
  }
}
```

- Use `validationError`, `notFound`, `conflict`, `internalError`, `statusError`, or `handleZodError` rather than ad hoc error JSON.
- Parse numeric route ids with `parseIdParam` or `parseOptionalIdParam`.
- Parse list routes with `parseListQuery`: `page`, `limit`, `sort`, and `order`.
- Client surfaces should read failures with `getApiErrorMessage(payload, fallback)` so legacy string errors and shared envelopes both work.

Do not render `payload.error` directly in React. It may be an object.

## Date Contract

Dates have two layers:

- User display/input: `DD-MM-YYYY`.
- Storage/API canonical value: `YYYY-MM-DD` where a machine format is needed.

Use `src/lib/dates.ts` for all date behavior:

- `formatDateForDisplay`
- `formatDateForInput`
- `normalizeStoredDate`
- `coerceUserDateInput`
- `parseStoredDate`
- `todayStoredDate`
- `normalizedSqlDateExpr`

Use `DateField` for user-entered dates. It accepts existing stored dates but commits normalized stored values and shows the `Date must use DD-MM-YYYY` error when a user draft is invalid.

Do not add one-off date parsers inside routes or screens.

## Country And Nationality Contract

Country/nationality display is centralized in `src/lib/countries.ts`.

Compatibility rules:

- User-facing athletics contexts should display World Athletics codes.
- ISO alpha-3 remains available for reference/storage compatibility.
- UI pickers should use `CountrySelect`.
- Import/export/validation paths should call the shared country helpers.
- Do not create one-off country-code maps in feature components or routes.

Important helpers:

- `resolveCountryInput`
- `normalizeCountryInput`
- `formatNationality`
- `formatCountryReference`
- `searchCountries`

## Data And Persistence Architecture

Sample Athletics is local-first and data-lane aware.

`src/lib/db.ts` is the public DB entry point:

- Chooses `process.env.SAMPLE_ATHLETICS_DB_PATH` or defaults to `data/ams.dev.db`.
- Creates the data directory if needed.
- Lazily initializes schema/seeds through a proxy around `better-sqlite3`.
- Runs runtime schema migrations before DB operations.

`src/lib/db/*` owns initialization details:

- `schema.ts`: base schema.
- `migrations.ts`: migration runners.
- `seeds.ts`: seed data.
- `inspect.ts`: table/column inspection.
- `initialize.ts`: initialization orchestration.

Compatible data-lane behavior:

- `development`: default local dev lane, no auth required, default port `3001`.
- `local-production`: local production lane, auth required, default port `3002`.
- Config lives in `data/lane-config.local.json` via `src/lib/data-lane-config.ts`.
- Runtime env values can override DB path, upload root, port, lane, and auth.

Before modifying local Sample Athletics databases, create a timestamped backup copy first. Never destructively overwrite production-like local data without explicit user agreement.

## File And Upload Boundaries

Use shared file helpers instead of writing direct path handling in screens/routes:

- Document file safety lives in `src/lib/document-files.ts`.
- Photo file safety lives in `src/lib/photo-files.ts`.
- Data-lane upload roots come from active lane config.

Compatible apps should keep runtime uploads under the lane's configured upload root and should not assume a hardcoded `public/` write target.

## Domain Module Pattern

The repo is moving toward behavior-preserving domain modules:

- API routes are adapters.
- Domain modules own validation, read models, commands, policies, and transactions.
- Large legacy facades can remain as compatibility facades while internals move into folders.
- UI screens can have feature-specific workflow helpers when state logic grows.

Examples:

| Area | Facade or entry point | Internal modules |
| --- | --- | --- |
| Athletes | `src/lib/athletes/api-routes.ts`, `src/lib/athletes/write-core.ts` | `write-*`, `*-routes`, `stats`, `photo`, `export` |
| Athletics results | `src/lib/athletics-results.ts` | `src/lib/athletics-results/*` |
| Competitions | `src/lib/competitions.ts` | `src/lib/competitions/*` |
| Championships | `src/lib/championships.ts` | `src/lib/championships/*` |
| Camps | `src/lib/camps.ts` | `src/lib/camps/*` |
| Documents | `src/lib/documents/*` | lifecycle, list, queue, owners, archive, scans |
| Calendar | `src/lib/calendar-events.ts` | `src/lib/calendar-events/*` |
| Event Catalogue | `src/lib/event-catalogue.ts` | `src/lib/event-catalogue/*` |

When building a compatible app, prefer the same sequence:

1. Keep the route payload and UI contract stable.
2. Add or reuse a domain entry point under `src/lib`.
3. Move implementation detail behind that entry point.
4. Update adapters/screens to call the entry point.
5. Add regression tests around the public behavior, not private helper shape.

## Screen And Workflow Boundaries

Sample Athletics distinguishes business workflows that may look related but have different ownership:

- Hosted Competitions: internal competition setup, assignments, readiness, and Athletics.app export.
- Sample Team/Championships: championship planning, entries, exclusions, and travel-plan creation.
- Camps: camp/travel execution, checkout, return, due departures, and closeout.
- Calendar: aggregation/read model across source modules; source records remain edited in their owner module.
- Settings: app-level operational configuration, not normal feature data entry.

Do not merge these workflows into one abstraction just because they share athletes, dates, or events. Share helpers for common mechanics, but preserve source ownership.

## Event Catalogue Contract

The Event Catalogue is the settings-backed source for athletics event options.

Compatibility rules:

- Event selection should prefer catalogue-backed options over free text.
- `event_group` is the user/admin category.
- `discipline_type` is derived internally from event group, relay flag, and base event.
- Athlete-facing selection labels can differ from raw catalogue display names where needed.
- Result display wording should come from shared formatting helpers, not repeated component strings.

## Testing And Verification

Use the repo's existing verification layers:

- `npm run lint` for linting.
- `npx tsc --noEmit` or `npm run build` for type/build confidence.
- `npm test -- --runInBand` for broad Jest runs when DB state is involved.
- `npm test -- --runTestsByPath <paths> --runInBand` for targeted slices.
- `npm run test:e2e` for Playwright e2e where a local browser flow is required.

Test data safety:

- Jest sets a per-run temporary `SAMPLE_ATHLETICS_DB_PATH` in `jest.setup.ts`.
- Do not point tests at `data/ams.dev.db` or `data/ams.prod.db` unless a test explicitly owns that scenario and backs up first.
- Browser/manual UAT is useful for visual or workflow changes, but do not claim it ran unless it actually did.

## Documentation Contract

Future agents should use `docs/README.md` first, then the smallest relevant source file.

Use these status labels in durable docs:

```md
Status: Source of truth | Active draft | Superseded | Historical reference
Last verified: YYYY-MM-DD
Supersedes: <older docs or None>
Superseded by: <newer doc or None>
Scope: <what this file governs>
```

Folder choices:

- `docs/product-specs/`: final behavior, acceptance criteria, and data/API scope.
- `docs/design-docs/`: final UI and workflow direction.
- `docs/exec-plans/active/`: pending implementation handoffs.
- `docs/exec-plans/completed/`: shipped or superseded implementation handoffs.
- `docs/references/`: durable architecture, technical, and background references.
- `docs/references/decision-records/`: rationale and rejected alternatives.
- `docs/brainstorming/`: active exploration only.

## Build Checklist For A Compatible App

Use this checklist when creating a new sample-athletics-compatible app or major app surface:

- Reuse the Sample Athletics shell pattern or clearly mark the app as shell-external.
- Import or mirror `globals.css` tokens before creating new colors.
- Build a local `ui-kitchen-sink.html` or link to the Sample Athletics one for visual review.
- Use shared button, badge, table, modal, tab, date, country, and form patterns.
- Preserve `DD-MM-YYYY` for all user-facing date display/input.
- Preserve the shared error envelope and client error reader.
- Keep route adapters thin and put behavior in `src/lib`.
- Use data lanes for local DB/upload paths.
- Back up local production-like data before write tests or manual mutation.
- Add tests at the public route/domain/screen contract level.
- Add a status-labeled doc when future agents need the decision.

## Do Not Reintroduce

- A second design system with different colors, radii, typography, or card density.
- Ad hoc date parsing or user-facing ISO date strings.
- One-off country/World Athletics code maps.
- Route handlers that mix request parsing, SQL, business policy, and response formatting in one large file.
- React clients that render shared API error objects directly.
- Database writes to local production data without a backup.
- Calendar edits that mutate source records outside their owner module.
- Docs without status when they look like source-of-truth guidance.

## Minimum Compatible App Skeleton

```text
src/app/layout.tsx
src/app/globals.css
src/components/layout/AppShell.tsx
src/components/layout/Sidebar.tsx
src/components/layout/TopBar.tsx
src/components/layout/CommandPalette.tsx
src/components/ui/Button.tsx
src/components/ui/DateField.tsx
src/components/ui/Modal.tsx
src/components/ui/StatusBadge.tsx
src/components/ui/Tabs.tsx
src/lib/api/responses.ts
src/lib/api/route-params.ts
src/lib/api/list-query.ts
src/lib/api/client-errors.ts
src/lib/dates.ts
src/lib/countries.ts
src/lib/data-lane-config.ts
src/lib/db.ts
ui-kitchen-sink.html
docs/README.md
```

Add only the domain modules required by the new app. Compatibility comes from preserving the shared contracts, not from copying every Sample Athletics feature.

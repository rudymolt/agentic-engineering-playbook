# Agent Playbook

> **Drop this file into the root of any new project.** An AI agent reading it should immediately understand how to collaborate effectively, what architectural patterns to reach for, what mistakes to avoid, and how to ship work in coherent increments.
>
> This playbook was written from lessons learned building the **Sample Fitness Programming App** — a TypeScript/React/Express app on top of a Python content pipeline. The principles are language-agnostic. Stack-specific examples appear as **case studies** and can be adapted to whatever stack the new project uses.

---

## How to use this playbook

1. **First conversation in a new project** — read this file top to bottom. It is the project's "constitution" until a more specific `CLAUDE.md` is written.
2. **Each new session** — re-read the section that matches the work you're about to do. Section 4 before a new feature, Section 6 before any file edit, Section 8 before a commit.
3. **When in doubt** — Section 11 ("Common pitfalls") is a fast sanity check before doing something you're not sure about.
4. **Case studies are evidence, not requirements.** The Sample Fitness examples show one way the principle plays out. Adapt the pattern to the project at hand.

### How to extend this playbook
- Add new sections at the end (Section 13, 14...) so existing references don't break.
- Within a section, append sub-sections rather than rewriting.
- Promote anything in "Common pitfalls" to a full section once it has a real fix to teach.
- The "Quick reference checklists" appendix is the single place to add new one-line rules — keep them terse.

---

## Table of contents

1. [The collaboration contract](#1-the-collaboration-contract)
2. [Project kickoff](#2-project-kickoff)
3. [Architecture decisions that compound](#3-architecture-decisions-that-compound)
4. [Slice-based delivery](#4-slice-based-delivery)
5. [Type discipline](#5-type-discipline)
6. [Surgical edits over rewrites](#6-surgical-edits-over-rewrites)
7. [State and data flow](#7-state-and-data-flow)
8. [Verification](#8-verification)
9. [Memory and skills](#9-memory-and-skills)
10. [Git workflow](#10-git-workflow)
11. [Common pitfalls](#11-common-pitfalls)
12. [Quick reference checklists](#12-quick-reference-checklists)

---

## 1. The collaboration contract

The first thing to understand: you are working *with* a human, not *for* them. The goal is shared progress on something they care about, not the appearance of activity.

### 1.1 Ask before you act

Almost every non-trivial request is underspecified. The cost of a 30-second clarifying question is always less than the cost of building the wrong thing. Default to asking when:

- The user says "create X" without specifying audience, format, or depth
- The user says "find / search / look at" without specifying scope
- The user says "fix / improve" without specifying the symptom or the bar
- Multiple reasonable interpretations exist

Use a structured multi-choice question. Cap it at 4 options. If the user has already clarified earlier in the conversation, don't re-ask.

**Example.** *"Build me a dashboard"* should not become a half-built dashboard. It should become four questions: who's the audience, which metrics, how often does it refresh, is this disposable or persistent.

### 1.2 Don't invent domain rules

If you don't know something domain-specific, say so. Mark it as an open question. Never make up a rule that sounds plausible.

> **Sample Fitness case.** `AGENTS.md` enshrines this as: *"Do not invent fitness rules. If something is unclear, mark it as an open question for the product owner."* The cost of inventing a fitness rule and writing it into a training programme is much higher than the cost of pausing to ask.

### 1.3 Match verification depth to the change

Don't run the full test suite for a typo fix. Don't ship a parser rewrite with only a type-check. The cost of verification should scale with the cost of being wrong. See §8 for the verification ladder.

### 1.4 Push back constructively

If the user proposes something that conflicts with their stated goals or with the project's architecture, say so. Briefly. Offer the alternative. Then defer to their judgment.

### 1.5 Don't add what they didn't ask for

Resist the urge to "improve" adjacent things. A request to fix a parser bug is not a license to refactor the parser. If you spot something worth changing, mention it; don't do it.

### 1.6 Use their vocabulary

Read the project's `CONTEXT.md` (or equivalent). Use the names they use for the nouns of the domain. Inventing your own terminology is a tax on every future conversation.

---

## 2. Project kickoff

The first 30 minutes in a fresh project shape everything that follows. Spend them on context, not code.

### 2.1 The three onboarding files

Almost every well-run project benefits from three small files at the root:

| File | Purpose | Audience | Updated when |
|---|---|---|---|
| `CLAUDE.md` | Governance: stack, commands, architecture, constraints | Any agent in the repo | Architecture or commands change |
| `AGENTS.md` | Quick-start: which files to read for which task | Any agent before starting work | Folder structure changes |
| `CONTEXT.md` | Domain vocabulary so agents don't re-derive it | Any agent doing domain work | New domain term enters the project |

If these don't exist yet, your first task in a new project is to create stubs.

> **Sample Fitness case — three-tier onboarding.** `CLAUDE.md` lists the stack (Vite + React + TS + Express), the dev commands, the data flow, and the constraints (`alpha-build/` is frozen, `src/` Python pipeline is frozen, markdown files are patched surgically). `AGENTS.md` says: *"For most tasks, read only the files needed for the requested scope"* and lists which files to read per task type. `CONTEXT.md` enumerates the project's nouns (CONVOY, FORCE, SET, ENDURE — the class formats) so a new agent doesn't waste tokens re-deriving them.

**What makes them effective:** they are layered by urgency. CLAUDE.md is the contract. AGENTS.md is the index. CONTEXT.md is the dictionary. Together they let an agent answer "what should I read first?" in under a minute.

### 2.2 The kickoff sequence

In order, on entering a fresh project:

1. **Read `CLAUDE.md`** if it exists. If not, create a stub with: project name, one-paragraph purpose, stack, dev commands, list of constraints.
2. **Read `AGENTS.md`** if it exists. If not, note it as a follow-up.
3. **Read `CONTEXT.md`** for any domain term you'll need.
4. **Read `MEMORY.md`** (your persistent memory index) for prior decisions.
5. **`ls` the top-level folders.** Identify entry points. Look for `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, etc., to confirm the stack.
6. **Skim the build plan** (often in CLAUDE.md) to know which slice is next.
7. **Don't read every file.** Read only what the requested scope needs. The temptation to "understand everything first" is the enemy of momentum.

### 2.3 The "do not modify" tiers

Every mature project has tiers of editability. Make these explicit early.

| Tier | Examples | Rule |
|---|---|---|
| **Frozen reference** | Snapshot of last known-good build | Never edit. Used for regression comparison. |
| **Generated output** | Files produced by a build pipeline | Patch surgically only; never rewrite wholesale. |
| **Source of truth** | Hand-edited config, content, schemas | Free editing, but with care — these drive generation. |
| **Active code** | The product you're building | Free editing target. |

> **Sample Fitness case — three frozen tiers, one active tier.** The project's `CLAUDE.md` declares:
> - `alpha-build/` is a frozen reference snapshot — never edit it.
> - `src/` Python pipeline — never modify.
> - Markdown files in `output/` — patch surgically only, never rewrite wholesale.
> - `programming-ui/` is the active development target.
>
> Each tier has explicit rules. An agent reading this knows immediately where it's safe to act and where it must tread carefully.

---

## 3. Architecture decisions that compound

A small number of decisions, made early, shape everything else. Get these right and the project ages well. Get them wrong and you fight the architecture forever.

### 3.1 One source of truth

For every piece of data the system handles, ask: **what is the canonical representation?** Then make sure nothing else holds a copy. Everything that needs the data either reads it or derives it.

**Benefits:**
- Forces surgical edits (§6) — you can't safely "rewrite" the source of truth.
- Eliminates sync bugs — there is no other place that can drift.
- One place to debug.

> **Sample Fitness case — markdown is the database.** The training programmes live as `.md` files in `output/`. There is no SQLite, no Postgres, no JSON sidecar. The Express server parses these files on read and patches them on write. The UI is a window onto the markdown. When the user wants to know what's in a programme, they can open the file directly — there's no risk of UI-vs-disk divergence because the markdown *is* the state.

### 3.2 Split parsing from serializing

If your system reads and writes a structured format (markdown, YAML, CSV, AST), keep the read path and the write path in separate modules. The reader can be lenient; the writer must be precise. They have different invariants and shouldn't share code beyond shared types.

> **Sample Fitness case.** `server/parser/parseClassProgramme.ts` reads markdown into a typed `ClassProgramme`. `server/parser/serializeClassProgramme.ts` takes an edit and produces a *minimal patch* to the original file. The parser dispatches across 5 schema strategies (CONVOY/SET, ENDURE, fixed-KCL SET, ARENA, NEXUS legacy). The serializer doesn't care which strategy parsed the file — it just patches the affected cell.

### 3.3 Content-based dispatch, not name-based

When you have multiple variants of a structure (file formats, message types, document layouts), dispatch on the *content* of the structure, not on a name or a tag.

**Why:** new variants can be added without touching the dispatcher. Renames don't break routing. A file's name lies more often than its contents do.

> **Sample Fitness case.** The parser detects which strategy to use by looking at the markdown:
>
> ```typescript
> if (hasElementTableSchema(content)) {
>   units = parseArena(text)
> } else if (hasEndureSchema(content)) {
>   units = reshapeEndureUnits(parseRowOriented(...))
> } else {
>   units = parseColumnOriented(...)
> }
> ```
>
> A new schema file added to `output/` auto-routes correctly. No registry to update, no class-name match to maintain.

### 3.4 Types as the source of domain invariants

If the domain says "weeks are 1, 2, 3, or 4," the type should say `1 | 2 | 3 | 4`, not `number`. Push as much validation as possible up to the type level. The runtime should never need to ask "is this a valid week?"

> **Sample Fitness case.**
>
> ```typescript
> export type WeekNum = 1 | 2 | 3 | 4
>
> export interface TargetValues {
>   reps:  string
>   load?: string
> }
> ```
>
> `WeekNum` is enforced at parse time. Anywhere downstream that takes a `WeekNum`, the type system has already guaranteed it's one of four values. No runtime check needed.

### 3.5 Custom exceptions for control flow at boundaries

Don't return string error codes from your business layer. Throw typed exceptions. Translate them to HTTP status codes (or whatever the boundary is) at the very edge.

> **Sample Fitness case.** The repository layer throws `ProgrammeNotFound`, `BlockNotFound`, `PatchHadNoEffect`. The route catches them and maps:
>
> ```typescript
> try {
>   const { undo } = repo.applySwap({ blockId, classSlug }, swap)
>   res.json({ ok: true, undo })
> } catch (err) {
>   if (err instanceof ProgrammeNotFound) res.status(404).json(...)
>   else if (err instanceof PatchHadNoEffect) res.status(422).json(...)
>   else throw err
> }
> ```
>
> Each exception carries semantic meaning. The route is a thin translator. The business layer doesn't know HTTP exists.

### 3.6 Environment overrides for testability

Anything that points at the filesystem, a database, or an external service should be overrideable via environment variable. Tests need their own sandbox; production needs the default; both should run the same code.

> **Sample Fitness case.**
>
> ```typescript
> export const OUTPUT_DIR = process.env.SAMPLE_FITNESS_OUTPUT_DIR
>   ? resolve(process.env.SAMPLE_FITNESS_OUTPUT_DIR)
>   : resolve(__dirname, '../../output')
> ```
>
> E2E tests point `SAMPLE_FITNESS_OUTPUT_DIR` at a fixture directory; production uses the default.

### 3.7 Broadcast, don't push

If multiple clients need to know about changes to shared state, watch the source of truth and broadcast a "something changed" event. Don't try to track which client cares about which slice of state — let them filter.

> **Sample Fitness case.** A chokidar watcher on `output/` broadcasts `{ type: 'changed', blockId, path }` over WebSocket. Each connected UI decides whether its current block matches and reloads if so. The server doesn't track subscriptions.

---

## 4. Slice-based delivery

A **slice** is a vertical cut through the system: types + business logic + UI + tests + docs, all in one coherent unit, committed together. Slices are the unit of progress. Not tickets, not files, not lines — slices.

### 4.1 Why slices

- Each slice is independently shippable. The project always works after a slice lands.
- A slice forces you to think end-to-end — you can't slide bugs across layer boundaries.
- Numbered slices give the user a visible rhythm and let them say "do slice 7 next" without ambiguity.

### 4.2 Slice anatomy

A typical slice:

1. **One-line goal.** Write it down. "Slice 7: read-only BLOCK tab showing KCL list and plate-loading budget."
2. **Types first.** What changes in the domain? Add or modify the canonical types.
3. **Business logic.** Parser, serializer, repository, service — whatever owns the new behaviour.
4. **API surface.** New routes or new fields on existing routes.
5. **State.** Store actions, payload types.
6. **UI.** Views, components.
7. **Tests.** Unit tests for the new business logic and store actions; smoke test still passes.
8. **Docs.** Update CLAUDE.md to mark the slice done, mention any new constraints.

You don't have to write them in that order, but every layer above should appear in the slice's commit, or you've split a slice in half.

### 4.3 Slice sizing

A good slice is one feature. A bad slice is "everything I felt like doing today."

> **Sample Fitness case.** Slice 6 was *"ENDURE/ARENA parser + serializeClassProgramme, accessory swap model, ArenaNotesEditor, ArenaRepsEditor, candidate pool expansions"* — 4,865 lines across 26 files. Big, but coherent: a complete new class format end-to-end. Slice 10 was *"launcher, Playwright smoke, verification checklist"* — 878 lines. Smaller, but coherent: shipping the v1.2 build. Both are valid slice shapes. What's invalid is "fix three unrelated bugs and add two unrelated features in one commit."

### 4.4 Architectural review cadence

Every ~3 slices, step back. Look at what's grown. Look for duplication, drift, layering violations. Run a structured review (a skill or checklist). Refactor before the technical debt compounds.

> **Sample Fitness case.** `CLAUDE.md` says: *"Run `/improve-codebase-architecture` every ~3 slices."* The cadence is explicit so it's not forgotten.

### 4.5 The Build Plan section

Keep a live "Build Plan" in `CLAUDE.md` listing done and remaining slices. The agent reads this on entry to know what's next.

> **Sample Fitness case** from `CLAUDE.md`:
>
> > Slices 1–6 complete. Remaining:
> > - **Slice 7** — BLOCK tab: read-only block metadata (KCLs, plate-loading budget, selection rationale)
> > - **Slice 8** — Reuse warnings (within-week and consecutive-day breach detection)
> > - **Slice 9** — File watcher (chokidar + WebSocket live refresh)
> > - **Slice 10** — One-click launcher + keyboard shortcuts + end-to-end verification

---

## 5. Type discipline

Strong types are the cheapest form of testing. Every rule in this section pays for itself many times over.

### 5.1 Literal unions over loose primitives

Anywhere a value is constrained, narrow the type. `'pending' | 'active' | 'done'` beats `string`. `1 | 2 | 3 | 4` beats `number`. The compiler catches typos and exhaustive `switch`es become free.

### 5.2 Discriminated unions for variants

Every variant carries a `kind` (or `type`, or `tag`) field. The compiler narrows automatically inside an `if (x.kind === 'foo')` block. Every consumer of the union must handle every variant.

> **Sample Fitness case.** The drawer's staging buffer holds a heterogeneous list of pending edits:
>
> ```typescript
> export type StagedChange =
>   | { kind: 'swap';        unitNum: number; accessoryIdx?: number; oldName: string; newName: string }
>   | { kind: 'target';      unitNum: number; reps: string; load?: string }
>   | { kind: 'arena-reps';  unitNum: number; accessoryIdx?: number; exerciseName: string; reps: string }
>   | { kind: 'arena-notes'; unitNum: number; accessoryIdx?: number; exerciseName: string; notes: string }
> ```
>
> Adding a fifth kind of change is a compile-time error in every `switch` that handles `StagedChange`. The compiler tells you what to update.

### 5.3 Single re-export, never re-declare

When the same type is needed in multiple modules (e.g. server and client), pick one as the canonical source and re-export from the other. Never copy the definition.

> **Sample Fitness case.** `src/domain/types.ts` is *only* re-exports:
>
> ```typescript
> export type {
>   WeekNum,
>   TargetValues,
>   UnitWeekSummary,
>   ProgrammeUnit,
>   ClassProgramme,
>   Block,
>   BlockMeta,
> } from '../../server/types.ts'
> ```
>
> The server is the source of truth for domain types; the client is downstream. There is no possible drift.

### 5.4 Type-check after every change

`tsc --noEmit` (or your language's equivalent) is the cheapest test you'll ever run. It catches roughly 80% of mistakes before any runtime executes. Run it before claiming a change is complete. Run it before every commit. Make it part of your reflex.

### 5.5 Outcome types over boolean returns

When an operation has multiple meaningful outcomes (not just success/failure), encode them in the return type.

> **Sample Fitness case.** Each patcher in the serializer returns:
>
> ```typescript
> type PatchOutcome =
>   | { status: 'patched';    lines: string[]; lineIdx: number }
>   | { status: 'idempotent'; lines: string[]; lineIdx: number }
>   | { status: 'missing';    lines: string[] }
> ```
>
> The caller can distinguish "I changed it" from "it was already correct" from "I couldn't find what I was supposed to patch." A boolean would have collapsed those three into one and made bugs much harder to spot.

### 5.6 Branded opaque types for IDs

When a value is "a string, but a *specific kind* of string" (an ID, a slug, a key), give it a branded type so it can't be confused with a plain string or with another kind of ID.

```typescript
type BlockId = string & { readonly __brand: 'BlockId' }
```

This costs nothing at runtime and prevents accidentally passing a `UserId` where a `BlockId` is expected.

---

## 6. Surgical edits over rewrites

The single most important rule in this playbook. If you remember nothing else, remember this:

> **Never rewrite a file when you can patch it. Never patch what you can leave alone.**

### 6.1 Why this matters

A rewrite touches every line. Every line touched is a chance to:
- Change formatting in ways the user didn't ask for.
- Drop a comment or a piece of metadata the user cared about.
- Silently introduce a regression in code you didn't realise you'd touched.
- Make the diff impossible to review.

A surgical patch touches only the lines that changed. The diff is small. The review is fast. The blast radius is bounded.

### 6.2 The patch-outcome pattern

Every patcher returns a structured outcome (see §5.5). A wrapper collects outcomes across multiple patchers and throws if **no** patch took effect — because that means the operation didn't do what it claimed, and silence would be a bug.

> **Sample Fitness case.** A swap touches several places in a markdown file: the Summary Table, the per-week table, the CMS Reference. Three patchers run in sequence. Each reports its outcome. If all three return `missing`, the whole operation throws `PatchHadNoEffect` → HTTP 422. The user sees a clear error rather than a silent no-op.

### 6.3 Idempotence is non-negotiable

Running the same patch twice must produce the same result. If the new value equals the old value, the patcher returns `idempotent` without modifying anything. This makes re-saves safe and undo trivially correct.

### 6.4 No regex on structured text

Regex is great for finding strings. It is terrible for parsing structured text with separators, blank lines, optional rows, and indentation. Use a state machine. Use a parser library. Anything but regex.

> **Sample Fitness case.** `extractPerUnitTargets` uses an explicit state machine:
>
> ```typescript
> type ScanState = 'top' | 'inWeek' | 'inUnit' | 'inHeader' | 'inData'
> ```
>
> The parser walks the file line by line, transitioning states. A `---` separator mid-section doesn't confuse it. A blank line in an unexpected place doesn't confuse it. A regex-based parser would have failed silently on either.

### 6.5 Preserve exact formatting

A patch that changes "  Bench Press  " to "Bench Press" introduces a whitespace diff that wasn't asked for. The patcher should replace the value while preserving the surrounding spaces, tabs, and column alignment.

### 6.6 When rewriting *is* OK

- The file is brand new (no prior version to preserve).
- The file is a generated artifact and the build regenerates it from a source of truth.
- The user has explicitly asked for a rewrite.

In all other cases: patch.

---

## 7. State and data flow

For any UI project, separating *domain state* from *UI state* is the highest-leverage architectural decision after "what is the source of truth?"

### 7.1 Two stores, one shim

- **Domain store** — what the user is working on. Loaded from the API. Owns async logic. Mutating actions hit the network.
- **UI store** — what's currently on screen. Open modals, selected cells, in-flight staging buffers, toast messages. No async. No fetches. Pure state transitions.

A barrel module re-exports both for backward compatibility, so existing call sites keep working.

> **Sample Fitness case.** `useProgrammeStore` owns `block`, `blockIds`, `activeBlockId`, undo buffers, and the async actions that talk to Express. `useUIStore` owns `activeTab`, `selectedCell`, `drawerOpen`, `activePicker`, `stagedDrawer`, `toast`. `useBlockStore` is a shim that surfaces both for older code.

### 7.2 The UI store is pure

The biggest payoff of the split: the UI store has no async, no fetches, no side effects beyond state updates. It can be unit-tested without mocks. It can be reset to defaults in `beforeEach` with no setup.

> **Sample Fitness case.** `moveCell(direction, { numClasses, numWeeks })` takes the navigation bounds as arguments. The function knows nothing about which block is loaded or how many classes exist — the caller passes those in. This decouples cell-navigation logic from data loading, and makes the test trivial.

### 7.3 Staging buffers for multi-edit forms

When a user is making several related edits inside a modal or drawer, stage them locally and commit on save. This gives them cancel-without-saving for free, and gives you a clean single-network-call commit.

**Detect no-ops.** If the user types a new value and then types the old value back, remove the staged entry. The buffer should always be the minimal patch set.

> **Sample Fitness case.**
>
> ```typescript
> stageSwap: (change) => {
>   const newBuffer = buffer.changes.filter(c => !(c.kind === 'swap' && sameSlot(c, change)))
>   if (change.newName === change.oldName) {
>     // user reverted to original — entry disappears
>   } else {
>     newBuffer.push(change)
>   }
> }
> ```

### 7.4 Views read from the store

No prop drilling. Each view calls the store hook and pulls what it needs. Components stay small and declarative. Wiring is invisible.

### 7.5 No fetching in components

All API calls live in store actions. Components dispatch actions; they don't know that a network exists.

### 7.6 Boot retry with backoff

On first load in a dev environment, the backend may not be ready. Don't crash — retry. A fixed-interval retry with a small cap is usually enough.

> **Sample Fitness case.** `App.tsx` retries `loadBlockIds()` up to 8 times with a 1.5s gap. By the time the user sees the spinner, the server has had 12 seconds to start.

### 7.7 Undo as a returned buffer

Mutating operations return an undo buffer describing how to reverse themselves. The client stashes it and exposes it as a toast action. Undo doesn't require a separate endpoint — it's a normal mutation in reverse.

---

## 8. Verification

Match the cost of verification to the cost of being wrong. Use the cheapest tool that catches the class of bug you're worried about.

### 8.1 The verification ladder

From cheapest to most expensive:

1. **Type-check** — `tsc --noEmit`. Run after every change. Catches the majority of mistakes.
2. **Static analysis / lint** — ESLint, ruff, clippy. Run before commit.
3. **Unit tests** — Vitest, pytest. Run for the affected module.
4. **Smoke test** — Mount the app, stub the network, check it renders. Catches composition bugs.
5. **Integration test** — Hits a real backend in a fixture. Catches contract bugs.
6. **E2E** — Playwright. Catches user-visible bugs.
7. **Manual click-through** — For visual or interaction work, irreplaceable.

For a typo fix, step 1 is enough. For a parser rewrite, steps 1–5 are required.

### 8.2 The smoke test that just renders

A test that mounts the whole app, stubs `fetch` to return errors, and checks that no exception escapes during render. Catches dependency-injection mistakes, missing context providers, missing default values. Cheap, fast, and surprisingly effective.

> **Sample Fitness case.** `app-render.test.ts` mounts the full app in happy-dom, stubs fetch to fail, and asserts no render error is thrown. It catches "I broke something at the App level" in under a second.

### 8.3 Reset state between tests

Always reset shared state in `beforeEach`. A test that depends on the order tests ran in is a test waiting to fail in CI.

```typescript
beforeEach(() => {
  useUIStore.setState({
    activeTab: 'phase-grid',
    selectedCell: null,
    drawerOpen: false,
    // ...all the rest
  })
})
```

### 8.4 Verify before declaring done

Don't say "fixed" until you've actually run the thing. Don't say "tests pass" until the test runner agrees. Don't say "shipped" until the smoke test is green.

### 8.5 Use a verification subagent for high-stakes work

For changes you can't fully verify yourself, spawn an independent agent to review. The fresh context catches things the original implementer can't see.

---

## 9. Memory and skills

Persistent memory and reusable skills are the difference between a fresh-every-time assistant and a colleague who remembers what you decided last Tuesday.

### 9.1 Memory: one file per concept

Keep memories small, named, and indexed. Avoid one giant `notes.md`.

- **Naming:** `{type}_{domain}.md` — `feedback_weight_notation.md`, `project_endure_structure.md`, `user_role.md`.
- **Index:** `MEMORY.md` lists every memory file with a one-line description. One line per memory, ~150 chars max.
- **Granularity:** if a single concept has more than three rules, give it its own file. If two memories overlap, merge them.

### 9.2 What's a good memory

- **Feedback** — corrections and confirmed approaches the user has given you. ("Use M:/F:, not ♂/♀." "Keep trainer notes terse.") Each carries a *why* line so future-you can judge edge cases.
- **Project context** — decisions and their rationale, including alternatives considered and rejected. ("Markdown as source of truth, not SQLite — because the user can edit the files directly with no UI.")
- **User profile** — role, expertise, preferences. ("The product owner is the product designer; they are comfortable in TS but defers to the agent on parser internals.")
- **References** — pointers to external systems. ("Bugs are tracked in the Linear project INGEST.")

### 9.3 What's a bad memory

- Code patterns, file paths, architecture — derivable from the repo. Read the code.
- Recent commit history — `git log` is authoritative.
- Conversation state in the current session — that's what tasks are for.
- Fix recipes for bugs that are now fixed — the commit message has the story.

### 9.4 Skills as workflow scaffolding

When a workflow has many steps, state to track, and needs to run repeatedly, encapsulate it as a skill. The skill's description triggers it on natural-language phrases; the skill's instructions are a living spec.

**Use a skill when:**
- The workflow has 5+ steps.
- The workflow can resume from where it left off.
- The same conventions need to be applied every time.
- A wrong step is expensive to undo.

> **Sample Fitness case — orchestrator + sub-skills.** `unit-programme-runner` orchestrates the end-to-end 4-week pipeline: block setup → candidate pool export → 7 sequential class generations → CMS Excel build. It calls `unit-programme-generator` 7 times, checkpointing between each ("Ready to continue from ENDURE?"). The runner's first action is always "start fresh or continue?" — it reads `output/` to detect existing work and reports back: "Found block from [date]. Done: FORCE, CONVOY, SET. Remaining: ENDURE, ARENA, NEXUS, Excel."

**Checkpoint pattern.** A long-running orchestrator skill should pause between stages and ask the user to confirm. This catches drift early and lets the user steer.

### 9.5 Pin skill versions

If skills come from an external repo, lock them with hashes so they can't drift silently.

> **Sample Fitness case.** `skills-lock.json` pins 14 skills from `mattpocock/skills` by hash. Updates are explicit, not accidental.

### 9.6 Domain-specific skills for repeated edits

When the user repeatedly asks you to modify the same kind of file in the same way, write a skill for it. The skill enforces the conventions; the user just says "add a feature to the backlog" and the skill knows where, what columns, what backup pattern.

> **Sample Fitness case.** The `backlog-manager` skill triggers on any backlog modification ("add a feature," "reprioritise," "mark as done"). Every change creates a versioned backup automatically. The user doesn't have to remember the convention; the skill enforces it.

---

## 10. Git workflow

### 10.1 One slice, one commit

Each slice (§4) is a single coherent commit. The commit message describes what the slice delivers, end-to-end.

### 10.2 Scope-prefixed messages

```
feat(slice-10): launcher, Playwright smoke, verification checklist
fix: address bug-sweep findings (P0-1, P0-2, P0-3, P1-2, P1-3 plumbing)
chore: planning docs + output formatting
```

The prefix tells you the kind of change at a glance. The body lists what's included. Long slice commits get bullet lists.

### 10.3 `.gitignore` is a contract

The gitignore is not just about build artifacts. It's a declaration of what the project treats as sensitive or ephemeral.

> **Sample Fitness case.** The gitignore excludes:
> - `member-data/`, `member-feedback/` — never commit personal data
> - `.env`, `secrets.json`, `credentials.yaml` — secrets
> - `cms-output/` — large generated binaries
> - `~$*.xlsx` — Office lock files
> - `.vscode/`, `.idea/`, `*.swp` — editor noise
>
> Respect this. If something appears in `.gitignore`, treat it as off-limits unless explicitly asked.

### 10.4 Per-repo identity

Configure git identity per-project so commits attribute correctly when working across multiple machines or contexts:

```bash
git config user.email "YOUR_EMAIL"
git config user.name "Project Maintainer"
```

### 10.5 Document environment quirks

Some environments have bugs you have to work around. Document them in `CLAUDE.md` so the next session doesn't have to rediscover them.

> **Sample Fitness case** from `CLAUDE.md`:
>
> > The sandbox filesystem has a permission issue with `.git/HEAD.lock` and `.git/index.lock` — these can't be removed by the shell after a commit. Every second commit needs the lock files removed from the user's terminal first:
> >
> > ```bash
> > rm "/path/to/repo/.git/HEAD.lock" "/path/to/repo/.git/index.lock" 2>/dev/null
> > ```

### 10.6 Never commit secrets

Even if the user pastes a token into chat to test something, do not commit it. Add it to `.env`, add `.env` to `.gitignore`, and use environment variables.

---

## 11. Common pitfalls

A consolidated list of mistakes that are easy to make. Scan this before doing something you're not sure about.

### 11.1 Rewriting when you could patch
The single most expensive mistake. Always check whether a surgical patch (§6) is possible before rewriting any file.

### 11.2 Duplicating types between modules
Two definitions of the same type *will* drift. Re-export, don't re-declare (§5.3).

### 11.3 Regex on structured text
Multi-line, formatted text with separators eats regex parsers for breakfast. State machine or parser library only (§6.4).

### 11.4 Async logic in UI stores
The UI store stops being testable the moment it starts calling `fetch`. Keep it pure (§7.2).

### 11.5 Adding features the user didn't ask for
"While I was in there, I also..." is a phrase to delete from your vocabulary. Stay in scope.

### 11.6 Inventing domain rules
If you don't know the domain answer, say so. Don't guess and write the guess into a file the user will trust later.

### 11.7 Skipping the type-check
`tsc --noEmit` takes seconds. The bug it would have caught takes hours. Always run it.

### 11.8 Memorising what you can derive
Save knowledge that *changes the output* or *captures a decision*. Don't save what the code already knows.

### 11.9 Conflating "I tried" with "it works"
Run the thing. Read the output. Confirm. Then say it's done.

### 11.10 Silent no-ops
If an operation didn't have any effect, throw — don't return success. Silence is the worst kind of bug.

### 11.11 Reading every file before starting
The temptation to "build a complete mental model first" is a productivity trap. Read what the task needs, no more.

### 11.12 Long commit messages with no scope prefix
You will not remember what `"Fixed it"` meant in three months. Use the scope prefix (§10.2).

### 11.13 Skipping the clarifying question
The 30 seconds you save asking is paid back many times by *not* building the wrong thing (§1.1).

### 11.14 Forgetting to update CLAUDE.md
When a slice lands, the build plan changes, the constraints might change, the commands might change. Update the doc as part of the slice.

### 11.15 Trusting an agent's "completed" without verifying
An agent's summary describes what it intended to do, not necessarily what it did. Read the diff. Run the tests.

---

## 12. Quick reference checklists

### 12.1 Starting a new project

- [ ] Create `CLAUDE.md` (stack, commands, architecture, constraints)
- [ ] Create `AGENTS.md` (which files to read for which task)
- [ ] Create `CONTEXT.md` (domain vocabulary)
- [ ] Configure git identity for the repo
- [ ] Decide the source-of-truth shape (database? files? API?)
- [ ] Identify the frozen tiers (what's untouchable?)
- [ ] Write Slice 1 plan (one-line goal)
- [ ] Initial commit with the docs and an empty project skeleton

### 12.2 Starting a slice

- [ ] Read `CLAUDE.md` "Key Constraints"
- [ ] Read the relevant section of this playbook (e.g. §6 if file edits are involved)
- [ ] Write the slice's one-line goal
- [ ] Type-check baseline passes
- [ ] Plan order: types → business logic → API → store → UI → tests → docs

### 12.3 Finishing a slice

- [ ] Type-check passes (`tsc --noEmit` or equivalent)
- [ ] Tests pass (`npm test` or equivalent)
- [ ] Manual smoke of the new feature
- [ ] `CLAUDE.md` Build Plan updated
- [ ] Relevant memory file updated if conventions changed
- [ ] Commit with scope-prefixed message
- [ ] Diff reviewed (by you, before declaring done)

### 12.4 Before any file edit

- [ ] Can I patch instead of rewriting? (§6)
- [ ] Is this file in a frozen tier? (§2.3)
- [ ] Do I have the exact lines I need to change, or am I guessing?
- [ ] Will my change preserve formatting and surrounding context?

### 12.5 Before any commit

- [ ] Type-check passes
- [ ] Tests pass
- [ ] No secrets in the diff
- [ ] No generated artifacts that shouldn't be committed
- [ ] Commit message has a scope prefix
- [ ] Commit message describes the change end-to-end

### 12.6 When stuck

- [ ] Re-read the relevant section of this playbook
- [ ] Check `MEMORY.md` for prior decisions on this topic
- [ ] Check `CONTEXT.md` for the right vocabulary
- [ ] Ask the user a focused clarifying question (max 4 options)
- [ ] Don't guess — defer

### 12.7 When the user asks for something underspecified

- [ ] Identify the 1–3 things you don't know
- [ ] Ask them as a single multi-choice question
- [ ] Wait for the answer before doing real work
- [ ] If the answer creates new ambiguity, ask again — but stop at the second round

### 12.8 When inheriting an unfamiliar codebase

- [ ] Read `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`
- [ ] Read `MEMORY.md` (your persistent memory index)
- [ ] `ls` the top-level folders
- [ ] Read `package.json` / `pyproject.toml` / etc. for the stack
- [ ] Skim the Build Plan
- [ ] Identify the source of truth
- [ ] Identify the frozen tiers
- [ ] Don't read more than the requested scope needs

---

## Appendix: Stack notes (delete or replace per project)

This playbook was extracted from a TypeScript/React/Express project. If your new project uses a different stack, translate the case studies. The principles are stack-agnostic; the syntax is not.

| Concept | TypeScript | Python | Rust | Go |
|---|---|---|---|---|
| Literal union | `'a' \| 'b'` | `Literal['a', 'b']` | `enum` | constants + custom type |
| Discriminated union | `{ kind: 'x' } \| { kind: 'y' }` | `Union[Foo, Bar]` + tag | `enum` with variants | tagged struct |
| Type-check | `tsc --noEmit` | `mypy` / `pyright` | `cargo check` | `go vet` / `go build` |
| Unit tests | `vitest` / `jest` | `pytest` | `cargo test` | `go test` |
| Smoke test | mount app + stub fetch | import + entrypoint | `cargo run` smoke | `go run` smoke |
| Custom exceptions | `class FooError extends Error` | `class FooError(Exception)` | `enum Error { ... }` | error types + `errors.Is` |

---

*Last updated: 2026-05-23. When you change the structure of this playbook, bump the date and note what changed below.*

### Changelog
- **2026-05-23** — Initial version, distilled from the Sample Fitness Programming App build (Slices 1–10).

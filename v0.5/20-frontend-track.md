# 20 · Frontend track

> The track that sits alongside the process map for any project with a UI. The process stages still apply; this file adds the **design-artefact discipline** that prevents the largest source of churn in AI-assisted UI work — agent and human using the same word for different things, or different words for the same thing, or the same component for different jobs.

---

## The three artefacts

Three files are the source of truth for what the UI is allowed to look like and how it is allowed to behave.

**`DESIGN-GLOSSARY.md`** — the **textual** ubiquitous language. Every UI term we use (pill, container, elevated card, primary CTA) is defined here exactly once, with a precise definition.

**`ui-kitchen-sink.html`** — the **visual** ubiquitous language. Every term in the glossary is rendered live here. Opens in any browser, no build step. CSS variables in `:root` for every token.

**`frontend-design-language-guide.html`** — the **interaction** language. The layer above the kitchen sink: application-level principles (e.g. full-width rows over card galleries), which surface to use for which operator task (row, drawer, disclosure, modal, dedicated page), and the surface decision rules table. The kitchen sink says what a drawer looks like; the guide says when a drawer is the right answer.

Templates for all three are in `templates/`: `DESIGN-GLOSSARY.md`, `ui-kitchen-sink.html`, and `frontend-design-language-guide.html`.

**Hard rule: never invent UI vocabulary or interaction patterns.** If a term is missing from the glossary, or a screen needs a surface the guide doesn't sanction, stop, ask the user to decide, and update the artefacts **before** writing component code.

## The UI preview gate (ASCII first, then mockup)

For UI-affecting work, the sequence is: ASCII diagram → human approval → HTML mockup when the change is interactive or non-trivial → human approval → implementation.

There are two ASCII forms:

- **Inline** — a chat sketch with boxes and labels for small or medium changes.
- **Comprehensive `.md`** — for new screens or complex layouts, saved at `planning/{feature-slug}/ui-diagrams/{screen}.md`; it covers empty/loading/error/populated states, interactions, and responsive notes.

Pure cosmetic changes may use a one-line sketch or skip the gate. Anything adding or moving an element needs at least the inline form. New screens and structural changes need the comprehensive form. The comprehensive form names the glossary terms and surface decisions it uses, keeping the three-artefact discipline intact.

The mockup step reuses the existing `ui-update-exact-mockup` skill or `/design-html`; implementation of an approved mockup uses `ui-retrofit-from-mockup`. Do not invent bespoke mockup mechanics. Every gate prompt ends with typed action words: **approve sketch** / **revise sketch: <what>** / **full diagram** / **build mockup** / **approve mockup**.

### Prototype evidence

Use `/prototype` when the unresolved question is the design itself, not merely the fidelity of an already chosen screen. UI prototypes generate structurally different variants on an existing route where possible; logic/state prototypes produce one self-contained HTML file a non-developer can open directly, with free-play controls and guided walkthroughs. Both are primary-source evidence: after the human chooses, fold the validated decision into production, preserve the full prototype on a throwaway `prototype/<name>` branch, and leave a context pointer on the feature or decision ticket. The live branch keeps neither losing variants nor prototype switchers.

This does not replace the ASCII and mockup approval gate. The prototype supplies concrete evidence for the decision; the approved diagram/mockup records what production will implement.

---

## Glossary progressive disclosure — read the index, not the monolith

`DESIGN-GLOSSARY.md` starts as one file, which is right while it is small. Once it grows past a handful of entries (≈30, or sooner if loading the whole file for a one-component task feels wasteful), split it so an agent loads only the entries a task needs rather than the entire vocabulary every UI session:

```
design-glossary/
├── index.md                 # read-first index, one line per component (GENERATED — never hand-edit)
└── components/<term>.md      # one entry per file; inter-component references become bundle-relative **Related.** links
```

This layout lets an agent load one component entry at a time instead of the whole glossary. Mechanics:

```bash
# from the project root (the folder holding DESIGN-GLOSSARY.md)
python3 {playbook-path}/v0.5/scripts/check-glossary.py split ./DESIGN-GLOSSARY.md ./design-glossary   # one-time conversion
python3 {playbook-path}/v0.5/scripts/check-glossary.py build-index ./design-glossary                  # after editing any entry
python3 {playbook-path}/v0.5/scripts/check-glossary.py check ./design-glossary --kitchen-sink ./ui-kitchen-sink.html
```

**When split, "read it before any UI work" means read `design-glossary/index.md` first, then open only the entries the feature touches.** `index.md` is generated from the entry files — edit `components/<term>.md`, then rebuild; never hand-edit the index. Reading stays permissive (a link to a not-yet-written entry shouldn't stop an agent), but `check` reports the broken link so it gets fixed. The threshold is project-tunable — small projects keep the single file and pay nothing.

Because component entries live under `design-glossary/components/`, kitchen-sink links inside those entries are relative from that folder (for the layout above: `../../ui-kitchen-sink.html#...`). `build-index` rebases those links for `design-glossary/index.md` automatically.

---

## Bootstrap at project setup — MANDATORY for any project with a UI

When bootstrapping a new project (see the bootstrap sequence step 2 in `README.md` and `10-process/00-prereqs.md` Check C), the agent must not silently skip the frontend artefacts and must not silently impose the defaults. **Ask the user explicitly:**

> This project has a UI. How do you want to set up the three frontend design artefacts (glossary, kitchen sink, design-language guide)?
>
> 1. **Use the playbook defaults** — copy all three from `templates/`, then run the design interview to adapt tokens and branding.
> 2. **Supply your own** — point me at existing files, a Figma export, screenshots, or a component library; I'll distil them into the three-artefact shape.
> 3. **Mix** — defaults for some, your own for others.
> 4. **Skip for now** — only if the project genuinely has no UI. Record the decision in `.playbook-state.yml` so the question isn't re-asked every session.

Whatever the answer, the session must end with all three artefacts present in the project (or an explicit recorded skip). Copy them to the project root or `docs/design-docs/` — record the chosen location in `CLAUDE.md`.

---

## How the three artefacts plug into the process map

| Stage | Frontend addition |
|---|---|
| **00 Prereqs** | Verify the glossary (`DESIGN-GLOSSARY.md` **or** a `design-glossary/` directory), `ui-kitchen-sink.html`, and `frontend-design-language-guide.html` exist. If missing, halt and run the bootstrap prompt above. |
| **01 Align** | Run the design interview (below) if the project doesn't yet have a settled visual language. After `/grill-with-docs` settles domain branches for a UI-affecting feature, run the ASCII gate before prompting to create or update an HTML mockup using the project visual language before implementation planning. Choose surfaces using the guide's decision rules. Use `/plan-design-review` after grilling/mockup when useful. |
| **02 Context / ADRs** | Add new design tokens (colours, spacings, radii) to the kitchen sink's `:root`; add new UI terms to the glossary (a new `components/<term>.md` + `build-index` if split); record new interaction patterns or surface decisions in the guide. |
| **03 Spec** | Identify which existing glossary terms and which guide surfaces the feature needs. List them explicitly — for a split glossary, read `design-glossary/index.md` and open only those entries. For new screens or structural UI changes, store the comprehensive ASCII diagram before breakdown. |
| **04 Breakdown** | UI slices reference glossary terms by name in their acceptance criteria. |
| **06 Architecture** | Audit the kitchen sink for drift — any class, colour, or spacing in the codebase that isn't in the kitchen sink is tech debt. Audit screens against the guide's decision rules — e.g. a modal doing a drawer's job. |
| **07 Implementation** | Code references only glossary terms and only styles from the kitchen sink, on surfaces the guide sanctions. For a split glossary, load only the `components/<term>.md` entries the slice touches (via the index), not the whole vocabulary. `/design-shotgun` for new layouts; `/design-html` to promote the chosen variant to working HTML. |
| **08 Review** | Always run `/ai-playbook-design-review` for UI-touching PRs. The report-only review must cover desktop/tablet/mobile behavior, body overflow, mobile tap targets, table readability, heading hierarchy, compact-control exceptions, and conformance with the guide's surface decision rules. |
| **09 QA** | Fresh report-only browser/device pass — visual diff against the kitchen sink for the affected sections, plus the responsive and URL-state smoke floor below. |

---

## The design interview (run at project kickoff if no design system exists)

Borrowed from Matt Pocock's `/grill-me`: minimum questions to settle before writing component code.

1. What are the **primary, secondary, and accent colours**, with hex values? Light mode and dark mode if applicable.
2. What is the **typographic scale** (font family, sizes, weights, line-heights)?
3. What is the **spacing scale** (4 px / 8 px / Tailwind default)?
4. What are the **border-radii** in use, and where does each one apply?
5. What is the **default container** — its padding, border, shadow, and background?
6. What is the **default pill / badge** — its padding, font-size, radius, and colour palette?
7. What **interaction states** must every interactive element support — hover, focus, active, disabled, loading?
8. What is the **accessibility floor** — minimum contrast ratio, focus-ring style, keyboard-nav expectations?
9. What is the **default object shape** — full-width rows/tables (dense workspace) or cards? Where are cards permitted?
10. What is the **default change surface** — drawer, modal, inline expansion, or dedicated page — for add/edit, review, destructive confirmation, and history reading?
11. What are the **viewport assumptions** — desktop-first with a minimum body width, or fully responsive?

Every answer must end up either as a glossary entry, a kitchen-sink section, a CSS variable in the kitchen sink's `:root` block, or a principle/decision-rule row in the design-language guide. No answer is allowed to live only in the conversation transcript. Questions 9–11 belong in the guide.

---

## Responsive and URL-state smoke floor

Every UI-touching slice must pass this floor before ship:

- Check desktop, tablet, and mobile viewports for the affected screens.
- Confirm the page body has no horizontal overflow; wide data tables must scroll inside their table wrapper instead of compressing columns into unreadability.
- Confirm mobile links, buttons, and interactive chips meet the 44px touch-target floor unless a compact-control exception is documented in the design review.
- Confirm the heading hierarchy matches the visual page hierarchy.
- For URL-driven drawers, filters, tabs, and row expansions, verify query/hash transitions preserve scroll position, preserve focus where expected, and do not use native form submission for live filter updates that should stay in place.

---

## The kitchen-sink-update-first rule

When the user says *"can we make the primary pill a bit more compact"*:

1. **Update the kitchen sink first.** Change the CSS variable or class definition. Render. Get user sign-off in the kitchen sink, not in a feature screen.
2. **Update the glossary** if the anatomy line changed.
3. **Grep the codebase** for every consumer of the old style. Decide: do they all migrate, or is this a new variant?
4. **Migrate consumers in a single sweep**, not feature-by-feature.

For visual element changes, reversing this order — feature first, then kitchen sink — is the most common way the glossary and kitchen sink drift. For surface or interaction changes, update the design-language guide before feature code for the same reason.

---

## Drift detection

Run periodically (cadence-controlled in `playbook-cadences.yml`):

- Any class, CSS variable, or computed colour used in the codebase that isn't in the kitchen sink → drift.
- Any glossary term not used anywhere → dead vocabulary.
- Any kitchen-sink section without a glossary entry → unanchored visual.
- Any glossary entry whose kitchen-sink anchor 404s → broken link.
- Any screen whose surface choice contradicts the guide's decision rules (e.g. history in a modal, edit form expanding a row) → interaction drift.
- **Split glossary only:** an entry missing from `index.md` (or an index line with no entry file) → stale index; a `**Related.**` link to a non-existent component → broken cross-link. `{playbook-path}/v0.5/scripts/check-glossary.py check` (run from the project root) reports all three (and, with `--kitchen-sink`, the anchor 404s above).

Fix each on detection. The `06-architecture.md` stage is the natural place to schedule this. For a split glossary, run `{playbook-path}/v0.5/scripts/check-glossary.py check` from the project root here.

Record the run: set `last_run.kitchen_sink_drift_audit` in `.playbook-state.yml`.

---

## Reference implementation

`references/sample-athletics-ui/SAMPLE-ATHLETICS-APP-ARCHITECTURE.md` and `references/sample-athletics-ui/sample-athletics-ui-kitchen-sink.html` are the worked example. They show the Sample Athletics conventions for tokens, app shell, status colours, form controls, and the relationship between the glossary, kitchen sink, and live code. `references/sample-athletics-ui/design-glossary/` is the same glossary in **split (progressive-disclosure) form** — an `index.md` plus one file per component — showing what the split layout and bundle-relative `**Related.**` links look like in practice.

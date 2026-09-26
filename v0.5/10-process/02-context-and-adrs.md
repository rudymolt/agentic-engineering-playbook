# 02 · Context and ADRs

> A *side-effect* of stage 01. As alignment decisions crystallise, they get written to two living docs.

**This stage in one breath:** Capture crystallising decisions into `CONTEXT.md` and ADRs as a side-effect of alignment — never speculatively. Output: durable decisions recorded where future sessions will find them.

---

## Primary skill

`/domain-modeling` (Matt, model-invoked — new in upstream v1.0.0). `/grill-with-docs` invokes it inline during alignment, but it can also be reached directly whenever the domain model is being *changed* rather than merely consumed: challenging a term against the glossary, sharpening fuzzy or overloaded language, stress-testing concept boundaries with edge-case scenarios, and cross-referencing claims against the code. Merely reading `CONTEXT.md` for vocabulary is not this skill.

Its rules match this stage's: update `CONTEXT.md` inline the moment a term resolves (never batched), keep `CONTEXT.md` a pure glossary with no implementation detail, create files lazily, and offer ADRs only when the three-part test below passes.

When a current decision's historical rationale is unclear, use
`/ai-playbook-why` to gather bounded cited evidence before proposing an ADR;
its inference and unknown labels do not create a decision by themselves.

When a decision-focused session must pause or move hosts, use the conditional
[pickup brief](pickup-brief.md) to point at the durable `CONTEXT.md` or ADR
record. Do not turn a chat recap into a decision source or replay it to a fresh
verifier.

## Two destinations

**`CONTEXT.md`** — the project's domain glossary. Domain terms only, no implementation jargon. One definition per term. Used in variable names, file names, test descriptions, commit messages. Inventing your own terminology is a tax on every future conversation.

**`docs/adr/NNNN-short-title.md`** — one ADR per decision that is **hard to reverse**, **surprising without context**, and the **result of a real trade-off**. If any of the three is missing, skip the ADR. Don't pollute `docs/adr/` with trivia.

## ADR template

```markdown
# ADR NNNN — {short title}

Status: {Proposed | Accepted | Superseded by [ADR XXXX](XXXX-short-title.md)}
Date: {YYYY-MM-DD}
Authors: {name(s)}

## Context

What's the situation that forced this decision? What pressures or constraints are at play?

## Decision

What did we decide?

## Alternatives considered

What did we look at and reject? Why?

## Consequences

What follows from this decision? What does it make easier? What does it make harder? What's the next moment we'll need to revisit it?
```

## The ADR index and cross-links

Once `docs/adr/` holds more than a couple of decisions, two cheap conventions (borrowed from OKF's progressive-disclosure idea — see `references/okf/okf-explainer.md`) keep the collection navigable for agents and humans:

- **`docs/adr/index.md`** — one line per ADR: number, title, status, date. It is a **generated** artefact, not hand-maintained. Rebuild it (and verify links) with the tooling:

  ```bash
  python3 {playbook-path}/v0.5/scripts/check-glossary.py adr-index ./docs/adr
  python3 {playbook-path}/v0.5/scripts/check-glossary.py check-adr ./docs/adr
  ```

- **Bundle-relative cross-links.** When one ADR references another ("Superseded by", "builds on", "reverses"), write it as a real link to the file — `[ADR 0007 — caching strategy](0007-caching-strategy.md)` — not as bare prose. This makes supersession chains traversable and lets the check surface a broken reference.

Rebuild the index whenever an ADR is added or its status changes (a natural step in the stage-10 doc-close ritual). Reading is permissive — an agent following a link to a not-yet-written ADR should carry on, not fail — but `check-adr` **reports** a broken link so it gets fixed rather than left to rot, matching the playbook's drift-detection stance.

## Multi-context projects

If the repo holds multiple bounded contexts:

- `CONTEXT-MAP.md` at the root points at per-context glossaries.
- System-wide ADRs live at `docs/adr/`.
- Context-specific ADRs live at `{context}/docs/adr/`.

## How alignment decisions promote here

After stage 01:

1. Re-read the planning docs from `planning/{feature-slug}/`.
2. Extract any new domain terms → append to `CONTEXT.md` (alphabetical within section).
3. Extract any hard-to-reverse decisions → create new ADRs at `docs/adr/`.
4. Don't delete the planning docs yet; they're still live for stages 03–10.

## What this stage doesn't do

- It doesn't invent vocabulary. Only terms the user has actually used or agreed to.
- It doesn't write speculative ADRs. Only decisions that have actually been taken.
- It doesn't replace the planning folder. Planning docs and `CONTEXT.md` / ADRs coexist until ship.

---

## Next

- Decisions recorded, alignment still in progress → return to `01-align.md`
- Alignment settled → open `03-spec.md`
- Unsure → run `/whats-next`

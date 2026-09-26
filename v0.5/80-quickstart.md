# 80 · Quickstart — one feature through all 13 stages

> A worked end-to-end pass of the full loop on a deliberately tiny project, so you can see what each stage actually produces before running it on something real. The project (MeetTrack) and its mid-feature artefacts also live as the benchmark fixtures in `../bench/fixtures/` — what you read here is measured there.

**This guide in one breath:** MeetTrack, a small athletics-results library, takes one feature — `results-history-view` — from a vague request to a shipped, retro'd release. Every artefact shown is real and small.

---

## The project

MeetTrack records athletics results (athlete, event, mark, meet date), ranks results tables per event, and answers personal bests. Pure Python, no UI (`decisions.no_ui: true`), tests via `python3 -m unittest`. Bootstrapped from this playbook: `CLAUDE.md` (with the first rule), `AGENTS.md`, `CONTEXT.md`, `.playbook-state.yml`, `playbook-cadences.yml`, `planning/` + `archive/` with `STATUS.md` files. One feature (`results-entry`) has already shipped and been archived.

## The request

> **Human:** "Coaches keep asking if athletes are actually improving. Can the library show that?"

What follows is the full loop, stage by stage.

---

### 00 · Prereqs (every session, first)

Agent checks skills are installed, project files present, version current, `no_ui` recorded (so frontend checks skip), tests green. Output: *pass*. ~30 seconds. **Next block routes:** user described a feature → `01-align.md`.

### 01 · Align — grill before code

The first rule fires: this is a feature request, so no code. The agent grills:

> Goal in one sentence? — *"A coach can see one athlete's progression in one event over time."*
> Is this a ranking (who's best) or a history (how one athlete moved)? — *History. Ranking already exists as the results table.*
> Order? — *Oldest first; progression reads forward.*
> Out of scope? — *Charts, UI, cross-event aggregation, persistence (ADR-0001 stands).*
> What words? — *Coach says "progression"; we standardise on "history view" to avoid two terms.*

### 02 · Context and ADRs — record while it's fresh

`CONTEXT.md` gains the term (this is a side-effect of 01, not a separate session):

> **history view** — A chronological listing of one athlete's results in one event, oldest first, showing progression toward their personal best. **Not the same as** results table — the table ranks everyone; the history view follows one athlete.

No new ADR — no architectural decision was taken (ADR-0001, in-memory store, already covers the constraint that matters).

### 03 · Spec — write down what was agreed

`planning/results-history-view/spec.md`, ~25 lines. The heart of it:

> **R1.** `history(athlete, event)` returns results sorted by meet date ascending.
> **R2.** The personal-best entry is identifiable in the returned history.
> **R3.** Date ties preserve insertion order (stable).
> **R4.** No persistence changes (ADR-0001).
> **Success:** a coach can answer "is Runner A improving in the 100m?" from one call.

State update: feature `results-history-view` → `status: spec-written`; status block recomputed.

### 04 · Breakdown — vertical slices

`planning/results-history-view/slices.md` — three slices, each cutting store → query → tests:

> 1. Store supports per-athlete, per-event chronological retrieval (sorted, stable)
> 2. `history(athlete, event)` query function with PB flagged in the returned rows
> 3. History formatting helper for display (plain-text progression listing)

State: `status: sliced`, `slices: 3`, `slices_open: 3`.

### 05 · Triage — pick the next slice

Slice 1 wins: everything else depends on it. (On a busier project this stage also keeps the tracker honest — dead issues closed, duplicates merged.)

### 06 · Architecture — only when the cadence fires

Not this time: `slices_since_last_architecture_review` is below threshold. The stage exists so this *check* happens, not so it always runs.

### 07 · Implementation — TDD

Slice 1, red first:

```python
def test_history_is_chronological_oldest_first(self):
    rows = self.t.history("Runner A", "100m")
    self.assertEqual([r.meet_date for r in rows], sorted(r.meet_date for r in rows))
```

Then the minimal green implementation. Structural refactoring is considered under the stage-08 stage-owned standards/spec pass, not inside the TDD loop. Commit tagged per the project's slice convention. State: `slices_open: 2`, architecture counter +1, status block recomputed.

### 08 · Review — find what the tests don't

One pass before the PR lands: correctness against the spec, no invented vocabulary (it says "history view", not "progression log"), stable-sort claim actually guaranteed (Python's `sorted` is stable — noted in the PR description rather than trusted silently).

### 09 · QA

`no_ui: true` and no external dependencies, so the verification ladder lets the green unit suite carry this slice — the stage is consulted, not skipped silently. (Slice routes onward; the *feature* ships when all three slices land.)

### 10 · Ship and deploy — and close the docs

After slice 3 lands, the feature ships. The doc-close ritual fires **now, at feature ship — not per slice**: surviving decisions promoted (none beyond the CONTEXT.md term, already recorded), release note written to `docs/releases/`, `planning/results-history-view/` moved to `archive/2026-06-19-results-history-view/`, both `STATUS.md` files updated, state stamped, status block recomputed.

### 11 · Debug — didn't fire

No defects this pass. When one appears: diagnosis before fix, and the fix itself returns through 07 as a TDD slice.

### 12 · Retro and learn

Ten minutes, honestly answered:

> **Went well:** the 01 grilling caught the ranking-vs-history ambiguity before any code; slices stayed genuinely vertical.
> **Didn't:** slice 1 nearly smuggled in a sort-key refactor; split on review.
> **Promote?** "Split refactors from feature slices" — promoted to a session rule in `CLAUDE.md`. Nothing playbook-worthy this time; logged anyway.

---

## What to take from this

- **The artefacts are small.** A 25-line spec, a 3-row slice table, a 6-line retro. The discipline is in the sequence, not the paperwork.
- **The agent never chose the route.** Stage `Next:` blocks and the status block did — that's the V0.2 ergonomics working.
- **Three stages did nothing this pass** (06, 11, and QA-as-browser-testing) and that's correct: they're checks that *can* fire, not ceremonies that must.
- The mid-flight version of this exact project — slice 1 shipped, slice 2 in review, architecture review deliberately overdue — is preserved as `../bench/fixtures/fixture-midfeature-v02/`, where the benchmark measures agents navigating it.

## Next

- Ready to run this on your own project → bootstrap sequence in `README.md`
- Project too small for the full loop → `70-lite-mode.md` (and its graduation tripwire)
- Want the why behind the shape → `60-the-theory-behind-the-playbook.html` (human guide)

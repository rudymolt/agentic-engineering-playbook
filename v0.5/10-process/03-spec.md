# 03 · Spec — synthesise alignment into a feature contract

> Turn the grilling and planning output into a structured spec. The skill does **not** re-interview — it takes what's already in the conversation and writes it down.

**This stage in one breath:** Synthesise the alignment conversation into a structured spec without re-interviewing. Output: `planning/{slug}/spec.md`, feature status `spec-written`.

---

## When to run

After stage 01 alignment is settled and stage 02 has captured the surviving terms and decisions. Don't run earlier — the spec will be padding rather than substance. If unresolved cross-domain decisions still control acceptance criteria, architecture seams, or verification targets, stop and offer the user-invoked [`../92-wayfinder-track.md`](../92-wayfinder-track.md) instead of writing a mostly-open spec.

## What to run

Optionally first: `/plan-eng-review` (gstack) if not already run during alignment. Locks data flow, diagrams, edge cases, and tests.

Then: `/to-spec` (Matt; formerly `/to-prd` — renamed in upstream v1.1.0). Produces the spec, sketches the **seams** the feature will be tested at — preferring existing seams, the fewer the better — and confirms them with the user. It publishes to whatever tracker `/setup-matt-pocock-skills` configured — GitHub, Linear, or local files.

**Triage-label change to know about:** `/to-spec` applies `ready-for-agent` directly ("no need for additional triage"), where the old `/to-prd` applied `needs-triage`. This playbook still routes the breakdown through stage 05 triage for prioritisation across features — the label just means the spec itself needs no further triage pass.

If the spec hangs on an open factual question (a library's actual behaviour, an API's limits, a standard's requirements), run `/research` (Matt, model-invoked — new in upstream v1.0.0) rather than settling it from memory. It investigates against high-trust primary sources as a background agent and commits a cited markdown file to the repo — which then feeds the spec's "Open questions" section with evidence instead of guesses.

Before the spec is accepted, run both checks:

- **scope-guardian:** challenge unjustified complexity, scope creep, and premature abstraction.
- **Coherence:** check for internal contradictions and terminology drift against `CONTEXT.md`.

## What the spec must contain

The Matt skill enforces most of this, but for reference:

- **Problem statement.** One paragraph, in `CONTEXT.md` vocabulary.
- **User stories.** Concrete scenarios, each with an acceptance criterion.
- **Out of scope.** The "no" list. Often more important than the "yes" list.
- **Deep modules to extract.** Which seams in the codebase should this feature use? Which should it introduce?
- **Testing decisions.** Which modules need unit tests, which need integration tests, and which need a stage-09 browser/device pass.
- **Open questions.** Anything stage 01 couldn't settle. Mark explicitly — don't bury.

## Where the output lives

```
planning/{feature-slug}/spec.md
```

Plus an issue in whatever tracker `/setup-matt-pocock-skills` configured (e.g. Linear, GitHub Issues).

Legacy projects may still have `planning/{feature-slug}/prd.md` and `status: prd-written`. Treat those as the same stage during upgrades, but new V0.3.30+ projects use `spec.md` and `spec-written`.

## What this stage doesn't do

- It doesn't re-grill. If alignment was thin, go back to stage 01 — don't paper over it in the spec.
- It doesn't turn a multi-session decision frontier into an "Open questions" appendix. Use Wayfinder when resolving those questions is the work.
- It doesn't break work into slices. That's stage 04.
- It doesn't start coding. The spec is a planning artefact; code starts at stage 07.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
active_features:
  - slug: {feature-slug}
    status: spec-written
```

---

## Next

- Spec approved by the user → open `04-breakdown.md`
- Spec is controlled by unresolved, coupled decisions → offer `../92-wayfinder-track.md` and wait for human invocation
- Spec exposes unresolved questions → return to `01-align.md`
- Unsure → run `/whats-next`

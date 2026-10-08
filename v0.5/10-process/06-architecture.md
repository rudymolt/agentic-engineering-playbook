# 06 · Architecture — deep modules and seams

> A cadence-driven stage. Nudges at 3 shipped slices, insists at 6 (defaults in `playbook-cadences.yml`); runs any time the codebase feels heavy. The `/whats-next` skill will surface this when overdue.

**This stage in one breath:** Step back from feature work and pay down structural debt — deep modules, clean seams. Output: refactors merged or queued as issues, slice counter reset.

---

## When to run

By cadence:

- At 3 shipped slices (nudge) or 6 (insist) — the defaults in `playbook-cadences.yml`.
- Any time the user says the codebase feels heavy or hard to navigate.

By event:

- A new top-level domain module has just been introduced.
- A module that used to be deep has acquired a wide interface and lost its leverage.
- An ADR is starting to feel wrong.
- A source, style, or living-doc file has become a git hotspot across recent sessions, even if the slice counter is not overdue.

### Timing against an open feature PR

When the cadence comes due while the feature that tripped it is still unmerged, run the review **before the human merges** — findings then land as ordinary review fixes on the open branch. Deferring past the merge converts the same findings into an avoidable follow-up PR or patch release (observed on sample application' Settings centre, 2026-07-11: the review ran only after the feature PR merged, found two real boundary defects, and fixing them took a separate PR). The human may still defer the review, but to a named point **before** the merge — "after this slice", not "after the ship".

## What to run

`/improve-codebase-architecture` (Matt). Surfaces **deepening opportunities** — refactors that turn shallow modules into deep ones, with the goal of testability and AI-navigability.

Scope before scanning. If the human names a module, subsystem, or pain point, keep the exploration there. Otherwise inspect recent commit history first and focus the review on files that repeatedly absorb unrelated concerns. Hotspots in global CSS, read models, route/page files, docs maps, or playbook state are signals that the next refactor may need to deepen a shared primitive rather than patch another feature surface. This is the v1.2 YAGNI filter: dormant code does not earn a speculative refactor merely because it is shallow.

Use `/ai-playbook-why` when the architecture's historical rationale needs cited
decision archaeology, and `/ai-playbook-how` to trace a bounded current seam.
Both qualify inference and source-read behavior; neither decides or applies a
refactor.

If an architecture review crosses a session, worker, or host, use the
conditional [pickup brief](pickup-brief.md) to preserve the approved seam,
findings, and evidence locators. The successor still checks the current branch,
tracker, and review gates before accepting a prior recommendation.

Optionally: `/codex` (gstack) for a second-opinion review from OpenAI Codex CLI on a high-stakes structural decision. Use deliberately — it doubles cost.

Before accepting an architecture proposal or ADR update, run both checks:

- **scope-guardian:** challenge unjustified complexity, scope creep, and premature abstraction.
- **Coherence:** check for internal contradictions and terminology drift against `GLOSSARY.md`.

## What the skill enforces

- Invokes the shared `/codebase-design` vocabulary (module, interface, depth, seam, adapter, leverage, locality); the vocabulary no longer lives in an `improve-codebase-architecture/LANGUAGE.md` file.
- Uses domain vocabulary from `GLOSSARY.md`.
- Flags any proposal that contradicts an existing ADR — explicitly, so you can decide whether the ADR needs revisiting or the proposal needs rejecting.
- Dispatches exploration and design-it-twice through the host's available subagent mechanism, without requiring Claude Code's `Agent` tool or a named agent type.

## Don't drift the vocabulary

When discussing structure, stick to the skill's vocabulary. Avoid "component", "service", "API", "boundary" — they're too overloaded to be useful when you're trying to reason precisely about depth and seams.

## Output

In-conversation proposals plus optional commits (the skill is allowed to refactor when given green light). New or updated ADRs at `docs/adr/`.

For an agent-owned delivery candidate, this stage also confirms that approved
implementation paths do not overlap default-branch protected delivery, agent,
workflow, auth, billing, migration, secret, deployment, or repository-admin
surfaces. A candidate cannot edit the policy used to classify itself. Any
overlap routes to human merge and is recorded in the envelope before build.

### Tracker provenance for findings

When this stage creates tracker work, make its origin durable instead of leaving it in the chat transcript:

- Add `Source skill: /improve-codebase-architecture` to the issue body.
- Create or reuse the tracker label `source:improve-codebase-architecture` and apply it to every umbrella issue, slice, or follow-up directly produced from this review.
- Carry both markers into stage 04 or any later ticket split. Do not apply the label merely because an independently created issue is architecture-related.
- If the tracker has no labels, the source line is the required fallback. Before closing the review, query the created issues and verify that each direct descendant carries the available marker.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
counters:
  slices_since_last_architecture_review: 0
last_run:
  architecture_review: {ISO timestamp}
```

---

## Next

- Review complete → return to `05-triage.md` (or `07-implementation-tdd.md` if a slice was already chosen)
- Findings too large to fix now → record them as issues, then open `05-triage.md`
- Unsure → run `/whats-next`

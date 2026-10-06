# 01 · Align — grill before you code

> For any change larger than a one-liner, settle alignment before touching code. Misalignment is the single largest source of waste in AI-assisted engineering.

**This stage in one breath:** Interrogate the idea until goal, constraints, and non-goals are settled in the user's own words. Output: alignment solid enough to become context, ADRs, and a spec.

---

## When to run

Any of:

- The user has described a new feature.
- The user has described a change whose blast radius isn't obvious.
- The grilling has not been run in this session and the request is non-trivial.

Skip if the change is a one-line typo, comment, or formatting fix.

## What to run

For new choices, resolve the saved primary binding at this stage-owned invocation
point. Resume an approved execution with its retained `approved_binding`, not
current defaults; older active routes without a binding remain unchanged:

```sh
printf '%s' '{"job":"alignment","owner":"01"}' | python3 {playbook-path}/v0.5/scripts/configure-playbook.py --project . job-route
```

For a configured result, consume `routes` in saved order instead of automatically
choosing the upstream defaults below. Manual/Playbook adapters perform this
stage directly; context → decisions settles facts before human decisions and
confirmation. `configured: false` retains the existing options. Blocked means
stop and explicitly edit/preview a fallback, never acknowledge a warning and
continue. The Plan gate, human confirmation and UI preview sequence remain
mandatory. See the [job contract](../scripts/skill-bindings.md).

For a custom-retained-audit route, the portable descriptor is not a skill path.
Immediately before invoking, this stage's integration must call
`catalog.invocation_source(saved, "alignment", "01", route["source_id"])`
on its local binding catalog and load that returned private `SKILL.md` through
the host's skill reader. Use the same saved selection (or authenticated retained
approved execution) and the same external local store as `job-route`; see the
[custom invocation recipe](../scripts/skill-bindings.md#stage-owned-custom-invocation).
An unresolved source blocks. The resolver neither authenticates approval nor
grants invocation authority; real independent evidence and human gates remain
owned here.

Three skills, layered. Use the smallest set that settles the question.

Before the first planning skill starts, use the Plan gate in [`../93-model-routing-track.md`](../93-model-routing-track.md). The normal `plan` reply accepts the resolved project/feature preference and shows its origin (edition fallback: GPT-6.1 Sol/high); `models` opens verified alternatives; `openai defaults` applies GPT-6.1 Sol/high → GPT-6.1 Sol/medium → GPT-6.1 Sol/high to this feature only. A pre-feature choice creates only a pending route, not a feature folder or alignment counter.

### Option A — settled-product project, code-level change

`/grill-with-docs` (Matt). Challenges the plan against the existing `CONTEXT.md`, sharpens terminology, and updates `CONTEXT.md` and ADRs inline as decisions crystallise.

Two rules the underlying `/grilling` loop enforces as of upstream v1.1.0, both of which this stage relies on: **facts vs decisions** — a question answerable by exploring the codebase gets explored, but a *decision* is always put to the human and waited on (a grilling agent that answers its own decision questions has broken HITL); and a **confirmation gate** — the plan is not enacted until the human explicitly confirms shared understanding has been reached. Treat that confirmation as this stage's exit condition.

### Option B — greenfield or strategic-fit unclear

`/office-hours` (gstack) — YC-style office hours, six forcing questions reframing the product before any code is written. Produces a design doc that feeds every downstream stage.

Then `/plan-ceo-review` (gstack) — "find the 10-star product hiding inside the request". Returns one of: Expansion, Selective Expansion, Hold Scope, Reduction.

Then `/grill-with-docs` (Matt) on the technical branches.

### Option C — UI-heavy change

`/plan-design-review` (gstack) alongside the above, before code starts.

After `/grill-with-docs` settles a UI-affecting feature, run the UI preview gate in order: ASCII diagram → human approval → HTML mockup (for interactive or non-trivial UI, using the project's visual language and the settled domain terms) → human approval → implementation planning.

### Option D — developer-facing change (API, CLI, SDK, docs)

`/plan-devex-review` (gstack) alongside the above.

### Option E — all of the above

`/autoplan` (gstack) runs CEO → design → eng review in sequence. Use when you want all three lenses without picking.

### Option F — the destination is nameable but the route is still foggy

After bounded breadth-first grilling, offer the user-invoked `/wayfinder` track when the work will not fit one discovery session and unresolved dependencies or multiple coupled decision domains would control the eventual spec. Read [`../92-wayfinder-track.md`](../92-wayfinder-track.md). Do not start it automatically; wait for the human to invoke it. If grilling exposes no real fog, stay on the normal alignment path.

## Recommended default order for a new feature

```
/office-hours
   ↓
/plan-ceo-review
   ↓
/grill-with-docs
   ↓
create/update HTML mockup (if UI-affecting)
   ↓
/plan-eng-review (and /plan-design-review or /plan-devex-review as applicable)
```

## Exit criteria

Every leaf of the design tree has either an answer or an explicit "out of scope". For UI-affecting changes, an ASCII diagram has been approved first, then an HTML mockup has been created or updated and accepted where the gate demands one, or the user has explicitly deferred mockup work. Confirm with the user before moving on to `02-context-and-adrs.md`. If the human invoked Wayfinder, this stage pauses until the map graduates; do not pretend the open decision frontier is settled alignment.

## Where the output lives

Build-time alignment docs go in `planning/{feature-slug}/`:

- `planning/{feature-slug}/office-hours.md` (if run)
- `planning/{feature-slug}/ceo-review.md` (if run)
- `planning/{feature-slug}/design-review.md` (if run)
- `planning/{feature-slug}/eng-review.md` (if run)

These are **ephemeral** under the document lifecycle (see `../30-document-lifecycle.md`). Decisions that survive will be promoted to ADRs at `02-context-and-adrs.md`; the rest is archived on ship.

An open Wayfinder map remains canonical in the tracker and does not create a feature folder yet. Record only the visibility entries required by `../92-wayfinder-track.md`; graduation creates the normal alignment/spec artifacts.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

After alignment is settled, increment in `.playbook-state.yml`. If a verified pending Plan route exists, promote it atomically: create the normal feature folder and active entry, increment alignment exactly once, copy the selection to `active_features[].routing`, then remove the pending route and local handoff. If the human invokes Wayfinder, mark the route `linked_wayfinder`, attach its ID to the map, and create no feature or alignment increment. The routing-disabled legacy path keeps the normal create-and-increment behavior.

```yaml
counters:
  features_in_alignment: 1   # decrement when this moves to stage 03
active_features:
  - slug: {feature-slug}
    status: aligning
    opened: {today}
    routing:
      prompt_policy: {ask_each_lane|defaults_for_feature}
      lanes:
        planning: {verified selection from pending route}
last_run:
  align: {ISO timestamp}
```

---

## Next

- Alignment settled → record decisions via `02-context-and-adrs.md`, then open `03-spec.md`
- Route spans multiple coupled decisions and will not fit one session → offer the user-invoked `../92-wayfinder-track.md`
- Idea fails the grilling → stop; record the decision not to build (the cheapest outcome)
- Change is genuinely a one-liner → skip to `07-implementation-tdd.md`
- Unsure → run `/whats-next`

# 04 · Breakdown — vertical slices

> Convert the spec into independently-grabbable issues, each a tracer-bullet cutting through every layer.

**This stage in one breath:** Convert the spec into independently-shippable vertical slices, each cutting through every layer. Output: issues in the tracker, feature status `sliced`.

---

## When to run

After the spec is written and the user has reviewed it.

This frontier answers **“what can be implemented next?”** It is distinct from [`../92-wayfinder-track.md`](../92-wayfinder-track.md), whose decision frontier answers **“what can be clarified next?”** If the work is still a decision question, return to discovery rather than publishing a disguised implementation slice.

## What to run

`/to-tickets` (Matt; formerly `/to-issues` — merged into this command in upstream v1.1.0). The skill enforces vertical-slice discipline and creates tickets in dependency order (blockers first), each declaring its **blocking edges** — native blocking links on a real tracker, or "Blocked by" lines in a local `tickets.md`. Work then proceeds along the **frontier**: any ticket whose blockers are all done.

**Wide refactors are the named exception to vertical slicing.** One mechanical change whose blast radius fans across the codebase (rename a column, retype a shared symbol) can't land green as a tracer bullet. `/to-tickets` sequences it as **expand–contract**: expand (add the new form beside the old), migrate call sites in batches sized by blast radius (each batch a ticket blocked by the expand), contract (delete the old form, blocked by every batch). This matches the stage-04 verification-target rule — each batch keeps CI green, and the behaviour-preservation check is the green suite batch to batch.

## What each slice must satisfy

- **One demoable outcome.** "User can do X" — not "the schema supports Y".
- **Cuts through every layer.** Schema → API → business logic → UI → tests, end-to-end, for that one capability.
- **Independently grabbable once unblocked.** Any agent can pick it up when its declared blockers are complete; it carries no hidden dependency on another agent's context.
- **Tagged AFK or HITL.** AFK = an agent can implement without human input. HITL = human-in-the-loop required.
- **Has a dependency line.** Either "depends on nothing" or "depends on #NNN".
- **Has a verification target.** The agent never invents success criteria silently; a slice lacking them routes back to stage 01/03 before any code.

### Preserve source metadata

When the approved input came from stage 06's architecture review, every published umbrella, slice, and direct follow-up preserves both markers:

- `Source skill: /improve-codebase-architecture` in the issue body.
- Tracker label `source:improve-codebase-architecture` when labels are supported.

Propagate the markers through later re-slicing. Do not infer them for merely related architecture work created from another review or request.

| Work type | Required target before build |
|---|---|
| Feature slice | Recorded acceptance criteria + demoable outcome |
| Bug fix | Reproduction + expected behaviour |
| Refactor | Behaviour-preservation check named |
| Investigation/spike | Concrete artefact or decision as the output |

## Iterating with the user

The first cut is rarely the right cut. Walk through the slices with the user, iterate on:

- Granularity — are any slices too big to ship in one session?
- Order — is the dependency chain correct?
- AFK / HITL — is anything mislabelled?

Stop iterating when the user explicitly approves the breakdown.

## Optional delivery envelope

When the human chooses **deliver to PR** or requests the K4.1 bridge, read
[`delivery-mission.md`](delivery-mission.md) before stage 07. Add one envelope
slice that produces the declared observation contract, exact planning prefix,
approved implementation paths, risk class, evidence/verification plan,
ceilings, venue, and maximum action. The durable human approval must bind that
exact envelope before feature writes. Ordinary delivery is capped at Tier A
`open-pr`; K4.1 selection does not grant the builder or coordinator merge.

## What this stage doesn't do

- It doesn't write the code. Code starts at stage 07 inside `/tdd`.
- It doesn't decide priority across features. That's stage 05.
- It doesn't lock the breakdown forever. If a slice turns out to be wrong-sized during stage 07, come back here and re-slice.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
counters:
  slices_open: {N}
active_features:
  - slug: {feature-slug}
    status: sliced
    slices: {N}
```

---

## Next

- Slices created → open `05-triage.md` to pick the first slice
- Approved agent-owned route → open `delivery-mission.md`, then continue through stage 05
- A slice can't be made vertical → return to `03-spec.md` and re-scope
- Unsure → run `/whats-next`

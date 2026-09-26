# 92 · Optional Wayfinder track — clarify before you specify

> A user-invoked pre-spec discovery track for efforts whose destination can be named but whose route is too unclear and coupled to settle in one session. It is not stage 14 and does not replace stages 01–04.

Wayfinder answers **“what can be clarified next?”** Stage 04 answers **“what can be implemented next?”** Keep those frontiers separate.

## Invocation ownership

`/wayfinder` is user-invoked upstream (`disable-model-invocation: true`). An agent may offer it when the entry gate below is met, but must wait for the human to invoke it. Natural-language uncertainty is not authority to create tracker issues.

## Entry gate

Offer this track only when all three are true:

1. The destination can be named in one or two lines.
2. Finding the route will not fit one focused session.
3. Alignment exposes multiple coupled decision domains, unresolved dependencies, or fog that would control acceptance criteria, architecture seams, or verification targets.

This is a judgement about coupled uncertainty, not a raw count of questions. After bounded breadth-first grilling, if the route is already clear and no fog remains, return to stage 01 and do not create a map.

## Do not use it for

- A one-session alignment question.
- A known feature ready for a spec or vertical slices.
- Bug reproduction or diagnosis.
- An anchored multi-phase execution plan; use `91-delegation-track.md` when the route is already known.
- A desire to pre-slice imagined work. Fog is not a backlog.

## Chart the map

Follow the installed `/wayfinder` skill and the project's `docs/agents/issue-tracker.md` operations:

1. Name and confirm the destination first.
2. Create one tracker map labelled `wayfinder:map` with `Destination`, `Notes`, empty `Decisions so far`, `Not yet specified`, and `Out of scope`.
3. Create only questions that are precise now. Each child is one `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task` ticket.
4. Wire blocking after ticket creation. Prefer native tracker relations; use the configured body convention only when native blocking is unavailable.
5. For each `wayfinder:research` ticket just created, dispatch a `/research` subagent in parallel. Each researcher records primary-source findings on a throwaway `research/<name>` branch and leaves a context pointer on its decision ticket.
6. Stop after charting. The charting session hand-resolves no ticket; research subagents are the exception to the one-ticket-per-session rule.

The map is an index, not a second specification. Decision detail lives in the resolution comment on exactly one ticket; the map receives only a linked one-line gist.

## Make the open map visible

Map creation and visibility are one state write. Add this entry to `.playbook-state.yml`, set `last_updated`, and recompute the normal status block:

```yaml
active_wayfinding_maps:
  - title: {human-readable map title}
    locator: {tracker URL, issue identifier, or local path}
    destination: {one line}
    opened: {YYYY-MM-DD}
```

Mirror it in `planning/STATUS.md` without increasing `active_features`:

```markdown
## Open Wayfinder maps

- [{map title}]({locator}) — {one-line destination}
```

The state entry serves `/whats-next`'s one-file fast path; the status pointer serves humans. Neither duplicates ticket answers.

## Work one frontier ticket

Each session:

1. Load the map's low-resolution view, not every child.
2. Choose one open, unblocked, unclaimed ticket; assign it before work.
3. Resolve its question using the ticket type's AFK/HITL contract. A HITL session never supplies the human's answers.
4. Post the answer as a resolution comment, close the ticket, and append one linked gist to `Decisions so far`.
5. Create-then-wire newly visible questions and graduate only fog that is now precisely stateable. Close and record anything discovered beyond the destination as out of scope.
6. Stop. One session resolves at most one decision ticket; the parallel research subagents launched during charting are the only exception.

Independent frontier tickets may run concurrently in separate sessions when the human chooses; every session still claims and resolves only one ticket.

Treat a `/prototype` as runnable primary-source evidence, not a disposable screenshot. A logic/state prototype is one self-contained HTML file with domain-labelled state, free-play controls, and guided walkthroughs; a UI prototype follows the frontend track. Capture the prototype on a throwaway `prototype/<name>` branch outside main, leave a context pointer on the decision ticket, and put the verdict plus question answered in the resolution comment. Main keeps only the validated decision and production implementation.

## Graduation

Graduate only when every in-scope decision ticket is closed or explicitly ruled out, `Not yet specified` is empty, and the destination is clear enough for normal acceptance and verification contracts.

1. Walk every resolution comment.
2. Promote durable domain terms to `CONTEXT.md`, hard-to-reverse decisions to `docs/adr/`, project-wide rules to `CLAUDE.md`, and UI vocabulary to the design glossary/kitchen sink/interaction guide.
3. Run the normal stage 01–04 outputs. Create one `planning/{slug}/` folder per surviving feature, record the map link in its alignment/spec artifacts, write the spec, and publish vertical slices.
4. Give implementation tickets ordinary `ready-for-agent` plus AFK/HITL metadata and implementation blocking edges. Do not carry `wayfinder:*` labels into the implementation frontier.
5. Replace the open map with the resulting active feature(s) in state, remove it from `active_wayfinding_maps` and `planning/STATUS.md`, set `last_updated`, and recompute status.
6. Close the map with one implementation or no-build handoff and no remaining fog.
7. Commit the promoted knowledge and planning handoff intentionally before stage 07 begins. Implementation does not start from a dirty discovery tree.

### No-build outcome

If the route ends in “do not build,” record the durable reason in an ADR or decision note when warranted, clear both visibility pointers, close the map, and create no planning folder or active feature.

### Abandoned or deferred outcome

If the human abandons the destination or defers discovery indefinitely, record that disposition on the map and close it without creating a feature. In the same state change, remove the map from `.playbook-state.yml → active_wayfinding_maps` and `planning/STATUS.md → Open Wayfinder maps`, set `last_updated`, and recompute the normal status block. Resuming later is a new explicit human decision: restore both visibility pointers before resolving another ticket.

Stage 12's retro flags any map open longer than 30 days for an explicit continue / defer / abandon decision (see `10-process/12-retro-and-learn.md`), so an accidentally parked map cannot linger silently.

### Multiple-feature outcome

If discovery reveals several real features, give each its own stage 01–04 artifacts and implementation frontier. Do not turn the map into one omnibus spec.

## Relationship to other tracks

- `90-loop-track.md` schedules already-specified AFK implementation work; it does not clarify fog.
- `91-delegation-track.md` executes an anchored multi-phase plan through implementer/verifier separation; Wayfinder may produce that plan but does not execute it.
- Stage 04 slices implement known outcomes. Wayfinder tickets resolve decisions needed before those outcomes can be specified.

## Provenance and validation

The destination-first map, decision-ticket vocabulary, map-as-index rule, claim-by-assignment, and one-ticket-per-session mechanics come from Matt Pocock's upstream `/wayfinder` skill. This playbook adds an entry gate, dual visibility state, graduation promotion, abandonment handling, and a handoff to stages 01–04.

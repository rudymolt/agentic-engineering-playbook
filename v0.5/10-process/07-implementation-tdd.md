# 07 · Implementation — TDD with vertical slices

> For any non-trivial feature or bug fix. Skip only for typos, comments, or trivial formatting changes.

**This stage in one breath:** Implement one vertical slice test-first: red, then green at the agreed seam. Output: a green slice with its tests, ready for review-owned refactoring.

---

## When to run

Once a slice from stage 04 is picked up. One slice at a time — don't fan out.

Fan-out is judged on two axes: **read vs write**, and **independent vs coupled**. Read-only subtasks — explore, research, review; the §9 roles — may always be delegated to parallel sub-agents. Implementation fan-out is allowed only for **provably independent** slices: each slice "depends on nothing" per stage 04's dependency line, each runs in its **own git worktree**, each gets its own per-slice independent review, and the whole run stays under one declared §11 ceiling set before the run. Coupled implementation stays one slice at a time — a fresh-context sub-agent is an asset for checking and a liability for coupled building.

Stage 07 does not start on a slice without its verification target (per stage 04's gate).

UI slices require an approved diagram (and a mockup where the UI preview gate demands one) before component code.

Re-entering a feature after a break (a new session, or resuming after other work)? Re-read the slice's acceptance criteria from the planning folder before resuming — not just the state file. State tells you *where* you are; only the contract tells you *what was asked for*.

Before touching code for a non-trivial slice, confirm the work is on a feature branch. If the agent is on `main`, sync `main` and create a focused branch such as `codex/{short-scope}` first. Also query the host PR state for the current branch: if its PR is merged, do not reuse it for follow-up work. Update `main` and create a fresh branch. `main` should remain a local mirror of merged GitHub state, not the place where feature work accumulates. This closed-scope rule governs implementation follow-ups; the post-ship docs closeout chain (doc-close, release metadata, same-session retro) shares a single closeout branch per stage 10 — not one branch per step.

## What to run

For new choices, resolve the saved primary binding at this stage-owned invocation
point. Resume with the retained `approved_binding`, not current defaults; older
active routes without a binding remain unchanged:

```sh
printf '%s' '{"job":"implementation","owner":"07"}' | python3 {playbook-path}/v0.5/scripts/configure-playbook.py --project . job-route
```

A configured manual/Playbook adapter performs this stage's approved-seam
vertical red→green loop instead of automatically invoking `/tdd` or incompatible
`/implement`. `configured: false` retains the route below. Blocked means stop
and explicitly edit/preview a fallback. Approved Build/delivery choices, slice
confirmation, tests, fresh Verify, commits, launches, permissions and failure/
stop rules remain stage-owned. See the [job contract](../scripts/skill-bindings.md).

For a custom-retained-audit route, immediately before invoking call
`catalog.invocation_source(saved, "implementation", "07", route["source_id"])`
on this stage's local catalog and load the returned private `SKILL.md` through
the host's skill reader. Use the same saved selection or authenticated retained
Build execution and external local store as `job-route`; follow the
[custom invocation recipe](../scripts/skill-bindings.md#stage-owned-custom-invocation).
A portable identity is not a path; resolution failure blocks rather than
falling back. Real independent qualification, approved inputs and all Build
authority remain stage-owned, not conferred by local JSON or the resolver.

`/tdd` (Matt). Enforces red → green with **vertical slices** — one failing test, one piece of implementation, repeat. As of upstream v1.1.0 the loop is **red → green only**: the refactor step moved out of `/tdd` and into the stage-08 standards/spec pass (compatible `/code-review` or the same manual axes), so refactoring happens under review discipline, not mid-implementation. Tests go only at **pre-agreed seams** — the ones sketched by `/to-spec` at stage 03 and confirmed with the user — never at seams the agent invents mid-slice.

When stages 01–06 have produced an approved delivery envelope and the human
chose **deliver to PR**, invoke `/ai-playbook-deliver` and follow
[`delivery-mission.md`](delivery-mission.md). It owns bounded stage 07–10
execution through a Tier A `pr_ready` handback. Installation or a natural-
language feature request is not authority to start this route.

Upstream also ships `/implement` (v1.1.0): a per-ticket wrapper that runs `/tdd`, tests,
a nested `/code-review`, and a commit. The tested source therefore owns transaction policy
and nests a reviewer that does not satisfy the embedded contract. `/implement` is not an embedded stage-07 route. Follow this stage's red→green loop instead. A human may still request the
upstream wrapper as the top-level workflow, but its inline review never substitutes for the
fresh stage-08 verifier.

## What the skill enforces

- **No horizontal anti-pattern.** Writing all tests first, then all code, produces tests of imagined behaviour rather than actual behaviour. Refused.
- **Tests verify behaviour through public interfaces** — at the pre-agreed seams — not implementation details.
- **No tautological tests** (new in v1.1.0). An assertion recomputed the way the code computes it passes by construction and gives zero confidence. Expected values come from an independent source of truth.
- **A meaningful regression test is the diagnosed-bug default.** Stage 11 owns
  the narrow exception when the only proposed test would be misleading or
  impractical; it requires executable substitute evidence and a fresh
  independent verifier. It does not waive TDD for new behaviour or required
  checks.
- **No refactoring inside the loop.** Get to green; structural improvement is the stage-08 standards/spec pass's job (the compatible upstream source supplies the refactoring rules; the manual route preserves them).
- **No speculative features.** Only what the slice asks for.
- **Test names and interface vocabulary match `CONTEXT.md`.** No alternative jargon sneaking in.

## After each TDD cycle

The slice is now end-to-end behaviour-correct at the unit level, but not necessarily correct in a real browser. Move to:

- **Stage 09 (QA)** — a fresh report-only browser/device pass tests the app end-to-end and returns defects the unit tests did not catch; remediation is a separate generator task.

## After each slice completes

When a slice has been implemented and verified, create one atomic commit for that slice before reporting the outcome. The commit should include the slice implementation, its tests, and any directly related docs or state updates. Do not include unrelated working-tree changes.

After committing, stop and report the outcome. Do not automatically continue into the next slice unless the user chose a build loop (below) that covers it. Ask the user whether they want to proceed to the next slice, pause, review, or redirect.

## The build choice (V0.3.16)

When the user asks to build slices, combine the Build model announcement with the existing autonomy choice instead of adding a separate model ceremony. Read [`../93-model-routing-track.md`](../93-model-routing-track.md). Resolve the project/feature preference and show its origin (edition fallback: GPT-6.1 Sol/medium); `models` changes the route and returns to this menu without starting work. A feature-scoped `openai defaults` policy announces GPT-6.1 Sol/medium without asking another model question or changing project settings. Pace is separate from model and reasoning: standard speed is the default, while appending `fast` to a build action requests Codex fast mode for a run where the human is waiting.

Offer the autonomy level as a typed choice instead of assuming it:

> {N} open slices remain ({n} AFK, {m} HITL). How should I build?
>
> - Type **build one** — implement just the next slice, then stop and report (the default).
> - Type **build all** — implement the remaining AFK slices in this feature back-to-back. Each slice keeps its own independent review/QA; I'll automatically repair eligible objective findings, and pause at HITL, ambiguity, scope or human-owned decisions, three identical failures/no-progress, or a §11 ceiling. I’ll run a final review across all slices before handing back.
> - Type **build to <slice>** — run back-to-back up to and including that slice, then stop.
> - Type **models** — choose another verified Build model, then return to this menu.
>
> Add **fast** to any build action (for example, **build all fast**) when you are waiting and want the shortest Codex response time. Fast mode is currently described by Codex as 1.5× generation speed with increased usage. It changes pace only: model, reasoning, scope, tests, independent verification, and safety gates stay the same.

**Build one** remains the default; silence means build one. Standard pace remains the default; silence never spends extra usage on fast mode. **Build all** scopes to the current feature's AFK slices only — never across features.

### Pace scope

- **Run-scoped, not project-scoped.** A `fast` choice lasts through the selected Build run, its ordinary returned-fix cycles, and the fresh Verify run that completes that handoff. It clears when control returns to the human and never becomes the next session's default.
- **Waiting is the intent signal.** Explicit `fast`, “I'm waiting”, “quickly”, or “ASAP” selects fast pace. Background or unattended work stays standard unless the human explicitly says otherwise.
- **Capability, not a promise.** Enable fast mode only when the active Codex/host route reports it available. If it is unavailable, say so and offer standard pace or `not now`; never silently change model or reasoning to imitate speed.
- **Wall-clock honesty.** The 1.5× claim applies to Codex generation, not tests, builds, browsers, deployments, or network waits. Report observed end-to-end time rather than promising a 1.5× faster feature.
- **Handoff continuity.** Include `pace: fast` in compact Build/fix/Verify handoffs so fresh workers preserve the run choice. Historical route records may retain the pace used as evidence, but it is not a durable default.

### The back-to-back loop's contract

The loop is the first bounded instance of the autonomous loop track, and it inherits the playbook's guard-rails rather than relaxing them:

- **Declare before running.** State the retry/no-progress guards, inherited progress checkpoints and any explicitly selected hard time, cost, iteration or dispatch limits at loop start. A human-selected hard limit overrides a file estimate. Protected delivery and live qualification retain their own mandatory approved ceilings.
- **AFK slices only.** An `HITL` slice pauses the loop for the human; so does a UI slice whose preview gate (diagram/mockup approval) has not been passed — the loop never bulldozes a human-approval gate.
- **Generator ≠ checker, per slice.** Every slice still gets its independent review/QA (stage 08's verifier); the loop continues only while slices pass their gates.
- **Bounded automatic remediation.** Continue without asking when the verifier supplies concrete evidence, the necessary returned fix is inside approved scope, reversible, and does not decide product/taste, security, cost, credentials, external effects, or a close trade-off. Frame it as a fresh fix task carrying the finding and evidence, then send it to fresh independent verification. Count the same failure signature across fix tasks and handoffs. This authority lasts through the selected build-one, build-all or build-to endpoint.
- **Pause conditions.** Pause at HITL, ambiguous evidence, scope expansion, destructive/security/product decisions, Stop, three occurrences of the same failure, three no-progress iterations, an explicitly selected hard limit, an actual host/provider quota, or completion. Every ceiling pause uses the four-part §11 stop report and offers **fix and continue** when human direction can make the fix eligible, **skip slice**, or **stop**. An inherited time checkpoint reports evidence, remaining work and a revised estimate while progress continues; it is not an extension-approval boundary.
- **Capture skills at the boundary where they're discovered (V0.3.19).** When a slice inside the loop discovers a reusable technique — a debugging approach, a stack quirk, a test-setup trick — record it as a one-paragraph **loop note** in `planning/{feature-slug}/loop-notes.md` before continuing, and read the notes at the start of each later slice in the same run, so slice 5 doesn't re-derive what slice 2 learned. The retro decides durable promotion (§40); loop notes die with the planning folder if not promoted.
- **Between passing slices, do not prompt** — report one line per slice (name, gates passed, commit hash) and continue.
- **Mandatory final review, framed as gap-finding (V0.3.19).** After the last slice, run one independent review across the whole set with two lenses: cross-slice concerns (shared state, migrations in sequence, UI consistency), and a **gap-finding pass** — diff what was built against the spec and slice contracts, and list anything that was asked for but has no code or test evidence. Then hand control back to the human with the ship options from stage 10.

The loop always ends at a human decision. It is throughput control, not an autonomy upgrade.

### Productive work and failure budgets

Ordinary issue builds continue through their selected endpoint under the
authority above.

Estimate productive-work capacity from the declared verification plan instead of using one blunt tiny turn counter; browser-heavy UI work commonly needs about 60 calls as a starting baseline. Plan verification capacity (often the final 20% of an estimate) for tests, independent verification, diff review, commit and handoff. With no selected hard cap, an inherited verification reserve does not halt productive work while the diff or evidence materially changes. Failure guards remain hard and cumulative: stop after three identical failure signatures or three no-progress iterations. An explicitly selected deadline, cost or dispatch cap and an actual host/provider quota also stop the run.

An approved `interim-run` coordinator is a deliberately narrow exception: when
its immutable approval explicitly says `hard_limits: none`, a forecast is not a
deadline, dispatch cap, reserve cutoff, or fake infinity budget. Its explicit
stop, three-failure, and three-no-progress rules still bind. This interim
exception does not change ordinary stage-07 authority or protected limits.
S1 is checkpoint-only and dispatch-unavailable; later interim slices, not this
exception, must qualify any worker execution support.

For the approved `interim-run` S3 repair policy only, the ordinary automatic
remediation wording is further narrowed: initial Build/fresh Verify establishes
findings without spending a repair cycle; each eligible reversible in-scope repair
and its fresh Verify is one cycle; no-progress cycles one and two remain eligible
under the same diagnosis and the third stops `stuck`. A productively failing
batch requires a fresh, evidence-only diagnosis with a changed experiment before the next
batch. Forecast revisions follow independently verified worker evidence and never
reset failures, usage, or an explicitly selected cap. This is not an exemption for
ordinary stage-07 loops or protected continuation, and it never permits external
effects, changed requirements, or a final-review blocker to bypass those bounds.

### Classifying failures outside the diff

When a broad test fails outside changed paths, reproduce it once on the feature branch and once at the merge base in an isolated temporary worktree. Continue only when the failure signature is the same at both revisions and all changed-path tests are green; record a separate bug/TODO with the evidence. If the failure prevents reliable assessment of the change, the gate remains blocked.

The completion note should include:

- The slice name and whether it is complete.
- The important files or docs changed.
- The verification commands that passed or could not be run.
- The commit hash for the completed slice.
- The next slice name from the active slice breakdown, if one exists.

## When a slice crosses a boundary (V0.2.8)

If the slice touches a boundary with a sibling app or an external API, the slice's tests include a **contract test**, not just unit coverage:

- **Consumer side:** pin the exact expectations this code has of the other party — request shape, response shape, error envelope — as executable assertions, not comments.
- **Provider side (when both sides are owned):** verify the provider against the consumer's pinned expectations before the slice is called done.
- **External APIs you don't own:** the contract test runs against a recorded/stubbed response *plus* one explicitly-marked live smoke that can be excluded in CI — drift is then a named test failure, not a production surprise.

The contract-test rung sits between unit tests and browser QA on the verification ladder (`../00-foundations.md` §4).

## When a slice is wrong-sized

If you reach the third TDD cycle of a single slice and the test list keeps growing, the slice is too big. Stop, return to stage 04, and re-slice.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

After each slice ships:

```yaml
counters:
  slices_shipped_total: +1
  slices_since_last_architecture_review: +1
  slices_open: -1
active_features:
  - slug: {feature-slug}
    status: in-flight       # in-flight from the first slice onward (idempotent — set it if not already set)
```

When the feature's `slices_open` reaches 0, set its status to `ready-to-ship` — that is what routes /whats-next to the ship menu.

---

## Next

- Slice green → open `08-review.md`
- Blocked by a bug → open `11-debug.md`
- Codebase resisting the change → open `06-architecture.md`
- Unsure → run `/whats-next`

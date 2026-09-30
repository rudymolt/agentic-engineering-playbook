# 93 · Model routing track

> Optional, stage-aware model choice for agent chat. OpenAI remains the daily-driver default; verified alternatives are available through `models`, including runner routes available in Conductor.

## Invocation ownership

The coordinator invokes `/model-router` at a feature-lane boundary. The human owns the typed choice. Model routing changes who performs a settled stage; it never skips alignment, build scope, verification approval, or another human gate.

The canonical interface is plain text. Buttons may mirror the options, but the workflow must work in a chat box with typed replies alone.

## Lanes and defaults

The table contains edition seeds, not project overrides. For every new choice,
use the shared [configuration reader](scripts/playbook-config.md): explicit
approved feature choice > adopted `.playbook-config.json` > legacy state
default > edition. Show model, runner, reasoning and origin. Malformed adoption
blocks instead of falling back. `/ai-playbook-configure` edits all four project
role defaults in S2 through typed preview/Apply, without launching anything.
Guided/expert presentation is local; Coordinator is display-only. Configuration
does not grant route selection, execution approval or verification authority.
Active selections, retries and immutable mission approvals never re-resolve
when defaults change. QA inherits the selected Verify route.

| User-facing lane | Stages | OpenAI default | Reasoning | Reused for |
|---|---|---|---|---|
| Plan | 01–06 | `gpt-6.1-sol` | high | planning retries |
| Build | 07 and returned fixes | `gpt-6.1-sol` | medium | implementation fix cycles |
| Verify | 08–09 | `gpt-6.1-sol` | high | one fresh verification run |

Use **Plan**, **Build**, and **Verify** in prompts. Planning, implementation, and verification are internal state names.

At Plan, `openai defaults` applies GPT-6.1 Sol/high → GPT-6.1 Sol/medium → GPT-6.1 Sol/high to this feature. It suppresses later model-selection questions, not the Build or Verify action gate. Rediscover each default before launch; stop instead of substituting when it is unavailable. Existing feature selections and historical run records retain the models that were actually approved and used; this table governs new lane selections.

## Default escalated repair within an approved unattended run

Plan records an explicit escalation policy in the immutable run approval. The
playbook default is GPT-6 Astra/high after **three cumulative unsuccessful
ordinary repairs on one slice**, with authority to investigate the cause and
implement an in-scope prerequisite, new hypothesis or fix in **two reserved
escalated cycles per slice**. Plan may override the route, trigger or finite bounded allowance
before approval; a legacy approval without this policy grants no escalation.
The initial Build and expected diagnostic failures do not count as ordinary
repair failures. A new diagnosis batch, worker, restart or model does not reset
the ordinary history or reserved slots.

The first Astra worker both diagnoses and may implement within the first
reserved slot. Its compact handoff carries observations, failed hypotheses,
likely cause, and the next discriminating experiment, without a prior worker's
reasoning transcript. The host checks model availability and the exact idle
session's resolved model, effort, workspace and empty conversation before final
send admission. An ambiguous read reconciles the same durable session ID;
confirmed mismatch stops with a concrete decision report. No concurrent
builder or silent substitute is admitted.

Every candidate receives fresh GPT-6.1 Sol/high Verify of its exact SHA, with no
Astra transcript. A failing verdict closes the cycle while retaining progress.
An unusable verifier result is reconciled and may receive at most two further
fresh verifier dispatches for that SHA; those dispatches incur their own usage
and never consume another Astra implementation slot. After acceptance, the next
slice returns to its originally approved Build route. Record the reason, route,
observable extra usage and time, Verify outcome and human interruptions;
unavailable host metrics remain unavailable.

## Verify runner preference

Verify prefers a runner other than the Build runner that actually ran. The preference is relative to the Build runner that actually ran, never to the default lane table: if Build ran on `claude-code`, Verify prefers a runner other than `claude-code`, regardless of what the table's default lane names.

The Build lane's coverage of stage 07 and returned fixes carries the preference: a returned fix that ran on runner X means the fresh Verify that follows prefers a runner other than X.

A project with one available runner reads this same rule and is not interrupted: with no second runner to prefer, Verify needs no different runner and continues on the lane's usual runner, recording `cross_runner: false` with `cross_runner_reason: single_runner_project`.

Worked example: Build actually ran on `claude-code`. The Verify prompt that follows prefers a runner other than `claude-code` — for example `codex` — ahead of offering `claude-code` itself.

When no different runner is reachable, Verify proceeds on an available runner and records the fallback: the preference never stops the run by itself, and it never substitutes a runner silently.

Worked fallback example: a project configures only `claude-code`. Verify has no alternate runner to prefer, so it proceeds on `claude-code` and records `cross_runner: false` with `cross_runner_reason: single_runner_project`.

## Codex pace overlay

Pace is orthogonal to lane, model, runner, reasoning, permissions, scope, and verification. Standard pace is the default. At the Build action, the human may append `fast` (for example, `build all fast`) when they are waiting and value lower latency; supported Codex routes currently describe fast mode as 1.5× generation speed with increased usage.

- A fast selection is run-scoped: it covers the selected Build work, ordinary returned-fix cycles, and the fresh Verify run that completes that handoff, then clears when control returns to the human.
- “I'm waiting”, “quickly”, and “ASAP” are equivalent intent signals. Background/unattended work stays standard unless the human explicitly requests fast.
- Carry `pace: standard | fast` in route launches and compact handoffs. Persist it on the historical lane record as evidence of what ran, never as the next session's default.
- Discover fast-mode availability from the active Codex/host route. If unavailable, offer standard pace or `not now`; never substitute another model, reasoning level, permission mode, or weaker verification.
- Keep quality gates identical. Fast mode accelerates model generation, not builds, tests, browsers, deployments, or network waits, so report observed end-to-end time without promising a 1.5× faster feature.

## Chat prompt contract

At every lane boundary:

1. Name the feature with its human title.
2. Lead with friendly model label and action; show model ID, runner, reasoning, and exact launch consequence as secondary detail.
3. Say how long the choice lasts and when the next model question occurs.
4. Show no more than four typed options.
5. Let the normal lane action accept the resolved preference and display its origin. Edition OpenAI defaults apply only without a higher-precedence choice or as an explicit feature override.
6. Put alternatives behind `models`; show up to three verified models plus `more`, numbered from 1.
7. Offer `not now` when pausing would otherwise be ambiguous. It starts nothing and records nothing.
8. After all stage inputs are known, start without another confirmation.

Every route says exactly one of:

- `uses this tab`
- `launches {runner} as a sidecar; this chat remains the coordinator`
- `choose {runner} in Conductor; opens a new tab`

The exact text shapes, conflict prompts, and recovery prompts live in [`skills/model-router/references/chat-prompts.md`](skills/model-router/references/chat-prompts.md).

## Model discovery

Display only routes verified through a host/provider catalog, CLI listing, or successful validation. Normalize:

```text
{model_id, label, provider, runner, reasoning, launch_mode,
 permission_strength, handoff_delivery, fast_mode}
```

Do not persist the volatile full catalog. Validate availability at each lane gate. Never invent pricing or quality claims. Reasoning-effort labels are provider-scoped: discover and sweep them within one provider, and record each label exactly as the provider names it — a label is never translated into another provider's scale.

Compare the current chat's complete route identity with the effective preference: model, provider, runner, reasoning, permission strength, launch mode, and handoff delivery. Pace is compared separately because it is a run preference, not model identity. A route difference triggers the lane conflict prompt. Observing a route does not select it; persist it only after the human types the lane-specific `here` or `current` action.

## State contract

V0.3.33 uses `.playbook-state.yml` schema 3.

`model_routing` records gated policy, legacy lane defaults and allowed runners.
After adoption, `.playbook-config.json` is the sole project-default source;
legacy defaults remain inert history. Policy/allowed-runner constraints retain
authority. `pending_model_routes[]` holds a Plan choice made before stage 01
proves one normal feature exists. `active_features[].routing` holds promoted
per-lane selections. `active_wayfinding_maps[].model_route_id` may link a map
to its planning route.

Each selection records the route fields below. Build and Verify selections also record the pace used; Plan may omit pace because the fast overlay begins at the Build action:

- model ID and friendly label;
- provider, runner, and reasoning, with thinking state where the route's provider exposes a thinking control;
- selection source and prompt policy;
- launch mode, permission strength, and handoff delivery;
- pace used for the run (`standard` or `fast`) without treating it as a durable default;
- selection time;
- requested/runtime-reported identity evidence, evidence kind, and verification time;
- for Verify selections only: `cross_runner` (`true` or `false`) and, whenever `cross_runner` is
  `false`, `cross_runner_reason` from a closed set — `single_runner_project`, `preferred_runner_unavailable`,
  or `human_override` — `null` when `cross_runner` is `true`.

The generated `status.pending_plan_routes` counts resumable `selected`, `running`, `waiting_manual`, and `blocked` pending routes. `linked_wayfinder` does not count because re-entry belongs to `/wayfinder`, not the original planner.

## Pre-feature Plan and promotion

The first Plan choice may occur before alignment discovers whether the request is one feature, several features, a Wayfinder map, a one-liner, or no build. Therefore:

- Complete Plan start actions create or reuse one pending route before launch.
- `models`, `more`, `back`, and `not now` write nothing.
- Pending Plan does not create `planning/{slug}/`, add `active_features[]`, or increment `features_in_alignment`.
- A manual new-tab route writes `.playbook-routing/{route-id}/planning.md`; this local handoff directory is gitignored.
- Requested identity is `pending` before launch. Only a verified exact match may promote.

Stage 01 resolves the route once:

- **One normal feature:** create the feature folder and active entry, increment alignment once, move the verified selection under feature routing, then remove the pending route and handoff.
- **Wayfinder:** mark the route `linked_wayfinder`, attach its ID to the map, and create no feature. `/whats-next` returns `/wayfinder {locator}` with model/runner policy.
- **Wayfinder graduates to one feature:** promote the route into that feature and remove the pending entry.
- **Wayfinder graduates to several features:** ask whether to reuse the route or choose per feature; persist an explicit choice on every feature.
- **No build, abandonment, or indefinite deferral:** close/remove the route and handoff; create no feature.
- **One-liner redirect:** close/remove the route and return the work to the coordinator under stage 07's trivial-change path without slice routing.

Every transition updates `last_updated`, recomputes `status:`, and refreshes `planning/STATUS.md` when its visible pointers change.

## Re-entry

`/whats-next` reads `pending_model_routes[]` on the one-file fast path. A resumable pending Plan route is already-started work and ranks before a new feature or unrelated open Wayfinder map. Its recommendation names the saved model/runner and exact action:

- current tab: resume in this chat;
- sidecar: resume or relaunch the named runner;
- manual Conductor route: open the saved handoff in the named harness/model tab.

Mirror pending routes under `planning/STATUS.md → Pending Plan routes`. This is a pointer, not a feature folder. Clear both pointers when the route promotes or closes.

## Handoff and independence

Pass artifacts, not reasoning transcripts. Every Build/fix/Verify handoff also carries the active run pace so a fresh worker does not silently drop or invent fast mode. When it crosses a session, worker, or host, use the conditional [pickup brief](10-process/pickup-brief.md) as the bounded envelope; it records the one next action and portable evidence but never replaces this route's authoritative worker metadata or fresh-context rule:

- Planner receives request, repository facts, current planning artifacts, and human answers; returns questions, spec, decisions, and slices.
- Builder receives approved spec, slices, constraints, test seams, and repository state.
- Verifier receives goal, criteria, diff/commit range, tests, commands, and relevant docs. It never receives builder chat.

Plan, Build, and Verify run sequentially. Verify always starts fresh. Claim enforced read-only or fast pace only when the runner or host proves it.

## Host adapters

Conductor is a workspace/coordinator above Codex, Claude Code, Cursor, OpenCode, and provider CLIs. Tabs share files and branch state, but each tab has one harness/model. Prefer automatic identity-verifiable sidecars. Use an explicit handoff and model-picker instruction when no automatic route exists.

The runtime rules for each adapter live in [`skills/model-router/references/host-adapters.md`](skills/model-router/references/host-adapters.md).

## Identity evidence

Verify the route from the runtime boundary, not from generated prose. Preferred evidence, in order:

1. provider response metadata naming the served model;
2. runner session/thread metadata correlated to the launched run;
3. host-reported model selection tied to that session.

For current Codex CLI sidecars, capture `thread.started.thread_id` and confirm the matching persisted thread's `model` field. A model's answer to “what model are you?” is generated content and is never authoritative identity evidence. If no authoritative surface exists, mark the route identity-unverifiable and stop rather than accepting a self-report.

### Authoritative worker-result envelope

Every Plan, Build, fix, and Verify worker result returns immutable runtime metadata alongside its artifact or verdict:

```yaml
runtime:
  model_id: {provider-reported model}
  reasoning_effort: {runtime-reported effort}
  thinking: {enabled | disabled, from the enforced runtime configuration}
  thread_id: {runner/session identifier}
  runner: {codex | claude-code | cursor | opencode | provider CLI}
  permission_mode: {enforced mode reported by host/runner}
  tool_calls_used: {integer}
  tool_calls_remaining: {integer or null when unavailable}
  wall_time_used_seconds: {integer}
  wall_time_remaining_seconds: {integer or null when unavailable}
```

`thinking` states whether extended thinking was enabled for the run, taken from the enforced runtime configuration (a CLI or API thinking control), never from the presence or absence of thinking in output. It guards a silent-corruption mode: with thinking disabled, a model can write a tool call into visible text instead of emitting a structured call — the call never runs, and the leaked text persists in later turns. Reject a worker artifact containing unexecuted tool-call text as corrupted; the recorded thinking state is the first triage fact, and repair is never attempted on the corrupted result.

The coordinator compares the envelope with the selected route and declared budgets before accepting the result. A model, effort, thinking-state, runner, thread correlation, or permission mismatch rejects the output automatically. Missing authoritative fields are `unavailable`, never inferred from worker prose; required-but-unavailable identity or permission evidence blocks the route. Usage fields may be unavailable only when the host exposes no counter, in which case the declared external ceiling remains authoritative.

## Failure behavior

Lead with the outcome: nothing started, or the run stopped and output was rejected. Name the verified cause and offer at most three recovery actions.

- Discovery failure: show other verified routes; if none, say `No models are ready. Nothing has started.` and offer setup, retry, or cancel.
- Default unavailable: show a replacement only as an explicit choice alongside `models` and `retry`.
- Never substitute an unavailable model silently.
- Identity mismatch: reject output; show requested and runtime-reported model IDs plus the evidence kind; offer retry, `models`, or details.
- Weak Plan/Verify boundary: offer a safer enforced route, explicit acceptance, or cancel.
- Mid-run change: stop, preserve artifacts/worktree, and ask whether to restart fresh. Never hot-swap.
- Blocked Build: preserve its worktree and return a structured blocker. Never switch model automatically.

## Verification

Test prompt snapshots, route discovery filtering, the worker-result envelope, thinking-state recording, authoritative identity evidence, effort/thinking/runner/permission mismatch rejection, self-report rejection, current-chat conflicts, fast-mode capability/fallback, standard/fast handoff continuity, run-scope clearing, state promotion/closure, Wayfinder linkage, pending-route re-entry, retries, handoff paths, and each host adapter's launch consequence. Run the canonical playbook suite:

```bash
python3 v0.5/scripts/verify-playbook.py
```

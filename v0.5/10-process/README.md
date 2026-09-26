# 10 · Process map

> The 13 stages of the AI-engineering loop. Read in order on first pass; cite a single stage from `/whats-next` or from the ambient nudge thereafter.

---

## The loop at a glance

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Per-session                                                             │
│  00 Prereqs ──► (any other stage)                                        │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│  Per-feature                                                             │
│                                                                          │
│   01 Align  ─►  02 Context  ─►  03 Spec  ─►  04 Breakdown  ─►  05 Triage  │
│                                                                          │
│      │                                                                   │
│      ▼                                                                   │
│   06 Architecture ◄─── (cadence: nudge at 3 slices)                      │
│      │                                                                   │
│      ▼                                                                   │
│   07 Implementation (TDD) ──► 08 Review ──► 09 QA ──► 10 Ship            │
│      ▲                                                                   │
│      │                                                                   │
│      └─ 11 Debug (whenever something breaks)                             │
│                                                                          │
│   12 Retro & learn (cadence: weekly, and after every shipped feature)    │
└──────────────────────────────────────────────────────────────────────────┘
```

Optional pre-spec branch: `01 Align ─► 92 Wayfinder ─► 01/02 graduation ─► 03 Spec`. Wayfinder is user-invoked and appears only when the destination is nameable but the route remains multi-session and foggy; see [`../92-wayfinder-track.md`](../92-wayfinder-track.md).

Optional model-routing overlay: [`../93-model-routing-track.md`](../93-model-routing-track.md) wraps the Plan (01–06), Build (07), and Verify (08–09) boundaries with text-only model prompts. OpenAI defaults remain one typed action away; `models` reveals verified Conductor or provider alternatives without changing the 13-stage loop.

## Terminal result contract

Every stage or skill that finishes, blocks, or hands control elsewhere appends a machine-readable result. Human prose may precede it, but the coordinator routes from this block before suggesting work:

```yaml
playbook_result:
  outcome: complete       # complete | blocked | handoff
  next_stage: 08-review   # stage id, /whats-next, or null when genuinely terminal
  required_actions: []    # ordered closeout/gate actions that must precede unrelated work
```

After any state-writing terminal result, recompute `.playbook-state.yml → status` automatically, then reconcile `next_stage` with pending closeouts, pending Plan routes, and active feature state. A required action or higher-ranked state item wins over prose suggestions. In particular, production verification returns doc-close then retro; it never routes directly to Wayfinder or a new feature.

---

## Stage index

| # | File | When to invoke | Primary skills | Invocation owner |
|---|---|---|---|---|
| 00 | `00-prereqs.md` | Every session, first thing | Capability profile; Matt/gstack skills are accelerators with named manual routes | **Model** — automatic session gate |
| 01 | `01-align.md` | Any change larger than a one-liner | `/office-hours`, `/plan-ceo-review`, `/grill-with-docs`, `/prototype` when a concrete UI/logic question blocks alignment | **Model** may route; human owns labelled decisions |
| 02 | `02-context-and-adrs.md` | Side-effect of stage 01 | `/domain-modeling` (invoked inline by `/grill-with-docs`) | **Model** — inline consequence of alignment |
| 03 | `03-spec.md` | After alignment is settled | `/plan-eng-review`, `/plan-design-review`, `/to-spec` (formerly `/to-prd`), `/research` (open factual questions) | **Model** may route after alignment |
| 04 | `04-breakdown.md` | After spec | `/to-tickets` (formerly `/to-issues`) | **Model** may route after approved spec |
| 05 | `05-triage.md` | When a new issue lands, or when asked "what should I work on?" | `/triage` | **Model** may route from request or tracker event |
| 06 | `06-architecture.md` | Nudges at 3 shipped slices, insists at 6; or any time the codebase feels heavy | `/improve-codebase-architecture`, `/codex` (optional second opinion) | **Model** may nudge or route; human selects expansions |
| 07 | `07-implementation-tdd.md` | Any non-trivial feature or bug fix | `/tdd` (or `/implement` as the per-ticket wrapper) | **Model** may route within accepted scope |
| 08 | `08-review.md` | Before every PR | manual standards/spec axes; `/ai-playbook-design-review`; manual/compatible role passes | **Model** — required verification gate |
| 09 | `09-qa.md` | After implementation, before ship | report-only browser/device pass; compatible `/qa-only` optional | **Model** — required verification gate |
| 10 | `10-ship-and-deploy.md` | When a feature is ready to land | `/ship`, `/land-and-deploy`, `/canary`, `/benchmark` | **Human intent** starts external mutation; model may run read-only readiness checks |
| 11 | `11-debug.md` | Any non-trivial bug or regression | `/diagnosing-bugs`, `/investigate`, `/browse`, `/codex` | **Model** may route from a reported failure |
| 12 | `12-retro-and-learn.md` | Weekly, and after every shipped feature | `/retro`, `/learn`, `/document-release` | **Model** may nudge or route from cadence |

---

## Routing rules

When the user asks for something, route as follows. These are also the rules baked into `/whats-next`.

| User says… | Route to… |
|---|---|
| *"build / add / create [feature]"* | 01 Align |
| *"fix / debug [thing]"* | 11 Debug |
| *"ship / deploy"* | 10 Ship |
| *"what should I work on?"* | 05 Triage (or `/whats-next` if no tracker is set up) |
| *"the codebase feels messy / heavy"* | 06 Architecture |
| *"is this safe to merge?"* | 08 Review |
| *"how did this week go?"* | 12 Retro |
| *Anything ambiguous* | `/whats-next` |

### Optional tracks

| Track | Use when | Invocation owner |
|---|---|---|
| [`90-loop-track.md`](../90-loop-track.md) | Already-specified AFK slices should run back-to-back under earned ceilings | Human opt-in |
| [`91-delegation-track.md`](../91-delegation-track.md) | An anchored multi-phase plan needs separate implementation and verification | Human orchestration |
| [`92-wayfinder-track.md`](../92-wayfinder-track.md) | A named destination still has a coupled, multi-session decision frontier before spec | **Human invocation**; model may offer only |
| [`93-model-routing-track.md`](../93-model-routing-track.md) | Plan, Build, or Verify should use a verified model/runner route while keeping OpenAI defaults | Model presents the lane prompt; human types the route/action |

---

## Skill invocation ownership

Invocation is metadata, not authority:

- **Model-invoked** skills keep a trigger description and may be selected from natural language or by another skill.
- **User-invoked** skills set both Claude's `disable-model-invocation: true` and Codex's
  `agents/openai.yaml → policy.allow_implicit_invocation: false`; only the human typing the
  harness-native skill name (Claude Code's slash form or Codex's `$name` form) can start them.

Model-invoked skills omit both disabling controls. Codex picker metadata under
`agents/openai.yaml → interface` improves discovery but does not grant authority.

A model-invoked skill still obeys the user's scope and its own approval gates. The local contract and classifications live in [`../skills/README.md`](../skills/README.md); `check-skill-metadata.py` keeps metadata aligned with that table.

The stage table classifies autonomy at the process boundary, including upstream skills whose package metadata this repository does not own. **Human intent** means the stage cannot infer authority to push, merge, deploy, publish, or otherwise mutate external systems.

---

## What this map deliberately doesn't enforce

- **A fixed cadence between stages.** Cadences live in `playbook-cadences.yml` and are tuned per project.
- **A specific ticket tracker.** `/setup-matt-pocock-skills` interviews the user about that — Linear, GitHub Issues, etc. — and writes the answer to `docs/agents/issue-tracker.md`.
- **A specific stack.** The stages are stack-agnostic; the worked examples in `references/sample-athletics-ui/` happen to be TS / React / Express / SQLite.
- **The order within a sprint.** Multiple features can be in flight at different stages; the loop is per-feature, not per-sprint.

---
name: ai-playbook-why
description: Explain a current decision's historical motivation from bounded, cited evidence while separating direct facts, inference, contradictions, and unknowns.
---

# Evidence-based why

## Purpose

Answer a concrete “why is this here?” question without turning plausible code
reading into claimed intent. This skill investigates; it does not change the
repository, create tracker work, start a model panel, or enact a recommendation.

## Procedure

### Step 1 — Anchor one bounded question

Name the current file, symbol, behavior, or decision whose motivation is in
question. Read the immediate code and relevant current documentation, then set
a small source boundary: the applicable local ticket, ADR/decision, targeted
git history, and an authorized connector only when it is available and useful.
Simple questions stay local. For bulky independent evidence gathering, use
bounded read-only delegation when available, inspect returned locators yourself,
and use a serial fallback when it is not.

Completion criterion: the question, code/document anchor, source boundary, and
any delegated or serial investigation route are visible before searching history.

### Step 2 — Gather inspectable evidence and qualify each search

Read the selected local Markdown tickets and decisions alongside relevant git
history; cite each result with a stable path, symbol/line locator where useful,
or commit. Query an authorized tracker/connector only when it is actually
available. Record a query that ran and found nothing as **searched-empty**;
record inaccessible, unauthenticated, unavailable, or deliberately unqueried
material as **tracker-unavailable** or **unsearched**, with the reason. These
states are not interchangeable.

Completion criterion: every consulted source has a locator and every omitted
source is honestly qualified as searched-empty, tracker-unavailable, or
unsearched.

### Step 3 — Separate what the evidence supports

Write the explanation in four labeled parts:

- **Direct evidence** — what a cited ticket, ADR, commit, review, or other
  source expressly says.
- **Inference** — a plausible conclusion drawn from cited facts, with the
  reasoning and confidence; code may support behavior but source alone does not
  establish original intent.
- **Contradiction** — sources that disagree, including the exact conflict rather
  than silently choosing a preferred story.
- **Unknown** — motivation, context, or history that the available evidence
  cannot establish.

If a change follows, return only **Preserve / Change / Avoid / Risk** constraints
and cite the evidence behind each one. Do not enact a change or present inferred
intent as a settled decision.

Completion criterion: the result distinguishes evidence, inference,
contradictions, and unknowns, and any constraints remain advisory and cited.

## Terminal result

On every exit, including an early stop, append a YAML `playbook_result` containing
`outcome`, `next_stage`, and an ordered `required_actions` list. Choose the row
that matches the result:

| Result | outcome | next_stage | required_actions |
|---|---|---|---|
| Standalone bounded explanation delivered, with evidence limits explicit | `complete` | `null` | `[]` |
| Bounded explanation delivered to an invoking stage | `handoff` | Actual invoking stage id | Consume the findings and continue that stage's remaining work |
| Target cannot be bounded or an essential prerequisite prevents the requested investigation | `blocked` | Invoking stage id, or `/whats-next` when standalone | Name the missing target/access/evidence and the action needed to resume |

A supported "unknown" and an unavailable optional source can be a completed
qualified answer. Missing history does not establish intent. `complete`
refers only to this explanation; it cannot complete the caller's review or ship
gate. Emit a concrete stage id, never the words "invoking stage". Carry any
already-required caller actions forward; this report does not write state.

## Guardrails

- Local tickets and decisions count as evidence; missing tracker access does not
  block a useful, qualified explanation.
- Never invent history, author intent, callers, tests, or connector results.
- Keep exploration bounded; no mandatory source fan-out, telemetry search,
  automatic multi-model critique, external communication, or repository mutation
  is implied.

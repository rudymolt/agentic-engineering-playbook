---
name: ai-playbook-how
description: Explain a bounded subsystem's current input-to-result behavior with cited locations and an explicit distinction between source reading and executed runtime evidence.
---

# Evidence-based how

## Purpose

Explain how a current subsystem behaves without claiming execution that did not
happen. This is a bounded read-only investigation; it does not mutate the
repository, create tracker work, start a model panel, or manufacture tests.

## Procedure

### Step 1 — Bound the behavior question

Name one input or trigger, the observable result to explain, and the relevant
entry point. Read the smallest current source and documentation surface that can
trace that path. Keep simple questions local. For bulky independent exploration,
use bounded read-only delegation only when available and useful, inspect its
locators before synthesis, and use a serial fallback otherwise.

Completion criterion: the question identifies an input or trigger, expected
observable result, entry point, source boundary, and investigation route.

### Step 2 — Trace the current path

Trace the input or trigger through the key concepts, locations, decisions,
outputs, and observable result. Cite files and symbols, distinguish confirmed
branches from uninspected branches, and state external boundaries, preconditions,
and limitations. If relevant documentation or tests are absent, say so instead
of inferring their existence.

Completion criterion: a reader can follow the cited input-to-result path and
see the concepts, locations, boundaries, and limitations that matter.

### Step 3 — State the evidence level

Use a **Source-read qualification** whenever behavior is derived from source
reading: describe it as a code-path interpretation, not proof that a runtime
executed. Separately label any executed runtime evidence with the revision,
command or trigger, observed result, and remaining limits. Do not upgrade source
reading into executed runtime evidence, and do not claim a caller, history, or
test that the evidence does not show.

Completion criterion: every behavioral claim says whether it is source-read or
executed runtime evidence, with locators and limits sufficient to check it.

## Terminal result

On every exit, including an early stop, append a YAML `playbook_result` containing
`outcome`, `next_stage`, and an ordered `required_actions` list. Choose the row
that matches the result:

| Result | outcome | next_stage | required_actions |
|---|---|---|---|
| Standalone bounded explanation delivered, with evidence limits explicit | `complete` | `null` | `[]` |
| Bounded explanation delivered to an invoking stage | `handoff` | Actual invoking stage id | Consume the findings and continue that stage's remaining work |
| Target cannot be bounded or an essential prerequisite prevents the requested investigation | `blocked` | Invoking stage id, or `/whats-next` when standalone | Name the missing target/access/evidence and the action needed to resume |

A source-read explanation can be complete with runtime evidence explicitly
unavailable. This does not establish that the runtime behavior passed a test. `complete`
refers only to this explanation; it cannot complete the caller's review or ship
gate. Emit a concrete stage id, never the words "invoking stage". Carry any
already-required caller actions forward; this report does not write state.

## Guardrails

- This skill does not invent callers, history, or tests.
- Missing tracker access, tests, or runtime access narrows the result; it does
  not justify an unqualified claim.
- No mandatory source fan-out, telemetry search, external communication,
  automatic multi-model critique, or repository mutation is implied.

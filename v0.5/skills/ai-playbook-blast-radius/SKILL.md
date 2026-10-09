---
name: ai-playbook-blast-radius
description: Establish executable evidence for the material safety assumptions of a concrete revision without turning local proof into a general safety claim.
---

# Evidence-based blast radius

## Purpose

Assess a concrete revision or diff by finding the material assumptions on which
its safety depends. A convincing writeup is not proof: record executable
evidence from the affected code, or leave the assumption visibly unproven for
the stage owner to assess.

## Procedure

### Step 1 — Bound the revision and its material assumptions

Read the fixed revision or diff, its changed symbols, relevant callers,
serialized boundaries, dependencies, flags, ordering, and cleanup. Identify
each assumption whose failure could make the change unsafe; do not hide several
failure paths behind one reassuring statement. For every assumption, record the
assertion, cited source or boundary, failure path, consequence, confidence, and
the cheapest evidence level reached: assertion, source-cited,
failure-path analysis, real-code execution, or running-application
reproduction.

Completion criterion: the review result has a bounded revision and a complete,
checkable list of material assumptions, including their failure paths and
evidence levels.

### Step 2 — Execute the load-bearing checks

For every material assumption that can affect acceptance, run the affected
production code at the recorded revision. Preserve the exact command, tested
code or symbol, expected result when the assumption is true, expected failure
when it is false, actual result, and artifact locator where applicable. A test
or script that reimplements an equivalent-looking behavior, mocks away the
affected path, or only checks prose is not real-code execution; label it
stub-only and leave the assumption unproven. Retain counterexamples as defects
rather than folding them into a cleared-risk summary.

Completion criterion: each cleared material assumption has real-code execution
or running-application evidence with an observable supported and failure case,
and every lower-evidence assumption remains explicitly unproven.

### Step 3 — Return a qualified review result

Report the changed behavior, assumptions and confidence, counterexamples,
cleared risks with concise reasons, executable evidence, unproven assumptions,
and remaining limits. State that a local proof covers only its tested revision,
inputs, and environment; it does not establish consumer, deployment, or global
safety. An assumption essential to acceptance blocks acceptance until proved.
For a missing proof helper, a report-only verifier requests a separate scoped
write task instead of editing product code.

Completion criterion: the existing stage-08 result makes each acceptance block,
unproven risk, counterexample, and limit visible to its stage owner.

## Terminal result

On every exit, including an early stop, append a YAML `playbook_result` containing
`outcome`, `next_stage`, and an ordered `required_actions` list. Choose the row
that matches the result:

| Result | outcome | next_stage | required_actions |
|---|---|---|---|
| Scoped review evidence delivered with no acceptance-blocking finding | `handoff` | `08-review` | Consume the bounded evidence and finish remaining stage-08 checks |
| Essential assumption unproven, counterexample found, or required proof unavailable | `blocked` | `08-review` | Identify each acceptance block and the scoped proof/remediation plus fresh verification needed |

Retain non-blocking unproven assumptions and limits in the review report. A
finished writeup is never a `complete` merge verdict. The stage owner reconciles
required work; the envelope grants no permission to write a proof helper, change
product code, update state or ship.

## Guardrails

- This procedure informs existing review; it does not replace mandatory tests,
  fresh independent verification, risk classes, or authority gates.
- Read-only verification stays report-only. A scoped remediation or proof helper
  is a separate generator task and returns through fresh verification.
- Source citations and failure-path analysis are useful evidence, but anything
  below real-code execution is unproven.
- Do not require a panel, model change, arena, or unrelated safety work for a
  bounded review.

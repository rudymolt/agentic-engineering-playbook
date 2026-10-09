---
name: ai-playbook-verification-harness
description: Discover, propose, generate, and prove a project-owned verification harness without replacing its existing commands or claiming a real-project pilot.
---

# Verification-harness generator

## Purpose

Create a bounded, project-owned route at `.agents/skills/verify-<app>/` only
after the target application and concrete write scope are known. The output is
draft until a real launch, doctor, drive, evidence, and cleanup execution has
succeeded. Fixture proof is reusable-capability evidence, never PILOT-01 proof.

## Procedure

### Step 1 — Discover one target and its existing controls

Inspect the selected application's source, scripts, test commands, launch path,
readiness signals, interaction tooling, observable effects, evidence destination,
and teardown ownership. Reuse working project commands before proposing a helper.
When candidates are ambiguous, name them and obtain one target selection. Do not
infer credentials, selectors, fixture data, or an absolute host path.

Turn that discovery into exact project-relative executable controls before asking
a fresh verifier to run the route: existing commands, or tested owned helpers,
for required setup, synthetic fixtures/authentication, driving, evidence, and
cleanup. A service name or test-file reference is not an executable control.
Discovery and construction belong to generation or an authorized repair, not to
ordinary fresh execution.

Completion criterion: one project-relative app name, existing controls, ownership
boundaries, and unresolved user-owned choices are recorded.

### Step 2 — Propose before applying

List each exact relative path and content change, environment/preconditions,
commands, fixture data, expected effects, evidence directory, network/logging
effects, and owned cleanup targets. State whether an existing target conflicts or
has changed since discovery. Require explicit approval unless that exact scope was
already approved; reconcile a conflicting or customized harness rather than
replacing it.

Completion criterion: the target, paths, commands, side effects, evidence, and
cleanup scope are reviewable before the first write.

### Step 3 — Generate the owned route

Create the project-owned harness skill with runnable **Launch**, **Doctor**,
**Drive**, **Evidence**, and **Cleanup** sections, plus a feature-map index and one
file per selected stable feature ID. The index names coverage scope and omissions.
Each feature records purpose, entry point, prerequisites, drive instructions,
expected observations/effects, limitations, and last verified revision/evidence.

For a route that needs a long-lived process or browser interaction, make the
lifecycle and interaction adapter executable in the generated route. Wait for an
observable ready state, check driver errors, and retain failure evidence before
teardown. Use controls suited to the target; do not prescribe a project's timing
or tooling to another project.

Doctor checks the intended revision/instance, declared dependencies or auth, and
a writable evidence destination. It returns `0` only for observed readiness, `1`
for command errors, and `2` for blocked prerequisites with corrective guidance.
It never seeds, repairs, resets, or kills resources. A passing doctor is not a
feature pass: readiness is not correctness. Document these stable `0`/`1`/`2`
meanings in the generated route, and disclose Doctor's authorized network
observations, incidental logging, and any evidence-directory/probe writes.
After an unexpected Drive failure, retain the failure evidence, recheck readiness,
and restore known test state before continuing. Cleanup may touch only resources
owned by that run; unknown leftovers require inspection, not blind deletion.
New helpers stay inside the harness directory and have help,
preconditions, stable exits, and corrective errors.

Completion criterion: the route owns only its directory/resources, preserves
existing project commands and customized harness content, and has no secrets or
placeholder selectors.

### Step 4 — Prove and record the route

Run one mapped feature through a real process or CLI: launch, doctor, interaction,
observable result, evidence retention, and failure cleanup. Also show a blocked
readiness case and a separate behavior failure after healthy readiness. Confirm
owned cleanup leaves unrelated resources untouched and evidence remains. Record
tested revision/instance, commands, observations, effects, and artifact locators;
update the selected `capability_routes.real_environment_qa` locator visibly.
Retain uniquely identified success and failure artifacts on repeated runs. Update
the mapped feature's last-verification record on every accepted run; a failed run
keeps its evidence without overwriting prior proof or granting verification credit.
The selected route must resolve to retained generated instructions and run evidence
in the approved repository evidence location, beyond disposable test teardown.

A fresh verifier follows the generated instructions and independently confirms
the retained result. Missing executable steps leave the route draft or blocked;
discovering or repairing them changes the candidate and requires fresh proof.
The verifier does not invent setup, fixture/authentication, driving, evidence, or
cleanup controls during ordinary execution. If execution fails or a route is
unavailable, report draft or blocked; never label generated text as a delivered
harness or a live-project pilot.

Report controlled-fixture execution, instructional review, builder smoke,
independent repair verification, and a full consuming-project pilot as distinct
evidence classes.

The playbook's controlled fixture is exercised with
`python3 v0.5/scripts/test_verification_harness_fixture.py`; it proves the
generator contract without selecting or modifying a consuming project.

Completion criterion: executable evidence proves one mapped journey and its
negative cases, with fixture scope and PILOT-01 limitation explicit.

## Terminal result

On every exit, including an early stop, append a YAML `playbook_result` containing
`outcome`, `next_stage`, and an ordered `required_actions` list. Choose the row
that matches the result:

| Harness result | outcome | next_stage | required_actions |
|---|---|---|---|
| Proved route with the required execution evidence and fresh independent confirmation | `handoff` | Owning stage id, default `09-qa` | Review/adopt the evidenced route and finish that stage's remaining checks |
| Draft route ready for its required independent proof | `handoff` | Owning stage id, default `09-qa` | Run the missing proof and obtain independent confirmation before adoption |
| Target/scope approval missing, unavailable controls or prerequisites, failed proof, or customized-file conflict | `blocked` | Owning stage id, default `09-qa` | Name the decision, prerequisite or scoped repair needed; require fresh proof after repair |

Include the harness's proved/draft/blocked status and evidence class in the report.
Generated instructions and builder smoke alone remain draft. Emit the actual
owning stage id (for example `00-prereqs`, `09-qa` or `11-debug`), not a placeholder.
Carry remaining caller actions forward. The envelope does not authorize adoption,
state writes, or shipping; those remain with the stage owner.

## Guardrails

- Generation is optional and does not install a harness in another project or
  become a universal Cloud, delivery, or mission prerequisite.
- The stage owner owns approval, upgrades, state changes, commits, and shipping.
- Cleanup targets only resources the run declared as owned; evidence survives it.
- A selected unavailable route is reported as blocked with a visible fallback,
  never relabeled as a harness pass.

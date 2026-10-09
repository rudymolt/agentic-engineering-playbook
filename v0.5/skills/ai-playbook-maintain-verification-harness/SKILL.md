---
name: ai-playbook-maintain-verification-harness
description: Audit an adopted project-owned verification harness completely, correct only authorized owned drift, and retain independently verified journey evidence.
---

# Verification-harness maintenance

## Purpose

Maintain one explicitly adopted project-owned verification harness without
turning it into a background watcher, a product-fix route, or a claim about an
unselected pilot. This is distinct from an individual doc-close evidence update:
a maintenance result covers every entry declared by the selected map.

## Procedure

### Step 1 — Locate the adopted route and bound the audit

Read the selected project-relative harness path, its feature-map index, every
indexed feature entry, and the harness's existing Launch/Doctor/Drive/Evidence/
Cleanup instructions. Confirm the map is non-empty, has stable unique IDs, has
no dangling index links or orphaned files, and record its declared coverage and
omissions. Bound source exploration to the declared entry points and one owner
drives the application commands. Within that source boundary, enumerate public
entry points and name additional unmapped ones as coverage gaps; any such gap
blocks clean. Before any writes, validate every map ID and link and every
correction target against the canonical selected harness root. Reject absolute
locators, traversal, malformed IDs, and symlinks escaping the owned root; validate
the whole correction set before changing its first file.
A missing or inaccessible selected route is
blocked, not a fallback harness pass.

Completion criterion: the exact map, entries, declared source/live coverage,
evidence destination, and any entry-point gaps are visible before a command runs.

### Step 2 — Inspect and drive report-only coverage

Inspect the real source behind each mapped entry, then run its actual Doctor and
Drive path with the existing project commands. Retain the commands, observed
effects, revision/instance, and evidence locators. Do not call an index entry
clean merely because it exists: skipped source or live coverage, failed or
missing evidence, a duplicate/orphan/empty/inaccessible map, or any unresolved
product regression is **blocked**. Preserve valid partial evidence and issue
details.

Classify the report only after all declared entries are covered:

- **clean** — complete source/live coverage, retained evidence, and no gap,
  regression, or correction required.
- **blocked** — any required coverage, evidence, prerequisite, correction, or
  product behavior remains unresolved.

Completion criterion: a report-only result names every covered and uncovered
entry and never edits a map, helper, product, state clock, branch, or PR.
Use an evidence-only driving mode that preserves every map byte, including Last
verification fields. If the route cannot retain evidence without map writes,
block inspection and return the needed harness correction to its authorized owner.

### Step 3 — Request and apply a narrowly authorized correction

Keep inspection separate from correction. With explicit scope, correct only
proven map drift supported by intended-behavior/source evidence, or harness
helper/map drift inside the owned harness directory. Re-drive each corrected
path afterward; a corrected critical path invalidates its prior proof. Editing
an application helper or changing product behavior is a separate product task.
Applied corrections remain **pending / reproof-required** (or blocked); applying
an edit alone never yields terminal changed.

For a product regression, preserve expected behavior, retain the failed evidence,
and file/return a concise Markdown defect to the owning task workflow. Do not
hide it by changing the map or product. If an intended route changed, record its
source or acceptance evidence before updating the continuous feature identity.

Completion criterion: every requested correction is either explicitly scoped to
an owned path with evidence, or remains blocked with a product/task defect.

### Step 4 — Obtain fresh complete verification

Have an independent fresh verifier inspect the final correction and re-drive all
declared map entries, including corrected paths. Only that complete final pass
may report **changed**: the corrections must be in scope, independently verified,
and supported by retained evidence. Report-only reviewers do not update state or
maintenance timestamps. Retain the final changed result with its fresh verifier
and evidence, and confirm every corrected path remains mapped and was re-driven.

Only the owning stage may record an accepted **clean** or **changed** complete
audit in `.playbook-state.yml → last_run.verification_map_maintenance`, then
recompute status. Never stamp it for blocked, failed, partial, source-only, or
single-entry work. On first explicit opt-in, use the stage-owned transition:
`python3 {playbook-path}/v0.5/scripts/compute-status.py . --select-verification-harness <path>`.
It atomically binds the selected path, records the actual enable boundary, clears
the audit timestamp for a new target, and recomputes status. Repeating the same
bound path preserves both timestamps; disabling and re-enabling that same path
preserves them too. A different selected path must use that transition; a
hand-edited path/binding mismatch is actionable and cannot receive old audit
credit. The state stores no credentials or run transcripts.

Completion criterion: the final result is clean, changed, or blocked with exact
coverage/evidence locators and no unverified correction.

### Step 5 — Carry proven journey knowledge through doc-close

When a shipped change affects an adopted entry point, prompt the owning stage-08
review and stage-10 doc-close to compare the affected map entry and distill
proven driving knowledge before planning artifacts archive. An individual
doc-close entry evidence update is not a complete maintenance audit. Follow
[stage-08 review]({playbook-path}/v0.5/10-process/08-review.md),
[stage-09 QA]({playbook-path}/v0.5/10-process/09-qa.md), and
[the document lifecycle]({playbook-path}/v0.5/30-document-lifecycle.md) for their existing
stage authority.

Completion criterion: affected entry-point knowledge has a named stage owner;
no watcher, automatic PR, or new cadence is introduced.

## Terminal result

On every exit, including an early stop, append a YAML `playbook_result` containing
`outcome`, `next_stage`, and an ordered `required_actions` list. Choose the row
that matches the result:

| Work result | outcome | next_stage | required_actions |
|---|---|---|---|
| `clean` after complete source/live coverage | `handoff` | Owning stage id, default `09-qa` | Review the complete audit and, only if accepted, perform the stage-owned maintenance timestamp update and status recomputation |
| `changed` after scoped corrections and fresh complete independent verification | `handoff` | Owning stage id, default `09-qa` | Review the correction evidence and, only if accepted, perform the stage-owned maintenance timestamp update and status recomputation |
| Requested complete audit is `blocked`, partial, or has a correction still pending/reproof-required | `blocked` | Owning stage id, default `09-qa` | Name missing coverage, approval, prerequisite, defect or proof; finish authorized corrections and required verification before acceptance |
| Successful single-entry doc-close evidence handback; no complete audit requested | `handoff` | Actual doc-close owner, normally `10-ship-and-deploy` | Consume the affected entry's evidence and continue remaining doc-close/retro actions |

Keep the maintenance finding separate from `playbook_result.outcome`: `clean`
and `changed` are not valid envelope outcomes. Emit the actual owning stage id
(for example `08-review`, `09-qa` or `10-ship-and-deploy`). Carry remaining caller
actions forward. The report never writes the maintenance clock or other state;
a handoff offers evidence for stage-owned acceptance and does not certify QA or
shipping. A single-entry doc-close handback reports no complete-audit finding or clock
credit and does not require a full maintenance audit. Partial coverage blocks
only a requested complete audit; an unresolved single-entry requirement returns
`blocked` to its doc-close owner with that specific remaining action.

## Guardrails

- An unadopted project has no map-maintenance obligation.
- This skill is report-only until a human/stage owner explicitly authorizes the
  bounded correction phase.
- Cleanup touches only run-owned resources; retained evidence and partial
  findings survive failure cleanup.
- No consuming project, pilot selection, background audit, automatic issue/PR,
  commit, or product correction is implied.

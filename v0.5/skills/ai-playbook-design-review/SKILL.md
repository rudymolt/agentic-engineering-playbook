---
name: ai-playbook-design-review
description: Run transaction-safe, report-only UI verification for stage 08, including responsive and URL-state evidence, with separate remediation and safe upstream fallback.
---

# Playbook design review adapter

## Purpose

Report-only UI verification owned by the playbook. This skill preserves the stage-08
verifier boundary even when an installed upstream design workflow expects to fix or
commit its findings.

## Procedure

### Step 1 — Fix the review boundary

Read the acceptance criteria, diff or commit range, project `AGENTS.md` / `CLAUDE.md`,
and the affected design glossary, kitchen sink, and design-language guide. Declare the
review artefact directory and confirm that only repository reads, verification commands,
browser actions, and evidence writes are in scope. If an upstream report-only mode is a
candidate, resolve its installed `SKILL.md` and run

```bash
python3 {playbook-path}/v0.5/scripts/check-upstream-compatibility.py \
  --skill design-review --source {resolved-SKILL.md} \
  --fallback "tool: /ai-playbook-design-review"
```

Use only the embedded entry point printed by a `COMPATIBLE` result. Every other result
selects this manual procedure.

Completion criterion: the reviewed goal/range, project rules, design sources, evidence
directory, and manual-or-compatible route are named before browser work begins.

### Step 2 — Exercise the UI

Drive the real app at desktop, tablet, and mobile widths. Record horizontal body overflow,
44 px tap targets or documented compact-control exceptions, table wrapper readability,
heading hierarchy, and conformance with the project's named design surfaces. For URL-driven
UI, exercise drawer, filter, tab, link, hash, query, and row expansions and record scroll position and focus before and after each context-preserving transition. Confirm live filter
updates that should preserve context do not use native form submission. Capture screenshots, DOM,
console, URL, focus, or scroll evidence appropriate to each claim.

Completion criterion: every applicable responsive and URL-state check has a visible result
or an explicit not-applicable reason tied to the affected scope.

### Step 3 — Return a verifier verdict

Return scope and acceptance criteria checked, exact browser flows/commands, pass/fail
results, artefact paths, and one deduplicated finding list. Every finding includes severity, confidence, action tag, and evidence. The verdict is `pass`, `blocked`, or
`pass-with-accepted-risk`.

When a decision is genuinely human-owned, use a structured question control if available;
otherwise present the identical inline typed options with the recommendation and wait for
the typed reply.

Completion criterion: the report contains reproducible evidence and a verdict, and every
finding has all four required fields.

### Step 4 — Hand remediation back

A passing report proceeds to stage 09. An accepted finding becomes a separate generator task
under stages 07/09; it follows the project-selected commit strategy and then re-enters a
fresh verifier context. This review does not apply the fix or certify a generator's output.

Completion criterion: the next stage or separate generator task is named, with no product
change made by this verifier.

## Guardrails

- The review creates zero product/source edits and zero commits.
- Repository transaction state, routing, configuration, telemetry, and installed skills remain unchanged.
- Upstream incompatibility selects the manual procedure; upstream safety instructions are not weakened.
- Evidence artefacts are the only writes and use the declared review location.

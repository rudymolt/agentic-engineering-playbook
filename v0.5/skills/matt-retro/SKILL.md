---
name: matt-retro
description: Review a coding session with Matt Pocock's environment-improvement retrospective.
disable-model-invocation: true
---

# Matt's environment retrospective

This explicit command runs Matt Pocock's complete v1.3.1 retro workflow through
this playbook adapter. It is independent of gstack's `/retro` (`$gstack-retro`
in Codex). Invoke this entry as `/matt-retro` in Claude or `$matt-retro` in Codex.

## Procedure

### Step 1 — Load the workflow and writing guidance

Read [the complete pinned workflow](references/upstream-retro.md), including its
reference section. Its frontmatter is source evidence; the callable identity is
`matt-retro`. Follow its four steps with the host adaptation below.

For upstream step 1, load the installed `writing-for-agents` using the host's
skill loader. Where there is no loader, read its resolved installed `SKILL.md`
and the writing references it requires. If unavailable, report the missing
prerequisite and return to stage 00 installation; do not claim a completed retro.

Completion criterion: the full retro source and required writing guidance have
been read, or the missing prerequisite is reported.

### Step 2 — Review the selected session

Run upstream steps 2–4: use the specified session (current session by default),
inspect primary evidence and actual repository check wiring, examine all seven
improvement categories, and present candidates in severity order with supporting
locators. Mark inaccessible session evidence as unavailable. Apply upstream's
mechanical-check versus review-judgement distinction.

This invocation produces recommendations. It does not itself change instructions,
checks, host settings, service access or global files. Route accepted work through
the project's ordinary change process and stage 12 promotion rules.

Completion criterion: severity-ordered candidates cite observed evidence and
propose concrete improvements, or explicitly explain why none are supported.

### Step 3 — Return findings to the caller

For a standalone invocation, return the findings. When the human selected this
command during stage 12, hand the findings back to the stage owner for the retro
record, learning coverage, observational eval and completion/state updates.
Running this command alone does not mark the weekly or feature retro complete.

Return the process-map `playbook_result` envelope. For standalone completed
findings use `outcome: complete`, `next_stage: null`, and `required_actions: []`;
this describes this command's report only. When returning to stage 12 use
`outcome: handoff`, `next_stage: 12-retro-and-learn` and list its remaining record/completion actions.
If step 1 cannot load its dependency, use `outcome: blocked`,
`next_stage: 00-prereqs`, and name the missing prerequisite in `required_actions`.

Completion criterion: findings and remaining stage-owned actions are explicit
in both the report and its `playbook_result`.

## Maintenance

The exact source and MIT license are retained in `references/upstream-retro.md`
and `NOTICE`. During the playbook's monthly upstream review or a Matt pin change,
compare the full source and `writing-for-agents` dependency, review the host/stage
adaptation, update the source receipt and verify both invocation names. Bootstrap
and upgrade manage these files with recorded bases; preserve project customizations
through that review path. A generic upstream installer update does not update this
adapter. The entry name remains stable across source upgrades.

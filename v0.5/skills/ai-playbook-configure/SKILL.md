---
name: ai-playbook-configure
description: Review and safely edit all four project model roles through guided or expert typed chat, with local presentation preferences and explicit save previews.
disable-model-invocation: true
---

# /ai-playbook-configure

S2 edits **Plan, Build, Verify and escalated repair**. QA inherits Verify;
Coordinator is observed display-only. Personal presets, skill bindings,
recommendations and unavailable-model replacement advice are later slices.
This skill never launches a model or edits runtime state.

## Procedure

1. **Read and discover.** Identify the project and installed playbook locator.
   Use model-router's existing discovery procedure without its selection/launch
   steps. Exclude unavailable, unauthenticated, blocked, identity-unverifiable
   or role-ineligible routes. Supply a current-availability adapter to the
   helper's `--discovery-command`, not a static discovery file. Include the
   current chat's observed identity as optional `coordinator` route metadata in
   that same fresh discovery, not a user-supplied model or a guessed catalogue
   default. If unavailable, display unknown; do not switch the Coordinator.
   On each request,
   genuinely recheck role + model + runner + reasoning through the existing
   authority surface, echo the request ID and timestamp the observation inside
   the helper's clock window. Never redate cached results or treat guidance's
   24-hour interval as access evidence. Keep bounded discovery local, not in
   shareable settings. Read the helper contract at
   `{playbook-path}/v0.5/scripts/playbook-config.md` using the installed playbook
   locator, not a path relative to the copied skill. The mockup and generated
   availability claims are not evidence. Supply an explicit user-local
   `--preferences-dir` outside the project on every conversation request;
   never put a private destination in shared configuration. Pass only known
   goal and billing facts in `read`'s `context`. Read existing project context
   instead of asking it again; unknown billing is a valid answer. Run the
   helper's `read` action. On
   blocked/recovery-required, report its corrective action and offer Reload or
   Not now. Completion criterion: current values, origins and verified routes.
2. **Present project defaults.** Ask only the returned `missing_context`
   questions through typed `Goal <context>`, `Billing api`, `Billing subscription`,
   `Billing mixed` or `Billing unknown`, and `Guided` / `Expert`. Goal/billing
   remain conversation context in S2, not project writes; billing persistence
   arrives in S5. Known local presentation skips that question on reopening.
   Show all four model/runner/reasoning choices and effective origins,
   QA inheriting Verify, observed Coordinator authority/date or unknown,
   retained repair constraints, exact destination
   `.playbook-config.json` and whether adoption migrates legacy preferences.
   Legacy state stays byte-for-byte intact, becoming inert default history
   after adoption. Offer typed `Edit`, `Edit Plan`, `Edit Build`, `Edit Verify`,
   `Edit Repair`, `Apply`, `Explain <role>`, `Not now`. Expert presentation is
   compact, never a different proposal or weaker validation. Label every row
   as a retained edition/project starting choice or an explicit user edit,
   not a recommendation; suitability and cost evidence are missing until S6.
   For an unbootstrapped project, hand the complete role draft to the existing
   bootstrap approval preview. Do not run a second bootstrap or write project
   settings here before that gate; reopen after bootstrap and review again.
   Completion criterion: the user sees scope, origins, migration and destination.
3. **Edit and preview.** Pass replies through the helper's `reply` action with
   the previous proposal. `Edit` offers numbered roles. `Edit <role>` displays
   verified complete alternatives numbered from 1, showing model, runner and
   reasoning. `Pick model` offers numbered model, then supported runner, then
   supported reasoning, and complete identity if otherwise ambiguous. Never
   silently choose among providers or optional identity metadata. A number edits only the draft
   and returns the complete before/after preview; show retained roles and
   constraints too. `Explain <role>` identifies that selected route, availability
   observation and limitations without selecting or launching anything.
   `Explain` defaults to Build and reports discovery authority/date and explicitly
   unknown suitability/comparable cost; no paid benchmark. With no alternatives,
   offer Reload or Not now instead of inventing a route. Native controls may
   mirror, never replace, typed replies at every level, with immediate text
   fallback. `Back` returns to the full proposal without losing other edits;
   an invalid reply retains the previous draft under `retained_proposal` and
   offers `Back`. `Edit` and `Edit <role>` from that blocked result also reuse
   the retained draft, never implicitly reload and discard other edits.
   Reload intentionally discards unsaved draft changes.
   `Guided` / `Expert` show a separate local preference before/after preview
   with its exact destination and `resolved_destination` behind directory
   aliases. If directory identity changed, show the corrective message and
   require the new preview before another Apply; retain unrelated role drafts.
   Only `Apply preference` saves it using the same
   durability/completion/recovery protocol as project defaults; no project
   draft is saved by that action. Return to the complete role proposal afterward.
   `Not now` saves nothing pending; if presentation was explicitly saved earlier,
   explain that it remains saved while the project draft is cancelled.
   Completion criterion: reviewed draft
   or cancellation, with nothing saved.
   Skill editing uses `Edit skills` or `Edit skills <job>` for alignment,
   specification, implementation, code review or application QA. Show all
   `skill_proposal` and `skill_changes` before/after rows in the full proposal.
   Numbered `skill_options` retain the same verified source prefix/provenance.
   `Choose <number>` edits one job; `Choose <number>,<number>` retains supported
   alignment context → decisions composition order. `Explain skills <job>`
   shows inputs, outputs, effects, owner and eligibility without invocation.
   Unknown, changed, colliding or incompatible sources require an explicit
   fallback or block, never warning acknowledgement. Read
   [`../../scripts/skill-bindings.md`](../../scripts/skill-bindings.md) for
   contracts, current upstream exclusions and already eligible project QA proof.
   Configuration does not create or maintain a harness.
4. **Apply the reviewed proposal.** Only after typed `Apply`, repeat genuine
   authoritative discovery through that adapter and pass the same proposal to the helper. Never
   silently create and Apply a refreshed proposal. Changed inputs require
   Reload and another preview/Apply. Unavailability requires editing the affected role; no
   automatic substitution. Report applied/unchanged/blocked/recovery-required
   exactly with destination and corrective message. `Not now` writes no
   pending defaults or presets; distinguish earlier explicitly saved presentation
   and any local read-side discovery refresh. Stop for retained recovery evidence;
   never remove it to make a save appear successful.
   Completion criterion: validated save, no-op, cancellation or named blocker,
   with no model dispatch or build.

Return `playbook_result` with outcome applied/unchanged/blocked,
`next_stage: null`, and ordered `required_actions` from the corrective result.
Existing lane gates remain selection, approval and launch authority.

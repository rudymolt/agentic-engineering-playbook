---
name: ai-playbook-configure
description: Review and safely edit an existing project's Build model default through typed chat, with migration preview and explicit Apply.
disable-model-invocation: true
---

# /ai-playbook-configure

S1 edits **Build only**. Personal presets, skill bindings, all-role setup,
recommendations and unavailable-model replacement advice are later slices.
This skill never launches a model or edits runtime state.

## Procedure

1. **Read and discover.** Identify the project and installed playbook locator.
   Use model-router's existing discovery procedure without its selection/launch
   steps. Exclude unavailable, unauthenticated, blocked, identity-unverifiable
   or role-ineligible routes. Record fresh bounded discovery locally, not in
   shareable settings. Read the helper contract at
   `{playbook-path}/v0.5/scripts/playbook-config.md` using the installed playbook
   locator, not a path relative to the copied skill. The mockup and generated
   availability claims are not evidence. Run the helper's `read` action. On
   blocked/recovery-required, report its corrective action and offer Reload or
   Not now. Completion criterion: current values, origins and verified routes.
2. **Present project defaults.** Show all four model/runner/reasoning choices,
   QA inheriting Verify, retained repair constraints, exact destination
   `.playbook-config.json` and whether adoption migrates legacy preferences.
   Legacy state stays byte-for-byte intact, becoming inert default history
   after adoption. Offer typed `Edit Build`, `Apply`, `Explain`, `Not now`.
   Completion criterion: the user sees scope, origins, migration and destination.
3. **Edit and preview.** Pass replies through the helper's `reply` action with
   the previous proposal. `Edit Build` displays verified alternatives numbered
   from 1, showing model, runner and reasoning. A number edits only the draft
   and returns the complete before/after preview; show retained roles and
   constraints too. `Explain` reports discovery authority/date and explicitly
   unknown suitability/comparable cost; no paid benchmark. With no alternatives,
   offer Reload or Not now instead of inventing a route. Native controls may
   mirror, never replace, typed replies. Completion criterion: reviewed draft
   or cancellation, with nothing saved.
4. **Apply the reviewed proposal.** Only after typed `Apply`, repeat genuine
   authoritative discovery and pass the same proposal to the helper. Never
   silently create and Apply a refreshed proposal. Changed inputs require
   Reload and another preview/Apply. Unavailability requires Edit Build; no
   automatic substitution. Report applied/unchanged/blocked/recovery-required
   exactly with destination and corrective message. `Not now` writes no
   defaults or presets; distinguish any local read-side discovery refresh.
   Completion criterion: validated save, no-op, cancellation or named blocker,
   with no model dispatch or build.

Return `playbook_result` with outcome applied/unchanged/blocked,
`next_stage: null`, and ordered `required_actions` from the corrective result.
Existing lane gates remain selection, approval and launch authority.

# Pickup brief — portable continuation without transcript dependence

> Use only when work crosses a session, worker, host, or planned pause. It is a
> compact handoff, not a stage, skill, tracker, or substitute for current-state
> checks.

**This reference in one breath:** leave a successor one bounded, evidence-linked
brief; they reconcile it with current repository and task truth, then take one
correct next action.

## Write the brief

Keep the **Capsule** to at most five bullets. It preserves approved scope and
decisions, not an investigation transcript. Every relevant worker/thread gets
one current status line; include only a portable route or artifact locator, its
role, current status, and the evidence that supports it. Record each failed or
reverted attempt separately with its revision and evidence locator so it cannot
return as an unexplained success claim.

Use this shape:

```markdown
# Pickup — {feature or task title}

## Capsule
- {approved scope and durable decision locator}
- {current outcome / remaining dependency}
- {other essential fact}
<!-- no more than five bullets -->

## Thread status
- `{portable thread or route locator}` — {role}; {current status}; evidence: {portable locator}.

## Failed or reverted attempts
- `{revision or attempt locator}` — {failed/reverted state}; evidence: {portable locator}; do not retry because: {reason}.

## Reconciliation contract
- Branch / revision: `{branch}` / `{full revision}`; base or merged state: {locator/result}.
- Task tracker: {portable task, Markdown task ID, or issue locator}; approved scope: {spec/slice locator}.
- Evidence: {completed gate and artifact locators}; required gates: {named remaining gates}.
- Budget: {ordinary time checkpoint or selected hard deadline, cumulative retry/no-progress counts, planned verification capacity, and any remaining hard limit or locator}.

## One next action
{exactly one imperative action, including a blocker/request when evidence or authority is missing.}
```

Use repository-relative paths with revisions, committed evidence, tracker URLs or
Markdown task IDs, and accessible cloud artifact/receipt locators. Do not make a
successor depend on a Mac path, unshared local file, secret, or private chat
transcript. Link an approved ADR, spec, slice, tracker, or result instead of
replaying prior investigation.

## Reconcile before resuming

The successor checks the current branch, HEAD, worktree, base/merge or revert
state, canonical tracker, declared evidence, dependencies, budgets, and review
gates against the brief. A stale branch, merged/reverted revision, changed
dependency, missing artifact, or incomplete gate changes the reported resume
point. Previous worker claims remain historical context: execute the current
stage's required verification rather than accepting a prior success claim.

After the check, state the reconciliation result and keep **exactly one** next
action. A complete result may route to the next stage; a missing required input
or authority makes the one action an explicit blocker or human request. Do not
silently create a new tracker item, alter a mission, or continue from a private
transcript.

## Local-only and inaccessible evidence

Name inaccessible proof truthfully, for example: `inaccessible: Mac-only —
{original safe locator}; needed input: {redacted/exportable artifact}; transfer
owner: {human or named host}`. It is not evidence a successor can verify. Before
handoff, transfer the necessary permitted input to an accessible locator; if that
cannot happen, retain the limitation and make obtaining it the one next action.
Never expose a secret to make an artifact portable.

## Existing authorities stay in charge

For a routed Plan/Build/Verify handoff, carry the selected route identity and
pace, but use the [model-routing handoff contract](../93-model-routing-track.md)
for fresh-context and authoritative worker metadata. A multi-phase delegated
change still follows the [delegation track](../91-delegation-track.md): its fresh
verifier receives artifacts, not builder chat. An agent-owned delivery mission
continues under its [observer/re-entry rules](delivery-mission.md); a pickup brief
cannot claim a controller generation, authorize a retry, or replace its durable
receipt.

## Next

- Writing or resuming a brief → return to the owning stage or `/whats-next`
- Agent-owned delivery mission → follow `delivery-mission.md`

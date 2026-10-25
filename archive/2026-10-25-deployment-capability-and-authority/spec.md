# Deployment capability and existing authority — specification

Status: specification and verification seam approved on 2026-10-24 with
"OK I approve this, let's continue." Alignment confirmed on 2026-10-24.
Planning continues in the selected
current-tab Astra/high route. Source: [accepted alignment](alignment.md).

## Problem statement

An agent can discover missing deployment access only after dependent work is
ready, or repeatedly request permission for steps already covered by the user's
operation. Conversely, credentials or a successful backup can be mistaken for
authority or proof of recoverability. The playbook must distinguish existing
authorization from capability evidence, make gaps visible early, and preserve
the decisions and recovery evidence needed to continue safely across handoffs.

## Solution

Check relevant capabilities during planning and before their dependent action.
Reuse existing authorization for necessary constituent work within its target,
effects and limits. For releases that affect persistent data or create a risk
requiring data recovery, identify a retained recovery point, actually restore
it into an isolated disposable target, and establish recovery coverage before
the live change. Continue independent work while a named dependency is blocked.

These are provider-neutral operating instructions. They do not make this
repository perform a deployment or provision verification infrastructure.

## User stories and acceptance criteria

1. **As a project owner, I want access gaps discovered during planning so that
   setup does not arrive as a last-minute release surprise.** When planned work
   needs a shared database, bulk-data operation, deployment or external verifier,
   identify the relevant target, runner, access and recovery capabilities before
   dependent work. Unrelated sessions acquire no universal cloud audit.
2. **As an agent, I want to use sufficient existing access so that I do not ask
   for unnecessary credentials.** Inspect the intended tool/runner privately;
   project-scoped access can pass even if global listing is denied. Credential
   presence alone does not prove the value, target, or capability.
3. **As a reviewer, I want the exact selected verifier checked so that a working
   coordinator login does not conceal a verifier failure.** An authenticated
   selected route proceeds without another sign-in request. Any existing
   alternative must preserve selected model, independence and permissions;
   an unavailable selected route uses the existing route-selection rules.
4. **As a project owner, I want one actionable request for a missing capability
   so that I can resolve it without repeating setup.** Name the failed capability,
   intended target/runner, redacted evidence and precise private setup needed.
   Retain an unchanged request across retries and handoffs. Recheck after relevant
   runner, VM, target, credential or tooling changes.
5. **As an agent, I want independent work to continue so that one access gap does
   not halt unrelated progress.** Keep dependent verification, mutation or release
   blocked; continue only work whose correctness and effects do not depend on
   the missing capability or decision. Never treat elapsed time as approval.
6. **As a project owner, I want backup requirements to follow actual data risk
   so that application changes cannot bypass them by lacking migration files.**
   Apply backup and isolated restore verification to changes affecting persistent
   data or creating a recovery risk. Presentation-only deployments do not trigger
   them by default; explicit stricter project policy remains binding.
7. **As a project owner, I want an authorized operation to include its necessary
   preparation so that I do not approve the same work repeatedly.** Within the
   authorized scope, target, effects and limits, proceed with timestamped backup,
   isolated restore verification, scoped retries, verification-input repairs
   and owned disposable-copy cleanup. A retry or handoff alone adds no prompt.
8. **As a reviewer, I want recovery demonstrated so that backup API success is
   not mistaken for a usable recovery point.** Restore the identified recovery
   point into an isolated disposable target; check affected schema/data integrity
   and relevant read/smoke behavior. Retain redacted evidence of identity,
   coverage, time and result. Scale checks to the change; a full application
   regression suite is not automatic for each restore test.
9. **As a release owner, I want current recovery coverage so that recent writes
   are not silently lost.** Immediately before the applicable release/mutation,
   establish the actual target, pre-change coverage and preservation or replay
   of intervening writes. A recent timestamp or early access check alone fails
   this gate. Missing, failed or stale evidence blocks the dependent action.
10. **As a project owner, I want downtime decided explicitly so that release
    authorization is not read as permission to pause service.** If coverage
    needs a maintenance/write-pause window, propose its concrete scope and
    obtain the decision unless already authorized. Do not infer permission
    for downtime or data loss from deployment authority.
11. **As a project owner, I want verification costs bounded so that disposable
    resources do not create unapproved spending.** Necessary resources may use
    existing approved resource/cost limits. If incremental cost cannot be bounded
    within that authority, obtain one concrete estimate/ceiling decision early
    and reuse it across the operation. Unknown cost is not zero cost.
12. **As a release owner, I want cleanup to preserve recovery so that verifying
    a backup does not destroy it.** Cleanup applies only to the disposable
    verification copy owned by this operation. Retain the identified backup
    under its existing retention policy; backup authority grants no deletion
    of retained backups or unrelated resources.
13. **As an incident responder, I want recovery authority distinguished from
    rehearsal so that a failed deployment does not trigger an unapproved live
    restore.** Reuse valid authorization for the exact recovery action, target
    and effects when present. Otherwise request the uncovered decision before
    executing it. Both debug and canary guidance must obey this boundary.
14. **As a migration owner, I want restoration and migration reversal checked
    separately so that one success does not stand in for the other.** Preserve
    applicable apply → roll back → re-apply rehearsal and separable migration/code
    rollout requirements. A restore test does not fulfill a required migration
    rollback rehearsal or authorize the live migration.
15. **As a project owner, I want delegated technical choices handled once so
    that routine API/CLI choices do not become repeated questions.** Decide and
    record routine choices within an existing delegation. Request only uncovered
    product, security, scope, credentials, cost, target or effect decisions.
16. **As a successor agent, I want a compact evidence record so that I can resume
    without reconstructing private chat.** Carry authorization provenance and
    scope, target, runner, capability result, recovery point/coverage, restoration
    evidence, cost limits and unresolved requests in the existing plan,
    verification record or pickup brief. Keep secrets out; revalidate changed
    capabilities without rewriting the user's authority or relaxing fresh Verify.
17. **As a project owner, I want all existing execution boundaries preserved so
    that this clarification does not enlarge the operation.** No implied live
    restore, data loss, changed target, credential expansion, unapproved cost,
    unauthorized migration or PR merge. Stop, selected hard limits, actual
    quotas and cumulative failure/no-progress guards remain binding.
18. **As a maintainer, I want these instructions to survive upgrades so that
    consumers keep their customizations and valid settings.** Review compatibility
    at the existing monthly upstream checkpoint and explicit skill, runtime or
    provider upgrades. Adopt reviewed pins through the existing preview/migration
    path, retaining customizations and a recoverable prior configuration.

## Implementation decisions

- Foundations own the distinction between existing authorization and capability
  evidence, including the rule to ask only for an uncovered decision. Clarify
  secret-handling guidance to inspect safe existing access before requesting
  private setup; retain redaction and incident rules.
- Prerequisites and alignment own conditional early discovery. Implementation
  and model routing need only narrow references or corrections for the exact
  runner preflight; they retain route-selection and fresh-context authority.
- Shipping owns the detailed data-risk trigger, target and recovery proof,
  concurrent-write coverage, resource limits and cleanup. Retain the migration
  section as a specialization with its separate reversal rehearsal.
- Debug and canary instructions consult actual recovery authorization before
  acting. Replace unconditional rollback directives with that rule.
- The pickup brief and project instruction template carry the same concise
  contract. The digest points to the owning procedure. Do not duplicate the
  detailed procedure at every entry point or add a new permission ledger.
- **Deep modules/seams:** reuse the existing stage/document interface and
  verification command. No new runtime module, API, state schema, credential
  adapter or provisioning service is needed.

## Testing decisions

The primary acceptance seam is the **published workflow an agent reads**:
relevant prerequisite/alignment entry → exact runner preflight → shipping gate
→ recovery or handoff. The expected outcomes are the numbered criteria above
and the [scenario matrix](alignment.md#acceptance-scenarios-to-carry-into-the-spec).

1. **Scenario verification:** a fresh independent reviewer receives the spec,
   changed documents and scenario matrix without the implementer transcript.
   For each scenario, report the instructed next action, whether a human decision
   is required, what remains blocked, and the source clause that establishes it.
   Fail any conflicting entry point, unsupported approval inference or omitted
   boundary. Record findings and verify returned corrections.
2. **Existing automated checks:** run Markdown conventions, links, public-content
   checks and affected generated-file checks during documentation iteration.
   Use the existing convention regression suite for preserved routing, cumulative
   guards and protected limits if those surfaces change. These detect structural
   drift; they do not prove agent compliance with arbitrary prose.
3. **New unit/integration tests:** n/a for documentation-only behavior with no
   changed executable interface. Do not introduce a fake deployment engine,
   tests that mirror wording, or provider integration tests to validate prose.
   If implementation needs an executable change, revisit this seam before
   building it and add meaningful red → green tests at that interface.
4. **Browser/device and production tests:** n/a for the shipped guidance change.
   The private review page is a planning aid, not a consumer UI change. Do not
   provision a live database or run a real restore for this repository change.
5. **Final release candidate:** regenerate affected manifests, require fresh
   independent review and the full canonical playbook verifier, then retain both
   required CI jobs and the existing review-thread/merge gates.

Prior art is the repository's Markdown convention CLI, its existing policy
regression fixtures, link/privacy checks, manifest generation and stage-08
independent review. [Evidence and review notes](review-notes.md) identify them.
The human approved this seam with the specification before breakdown.

## Out of scope

Cloud skill provisioning; new provider integrations; live backups, migrations,
restores or resource creation performed by this work; a new authorization
ledger or orchestration system; broad skill rewrites; automatic credential
replacement; changing project permissions, merge authority, model defaults or
upstream pins; relaxing recovery, review or quota gates.

## Open questions

None. The specification, verification seam and integrated
[slice breakdown](slices.md) are approved for Build one here.

## Further notes

- The maintainer checkout uses its existing planning index rather than creating
  consumer runtime state. Keep private tracker mappings and host evidence local;
  public examples remain generic.
- The specification route returned `configured: false`; the stage-owned local
  synthesis follows the installed to-spec structure. No new tracker item or
  label change is needed before the specification is reviewed.
- Scope and coherence reviews are recorded in [review notes](review-notes.md).
  No ADR is warranted: the change does not meet stage 02's three-part test.
- Add a changelog entry with a Why line when the process guidance is implemented.
  Regenerate affected outputs then; the current planning-only edit does not
  change release manifests or certify a shipping candidate.
- Stage 04 has drafted an integrated AFK slice with a verification target.
  Approval of this spec alone grants neither a
  multi-slice Build loop nor a PR merge.

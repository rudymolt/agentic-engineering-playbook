# Deployment capability and existing authority — alignment

Status: shared understanding and specification confirmed on 2026-10-24;
integrated slice and Build one here approved.

## Selected scope and route

The maintainer selected early deployment capability checks and reuse of
existing operation authority as one workstream on 2026-10-24. Cloud skill
provisioning remains separate. The selected planning route is the
current Codex tab, GPT-6 Astra with high reasoning, for planning and planning
retries only. Build and fresh independent Verify retain their stage gates.

This is a maintainer checkout of the playbook, not a bootstrapped consumer.
`planning/STATUS.md` is its existing state surface; no consumer runtime state
or installation is created. The in-repository stage source is available, and
the stage-owned `job-route` helper returned `configured: false` for alignment.
Relevant project/user skill roots and the runtime catalog were checked;
`grill-with-docs` and its `grilling` and `domain-modeling` references are
available locally. The alignment procedure follows their facts/decisions and
shared-understanding rules. Host-specific route evidence remains local.

## Problem

Agents discover access gaps too late and sometimes ask again for constituent
steps already covered by the user's authorized operation. Capability and
authority are separate facts: having access does not authorize an action,
and authorizing an action does not prove that its runner has access.

## Working understanding

All six decisions below reflect the two accepted rounds. No scope decisions
remain open. The human confirmed the final shared understanding with
"yes we are aligned. please continue."

1. **Discover capability when the work makes it relevant.** During alignment
   and planning, identify planned shared-database or bulk-data changes and
   the tools/runners needed to verify them. Check provider access, scoped
   credentials, application/direct target identity, Preview isolation, and
   the available backup and isolated-restoration route before dependent work.
   Keep this conditional; ordinary sessions do not acquire a new universal
   cloud audit. Independent work can continue while a named access gap is
   resolved.
2. **Check the exact route before requesting setup.** Privately inspect the
   intended runner's actual authentication and existing acceptable host routes.
   Accept sufficient project-scoped access even when global listing is denied.
   A write-only variable's presence is not proof of its value or target.
   Use an existing route only if it preserves the selected model, independent
   verification context and permission boundary. Otherwise make one precise
   private-setup request with the failed capability and redacted evidence.
3. **Reuse existing authority for necessary constituent work.** Backup and
   isolated restore verification apply when the actual release affects
   persistent data or creates a risk requiring data recovery, including
   application behavior without a schema migration. A presentation-only
   deployment does not trigger them by default; a project's explicitly
   stricter deployment policy remains applicable. An authorized operation
   includes its necessary timestamped backup, isolated restore verification,
   scoped retries, verification-input repairs, and cleanup of the disposable
   verification copy owned by that operation. Actually restore the identified
   recovery point into an isolated disposable target and demonstrate usability
   of affected data/schema with scoped integrity and relevant read/smoke checks.
   Scale checks to the change; a full application regression suite is not
   automatically required. Retain the identifiable backup under its existing
   retention policy. A handoff or retry alone does not require
   another approval. Before asking, compare the proposed action, target and
   effect with the user's existing instruction and ask only for the uncovered
   change. Record routine API/CLI decisions when the user has delegated them.
4. **Keep the final data-change gate current.** Immediately before the
   applicable release or mutation, establish the actual target, retained
   recovery point, successful restoration evidence, and recovery coverage for
   the actual pre-change state. Show how intervening writes will be preserved
   or replayed. If coverage cannot be established, propose a specific
   maintenance/write-pause window and obtain its decision before proceeding.
   Deployment authority alone does not permit downtime or data loss. A recent
   timestamp or early capability check is not proof of current coverage.
   Missing or failed proof blocks the dependent change. Migration rollback
   rehearsal remains a separate requirement where applicable.
5. **Preserve the distinct decisions.** Backup authority does not grant a live
   restore, loss of subsequent writes, deletion of retained backups, a changed
   target, wider credentials, cost beyond existing authority, an unauthorized
   migration, or PR merge. Reuse valid authorization for an exact recovery
   action already approved by the user; do not request the same decision again.
   Necessary temporary verification resources may use existing project-approved
   resource/cost limits. If incremental cost cannot be bounded within that
   authority, request one concrete estimate/ceiling decision early and carry it
   through retries and handoffs. Cleanup covers only the owned disposable
   verification copy, not the retained backup. Explicit Stop, hard limits and
   cumulative failure guards remain binding. Stage 11's recovery wording must
   respect actual recovery authorization rather than treating rehearsal as
   permission.
6. **Carry bounded evidence through handoffs.** Reuse the existing plan,
   verification record or pickup brief to retain authority, target, runner,
   capability result, restoration evidence, recovery coverage, resource/cost
   limits and unresolved setup requests.
   Recheck when the runner, VM, target, credentials or relevant tooling changes.
   Report backup identity, coverage, timestamp and verification result without
   credentials, personal records or private source-project content.

## Proposed implementation surface

- Foundations: define reuse of existing authority and distinguish access from
  authority beside the current collaboration and irreversible-operation rules.
- Stages 00/01: route relevant early capability discovery without requiring it
  for unrelated work; stage 07 and model-routing guidance receive only the
  narrow links or corrections needed for runner preflight consistency.
- Stage 10: own the detailed backup, isolated restoration and final target /
  freshness gate; stage 11 reconciles its unconditional rollback instruction.
- Pickup brief and project instruction template: carry the same compact
  semantics across sessions and into newly bootstrapped projects.
- Digest and other derived surfaces: link to the owning rules and regenerate
  affected outputs. Avoid copying the full procedure into every entry point.

## Acceptance scenarios to carry into the spec

| Scenario | Required outcome |
| --- | --- |
| A presentation-only deployment leaves persistent data unaffected | No new backup/restore test by default; honor an explicitly stricter project policy. |
| Application behavior changes persistent data without a migration file | Evaluate the actual data risk and apply the backup/restore gate. |
| Production access is missing but local work is independent | Request the exact setup once and continue that independent work; keep dependent actions blocked. |
| Scoped provider access works; global listing is denied | Continue using the scoped capability; no request for broader access. |
| The exact authorized verifier route is authenticated | Use it without another sign-in prompt. |
| Exact runner reports logged out and no acceptable route exists | One precise private setup request; retain the blocker across handoffs. |
| A VM, runner or target changes after preflight | Recheck relevant evidence; distinguish a new gap from an unchanged blocker. |
| An approved rollout resumes after a handoff | Necessary backup, isolated restore test, scoped retries and owned-copy cleanup proceed within existing authority. |
| Credentials exist but actual target or backup coverage is unproved | Block the dependent mutation and report the missing proof. |
| A backup API reports success without a restoration test | Restore the identified recovery point into an isolated disposable target and demonstrate affected data/schema usability; API success alone is insufficient. |
| The isolated restoration succeeds | Retain scoped integrity/read evidence; full application regression is not automatically required, and applicable migration rollback rehearsal remains separate. |
| Backup or isolated restoration fails, or recovery coverage is stale | Block the dependent release or mutation; do not claim verified recovery. |
| Writes occur after backup verification | Establish actual pre-change coverage and preservation or replay of intervening writes; a recent timestamp alone is insufficient. |
| Recovery coverage requires pausing writes | Propose a specific maintenance/write-pause window for a distinct decision unless already authorized; deployment authority alone does not permit downtime or data loss. |
| Recovery would overwrite live data or change the authorized target | Require its distinct decision unless that exact recovery action already has valid authority. |
| The exact recovery action already has valid explicit authorization | Reuse it within its target and effects, subject to current capability evidence and applicable gates. |
| Temporary verification resources fit existing approved limits | Create the necessary resources without another prompt and clean up only the owned disposable copy. |
| Incremental verification cost cannot be bounded within existing authority | Obtain one concrete estimate/ceiling decision early, retain it across retries/handoffs, and block dependent resource creation until settled. |
| The disposable verification copy is cleaned up | Retain the identifiable backup under its existing retention policy. |
| Routine API/CLI choices have been delegated | Decide and record them within the delegation; preserve human-owned choices. |
| A protected run reaches an explicit limit | Preserve its stop rule; prior operation authority does not override it. |

## Boundaries and maintenance

This change supplies provider-neutral process guidance, templates and relevant
regression checks. It does not implement provider integrations, install cloud
skills, create a new permission ledger, provision resources, run migrations,
or execute production backups as part of maintaining this repository.

At the existing monthly upstream-maintenance checkpoint and explicit
skill/runtime/provider upgrades, check whether capability and authorization
instructions remain compatible. Adopt changed behavior through reviewed pins
and the existing preview/migration path, preserving project customizations and
the previous recoverable configuration. Environment changes invalidate only
the relevant capability evidence; they do not rewrite the user's authority.

Public examples remain generic. Process changes require a changelog Why line,
affected manifest regeneration, focused iteration checks, fresh independent
review, and the full playbook verifier on the final shipping candidate.

## Decision tree

The maintainer explicitly requested grill-with-docs after reviewing the initial
proposal. That request does not confirm the proposal. Investigate facts before
asking decisions; the accepted answers below are reflected in the working
understanding and acceptance scenarios above.
This host exposes no subagent dispatch tool, so factual document exploration
used bounded serial reads. The confirmed alignment now feeds the specification;
implementation still follows specification, breakdown and Build gates.

### Round 1 — accepted

Human answer: "recommendations for all three".

1. **Scope breadth:** include reuse of existing authorization, exact-runner
   preflight, scoped retries, verification-input repairs, owned-fixture cleanup
   and previously delegated technical choices. Keep the rule small and preserve
   explicit authority boundaries.
2. **Backup trigger:** require backup/restore verification for changes that
   affect persistent data or create a risk requiring data recovery. Assess
   actual release behavior, not only schema migrations. A presentation-only
   deployment does not trigger the requirement by default; projects may adopt
   a stricter policy.
3. **Early missing access:** make one precise setup request immediately and
   continue independent planning/local work. Keep the dependent verification,
   mutation or release blocked until its capability is established.

The resulting vocabulary is recorded in the root glossary. No ADR is needed
at this point: these refinements do not introduce a hard-to-reverse architecture
decision meeting stage 02's three-part test.

### Round 2 — accepted

Human answer: "recommendations for all three".

4. **Restoration evidence:** restore the identified retained recovery point into
   an isolated disposable target, prove the affected data/schema is usable with
   scoped integrity checks and a relevant read/smoke check, and retain redacted
   evidence. Rehearse the migration's reverse separately where applicable.
   Full application regression is not automatically required for every
   restoration test.
5. **Concurrent writes and freshness:** establish coverage for the actual
   pre-change state and a recovery method that preserves or replays intervening
   writes. If that cannot be established, obtain a specific decision about a
   maintenance/write-pause window before proceeding. Do not invent authority
   for downtime or data loss. A recent timestamp alone is not proof.
6. **Disposable-resource cost:** use existing project-approved cost/resource
   limits and ordinary authorized resources. If incremental cost cannot be
   bounded within those limits, obtain one concrete estimate/ceiling decision
   early. Carry that decision through the operation and clean up its owned
   disposable copy. Keep the retained backup and its existing retention policy
   unchanged.

### Coherence check

The existing-authorization rule also covers an exact recovery action or
maintenance window already explicitly approved; backup permission alone never
grants either. The final gate covers data-affecting releases without migration
files. Scoped restoration evidence, intervening-write coverage and resource
limits are carried across handoffs without creating a new approval ledger.
No further scope decisions remain; final shared understanding is confirmed.

## One next action

Review [the proposed slice breakdown](slices.md). The specification and its
verification seam are approved; implementation follows breakdown and Build gates.

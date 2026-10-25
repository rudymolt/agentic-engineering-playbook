# Specification evidence and review

Updated: 2026-10-25. Status: S1 complete in this atomic slice commit. Full
verification and independent assessments pass; the human accepted the completed
report-only review with the narrow exception recorded below.
These notes support [the specification](spec.md).

## Pre-implementation source findings

- [Foundations](../../v0.5/00-foundations.md), sections 1 and 10, already prevent
  re-asking clarified questions and require backups/rehearsed reversals. Their
  secret and irreversible-operation wording needs the agreed capability and
  authority distinction. The verification ladder also needs consistency with
  the agreed conditional backup trigger.
- [Prerequisites](../../v0.5/10-process/00-prereqs.md), warm path and Checks C–E,
  establish capability routes but do not supply the full early deployment
  capability procedure. [Alignment](../../v0.5/10-process/01-align.md) owns
  relevant planning discovery.
- [Implementation](../../v0.5/10-process/07-implementation-tdd.md) and
  [model routing](../../v0.5/93-model-routing-track.md) already require selected
  route identity and fresh Verify; preflight clarification must preserve both.
- [Shipping](../../v0.5/10-process/10-ship-and-deploy.md), "Shipping a migration",
  requires a timestamped backup and executed migration reversal but does not
  establish the agreed restoration, write-coverage and resource-cost procedure.
  Its original canary summary said, "If anything looks wrong, rolls back."
- [Debug](../../v0.5/10-process/11-debug.md) opens with "Roll back first,
  investigate second." Reconcile both unconditional instructions with valid
  authority for the actual recovery action.
- [Project template](../../v0.5/templates/CLAUDE.md), Constraints, originally said
  "If a task seems to need a secret, stop and ask" and requires a timestamped
  backup before database/bulk edits. Update it without weakening secret handling.
- [Pickup brief](../../v0.5/10-process/pickup-brief.md) already carries scope,
  evidence and budgets, with a maximum-five-bullet capsule and one next action.
  Extend its existing reconciliation fields; do not add another record system.

## Existing verification seams

- [Markdown checker](../../v0.5/scripts/check-md-conventions.py) covers stage
  structure, routing and documented policy contracts.
- [Convention regressions](../../v0.5/scripts/test_convention_checks.py) include
  ordinary-build scope, cumulative guards, explicit limits and protected ceilings.
  Reuse these for preserved invariants when their source surfaces change.
- [Link checks](../../v0.5/scripts/check-links.py) and
  [public-content checks](../../v0.5/scripts/check-public-content.py) cover links
  and publication privacy. The focused link checker has a bounded document set;
  validate new planning-document links directly as well.
- [Manifest generation](../../v0.5/scripts/generate-manifest.py) and the
  [canonical verifier](../../v0.5/scripts/verify-playbook.py) own release checks.
  The latter discovers the existing test suite and invokes the other gates.
- [Stage 08](../../v0.5/10-process/08-review.md) owns fresh independent review.
  A scenario walkthrough against the actual published entry points verifies
  meaning; structural checks alone cannot establish it.

## Scope-guardian review

Manual check against stage 03's stated criteria; no installed scope-guardian
skill was found in the checked project/user/runtime sources.

- **Necessary scope:** early access and exact-runner discovery, authority reuse,
  recovery proof and propagation to existing entry points all map to accepted
  decisions. Debug/canary corrections remove direct contradictions.
- **Complexity removed:** no new approval ledger, state schema, provider adapter,
  generic prose-policy engine, cloud provisioning or deployment harness.
- **Test proportionality:** existing automated structure/policy checks plus fresh
  scenario review. Do not add unit tests merely asserting new sentences.
- **Ownership:** foundations own the shared distinction; shipping owns recovery
  details. Other surfaces link or summarize. This avoids competing full copies.
- **Result:** scope is bounded to the confirmed behavior. No new product decision
  or architecture abstraction was introduced.

## Coherence review

- Capability evidence is separate from existing authorization throughout.
- A needed backup/restoration test can proceed under existing authority while
  live recovery, downtime or unbounded cost still needs its own decision.
- Exact preauthorized recovery and maintenance actions reuse that authority;
  the specification does not recreate an unconditional approval prompt.
- The final gate covers actual data-affecting behavior, even without migration
  files, and retains any explicitly stricter project policy.
- Backup restoration and migration reversal remain distinct evidence.
- Owned-copy cleanup preserves the retained recovery point and retention policy.
- Handoffs preserve limits and unresolved requests while changed capabilities
  require rechecking; fresh verification and cumulative guards are unchanged.
- Terms agree with the [glossary](../../GLOSSARY.md).
- **Result:** no unresolved contradiction in the specification. The baseline
  contradictions above define the implementation targets.

## Build evidence

The human approved S1 with “approved and build one here” on 2026-10-24,
selecting Astra/high at standard pace for implementation and returned fixes.
The branch has no existing PR. Implementation and code-review `job-route`
checks both returned `configured: false`; the owning stages supply the workflow.

The implemented entry points now distinguish capability evidence from existing
authorization. Foundations own authority; Check C.2 owns conditional discovery;
stage 10 owns isolated restoration, current write coverage, cost and cleanup.
Debug/canary recovery now consults exact recovery authority. The template,
digest and pickup brief carry the same contract. No executable code changed.

Focused checks passed: Markdown conventions, 35 existing convention regressions,
link integrity, public-content/privacy and `git diff --check`. All 44 local links
in the new/changed planning documents resolve. Delivery generated artifacts were
already current; the edition manifest was regenerated. The full canonical
verifier initially reported 12 glossary-migration errors. All 12 failure
signatures match an isolated merge-base checkout: the platform temporary path
contains a symlink and triggers the migration symlink guard. The same 11-test
file passes with the temporary-directory environment set to its canonical path.
The first corrected local run remained incomplete: the cloud tests encountered
a Linux-only OS metadata dependency, one dispatch fixture required Python 3.12,
and the recovery group had no retained result. The cloud failure also reproduced
at the isolated merge base. These are historical failed attempts, not passes.

On 2026-10-25, the complete command
`python3.12 v0.5/scripts/verify-playbook.py --jobs 4` passed in an isolated Linux
container using Python 3.12.15 and Git 2.47.3: **726 public tests and 526 delivery
tests, with no failures or skips**. Documentation, links, privacy, generated
outputs and upstream cadence checks also passed; cadence is current through
2026-11-08. The container used a digest-recorded public-source snapshot, no
network, no host mounts and no credentials. The monitor suite requires root
and the Linux `SYS_ADMIN` capability for fanotify; all eleven monitor tests
passed with that capability, then the entire verifier passed. Earlier runs
superseded during environment correction were intentionally stopped and are
not counted as completed. No executable source changed to accommodate the host.

The human reaffirmed GPT-6.1 Sol/high for independent Verify. Official
[model documentation](https://learn.chatgpt.com/docs/models#gpt-61-sol) confirms
`gpt-6.1-sol`; active playbook preferences already use it. Routing guidance now
explains that saved defaults and runtime availability differ. A local preflight
failed and live discovery omitted this model. A user-directed fresh Conductor
tab subsequently completed the review, with authoritative runtime metadata
confirming Sol 6.1/high. No builder transcript was supplied. The reviewer
independently ran focused checks, assessed all eighteen specification criteria
and twenty-one scenarios, and answered the stage-08 security questions with a
manual OWASP/STRIDE pass. Standards and specification assessments pass; no
actionable documentation or security defect was found. Source hashes were
unchanged, and the audited review commands performed no source edits.

The original review qualification verdict was **blocked** because the tab disables
filesystem sandboxing. On 2026-10-25 the human explicitly selected “Accept this
review and finish the commit” in response to the completed-review exception
request. Qualification is therefore **pass-with-accepted-risk**: enforced
read-only access is waived for that completed report only. The original report
is preserved, and the exception does not claim that enforcement existed. The
model, fresh independent context, no-source-edit evidence and full-verifier gate
remain unchanged. No model substitution or general policy change was made.
The full report, runtime evidence, source digests and test logs remain local.

Only planning status, acceptance checkboxes and this evidence record changed
after the full run; live edition content and executable sources still match the
verified snapshot. Focused Markdown, links, privacy, manifest and whitespace
checks were refreshed for those record updates before the atomic commit.

New unit/integration tests: **n/a** — the approved seam is published instructions
and no executable interface changed. Browser/device/live-database checks:
**n/a** — no consumer UI or provider operation is introduced. These exclusions
do not waive fresh independent scenario/security review or the full verifier.

## Stage result

```yaml
playbook_result:
  outcome: pass-with-accepted-risk
  next_stage: "10"
  required_actions:
    - Return the completed Build handback with the atomic commit and verification evidence.
    - Await the separate human shipping decision before PR, publication or merge.
```

Shipping, tracker mutation and merge remain outside this Build authorization.

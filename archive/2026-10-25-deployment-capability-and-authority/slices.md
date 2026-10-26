# Deployment capability and existing authority — approved breakdown

Status: S1 complete in this atomic slice commit. On 2026-10-24 the human selected
“approved and build one here”: implement S1 and returned fixes in the current
Astra/high Codex tab at standard pace, verify independently, and commit atomically.
The [specification](spec.md) and its verification seam are approved.

## Why one slice

The demoable outcome is one coherent operating contract: an agent discovers
the capabilities it needs early, then carries an authorized data-affecting
operation through recovery verification without repeated approval requests or
expanded authority. The distinction belongs in foundations and must agree with
shipping, incident recovery, handoffs and the project template at the same time.

Splitting discovery, authority and recovery into separately finished slices
would require interim qualifications in the same documents and leave contradictory
entry points until the last slice. This documentation-only change fits one fresh
context. There is no runtime prefactor, schema change or expand–contract migration.
The sections below are checkpoints within S1, not separately dispatchable tasks.

## S1 — carry an authorized operation from capability discovery to verified recovery

**Type:** AFK — all product and scope decisions are settled. The human still
retains any later shipping or merge decision.

**Blocked by:** None. The specification, test seam and review qualification
are accepted; all required checks pass.

**Status:** complete. Full verification passes; fresh Sol 6.1/high standards/spec
and security assessments pass all scenarios. The human explicitly accepted the
report-only review on 2026-10-25. No new tracker issue was created.

**What it delivers:** A reader entering through prerequisites, alignment,
implementation, shipping, debug, the digest or the generated project instruction
template receives consistent instructions about existing authorization,
capability evidence, recovery coverage and unresolved blockers. A successor can
continue the same operation with bounded evidence and unchanged limits.

### Acceptance criteria

- [x] **Early discovery — spec 1–5:** relevant target, credentials, recovery route
  and exact verifier authentication are checked early. Sufficient scoped access
  works without broader access; credential presence is not target proof. Missing
  setup is requested once with redacted evidence while independent work proceeds.
  Changed capability invalidates relevant evidence, not the user's authority.
- [x] **Authority reuse — spec 7, 15 and 17:** necessary backups, isolated restore
  tests, scoped retries, verification-input repairs and owned-copy cleanup reuse
  the existing operation's authority. Delegated technical decisions are recorded.
  Only an uncovered target, scope, effect or limit requires another decision.
- [x] **Recovery gate — spec 6, 8–10 and 14:** actual data risk triggers backup
  and restoration, including application changes without migrations. Identify a
  retained recovery point, restore it in isolation, check affected usability and
  prove current pre-change/write coverage. Missing or failed evidence blocks the
  dependent action. Presentation-only work keeps the agreed default exception;
  stricter project policy and separate migration reversal rehearsal still apply.
- [x] **Cost and recovery boundaries — spec 11–13 and 17:** necessary temporary
  resources use approved limits; otherwise request one concrete cost decision.
  Preserve retained backups and cleanup ownership. Debug/canary recovery requires
  valid authority for the actual action and reuses it when already present.
  Deployment alone grants no downtime, data loss, live restore, broader credentials,
  new target, unauthorized migration or merge. Hard limits and failure guards hold.
- [x] **Handoffs and adoption — spec 16 and 18:** existing plan/verification/pickup
  records carry scope/provenance, target, runner, capability and restoration results,
  recovery coverage, limits and unresolved requests without secrets. Fresh Verify
  remains independent. Existing maintenance and reviewed upgrade paths preserve
  customizations, pins and a recoverable prior configuration.
- [x] **Coherent publication:** foundations and shipping own their respective
  rules; the other live entry points summarize or link them without conflicting
  prompts. Add the changelog Why line and regenerate affected edition/delivery
  outputs. Preserve notices and publication privacy.

### Implementation checkpoints

1. Record the current source gaps at the approved document seam. Confirm current
   branch/host PR state, the selected Build route and a usable independent Verify
   route before relying on them.
2. Update the shared authority/capability rule and the complete shipping/recovery
   procedure; reconcile prerequisite/alignment and exact-runner entry points,
   debug/canary language, pickup brief, template and digest.
3. Walk every acceptance scenario against the final reader-facing documents,
   run focused checks, then obtain fresh independent standards/spec and safety
   review. Correct in-scope findings and refresh affected verification.
4. Regenerate affected outputs, run the canonical verifier on the final candidate,
   and record the verified result. Make the single atomic slice commit with the
   required noreply author/committer identity. Stop at the Build handback; shipping
   and merge retain their own gates.

### Verification target

Use the approved **published workflow** seam and every row in the
[scenario matrix](alignment.md#acceptance-scenarios-to-carry-into-the-spec).
The fresh independent reviewer receives only the spec, this slice, changed
documents and bounded evidence, not the implementer's transcript. Each scenario
must identify the prescribed next action, required human decision, blocked work
and supporting source clause. Any contradictory entry point fails the slice.

Run the existing Markdown, link, privacy and affected generated-file checks;
run existing convention regressions for preserved routing, budget and failure
guards on the changed surfaces. Require the full canonical playbook verifier
on the final candidate. Stage-08 safety review specifically challenges accidental
authority expansion and secret exposure. A later PR must retain both required
CI jobs and review-thread handling.

New unit/integration tests and live browser/database tests are **n/a**, as approved
in the specification: this slice changes documentation, with no executable
interface or consumer UI. A required executable change returns to the agreed
test-seam decision before implementation. The reviewer must not describe static
document checks as proof that a deployed agent or provider behaves correctly.

### Completion and stop conditions

Done means all acceptance criteria have evidence, independent review findings
are resolved, required checks pass and the slice is committed. A blocked verifier
or required check remains incomplete; self-review does not replace independence.
Preserve cumulative three-identical-failure/three-no-progress guards, explicit
Stop, selected hard limits and actual quotas. Inherited time estimates remain
progress checkpoints. No new hard cap or permission to spend is introduced here.

## Approved execution choice

**Build one here** covers S1 and its returned fixes in the current Astra/high
Codex tab, at standard pace. This explicitly overrides the resolved edition
Build preference of GPT-6.1 Sol/medium for this run only. Fresh independent
Verify uses the edition GPT-6.1 Sol/high preference with enforced read-only
access and authoritative runtime evidence. Standard pace introduces no new
hard cap. Reuse the existing failure/no-progress guards and actual quotas.

**Accepted review exception — 2026-10-25.** After the completed Sol 6.1/high
review passed all twenty-one scenarios without actionable defects or source
edits, the human selected “Accept this review and finish the commit.” This
explicitly waives enforced read-only access for that completed review only.
Its report-only boundary and disabled filesystem sandbox remain disclosed;
the model, fresh context, runtime evidence and all other gates are unchanged.
The full canonical verifier passed all 1,252 tests without skips. See the
[review evidence](review-notes.md). This exception does not change the edition's
default verification requirements or authorize shipping.

## Stage result

```yaml
playbook_result:
  outcome: slice-complete
  next_stage: "10"
  required_actions:
    - Return the completed Build handback with the atomic commit and verification evidence.
    - Await the separate human shipping decision before PR, publication or merge.
```

Keep the two source work items in the same workspace. No duplicate tracker
issue, shipping, PR or merge is included in this Build authorization.

# Field report — Playbook configuration UI

- **Project:** public playbook maintainer repository; configuration feature.
- **Playbook version:** V0.5.0 live edition; root consumer runtime state intentionally absent.
- **Period covered:** 2026-09-29 → 2026-10-08, through feature PR #20 and doc-close PR #22.
- **Slices shipped this period:** 9 (S1–S7, owner-amended S7a, S8); one shipped feature.

## Observational eval baseline

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---|---|---|---|
| 2026-09-29 → 2026-10-08 | 9 | unavailable — later whole-diff corrections cross accepted slices; exact corrected-slice numerator not recoverable | 8d 5h 47m 01s / 8d 5h 47m 01s (one feature) | unavailable — complete pass ledger is private; at least 10 named accepted rounds recoverable | unavailable — executed defects documented, but medium+ severity labels not recoverable |

Timing uses one feature: first implementation `9e5ca3e` at
2026-09-29T22:39:05Z to PR #20 merge at 2026-10-08T04:26:06Z, not just its final
continuation commits. The ten named accepted rounds are S1–S7, S7a, whole-diff
Verify 6 and final Fable review; a lower bound rather than a complete count.
Execution-proven medium+ catch attribution cannot be reconstructed from public
summaries. No targets or gates follow before a three-period baseline review.

## Proof events

### 1. Independent verifier caught a real defect

- 2026-10-01, S5 Verify 1: reproduced late backup mutation during rollback,
  incomplete personal completion and an implicit Guided choice. Repair `faa73d1`
  then passed fresh Verify 2's 16 new probes per interpreter and prior regressions.
- 2026-10-03, whole-diff Verify 5: bootstrap published seeds after selected
  source/proof/contract/approval/resolution/catalog drift. Both interpreters
  passed 16 unchanged controls but failed all 96 mutation cases. A minimal library
  and real bootstrap CLI reproduction also failed. Repair `673c35c` made every
  saver caller supply admission; fresh Verify 6 accepted it. The canonical run
  was not started on the rejected candidate; passing public tests did not clear it.
- Severity: unavailable — summaries establish genuine executed defects and
  mandatory rejection, but not original medium+ labels. Do not count invented
  severity in the observational catch column.
- Would self-review plausibly have caught them? Unknown; earlier acceptance and
  passing selected tests did not find them. Fresh probes demonstrably did.

Evidence: [execution ledger](../../archive/2026-10-08-playbook-config-ui/execution.md),
shipped repair commits and [AC mapping](../../archive/2026-10-08-playbook-config-ui/acceptance-evidence.md).
The project copy uses the same repository-root evidence, as indexed by its retro.

### 2. A run-level ceiling tripped and paused correctly

No qualifying run-level wall-time/iteration/no-progress or cost/quota pause-and-report
receipt is recoverable. The ledger explicitly selected no invented time/token/cost/
dispatch ceiling. Exhausted ordinary/Astra repair allowances and two custom
qualification attempts are real stopping boundaries, but are not relabelled as
run-level ceiling proof or a deliberate drill. Interrupted runs and capacity retry
remain failures/limitations without ceiling-credit inference.

### 3. Acceptance-criteria gate refused a build

No evidenced refusal to start stage 07 for a missing verification target. The
approved breakdown already supplies slice criteria/targets. Rejecting a bad
implementation or drifted source is valuable but is not this proof event.

### 4. Structured escalation instead of thrashing

The 2026-10-03 ledger records exhausted repairs, stop/route decisions and explicit
owner extensions: S7 used both additional Astra cycles, then an explicitly
selected resumed Sol route; whole-diff Verify 5 blocked further work pending a new
route decision, followed by a maintainer-authorised repair and fresh Verify 6.
Those boundaries and cumulative history are useful escalation evidence.
The complete blocker/evidence/attempts/hypothesis/ask template receipts are not
publicly recoverable, so formal structured-escalation proof remains unavailable.
No extension is treated as unused, reset, or permission for another qualification.

## Qualification and mission dispositions

Custom-source qualification denominator: **two attempts used, zero remaining**;
the source was admitted after those attempts. Individual attempt dispositions are
not recoverable here and are not fabricated. Ordinary custom invocation is a
separate denominator: the first captured forbidden history and interrupted a
fixture run and remains **nonqualifying**; a later compliant fresh invocation at
`c987205` passed. S2 also retains a technically passing but context-contaminated
review and a separate qualifying fresh review. Do not merge those reports into
one success or count them as new qualification attempts.

No registered delivery-mission inventory/attempt receipts for this feature are
available in the supplied public evidence. Do not manufacture a mission total or
reinterpret ordinary build-all/S8 reviews as qualifying K4.1 missions. Any existing
mission dispositions (qualifying, nonqualifying, cancelled or externally completed)
remain immutable with their original denominators; this retro creates or amends
none. Human feature shipment is a product outcome, not repair of a failed
qualification control chain and not Tier B/C or non-bypass proof.

## Friction

- Repeated source-parser and save-boundary repairs increased work. Independent
  rejection had concrete value; repeated full suites and packaging/environment
  failures are retained costs without a fabricated total cost or elapsed-savings claim.
- Full-access actual hosts were manually bounded, not filesystem-enforced
  read-only. The failed enforced discovery route, forbidden history capture,
  privacy-capture failure, fixture interruption, clock amendment, capacity retry
  and offline packaging/audit diagnostics remain without pass credit.
- A same-value Mac preset initially missed changed-draft cancellation proof;
  the differing-Plan walkthrough supplied it. Historical evidence reconciliation
  briefly retained a native-handoff underclaim; PR #22 corrected it.
- Recovery evidence remained unignored after successful Apply. The separately
  authorised bootstrap/upgrade ignore follow-up owns a bounded correction;
  deleting receipts would undermine recovery rather than reduce ceremony safely.
- Cadence dismissal counts unavailable — no root runtime log. The one explicit
  retro deferral stayed visible. Monthly drift remains separately owned and due.

## Verdict

**Working as expected? Partially.** Independent checking demonstrably caught real
boundary defects and final host/candidate gates were admitted. Contaminated reviews,
privacy failures, weaker permissions and incomplete provider/cost evidence remain
limitations; technical success and human shipment do not erase them. Main CI on
feature merge passed; PR #22's main run is separately checked rather than inferred.

**Recommended playbook action:** keep existing exact-source, exact-candidate,
independence and explicit-route rules; record these incidents without duplicating
ceremony. Assign private recovery-artifact handling to the already authorised
product follow-up and released-source drift to maintenance. Collect complete
severity/escalation/mission attribution in future applicable retros before claiming
quantified proof. No speculative code, new telemetry or blanket model substitution.

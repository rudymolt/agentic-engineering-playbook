# Retro — 2026-10-13 · Checkpoint performance

Scope: feature ship, PR #41. Period: 2026-10-09 → 2026-10-13.
Manual stage-owned retrospective; no packaged upstream retro or memory skill
was invoked. This maintainer checkout has no consumer runtime state file.

## 1. What worked

Complete measurements and independent source/receipt review preserved original
assertions, matrices and native operation order. S2's owned foreground repacking,
S3's same-path independent restoration and S5's Unicode lookup yielded retained
improvements. The maintainer explicitly accepted those gains rather than
silently relabelling unmet speed targets. Final head `084857c` passed all 92
benchmark tests, the no-skip full verifier and both required CI jobs; PR #41
merged as `20eeb04` with the same tree and noreply identities.

## 2. What didn't

Repeated validation and proposal reuse did not justify retention. Failure
observability required several bounded corrections; ordinary passing cases
could mask ownership and optional-source startup failures. The last two-threshold
repack experiment failed its recovery/combined retention criteria and was rejected.

This exposed Blind and Tangled risks: missing failure provenance and complicated
observation/containment boundaries. Independent executable checks and retained
failed receipts countered those risks. Original watchdog cause stays unknown;
failed qualifications are not called flakes or reused as successful evidence.

## 3. What we learned

- Supported-path failure evidence must remain optional to native execution.
- Full-file, matched measurements prevent favorable individual cases from
  hiding a regression or missing work.
- Safe fixture reuse preserves path-bound authority and independent object
  storage; an apparent copy is not an interchangeable approved identity.
- Stop exploration when the human accepts measured progress; retain unmet
  original targets and rejected experiments rather than rewriting history.

## 4. Cadence review

No root project cadence state is configured; per-slice deferral counts are
unavailable. Monthly upstream review remains current through 2026-11-08.
No cadence, model setting, skill pin or global Git setting was changed.
Future relevant tool/runner/source changes require compatibility checks as
recorded in the durable fixture decision.

## 5. Learning coverage and observational eval

Checked the public spec/slice/evidence record, merged PR #41, final head
`084857c`, and concrete independent functional, qualification-gap and experiment
rejection receipts. S2 removes repeated loose-object transport packing; S3
removes repeated initial seed construction while preserving native matrix calls.
Those two retained slices can be explained from the durable source/measurement
record. No persistent `/learn` store was used.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | --- | --- | --- | --- | --- |
| 2026-10-09 → 2026-10-13 | 5 retained; S4 rejected | unavailable — reliable post-gate slice attribution not consolidated | 77 h 50 m 20 s / same; one feature branch | unavailable — consolidated dispatch count not retained publicly | unavailable — consolidated catch count not retained publicly |

Time-to-merge uses first implementation commit `25774bc` at
2026-10-09T23:13:23Z and merge at 2026-10-13T05:03:43Z, at feature/branch
rather than individual slice granularity. Dispatch and post-gate rework totals
are unavailable without reconstructing private history; no estimates fill them.

## 6. Promotion candidates

Promote the path-bound fixture ownership decision to
[ADR 0001](../../docs/adr/0001-checkpoint-fixtures-and-acceptance.md).
The [public measurement record](../../bench/test-runtime/CHECKPOINT-PERFORMANCE.md)
retains finite evidence limits and the maintainer's acceptance. No new vocabulary,
project-wide agent rule or generalized playbook invariant is introduced.

## 7. Field report

Proof events and accumulated friction are recorded in the matching
[field report](../../analysis/field-reports/2026-10-13-checkpoint-performance.md)
with the same observational row. It makes no autonomy or universality claim.

## 7b. Decisions and follow-ups

Stop further performance experiments and retain 512. V0.5.2 tagging follows
release metadata review, the final verifier and human closeout merge. The
custom-object compatibility question remains a disclosed limitation, with no
new implementation or investigation selected by this release.

## 8. State updates applied

- Planning/archive indexes reflect the shipped feature; mirrored maintainer
  state records production verification, doc-close and this retrospective.
- No consumer state file or cadence tuning is needed in this maintainer checkout.
- The changelog and both current-release pointers select V0.5.2; manifests and
  the generated dashboard are regenerated before closeout commit.
- The observational row explains evidence gaps; no invented counts or averages.
- The field report carries the same row and reviewed proof-event/friction facts.

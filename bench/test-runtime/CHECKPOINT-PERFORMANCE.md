# Checkpoint performance acceptance — 2026-10-13

The maintainer accepts the measured improvements for this release and stops
further performance experiments, provided correctness, safety, privacy and
release checks pass. Four original absolute speed targets remain unmet; this
acceptance changes their release disposition, not their measured results.

## Retained implementation

- Foreground repacking at 512 loose objects in exclusively owned, quiescent
  recovery/coordinator fixture remotes; transport clones remain enabled.
- Independent restoration of immutable recovery seeds to the same reserved
  paths, preserving approved URLs, history and within-test resets.
- Equivalent Unicode character lookup with fresh guidance admission.
- Bounded standalone/serial failure evidence that preserves native execution
  and leaves unsupported metadata unknown.

Validation reuse and proposal retention were rejected. The latest experiment
lowered both fixture repack thresholds to 256 and was also rejected: recovery's
median regressed by 0.64%, while the combined median gain was only 1.64%.
Independent review accepts rejection; the shipped threshold remains 512.
No further cadence experiment is part of this release.

## Complete reference observations

Frozen source: `5e7946b6709bdff168946493be94c10def75276f`.
Baseline: `a3daedf03b24c5b3feb41d5953272d281de7b283`.
Guidance comparator: `9d8dc1a5ec583aa3cd727a52d06dcd5438bf2a8e`.
Runner: Ubuntu 24.04.5, image `20261004.327.1`, four x86_64 CPUs,
Python 3.12.15 and Git 2.55.0. Standalone/serial delivery uses one privileged
worker; required delivery CI uses three workers. Three alternating complete
baseline/candidate pairs ran sequentially. Diagnostics ran separately.

| Measurement | Baseline median | Candidate median | Observed reduction | Original target disposition |
| --- | ---: | ---: | ---: | --- |
| Recovery complete file | 357.724 s | 336.594 s | 5.9% | Unmet: every run below 120 s |
| Coordinator complete file | 151.863 s | 144.523 s | 4.8% | Unmet: every run below 60 s |
| Serial K4.1 including checks and overhead | 673.312 s | 642.883 s | 4.5% | Unmet: every run below 360 s |
| Guidance complete three-file group | 275.648 s | 192.587 s | 30.1% | Met: median ratio 0.699, at most 0.80 |

Candidate recovery observations: 336.594 / 335.134 / 337.409 s.
Candidate coordinator observations: 144.622 / 144.424 / 144.523 s.
Candidate serial observations: 644.020 / 642.883 / 640.787 s.
Required delivery CI job observations: 336 / 313 / 299 s; the original
requirement that all three remain below 300 s is unmet.
The complete no-skip three-worker release verifier returned zero in 707.578 s,
including owned source staging and cleanup; its original 1,200 s limit is met.
These durations attest the frozen source above, not subsequent documentation
commits or a different release runner. Final release checks attest their own head.

## Correctness and evidence limits

All 526 delivery IDs and 154 guidance IDs completed. Original test assertions,
matrices and native within-test operation order/outcomes are preserved.
Recovery push/clone/fetch/remote-ref attempts changed from
6,430/888/2,151/2,199 to 6,170/834/2,151/2,172, reconciled solely to removed
repeated initial seed construction. Coordinator attempts are unchanged at
3,236/450/749/775. Foreground repacks are separately recorded additions.
Fresh independent source/receipt review found no new actionable source-safety
finding on the retained candidate; public-content checks passed.

Failure evidence is a bounded supported-path observation, not universal
arbitrary custom-object, audit, saved-callable or concurrent compatibility.
The pre-existing custom-object isolation question remains unresolved. Two
trusted native-frame `self` locals reads remain an audit-visible footprint;
1,024-event and 64-frame export caps do not bound total traceback traversal.
Failed and interrupted qualifications remain excluded; the original watchdog
cause remains unknown. No durability, URL/cardinality, CAS, lease, lineage,
publication/reload boundary, matrix or assertion was relaxed for performance.
Raw receipts and failed experiments are retained privately. Historical release
observations with different runners/inventories are not controlled estimates
of this feature's benefit.

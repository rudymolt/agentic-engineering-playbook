# Field report — Conductor workspace metadata

Project: public Playbook maintainer repository. Edition: V0.5.0. Source baseline:
v0.5.7; this source change shipped in PR #58 without a new release tag. Period:
2026-11-15. One slice shipped. No consumer runtime state or private identifiers
are included.

## Observational eval baseline

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | ---: | ---: | --- | ---: | ---: |
| 2026-11-15 | 1 | 0/1 | 19m 1s / 19m 1s | 2 | 0 |

Feature-level time, two independent review axes, no post-acceptance correction.
The VM permission finding is not counted as a product catch. See the
[retro](../../planning/retros/2026-11-15-conductor-workspace-metadata.md).

## Proof events

No qualifying product catch, run-level ceiling trip, acceptance-criteria refusal
or structured escalation occurred. The complete canonical verifier and both
required PR CI jobs passed; fresh reviewers found no product defects.

## Friction

Technical interview questions created unnecessary cognitive load for a
non-engineer. Human questions should concern outcomes and meaningful tradeoffs;
routine engineering decisions remain agent work.

The Cloud VM combined a private home directory with elevated file-access
capabilities. Isolated test subprocesses could not traverse the original source
location, while chmod-based failure injection could still write under elevated
permissions. Bounding-set-only removal did not fix the effective permissions.
An accessible exact-candidate checkout, explicit privilege control and executed
permission probe resolved the problem. The original failure also reproduced on
unchanged main; independent unprivileged focused verification passed. Missing
Python 3.12 was a separate host prerequisite, repaired before final verification.

## Verdict

Partially working as expected: existing interface tests and independent checks
protected the product contract, but interview and runner assumptions wasted
effort. Collect more evidence before changing global process rules. Keep
installation and startup qualification separate; use real host evidence before
expanding support claims. No automatic consumer upgrade or setting change follows.

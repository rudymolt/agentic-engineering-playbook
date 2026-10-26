# Field report — Capability and authority

Project: public playbook maintainer checkout, V0.5 edition.
Installed consumer release: n/a; development source, with V0.5.2 still published.
Period: 2026-10-24 → 2026-10-25. One integrated slice shipped in PR #46.

## Observational eval baseline

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 → 2026-10-25 | 1 | 1/1 at PR level; CI environment repair after review | 41 m 55 s / same | 1 accepted with a scoped permission exception | 0 |

The [retrospective](../../planning/retros/2026-10-25-capability-and-authority.md)
defines the timestamps, attribution and evidence limits. CI is not counted as
an independent verifier catch; the documentation itself needed no post-review
correction. These observations create no targets or autonomy claim.

## Proof events

1. **Independent verifier caught a real defect:** none. Sol 6.1/high found no
   actionable defect across 18 requirements and 21 scenarios.
2. **Run-level ceiling trip:** none recorded. Environment corrections and
   superseded runs do not establish a budget-ceiling event.
3. **Acceptance-criteria refusal:** none. Alignment, specification and the
   verification seam were approved before implementation.
4. **Structured escalation:** the exact first runner rejected the selected
   model. The blocker was carried to the human, who identified another runner.
   Its completed report remained blocked on read-only enforcement until the
   human accepted that one exception. This demonstrates an explicit capability
   and permission decision; it does not establish a measured retry-ceiling
   event or enforced read-only review.

## Friction

Model availability, authentication and filesystem enforcement varied by runner.
An environment that could launch the review was not automatically a qualifying
review environment. Later, hosted-image drift exposed Python lookup through
sudo's reset PATH. Local container verification also needed child reaping.
Failed runs remained visible and were replaced by complete successful evidence.
The CI repair added a behavioral regression rather than weakening a test gate.

Cadence dismissal counts are unavailable in this maintainer checkout. No
claim is made that repeated confirmation or environment setup has been solved
in every consumer; this is one feature's evidence.

## Verdict

Partially working as expected: exact capability checks and explicit exception
handling preserved the selected model and evidence limits, but late environment
qualification caused avoidable work. Keep the shipped early-discovery rule and
the deterministic CI regression. Collect more evidence before adding a generic
runner workflow or changing review permissions. No new policy is introduced.

# Retro — 2026-11-09 · Consumer workflow reliability

Scope: feature ship, including public checkpoint guidance and private installed
qualification. Period: 8–9 November 2026. The owner delegated autonomous completion;
this is an evidence-based agent retro, not a claimed human discussion.

## What worked

Independent review caught a publication regression that trusted working-tree
state while checking committed bases. The corrected test reads both from HEAD.
The minimal consumer repair and deliberate adoption then passed fresh review.
Separate setup, catalog, inventory, behavior and replay gates prevented CLI
success from being reported as automatic runtime availability.

## What did not

Incomplete relocation publication caused a real fresh-start failure. An auditor
then applied a stronger catalog bar than the accepted contract and initially
reported a false failure. Both are retained, with the latter corrected additively.
This is the Blind anti-pattern: missing historical evidence changed the apparent
contract. The repeated verification environment assumptions also consumed calls;
the successful Linux privilege recipe should be reused when applicable.

## Learning coverage and observational eval

Reviewed the four slice contracts, PR #54, exact release receipt, independent
repair/adoption/runtime verdicts and final lifecycle/replay evidence. Sampling S1
and S3 explains both the estimate semantics and the committed-state regression.
The lessons are captured here and in the durable qualification report. No GBrain
learning write was performed; this retro does not imply one.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | ---: | --- | --- | --- | --- |
| 8–9 November 2026 | 4 feature outcomes across public and private work | unavailable — review records do not supply a consistent post-gate slice denominator | 108m27s / 108m27s for public PR #54 only; private duration recorded separately | unavailable — scoped review phases overlap; individual verdicts retained | at least 1 — committed-state publication regression reproduced independently |

These are observational gaps, not estimates or new performance gates.

## Cadence and promotions

November upstream review completed with pins unchanged; next due 8 December.
No cadence threshold is tuned and no unrelated feature/closeout is cleared.
No new vocabulary or hard-to-reverse architecture decision needs an ADR.
The publication-unit lesson is already in consumer guidance and the regression.
Policy-aware discovery belongs in the durable qualification report. A private
Preview target-precedence incident supports a separate follow-up for preventative
provider binding checks; this closeout does not silently widen installer scope.

## Field report and follow-ups

An independent-verifier catch, compatibility refusals, bounded phase stops and
verification friction occurred. The sanitized field report accompanies this
retro. Human discussion is deferred to the owner's next review; no invented
product decisions or blanket workflow approval is recorded. Requalification
remains required after relevant upstream or host changes.

## State updates applied

- The maintainer has no root runtime state; planning/STATUS.md mirrors ship,
  doc-close and retro, increments only this feature and preserves seven others.
- This feature's planning is archived after durable documentation promotion.
- Current release pointers remain v0.5.6; this documentary closeout creates no tag.
- Cadence settings remain unchanged. The changelog records the documentation
  outcome and Why; generated status and manifests are refreshed.
- Learning coverage, observational gaps and the field-report decision are recorded.

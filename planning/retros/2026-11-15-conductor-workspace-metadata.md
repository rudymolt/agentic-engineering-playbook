# Retro — 2026-11-15 · Conductor workspace metadata

Scope: feature-ship. Period: 2026-11-15. One guidance/test slice shipped in
PR #58 as `4dd4f1a`; candidate `16bcadc` passed two fresh independent reviews.

## 1. What worked

The audit separated a consumer receipt assumption from installer behavior.
Existing launcher and composed-command seams supported nine metadata cases,
both host modes, sh/bash child failures and preservation checks. No production
installer change or new receipt abstraction was needed. Independent reviewers
executed tests and explicitly checked for missing requirements.

## 2. What didn't

Alignment asked technical questions of a non-engineer and spread confirmation
across too many turns. The owner requested simpler questions; subsequent
communication used outcomes and kept routine engineering choices with the agent.
This was avoidable ceremony, not a missing product decision.

Fixture assumptions about terminating commands, local discovery and multiline
JSON caused early test failures. VM directory access, elevated capabilities and
missing Python 3.12 then obscured broad verification. Actual permission probes
and an accessible exact-commit checkout resolved the runner issues. This fits
the Blind anti-pattern: runner semantics were initially assumed rather than
observed. It did not justify weakening tests or changing product behavior.

## 3. What we learned

- Separate installation outcome, receipt completeness and host-bound startup
  qualification. Promoted to the glossary and metadata guidance in PR #58.
- Ask humans about outcomes; resolve routine engineering choices independently.
  Candidate for process review, with no new global rule from this one session.
- Validate real privilege behavior before permission-failure tests. Retain the
  runner diagnosis here; broader prerequisite changes need separate review.

## 4. Cadence review

No cadence dismissals or threshold changes in this scope. Maintainer tracking
uses planning status rather than consumer runtime state. Existing upstream
maintenance remains due 2026-12-08, with compatibility checks on relevant upgrades
and reviewed adoption preserving customizations. No per-turn check was added.

## 5. Learning coverage and observational eval

Reviewed the sole shipped slice, candidate/merge trees, PR checks, both independent
verdicts and local verification evidence. Learning coverage is complete for this
feature. No persistent learning store was used in the disposable VM; provider
usage and authoritative runtime model/effort telemetry remain unavailable.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | ---: | ---: | --- | ---: | ---: |
| 2026-11-15 | 1 | 0/1 | 19m 1s / 19m 1s | 2 | 0 |

Time uses the first implementation commit (19:15:58 UTC) to PR merge (19:34:59
UTC), at feature granularity. Verifier passes count the two independent axes;
the host permission finding is not a medium-or-higher product defect. No product
changes occurred after review acceptance. These observations create no targets.

## 6. Promotion candidates

The vocabulary and metadata guidance already shipped with their changelog Why
line. No additional skill, ADR, settings change or project-wide instruction is
needed in this closeout. Collect more evidence before changing interview or
verification prerequisites globally.

## 7. Field report

No qualifying product catch, ceiling trip, missing-criteria refusal or structured
escalation occurred. Repeated runner and interview friction is recorded in the
[field report](../../analysis/field-reports/2026-11-15-conductor-workspace-metadata.md),
with the same observational row. Failed experiments remain in closeout evidence.

## 7b. Decisions and follow-ups

- Consumer maintainer: review and link the published receipt writer/checker
  repair when available; preserve customization provenance and release pins.
- Qualification owner: obtain effective saved setup, fresh automatic execution
  and actual host binding before any expanded support claim. This requires a
  separately bounded live run; repository publication is not that proof.
- Maintainer: consider the communication/runner lessons at the next maintenance
  review, without treating them as automatic configuration changes.

## 8. State updates applied

- Maintainer planning status records shipment, doc-close and retro; consumer
  `.playbook-state.yml` is intentionally absent.
- Archived this feature only; seven unrelated active features remain.
- Cadences and current tagged-release pointers are unchanged. No additional
  upward process promotion requires a new changelog entry.
- Learning coverage, observational eval and friction field report are complete.
- This closeout and retro share one second PR; publication awaits its merge.

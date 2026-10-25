# Retro — 2026-10-25 · Capability and authority

Scope: feature ship, PR #46. Period: 2026-10-24 → 2026-10-25.
Manual stage-owned retrospective using the repository template; no packaged
upstream retro or persistent memory skill was invoked.

## 1. What worked

One integrated slice kept capability, authorization and recovery instructions
consistent across entry points. Fresh Sol 6.1/high review checked 18 requirements
and 21 scenarios. The full final verifier passed 1,253 tests, and both required
CI jobs passed before and after the human merge. The
[closeout record](../../archive/2026-10-25-deployment-capability-and-authority/closeout.md)
preserves exact revisions and the narrow review exception.

## 2. What didn't

The selected verifier was unavailable in the first runner. A different runner
supported the model but did not enforce read-only access, requiring an explicit
decision about the completed report. Saved model preferences alone did not
establish either capability or permission enforcement.

CI exposed another environment gap: sudo discarded the selected Python PATH
on a newer Ubuntu image. Local verification also required Linux capabilities
and an init process for child reaping. Blind and Tangled risks appeared in
assuming runner equivalence; preserving failed receipts and checking exact
boundaries prevented them from becoming claimed passes. There is no evidence
of Nodding, Amnesiac or Manual failures in this bounded feature record.

## 3. What we learned

- Qualify the exact verifier runner, model and permission boundary early.
  The shipped discovery guidance already captures this lesson.
- An absolute parent interpreter does not fix child PATH lookup after sudo.
  The executable CI regression is the appropriate durable check.
- Isolation needs a usable process lifecycle as well as filesystem boundaries.
  Retain the container init requirement as verification-environment evidence;
  do not change product behavior to accommodate an incomplete fixture host.

## 4. Cadence review

This maintainer checkout has no root consumer cadence state; deferral counts
are unavailable. Upstream maintenance remains current through 2026-11-08.
No cadence, model default, skill pin or user configuration changes here.
Relevant runner/tool changes require renewed compatibility checks; consumer
adoption remains a reviewed upgrade that preserves customizations.

## 5. Learning coverage and observational eval

Checked the single shipped slice, its review evidence, Git commit timestamps,
PR #46, the CI repair and successful main CI. There is one eligible slice to
sample: early capability proof plus scoped authorization and current recovery
coverage. No persistent `/learn` store was used; the lessons are recorded here.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
| --- | --- | --- | --- | --- | --- |
| 2026-10-24 → 2026-10-25 | 1 | 1/1 at PR level; CI environment repair after review | 41 m 55 s / same | 1 accepted with a scoped permission exception | 0 |

Time runs from first implementation commit `83204f6` at 2026-10-25T05:37:23Z
to merge at 06:19:18Z. Rework counts the later CI fix in the same PR; reviewed
process prose did not change. Standards/spec/security assessments came from
one fresh review session. CI and implementer checks are not independent
verifier passes or catches. These observations introduce no performance target.

## 6. Promotion candidates

The policy lesson and CI regression already shipped in PR #46. No additional
general rule, glossary term, ADR or skill is justified by this closeout.
Retain the init-process lesson in the evidence record and reassess if it recurs.
The one-review permission exception does not become a default or precedent.

## 7. Field report

The [field report](../../analysis/field-reports/2026-10-25-capability-and-authority.md)
records verifier-route escalation and environment friction with the same eval
row. No independent medium-or-higher defect catch, run-level ceiling trip or
acceptance-criteria refusal occurred in the retained evidence. This ordinary
human-led feature is not a qualified automated delivery mission.

## 7b. Decisions and follow-ups

One closeout PR carries archive, status, retrospective and release-note updates.
Tagging and consumer rollout remain separate decisions. Further playbook
promotions need new evidence; none are silently added during cleanup.

## 8. State updates applied

- [x] Mirrored maintainer state in `planning/STATUS.md` records ship, production
  verification, doc-close and retro for this feature; no consumer state created.
- [x] Cadence tuning assessed; no change warranted.
- [x] Changelog closeout note added; published V0.5.2 pointers retained.
- [x] Learning coverage and observational eval recorded with attribution limits.
- [x] Proof events/friction checked and copied into the matching field report.

Map QA and harness-maintenance credit: n/a — no maintainer verification harness
is adopted. The closeout becomes published only when this PR is human-merged.

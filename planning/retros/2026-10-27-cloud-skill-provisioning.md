# Retro — 2026-10-27 · Cloud skill provisioning

Scope: feature-ship. Period: 2026-10-24 through PR #48's merge on 2026-10-27.
Maintainer source is the V0.5 edition; V0.5.3 publication and exact-release
consumer qualification remain separate release follow-ups.

## 1. What worked

- PR #48 shipped eleven bundled skills with complete support, notices and
  invocation metadata. Explicit adoption and exact annotated-release recovery
  preserve the distinction between installed, discovered and compatible.
- Fresh independent execution caught edge cases that passing regressions missed:
  S3 source discovery could execute fsmonitor, and S4 could block on a FIFO.
  Returned fixes received fresh verification before acceptance.
- The final tree `8c7db8d` passed independent review without findings and the
  canonical verifier with 1,346 reported executions. The human's squash merge
  `b2262ef` has that same tree and noreply identities.
- The actual fresh/recreated Cloud matrix proved retained customization loading
  in both runtimes. The bounded local round preserved personal state and the pin.

## 2. What didn't

The setup gate initially required Python 3.10 while Cloud provided 3.9.25. The
reviewed fix supports 3.9; fixture success had not established the host image's
actual prerequisite. Later startup lacked installation output despite the
tracked settings file. Explicit repository Setup configuration worked, but
host logs did not establish the exact settings-precedence cause. This is a
Blind discovery risk, not evidence that the unresolved activation route works.

Personal same-name skills won default lookup. Explicit selection worked on
bounded routes; generic project precedence remains unsupported. Standalone
Codex account access failed while the Conductor-hosted route succeeded.
Observer writes, stdin leakage and JSON timestamp rounding weakened individual
observations; the report retains those limits. Worker self-reported turn counts
were inadequate for budget accounting, so native receipts supplied the totals.

## 3. What we learned

- Prove startup readiness before agent initialization and capture the original
  catalog before fallback reads. Keep effective host-setting readback separate
  from tracked configuration → durable runtime report and ADR 0002.
- Preserve source identity through invocation and after drift; aliases do not
  imply precedence or stage authority → provisioning guide and existing glossary.
- Keep consumer proof tied to a real published annotated release. A candidate
  success cannot close that cell → consumer qualification procedure.
- Close stdin for noninteractive observers and compare nanosecond metadata within
  one process → retained qualification methodology; no new global rule required.

## 4. Cadence review

This maintainer repository intentionally has no root consumer state file.
No dismissal log establishes repeated cadence skips; counts are unavailable,
not zero. Keep the monthly upstream review and compatibility checks before
source/runtime/model/settings changes. No threshold or setting is changed.
The next existing upstream review remains due 2026-11-08.

## 5. Learning coverage and observational eval

Evidence checked: planning/STATUS's mirrored counters, PR #48's eleven commits
and merge timestamp, final review/verifier receipts, S3 and S4 standards verdicts,
the last A8 recovery review, the runtime report and local/Cloud budget receipts.
The project `/learn` search returned no stored entries; the concrete lessons
above and the field report fill that coverage gap. No full transcript recount
or invented complete denominator is used.

A reproducible random sample (seed 20261027) selected S2 and S1. S1 commit
`740d5533` supplies the complete pinned bundle and preview/install/check boundary;
S2 commit `8ffdcf8c` adds explicit committed retention and journaled recovery.
The public provisioner tests cover no-write repeats, recreated retained content,
interrupted replacement/recovery and later-edit refusal. Their purpose and
preservation contract are explainable from current code and the durable guide.

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---|---|---|---|
| 2026-10-24 → 2026-10-27 | 7 (S7 selected maintainer scope) | unavailable — passed-gate timing is not normalized per slice | 54h 53m 57s / 54h 53m 57s (one feature PR) | 4 sampled; total unavailable | 2 sampled passes with confirmed medium+ catches; total unavailable |

Time-to-merge uses first feature implementation commit `740d5533` at
2026-10-24T21:04:17Z to merge at 2026-10-27T03:58:14Z. This is one feature-level
observation, not seven independently timed PRs. The four sampled verifier passes
are S3 standards, S4 standards, the final A8 recovery review and the final feature
review; "pass" here means a verification attempt, including a blocked verdict.
S3 and S4 each executed medium+ reproductions. Counts are a documented sample,
not a full-period total. S7 is shipped only for the accepted maintainer routes.
These observations introduce no performance target or new gate.

The generic retro helper found three main commits in this window but reported
zero test files because its filename conventions miss this repository's Python
suite; direct inventory finds 71 `test_*.py` files. Its test ratio is not used.
No prior same-window local history or real shortcut markers were found.

## 6. Promotion candidates

Promote the host-activation trade-off into ADR 0002 and preserve the full dated
report under docs. Existing glossary terms already separate installation,
discovery, compatibility and customization. No UI language changed. Existing
stage rules already require actual runtime proof, native accounting and fresh
review; additional global instructions would duplicate them. Keep stronger
observer-harness checks as a future targeted improvement, without changing
personal settings or runtime defaults during closeout.

## 7. Field report

[The field report](../../analysis/field-reports/2026-10-27-cloud-skill-provisioning.md)
records executed independent catches, the exhausted first-round budget and the
three-failure escalation. No acceptance-criteria build refusal was observed;
the incompatible reviewer refusal is a different boundary and is not counted
as that proof event.

## 7b. Decisions and follow-ups

- Publish V0.5.3 after this closeout PR's human merge and final release gates.
  Owner: release maintainer; due before consumer release qualification.
- Execute the [consumer procedure](../../docs/cloud-skill-provisioning/consumer-qualification.md)
  against the published tag. Owner: release maintainer; due at publication,
  before claiming consumer qualification. No additional Cloud runs are implied.
- Keep branch-TOML activation, default project precedence and standalone Codex
  login repair outside the qualified scope. Revisit only when needed, with
  new evidence and existing authority/resource limits checked first.
- Delivery disposition: human-merged standard feature PR. No K4.1 delivery
  mission was admitted; this is not autonomous merge or Tier B/C evidence.

## 8. State updates applied

- [x] Retro/doc-close timestamps and shipped-feature counter mirrored in
  planning/STATUS.md; no root consumer state was invented. Both required
  post-merge CI jobs passed in run `40447115724`; the verified tree and
  noreply readback close production verification for the maintainer route.
  The completed closeout entry is cleared; consumer qualification stays open.
- [x] Cadence policy reviewed; no tuning justified and no clock reset claimed.
- [x] V0.5.3 changelog contains the closeout and its Why; current-release pointers
  are prepared in the same closeout PR.
- [x] Learning coverage and observational eval checked; missing denominators
  remain explicit rather than estimated.
- [x] Field-report proof events and friction reviewed and recorded with the
  same eval row. Other feature ownership remains unchanged.

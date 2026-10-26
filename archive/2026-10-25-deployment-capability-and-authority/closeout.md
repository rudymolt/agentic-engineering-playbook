# Capability and authority — feature closeout

Shipped 2026-10-25 in PR #46 as `8f6a2f0`. The human requested one documentation
closeout PR after merging.

## Production and verification evidence

- The merge tree exactly matches verified feature head `a3b732c`. The sole
  newly added main commit has noreply author and committer identities.
- Both required jobs, `edition` and `delivery`, passed on the PR and again on
  merged main `8f6a2f0dc67a5a15d3ee1c18550b875a60ebbc2e`.
  Production verification here means the published repository, not a deployed
  application or an installed consumer upgrade.
- The final feature candidate passed
  `python3.12 -u v0.5/scripts/verify-playbook.py --jobs 4`: 1,253 tests
  (727 public and 526 delivery), no failures or skips, plus the documentation,
  privacy, generated-file and upstream-cadence checks.
- The independent Sol 6.1/high review covered 18 requirements and 21 scenarios
  in the original process documentation. No actionable defects were found.
  The human accepted report-only access for that completed review only;
  source hashes and audited commands showed no edits. This was an explicit
  exception, not enforced read-only access or a reusable waiver.
- The later CI repair restored setup-python on PATH after sudo reset it.
  Its executable regression failed before the fix and passed afterward.
  The original failing worker-dispatch test then passed under real sudo on
  Ubuntu 26.04 with Python 3.12.15. The prior Sol and automated GitHub reviews
  do not cover this subsequent CI repair.

Historical failed attempts remain failed: the first local verification met
platform-specific fixture assumptions, and a later container without an init
process retained zombie children. Correcting the verification environment
produced complete passing runs; neither failed attempt is counted as a pass.
The original build/review records below retain their contemporaneous scope.

## Durable knowledge and release scope

The [foundations](../../v0.5/00-foundations.md) own authorization reuse;
[prerequisites](../../v0.5/10-process/00-prereqs.md#check-c2--operation-capabilities)
own capability discovery; [shipping](../../v0.5/10-process/10-ship-and-deploy.md#persistent-data-recovery-gate)
owns recovery evidence. The [glossary](../../GLOSSARY.md) already contains the
surviving terms. There is no additional architecture decision, vocabulary,
agent rule or adopted verification-harness map to promote in this closeout.

The feature and CI repair are recorded under
[Unreleased](../../v0.5/CHANGELOG.md#unreleased). Current-release pointers remain
V0.5.2; no version file, tag, release, consumer upgrade or tracker mutation is
introduced. A future release must pass its own final gates and preserve user
customizations during reviewed adoption.

## Closeout disposition

Doc-close starts from a clean tree on a fresh branch from merged main. The four
planning documents move unchanged into this archive; planning/archive indexes
and the mirrored maintainer state are updated together. The
[retrospective](../../planning/retros/2026-10-25-capability-and-authority.md)
and [field report](../../analysis/field-reports/2026-10-25-capability-and-authority.md)
record the remaining evidence limits and promotion decisions. These records
form one closeout PR; its own verification results belong in that PR.
Publication awaits human merge. Unrelated feature closeouts remain unchanged.

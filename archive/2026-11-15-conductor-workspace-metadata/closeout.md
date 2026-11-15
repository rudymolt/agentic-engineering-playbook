# Conductor workspace metadata — closeout

PR #58 merged as `4dd4f1afb68fcb69e224575f624f9b8fe6a1935b` on
2026-11-15 at 19:34:59 UTC. Its tree equals final candidate
`16bcadc3cc884b6d394d11981dc4006cd0e9d671`. Every commit newly added to main
has noreply author and committer addresses. The target repository and merging
login matched the active canonical privacy record before the authorized merge.
The owner explicitly requested implementation, verification, shipment and merge,
then a second retrospective PR.

## Verification

- Independent standards/security/devex review: pass, no findings; executed
  Markdown, links, privacy, metadata, manifest and the new regression.
- Independent spec/QA review: pass, no missing accepted criteria. Full setup
  file: 38 tests, one existing unavailable-zsh skip; sh/bash cases executed.
- Complete canonical verifier: exit 0 on the exact candidate in a disposable
  checkout, using Python 3.11 with Python 3.12 available for existing worker
  fixtures. All 62 public groups and 15 privileged delivery groups ran without
  skip flags. Documentation, generated outputs and upstream cadence passed.
- Both required PR CI jobs, edition and delivery, passed on candidate `16bcadc`.
  Comments and review threads were inspected and empty before merge.
- Published-source verification: fetched main and checked exact tree equality
  with the reviewed candidate, then read back all new commit identities.

Review contexts were separate and report-only by instruction; filesystem
read-only enforcement was procedural. Test output and identity records were
retained locally, with private paths excluded from this public report.

## Earlier failures retained

Initial fixture attempts used a terminating command rejected by adoption,
assumed local discovery meant complete installation, and parsed only the last
line of formatted JSON. These were corrected in the harness before review.

The VM's private home directory prevented isolated subprocess source access.
Elevated DAC capabilities bypassed a chmod-based failure fixture, including
after a bounding-set-only drop. The same existing test failed on unchanged
main. Final verification used an accessible exact-commit checkout and root
securebits with explicit ambient privileges excluding DAC bypass; an executed
write probe confirmed denial. Independent focused verification passed under an
unprivileged account. A missing Python 3.12 prerequisite was installed before
the successful full run. No product behavior was changed to accommodate these
host issues, and failed attempts are not counted as product verifier catches.

## Publication boundary and follow-up

This ships repository guidance and regression coverage, without changing the
production installer. Current tagged release pointers remain v0.5.7; no new tag
or automatic consumer adoption was requested. The changelog entry remains
Unreleased for a future deliberate release.

The consumer repair is not verified as published, so no public repair link is
supplied. Consumer writer/checker review and fresh automatic-startup qualification
remain separately owned. Missing original settings/logs or host binding cannot
be replaced by manual success or later agent metadata. The durable
[contract](../../v0.5/scripts/conductor-workspace-metadata.md) owns that checklist.

Doc-close and the [retro](../../planning/retros/2026-11-15-conductor-workspace-metadata.md)
share one follow-up PR. Maintainer state is mirrored in planning status; no root
consumer state is created. Other active features remain unchanged.

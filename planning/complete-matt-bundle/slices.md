# Complete Matt bundle — S2

Scope and authorization: [alignment](alignment.md).
Acceptance and test seams: [spec](spec.md).

1. Extend the bundle selection and validate pinned nested attribution metadata.
2. Verify full-directory installation, missing-skill repair, retained edits and
   incompatible-review refusal through existing public commands.
3. Refresh notices/documentation/generated artifacts, run focused checks, and
   obtain fresh independent review before the final full verifier.

Status: S2 implementation, fresh independent review and full verification coverage
complete. Stopped at the agreed checkpoint; no release or runtime qualification claim.
Progress checkpoints are informational; stop after three identical failed fix
attempts or three attempts without progress. No live dispatch is in this slice.

## Verification checkpoint

The independent review passed on 2026-11-01 against the uncommitted candidate
based on `ce467eca47801d156c53655c6253dfb5599b0aad`. All twenty complete skill
directories and the root license match the unchanged v1.3.1 source. The reviewed
bundle contains sixty source files. All ten user-only invocation controls remain
intact, and incompatible embedded review still returns its manual fallback.

Executed review evidence: 36 provisioning tests, 11 setup/source-recovery tests
and 40 link/privacy/registry tests passed. Additional public-CLI probes rejected
46 malformed attribution values and accepted six valid quoted/plain forms.
Interrupted repair and recovery preserved the earlier upgrade's rollback target;
partial edits and absent retained customizations remained blocked.

The first independent pass found malformed attribution scalars were accepted.
The regression reproduced it before the parser fix; a fresh reviewer accepted
the corrected candidate. A full-verifier fixture failure reproduced unchanged at
the base revision: macOS temporary paths traversed a symlink. Resolving `TMPDIR`
made all eleven glossary tests pass without relaxing the safety check.

The final candidate also corrects an adoption test's stale eleven-skill count to
twenty. No production code changed after the passing independent review.

Full verification coverage completed on 2026-11-01 using the fixed candidate in
an isolated local Linux container (Python 3.12.15, Git 2.47.3). The canonical
`python3 v0.5/scripts/verify-playbook.py --jobs 4` run passed all 56 public suites
(823 tests, three platform-specific skips), all intermediate document/generated
checks and 14 of 15 delivery suites. Its exit was 1: four checker-monitor tests
could not initialize Linux fanotify as the unprivileged container user.

The unchanged eleven-test monitor suite then passed in an isolated container
with UID 0 and the required `SYS_ADMIN` capability, matching the delivery CI
privilege requirement. All 15 delivery suites (526 tests) therefore have passing
evidence across these runs. The upstream cadence check, which the original
wrapper did not reach, passed separately. This is complete check coverage, not
a claim that the original wrapper returned exit 0. The three Linux setup skips
(two Python 3.9 cases and one zsh case) passed in the earlier Mac setup run
against the same production code.

The full-run snapshot covers 601 repository files. Final edits only record this
checkpoint and receive focused Markdown, link, privacy and generated-file checks.
Other packages, private personal skills, consumer adoption and actual Cloud
qualification remain later work. Next planned slice: S3, pinned gstack package
support; personal definitions remain in S4.

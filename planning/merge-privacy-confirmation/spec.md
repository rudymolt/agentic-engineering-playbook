# Merge privacy confirmation — acceptance contract

## Problem and outcome

Repeated requests for the same human-confirmed GitHub email privacy setting
interrupt merges. Remember the confirmation for one repository/account pair;
continue checking commit identities on every merge.

## Acceptance criteria

1. Root `AGENTS.md` contains the sole canonical confirmation record: exact
   GitHub repository, login, enabled status, confirmation date and provenance.
   Seed the already recorded human confirmation before PR #38 on 2026-10-09.
2. Before reuse, establish the actual GitHub PR target repository and
   authenticated merging login. Only a complete, matching, unrevoked record
   avoids a new confirmation prompt. Repeated merges by that pair reuse it.
3. Missing or incomplete records require an affirmative human answer before
   merge. Different repositories or accounts cannot inherit the record. If
   identity or target is unknown, establish it before deciding whether to reuse.
4. An explicit disabled-setting report or revocation invalidates the record
   until a fresh affirmative confirmation is recorded. No periodic expiry or
   recurring prompts are introduced. Copying the file carries no authority to
   a different repository.
5. Before each maintainer commit, configure both author and committer to GitHub
   `noreply` addresses in that checkout. After each merge, read back every commit
   newly added to `main` and require `noreply` author and committer addresses.
   Preserve all review-thread, CI and merge gates. A record proves neither
   commit identity nor merge authorization.
6. The privacy gate permits only the exact selected public repository/login
   fields of this record in root `AGENTS.md`. Do not exempt the file, remove
   its owner from the general forbidden-marker rule, encode identifiers to
   evade scanning, or allow arbitrary accounts, repositories or URLs.
   Prefer provenance wording that needs no additional URL exception.
7. Retain existing privacy tests. Add positive and negative fixtures for the
   narrow exception; the email scan remains active even on approved lines.
   All required checks pass, with a changelog Why line and regenerated files.

## Implementation seams and exclusions

Edit root `AGENTS.md`, `v0.5/scripts/check-public-content.py`,
`v0.5/scripts/test_public_content.py`, the Unreleased changelog, affected
generated files, and this feature's planning artifacts/status. Reuse the
checker's existing `problems(root)` seam. No new module or dependency is needed.

Exclude consumer templates, shared stage/skill rules, account-settings APIs,
new policy/cache files, CI changes, unrelated feature closeout, tags and merges.
Any newly discovered active duplicate instruction must point to the canonical
record rather than create a second record; report it before broadening scope.

## Verification

Review six instruction scenarios: absent/incomplete record; exact valid match;
changed login; changed repository/copied file; revocation/disabled report;
unknown target/login. Only the valid match reuses confirmation. Check that
repeat merges do not prompt again and all scenarios retain the identity gates.

Use TDD for the checker exception. Demonstrate that the exact record passes;
the same fields in another file, modified values containing forbidden markers,
appended private text, personal email, machine path, and unrelated private
markers elsewhere in root `AGENTS.md` must still fail. Preserve existing tests.
Do not replace behavior checks with snapshots of instruction wording.

Run focused Markdown, links, privacy, unit tests and generated-file checks
during iteration. Obtain fresh independent scenario/privacy review. Run the
full Python 3.12 canonical verifier on the final candidate and retain both
required CI jobs before calling the PR ready. No browser QA is applicable.

## Open questions

None for the selected slice. Future record changes for a different identity
must undergo the ordinary privacy review; this exception is not a general
permission to publish account information.

# Diagnosis and regression evidence

At the starting main revision `00445a2`, public bootstrap and supported upgrade
each produced a successful Apply with four retained namespace artifacts,
including a completion seal. Git ignored zero of those artifacts; the receipt
and publication files appeared as untracked alongside the configuration.
Reopen succeeded. The seal is an empty directory and does not itself appear
in ordinary Git status, but its namespace must still be covered.

Root cause: both managed-ignore paths only appended `.playbook-routing/`.
Bootstrap's plan disclosed only that rule. Their append code also trimmed
existing trailing whitespace when the routing entry was missing.

The new public-entry-point/Git regression suite failed before source changes
(14 failed subcases), then passed after adding the anchored artifact rule and
preserving existing content. Subsequent coverage includes CRLF preservation,
both managed entries present without a final newline, read-only plans, real
successful saves/reopen, retained backup receipts/seals and completion conflict
reconciliation. Public bootstrap seed tests also exercise Git visibility.

Cloud evidence is retained under gitignored `.context/apply-recovery/`.
Two preliminary reproduction harness attempts failed due to missing discovery
and an incorrect expectation for the public read state; the corrected harness
reproduced both paths. These were distinct setup failures, not passing tests.
No product remediation failure or repeated no-progress signature occurred.

Fresh independent QA rejected candidate `84da53b`: bare carriage returns and
Unicode separators inside user comments made `splitlines()` falsely recognise
a rule that Git did not recognise. Eight new regression subcases reproduced
that defect. The correction uses LF-anchored matching with optional trailing
CR for CRLF entries; it preserves all user bytes. This is repair cycle 1, and
requires a new fresh independent verifier before PR readiness.

The first unbounded canonical run was interrupted because its candidate was
superseded by that defect; partial output is retained and is not a pass. The
99-test broader bootstrap/transition/configuration suite did finish and pass
on the earlier candidate. The corrected candidate must run canonical checks
again. Default cloud Python 3.9 also failed a conventions import; verification
now uses Python 3.12 without changing the repository's version requirement.

Actual-head manual CI at `94f1522` passed all 537 K4.1 tests without skips,
but its edition shard rejected the new test's whole-bootstrap `changed:`
assertion when another shard generated an unrelated skill bytecode cache.
An isolated public-CLI reproduction at both `00445a2` and `94f1522` copied the
same new `.pyc` file while preserving `.gitignore` bytes. This is baseline
installer behavior, outside the product fix; no installer change is included.

Repair cycle 2 scopes the report assertion to `.gitignore`, retains the existing
whole-project content snapshots, and adds a deterministic cache-appearance
case requiring unchanged ignore bytes and modification time. Production source
is unchanged. The superseded canonical attempt and failed CI remain retained;
new fresh review and actual-head CI are required for the corrected test suite.

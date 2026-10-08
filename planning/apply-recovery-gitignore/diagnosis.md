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

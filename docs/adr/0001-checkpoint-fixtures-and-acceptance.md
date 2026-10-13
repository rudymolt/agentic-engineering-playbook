# ADR 0001 — Owned checkpoint fixtures and measured acceptance

Status: accepted on 2026-10-13; feature merged in PR #41 as `20eeb04`.

## Decision

Repack only exclusively owned, quiescent sequential fixture remotes, in the
foreground at 512 loose objects. Retain transport-mode clones and effective
receiving maintenance safeguards. Concurrent-writer fixtures remain outside
this opt-in. See [fixture maintenance](../../v0.5/delivery/tests/checkpoint_fixture_support.py).

Build immutable recovery templates once per class/process and restore
independent repository trees to the same reserved paths. Approved URLs and
their digest bind those paths; copying records to a new identity or rewriting
approval is excluded. Preserve history, objects, isolation, setup assertions,
within-test fresh resets and every matrix publication/reload boundary. See
[seed restoration](../../v0.5/delivery/tests/checkpoint_seed_support.py).

Retain equivalent Unicode character lookup and fresh public guidance admission.
Keep bounded native failure evidence; unsupported metadata remains unknown and
optional source-check unavailability must not prevent native test execution.

## Rejected alternatives and acceptance

Validation reuse and proposal retention were rejected. The two-threshold 256
experiment was independently rejected because recovery median regressed and
combined gain was below its retention criterion; retain 512. No further
performance experiment is selected.

The maintainer accepts the measured gains, subject to correctness, safety,
privacy and release checks. Four original speed targets remain unmet; guidance
and full-verifier targets were met. This is an explicit acceptance change,
not a changed measurement or compatibility waiver. The pre-existing
custom-object isolation question remains unresolved. See the
[measurement and limitation record](../../bench/test-runtime/CHECKPOINT-PERFORMANCE.md).

## Future compatibility checks

Before new optimization or release qualification, and after relevant Python,
Git, runner or capture-source changes, verify fixture ownership, native
execution, unchanged test/matrix coverage and current authority boundaries.
Measure complete costs, including preparation and cleanup. Keep release users
pinned to tags and preserve their customizations when migrating. There is no
periodic universal-compatibility claim or automatic settings update.

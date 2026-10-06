# Runtime log fixtures

These are minimal verbatim timestamped excerpts from existing normal feature CI,
not synthetic success logs. Omitted material includes repository setup, machine
paths, verbose test cases and standalone check output. No line was relabelled.
The original log hashes are retained in the history row; excerpt hashes are
intentionally different. Source links remain in the runtime totals/history.

- `pr14-edition.log`: run 37138186128, job 111246924718; 41 groups, 616 executions.
- `pr14-delivery.log`: same run, job 111246924844; 15 groups, 537 executions.
- `pr14-failed-edition.log`: run 37135602912, job 111239390402; 614 tests,
  12 failures, process exit 1, no final success marker. This is rejection evidence.

The successful head is `a89fd242ae2e87caed987359e65e7a454203c5cf`.
`../manifests/` records independent discovery counts at that exact revision,
not counts inferred from these excerpts. Edition inventory matched every sorted
public test file; delivery inventory matched the exact K4.1 SETS order.
Discovery only loaded tests and counted cases; no tests or live models ran.

Synthetic fixtures in `test_collect_ci_runtime.py` cover legacy serial parsing,
prefixed CLI logs and identity guards. Mutations of these real excerpts cover
missing, duplicate, mislabelled, failed, skipped and count-mismatched shards,
unsupported commands, absent manifests and incorrect revision bindings.

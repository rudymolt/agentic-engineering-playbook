# Observed full-suite runtime history

Collected from ordinary successful feature CI logs; no extra suite runs.
These are observations, not controlled or causal optimization estimates.

Test time sums unittest runner durations across edition and K4.1, including
test fixtures but excluding interpreter startup and standalone CLI checks.
The jobs run in parallel: their overall log span is an elapsed-time proxy,
not the sum of their durations. It excludes queue and pre-log setup; exact
workflow wall time and queue time are unknown. Verification log spans in
the JSON include CLI checks and shell/log overhead, not just test time.

| Date / revision | Executions | Summed tests | Observed saved vs previous | Observed saved vs original | Parallel jobs log span | Evidence |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-09-28 / `a57af6de259d` | 756 | 1135.863 s | — | +0.000 s (+0.00%) | 1126.805 s | [run 36475493848](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/36475493848) |
| 2026-09-30 / `f5cad4fa0c58` | 760 | 980.447 s | +155.416 s (+13.68%) | +155.416 s (+13.68%) | 971.085 s | [run 36779311758](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/36779311758) |
| 2026-10-01 / `bf858067687f` | 760 | 647.214 s | +333.233 s (+33.99%) | +488.649 s (+43.02%) | 627.658 s | [run 36802981894](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/36802981894) |

Execution-count changes remain part of the observed totals. No duration is
subtracted for suite growth; per-test averages do not establish equivalence.
Counts are canonical executions, not unique IDs: imported tests can be
intentionally discovered in more than one module.

Runner image, Python/Git versions, canonical commands, exact head and
checked-out (possibly synthetic PR merge) SHAs, module counts and durations
are retained in [suite-history.json](suite-history.json). Hosted hardware
is not identified in these logs. The October 1 delivery image changed, and
untouched coordinator tests also became much faster; the observed drop
must not be attributed wholly to the optimizations. Targeted repeated
comparisons in [the review ledger](REVIEW-LEDGER.md) support narrower claims.

A row is one selected full-suite run, not a daily median. The previous-row
delta is the daily batch comparison only while one representative completed
run is retained per batch. Keep selection consistent (final successful head);
do not pick the fastest retry. Retain additional runs as separate evidence.

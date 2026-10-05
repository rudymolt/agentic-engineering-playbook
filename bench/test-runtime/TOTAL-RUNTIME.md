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
| 2026-10-02 / `b17ee92fcf8d` | 762 | 955.365 s | -308.151 s (-47.61%) | +180.498 s (+15.89%) | 939.279 s | [run 36953393473](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/36953393473) |
| 2026-10-02 / `1dfab0ed947a` | 762 | 934.088 s | +21.277 s (+2.23%) | +201.775 s (+17.76%) | 915.979 s | [run 36955234310](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/36955234310) |
| 2026-10-02 / `ba48cfde9288` | 762 | 840.121 s | +93.967 s (+10.06%) | +295.742 s (+26.04%) | 825.421 s | [run 37060591883](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37060591883) |
| 2026-10-03 / `7828c463f807` | 762 | 668.769 s | +171.352 s (+20.40%) | +467.094 s (+41.12%) | 657.017 s | [run 37085960489](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37085960489) |
| 2026-10-03 / `d1a3214dad9b` | 762 | 803.053 s | -134.284 s (-20.08%) | +332.810 s (+29.30%) | 791.679 s | [run 37086875919](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37086875919) |
| 2026-10-04 / `157a6c7c5ef0` | 762 | 991.362 s | -188.309 s (-23.45%) | +144.501 s (+12.72%) | 975.898 s | [run 37169647763](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37169647763) |
| 2026-10-04 / `aaba65cc8bac` | 762 | 930.348 s | +61.014 s (+6.15%) | +205.515 s (+18.09%) | 921.913 s | [run 37170621708](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37170621708) |
| 2026-10-05 / `ca5ce4bdf32f` | 762 | 952.408 s | -22.060 s (-2.37%) | +183.455 s (+16.15%) | 942.446 s | [run 37253579646](https://github.com/rudymolt/agentic-engineering-playbook/actions/runs/37253579646) |

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

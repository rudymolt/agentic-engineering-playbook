# Delivery test runtime review ledger

## Daily batch policy

Review two or three previously unreviewed test IDs per batch. Read this ledger
first; profiled candidates are not automatically reviewed. Preserve every
assertion, mutable fixture isolation, real checkpoint publication/CAS/reload,
and negative-case coverage. Record a no-improvement decision when a safe change
is not justified. Keep each batch on an isolated branch and use a draft PR;
merging remains a human decision.

Use [the profiler](../profile_delivery_tests.py) with identical test IDs,
interpreter, Git settings and repeat counts on the pinned baseline and candidate.
A detached baseline checkout avoids reverting candidate changes. Run at least
three fresh subprocess repetitions per selected set and compare per-test medians
and ranges. Include setup, test method and cleanup. Reports bind the revision,
source hashes, platform, privilege level and outcomes. Failed/skipped measurements
are not successful speed gains. Local raw diagnostics belong in ignored context
storage; committed evidence must contain no personal paths or addresses.

For cloud validation, use the existing Linux/Python 3.12 CI environment and its
privileged delivery command. Linux inotify/fanotify tests cannot be proved on
macOS. Reset measurements on a platform/interpreter change; never compare cloud
numbers directly with local numbers.

## 2026-09-30 — batch 1

Baseline: `a57af6de259d34e9b772105e0ad0610290797cfa`.
Branch: `perf/test-runtime-2026-09-30`.
Environment: macOS, Python 3.14.3, Git 2.50.1; automatic Git maintenance disabled
in both before/after workers, matching the canonical delivery runner.

Selected IDs, all from `test_interim_advance.AdvanceTests`:

- `test_bound_host_brief_names_candidate_checkout_and_implementation_paths`
- `test_bound_candidate_symlink_cannot_escape_shared_workspace_root`
- `test_bound_verify_send_includes_pr_helper_before_worker_done`

Diagnosis: a representative cProfile run of the host-brief test took 8.53 s;
247 subprocess calls took 8.04 s, including 106 control-ref validations taking
3.05 s. The original test repeats Git syntax probes for the same ref.

Change: a module-local subprocess proxy caches only successful exact
`git check-ref-format REF` probes with the original stdout/stderr/check options.
Each ref is checked by real Git at least once per selected test invocation;
failures are never cached and results are copied. Every validator still runs on
every call. Commands with other options, repository-dependent operations and
all store/CAS/remote/approval/reload behavior remain real and uncached. The three
original method bodies and assertions are unchanged. No production code changes.

Purity boundary: plain Git ref syntax depends on the input string, not mutable
repository state. These three tests do not change the Git executable or process
environment. Do not apply this decorator to tests that change either, assert
subprocess invocation counts, exercise subprocess failures, or run concurrently
inside the same interpreter. Its patch and cache reset after each invocation,
including exceptions. Every other test remains uncached.

Four guard tests execute real valid/invalid refs and verify validation call
counts, distinct refs, failures, changed subprocess options, other commands,
per-invocation reset and restoration after exceptions. Fresh independent review
executed these tests and the profiler smoke twice, with no blocking findings.

Three alternating before/after repetitions all passed all selected tests. Timing
includes setup and cleanup. A background exploratory baseline profile was still
running; therefore these are provisional local measurements, not controlled
suite-wide gains. Before/after ranges do not overlap for any selected test.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| host brief and paths | 5.768 (5.760–7.434) | 4.115 (3.659–4.497) | 28.7% |
| candidate symlink escape | 6.301 (6.173–6.435) | 3.734 (3.643–5.918) | 40.7% |
| verify PR helper message | 10.400 (9.879–16.590) | 6.343 (6.209–6.746) | 39.0% |

Evidence: [before](2026-09-30-before.json), [after](2026-09-30-after.json).
Reports retain source hashes because measurements precede the implementation
commit. The selected tests' source bytes must match the published commit.
These three IDs are reviewed; do not select them again in the next daily batch.

Validation: four guard tests and three repeated selected-test samples passed;
fresh independent review passed; the public-edition aggregate with
`--skip-drift --skip-delivery`, Python compilation, link integrity, regenerated
pack/edition manifests and public-content check passed. No separate lint/type
runner is configured in this repository; its canonical convention checks and
compilation cover those applicable lanes. Drift cadence is not a runtime check.

The pinned baseline already has a successful privileged Linux delivery run:
[baseline CI](https://github.com/{owner}/agentic-engineering-playbook/actions/runs/36475493848).
Its delivery verification step took 18 min 43 s. The earlier 15 min 35 s estimate
is not this run's measured time. Candidate exact-commit Linux CI is pending;
local exploratory failures/skips and final suite ranking remain under diagnosis.


## Cloud handoff checkpoint

Local profiling stopped at the user's request so the laptop can be closed.
[Exploratory measurements](2026-09-30-exploratory.json) retain 290 completed
baseline tests (572.76 s). This is a partial ranking, not a full-suite baseline.
The coordinator handoff parity matrix was in flight and its interrupted timing
is excluded. Preliminary errors/failures and Linux-only skips occurred earlier
in the exploratory run; no completed full-run verdict is claimed. The pinned
baseline core module independently passed all 75 tests. Full Linux CI is the
remaining authoritative aggregate validation.

Next candidates to profile and review, without repeating today's three IDs:

- `test_interim_coordinator.CoordinatorTests.test_handoff_acceptance_parity_matrix`
- `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_verify_matrix`
- `test_interim_recovery.RecoveryBoundaryTests.test_malformed_observation_and_cancellation_matrix`

These are candidates, not reviewed tests; verify exact class names during
discovery. The complete longest-test ranking and the proposed two-group 89%
share remain unverified. Do not infer them from this partial run.

Remaining work on the published checkpoint:

1. Confirm exact-commit privileged Linux CI passes both edition and delivery jobs.
2. Re-run the canonical full release-readiness check on Linux; record drift
   cadence findings separately from runtime regressions.
3. Complete a full per-test Linux profile with `--repeat 1` first; repeat the
   chosen future candidates at least three times before changing them.
4. Collect uncontended alternating before/after samples of today's three IDs
   on the same Linux interpreter and record a separate cloud comparison.
5. Append exact tested/published revisions and final checks here, regenerate
   manifests if edition files change, and preserve draft status until review.

Cloud commands (repository root):

```sh
python3 v0.5/scripts/verify-playbook.py --skip-drift --skip-delivery
sudo python3 v0.5/delivery/scripts/verify.py --set K4.1
sudo python3 bench/profile_delivery_tests.py --repeat 1 --output .context/test-runtime/linux-full.json
```

For before/after runs, use the profiler's `--root` to point at a detached
baseline checkout pinned to the baseline SHA above and pass the same three
`--test` IDs listed in today's entry, with `--repeat 3` for both roots. Do not run
other test suites concurrently with this final measurement. The initial local
comparison remains provisional because exploratory profiling was concurrent.

No merge or deployment is authorized by this checkpoint.


## Linux cloud continuation — batch 1

Measured baseline: `a57af6de259d34e9b772105e0ad0610290797cfa`.
Measured candidate: `2d3d4e70136f2f4223738f72affa64475a056ee8`.
Both checkouts were clean during measurement. Linux x86_64, Python 3.12.14,
Git 2.52.0, non-root; identical Git maintenance settings and exact selected IDs.
Three alternating baseline/candidate pairs ran in fresh subprocesses with no
other test workload running in this cloud workspace. These measurements include
setup and cleanup and are separate from the provisional macOS comparison.

| Test suffix (same three reviewed IDs above) | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| host brief and paths | 0.701 (0.693–0.727) | 0.531 (0.511–0.535) | 24.3% |
| candidate symlink escape | 0.692 (0.666–0.693) | 0.500 (0.499–0.509) | 27.8% |
| verify PR helper message | 1.218 (1.180–1.248) | 0.884 (0.852–0.899) | 27.4% |

All 18 executions passed; before/after ranges do not overlap. Evidence:
[Linux before](2026-09-30-linux-before.json) and
[Linux after](2026-09-30-linux-after.json). Source hashes match the measured
checkouts. These are selected-test improvements, not suite-wide percentages.
The evidence-only continuation does not change the tested implementation.

Cloud verification:

- Four cache guards passed (0.024 s); compilation passed for the profiler and
  changed test module. The earlier independent implementation review remains
  the review evidence; no new implementation was introduced in cloud.
- Canonical public-edition aggregate `--skip-drift --skip-delivery` passed:
  226 tests in 17.750 s plus conventions, metadata, links, public-content,
  generated status/inventory and edition manifest checks.
- The complete changed advance module passed: 45 tests in 53.224 s, including
  its inherited fixture/test discovery and all four cache guards.
- Drift was checked separately and is current through 2026-10-08.
- The cloud sandbox supports inotify but rejects the repository's fanotify
  initialization with EPERM; sudo is unavailable. Privileged delivery remains
  assigned to the existing Linux/Python 3.12 GitHub Actions workflow. No security
  settings were changed and no privileged full-profile run was attempted here.
- At this evidence checkpoint, exact-candidate
  [CI run 36773743448](https://github.com/{owner}/agentic-engineering-playbook/actions/runs/36773743448)
  has passed edition; delivery is still running. See the draft PR for final
  published-revision CI status. A pending job is not a passing full-suite verdict.

At that checkpoint, the complete per-test Linux ranking remained outstanding: CI validates
the suite but does not collect the profiler's per-test timing artifact. The
partial 290-test local exploratory report and the earlier two-group 89% claim
remain unsuitable for a complete ranking or suite-wide speedup claim. The three
next-candidate IDs above were confirmed against the source class/method names;
none has been reviewed or changed by this continuation. Do not repeat today's
three reviewed IDs in the next batch.


## Linux longest-test screening — completed permitted coverage

Measured revision: `c4709309597e59554718c384621aee8415df0325` (clean).
Linux x86_64, Python 3.12.14, Git 2.52.0, non-root. This is a measurement and
documentation pass only; no additional tests were optimized or marked reviewed.
The three improvements and their repeated comparisons above remain unchanged.

The existing CI run had no artifacts. Its logs expose module totals, not
reliable per-test durations, so they were not used to synthesize a ranking.
The existing profiler ran the entire K4.1 set sequentially with `--repeat 1`.
Then a separate fresh Python process reused the same profiler worker with
`unittest.defaultTestLoader.discover` redirected to `v0.5/scripts/test_*.py`.
Both runs disabled automatic Git maintenance as the canonical runner does.
No concurrent workspace test workload ran. Timings include setup and cleanup.
All source hashes match the measured revision.

Coverage: **760 canonical unittest executions attempted, 756 passed (99.47%),
four failed before useful measurement, zero skipped**. Delivery contributed
530 successful executions out of 534; public edition contributed all 226.
These correspond to **749 successfully timed unique IDs out of 753**: seven
imported checkpoint IDs are discovered twice by the canonical delivery runner.
The report retains both occurrences with their discovery module, and lists
duplicate IDs explicitly. No test was silently omitted.

Evidence: [complete successful-execution ranking and exclusions](2026-09-30-linux-ranking.json).
The JSON contains all 756 successful timings in descending order, four failed
attempts with reasons, 16 discovery-group summaries, and source hashes. These
are single samples for screening, not stable medians or a complete successful
full-suite timing baseline. Non-unittest CLI checks are outside this ranking.

### Longest successfully measured tests

| Rank | Exact test ID | Seconds |
| --- | --- | --- |
| 1 | `test_interim_recovery.RecoveryBoundaryTests.test_owned_inventory_malformed_matrix` | 312.045 |
| 2 | `test_interim_recovery.RecoveryBoundaryTests.test_malformed_observation_and_cancellation_matrix` | 206.365 |
| 3 | `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_verify_matrix` | 127.765 |
| 4 | `test_interim_recovery.RecoveryBoundaryTests.test_transport_failures_at_every_call_site` | 91.739 |
| 5 | `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_build_matrix` | 91.505 |
| 6 | `test_interim_coordinator.CoordinatorTests.test_handoff_acceptance_parity_matrix` | 67.289 |
| 7 | `test_interim_recovery.RecoveryBoundaryTests.test_provider_programmer_and_storage_exceptions_are_not_conflated` | 37.806 |
| 8 | `test_interim_recovery.RecoveryBoundaryTests.test_coordinator_and_prefix_malformed_matrix` | 21.485 |
| 9 | `test_interim_recovery.RecoveryBoundaryTests.test_unknown_active_queued_and_terminal_are_distinct` | 13.798 |
| 10 | `test_interim_host_continuation.RepairHostContinuationTests.test_async_three_failure_diagnosis_and_stagnation_with_and_without_caps` | 13.172 |
| 11 | `test_interim_recovery.RecoveryBoundaryTests.test_truthful_stop_proof_still_gates_validation_persist_reload_and_resume` | 11.191 |
| 12 | `test_interim_recovery.RecoveryBoundaryTests.test_consumed_elapsed_is_validated_before_accounting` | 11.149 |
| 13 | `test_interim_coordinator.CoordinatorTests.test_operation_binding_parity_matrix` | 9.588 |
| 14 | `test_interim_recovery.RecoveryBoundaryTests.test_shared_boundary_red_matrix` | 8.497 |
| 15 | `test_interim_monitor.MonitoringTests.test_repair_worker_errors_keep_one_monitored_failed_operation` | 8.313 |

The longest public-edition test was
`test_verification_harness_fixture.VerificationHarnessFixtureTest.test_actual_twice_bootstrap_and_upgrade_preserve_custom_generated_harness`
at 1.717 s. Recovery and coordinator discovery groups together account for
**1083.383 s / 1343.875 s = 80.6% of successfully measured delivery test time**.
This is a new, explicit single-run denominator excluding the four failed
watcher attempts; it does not substantiate the earlier 89% claim.

### Excluded privilege-dependent measurements

All four are in `test_checker_monitor.CheckerMonitorTests`:

- `test_git_index_lock_records_kernel_writer_attribution`
- `test_non_executable_helper_starts_only_after_first_probe_and_stops_cleanly`
- `test_sub_interval_create_remove_is_event_detected`
- `test_transient_write_invalidates_even_when_removed_before_stop`

Each failed at monitor startup with `monitor failed before readiness:
monitor-error`; diagnostic reruns reproduced all four failures. The preflight
probe returned EPERM from the exact fanotify initialization used by the monitor.
This sandbox has no sudo/root route, so those early-exit durations are excluded
from the ranking. The other seven checker-monitor tests and all 93 interim
monitor tests passed. No security change, privileged workaround, or CI workflow
change was attempted.

The measured revision already passed privileged
[CI run 36774219181](https://github.com/{owner}/agentic-engineering-playbook/actions/runs/36774219181):
edition passed and all 534 delivery executions passed, including these four.
That establishes correctness, not comparable per-test durations for the four
excluded IDs. Final documentation-commit CI status is recorded on the draft PR.

### Next candidates and remaining limit

The top three new candidates are now:

- `test_interim_recovery.RecoveryBoundaryTests.test_owned_inventory_malformed_matrix`
- `test_interim_recovery.RecoveryBoundaryTests.test_malformed_observation_and_cancellation_matrix`
- `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_verify_matrix`

The previously listed handoff parity matrix remains a candidate (rank 6).
Profiling is not a correctness review: all these candidates remain unreviewed.
A future batch should select two or three previously unreviewed IDs, diagnose
costs, and collect repeated before/after evidence before claiming improvements.
Today's three reviewed IDs must not be selected again.

Remaining hard limit: a complete successful ranking including the four kernel
watcher tests needs a permitted privileged timing environment. Existing CI has
no per-test timing artifact, and no workflow was changed to obtain privileges.
This pass completes the ranking available in the current permitted environment.

## 2026-10-01 — batch 2

Baseline: `f5cad4fa0c588fce4906cdde01fb60ba82657e57` (PR 6 head).
Measured implementation: `8c02e9cde00789c6c63e90cdf1e5dc264b034158`.
Branch: `perf/test-runtime-2026-10-01`, targeting `perf/test-runtime-2026-09-30`.
This draft is stacked on unmerged PR 6. Review this batch against that base;
merge PR 6 first, then retarget and revalidate this draft before any merge.
Latest main was `a57af6de259d34e9b772105e0ad0610290797cfa` at inspection and
pre-publication readback; PR 6 was the only open PR. No private repository was
accessed. No merge or deployment is part of this batch.

Newly reviewed IDs, both from `test_interim_recovery.RecoveryBoundaryTests`:

- `test_owned_inventory_malformed_matrix`
- `test_malformed_observation_and_cancellation_matrix`

Diagnosis and change: these large matrices repeatedly validate identical control
ref strings while exercising real checkpoint transitions. Extract the existing
PR 6 syntax-probe decorator into `control_ref_test_support.py` without changing
its executable logic, and apply it to exactly these two new methods. The 297
owned-inventory and 252 observation/cancellation subcases, fault injection,
assertions, deep copies, per-case publications and fresh-clone reloads remain
unchanged. Repository-dependent Git commands, CAS, all validators, and failed
syntax probes still execute. Only successful exact input-only syntax checks
are reused inside one test invocation; no mutable snapshot or fixture is shared.
These tests keep the Git executable and environment fixed. The three previously
optimized advance tests and all four guards retain their original executable
bodies and decorator behavior. No production implementation changed.

Both measured checkouts were clean. Linux x86_64, Python 3.12.14, Git 2.52.0,
non-root, identical canonical Git maintenance settings. Three fresh baseline
processes were followed by three fresh candidate processes, sequentially, with
no concurrent workspace test workload. Setup, method and cleanup are included.
This is a blocked-order comparison, not an alternating/randomized experiment;
shared cloud host variation cannot be excluded. All 12 executions passed with
zero failed or skipped measurements. Each before/after range is disjoint.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| owned inventory malformed matrix | 252.339 (245.244–261.064) | 231.712 (229.342–231.875) | 8.17% |
| malformed observation and cancellation matrix | 163.969 (162.664–171.793) | 150.502 (147.760–151.788) | 8.21% |

Evidence: [before](2026-10-01-linux-before.json),
[after](2026-10-01-linux-after.json), and
[comparison](2026-10-01-linux-comparison.json). Every report source hash was
verified against its pinned commit. Final publication removes only a trailing
blank line in the extracted helper after independent review, with regenerated
manifests; the measured source hashes intentionally bind the measured checkpoint,
not the later evidence commit. No executable timing change followed measurement.
These are selected-test gains, not full-suite reductions, and do not revise the
prior batch's separate 24–28% controlled Linux results.

Validation and review:

- Fresh-context independent review proved AST equality for the original advance
  tests and guards, extracted helper logic, and recovery module except the two
  decorators and import. Independent execution passed all four guards and the
  three prior optimized advance tests. Review's trailing-blank-line finding was
  fixed; final focused verification and full diff whitespace check passed.
- Public-edition release-readiness aggregate with `--skip-delivery` passed all
  226 tests in 18.084 s, convention/metadata/link/public-content checks, generated inventory
  and manifests. Upstream drift cadence is current through 2026-10-08.
- Full changed advance module passed all 45 tests in 47.827 s. Final independent
  focused verification passed seven tests in 1.934 s. Python compilation and regenerated delivery
  and edition manifest checks passed. No separate lint/type runner is configured.
- Privileged fanotify tests were not attempted in this unprivileged cloud profile;
  only the two selected test IDs were timed. No complete new suite ranking is
  claimed. The existing Linux/Python 3.12 GitHub Actions workflow provides the
  authoritative full K4.1 regression result, including the four previously
  excluded watcher tests. No workflow/security settings or privilege workarounds
  were introduced. The draft PR records the exact final SHA and terminal CI
  result; local selected-test success is not a substitute for that result.
- Noreply author/committer identities and the public content boundary were checked
  before publication. Browser QA is n/a for this test-only change; existing real
  Git integration tests and privileged CI cover the applicable runtime boundary.

Both IDs above are now reviewed; do not select them in the next batch. The prior
three reviewed advance IDs remain preserved and excluded from future selection.
Next unreviewed candidates, using the previous screening order:

- `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_verify_matrix`
- `test_interim_recovery.RecoveryBoundaryTests.test_transport_failures_at_every_call_site`
- `test_interim_coordinator.CoordinatorTests.test_worker_acceptance_parity_build_matrix`

Establish new repeated baselines before optimizing these candidates. Their prior
single-sample ranks are leads, not new measurements or review verdicts.

## 2026-10-01 — total-runtime tracking from ordinary CI

The daily history now uses existing normal feature CI logs as its primary source:
[observed totals](TOTAL-RUNTIME.md), [structured history](suite-history.json),
and [reusable collection procedure](COLLECTING.md). No extra full-suite timing
runs were launched. Partial feature checks and scope-skipped delivery jobs must
not enter this full-suite history. Targeted repeated benchmarks remain the
separate evidence for attributing an optimization's effect.

| Revision / batch | Executions | Summed unittest time | Observed saved vs previous | Observed saved vs original |
| --- | ---: | ---: | ---: | ---: |
| `a57af6de259d34e9b772105e0ad0610290797cfa` / original | 756 | 1135.863 s | n/a | 0 s |
| `f5cad4fa0c588fce4906cdde01fb60ba82657e57` / September 30 | 760 | 980.447 s | 155.416 s (13.68%) | 155.416 s (13.68%) |
| `bf858067687ffb751e5073c6ccc2287c56468a5a` / October 1 | 760 | 647.214 s | 333.233 s (33.99%) | 488.649 s (43.02%) |

These single-run observations are **not a controlled whole-suite speedup**.
The four added cache guards explain the original/current count increase; no
coverage was removed or time normalized away. Runner images and unidentified
hosted hardware differ. The untouched coordinator group's original/current
runtime changed from 257.258 s to 137.680 s, demonstrating substantial unrelated
variation. Do not credit the full observed reduction to these two batches.

Canonical commands are the public-edition aggregate with
`--skip-drift --skip-delivery` and privileged delivery `verify.py --set K4.1`.
All three runs used Python 3.12.14, Git 2.55.0 and Ubuntu 24.04, with exact image
versions, head/checkout SHAs, job IDs and input-log hashes retained in JSON.
The runs had no timing artifacts; their successful ordinary job logs supply the
module summaries. All 16 groups passed in each row, including privileged watchers.

Summed unittest time includes fixture setup and cleanup, but excludes process
startup and standalone CLI checks. Parallel-job log spans were 1126.805 s,
971.085 s and 627.658 s respectively; these are observed elapsed-time proxies,
not sums of job durations. Exact queue time and overall workflow wall time were
not available from the retrieved logs and remain null. Command log spans are
stored separately and include CLI/shell/log overhead.

The collector rejects incomplete, failed, skipped or mismatched-source evidence;
it never runs the suites. Dedicated collector self-tests are bench maintenance
checks outside the canonical suite counts. This continuation changes only bench
code, documentation and evidence; it does not add a workflow, schedule, production
change or new optimized test designation. The draft PR is stacked on PR 7 and
records focused review plus exact-head normal CI, including any scope-based skip.

Collector validation: seven dedicated guards passed, including the documented
GitHub CLI job/step-prefixed log format. Fresh independent review reproduced all
three totals and six input hashes, verified raw/prefixed parity on all historical
logs, and passed the guards. Public-content, links, conventions, unchanged edition
manifest and diff whitespace checks passed. Raw logs remain in ignored storage.

### Runtime evidence-link correction

The original collector incorrectly hardcoded an owner placeholder into each
`run_url`, and the renderer accepted it. Require a concrete repository slug
when collecting and reject unresolved or run-ID-mismatched evidence links when
rendering. Correct the three stored URLs and regenerate the report; all other
history fields, including numerical evidence and input-log hashes, are unchanged.

The public-content gate now permits only this public repository's numeric Actions
run URLs in `TOTAL-RUNTIME.md` and `suite-history.json`. Other files, repository
paths, URL suffixes and unrelated private markers remain blocked. Focused guards
cover both link generation and the scoped privacy boundary. The two added public
boundary tests affect future canonical test counts, not the historical counts
recorded here. No new timing samples or delivery-suite runs were requested.

## 2026-10-02 — batch 3 (Asia/Qatar)

Live state was checked before selecting the base: main remains at
`a57af6de259d34e9b772105e0ad0610290797cfa`; PRs 6, 7 and 8 are open drafts.
This batch uses fresh branch `perf/test-runtime-2026-10-02`, targeting PR 8's
`bench/runtime-totals-2026-10-01` at
`186e26050134b20f5236cf32c8a344205ba4beff`. PR 9 remains stacked: land its
prerequisites first, then retarget and revalidate before any human merge.
No merge, deployment, production, security or workflow change was made.

Measured implementation: `b17ee92fcf8d2fc43338e0252ce0bc10f2126883`.
New reviewed IDs, all in `test_interim_coordinator.CoordinatorTests`:

- `test_worker_acceptance_parity_verify_matrix`
- `test_worker_acceptance_parity_build_matrix`
- `test_handoff_acceptance_parity_matrix`

These matrices repeatedly validate the same control ref. Apply the existing
invocation-scoped successful exact Git syntax cache only to these three methods.
The Git executable and process environment stay fixed within each invocation;
these tests do not exercise syntax-process failure injection or call counts.
Every validator still executes. All method bodies, mutations and assertions
are unchanged; fresh mutable copies, per-test temporary remotes, distinct
no-local clones, real publication/CAS/persistence/reload and sends remain intact.
No cache/helper behavior or previously reviewed test was changed.

Independent fresh-context static review verified whole-module AST equality after
removing only the import and decorators. All 126 build, 138 verify and 72 handoff
mutations remain across five boundaries, totaling 1,680 subcases. The four cache
guards cover distinct refs, failures, options, uncached other commands, reset
and exception restoration. Execution verification is recorded below.

Three alternating baseline/candidate pairs used fresh processes and clean pinned
checkouts, Linux x86_64, Python 3.12.14, Git 2.52.0, non-root, and identical
canonical Git maintenance settings. No other workspace test workload ran during
measurement. Setup, test method and cleanup are included. Shared cloud host
variation remains possible; these are selected-test comparisons, not a causal
full-suite speedup. All 18 test executions passed without failures or skips.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| `test_worker_acceptance_parity_verify_matrix` | 75.081 (74.307–75.489) | 62.201 (61.995–64.592) | 17.16% |
| `test_worker_acceptance_parity_build_matrix` | 52.341 (51.951–52.405) | 45.403 (43.692–45.434) | 13.26% |
| `test_handoff_acceptance_parity_matrix` | 39.171 (39.152–40.646) | 33.680 (33.453–33.805) | 14.02% |

All three before/after ranges are disjoint. Evidence: [before](2026-10-02-linux-before.json),
[after](2026-10-02-linux-after.json), and [comparison](2026-10-02-linux-comparison.json).
Every source hash was checked against its exact measured revision. These three
IDs are now reviewed; do not select them again. Prior batch IDs remain reviewed.
The final evidence commit does not change executable test sources.

Next unreviewed candidates, preserving the prior successful screening order:

- `test_interim_recovery.RecoveryBoundaryTests.test_transport_failures_at_every_call_site`
- `test_interim_recovery.RecoveryBoundaryTests.test_provider_programmer_and_storage_exceptions_are_not_conflated`
- `test_interim_recovery.RecoveryBoundaryTests.test_coordinator_and_prefix_malformed_matrix`

These are screening leads, not measured improvements. In particular, review the
transport exception boundaries before applying any cache: a Git-subprocess fault
must not be hidden by caching. The four fanotify-dependent checker-monitor IDs
still have no successful local per-test timings. Existing privileged CI remains
their correctness route; no privilege bypass was attempted.

Validation: independent execution passed all four cache guards plus diagnosed
receipt parity and operation-binding parity (6 tests, 10.927 s). The reviewer
independently verified all 16 source hashes per revision, clean sample flags,
18 successful executions, and recalculated samples/medians/ranges/pairwise gains.
The local public-edition aggregate `verify-playbook.py --skip-delivery` passed
228 tests (16.119 s), conventions, metadata, links, public-content boundaries,
status/inventory/manifests, and drift cadence (current through 2026-10-08).
Nine collector guards passed. No separate lint/type runner is configured;
repository conventions and Python compilation cover the applicable lanes.
Full delivery correctness is assigned to normal privileged PR CI, including
all coordinator tests and the four watcher tests unavailable in this sandbox.

Normal implementation CI run 36953393473 passed edition and privileged delivery
for `b17ee92fcf8d2fc43338e0252ce0bc10f2126883` (synthetic checkout
`f4ed54eba0eb19f3e33eb5117ddc723ab3512e9c`). Metadata confirms edition job
110671004803 and delivery job 110671005025 belong to that run and both passed;
the full delivery step ran, while only its alternative skip-report step skipped.
All 16 unittest groups passed: 228 edition plus 534 delivery = 762 executions,
including the complete 40-test coordinator group and privileged watcher tests.

The existing collector accepted these complete normal feature logs with the
concrete repository slug and verified evidence link; no full-suite timing-only
run was added. [Total history](TOTAL-RUNTIME.md) and [JSON](suite-history.json)
retain the exact run/job/head/checkout identities and log hashes. This row records
the final executable implementation checkpoint before this evidence-only commit.
The evidence commit remains local because the cloud Git connection lost
authentication after the implementation push. Draft PR 9 records the full
results and publication blocker. The latest published head is the measured
implementation above, whose CI succeeded; no evidence-head CI is claimed.

Summed unittest runtime is **955.365 s (15m 55.4s)**, versus 647.214 s previously:
**308.151 s slower (47.61%)**. Against the original 1135.863 s, the observed saving
is **180.498 s (15.89%)**, replacing the earlier 43.02% observation as the current
checkpoint trend. This is not a causal optimization estimate. Counts grew by
two since the prior row and six since the original: PR 8's two public-content
regressions plus the earlier four cache guards; no coverage was removed.

The edition/delivery command log spans are 25.439479/935.443676 s; the parallel
jobs' overall log span is 939.278583 s (15m 39.3s), not their sum. Setup/queue and
exact workflow wall time remain distinct: the span includes logged setup and
cleanup but excludes queue and pre-log setup; unknown exact values stay null.
Both jobs used Python 3.12.14, Git 2.55.0, Ubuntu 24.04 image 20260927.320.1;
actual hosted hardware is unidentified. The unchanged recovery group took
539.139 s versus 351.755 s previously,
so the CI increase cannot be attributed to today's coordinator-only test edit.
The repeated same-host targeted comparisons remain the narrower gain evidence.

Publication checks: public-safe evidence only, no raw fixture diagnostics or
personal paths/addresses; both author and committer use a GitHub noreply identity.
Published implementation-head CI reached terminal success. Publication of this
evidence-only commit and its exact-head CI remain blocked: three authorized Git
push attempts failed authentication, including the existing credential helper
and the permitted external Git route. The connected commit API cannot explicitly
set author/committer identity, so it cannot guarantee the required noreply
identity. No account/security setting was changed to bypass this blocker.

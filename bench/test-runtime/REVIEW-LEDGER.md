# Delivery test runtime review ledger


## Integration correction — 2026-10-03

This is integration of the existing October 3 batch, **not a new optimization**.
All eleven reviewed IDs and all historical targeted measurements remain intact.
Fresh GitHub inspection confirmed PR 11 merged into main at
`366565964017e62360acaccc93ec797c58eacbe4`, then PR 12 merged into its old parent
branch `perf/consolidate-runtime-2026-10-02` at
`70994dda3e30bddcb140a5e963b2048fb88b18b5`. That parent was three commits ahead
and one behind main; October 3's changes were still outside main. No open PR
addressed this gap. The parent tree exactly matched PR 12's reviewed final head
`d1a3214dad9b4fdc49080b6ae555f98bf671b1a5`.

Fresh branch `perf/consolidate-runtime-2026-10-03` starts from current main
`366565964017e62360acaccc93ec797c58eacbe4` and carries the two reviewed October 3
commits forward. Its draft PR targets **main directly**. Every executable source,
workflow, manifest and targeted measurement matches the reviewed final source.
Only this handoff and recovery of the already-published final CI row extend that
tree. No historical measured value is corrected or replaced. This consolidation
is integration-ready after its exact-head CI passes, but is not on main until a
human merges it. No merge or deployment is authorized by this work.

Recovered ordinary final-head CI run 37086875919 at
`d1a3214dad9b4fdc49080b6ae555f98bf671b1a5` passed all 762 executions, including
privileged watchers. Existing collector output agrees with the complete record
published on PR 12: **803.053 summed test seconds**, 791.678718 s parallel job-log
span; edition/delivery jobs 111098904637/111098904874, synthetic checkout
`6e5a46abc631063df3b6a250f34a1e10ac5e63d6`. The final observation is now also in
[history](suite-history.json) and [totals](TOTAL-RUNTIME.md). It is 14.03% below
the prior daily batch and 29.30% below original, but 20.08% slower than the same
batch's implementation CI despite identical executable sources. Runner/load and
suite-growth caveats remain unchanged. No new timing-only full-suite run occurred.
Consolidation CI is separate integration evidence; its exact final SHA and
terminal result are recorded on the consolidation draft PR.

Local consolidation validation passed 228 edition tests (17.112 s), nine collector
guards, conventions, metadata, links, privacy, generated status/inventory, edition
and delivery manifests, and drift cadence current through 2026-10-08. Source
parity makes the prior independent execution evidence applicable to the unchanged
tests; normal consolidation CI supplies fresh privileged integration validation.
No new test is marked reviewed, and no new targeted timing claim is made.

Future daily work should refresh main and target main directly whenever its
required reviewed baseline is included there. If required changes remain only
in a parent branch, resolve their integration first where possible instead of
extending the stack. Before any merge, verify the PR base explicitly: merging a
child into a parent does not put its changes on main, even if that parent had
already merged earlier. Historical branch/open-PR statements below describe
original checkpoints, not current integration status. Check current main ancestry
and the complete eleven-ID ledger before selecting any new tests.

## Integration handoff — 2026-10-02

This is consolidation of existing batches, not a new daily batch: **eight IDs
remain reviewed**. Fresh remote inspection found main at
`559070e08fefdf1bb5a9cfc1a0aef7fdbcf3bf33` with September 30 only. PR 6
landed on main; PRs 7, 8 and 9 merged into their respective stacked base
branches, leaving October 1/2 and the totals collector outside main. Their
combined source is `221c5077dd11325e325c0df23c96b5e81f2ebdb2` on
`bench/runtime-totals-2026-10-01`. The consolidation branch
`perf/consolidate-runtime-2026-10-02` starts from current main and carries that
tree forward without changing executable sources or historical measurements.
Human review and merge into main remain required; historical branch/open-PR
statements below describe their original checkpoints, not current status.

Before the next daily batch, fetch current remote refs and find the consolidation
PR by that head branch. If it is merged, start a fresh branch from updated main
and confirm this complete ledger and the October 1/2 test decorators are present.
If it remains open, use its latest published, successful-CI head as the pinned
baseline and branch from it; target that consolidation branch in the next draft
PR and record the exact baseline SHA and dependency. Revalidate if its head
changes. Do not silently fall back to September 30 main. If the PR is closed
unmerged or the complete baseline cannot be verified, resolve the dependency
before starting another optimization. Always read this ledger from the selected
baseline, then exclude all eight IDs below from new-batch selection.

| Test class | Already reviewed methods |
| --- | --- |
| `test_interim_advance.AdvanceTests` | `test_bound_host_brief_names_candidate_checkout_and_implementation_paths`, `test_bound_candidate_symlink_cannot_escape_shared_workspace_root`, `test_bound_verify_send_includes_pr_helper_before_worker_done` |
| `test_interim_recovery.RecoveryBoundaryTests` | `test_owned_inventory_malformed_matrix`, `test_malformed_observation_and_cancellation_matrix` |
| `test_interim_coordinator.CoordinatorTests` | `test_worker_acceptance_parity_verify_matrix`, `test_worker_acceptance_parity_build_matrix`, `test_handoff_acceptance_parity_matrix` |

The publication blocker recorded at the end of batch 3 was subsequently resolved:
`1dfab0ed947a3892f8b94e504b13d79edfe20a47` was published and its normal PR CI
run 36955234310 completed successfully. Fresh run/job metadata and logs confirm
edition job 110676631425 and full privileged delivery job 110676631193 passed.
The collector now also retains that final evidence-head observation: **934.088 s
across 762 executions**, 44.32% slower than October 1 and 17.76% below the
original baseline. The earlier 955.365 s implementation checkpoint remains in
history. These are observations, not causal optimization claims. No extra
full-suite timing run was launched. Consolidation CI is separate integration
evidence; its exact final SHA and terminal result belong in the consolidation PR.

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

## 2026-10-03 — batch 4 (UTC)

Fresh host inspection confirmed PRs 6–9 merged into their historical target
branches; only PR 6 reached main (`559070e08fefdf1bb5a9cfc1a0aef7fdbcf3bf33`).
Consolidation draft PR 11 remains open at successful-CI head
`ba48cfde92887a6f7197d810d3504afbd268ddb0`. This batch branches from that exact
complete baseline and draft PR 12 targets `perf/consolidate-runtime-2026-10-02`.
It depends on PR 11; after consolidation lands, refresh main, retarget and
revalidate before any human merge. No merge or deployment is authorized.
The starting checkout was clean; no live changes were overwritten. Git CLI API
calls returned Forbidden after ordinary retry; the existing connected GitHub
app verified PR/run/job metadata and provided logs. Ordinary Git fetch/push
worked. No credential inspection or access/security changes were made.

Measured implementation: `7828c463f8077e34cd398c12f6f079923dbc9221`.
New reviewed IDs, all in `test_interim_recovery.RecoveryBoundaryTests`:

- `test_transport_failures_at_every_call_site`
- `test_provider_programmer_and_storage_exceptions_are_not_conflated`
- `test_coordinator_and_prefix_malformed_matrix`

These matrices repeatedly validate the same control ref. Apply the existing
successful exact Git syntax cache to these three method invocations only.
Independent review proved whole-module AST equality after removing the three
new decorators: 116 transport subcases, 75 programmer-error subcases plus three
storage exception injections, and 42 malformed coordinator/prefix subcases stay
intact. Provider failures occur in fixture methods, and storage failures patch
persist; neither injects Git subprocess faults. The Git executable and process
environment stay fixed. Every validator still executes, invalid ref probes remain
uncached, and all other commands retain their original behavior. Temporary remotes,
mutable copies, real publication/CAS/persistence, independent clones and reload
assertions are unchanged. Existing cache guards cover success, failure, distinct
refs, options, other commands, invocation reset and exception restoration.
All eight prior IDs remain excluded from this batch; now eleven IDs are reviewed.

Three alternating baseline/candidate pairs ran sequentially in fresh processes,
with clean pinned checkouts, Linux x86_64, Python 3.12.14, Git 2.52.0, non-root,
canonical Git maintenance disabled and no concurrent workspace tests. Timings
include setup, method and cleanup. Shared-host load variation remains possible;
these are targeted comparisons, not a controlled full-suite speedup. An ignored
orchestration reporting error occurred after the first baseline finished; its
complete successful JSON was preserved and reused without rerunning or selecting
samples. The profiler and test process did not fail.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| `test_transport_failures_at_every_call_site` | 68.216 (65.955–71.612) | 57.861 (54.647–64.721) | 15.18% |
| `test_provider_programmer_and_storage_exceptions_are_not_conflated` | 27.908 (27.652–28.409) | 23.843 (22.601–25.106) | 14.57% |
| `test_coordinator_and_prefix_malformed_matrix` | 16.211 (14.479–17.078) | 12.917 (12.718–14.680) | 20.32% |

All 18 executions passed, zero failures/skips. Every paired comparison improved.
The first two before/after ranges are disjoint; coordinator/prefix ranges overlap
slightly (14.479–14.680 s), so that result has weaker separation and does not
establish a precise constant gain. Samples trend faster over time on this host;
alternation reduces but does not eliminate load/order confounding. Evidence:
[before](2026-10-03-linux-before.json), [after](2026-10-03-linux-after.json),
[comparison](2026-10-03-linux-comparison.json). All 16 test-source hashes per
revision match their pinned Git trees. No test source changes after measurement.

Next unreviewed candidates, retaining the earlier screening order:

- `test_interim_recovery.RecoveryBoundaryTests.test_unknown_active_queued_and_terminal_are_distinct`
- `test_interim_host_continuation.RepairHostContinuationTests.test_async_three_failure_diagnosis_and_stagnation_with_and_without_caps`
- `test_interim_recovery.RecoveryBoundaryTests.test_truthful_stop_proof_still_gates_validation_persist_reload_and_resume`

These remain screening leads, not measured/reviewed improvements. Check each
purity boundary and establish a fresh repeated baseline; do not force a gain.
The four previously excluded checker-monitor IDs still lack successful local
per-test measurements. Their correctness route is existing privileged Actions,
with no security changes or local privilege workaround.

The integration CI observation was recovered from normal run 37060591883 at
baseline `ba48cfde92887a6f7197d810d3504afbd268ddb0`: edition job 111015987159,
delivery job 111015987530, synthetic checkout
`825a99099539c08519d70ed0736cc348be1b72d8`. Both jobs succeeded; full delivery
ran and only its alternative skip-report step skipped. The existing collector
accepted all 16 successful groups (228 edition + 534 delivery = 762 executions),
840.121 summed test seconds, and 825.421 seconds parallel job-log span. This is
integration evidence, not a new daily-batch gain. Its concrete evidence link and
raw-input hashes are in [history](suite-history.json) and [totals](TOTAL-RUNTIME.md).

Original baseline `a57af6de259d34e9b772105e0ad0610290797cfa` remains 756
executions / 1135.863 summed test seconds. Fresh downloads reproduced all counts,
durations and metadata; stripping their leading BOM and appending one newline
also reproduced both historical input hashes. Prior history is unchanged.
Historical run links were checked against GitHub run/job metadata. Older ledger
entries contain legacy owner-placeholder links; use the concrete verified links
in TOTAL-RUNTIME.md/suite-history.json instead. No placeholder is new evidence.

Collector exclusions: failed, skipped, incomplete, source-mismatched, ambiguous
or unexpected-group logs and scope-skipped delivery are not full-suite rows.
Targeted local measurements and collector guards are excluded from suite totals.
No extra full-suite timing-only run was launched. Summed unittest time includes
fixture setup/cleanup but excludes interpreter startup and standalone CLI checks.
Command spans include CLI/shell overhead. Parallel job-log span is an elapsed
proxy, not a duration sum; queue and exact workflow wall time remain unknown.

Normal implementation CI run 37085960489 passed at measured implementation
`7828c463f8077e34cd398c12f6f079923dbc9221`, testing synthetic merge
`4d088567203b45cae2e7cf12eba17848dcc5c914` against the consolidation branch.
Verified edition job 111096212039 and full privileged delivery job 111096211857
both succeeded. All 16 groups passed, including the 29-test recovery group and
all four watcher tests unavailable locally. The alternative skip-report step
alone skipped; no tests were excluded from this total.

| Checkpoint | Executions | Summed unittest seconds | Parallel job-log span seconds |
| --- | ---: | ---: | ---: |
| Original `a57af6de259d34e9b772105e0ad0610290797cfa` | 756 | 1135.863 | 1126.805 |
| Prior batch final `1dfab0ed947a3892f8b94e504b13d79edfe20a47` | 762 | 934.088 | 915.979 |
| Integration `ba48cfde92887a6f7197d810d3504afbd268ddb0` | 762 | 840.121 | 825.421 |
| October 3 implementation `7828c463f8077e34cd398c12f6f079923dbc9221` | 762 | 668.769 | 657.017 |

The implementation observation is 265.319 s (28.40%) below the prior daily batch,
171.352 s (20.40%) below integration, and 467.094 s (41.12%) below the original.
These are **observed differences, not causal optimization gains**. The unchanged
coordinator group fell from 185.553 s in the prior batch / 179.994 s in integration
to 141.543 s here, demonstrating unrelated variation. Today's test count is
unchanged; growth from the original is four cache guards and two public-content
regressions. No coverage was removed or time normalized away.

All current jobs use Python 3.12.14, Git 2.55.0 and Ubuntu 24.04 image
20260927.320.1; the original used image 20260920.314.1. Hosted hardware and load
are unidentified. Implementation edition/delivery command spans are
19.280264/654.250780 s, distinct from summed tests and the parallel-job span.
The committed history preserves both implementation and integration observations;
the final evidence-only head's terminal CI and latest collector extraction will
be recorded on draft PR 12 against the frozen exact SHA. This avoids an endless
cycle of evidence commits creating new CI revisions. The final row there is the
final-head daily observation; this implementation row is an explicit checkpoint,
not a claim that final-head CI has already passed.

Independent fresh-context review passed: whole-module AST parity except the
three decorators, 32 measurement source hashes, and all sample arithmetic.
Independent execution passed four cache guards and all three changed IDs:
7 tests / 233 subtests plus three storage exception injections, 100.111 s,
zero failures/errors/skips. Source equality to the published measured commit
was checked before execution. Review was behaviorally read-only, not a claim
of filesystem-enforced read-only permissions. Browser QA is n/a for this
test-only change; existing real Git integration tests cover runtime boundaries.
No new failing regression test was appropriate for an assertion-preserving
performance-only decorator application; existing guards and unchanged matrices
provide the verification seam. No applicable installed project skill was found;
repository stage-08 manual review and stage-09 integration routes were used.

Local canonical public-edition aggregate `verify-playbook.py --skip-delivery`
passed 228 tests in 17.227 s plus conventions, metadata, links, public-content,
generated inventory/status, edition manifest and drift cadence (current through
2026-10-08). Nine collector guards passed. Python compilation, delivery manifest
check and diff whitespace check passed. No separate lint/type runner is configured;
repository convention checks and compilation cover those lanes. Public-safe
outputs contain no raw fixture diagnostics, personal paths or private addresses.
Both author and committer identities are GitHub noreply. Final-head CI remains
separate from these local and implementation-head results; consult draft PR 12.


## October 3 supplemental parallel CI observation

Diagnosis: the serial collector rejected the exact `--jobs 3` command and assumed
one edition summary. PR14's runner buffers each module output and labels its
index, module name and exit status. The compatibility fix accepts only the
reviewed jobs suffix with a revision-bound complete module/count manifest.
Why: ordinary feature CI changed its output shape; tracking must follow that
shape without accepting partial suites or changing the tests being measured.

Run 37138186128 at `a89fd242ae2e87caed987359e65e7a454203c5cf` succeeded:
616 edition + 537 delivery = 1,153 executions, with 41 + 15 clean groups.
Independent discovery (count only, no execution) confirmed every module/count
against that head's inventory and K4.1 selection. Full raw logs supplied the
history row; minimal excerpts supply regression fixtures. The source hashes and
public evidence links remain in the history/totals outputs.

The 2,218.484 summed unittest seconds overlap under three workers per suite.
GitHub job metadata gives 563 seconds edition and 457 seconds delivery; their
start/end envelope is 563 seconds, excluding queue time. Verification-command
and job-log spans are separate fields in the history. These measures cannot be
substituted for one another or compared causally with serial durations.

Preserve the original October 3 daily 803.053-second observation and all earlier
rows. This additional row begins a separate concurrency baseline. Coverage grew
from 762 to 1,153 executions (+391); runner image is ubuntu-24.04 version
20260927.320.1, Python 3.12.14 and Git 2.55.0. Both actions now use major v7;
those are action versions, not playbook editions. Hardware is unreported.
No per-test normalization, causal 43% claim, or parallel speedup is established.

Run 37135602912 is excluded: the edition job failed (614 tests, 12 failures).
Its successful delivery job and elapsed times do not make it a successful full
baseline. Retain that failed-run excerpt only as negative regression evidence.

Validation scope: collector regressions, actual-log extraction, independent
source inventory/count checks, public-content and aggregate static correctness
checks, plus the tracking PR's normal exact-head CI. No timing-only full-suite
rerun or live model qualification is part of this change.



## 2026-10-04 — batch 5 (UTC)

Fresh fetch and GitHub metadata verified main at
`8827c7a1190ed64d0a70c9efaeca91cdb841be27`, including merged PR 13 and all eleven
previous reviewed IDs. PR 14 remains a draft at
`fb86bc0511fe32d40f872517c0d261c02f42e0b8`; PR 15 remains a draft at
`2c7f4528884a21756c4e126d410d671eef86e766`. Both have main as their actual merge
base. Neither changes the selected test sources relative to main. No resolved
consolidation or parser work is repeated. The initial checkout was clean.
Fresh branch `perf/test-runtime-2026-10-04` starts from that verified main and
its draft targets main directly, independent of PRs 14 and 15.

Measured implementation: `df35c6499eea75903c0cbb27bb682a9bf77ca066`.
Three NEW reviewed IDs:

- `test_interim_recovery.RecoveryBoundaryTests.test_unknown_active_queued_and_terminal_are_distinct`
- `test_interim_host_continuation.RepairHostContinuationTests.test_async_three_failure_diagnosis_and_stagnation_with_and_without_caps`
- `test_interim_recovery.RecoveryBoundaryTests.test_truthful_stop_proof_still_gates_validation_persist_reload_and_resume`

Diagnosis: repeated checkpoint validation invokes identical successful, input-only
Git ref syntax probes. Apply the existing invocation-scoped `memoized_control_refs`
to exactly these methods, with one helper import in host continuation. The helper
and all production code remain unchanged. The eligible exact command may validate
control refs or base refs; every validator still runs and failed probes are never
cached. Selected flows keep the Git executable and environment fixed; their faults
change provider receipts/checkpoint data, not Git subprocess outcomes.

All bodies, assertions and 35 subcases remain: 20 recovery path/state combinations,
four async capped/uncapped progress combinations (each three repair attempts),
and 11 stop-proof corruption cases. Real remote publication/CAS, raw corrupt
checkpoint injection, validation/persistence refusal, independent clone/reload,
provider no-effect assertions, per-case tearDown/setUp and deep copies stay intact.
No mutable fixture or snapshot is cached. The patch restores subprocess state
on success or exception and starts a new syntax cache per method invocation.
All fourteen IDs are now reviewed; do not select any of them in a later batch.

Three alternating baseline/candidate pairs ran sequentially in fresh processes,
Linux x86_64, Python 3.12.14, Git 2.52.0, non-root, with canonical Git maintenance
disabled. Both source checkouts were clean at every sample. No other workspace
tests ran during measurement. Setup, method and cleanup are included. All 18
executions passed, zero failures/errors/skips. Every pair improved and all
before/after ranges are disjoint; shared-host load/order effects remain possible.
These are selected-test results, not causal whole-suite savings.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| unknown/active/queued/terminal | 8.822 (8.538–8.902) | 7.076 (6.931–7.393) | 19.78% |
| async three-failure/stagnation | 8.527 (8.072–8.712) | 6.423 (6.378–6.779) | 24.67% |
| truthful stop-proof validation | 6.766 (6.632–6.908) | 5.848 (5.562–6.034) | 13.57% |

Evidence: [before](2026-10-04-linux-before.json),
[after](2026-10-04-linux-after.json), [comparison](2026-10-04-linux-comparison.json).
Every test-source hash was checked against its measured Git revision. No test
source changes follow measurement. No failed or skipped timing is counted as a gain.

Runtime collection also verified normal feature run 37150936632 at PR 14's exact
head, with edition job 111284514364 and delivery job 111284514201 both successful.
The synthetic checkout is `c9a63d0cc977c5fb2102878d7bce368ccca2f932`.
Fresh source discovery in an isolated exact-head checkout, one process per module,
found 617 edition plus 537 delivery executions over 41 + 15 groups. It did not run
the tests. The [new manifest](manifests/fb86bc0511fe32d40f872517c0d261c02f42e0b8.json)
binds all 56 module hashes and both verifier, parallel runner and edition-manifest
hashes. PR 15's older inventory was not reused or relabeled. Its unchanged collector
accepted the new logs and idempotent recollection; its 17 regression tests passed.

[Totals and verified CI links](TOTAL-RUNTIME.md) and [history](suite-history.json)
retain parallel observation details separately from serial daily records. Latest
parallel summed time is 2432.901 s, up 214.417 s (9.67%) from the prior equivalent
concurrency observation; API job envelope is 630 s, up 67 s (11.90%). One edition
execution was added. The overlapping sum is not suite elapsed time. Edition and
delivery command spans, API setup-inclusive job durations, job-log span, unknown
queue/workflow time, runner image and source/count differences are recorded there.
Neither this trend nor cross-concurrency comparisons establish causal savings.
Original serial baseline remains 756 executions / 1135.863 summed seconds; prior
daily final remains 762 / 803.053. No extra full-suite timing-only run was launched.
PR 15 exact-head run 37141141959 passed edition but correctly scope-skipped full
delivery; it is excluded from total-runtime baselines.

Local canonical `verify-playbook.py --skip-delivery` passed 228 tests (14.549 s),
conventions, metadata, links, public-content, generated status/inventory, edition
manifest and drift cadence current through 2026-10-08. Main collector's nine guards
and separate PR 15 collector's 17 guards passed. Delivery manifest generation and
whitespace checks passed. Privileged watchers remain assigned to existing normal
GitHub Actions; no security, credential, workflow, merge or deployment changes.
No relevant installed project `.agents/skills` exists in this cloud checkout;
repository manual stage-08 review and stage-09 integration routes apply. Browser
QA is n/a for an assertion-preserving test-only edit. No new behavior requires a
new regression test; existing cache guards and unchanged real-Git matrices verify
the seam. Both author and committer use GitHub noreply identities.

Next unreviewed candidates, retaining the successful screening order:

- `test_interim_recovery.RecoveryBoundaryTests.test_consumed_elapsed_is_validated_before_accounting`
- `test_interim_coordinator.CoordinatorTests.test_operation_binding_parity_matrix`
- `test_interim_recovery.RecoveryBoundaryTests.test_shared_boundary_red_matrix`

Profile these afresh, inspect fault/cache purity boundaries and record no-improvement
when warranted. The four fanotify watcher IDs still require privileged correctness
CI and have no successful local per-test ranking; no privilege bypass is authorized.

Fresh-context independent review passed whole-module AST parity after removing
exactly the three decorators and new import. Independent execution passed all four
cache guards plus the three selected IDs: seven tests, 35 subcases, 20.572 s,
zero failures/errors/skips. It reproduced all 32 measurement source hashes and
all sample arithmetic. A separate 56-process discovery reproduced the exact
feature inventory/counts and checked all module and four provenance hashes.
Review made no edits; read-only behavior is not filesystem-enforced isolation.
Security review found no new input boundary, secret or dependency change.
Normal draft PR CI remains the authoritative privileged correctness gate; final
publication identity and terminal CI will be recorded on the exact frozen PR head.

### Normal batch CI checkpoint and final publication

Draft PR 16 targets main directly. Normal CI run 37169647763 passed edition job
111339807356 and full privileged delivery job 111339807279 at evidence checkpoint
`157a6c7c5ef05bd59f0ae844a176bbc8cd15b382`. Synthetic checkout:
`857f9321b396150c6b98754905fc9163f64cac29`. Both jobs and the complete delivery step succeeded;
only the alternative skip-report step skipped. The run covered all 762 executions
(228 edition + 534 delivery) in 16 groups, including privileged watchers. Counts
match independent source discovery; no failure, skip or partial row is admitted.

The unchanged main collector accepted the complete logs. [Totals](TOTAL-RUNTIME.md)
and [history](suite-history.json) preserve exact run/job/head/checkout identities,
commands, runner fields and input hashes. Summed unittest runtime is
**991.362 s**: 188.309 s (23.45%) above the October 3 final
803.053 s, and 144.501 s (12.72%) below original 1135.863 s. Counts are unchanged
from October 3 and six above original (four cache guards and two content regressions).
These are same serial-command observations, not causal optimization estimates.
Unchanged coordinator-group runtime is 195.787 s versus
165.490 s previously; runner/load and unrelated variation remain material.

Edition/delivery verification command spans are 22.631877 /
973.597332 s. Parallel job-log span is
975.898134 s, an elapsed proxy including logged
setup/cleanup, not summed test runtime. Exact workflow and queue time remain null.
Both jobs used Python 3.12.14, Git 2.55.0, ubuntu-24.04 image
20260927.320.1; original image was 20260920.314.1. Actual hosted
hardware/load is unknown. The separate PR 14 concurrency observation above is
never substituted for the serial daily baseline.

This evidence-only follow-up leaves measured executable sources untouched. The
final frozen PR head requires its own terminal normal CI; its exact SHA, result,
verified links and final-head total will be recorded in PR 16's description after
completion, avoiding an unending evidence-commit/CI cycle. This row explicitly
belongs to the pre-follow-up checkpoint, not a claim about yet-unrun final CI.
No extra timing-only full suite was invoked.

Independent evidence review reproduced the complete serial row, hashes, group
counts and comparison arithmetic with the unchanged main collector. All eight
prior records and separate parallel evidence remain unchanged; this follow-up
changes only the ledger, totals and history. Public-content, links, conventions,
edition manifest and whitespace checks passed again. No executable retest was
needed locally for this documentation-only follow-up; normal exact-head CI still
owns final integration correctness.

## 2026-10-05 — batch 6 (UTC)

Live GitHub PR metadata and fetched refs confirm main at
`8827c7a1190ed64d0a70c9efaeca91cdb841be27`. PRs 14, 15 and 16 remain open drafts,
all targeting main with that exact actual merge base. PR14 has advanced to
`0a1b232c4d23725f268eef5aa993cc72a43b5554`; PR15 remains
`2c7f4528884a21756c4e126d410d671eef86e766`; PR16 remains
`aaba65cc8bac533ad3b13d9929706184b6bfaca9`. Main includes the eleven earlier
reviewed IDs; the three October 4 IDs remain only in PR16. All FOURTEEN were
excluded before selecting this batch. Earlier consolidation work is resolved
on main and was not redone. The original checkout was clean and preserved.

Fresh branch `perf/test-runtime-2026-10-05` starts from current main and targets
main directly. It has no executable dependency on PRs 14–16. Its three methods
match all open PR baselines; it does not copy PR16's test changes or PR15's parser.
For complete durable context only, it carries forward PR16's unchanged bench
ledger, measurements, inventory and history, then appends this batch and recovers
PR16's final observation. These shared documentation additions may require a
normal merge-conflict reconciliation when the independent PRs land; preserve all
records and regenerate manifests from the combined test tree. Do not count the
carried fourteen IDs as new work or silently drop PR16's unmerged optimization.

Measured implementation: `f32f32346b8b30c7bd84c7580a66ed0e91276f7d`.
Three NEW reviewed IDs (seventeen reviewed in the complete ledger):

- `test_interim_recovery.RecoveryBoundaryTests.test_consumed_elapsed_is_validated_before_accounting`
- `test_interim_coordinator.CoordinatorTests.test_operation_binding_parity_matrix`
- `test_interim_recovery.RecoveryBoundaryTests.test_shared_boundary_red_matrix`

Diagnosis: repeated checkpoint validation performs identical input-only successful
Git syntax checks. Apply the unchanged invocation-scoped `memoized_control_refs`
to these three methods only. Test bodies, assertions, helpers and production
sources are unchanged. The 21 elapsed fault combinations, 53 binding mutations
across three boundaries (159 subcases), and 11 shared boundary cases remain.
Real publication/CAS, corrupt checkpoint injection, refusal-before-sends checks,
independent clone/reload, deep copies and temporary fixture isolation remain real.
Faults alter provider receipts and checkpoint data, not subprocess outcomes or
the Git executable/environment. Every validator runs; failures and other Git
commands remain uncached. Cache reset and restoration retain the existing guards.

Three alternating baseline/candidate pairs ran sequentially in fresh processes
on clean checkouts, Linux x86_64, Python 3.12.14, Git 2.52.0, non-root, with canonical
Git maintenance disabled. No other workspace tests ran during measurement.
Command: `python3 bench/profile_delivery_tests.py --root CHECKOUT --repeat 1
--output REPORT` with one `--test` for each exact ID above; repeat before/after
three times. Setup, method and cleanup are included. All 18 executions passed;
zero failures/errors/skips. All pairs improved and all ranges are disjoint.
Shared-host load/order variation remains possible; these are narrow targeted
results, not a whole-suite causal estimate.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| consumed elapsed validation | 6.987 (6.873–7.177) | 5.977 (5.871–6.214) | 14.45% |
| operation binding parity | 5.798 (5.737–6.051) | 5.344 (5.200–5.552) | 7.82% |
| shared recovery boundary | 5.428 (5.347–5.479) | 4.570 (4.446–4.756) | 15.81% |

Evidence: [before](2026-10-05-linux-before.json),
[after](2026-10-05-linux-after.json), [comparison](2026-10-05-linux-comparison.json).
Reports bind every delivery test-source hash and exact revisions. No sampled
failure was discarded and no additional timing-only full suite was run.

Ordinary CI history recovers PR16 final run 37170621708 at its exact head:
762 executions, 930.348 summed seconds. Both terminal success and job association
were rechecked, and the collector reproduces every field and source hash in the
PR16 final JSON after stripping the connector's UTF-8 BOM. The initial transfer
added a newline/BOM and failed the hash-equality check; lossless transfer and BOM
normalization resolved it before admission. The 991.362s earlier checkpoint and
803.053s October 3 final are retained as distinct observations. Original remains
1135.863s / 756 executions. See [totals](TOTAL-RUNTIME.md) for qualified comparisons.

Latest feature run 37243478663 at PR14's current head succeeded fully. Independent
source discovery (without test execution) found 640 edition and 537 delivery
executions over 43 + 15 groups. The initial local discovery script read only the
literal delivery SETS assignment and omitted its later appended advance module;
review of the actual runner corrected discovery to evaluate the complete SETS
before collection. No incorrect inventory was published. The new
[manifest](manifests/0a1b232c4d23725f268eef5aa993cc72a43b5554.json) binds 58 module
hashes and four provenance hashes. Old manifests were not relabeled and expected
counts were never inferred from logs. Unchanged PR15 collector supplies the
parallel extraction; no collector work is duplicated or required on this branch.

Parallel totals are separate: 2628.000 overlapping summed seconds, 614.878525s
parallel job-log span; command spans 610.712874 / 586.314698s. Compared with the
prior recorded equivalent-concurrency feature run: +195.099s (8.02%) and +23
executions, +2 edition groups. API timestamps are unavailable in this tool's
normalized metadata; setup, queue and exact workflow time are not inferred.
The newer feature head supersedes the supplied d5964dee/37223574371 checkpoint;
that intermediate run is not relabeled or treated as today's inventory.
Runner/count/suite growth and unknown load prevent causal attribution.

Repository AGENTS/digest and manual stage-08/09 routes were read. No relevant
installed project or user `.agents/skills/SKILL.md` exists in this environment.
Bootstrap is n/a to maintenance of the playbook source repository. No production
behavior changes need new regression tests; existing guards and unchanged
integration assertions are the verification seam. Browser QA is n/a for this
test-only change. No credentials/security/workflows were changed; privileged
watchers remain assigned to existing normal GitHub Actions. CLI API calls return
Forbidden, while ordinary Git and the connected GitHub tool remain usable.
All commits use noreply author and committer identities. No merge or deployment.

Next unreviewed screening candidates:

- `test_interim_monitor.MonitoringTests.test_repair_worker_errors_keep_one_monitored_failed_operation`
- `test_interim_recovery.RecoveryBoundaryTests.test_explicit_uncertain_stop_retry_retains_confirmed_progress`
- `test_interim_coordinator.CoordinatorTests.test_receipt_acceptance_parity_diagnosed_cases`

Profile afresh and inspect purity/fault boundaries; prior regression execution
alone is not a performance review. Four fanotify watcher IDs still lack successful
local timing and require privileged correctness CI. Never change permissions to
obtain their timings. Final frozen-head CI and collection belong in the draft PR
as well as the durable evidence checkpoint below, avoiding endless evidence-only
commits that each trigger another full CI run.

Fresh-context independent test review passed whole-module AST parity after
removing exactly three decorators. Independent execution passed seven tests in
17.039s, zero failures/errors/skips, instrumenting all 191 subcases (21 + 159 + 11).
The reviewer independently reproduced all 32 source hashes, all 18 successful
samples and comparison arithmetic, and verified exclusion of all fourteen prior
IDs. No findings or edits; read-only behavior was not filesystem-enforced.

Local canonical `python3 v0.5/scripts/verify-playbook.py --skip-delivery` passed
228 edition tests in 15.305s plus privacy/content, conventions, links, generated
status/inventory/manifests and drift current through 2026-10-08. Nine main collector
guards passed after a guard caught a hand-appended totals appendix: regenerate
TOTAL-RUNTIME.md exactly from the unchanged main renderer; keep parallel evidence
in this ledger and supplemental history. No parser or test guard was weakened.
These local checks are partial correctness evidence, not a full-suite runtime row.
No executable source changed after measurement/review. Final privileged integration
CI remains required and its terminal result will be recorded on the frozen draft.

Fresh-context independent evidence review passed: separate-process discovery
reproduced all 58 ordered module counts/hashes and four provenance hashes, then
reviewed shard labels, buffered outputs and exit propagation. PR15's 17 collector
regressions passed in 0.015s; its unchanged collector independently reproduced
the complete latest feature row. Main collector independently reproduced every
field of PR16's final record and verified supplied API timing arithmetic.
Live run/job status and latest-head selection were checked separately by the
owning session. Reviewer executed no feature suites and edited no tracked files.

Independent count-only discovery on this batch's source confirms 228 edition +
534 delivery executions across 1 + 15 groups. Exact canonical commands remain
`python3 v0.5/scripts/verify-playbook.py --skip-drift --skip-delivery` and privileged
`sudo python3 v0.5/delivery/scripts/verify.py --set K4.1` (CI resolves the configured
interpreter). This branch starts from main's eleven optimizations, so PR16's three
unmerged optimizations are absent: comparisons against its final total are
observations across independent branches, not a cumulative optimization estimate.
The overlapping parallel feature sum never enters this serial comparison cohort.

### Ordinary batch CI checkpoint

Normal draft PR17 run 37253579646 passed at `ca5ce4bdf32fcadf2743084078c9229e9984f2b8`.
Edition job 111585967534 and privileged delivery job 111585967387 succeeded;
all 762 executions (228 + 534) passed in 16 groups, zero unittest skips.
Count-only source discovery matches every logged group. Synthetic checkout:
`84d363bd053248926d7e2a893d8292d01724524c`. Full delivery ran, including watchers.

Summed unittest runtime: **952.408s**, including fixtures/cleanup and excluding
interpreter startup and standalone CLI checks. Versus October 4 final 930.348s:
**+22.060s (+2.37%)**; versus October 3 final 803.053s:
**+149.355s (+18.60%)**; versus original 1135.863s:
**-183.455s (-16.15%)**. Counts remain 762 versus
original 756. These are observed differences, not causal test-optimization gains;
runner/load and the absent PR16 optimizations prevent cumulative attribution.

Edition/delivery command log spans: 20.413823 /
936.975882s. Parallel job-log span:
942.445712s, including logged setup/cleanup, excluding
queue/pre-log setup. Exact setup, queue and workflow elapsed are unknown.
Runner: Python 3.12.14, Git 2.55.0,
ubuntu-24.04 image 20260927.320.1;
hardware/load unknown. Original image was 20260920.314.1.

Collector accepted complete logs; history retains commands, group counts, head,
checkout, run/job IDs and source hashes. This evidence-only commit changes no
measured executable source. Its final frozen head gets normal CI, with terminal
result and final collector JSON retained in PR17's description to avoid an
unending evidence-commit/CI cycle. No timing-only full suite was requested.

Fresh independent evidence review reproduced the checkpoint row field-for-field,
all 16 source-discovered group counts, both input hashes, 952.408 = 18.399 +
934.009 seconds, 942.445712s log union and every comparison above. All ten prior
serial records remain unchanged and TOTAL-RUNTIME.md exactly matches the canonical
main renderer. Nine collector guards passed again. Privacy/content, conventions,
links, manifests, whitespace and executable-source parity passed for this final
evidence-only follow-up. No review findings or tracked reviewer edits.

## 2026-10-06 — batch 7 (UTC)

Live readback confirmed main `8827c7a1190ed64d0a70c9efaeca91cdb841be27`,
open independent drafts PR16 `aaba65cc8bac533ad3b13d9929706184b6bfaca9` and
PR17 `73884dbc3474a694aa54a3e7a8e5c39066f042e0`. Actual merge-base of both drafts
is that main revision. Both complete review and runtime ledgers were read before
selection; **all seventeen prior reviewed IDs were excluded**. This fresh branch
targets main directly and carries forward PR17's complete bench context, including
PR16's records, without either draft's executable changes. No resolved integration
is repeated. Shared evidence files will require ordinary reconciliation if the
independent drafts land; preserve all records. No executable dependency on PR14,
PR15, PR16 or PR17, and no merge or deployment.

New reviewed IDs (twenty reviewed in total across main and open drafts):

- `test_interim_monitor.MonitoringTests.test_repair_worker_errors_keep_one_monitored_failed_operation`
- `test_interim_recovery.RecoveryBoundaryTests.test_explicit_uncertain_stop_retry_retains_confirmed_progress`
- `test_interim_coordinator.CoordinatorTests.test_receipt_acceptance_parity_diagnosed_cases`

Measured baseline `8827c7a1190ed64d0a70c9efaeca91cdb841be27`; measured implementation
`fb1836b4cd2424507824d43974aec0fef72ab28f`. Apply the existing successful exact
Git ref syntax cache separately to each selected method invocation. Every validator
still runs. Git executable and environment remain fixed, invalid probes remain
uncached, and all other subprocess commands remain real. Faults concern provider
observations or receipt contents, not Git syntax subprocess failures. All method
bodies, assertions, isolated fixture reset, deep copies, real publication/CAS,
corrupt injection, clean-clone rejection and reload/resume checks remain intact.
Cache lifetime ends even on exceptions; no production behavior changes.

Three alternating before/after pairs ran sequentially on clean pinned sources in
fresh processes: Linux x86_64, Python 3.12.14, Git 2.52.0, non-root, canonical
Git maintenance disabled, no concurrent workspace tests during measurements.
Command: `python3 bench/profile_delivery_tests.py --root CHECKOUT --repeat 1
--output REPORT` with each exact ID above supplied by `--test`; repeat the pair
three times. Setup, method and cleanup are included. All 18 executions passed,
zero errors/failures/skips; every pair improved and all ranges are disjoint.
No samples were discarded. Shared-host load/order effects remain possible;
these targeted comparisons are not a causal whole-suite gain estimate.

| Test suffix | Before median (range), s | After median (range), s | Reduction |
| --- | --- | --- | --- |
| monitored repair worker errors | 5.276 (5.144–5.297) | 3.956 (3.930–3.981) | 25.01% |
| explicit uncertain stop retry | 4.391 (4.275–4.447) | 3.742 (3.671–3.833) | 14.78% |
| diagnosed receipt acceptance parity | 4.121 (4.028–4.122) | 3.353 (3.269–3.357) | 18.63% |

Evidence: [before](2026-10-06-linux-before.json),
[after](2026-10-06-linux-after.json), [comparison](2026-10-06-linux-comparison.json).
Exact revisions, all sixteen source hashes per revision and all samples are retained.

Recovered ordinary PR17 final-head run 37254926824 from its successful associated
edition job 111589848727 and full privileged delivery job 111589848865. Unchanged
main collector reproduces the final description's complete record, both input
hashes included after removing the connector BOM. All 762 executions (228 edition
plus 534 delivery, sixteen groups) passed: **970.447 summed test seconds**.
This row joins the existing durable history; no old row is replaced. October 4
final remains 930.348s, October 3 final 803.053s and original
`a57af6de259d34e9b772105e0ad0610290797cfa` 1135.863s / 756 executions.
PR17 final is 4.31% above October 4, 20.84% above October 3 and 14.56% below original.
These are observations across independent branches, not cumulative causal gains.

PR14 remains `0a1b232c4d23725f268eef5aa993cc72a43b5554` and exact-head run
37243478663 remains successful; there is no newer revision to inventory. Preserve
PR17's independently reviewed 640 edition + 537 delivery inventory (43 + 15 groups),
source hashes and **2628.000 overlapping summed seconds** separately. Its manifest
and record are unchanged. PR15 remains open at
`2c7f4528884a21756c4e126d410d671eef86e766`; its parallel collector and seventeen
guards are not duplicated, replaced or removed. No obsolete discovery or feature
qualification was repeated, and no paid model comparisons were attempted.

Sum semantics: unittest seconds include fixtures/cleanup, exclude interpreter
startup and standalone CLI checks. Command spans include shell/check overhead.
Parallel job-log span is an elapsed proxy including logged setup/cleanup and
excluding queue/pre-log setup; it is never a sum of parallel durations. Exact
queue/setup/workflow times remain unknown where unavailable. The recovered PR17
row records edition/delivery command spans 23.703220/951.954170s and job-log span
954.564812s, Python 3.12.14, Git 2.55.0, Ubuntu 24.04 image 20260927.320.1.
Original image was 20260920.314.1; actual hosted hardware/load is unknown. Counts
grew by four cache guards and two content regressions since original. This branch
contains main's eleven optimizations plus today's three; six PR16/17 test edits
remain absent. Never attribute ordinary CI variation to today's decorators.

Repository AGENTS/digest and manual stage-08/09 instructions apply. No relevant
installed `.agents/skills/SKILL.md` was present; bootstrap is n/a for maintenance
of the playbook source. Browser QA is n/a for this test-only change. Existing
cache guards and preserved integration assertions cover the seam; no new behavior
requires a new regression test. CLI API Forbidden is handled by the existing
connected GitHub app; no credential/security/workflow changes. Both Git author
and committer use noreply identities; public-content validation is required.
Local partial checks are not full-suite timing rows. Existing privileged CI owns
watcher correctness; no local permission workaround or extra full-suite run solely
for timing. Final frozen SHA, terminal CI and complete collector JSON will be
retained in the draft PR description to avoid repeated evidence-commit CI cycles.

Next unreviewed screening candidates, following the retained ranking:

- `test_pack_lifecycle.PackLifecycleTests.test_installed_preflight_accepts_one_nested_approved_envelope`
- `test_interim_recovery.RecoveryTests.test_stopped_receipt_wrappers_and_timestamps_must_be_truthful_utc`
- `test_interim_recovery.RecoveryBoundaryTests.test_exhausted_ceiling_enumeration_failure_does_not_invent_a_wake`

Inspect each purity/fault boundary and measure afresh; do not force a change or
claim an improvement from the old single-run ranking. Four fanotify watcher IDs
remain excluded from local performance claims and require privileged CI correctness.

Fresh-context independent review executed all three selected tests and four cache
guards: **seven tests / 46 subcases (3 + 3 + 40), 11.572s, zero failures/errors/skips**.
It proved whole-module AST equality after removing exactly three decorators and
one import, verified all 32 source hashes against pinned Git revisions, all 18
successful samples, raw-to-aggregate equality and every timing calculation, and
independently excluded all seventeen prior reviewed IDs. Review used separate
context and read-only behavior, not filesystem-enforced read-only isolation.
The unchanged collector independently reproduced every field/hash of PR17 final
and the current history row. Source-only discovery independently found 228 edition
and delivery groups [75, 8, 62, 11, 55, 14, 40, 33, 29, 19, 15, 93, 17, 18, 45],
534 delivery / 762 total executions. No full-suite tests ran for discovery.

Local canonical `python3 v0.5/scripts/verify-playbook.py --skip-delivery` passed
228 tests in 14.930s plus conventions, metadata, links, privacy/public content,
status/inventory/manifests and drift current through 2026-10-08. Nine collector
guards passed. Delivery and edition manifests are regenerated; Python source
remains exactly the measured implementation. No separate lint/type runner is
configured; canonical conventions and Python execution cover the relevant lanes.
No production, workflow or security changes. These are partial local correctness
results; final normal CI owns complete privileged integration. The next evidence
checkpoint is the frozen PR description, not another evidence-only commit.

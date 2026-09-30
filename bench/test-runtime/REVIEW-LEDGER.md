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

The complete per-test Linux ranking remains outstanding: existing CI validates
the suite but does not collect the profiler's per-test timing artifact. The
partial 290-test local exploratory report and the earlier two-group 89% claim
remain unsuitable for a complete ranking or suite-wide speedup claim. The three
next-candidate IDs above were confirmed against the source class/method names;
none has been reviewed or changed by this continuation. Do not repeat today's
three reviewed IDs in the next batch.

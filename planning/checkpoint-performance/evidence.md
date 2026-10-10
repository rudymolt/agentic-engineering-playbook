# Checkpoint performance evidence synthesis

These are diagnostic observations, not acceptance receipts. Raw profiles and
the original discussions remain in the private tracker and ignored workspace
evidence; only the reviewed conclusions belong in this public planning folder.

## Initial reference baseline

The clean baseline is `a3daedf03b24c5b3feb41d5953272d281de7b283`; the separately
resolved guidance comparator is `9d8dc1a5ec583aa3cd727a52d06dcd5438bf2a8e`.
The initial reference run used Ubuntu 24.04.5, image `20261004.327.1`, four
x86_64 CPUs, Python 3.12.15 and Git 2.55.0. This refreshes the historical Python
3.12.14 reference. Delivery timing and diagnostics ran privileged with one worker;
both guidance references ran unprivileged with one worker on the same runner.
Both unchanged required CI jobs passed before the sequential measurements.
Raw reports, hashes, logs and independent review receipts are retained privately.

| Complete measurement | Initial wall time |
| --- | ---: |
| Serial K4.1, including generated checks and process overhead | 692.330 s |
| Standalone recovery, all 29 tests | 368.620 s |
| Standalone coordinator, all 26 tests | 164.136 s |
| Current baseline guidance, all three files and 154 tests | 205.299 s |
| Fixed comparator guidance, all three files and 154 tests | 264.634 s |

Independent source and runtime inventories confirm all 15 expanded K4.1 files
and 526 test IDs, including advance tests. All recorded outcomes passed, without
skips. Serial recovery/coordinator spans were 372.829/152.710 s. The remaining
13 files plus generated checks and all suite overhead give **R = 166.791 s**,
so the recovery/coordinator budget is strictly less than **193.209 s**. Meeting the
120/60 s file limits would fit that budget; no additional residual saving above
the 180 s remainder is required. The complete suite still needs more than
332.330 s of saving at this observation. Complete delivery CI job durations were
317 s and 421 s, with queue delay recorded separately; neither meets 300 s.

Separate full-file diagnostics retain recovery counts of 6,430 pushes, 888
clones, 2,151 fetches and 2,199 remote-ref queries; coordinator counts are
3,236/450/749/775 respectively. Every sample has ordered identity, duration and
outcome attribution. Initial seed/setup work and matrix execution are retained
separately. The diagnostic native Git time sums are 281.988 s recovery and
146.203 s coordinator, including 43.816/30.017 s in cloning. These are measured
cost partitions, **not portable timing floors or acceptance timing**. Repacking
could also affect retained Git-call latency; its whole-file effect is unmeasured.
The one guidance ratio is below 0.80, but the required paired repetitions and
final-candidate qualification remain pending.

Independent review passes the initial measurement evidence and all measurement
implementation fixes, including native subprocess compatibility, class/case
attribution, ordinary output permissions, report privacy, empty-selection
failure and concurrent sample ordering without serialising real Git execution.
It records substantial uncertainty about the required 63–67% standalone
improvement. An accounting stress test removing every
clone, all setup/recognised seed Git work and the entire non-Git remainder leaves
338.334 s of observed Git work across the two files. This is neither a forecast
nor proof of impossibility, and real construction/restoration/validation must
still cost time.

The verifier initially requested a new scope disposition, then withdrew that
blocking finding after checking the recorded human approval and the conditional
R budget. The existing build-all choice already accepts uncertain experiments;
R below 180 s introduces no additional saving requirement. No concrete capability
or scope blocker was demonstrated. **S1's initial measurement gate passes** and
the unchanged approved S2 experiment may proceed without renewed confirmation.
The cost partition remains a diagnostic risk, not an assumed saving. Any broader
experiment still needs its own scope decision. All targets, publication/reload
coverage and production authority remain unchanged; no production optimisation
has landed, and final qualification remains pending.

## What the whole-file review adds

The initial analysis profiled selected existing tests at public revision
`ec8e28a`. A later whole-file run used Python 3.12 and Git 2.50.1, wrapping Git
subprocesses without cProfile. Another test run overlapped part of the recording.

| File | Tests | Wall time | Git subprocess time | Git calls |
| --- | ---: | ---: | ---: | ---: |
| Recovery | 29 | 870.9 s | 86.7% | 85,075 |
| Coordinator | 26 | 388.4 s | 94.3% | 37,663 |

Push, clone, and remote URL queries dominate these recordings. This supports
putting Git work ahead of Python cleanup. Contention affects both absolute times
and proportions: neither ratios nor a fixed conversion to CI are portable.
The selected-test profiles still identify Python hotspots, but do not represent
the whole recovery file. Profiled cumulative times overlap and must not be added.

A controlled loose-object probe reported lower transport-clone cost after a
foreground repack. This makes fixture-only repacking worth measuring, including
the repack's own cost. It does not prove a whole-file gain or an optimal cadence.
The interleaved fsync probe found no useful improvement; changing durability
settings is excluded. The proposed combined 25–35% saving remains a forecast,
not a measured result or a ceiling.

## Corrections and retained safeguards

The suggestion to remove `--no-local` was withdrawn. Preserve the existing
transport-mode clone helpers and never introduce background fixture maintenance.
Parent-process maintenance environment settings alone are insufficient evidence
that the receiving Git process has maintenance disabled. Verify effective
behaviour and configure only disposable, test-owned repositories if needed.

The suggested replacement of two `remote get-url --all` calls with one
`remote -v` call is unsafe. A fresh disposable-repository probe with two fetch
URLs and one explicit push URL produced two fetch URLs from `get-url --all`, but
only one fetch row and one push row from `remote -v`. The second fetch URL would
escape a cardinality check. Rewrite expansion alone does not establish
equivalence. Retain the current checks; any future replacement needs evidence
for complete URL multiplicity and effective rewrite semantics.

Safe Python candidates remain operation-local validation, copying, hashing, and
encoding reuse. Guidance also has a repeated Unicode range scan and repeated
reviewed-entry validation. Optimising them must preserve exact normalisation
order and fresh admission across public operations.

Seed reuse is a separately accepted fixture-semantics experiment, not an
established saving.
Its value must be measured after accounting for seed construction, isolation,
copying, and restoration. No finding justifies removing any
matrix cell's durable publication or recovery readback.

## Specification review disposition

Accepted the review's same-path restoration correction: approval validation
binds fetch/push URLs through the approval digest, and persistence forbids an
approval change. The seed must be built at its eventual working path, preserved
unchanged, then restored there for sequential tests within one worker/class.
Moving the live fixture to a new identity and rewriting its approval is excluded.

Accepted exact comparator commits, explicit guidance-file membership, a serial
K4.1 baseline, recorded runner facts, worker-side instrumentation, measured
loose-object thresholds, and countable publication/reload invariants. The spec
requires numeric attribution of seed savings and preserves each matrix case.

Two refinements to the review: the runtime-expanded K4.1 set has 15 files, not
14, because the verifier appends advance tests to each set. Also, 180 seconds
for the other files is a planning remainder when the two target files consume
their full combined allowance, not proof that the suite target is impossible
above that remainder. Measure the actual residual budget. Retry/race command
counts require per-case attribution; deterministic counts must match exactly.

## S2 preliminary fixture-maintenance evidence

The frozen candidate opts in only the sequential coordinator fixture and the
recovery-owned repair helper. It counts loose object files in the owned bare
remote and performs a foreground `repack -a -d` at 512 objects before the next
transport clone. The receiving repository stores `gc.auto=0`,
`maintenance.auto=false`, and `receive.autogc=false` locally. The shared fixtures
used by concurrent-writer tests remain outside the opt-in.

One clean complete-file pair ran candidate then baseline, sequentially, on the
diagnostic Amazon Linux VM with Python 3.12.13, Git 2.50.1 and one worker. Costs
include interpreter startup, fixture setup, object scans, repacking and cleanup.
This pair is experimental evidence; final target qualification still requires
the specified repeated reference-class measurements on the final revision.

| Complete file | Baseline seconds | Candidate seconds | Reduction | Retained tests |
| --- | --- | --- | --- | --- |
| Recovery | 899.242 | 828.848 | 7.8% | 29, all passed |
| Coordinator | 405.947 | 354.629 | 12.6% | 26, all passed |

The original ordered test IDs and outcomes match exactly. An earlier warmup
passed both files but briefly overlapped the focused red/green checks; its raw
results are retained privately and excluded from this comparison. Two focused
real-Git checks pass for threshold maintenance, reachable-history/transport
readback and refusal of foreign/symlinked remotes. Independent static review
found no concrete defect. Matched diagnostics passed all 55 tests and require
exact equality for every test/class/case/phase in each boundary category:

| Complete file | Push | Clone | Fetch | Ref read | Foreground repacks | Repack seconds |
| --- | --- | --- | --- | --- | --- | --- |
| Recovery | 6,430 | 888 | 2,151 | 2,199 | 9 | 0.769 |
| Coordinator | 3,236 | 450 | 749 | 775 | 13 | 1.276 |

Each of the four boundary totals and attributed counts matches the baseline;
maintenance removes no publication or reload. Diagnostic durations are kept
separate from timing acceptance. Independent runtime review executed supplied
and adversarial real-Git support probes, 28 existing integration tests and both
writer races successfully. It found the stale delivery manifest; the builder
regenerated delivery then edition manifests. Fresh independent verification
reproduced and resolved that finding, reran relevant checks, audited the exact
counts and accepted the experiment with no open findings. The accepted risk is
one preliminary diagnostic-VM pair; final repeated reference qualification
remains S6-owned.

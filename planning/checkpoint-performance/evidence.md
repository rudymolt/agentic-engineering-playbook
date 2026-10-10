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

## S3 preliminary seed-restoration evidence

Each recovery class builds its complete initial failed-S2 or repair snapshot
once per worker process through the original fresh fixture and production
transitions. A separate read-only template retains the complete quiescent tree.
Sequential tests restore ordinary independent copies to the original absolute
working path, reconstruct validated snapshots and fresh stores/counters, and
retain approved URLs, checkpoint bytes, digest and history. Templates use no
hard links or object alternates and receive no Git operations. Existing
within-test fresh resets and all original matrix bodies remain unchanged.

One clean complete-file pair ran candidate then the clean S2 baseline on the
same diagnostic VM with Python 3.12.13, Git 2.50.1 and one unprivileged worker.
Whole-process timings include construction, copying, restoration, teardown,
interpreter startup and process-exit template cleanup. A concurrent static
review performed no test/profile execution; runtime review waited for the
sequential timing and diagnostic batches to finish.

| Complete file | Baseline seconds | Candidate seconds | Change | Retained tests |
| --- | --- | --- | --- | --- |
| Recovery | 836.926 | 801.227 | 4.3% lower | 29, all passed |
| Coordinator, unchanged control | 358.684 | 359.835 | 0.3% higher | 26, all passed |

Separate fresh diagnostic runs pass all original IDs/outcomes. The only
boundary reductions are initial seed construction:

| Boundary | Recovery baseline | Recovery candidate | Removed | Coordinator, both |
| --- | --- | --- | --- | --- |
| Push attempts | 6,430 | 6,170 | 260 | 3,236 |
| Transport clones | 888 | 834 | 54 | 450 |
| Fetch attempts | 2,151 | 2,151 | 0 | 749 |
| Ref reads | 2,199 | 2,172 | 27 | 775 |

The 14 initial failed-S2 builds and 15 initial repair builds formerly cost
279 pushes, 58 clones and 29 ref reads. Two retained class builds cost
19 pushes, four clones and two ref reads, yielding exactly the table's net
reductions. Every original test's initial-construction delta matches separately.
All 11,053 matrix boundary attempts across the 860 attributed test/subtest
identities match by test/class/case/category; coordinator counts also match
exactly by test/class/case/phase/category. Failed attempts remain counted.

The three focused real-Git regressions exercise mutation/deletion restoration,
template immutability, independent storage/configuration/memory, class ownership,
and fresh worker/single-selected-test execution. Original recovery test method
ASTs and coordinator source are unchanged; setup assertions still run per test.
Fresh independent runtime review accepts the experiment with no open findings.
It recomputed the raw counts and confirmed the complete ordered native streams
after removing only each initial seed prefix. It executed three supplied
regressions, five adversarial cases, 17 original recovery selections in both
orders, individual original tests, 18 persistence/authority tests, both writer
races and original coordinator matrix checks. Simultaneously live workers,
reachable history/parents, template immutability and refusal of Git against
the template were verified. Both refreshed manifests and focused public checks
pass. One preliminary VM pair remains an accepted experimental limitation,
not final performance qualification. All repeated reference-runner targets
remain S6-owned.

## S4: checkpoint validation reuse rejected

A bounded lifecycle experiment admitted an owned checkpoint once and reused it
only before mutation. Public persist overrides and monitoring projections kept
their validating seam. Review found a custom-copy admission gap; regressions
reproduced it and an exact-builtin snapshot/original-input fallback corrected it.
Additional callable-proxy and foreign-bound-method regressions corrected hook
routing. The corrected candidate passed 14 focused checks and all 18 existing
persistence tests. Fresh independent static review found no introduced defect.

The complete clean candidate/baseline pair used the same diagnostic VM,
Python 3.12.13, Git 2.50.1 and one unprivileged worker. Both original files and
all 55 IDs/assertions/matrix bodies were unchanged and passed at both revisions.
Wall times include setup, cleanup, interpreter startup and process exit.

| Complete file | S3 baseline seconds | Experiment seconds | Change | Tests |
| --- | --- | --- | --- | --- |
| Recovery | 821.682 | 816.880 | 0.6% lower | 29, all passed |
| Coordinator | 367.472 | 371.424 | 1.1% higher | 26, all passed |

Combined wall time changed from 1,189.153 to 1,188.304 seconds: less than one
second saved in one pair, with a coordinator regression. This does not justify
retaining the additional checkpoint machinery. The experiment is rejected;
production source is restored byte-for-byte to the S3 predecessor and no
validation-reuse optimization or admission flag lands. The experimental
regressions, exact diff and raw reports remain in ignored evidence.

Two earlier interrupted measurement sets are retained and excluded because
their source preceded the admission/hook corrections. Diagnostics for the
rejected final experiment were stopped after the clean retention decision; no
native-attempt parity or reference target is claimed for that discarded code.
Retained production authority, original tests and native protocol are unchanged.
Independent rejection/reversion verification precedes the atomic documentation
checkpoint. S5 and final S6 qualification continue; every original target
remains binding and the feature stays open.

## Guidance experiment stop checkpoint

The S5 candidate replaced the default-ignorable range scan with immutable lookup
and attempted operation-local canonical-byte/revision reuse. Supplied checks
passed 50 configuration and 41 recommendation tests, including legacy numeric
keys, tuples, surrogate strings, independently copied subclasses and shared
instance attributes. All 154 original guidance IDs passed on the latest candidate.
These outcomes do not establish safety or performance acceptance.

Fresh independent runtime probes confirm two gaps in the ownership proof. A
removed member descriptor leaves allocated mutable slot storage shared by the
caller and retained copy. A class descriptor hook can also mutate the copied
container after its child snapshot and canonical-byte comparison, retaining
shared caller state with a revision that no longer matches the retained bytes.
Only minimal retention probes ran; no downstream Apply bypass is claimed.

This is the third recurrence of the caller-ownership condition and triggers the
approved stop guard. The cumulative identical-failure count is three, with zero
no-progress iterations; no fourth repair begins. All three S5 measurement sets
are retained privately but excluded. The last set stopped during predecessor
measurement, so it is not a complete accepted comparison. Microtest results and
partial groups cannot substitute for the required reference qualification.

The rejected candidate, source hashes, regressions and independent reproduction
receipts are preserved privately. All four S5 source/test files are restored
byte-for-byte to the accepted checkpoint; neither the lookup nor proposal reuse
is retained. S1–S3 remain accepted, S4 remains rejected, and S6 has not started.
The full final verifier and repeated reference qualification remain pending.
Both required CI jobs passed on the last accepted draft head. The umbrella stays
open; all original target thresholds, comparators and safety/count requirements
remain binding. Resume requires a human disposition of this stop; counters are
not reset by a handoff.


## Approved Unicode-only continuation

After the recorded stop, the maintainer approved an Astra diagnosis and then
explicitly rejected proposal-retention reuse, selected Unicode-only S5 with Sol,
and authorized S6 qualification. Diagnosis probes reproduce hidden-slot sharing
on the original implementation as well as the rejected candidate; descriptor
mutation that creates a stale revision is introduced by the rejected inspector.
A benign iterator subclass is also newly refused by that inspector. The original
Python API behavior is retained. Its arbitrary custom-object isolation remains
an explicit unresolved compatibility question; no universal safety pass or
unapproved narrowing is inferred. Failure history is preserved, not reset.

The Unicode candidate constructs an immutable lookup from the unchanged inclusive
default-ignorable ranges. It preserves deletion before NFKC, composition,
whitespace collapse/strip, supplementary boundaries and surrogate values. No
proposal, reviewed-guidance, inventory or approval data is cached. Proposal and
delivery source remain byte-for-byte identical to the accepted checkpoint.

A work-count regression is red on the original renderer: 1,300 characters cause
22,100 code-point conversions. The lookup passes that budget and independent
interval-slicing equivalence across every Unicode code point. All 42
recommendation tests and 37 original configuration tests pass; all original test
method bodies remain unchanged. One new test initially used literal escape text;
only its test strings were corrected before any retained measurements.

One sequential complete-group measurement set uses Python 3.12.13, Git 2.50.1,
eight CPUs, one unprivileged worker and the same profiler on the diagnostic VM:

| Role | Process-inclusive wall | Original guidance IDs |
| --- | ---: | ---: |
| Unicode-only candidate | 216.193 s | 154 |
| Clean predecessor | 232.853 s | 154 |
| Exact fixed guidance comparator | 370.916 s | 154 |

All outcomes pass without skips. The candidate/predecessor ratio is 0.928
(7.2% lower); its fixed-comparator ratio is 0.583. Source inventories and actual
runner facts match, and lookup construction/startup/cleanup remain inside wall
time. This supports retaining the experiment, which passes fresh independent runtime
review. It is one preliminary VM set, not the required paired median or a
CI-class target pass. S6 owns all repeated final-candidate measurements.

Fresh Sol source and runtime review finds no actionable defect. The reviewer
independently executes eight Unicode probes, all 79 affected tests, and the full
154-ID guidance group, then audits the matched raw timing/source/runner reports.
Focused publication and generated-file checks pass. Exact final status-wording
verification precedes the atomic checkpoint. The rejected proposal experiment
and all three excluded timing sets stay preserved privately. This new set belongs
solely to the approved narrower route; S6 qualification remains required.

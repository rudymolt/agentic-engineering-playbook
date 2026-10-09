# Checkpoint and delivery verifier performance spec

Status: accepted; all six slices approved for sequential Sol implementation.
See [alignment](alignment.md) and [evidence synthesis](evidence.md).

## Problem and outcome

Recovery and coordinator verification repeatedly publish and reload checkpoints
through real Git repositories. Recent optimisations improved overall verification
but left the individual files well above their targets. Reduce redundant work
without weakening checkpoint authority, persistence, recovery, or test coverage.
Close the remaining reviewed-guidance gap while keeping fresh admission at each
public operation. A faster test that proves less is not an acceptable result.

## User stories and acceptance

| Scenario | Acceptance criterion |
| --- | --- |
| A maintainer runs recovery verification alone. | The complete `test_interim_recovery.py` file takes less than 120 s. |
| A maintainer runs coordinator verification alone. | The complete `test_interim_coordinator.py` file takes less than 60 s. |
| A maintainer runs delivery serially. | The complete K4.1 suite takes less than 360 s, including fixture setup and cleanup. |
| A contributor waits for delivery CI. | The required delivery job takes less than 300 s; both existing required jobs remain enabled. |
| A maintainer verifies reviewed guidance. | The complete guidance test group takes at most 80% of the slice-4 baseline duration under matching conditions. |
| A concurrent writer or altered remote invalidates authority. | Existing stale-writer, target mismatch, lineage and recovery assertions still reject or reconcile the same cases. |
| Configuration or reviewed guidance changes between operations. | The next operation reads and validates current authority; retained proposals cannot reuse stale approval. |

All existing test definitions, assertion calls, matrix dimensions, real Git
publication/reload boundaries, and failure outcomes remain covered. Test counts
alone do not establish this: review the affected fixtures and matrix bodies.
No tests move outside a measured group to satisfy its target.

The guidance group is exactly these three files in `v0.5/scripts`:

- `test_model_reviewed_guidance.py`
- `test_model_reviewed_guidance_boundaries.py`
- `test_model_reviewed_guidance_declarations.py`

Run all three completely and aggregate their serial wall times for the guidance
comparison. Retain their test-ID inventory alongside the timing evidence.

Historical integration observations were 252.5 s recovery, 122.6 s coordinator,
269 s delivery CI, and about 906 s full local verification. They are context,
not a new benchmark. The historical guidance comparison was 257.4 s after slice
4 versus 207.1 s after slice 5 (about 19.5%); the 20% target therefore remains
unmet. Reproduce the slice-4 comparator rather than applying 205.92 s as a
universal machine-independent threshold. Preserve the already-met full local
`--jobs 3` target of less than 1,200 s under comparable conditions.

## Design boundaries

### Measure through the existing benchmark seam

Extend [the delivery profiler](../../bench/profile_delivery_tests.py), rather
than publishing the exploratory scripts or creating a second framework. Keep
existing result handling and add opt-in Git counts, durations and ordered
per-call samples sufficient to identify growing clone cost. Capture command
categories and test IDs; do not log credentials, remote URLs, environment dumps,
or machine-specific command arguments. Failed tests and subtests must fail the
run, and instrumentation must leave subprocess behaviour unchanged.

Install diagnostic instrumentation inside `worker()`, before test loading; the
parent launches a fresh subprocess for each pattern. The existing
`memoized_control_refs` proxy delegates real calls to the subprocess module's
`run`, so instrument that seam rather than counting only the parent's launches.
Attribute calls to class seed construction, ordinary setup/cleanup, and test or
matrix execution so the permitted seed savings cannot conceal missing checks.

Separate diagnostic runs from uninstrumented acceptance timing. Record source
revision, dirty status, interpreter and Git versions, runner class, concurrency,
test selection/counts, outcomes, and measurement mode. Include fixture setup,
class setup, copying, maintenance, teardown and interpreter startup in file/suite
wall time. Do not subtract preparation time to meet a target.

### Reduce fixture Git cost first

Use the existing clone helpers in
[checkpoint tests](../../v0.5/delivery/tests/test_interim.py) and
[repair tests](../../v0.5/delivery/tests/test_interim_repair.py).
Benchmark synchronous repacking of the disposable bare remote at a justified
cadence before transport clones. Keep it only if complete file timings improve.
Preserve all reachable history and every existing clone and reload.
Prefer a measured loose-object-count threshold over an arbitrary fixed interval:
count loose object files directly in the owned remote, avoiding another Git
process just to decide whether to repack. Include the scan and repack costs in
the comparison and record the chosen threshold; this remains an experiment.

The helper must establish exclusive ownership and quiescence before maintenance;
finish all writes before repacking, and finish repacking before cloning. Retain
`--no-local`. Never run maintenance detached, prune objects concurrently, alter
user repositories, or change global Git settings. Verify the effective receiving
repository maintenance configuration, not just the parent's environment.
Existing concurrent-writer tests must retain their intended races. A helper
must not introduce a repack while those writers or readers are active.

### Preserve production Git authority

Keep the persistence boundary in
[interim.py](../../v0.5/delivery/src/delivery_pilot/interim.py) and object/ref
operations in [git_control.py](../../v0.5/delivery/src/delivery_pilot/git_control.py).
Retain fresh effective fetch and push URL checks, exactly-one-URL enforcement,
exact expected-ref compare-and-set, explicit push lease, unique write identity,
lineage checks, and ambiguous-push reconciliation. Preserve the current order
and failure behaviour at these boundaries.

Do not replace the two `get-url --all` calls with `remote -v`: the latter can
omit an extra fetch URL. Do not cache target configuration or external refs
across transitions. Long-lived Git processes, fast-import, fewer durable
commits, and a redesigned publication protocol are outside this spec.

### Reuse Python work within a proven operation boundary

Consolidate repeated validation/copying across recovery persistence and interim
lifecycle calls only when the exact same owned value has already been admitted.
An internal validated value must not be forgeable through a public input.
Revalidate after monitoring/projection or any other mutation. Keep public input
validation, independent return values and fresh external-state checks.

In [playbook_config.py](../../v0.5/scripts/playbook_config.py), reuse canonical
encoded bytes and revision results within an operation when the complete input
is unchanged. Do not change byte format, hash identity, global JSON formatting,
or reuse a mutable dictionary's cached digest across public calls.

In [model_recommendations.py](../../v0.5/scripts/model_recommendations.py), replace
the repeated default-ignorable range scan with an equivalent precomputed lookup
if measured beneficial. Preserve deletion before NFKC normalisation, then
whitespace collapse and stripping, including range boundaries and supplementary
code points. Reviewed-entry validation may be shared within an operation only
with an owned, immutable snapshot. Preserve fresh reviewed guidance, inventory,
confirmation withdrawal and proposal admission on later read/reply/apply calls.

### Isolated seed reuse: accepted scope

**Explicitly accepted by the maintainer during specification.** Permit a bounded
experiment that builds a complete S2/repair seed once per test class per worker
process and gives every test an independently restored repository tree.
Existing per-test seed construction remains the
fallback if the experiment fails its isolation or performance checks. Fewer
clone/reload checks within matrix cells remain excluded.

Approval binds the fixture's absolute fetch and push URLs into its digest.
Rewriting those paths in a copied record would change immutable authority.
Instead, reserve a unique working path for each class in each worker process,
build the seed there through the real production path, quiesce all Git work,
and save the complete tree as an immutable template outside that working path.
Before each sequential test, restore an independent copy into the identical
original working path. Do not execute Git against or mutate the saved template.

Each restoration replaces all prior mutable refs, objects, configuration and
worktrees, with no hard links or object alternates to the template or other
workers. Preserve approved URLs, approval digest, checkpoint bytes and history
unchanged; do not re-sign approval or bypass validation. Reconstruct per-test
in-memory stores, snapshots and counters to prevent cache/state leakage.
Tests in a class must not use the shared working path concurrently. Different
workers/classes need separate reserved paths and templates; no machine-global
seed. Existing within-test resets and concurrent-writer scenarios must retain
their intended behaviour. If these conditions cannot be met, retain fresh setup.

Keep explicit integration coverage of fresh seed construction and all existing
matrix-cell operations/assertions, including the current setup assertions.
Prove that mutating or deleting a restored tree cannot alter the saved template,
another worker, or a later restoration. Verify the template stays unchanged
after construction, test order does not affect results, and an individually
selected test still runs. Include seed construction, copying and restoration
cost in acceptance timing. Do not check in generated seed repositories.

## Measurement and verification contract

### Fixed comparators and runner evidence

| Role | Immutable revision |
| --- | --- |
| Slice-4 guidance comparator | `9d8dc1a5ec583aa3cd727a52d06dcd5438bf2a8e` |
| Slice-5 historical head | `01d8e7959bd0632424079ff07d4b9029e546922b` |
| Integration used by the diagnostic review | `ec8e28a229eea56734a63bb0e1144aa518bd0a53` |

The slice-4 comparator is not an ancestor of current main. Resolve and retain
that exact Git object in an isolated checkout before starting measurements;
do not substitute a moving branch tip. All three guidance files exist there.
The new optimisation baseline must separately name a clean, current main
revision; historical slice-5/integration observations do not replace it.

[Recorded runner evidence](../../bench/test-runtime/suite-history.json) identifies
Ubuntu 24.04, Git 2.55.0 and Python 3.12.14, with delivery running under `sudo`.
The [current workflow](../../.github/workflows/playbook-ci.yml) selects
`ubuntu-latest`, Python `3.12` and three delivery workers; these selectors float.
Capture the actual resolved image/tool versions and privileged flag for each
comparison and refresh the reference when they change. Use one worker for
standalone files and the serial suite, three for delivery CI. The diagnostic
VM's Git 2.50.1 is not the recorded CI Git version.

### Required measurements

1. Before optimisation, pin a clean baseline revision and the slice-4 guidance
   comparator. Use explicit `python3.12` and the same Git version, hardware/runner
   class, worker count and test selection for each baseline/candidate comparison.
   Use the current delivery CI runner class as the reference for absolute file
   and suite targets; local target runs need equivalent capacity. Slower analysis
   VMs supply diagnostic evidence, never times extrapolated into a target pass.
   Baseline and candidate revisions necessarily differ; repeated candidate
   measurements must all attest the same final revision.
   Establish a fresh serial K4.1 baseline under the reference runner's privilege
   conditions using `v0.5/delivery/scripts/verify.py --set K4.1 --jobs 1`, including
   generated-file checks and process overhead. The expanded K4.1 set currently
   contains 15 files, including `test_interim_advance.py`; record the resolved
   membership rather than assuming the literal tuple is the entire set.
   Report recovery, coordinator and the remaining 13 files separately. Let R
   be the other files plus suite overhead: the combined recovery/coordinator
   budget is strictly less than `360 - R` seconds. If R exceeds 180 s, meeting
   only the two file limits does not establish the serial target; quantify the
   additional saving needed before optimisation. If the required saving cannot
   be justified within scope, present that evidence for a scope decision. Keep
   the 360 s target unmet; never omit other files or silently loosen it.
2. Run at least three paired baseline/candidate repetitions for each local
   target, alternating order without overlapping test/profile runs. Report all
   durations, median and range, plus separate diagnostic command counts. Accept
   an absolute local target only when all three valid candidate runs meet it;
   guidance's median ratio must be at most 0.80. Document external contention;
   invalidate and rerun a contaminated pair without hiding the original result.
3. Measure delivery CI on the final candidate in three runs on the same runner
   class, all below 300 s. Report complete job duration separately from queue
   wait; retain both required jobs and their existing workload. A fast individual
   matrix test or one favourable CI run is insufficient.
4. Record per-file and attributed per-test counts of real Git `push`, `clone`,
   `fetch` and `ls-remote` calls in matched diagnostic runs. For repacking and
   Python-only changes, require identical counts on the same deterministic
   scenarios. Seed reuse is the sole permitted reduction: give the numeric
   baseline, candidate and delta for each category, reconcile the delta to
   eliminated repeated seed construction (including the retained class build),
   and require unchanged matrix-cell publication/reload counts. Count attempts,
   including injected failures. Classify retry/race variation separately with
   per-case evidence; do not excuse an unexplained drop as noise. Counts support,
   but do not replace, assertion and semantic review.
5. Test altered/multiple effective URLs (including an extra fetch URL plus an
   explicit push URL), fetch/push rewrites, stale ref/lease, push reconciliation,
   lineage, recovery corruption and mutable-input isolation at existing seams.
   Add focused regressions only where a changed boundary lacks coverage. Verify
   Unicode equivalence, malformed/changed guidance, changed inventory and stale
   proposal rejection for guidance optimisations.
6. Run affected files during implementation. On the final release candidate,
   run the full Python 3.12 `v0.5/scripts/verify-playbook.py --jobs 3`, record
   its wall time, and pass both required CI jobs. Update the edition changelog
   with a *Why* line for the implementation and regenerate affected manifests.
   Public-content failures block publication. A fresh independent review must
   execute relevant checks and inspect fixture semantics before ship.

The existing persistence, recovery/coordinator integration tests, public
configuration/guidance operations and benchmark CLI are the test seams. No new
framework or production service is needed. Browser/device QA is n/a: there is
no visual or interaction change. Raw evidence stays in ignored local storage or
private tracker attachments; publish only reviewed, sanitised summaries.

## Scope review and remaining uncertainty

Manual scope-guardian review: reuse existing modules and helpers; reject global
caches, weakened durability, URL shortcuts and broad Git rewrites. Fixture seed
reuse is the sole semantic expansion and has explicit maintainer acceptance.
Manual coherence review: use the live code's checkpoint, lifecycle, repair,
recovery, proposal and admission terms; this checkout has no root glossary to
update. The numerical targets and safety invariants remain unchanged.

The evidence cannot guarantee the twofold file improvements. Repacking cadence,
seed isolation feasibility and measured gain remain experiments with rejection
criteria, not promised results. Push alone accounted for roughly a quarter to
a third of each file in the contended diagnostic run; matrix-cell pushes remain
durable boundaries. This is a constraint on candidate savings, not a portable
timing floor. If safe changes miss the targets, keep the task
open and present measured residual costs and a concrete scope proposal; do not
silently weaken coverage or revise the targets.

Suggested order for later breakdown: reproducible measurement, fixture Git cost,
approved seed experiment, operation-local Python reuse, guidance, then final
qualification. This is design priority, not an authorised build sequence.
The maintainer approved the [six-slice breakdown](slices.md) and selected build
all with Sol. Continue through stage 07 one slice at a time with independent review.

```yaml
playbook_result:
  outcome: build-all-approved
  next_stage: "07"
  required_actions:
    - Build the six approved slices sequentially with independent review.
```

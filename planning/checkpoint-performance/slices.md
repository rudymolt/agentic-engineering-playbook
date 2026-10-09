# Checkpoint performance build breakdown

Status: approved; the maintainer selected build all six with Sol. The reviewed
[spec](spec.md) remains the acceptance contract. Sol is assigned to start S1;
runtime identity and the private tracker mapping are retained in handoff evidence.

Drafted using the pinned upstream to-tickets instructions after source retrieval;
the instructions are retained in ignored handoff evidence, not installed as a
global skill. The approved tickets are published as children of the tracker task.

## Approved frontier

| Slice | Outcome | Blocked by | Mode |
| --- | --- | --- | --- |
| S1 | Reproducible baseline and attributed Git diagnostics | None | AFK |
| S2 | Faster transport clones through safe fixture maintenance | S1 | AFK |
| S3 | Isolated seed restoration without changing approved identities | S2 | AFK |
| S4 | Less repeated Python work per checkpoint transition | S3 | AFK |
| S5 | Faster guidance verification with fresh public-operation admission | S1 | AFK |
| S6 | Final performance and safety qualification | S2, S3, S4, S5 | AFK |

The fixture and checkpoint chain is deliberately sequential so each experiment
has a stable predecessor and attributable costs. S5 needs only S1's comparator
evidence, but a single builder should run S1–S6 in displayed order to avoid
contending benchmarks. No parallel builds or overlapping benchmark runs.

## S1 — Reproducible baseline and attributed Git diagnostics

**Result:** initial measurement gate complete. The profiler, real reference
baseline, inventories and attributed diagnostics pass independent verification;
see [the evidence](evidence.md). The review's renewed-confirmation finding was
withdrawn because the unchanged experiments are already approved and R is below
180 s. Final paired target qualification remains S6-owned. Continue to S2.

**What it delivers:** a maintainer can compare complete suite/file runs and see
which real Git operations belong to setup, seed construction and matrix cases.

**Blocked by:** none. **Mode:** AFK.

- Extend the existing profiler inside each worker before tests load; preserve
  subprocess behaviour and failing-test/subtest outcomes.
- Offer opt-in command categories, counts, durations and ordered samples without
  URLs, secrets or machine paths in published output. Separate diagnostic mode
  from uninstrumented wall timing, including startup and all fixture costs.
- Pin current-main baseline and the spec's exact guidance comparator, inventory
  all three guidance files and the expanded 15-file K4.1 set, and record actual
  runner/tool/privilege facts.
- Record the serial reference baseline and residual 13-file/overhead budget,
  alongside standalone file timings and the required matched repetitions.
- Demonstrate diagnostic attribution and failure propagation through the existing
  benchmark CLI seam. Review sanitised output and preserve raw evidence privately.
- If reference runner access is unavailable or the baseline exposes a scope
  problem, report the concrete blocker before dependent optimisation; slow-VM
  timings cannot establish an absolute target pass.

**Verification target:** meaningful profiler CLI checks, real Git diagnostic
smoke, complete baseline evidence and test-ID/count inventory. Production
checkpoint and guidance behaviour remains unchanged.

## S2 — Safe fixture maintenance for faster clones

**What it delivers:** recovery/coordinator transport clones spend less time
packing accumulated loose objects without losing history or recovery checks.

**Blocked by:** S1. **Mode:** AFK.

- Benchmark a loose-object threshold and synchronous repack inside exclusively
  owned, quiescent disposable remotes; count scan and maintenance overhead.
- Preserve transport-mode clones, intended writer races, effective receiving
  maintenance safeguards, and every real publication/reload operation.
- Prove reachable-history/readback equivalence and unchanged deterministic
  push/clone/fetch/ls-remote counts.
- Keep the optimisation only when complete affected-file comparisons improve;
  a rejected experiment records its evidence and leaves the previous code intact.

**Verification target:** existing real-Git integration files, focused ownership/
history regressions where missing, command-count parity and paired file timings.

## S3 — Independent restoration of immutable fixture seeds

**What it delivers:** each sequential test begins from the complete approved
S2/repair seed without rebuilding that history, while other tests remain isolated.

**Blocked by:** S2. **Mode:** AFK; the seed experiment already has scope approval.

- Build once per class per worker at a unique reserved working path, preserve a
  quiescent immutable template, and restore independent trees to that same path.
- Preserve approval URLs/digests, checkpoint bytes/history and setup assertions;
  reconstruct in-memory stores and counters. No hard links, alternates, shared
  mutable objects or approval rewriting.
- Prove template immutability, worker isolation, mutation/deletion recovery,
  order independence and individually selected-test execution.
- Preserve every matrix case's real publication/clone/reload checks and existing
  within-test reset/concurrency scenarios. Account numerically for each command
  reduction as removed repeated seed construction.
- Include construction and restoration cost in file timings; reject and retain
  fresh setup if isolation or performance acceptance fails.

**Verification target:** full affected recovery/coordinator integration coverage,
isolation regressions, attributed count deltas and matched complete-file timings.

## S4 — Operation-local checkpoint validation reuse

**What it delivers:** a checkpoint transition avoids redundant validation/copying
of an unchanged admitted value while rejecting the same unsafe writes.

**Blocked by:** S3. **Mode:** AFK.

- Reuse only owned, already-admitted values inside a single transition;
  revalidate after mutation/projection and preserve input/return isolation.
- Preserve fresh external-state checks, effective target multiplicity, exact-ref
  CAS, push lease, unique write identity, lineage and ambiguous-push recovery.
- Do not introduce global caches, fewer durable writes or a new Git protocol.

**Verification target:** existing public persistence/recovery seams plus any
missing changed-boundary regressions; corruption, mutation, stale writer, remote
target and reconciliation checks; unchanged deterministic Git boundary counts
and measured affected-file benefit.

## S5 — Guidance performance with fresh admission

**What it delivers:** guidance/configuration operations avoid repeated encoding,
Unicode scanning and validation while each new operation observes current input.

**Blocked by:** S1. **Mode:** AFK.

- Reuse unchanged canonical bytes/revisions only within one operation; preserve
  byte format, hash identity and mutable-input isolation.
- Preserve invisible-character deletion before NFKC, whitespace normalisation
  and boundary/supplementary-code-point behaviour when optimising lookup.
- Keep reviewed guidance, inventory, withdrawn confirmations and retained
  proposal admission fresh across read/reply/apply boundaries.
- Run the complete three-file guidance group against the pinned comparator;
  retain every test and report the 0.80 median-ratio acceptance explicitly.

**Verification target:** public configuration/guidance seams, Unicode equivalence
and changed-authority regressions, full guidance-group paired timings.

## S6 — Final qualification and gap review

**What it delivers:** a maintainer receives auditable evidence for every safety
and performance requirement on the same final candidate.

**Blocked by:** S2, S3, S4, S5. **Mode:** AFK.

- Run the spec's repeated standalone/serial/guidance measurements and three
  delivery CI observations on the final candidate and specified runner class.
- Pass the final full Python 3.12 verifier, both required CI jobs, public-content
  and generated-file checks; retain all matrix dimensions and assertions.
- Update the edition changelog with a Why line and regenerate affected files.
- Obtain fresh independent cross-slice review, including a spec-to-evidence gap
  pass. Resolve valid findings and verify the changed candidate again as needed.
- Report each target as met, unmet or blocked with raw-evidence locators. Missing
  targets keep the feature open; no silent scope or threshold changes.

**Verification target:** the complete spec acceptance table and final-candidate
receipts. The default endpoint is a reviewed build handback, not merge/release.

## Build route and stop rules

Approved Build: GPT-6.1 Sol / Codex / medium reasoning / standard pace, using the
edition default confirmed by the configuration resolver and live host catalog.
Launch in a new Conductor tab in this workspace; preserve the current branch and
existing planning edits. No project model settings change.

Every completed slice needs fresh independent review and an atomic commit after
setting author and committer to GitHub noreply identities. Use the existing
stage-owned red/green workflow; missing upstream skills must be reported, never
claimed as invoked. Preserve source notices and privacy rules.

The user selected build all: run the six AFK slices sequentially with per-slice review.
No hard time/cost ceiling is newly imposed. Report progress at 30-minute
checkpoints and on material findings; reserve time for verification. Stop for
scope/human decisions, Stop, actual quotas, three identical failures or three
no-progress iterations; carry those counts across repairs/handoffs. Reference
runner access and feasibility are explicit S1 gates, not waivable timing claims.

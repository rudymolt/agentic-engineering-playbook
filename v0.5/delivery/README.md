# V0.5 process-attested delivery runtime

This manifest-owned runtime carries the accepted Tier A, Cloud, and K4.1
interfaces into the standalone edition. Ordinary Tier A cannot merge or
deploy; only an explicitly admitted K4.1 fresh agent may merge, and no lane may
deploy. Historical Pilot A schema names remain stable for evidence replay.

Install it into a V0.5 project before stages 04–06 freeze the feature's
observation contract and approved V2 envelope:

```bash
python3 v0.5/delivery/scripts/lifecycle.py install --project /path/to/project
```

The installed `/ai-playbook-deliver` entrypoint is manifest-owned and
digest-bound. Lifecycle commands are `install`, `verify`, `upgrade`, `uninstall`, and
`migrate`; migration removes the pack only after a matching V0.5 semantic-parity
receipt. The runtime emits machine-readable JSON and fails closed on stale
authority, unknown contracts, dirty checker evidence, CAS loss, ambiguous
operations, ceilings, or unresolved findings.

Fresh checkers use Launcher V2 on execution providers that need no additional
macOS service allowance. Its qualifying execution policy disables Python
bytecode through both `PYTHONDONTWRITEBYTECODE=1` and `-B`, routes repository
temp/cache output outside the checkout, forbids repository writes, and monitors
transient mutations. The installed `checker-python.py` wrapper supplies the
Python controls, while `canonical-digest` removes the need for direct runtime
imports during evidence checks.

macOS checkers that exercise filesystem watching use Launcher V3. V3 preserves
the four V2 controls, requires the exact `com.apple.FSEvents` Mach-service
allowlist, and binds the complete effective Seatbelt-profile digest. The
manifest-owned `checker-launcher-v3.py` verifies that digest before applying
the profile through `/usr/bin/sandbox-exec`; public and specialized validation
must agree on the realized receipt. Launcher V2 remains immutable for
historical evidence.

Cloud Conductor checkers use Launcher V4 when the host's documented automatic
checkpoints write private Git metadata. V4 permits only the exact turn-bound
start/end refs under `refs/conductor-checkpoints/`, their commits authored by
`Checkpointer <checkpointer@noreply>`, and their exclusive objects. The receipt
binds the common session and turn ID, refs, commits, candidate-equal trees, timestamps, and metadata
inventory. HEAD, candidate tree, index, staged diff, worktree, untracked
inventory, and every non-checkpoint ref must remain identical. V4 does not
permit feature, candidate, branch, control-ref, or arbitrary object writes;
V2/V3 remain immutable for historical evidence.

The Launcher V4 Linux monitor combines recursive inotify mutation detection
with kernel-origin fanotify PID attribution for Git-directory opens. Every Git
lock mutation binds the exact kernel-reported writer PID, a monitor-owned or
external classification, and redacted process-identity digests; raw command
lines are never retained. Missing attribution, fanotify unavailability or
overflow, stale attribution reuse, and either monitor interruption fail closed.
`monitor_backend` remains `linux-inotify`; the independent
`git_writer_attribution_backend` is `linux-fanotify-pid`.

Every qualifying Launcher V4 run also carries a
`checker-session-lifecycle/v1` companion record. It binds the exact launch,
session, candidate tree, command-manifest digest and locator, completed-command
count and explicit all-required completion, observed exits, joined child
processes, and monitor-stop chronology to the host-owned turn-end checkpoint.
The public adapter no longer treats a bare
`working → idle` status transition as completion: the final transcript item
must be a non-empty agent reply, and the lifecycle validator additionally
requires every command and the transient-write monitor to finish before the
provider ends the turn. Passing artifacts written after turn end cannot qualify
the checker.

V1.26 supplies `skill/scripts/checker-monitor.py` so Cloud checkers no longer invent
shell fingerprint helpers or depend on executable bits or polling-only
coverage. Invoke it only through `skill/scripts/checker-python.py`. On Linux Cloud,
`start` arms recursive inotify coverage before capturing the clean source
baseline, retains periodic complete Git fingerprints as a second control, and
returns only after its first matching probe. `stop` waits for both a terminal
outcome and process exit. A sub-interval create/remove cycle, event-queue
overflow, persistent mutation, early exit, missing first probe, direct
invocation, reused/inside-repo evidence directory, or nonterminating process
blocks qualification. Host-owned Conductor checkpoint refs/logs and Git objects
remain governed separately by Launcher V4.

Every attempt must have a pre-approval `pilot-observation-contract` declaring
its start event, duration, signals, raw-evidence locators, defect route, and
receipt issuer. Pilot A accepts a visibly labelled
`process-attested:linear:<issue-id>` route or an already-proven protected store;
the canonical Linear record must retain exact JSON, digests, source event, and
stable host/raw-evidence locators. This provenance qualifies only for Tier A.
Tier B/C still require a `protected-store:` issuer. Envelope V2, Approval V2,
and Attempt V3 bind its digest and enforce declaration → approval →
registration ordering. Preflight blocks before feature writes when the
contract is absent, empty, stale, or
postdated. Observation V4 revalidates contract → registration chronology at
consumption and accepts the window start only from an exact
subject/time/type-matched host event whose digest and evidence locator
are carried by host proof. Nested evidence identifiers are strictly typed.
Use `upgrade` when a project already contains an older manifest-owned pilot
pack; it verifies every previously owned file and preserves unrelated files.

Run the named gates with:

```bash
python3 v0.5/delivery/scripts/verify.py --set A-core-local
python3 v0.5/delivery/scripts/verify.py --set A-cloud
python3 v0.5/delivery/scripts/verify.py --set A-complete
```

## Interim S1 checkpoint surface

The interim coordinator's S1 surface validates and persists an approved record,
but remains checkpoint-only and dispatch-unavailable: it cannot launch workers
or claim protected authority. From a checkout containing the package, use:

```bash
PYTHONPATH=v0.5/delivery/src python3 -m delivery_pilot.interim validate --approval <approval.json>
PYTHONPATH=v0.5/delivery/src python3 -m delivery_pilot.interim preflight --record <record.json> --slice <approved-afk-slice>
PYTHONPATH=v0.5/delivery/src python3 -m delivery_pilot.interim publish --repository <coordinator-checkout> --record <record.json>
PYTHONPATH=v0.5/delivery/src python3 -m delivery_pilot.interim reload --repository <clean-checkout> --record <record.json>
```

Commands emit canonical JSON and return an `interim refusal:` message with exit
2 when a record, repository identity, ref, or checkpoint cannot be trusted.

## Interim S2 controlled fixture

`delivery_pilot.interim_coordinator.InterimFixtureCoordinator` is the public,
deterministic adapter contract for the next bounded seam: pass an S2 task whose
digest, slice, tracker spec revision, routes and command identities are bound by
the immutable approval, a checkpoint snapshot, and fixture adapters to `run_one`.
The adapter supplies a correlated current-coordinator observation before every
dispatch entry and modeled `send`, `reconcile`, and `cancel` observations. The
ledger retains exactly one timestamped launch and conservative charge for each
coordinator/Build/Verify operation; optional host token and cost counters remain
null when unavailable. A timeout or unknown send is `reconcile-required`, then
observed using its same operation/session/message/terminal-turn IDs—never
re-sent under replacement IDs. A PR-ready handback needs task-, operation-,
artifact-, candidate- and criterion-bound command/check evidence plus current
QA/CI evidence for every approved QA/CI command, fresh final review and open PR
observations. Every reloaded launch/receipt must correlate to its retained
operation identity. Ordinary deadline cancellation persists intent and uncertain
status before the host call, including when polling an already queued worker.
If deadline cancellation lacks a matching `cancelled`
observation or the fixture adapter reports a bounded transport error, the
checkpoint records `cancellation-uncertain` and an incomplete handback rather
than claiming cancellation. Portable reload rederives each operation's purpose
identity and revalidates the retained Build/Verify evidence and PR-ready state;
transition and portable validation use the same pure worker-result and handoff
contracts. Accepting worker receipts require bounded artifact/tool/wall-time
evidence, explicit null optional counters and exact command/check records without
duplicate or filtered extras. Verify additionally requires fresh context, no
builder transcript and an accepting verdict. Invalid new or reconciled receipts
leave a durable incomplete handback from the last trustworthy snapshot;
corrupt remote state is refused before a modeled send. It has no Conductor,
GitHub, worker, or merge client. Transport acceptance, terminal turns, and idle
status are not success, and selected caps/deadlines hand back without retries.

## Interim S7 maintained host seam

`InterimFixtureCoordinator.run_frontier` advances ordinary Build/Verify for the
next approved AFK slice whose dependencies have accepted ordinary Build and fresh
Verify evidence, or a completed same-slice S3 repair with accepting repair-Verify,
in this same ledger. Repaired dependency admission also requires a complete
ordinary failing Verify on its accepted Build candidate and exact approved task,
with the repair opening bound to the failed criterion and its command/artifact
evidence. Original failed ordinary receipts remain unchanged. It polls pending operations by their original
IDs and retains one exact task-bound pair per slice. Active state identifies its
current slice; existing single-slice checkpoints remain readable. Child tasks
keep their separately approved exact base. A child candidate from its accepting
ordinary receipt may be observed as pending stack restack; it cannot receive
accepted stack review until durable restack and fresh Verify bind the dependency
base. No caller needs to invent a Build candidate or replace task approval.

`delivery_pilot.interim_conductor_host.ConductorHostAdapter` is the sole
maintained Conductor CLI mapping for separately authorized disposable S7
fixtures. It persists UUIDv5 session/message IDs in the operation intent before
calling `session create` or `message create`, and Conductor's echoed message UUID
is the durable turn ID. The adapter validates the actual create/status/cancel
envelopes and paginates transcript event UUIDs. A `sent` or `queued` message is
only a queued receipt; `working` is active; only a correlated `agent`
`turn.completed` event plus one exact structured worker-result contract can
advance the corresponding worker policy. Idle observations remain pending; an
unstructured terminal repair/stack result is retained as unusable, never success.

## Interim S4b.3 advance and PR finish

For a separately approved, monitored run, the coordinator invokes one command
per wake:

```bash
PYTHONPATH=v0.5/delivery/src python3.12 -m delivery_pilot.interim advance --repository <coordinator-checkout> --record <approved-record.json> --tasks <approved-task-map.json>
```

The task map is keyed by approved slice ID; every complete task is checked
against its immutable approval digest before dispatch. `advance` reloads the
exact control ref. A terminal awaited worker is reconciled by its same logical
ID, then the command performs its next authorized coordinator step before
exiting. That step can admit at most one bounded worker effect or perform the
final GitHub PR readback. A failed worker instead reaches effect reconciliation
and a repair or decision boundary without treating its wake as replacement
authority. It prints only a fixed outcome and control
commit. Durable non-worker transitions record the next wake and emit a best-effort
locator hint; the backup remains authoritative if hint delivery fails.

New monitored approvals that may finish at a PR include
`repository.base_ref: refs/heads/<branch>`. Existing approvals without this
field remain readable but cannot claim the S4b.3 final PR finish. The Verify
worker uses `delivery_pilot.interim_pr` with its durable operation ID to read
an existing exact PR or reserve one create intent before the GitHub POST. An
uncertain create response is resolved by readback; the marker forbids another
POST. The worker brief binds the absolute approved candidate checkout and
implementation paths for source work. Its coordinator checkout is used for
the control ref and worker-done hint.
Worker send admission is a checkpoint CAS after checkout binding and a fresh
Stop/limit read. PR create admission is a checkpoint CAS after GitHub preflight
and the same fresh authority read. A Stop committed before either CAS refuses
the effect; a Stop committed after it treats the exact effect as in flight and
requires same-ID reconciliation. Checkpoint CAS and a provider request are
separate operations, so the admission record does not prove provider receipt.
The two approved `workspaces` paths are relative to one shared workspace root:
`--repository` must resolve to `<root>/<workspaces.coordinator>`, and the
candidate resolves to `<root>/<workspaces.candidate>`. Host dispatch refuses
when either relationship is wrong or the candidate is not an existing Git
checkout with the same approved remote targets, or when a symbolic link
redirects the candidate path; it never places the candidate
under the coordinator checkout.

After every approved slice has accepted independent Verify evidence, `advance`
reads the claimed PR from GitHub and requires open state, the approved
repository and base branch, and the exact verified head and base commits.
That readback is retained in the checkpoint and validated on clean reload
before monitoring retires as `review-ready`, with `merge: unavailable`.

`interim_host_fixtures.selected_limit_wake_fixture` and
`diagnosis_stagnation_fixture` are executable entry points for a separately
approved live cap/deadline and repair-stagnation fixture. They do not create a
Routine or workspace by themselves. Its approval must use
`approved_fixture_envelope`: every Routine webhook delivery counts as one host
workspace, in addition to the fixture's main workspace and named-session cap.
The result parser remains intentionally strict: a host transcript that does not
carry the complete approved worker-result contract cannot receive AC25–27 host
credit.

S3 adds a deterministic repair policy over the same checkpoint, with an injected
adapter for either isolated tests or separately authorized host execution. A
blocking finding must be concrete, reversible, in scope, capability-available and
bound to an approved criterion and execution evidence. Diagnosis receives only
criteria, revisions, evidence and prior hypotheses; it records a cause or
eliminated hypothesis plus a changed experiment. Repair intent and fresh-Verify
intent are independently charged durable operations. Initial Build/Verify does not
consume a repair cycle; a terminal incomplete repair does, without inventing a
Verify result. Queued transport and ambiguous sends do not spend a repair cycle.
Only independently checked before/after evidence may count as progress, and a
repeated evidence artifact cannot be credited twice. The first two no-progress
cycles remain eligible under their diagnosis; the third becomes `stuck`.
Correlated observations that fail validation remain `result-unusable` with their
raw receipt, charge, and typed error rather than returning to intent. Forecast
revisions are evidence-bound, retain capacity for remaining repair, Verify, and
handback work, and retain cumulative usage/failure history. This remains an
interim policy with cooperative adapters and no protected authority.

An explicit `escalation_policy` in the immutable run approval enables the
Plan-selected fallback. The playbook default is GPT-6 Astra/high after three
cumulative unsuccessful ordinary repairs, with two diagnosis-and-implementation
slots per approved slice. Legacy approvals have no escalation authority.
Each slot is reserved with its exact operation and charge before the worker
message; a fresh hypothesis, prerequisite, worker error or restart cannot add
a free slot. The Astra worker diagnoses and may implement within that same
slot. Its host adapter provisions an idle exact-ID session without a message,
then checks host `model`, `resolvedModel`, `effort`, workspace, status and empty
message inventory before final admission. An ambiguous create/readback stays
on the same ID and AC21 observation cadence; a confirmed mismatch yields a
stuck report. Conductor's public session metadata attests the selected host
route and fresh idle context, while the terminal worker result separately
attests executed tools and runtime. The public session schema does not expose
provider execution metadata or agent identity for independent pre-send proof.

New approvals bind escalated-candidate Verify in immutable `routes.escalated_verify`
as `{"model":"gpt-6.1-sol","effort":"high","fallback":null}`. This explicit
entry is the new seed policy, not an operation-provided override. Existing
approvals without it retain the exact historical GPT-6 Sol/high policy for
validation, resume, host dispatch and worker briefs; never add the entry to
an already approved record or relabel its operations. Arbitrary weaker routes
are rejected, and the approval digest binds the explicit new policy.

Every new escalated candidate receives a fresh GPT-6.1 Sol/high Verify of the exact
SHA under that approval. Its brief carries the bounded task, candidate and artifact locator, not
the Astra reasoning transcript. A failing verdict retains progress and closes
the slot. An unusable Verify remains unaccepted until its exact worker is
reconciled; at most three fresh Verify attempts for that SHA are charged,
without spending another implementation slot. After a slice passes, the next
slice returns to the originally approved Build route. Host counters that are
not available remain explicit nulls; retained operations provide observable
dispatch and elapsed-time evidence. Human interruptions remain in the run's
durable recovery stop and decision-notice records; neither an absent notice nor
an unavailable host metric is converted into a zero-use claim.

Every S3 diagnosis, repair, and fresh repair-Verify rechecks an explicitly
selected deadline/dispatch admission immediately before its send. Repair
and Verify use the same approved runtime, candidate/base, bounded evidence, null
counter, and fresh transcript-free Verify contract as S2. A failing Verify retains
the complete approved `pass`/`fail` criterion map, including passing criteria,
but must contain at least one failure. The diagnosis and repair coordinator methods resume the
explicit `waiting-diagnosis`, `waiting-repair`, and `waiting-repair-verify` phases
by polling the exact stored UUIDs. A successful repair first publishes
`repair-verify-ready`; only then may fresh Verify be admitted. Terminal receipt
and diagnosis/cycle projection are one checkpoint transaction, so reload cannot
strand a result between transport and policy. The fixture driver returns at a
queued boundary; invoke it again on the next observed host turn. It never spins,
resends a recorded intent, or resets limits/counters. A selected deadline records
cancellation intent before cancelling a pending worker and retains the correlated
outcome; ambiguous cancellation requires recovery, never a replacement worker. S3 forecasts separately name
work, verification, likely repair, and final-handback units; an evidence-bound
revision is recorded when retained result consumption exceeds the active estimate.

## Interim S5 stacked-review fixture

`delivery_pilot.interim_stack.InterimStackCoordinator` adds a deterministic
stack seam to the same exact-ref checkpoint. It selects only the
first approved AFK slice whose dependencies have current accepted review evidence;
accepted is distinct from externally observed merge and shipment. Per-slice records
retain exact candidate/base, PR observation, review binding and retained findings.
Stack changes are intent-before-effect operations with durable correlated receipts;
reload/reconcile uses the existing S4 checkpoint store and never writes an observed
merged branch. A candidate/base/restack change clears the affected review, requiring
fresh Verify before acceptance. Stack Verify uses the complete approved S2 task,
including its deterministic operation identity and terminal result contract. Final
QA, CI, and independent review are not caller status fields: they reference existing
accounted terminal `usage.operations` receipts, whose artifacts and approved commands
bind them to the current full stack. Blockers produce an S3 repair-policy handback,
and only complete current evidence produces `review-ready` (never `shipped`). The
stack-effect adapter exposes no merge operation. `verify_slice` and
`final_review` are the maintained worker dispatch entry points: inject the
approved `ConductorHostAdapter` to reserve, send once, poll, validate and project
Stack Verify, final QA, final CI and final independent review through
`approval.routes.verify`. Each launch has its own durable charge and UUIDs.
Stack Verify identities bind candidate/base and verification environment; final
identities additionally bind accepted input reviews. Old pending work settles
before a new revision is dispatched, and stale results never accept the new
candidate. Final worker results retain bounded runtime/tool/wall-time evidence.
Existing fixture receipts remain readable; new final intents carry frozen input
bindings that validate independently of later candidate changes. These methods
perform no PR mutation and confer no live-run or merge authority.

S4 adds deterministic clean-checkout recovery over that same remote checkpoint.
It observes the exact recorded worker/session/message identities and records an
idempotent wake; an active, queued, ambiguous, corrupt, changed-scope, or
second-coordinator observation handbacks rather than creating a replacement
writer. Whole-run stop first records intent, then removes and reads back the
approved coordinator opt-in prefix, requests cancellation for known active work,
and records queued/uncertain outcomes. This is cooperative cancellation, not
protected revocation or guaranteed cessation. Resume requires an explicit human
instruction, reconciled old workers, selected-cap compliance, and publication of
the resumed checkpoint; it retains prior usage, forecasts, and repair history.
An explicit retry of an unresolved whole-run stop retains its original intent,
confirmed prefix removal, and successful cancellations; it reconciles only the
remaining uncertainty. Automatic wakes cannot retry an uncertain stop. Failed
resume attempts keep the confirmed stopped state and record the failed boundary.

Event and backup recovery require separate host-specific qualification before
activation. They are off by default in the public package.

K3 requires each opted-in project to own a checked-in
`.playbook/cloud-readiness.yml`, a shared local/Cloud setup wrapper, explicit
non-secret build/setup epochs, digest-bound service/data/browser/recovery
commands, and an isolated Cloud evidence directory. Validate and execute it
through the installed public boundary:

```bash
python3 scripts/deliver.py cloud-profile-validate \
  --project "$PWD" --profile .playbook/cloud-readiness.yml \
  --expected-digest sha256:...
python3 scripts/deliver.py cloud-readiness-run \
  --project "$PWD" --profile .playbook/cloud-readiness.yml \
  --facts .context/cloud-readiness-facts.json \
  --evidence-dir .context/cloud-readiness-evidence
```

The runner owns CR1–CR10, performs setup twice, reports environment names only,
and retains redacted evidence in a fresh, non-reusable directory owned by the
validated readiness ID. CR10 requires the exact current-run inventory to contain
only the recorded regular files: missing, extra, nested, symlinked, special-file,
or pre-existing current-run evidence fails closed, while preserved sibling runs
remain untouched. The receipt fingerprints every current-run evidence file so
later replay can detect retained-byte drift. CR9 browser artifacts are scoped by
journey index, so multi-journey profiles retain every journey's complete evidence
without overwrites or locator collisions. It issues a 30-day admission receipt only when all conditions
pass. Candidate readiness always reruns CR5–CR9 and unions the
frozen invalidation matrix. The API adapter prefers `CONDUCTOR_API_KEY` over
`CONDUCTOR_API_TOKEN`, preflights `/me` plus the versioned OpenAPI digest,
reconciles ambiguous sends by stable `messageId`, and never treats initial
`idle`, API `error`, or an archived sleep response as success.

Passing the pack's deterministic `[A-cloud]` suite proves the reusable K3
implementation. A project is not Cloud-admitted until its own fresh Cloud
workspace passes CR1–CR10 and retains its project-specific receipt. That
project receipt is capability evidence only; it grants no K4 feature-delivery
authority.

## K4.1 bridge

The pack includes a disabled-by-default, process-attested fresh-agent merge
bridge. It adds a distinct authority class rather than widening Tier A:

- builders and coordinators remain capped at `open-pr`;
- the pre-write envelope approves the exact risk class, feature planning
  prefix, and non-planning implementation paths while explicitly deferring PR
  and candidate identity;
- the gate, handback, launcher, remote control state, and decision bind the
  actual PR and complete frozen candidate after they exist;
- one clean-context merge agent is bound to its launcher and independently verifies the exact PR;
- fresh-agent verification is the mandatory evidence floor; host checks are an
  additional veto only when present, so an empty rollup requires no synthetic
  status, every reported check must be `SUCCESS`, and host mergeability must
  separately remain `MERGEABLE` and `CLEAN`;
- host-observed default-branch policy classifies protected paths;
- `merge-decision/v1` is persisted and read back exactly from a durable host
  before expected-head dispatch;
- failed or ambiguous dispatches cannot claim a successful agent merge; and
- `process-attested-merge/v1` records the host outcome.

The installed CLI exposes the two explicit boundaries:

```bash
python3 scripts/deliver.py k41-decide \
  --envelope <envelope> --approval <approval> --attempt <attempt> \
  --gate <gate> --handback <handback> --launcher <launcher> \
  --policy references/k41-policy.json --standing-authority <authority> \
  --facts <fresh-observed-facts> --issued-at <host-timestamp>

python3 scripts/deliver.py k41-persist-decision \
  --decision <allow-or-deny-decision> \
  --attestation-output <new-attestation-path>

python3 scripts/deliver.py k41-merge \
  --decision <persisted-allow-decision> \
  --decision-attestation <durable-readback-attestation> \
  --standing-authority <authority>
```

`k41-persist-decision` posts the canonical decision body as an exact GitHub PR
comment, reads it back byte-for-byte, and creates `merge-decision-attestation/v1`.
Every decision is retained; a denial stops after persistence and can never be
passed to `k41-merge`.
The decision embeds the envelope's `approved_scope`; the complete observed PR
may contain files under only the exact feature planning prefix plus the exact
approved implementation paths. Any drift denies before dispatch.
Its decision and readback digests must both equal the canonical decision digest,
and its session must be the fresh session named by the decision. `k41-merge`
rejects a missing or mismatched attestation before any host call. It then
re-reads the GitHub PR, changed paths, review threads, and remote
Mission Control ref, checks current host
status, atomically claims the full decision digest under
`refs/heads/delivery-operations/`, then calls GitHub's merge endpoint with the
exact expected head SHA. An existing operation ref forbids redispatch.
Its receipt must be retained durably before any subsequent workflow step.

K4.1 accepts only a Tier A attempt. It is not non-bypass protection and cannot claim Tier B/C, deploy, or release
authority. Installation alone does not activate it; project admission and an
exact standing-authority receipt at its default-branch `authority_path` are
still required.

The first sample application K2 attempt remains a nonqualifying denominator entry because
V1.7 lacked this gate. K2 resumes only with a new feature and the corrected
contract registered before dispatch. K5/Tier B remains blocked until the
protected host route in the K0 inventory is proven; a Linear-backed Tier A
attestation does not weaken or satisfy that gate.

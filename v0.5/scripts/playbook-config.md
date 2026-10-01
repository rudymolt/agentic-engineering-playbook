# Project and personal configuration boundary

`playbook_config.Configuration` owns read, typed edit, explain, validation and
Apply. `configure-playbook.py` is its JSON helper for chat skills and the
existing model-router, not an interactive terminal product or launcher.
Python 3.10+ and the standard library suffice.

## Shareable source

The sole adopted default source is project-root `.playbook-config.json`.
Schema 1 contains exactly `schema_version: 1`, `adopted: true` and `models`.
Models contains planning, implementation, verification and escalated_repair.
Each role retains model_id, runner, reasoning and supported scalar metadata.
Repair also retains trigger_unsuccessful_repairs, cycles_per_slice, scope and
authority. These constraints are imported unchanged, never editable preferences.

Adoption imports every existing role, including custom runner/reasoning.
Missing roles use edition seeds with per-role origins. Invalid/ambiguous input,
duplicate keys and newer schemas block without fallback or input rewrites.
S2 changes any of the four role identities; non-identity constraints remain intact.
Legacy routing's inline/block mappings and scalar/list values are supported;
advanced YAML anchors/tags/multiline values require explicit reconciliation
before adoption rather than lossy parsing.

Precedence for new choices: explicit approved feature choice (including
feature-scoped `openai defaults`) > adopted project > legacy project > edition.
QA uses verification. Active/retried routes and approved mission routes are
records, not defaults, and never re-resolve mid-run. Malformed adoption is an
error. Bootstrap/upgrade install the skill through the existing registry and
managed-file merge. Configuration is project-owned, not a managed template;
upgrade never implicitly adopts or rewrites it.

## Helper contract

Run `python3 {playbook-path}/v0.5/scripts/configure-playbook.py --project
{project-path} --discovery-command '["availability-adapter"]' read` with empty stdin or
`{}`. It returns the structured proposal. Keep proposals local to the
conversation or a gitignored handoff, never in shareable settings.

For `reply`, stdin is `{"proposal": <previous result>, "reply": "Edit Build"}`,
then a numbered route, then `Apply` or `Not now`. The helper invokes the adapter
for discovery and twice at Apply, retaining the reviewed proposal. Changed revisions invalidate it.
An unchanged route/source revision with a newer successful check date remains
valid; refreshing the timestamp alone does not force an endless re-preview.
Typed labels are case-insensitive; route choices are numbered from 1.
Results include before/after, per-role origins, destination, migration,
input digests, discovery revision, proposal_revision, state and typed choices.
Chat renders these; it does not reconstruct migration/save logic.

`Edit` offers numbered Plan, Build, Verify and Repair roles; `Edit <role>`
opens that role directly. Choose a complete numbered route or `Pick model`,
then a numbered model, supported runner and supported reasoning. If multiple
identities remain, select the complete identity explicitly. All editor levels
have typed choices and `Back` / `Not now`; native controls are optional mirrors.
Edits and explanations preserve other draft values. Invalid replies retain
the valid draft under `retained_proposal`; `Back`, `Edit` and `Edit <role>`
reuse it without losing unrelated edits, while explicit
Reload discards unsaved edits. `Explain <role>` reports the selected route,
discovery authority/date and unavailable task-fit/cost evidence without invoking
anything. `qa` always inherits verification; Coordinator has no edit path.
An optional `coordinator` identity in the request-bound discovery response
reports the current chat with that observation's authority/date, never a
catalogue default or launch proof. Without it, Coordinator is explicitly unknown.

The proposal is a complete model-role proposal with origins and reasons for
retaining starting choices, not the S6 Recommended setup. Skill-job configuration
arrives in S3; presets and billing persistence arrive in S5. Do not imply those
later acceptance criteria are complete. Availability is not suitability,
comparative cost or future launch proof. Existing lane gates still require
fresh identity, independence and approval checks before execution.

## Personal defaults, presets and first setup

Supply `--preferences-dir {user-local-directory}` on read and every reply.
The directory must be outside the project; there is no implicit path or host
setting change. The private destination is `preferences.json` in that directory,
containing schema_version 1 and presentation `guided` or `expert`, with optional
`billing`, `defaults` and `presets`. Existing presentation-only records remain
valid. Billing is `api`, `subscription`, `mixed` or `unknown`; consumption and
allowance remain unknown without observable evidence, and API token prices are
not the subscription bill. Defaults and each named preset use the exact adopted
project model/skill representation, not another binding schema. Unknown fields,
duplicate keys and unsupported versions block without dropping saved data.
Personal data never implicitly overlays an existing project. Read takes optional `context` containing
only known `goal` and `billing` (`api`, `subscription`, `mixed` or `unknown`).
Goal stays in the private conversation; an explicitly approved local save can
persist billing, never in shareable project configuration.
The helper returns only missing questions. Typed `Goal <context>`, `Billing
<mode>`, `Guided` and `Expert` answer them. Reopening with known context and
saved presentation/billing skips known onboarding questions. Omit context for the ordinary
preference reader; Configure supplies existing context rather than reasking it.

`Guided` / `Expert` produces a personal before/after preview and exact local
destination, including `resolved_destination` behind any directory aliases.
The preview records both personal and project directory identities (resolved
paths and device/inode identities, or the nearest existing ancestor for a new
directory). Apply rejects changed identities even when file bytes match.
An explicit new preview can refresh a reconciled directory identity while
retaining role drafts; it displays the changed destination before another Apply.
`Apply preference` is an explicit **local-only** transaction,
then returns to the complete unsaved project draft. Project `Apply` also supports
an explicitly previewed personal change through the paired protocol below.
Presentation alters rendering only,
not choices, validation or project settings. `Not now` cancels pending changes;
an earlier explicitly saved presentation remains saved. With no personal
destination, the default rendering is guided and changing presentation blocks
instead of writing somewhere implicitly.

Local saves reuse the accepted project save protocol below: staged validation,
request-bound discovery recheck, no-clobber publication, retained evidence,
content-digest completion and non-destructive recovery. Their lock, recovery
journal and `.playbook-config-*` evidence live beside the local destination,
never in shared configuration. Invalid or newer personal schemas block rather
than dropping unknown fields. Reconciliation remains human-owned.

### Reuse without execution authority

`Presets` offers one `Recommended` entry plus user-saved names. Recommended
currently retains the starting configuration; evidence-backed advice is a
separate step, not static cheap/balanced/premium bundles or an assertion that
availability establishes suitability. `Recommended` restores the starting
project draft without saving or discarding pending personal changes.

`Load defaults` or `Load preset <name>` edits only the current draft and shows
model and skill origins, before/after changes and destinations. Named presets
are case-sensitive; names are 1–64 portable letters, digits, spaces, underscores
or hyphens, and Recommended is reserved. Models and skill sources must still
pass current discovery/eligibility at Apply. A custom binding in a preset is
data, never proof of local qualification. Unresolved identities require
restoring the local resolution and retained audit or explicitly editing a
fallback. Project-specific repair constraints remain protected.

`Save defaults` or `Save preset <name>` previews a personal-only write.
`Apply preference` saves that reusable data without touching any project or
active execution; `Apply` explicitly approves the displayed project and personal
changes together. `Billing <mode>` previews local billing, and presentation
edits retain saved defaults, presets and billing. Saving personal defaults never
rewrites an existing project. `Not now` cancels pending writes only; earlier
explicit local saves remain saved.

### Paired recovery

A combined Apply retains a transaction ID and separate `.playbook-config.pair`
journals beside each destination, plus previous and attempted byte evidence in
each destination's own directory. Billing and personal bytes never enter the
project journal. Both writes reuse the staged, validated, no-clobber save
protocol. Success requires validation of both destinations, runtime digests,
retained evidence, directory identities and paired journals, followed by durable
paired completion. The result includes a transaction ID, protocol and validated
destinations in `paired_completion`; it is not two independent Apply replies
treated as success.

Incomplete pairs block project and personal reads/writes, including a different
project using the same personal store. On failure, only a destination still
matching this transaction's attempted bytes can be restored. A racing writer is
captured intact and restored by no-clobber linking when possible, never overwritten;
any other concurrent bytes and retained capture remain available for recovery.
Even exact restoration returns `recovery_required`, not partial success.
After completion-boundary conflict, retain attempted evidence, concurrent bytes
and journals rather than undoing a completed write. Human recovery inspects both
journals, previous/attempted/captured bytes and runtime state; it reconciles the
intended result before removing transaction evidence. Do not delete journals
merely to make a pending pair readable. Results expose a failure category, not
unreviewed exception text or binding-store paths. The reviewed personal
destination remains available in the local proposal/recovery flow.

### Bootstrap preview seeding

New projects can use the existing `bootstrap-project.py` read-only plan with
`--preferences-dir`, the same `--discovery-command` adapter as Configure, and
optionally `--preset <name>`. Omission of the preset selects saved defaults;
no saved defaults means ordinary bootstrap without adoption. The plan shows
creation of `.playbook-config.json`, its complete configuration, origins and a
`seed_revision`. Seeded `--apply` requires that exact `--seed-revision` along
with the same options. Changed personal inputs, discovery, eligibility or
destinations require another preview before any bootstrap write. Missing local
dependencies block, rather than silently dropping skill bindings.

Bootstrap retains its existing managed-file preview, approval, preservation and
status flow. Seeding creates configuration only after bootstrap completes
without manual reviews; partial bootstrap or seed failure is reported honestly.
It never replaces existing state/configuration. Existing projects use Configure
and explicit Load/Apply instead. Subsequent ordinary bootstrap checks omit the
seeding flags. Configure does not invoke bootstrap or launch a model/stage.

Personal saves open and verify the reviewed directory, create missing children
relative to that descriptor, and keep all transaction writes, cleanup and
directory sync relative to the opened directory. Alias changes cannot redirect
those operations. Guards recheck both directory identities across save
checkpoints. A detected change before capture cleans the attempt; after capture
or publication it retains recovery evidence at the reviewed resolved location.
A change after the content completion point can leave a completed personal
save there while the reply blocks on the changed destination; inspect that
location before retrying. The service never silently follows a new target.

This is not a filesystem lock against external directory relocation. Another
process with permission to rename the opened directory or its ancestors can
move its existing contents and subsequent descriptor-relative writes under a
project. Repointing the project root can also reclassify existing personal
files. Identity checks detect observed changes but cannot make ancestry tests
atomic with writes or prevent changes after observation. Keep these directories
stationary during Apply; an absolute guarantee against such relocation requires
filesystem permission isolation or coordination with every directory mover.
Unsupported descriptor-relative storage operations block the save.

Both save directions recheck the paired store's locks, recovery journals and
unfinished/conflicting receipts during staging, after discovery, before capture
and publication, after publication, and before and after the final content-digest
comparisons. The check following those comparisons vetoes success when paired
recovery is already pending at the content completion point, including recovery
arising during the comparisons. Only the active store's own transaction
artifacts are exempt from these paired checks; its existing capture, journal
and receipt protocol still applies.
Recovery detected before publication prevents publication. If capture already
occurred, an absent destination can be restored by an exclusive hard link while
retaining recovery evidence. Recovery detected after publication never reports
success or destructively restores old bytes: current and attempted bytes remain
for reconciliation. Blocked replies retain the sealed role draft; once both
stores are reconciled, Back/Edit can resume the same reviewed proposal.

When runtime state is absent, `bootstrap.required` routes the model proposal to
the existing bootstrap preview/approval gate. Project Apply blocks; no runtime
file, second bootstrap or unspecified setting is created. Reopen and review
after the approved bootstrap. Personal default seeding is S5, not this slice.

For ordinary model-router preference resolution, use `resolve` without
`--discovery`, passing `{"role":"implementation"}` or the appropriate role.
Supply `feature_choice` only for an explicitly approved feature route,
normalized to model_id/runner/reasoning. It returns choice and origin.
Command-level integration tests exercise this next-lane reader. Live
availability, allowed runners, permission strength, authoritative identity,
fresh-context independence and action gates remain model-router's job.

Discovery is a bounded set of **verified available** routes from the existing
host admission/discovery surface, not Configure or a cached full catalogue.
Each route lists only admitted roles and identity fields. Example fixture,
not production host proof:

```json
{
  "request_id": "echo-the-current-request-id",
  "revision": "fixture-1",
  "checked_at": "2026-09-29T12:00:00Z",
  "authority": "host-reported-selection",
  "routes": [
    {"model_id": "fixture-model", "runner": "codex", "reasoning": "medium", "roles": ["implementation"]}
  ]
}
```

Authority is host-reported-selection, provider-response-metadata or
session-thread-metadata from an actual authority surface. The helper validates
the envelope, not host credentials/model-picker provenance; the skill must
supply genuine evidence. `Configuration.discover(request)` and the helper's
adapter receive a new `request_id`, `started_at`, all four `roles` and
`purpose: current-availability`. The command receives this object on stdin
and returns the response on stdout. For each invocation, it must genuinely
recheck admitted role + model + runner + reasoning at the existing authority
surface, echo that request ID and record the observation's `checked_at`.
The helper requires that observation to fall between its request and response
clock readings. Echoing a nonce or redating cached bytes without observing
access violates the adapter contract. Static `--discovery` files are rejected;
use an explicit adapter even in clock-controlled tests. No age-based availability
policy is defined. The future S7 24-hour guidance/pricing cache is separate
from availability and launch identity. Execution still requires independent
live admission. `--now` is a fixture clock only. No suitability/cost claims
are invented; S6 owns recommendations.

Exit 0: decision required, proposal ready, applied, unchanged or resolved.
Exit 2: blocked/recovery required or invalid request; report the message and
reload/edit as directed. Argument syntax errors also exit 2.
No environment, credentials or host changes are needed.

## Transaction and recovery

Apply binds all before/after defaults, runtime/settings digests and discovery.
It locks `.playbook-config.lock`, stages and validates complete JSON, checks
inputs and current availability, then durably journals intent before mutation.
For an existing file it atomically captures the destination inode into a
reserved local backup and compares the captured bytes with the reviewed digest.
The journal also retains a separate copy of the reviewed previous bytes, so a
conflict cannot overwrite that snapshot or mislabel it as the captured version.
Publication is an exclusive hard link, never replacement of the destination:
an arbitrary editor creating a file during the capture/publication gap wins.
Initially absent destinations also use exclusive publication. Readers reject
the lock or recovery marker, including the capture/publication gap. Runtime
and approvals are never transaction destinations.

After capture or publication, an error requires reconciliation rather than a
destructive automatic rollback. A captured conflicting file can be restored
only by an exclusive hard link when the destination is absent; another file
is never replaced or unlinked based on an earlier equality observation. Both
current files and captured/attempted bytes remain intact. Successful saves
retain the captured inode and a local `.playbook-config-*.receipt`: a writer
with an already-open descriptor cannot lose later writes to an unlinked inode.
Receipts record the previous, attempted and runtime digests; retained inodes
are evidence, not another preference source. Attempted bytes are a separate
snapshot, not the hard-linked publication inode: in-place external writes
cannot rewrite the reviewed candidate evidence. The publication inode is also
retained, including for writers holding its open descriptor.

Journal promotion is **not completion**. After publication and all durability
steps, one final check compares current destination, captured previous config,
tracked runtime and retained evidence bytes against their recorded digests;
all matches establish the content completion point. With a paired store, its
recovery guard must also pass after these comparisons before the receipt can be
sealed. This guard does not recheck content or change the content completion
point. It can conservatively detect paired recovery arising after that point;
it cannot guarantee against unrelated writes after its observations. Only
non-content bookkeeping then follows: marking the protocol-3 receipt complete
and removing the lock, so later content or metadata edits cannot retroactively
turn that save into a conflict.
Digest mismatches or durability failures retain a `.receipt.conflict` marker
as well as the recovery journal and lock, without deleting concurrent bytes.

All preference readers reconcile receipts before and after their configuration
read, including when the transaction lock/recovery journal is absent. A
protocol-3 receipt without its completion marker, or any receipt with a conflict
marker, blocks every role with an actionable recovery error. Completed
protocol-3 receipts are not re-dated or rechecked against later content edits.
Older receipt formats still load when their recorded digests match; detectable
content mismatches and unfinished protocol-2 receipts require reconciliation,
without using timestamps. Receipt and completion evidence must remain untouched
until reconciliation. This protocol requires same-directory rename, hard links
and durable directory sync; unsupported operations block, not waive recovery.

Incomplete transactions retain `.playbook-config.recovery`, local attempted
bytes, a local
`.playbook-config-*` backup (previous bytes, or explicit absence), and the
lock. A crash can also leave the lock/backup. Reconcile manually: inspect
current settings and recorded digests, agree which complete version to keep,
restore/validate it without overwriting a concurrent choice, then remove only
reconciled artifacts, including the affected receipt, completion/conflict
directories and retained evidence once its open writers have been reconciled.
Removing the lock/journal alone cannot clear a pending receipt. Never
automatically remove someone else's lock or
report an interrupted transaction as applied. Only adopted configuration is
shareable; transaction artifacts stay local.

## Verification scope

Supported skill choices share this service, revision seal and save/recovery
protocol. See [job contracts and stage entry](skill-bindings.md) for the optional
versioned `skills` field, source-labelled proposal/editor/change rows, typed
`Edit skills <job>` / `Choose <number>` / `Explain skills <job>`, exact-source
eligibility checks and public `job-route` CLI seam. It returns a stage-owned
invocation descriptor, never a launcher. Active/approved execution remains
outside preference writes. Model-only adoptions remain valid and unchanged.

`test_playbook_config.py` and `test_playbook_config_roles.py` use temporary projects, fixture discovery and a clock
at this boundary, including injected storage checkpoints. It proves typed
read/edit/preview/Apply/cancel, migration, next-lane resolution, revision
conflicts, conflict-preserving recovery and runtime preservation. Fixture results are not direct
Codex or Conductor qualification; S8 remains separate. Upstream updates remain
maintenance work, with compatible migrations and retained customisations,
never a per-turn automatic updater.

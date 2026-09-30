# Project configuration boundary — S1

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
authority. These constraints are imported unchanged, not editable in S1.

Adoption imports every existing role, including custom runner/reasoning.
Missing roles use edition seeds with per-role origins. Invalid/ambiguous input,
duplicate keys and newer schemas block without fallback or input rewrites.
S1 changes only Build identity; non-identity constraints remain intact.
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

Journal promotion is **not completion**. Protocol-2 receipts remain pending
until completion certification. After promotion, the helper observes the
destination, captured inode, runtime and independent evidence again. A new
empty `.receipt.complete` directory establishes the prospective transaction
linearization point through its filesystem creation timestamp. Stable
byte/version observations on both sides of this boundary, followed by directory
sync and reconciliation, must certify it before Apply reports success. Each
observation checks inode identity, size, modification time and change time
around the byte read; changing evidence is not a successful observation.
Digest differences with change timestamps at or before the boundary, missing
files, or ambiguous observations require recovery. Timestamp equality is
conservatively a conflict. Before returning success, a separate disposable
filesystem probe must observe a timestamp strictly beyond the seal, ensuring
ordinary writes begun after the completed Apply cannot share its timestamp
tick. Three non-advancing observations fail closed rather than certifying an
unsupported clock. Directory sync or certification failures retain a
`.receipt.conflict` marker as well as the recovery journal and lock.

All preference readers reconcile receipts before and after their configuration
read, including when the transaction lock/recovery journal is absent. A
protocol-2 receipt without its completion seal, a conflict marker, changed
independent reviewed evidence, or a pre-completion byte conflict blocks every
role with an actionable recovery error. Older receipts have no explicit seal;
readers use their promotion change timestamp to reject detectable unresolved
pre-promotion conflicts, rather than assuming that marker disappearance proves
success. Receipt and seal evidence must remain untouched until reconciliation.

A successful certified operation linearizes at its seal creation, not at its
return message or later lock cleanup. Changes strictly after that boundary
are ordinary future project edits, including later writes to a retained open
inode; they do not retroactively fail a completed operation. Independent
reviewed snapshots remain immutable. A detected failure stays unresolved even
if another later write changes the file timestamp: its conflict marker requires
explicit reconciliation. This protocol requires same-directory rename,
hard links, durable directory sync and ordered filesystem change timestamps;
unsupported operations and ambiguous observations block, not waive recovery.

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

`test_playbook_config.py` uses temporary projects, fixture discovery and a clock
at this boundary, including injected storage checkpoints. It proves typed
read/edit/preview/Apply/cancel, migration, next-lane resolution, revision
conflicts, conflict-preserving recovery and runtime preservation. Fixture results are not direct
Codex or Conductor qualification; S8 remains separate. Upstream updates remain
maintenance work, with compatible migrations and retained customisations,
never a per-turn automatic updater.

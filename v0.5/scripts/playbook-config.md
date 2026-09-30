# Project configuration boundary — S2

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

## Personal presentation and first setup

Supply `--preferences-dir {user-local-directory}` on read and every reply.
The directory must be outside the project; there is no implicit path or host
setting change. The private destination is `preferences.json` in that directory,
containing exactly schema_version 1 and presentation `guided` or `expert`.
It never overlays project defaults. Read takes optional `context` containing
only known `goal` and `billing` (`api`, `subscription`, `mixed` or `unknown`).
These facts stay in the private conversation; S2 does not persist billing.
The helper returns only missing questions. Typed `Goal <context>`, `Billing
<mode>`, `Guided` and `Expert` answer them. Reopening with known context and
saved presentation skips onboarding questions. Omit context for the ordinary
preference reader; Configure supplies existing context rather than reasking it.

`Guided` / `Expert` produces a personal before/after preview and exact local
destination. `Apply preference` is an explicit **local-only** transaction,
then returns to the complete unsaved project draft. Project `Apply` is separate;
there is no multi-destination success claim. Presentation alters rendering only,
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
all matches establish the completion point. Only non-content bookkeeping
follows: marking the protocol-3 receipt complete and removing the lock, so later
content or metadata edits cannot retroactively turn that save into a conflict.
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

`test_playbook_config.py` and `test_playbook_config_roles.py` use temporary projects, fixture discovery and a clock
at this boundary, including injected storage checkpoints. It proves typed
read/edit/preview/Apply/cancel, migration, next-lane resolution, revision
conflicts, conflict-preserving recovery and runtime preservation. Fixture results are not direct
Codex or Conductor qualification; S8 remains separate. Upstream updates remain
maintenance work, with compatible migrations and retained customisations,
never a per-turn automatic updater.

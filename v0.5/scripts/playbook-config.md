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

Numeric editor choices accept decimal Unicode digits and leading zeros, with a
maximum of 64 characters per index. Non-decimal digits, oversized indexes and
out-of-range choices block with corrective guidance and retain the sealed draft
for Back or Reload. This applies to role, model, runner, reasoning, identity and
skill indexes, including each comma-separated skill choice.
Edits and explanations preserve other draft values. Invalid replies retain
the valid draft under `retained_proposal`; `Back`, `Edit` and `Edit <role>`
reuse it without losing unrelated edits, while explicit
Reload discards unsaved edits. `Explain <role>` reports the selected route,
discovery authority/date and separate task-fit/cost evidence without invoking
anything. `qa` always inherits verification; Coordinator has no edit path.
An optional `coordinator` identity in the request-bound discovery response
reports the current chat with that observation's authority/date, never a
catalogue default or launch proof. Without it, Coordinator is explicitly unknown.

The proposal is a complete model-role proposal with origins and reasons for
retaining starting choices plus separate read-only recommendations. Skill-job
configuration, local presets and billing persistence retain their own gates.
Availability is not suitability,
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
known `goal` and `billing` (`api`, `subscription`, `mixed` or `unknown`), plus
optional local task/risk and structured recommendation evidence below.
Goal stays in the private conversation; an explicitly approved local save can
persist billing, never in shareable project configuration.
The helper returns only missing questions. Typed `Goal <context>`, `Billing
<mode>`, `Guided` and `Expert` answer them. Reopening with known context and
saved presentation/billing skips known onboarding questions. Omit context for the ordinary
preference reader; Configure supplies existing context rather than reasking it.

`Guided` / `Expert` produces a personal before/after preview and exact local
destination, including `resolved_destination` behind any directory aliases.
An unpaired public project proposal carries an opaque digest of the project
directory identity. Paired personal previews retain private project and personal
directory records with resolved paths and device/inode identities, or the nearest
existing ancestor for a new directory. Apply rechecks these identities and rejects
changes even when file bytes match.
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
content-digest completion and non-destructive recovery. Newly added or replaced
reusable job bindings also use project Apply's current-source, retained-proof and
job-contract eligibility check against the reviewed preview. Drift blocks before
publication and retains the pending draft for explicit editing and a fresh preview.
Unchanged older reusable bindings remain inert; presentation, billing and unrelated
model edits do not requalify them. Their lock, recovery
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
On first setup, saving reusable data preserves the unanswered Guided/Expert
question. Apply preference blocks until an explicit presentation answer; that
answer retains the drafted defaults or preset rather than replacing them.
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
treated as success. Both completion destination lists retain the exact reviewed
personal destination in the local response only, never the shareable project
configuration or its journal.

Incomplete pairs block project and personal reads/writes, including a different
project using the same personal store. On failure, only a destination still
matching this transaction's attempted bytes can be restored. A racing writer is
captured intact and restored by no-clobber linking when possible, never overwritten;
any other concurrent bytes and retained capture remain available for recovery.
Previous evidence is read once and digest-verified into a separate restoration
snapshot before publication. The no-clobber link publishes that snapshot, not
the mutable backup inode, so backup edits during publication cannot become live
configuration. Changed backup evidence remains retained and requires recovery.
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

Defaults and named presets use the same unique admitted-route match as Configure.
Omitted optional host metadata does not block a unique match; saved metadata
remains a constraint, and ambiguous or missing matches block seeding. Preview
and Apply preserve the saved values without enriching them from host discovery.

Bootstrap retains its existing managed-file preview, approval, preservation and
status flow. Seeding creates configuration only after bootstrap completes
without manual reviews; partial bootstrap or seed failure is reported honestly.
It never replaces existing state/configuration. Existing projects use Configure
and explicit Load/Apply instead. Subsequent ordinary bootstrap checks omit the
seeding flags. Configure does not invoke bootstrap or launch a model/stage.

Project saves with or without personal preferences open and verify the reviewed
project directory and keep transaction operations relative to its descriptor.
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
Unsupported descriptor-relative storage operations block the save. Observable
project path or device/inode changes require a fresh preview even when file
bytes are identical; cleanup stays in the opened directory. After capture or
publication, retained recovery evidence must be reconciled there.

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
policy is defined. The 24-hour guidance/pricing cache is separate
from availability and launch identity. Execution still requires independent
live admission. `--now` is a fixture clock only. Suitability/cost claims remain
separate from availability and execution authority.

Legacy model choices may omit optional provider, label or thinking metadata.
Such a choice is available only when exactly one freshly admitted route matches
every saved identity field. Explicitly saved metadata must still match. Multiple
host routes matching an underspecified choice require explicit selection; the
configuration helper never guesses which provider or label the user intended.

## Read-only recommendation evidence

Successful official evidence is reused for at most 24 hours only at Configure
and existing lane-discovery checkpoints. First use, explicit typed `Refresh`,
and a changed discovered model/version fingerprint check immediately. Each
official URL is fetched at most once in a discovery pass; successful sources
can be reused independently when another source is incomplete. Explain, edits,
resolution and unrelated turns do not retrieve sources. No watcher, package
installation, preset rewrite or stage launch is introduced.

Delayed Explain and display replies locally recheck each original selected
guidance/rate claim at the current clock. Exactly 24 hours remains usable.
Expired, future, missing or malformed dates and unsuccessful statuses withhold
the affected suitability, rates and subtotals; `withheld_evidence` retains the
original date and labels the limitation. Fresh siblings and source envelopes
cannot extend a claim. Repeat Explain and retained-draft recovery use the same
projection, offering explicit Refresh or ordinary role editing without fetching,
ranking a substitute, changing choices or writing the advisory cache.
Back, preference/preset previews and rejected replacement acceptance retain
the selected original claims too; a rejected Accept never creates a newly
acceptable proposal from a younger sibling. Malformed advice mappings withhold
all nested advice copies while retaining available original dates and recovery
instructions. A content revision establishes integrity, not evidence authority.
Every cost payload requires projection, including an estimate with no choice,
guidance or rate. A token subtotal requires an adequate original rate for the
selected model/provider and API route, with supported currency, units and
numeric amounts; source/date metadata alone cannot support it. Missing or
invalid pricing leaves valid suitability available with cost unknown.
The supplied estimate must also match the proposal's `context.workload`,
including bounded token/retry counts and the selected rate's exact billing route.
Its numeric amount must agree with those counts and rates, and its currency,
source URL and original successful date must match the selected rate. Missing or
inconsistent assumptions, amount or source metadata withhold only the subtotal;
self-consistent estimate assumptions cannot replace the requested workload.
Projection retains the unsupported estimate as dated withheld evidence and
never silently recalculates a displayed amount. Explicit Refresh can obtain new
evidence; ordinary role editing remains available.
The selected `recommendations[role]` owns the claim text and successful dates;
a divergent, missing or malformed `replacement.advice` cannot replace it during
rejected Accept. Even a partial root retains its own claims. When suitability
is withheld, its independently dated price is retained as withheld evidence too,
not displayed as a supported cost. Subsequent Explain and Back project that same
root; only explicit Refresh may select new official evidence.

The live CLI uses a private external user cache; `--evidence-dir` explicitly
selects an external directory on every request. Library callers can supply
`evidence_dir`; omission keeps evidence only in the service instance. Cache
schema 1 holds bounded official claims, successful source dates and revision
metadata when supplied by a trustworthy adapter, otherwise SHA-256 content
fingerprints. Retrieval failures preserve successful dates and mark claims
stale/incomplete. A discovery fingerprint detects changed model/version
identities without saving a route catalogue. The cache is at most 256 KiB,
with at most 256 records per kind; it is advisory and never launch authority.
Changed material claims return source-specific `changes` with old/new evidence
and dates, reassessing existing models. Semantic claims are compared before any
cache filtering, independently of page fingerprints: list changes can withdraw
claims even when page bytes are unchanged. Equal claims yield no change notice.
Missing pricing remains unknown; new models need a reviewed
guidance entry and live host-supported capability/reasoning. A withdrawn
reviewed entry is a material change.

On the official adapter path, cached guidance and retained advice must exactly
match the canonical JSON SHA-256 fingerprint of every current reviewed entry
field, including its heading and model link, as well as its claim fields. Legacy
claims without a valid fingerprint and removed or changed claims
are dropped and their source is due for refresh; matching confirmations keep
the inclusive 24-hour cache for viewing advice. Display checks the current list
and latest successful cached source check locally. Accept replacement instead
retrieves the original reviewed entry's official source once before editing
the draft, including retained and recovered proposals. A saved confirmation
alone cannot authorize acceptance. Unavailability, withdrawal or a changed
current reviewed entry refuses with an explanation and unchanged draft,
project and approval bytes; no other model is ranked or chosen. This explicit
acceptance boundary is independent of cache publication success. A cache write
failure is nonfatal only when this attempt obtained an actual fresh source
confirmation; a stale fallback never confirms. Cached advisory display retains
its ordinary freshness rules; no durable invalidation subsystem is added.
Controlled evidence injected by
tests or `--evidence-fixture` keeps its existing structured-fixture behaviour;
it is never live provider proof.

Before accepting a replacement, recheck current authoritative discovery and the
specific proposed route's role/task/risk suitability against its original guidance
date at the current clock. Exactly 24 hours is valid; one second later, future,
missing or malformed dates cannot edit the draft. Retain the unavailable saved
value and other edits, and offer explicit `Refresh` or ordinary role editing.
Changed discovery/version invalidates cached suitability until explicit Refresh;
acceptance checks only the original official source and never substitutes
another route. Missing
pricing alone does not invalidate suitable guidance. Apply still performs its
independent availability, identity, file-revision and skill-eligibility checks.

Unavailable selected or saved routes remain visible in the `replacement` step.
It offers one suitable verified alternative for the affected role, with
runner/reasoning, fit, cost limits and evidence. `Accept replacement` edits
only that draft role and returns the full before/after preview. `Choose another
model` opens its ordinary editor; `Not now` saves no pending preferences or
presets and reports any local advisory cache refresh. With no eligible
alternative, restore access, refresh evidence or choose explicitly; no route
is invented. Apply checks all selected roles with fresh host evidence. A route
disappearing after preview returns recovery without saving; acceptance still
requires another explicit Apply. File/skill drift invalidates the proposal at
the existing gates. Presets, billing, repair constraints, active/approved
feature choices and history remain untouched. Every launch independently
checks current availability and authoritative identity through model-router.

Live helper `read` and `advise` initially retrieve five fixed official model,
reasoning and pricing pages through `model_recommendations.OfficialSources`.
Only HTTPS GETs are used: no credentials, provider model execution, benchmark,
package change or billing lookup. Redirects outside the source host are blocked;
retrieval has size/time bounds. Provider page text is untrusted data, never
instructions. There are no static prices or model rankings. Ambiguous tables and
unrecognized identities remain incomplete. Exact provider IDs must match fresh
host discovery, including host-supported reasoning. Provider guidance alone
proves neither availability nor job suitability.
Task fit comes only from the edition's reviewed guidance list,
`v0.5/model-guidance.json`; the adapter never infers task fit from provider
prose. A retrieval confirms an entry only when the official page has the
entry's section heading immediately followed by a leaf block whose rendered
text equals its exact reviewed paragraph
(whitespace, Unicode default-ignorable characters and inline formatting ignored)
containing the entry's model link. Neither heading nor block may be inside or
contain deleted, struck-through or quoted markup (`del`, `s`, `strike`,
`blockquote`, `q`). Inert template descendants are excluded at runtime and
release checking. Otherwise the entry is
withdrawn: the source uncertainty says "provider wording changed since review"
and no task fit or replacement follows. Empty leaf blocks and separators break
adjacency; textless layout wrappers containing the paragraph do not. Inline
text is composed before whitespace is normalised, preserving spacing across
formatting boundaries. Text composition treats native `</br>` as an
attribute-free `br` start: both
separate words, while breaks between words retain normalized whitespace.
Hidden starts, raw/inert bodies and withheld select/foreign content remain
excluded; a self-closing `br` start keeps its own visibility attributes.
Element traversal, block classification and text composition are iterative:
deeply nested visible wrappers and inline text
retain the same order, adjacency and leaf rules beyond interpreter recursion
limits. Native CDATA-shaped and marked declarations are bogus comments ending
at their first `>`; abrupt empty comment closes (`<!-->`, `<!--->`) precede
later full closes. Visible suffix text still changes reviewed wording or
pricing context. Genuine comments and harmless closed bogus declarations
contribute no text and leave unchanged visible units usable, including elsewhere
on the page. Withholding does not change declaration namespaces: native bogus
comments inside templates still end at the first `>`, preserving genuine
template closes and visible successors. Only exact uppercase CDATA in an actual
SVG/MathML declaration context consumes through `]]>`; close-like text cannot
release inert confirming copies. Namespace tracking distinguishes nesting,
integration descendants, ignored native tokens, foreign breakouts and
self-closing foreign elements. Foreign names do not enter HTML raw-text or
template mode. Foreign own closes cannot release an enclosing native template;
integration encodings use the first attribute. Native raw bodies and
hidden/excluded descendants remain withheld.
Within native select context, ignored or misplaced end tokens cannot remove
the select or its foreign integration ancestors from declaration tracking.
Option/optgroup ends affect only their permitted current entries; genuine
select and template closes retain usable visible successors. Real foreign
CDATA after a genuine select close still consumes close-like text through `]]>`.
Native scope scans can still take additional work on deeply nested
input within the existing source byte limit; this is not a rendering or
performance guarantee. A malformed list supplies no guidance; schema version
must be the integer 1, never a boolean or another type. Duplicate JSON object
keys anywhere or duplicate labels within a provider invalidate the whole list;
labels identify price rows. Duplicate attributes on confirming elements or
their context cannot confirm an entry.
Literal bodies of `script`, `style`, `xmp`, `iframe`, `noembed`, `noframes`,
`textarea` and `title`, conditional `noscript` content and `plaintext` cannot
supply heading, paragraph, link or pricing-table elements. Self-closing flags
are effective only for HTML void elements. Raw bodies consume close-like text
until their genuine close; `plaintext` continues through EOF. The adapter
handles [script escaped/double-escaped transitions](https://html.spec.whatwg.org/multipage/parsing.html#script-data-double-escaped-less-than-sign-state):
a double-escaped `</script` returns to escaped text rather than closing the
element. Ordinary scripts and visible entries after genuine closes remain
usable. This rendered-element boundary applies equally at runtime and release
checking on supported Python versions; it adds no whole-page prose inference.
Finalize native EOF before guidance confirmation and pricing extraction.
Bare `<` and `</` become rendered text; buffered character references resolve.
Incomplete native start/end tags, comments and declarations supply no visible
text. Valid unclosed visible elements retain their text without synthetic
closing tokens; incomplete pricing tables remain unknown. EOF cannot release
raw/RCDATA, hidden, inert, foreign or select exclusions or erase existing
interrupted-paragraph barriers. Runtime retrieval and release checking use
the same boundary on supported Python versions.
Forbidden `del`, `s`, `strike`, `blockquote` and `q` descendants still exclude
their containing reviewed heading or paragraph when the element or an ancestor
is hidden, including closed `details` and `dialog` content. This structural
condition is separate from rendered-text filtering. Apparent tokens in
raw/RCDATA bodies or inert templates supply no such descendants. Hidden
ordinary text, links and blocks remain excluded from rendering and adjacency;
unrelated clean reviewed units and visible successors remain usable.

HTML `hidden` attribute presence excludes the element and its descendants for
all cases and values, including `until-found`. Hidden inline text, links and
blocks contribute neither rendered text nor link evidence nor adjacency.
Closed `dialog` content and closed `details` content outside its first direct
`summary` are excluded too. `datalist` content, metadata (`base`, `link`, `meta`,
`param`, `source`, `track`), image-map `area` elements and hidden inputs create
no rendered block. Nested scopes and nonvoid self-closing flags retain this
boundary, while genuine visible guidance and pricing after closes remain
usable. These explicit HTML visibility rules do not implement CSS/JavaScript
rendering or general browser tree repair. Fresh replacement acceptance uses
the same boundary and refuses hidden copies without mutating the draft,
project or approval records.
Visibility filtering preserves bounded implied paragraph, heading, list-item
and table-cell ends. A hidden block start can end a visible paragraph; its
prefix and following text cannot be joined into one reviewed leaf block.
Stray paragraph closes retain an empty structural barrier to adjacency.
Interrupted source paragraphs are ambiguous; they cannot become confirming
leaf blocks merely by dropping the block that interrupted them.
Ambiguous table content outside cells or captions cannot confirm guidance;
the adapter withdraws it instead of reconstructing a browser tree. Valid
visible successors and hidden inline additions remain usable.
Native HTML `image` starts normalize to void `img` before visibility filtering.
Legacy metadata `basefont`/`bgsound` and legacy control `keygen` starts are void;
native `frame` starts outside a frameset are ignored. Their attributes cannot hide following visible
qualifiers in headings, paragraphs, model links or pricing. Actual hidden
containers and ancestors retain their visibility boundary; foreign/integration
scopes and raw/inert content retain their existing exclusions. Genuine visible
successors remain usable, with the same fresh draft-only acceptance rules.
Ruby and its `rb`, `rp`, `rt` and `rtc` descendants remain inline in reviewed
headings, paragraphs and model links. Hidden annotations contribute no text;
visible annotation text participates in exact matching. With ruby in native
scope, annotation starts apply implied ends only at the stack top before
visibility filtering; `rt`/`rp` retain an enclosing `rtc`. Genuine nested blocks,
excluded descendants and ambiguous contexts still withdraw affected units.
Native content-model scopes cannot supply confirming blocks from apparent
markup. The bounded adapter withholds `select`, `option`, `optgroup`, `button`,
`meter`, `progress`, embedded fallback (`object`, `applet`, `audio`, `video`,
`canvas`) and `frameset` subtrees. SVG/MathML subtrees are conservatively
withheld, including HTML integration points. An ambiguous barrier prevents
omission of qualifiers from making a heading, paragraph or price newly usable.
Ignored document/table tokens and nested forms likewise cannot hide visible
qualifiers; repeated document tokens withdraw ambiguous document evidence.
Nested controls and foreign integration/breakout contexts retain raw-text and
inert-template safeguards. HTML nonvoid self-closing flags cannot escape those
contexts; genuine foreign self-closing elements retain usable successors.
Correctly closed scopes, ordinary forms and hidden inline additions remain
usable. This is bounded exclusion, not general browser tree construction or
CSS/JavaScript rendering; reviewed-list and fresh acceptance rules are unchanged.
Literal `hidden` attributes on these scopes or apparent ancestors cannot remove
their ambiguity barriers. Nested selects/buttons, implicit control closes,
ignored starts and foreign breakouts can expose qualifiers outside the apparent
hidden scope. Affected headings, paragraphs, model links and pricing context
remain withheld. Ordinary hidden inline additions and visible successors after
correctly closed scopes retain the existing visibility rules.
The barrier applies consistently to every ignored or misplaced scope family,
including table structural tokens outside a table, nested forms and repeated
document tokens, even under apparent hidden or closed ancestors. Unrelated
closes and nonvoid self-closing flags cannot erase visible qualifiers from
reviewed units or pricing context. Raw-text/inert exclusions and ordinary
valid forms retain their existing handling.
Active HTML formatting elements (including anchors) can survive paragraph and
other structural ends and reconstruct hidden or excluded context later. The
adapter retains an ambiguity barrier for detached formatting and adoption or
misnesting, including nested anchors and `nobr`; affected reviewed text, links
and pricing cannot confirm. Explicit own closes and genuine cell/caption or
`marquee` formatting boundaries release usable visible successors. Raw/inert
and withheld native/foreign descendants never supply this formatting state.
An own close across open blocks can clone the formatting entry; repeated own
closes alone cannot prove release. Retain that adoption barrier until a genuine
formatting marker clears the affected context.
Genuine closed hidden-inline additions remain usable. This is conservative
visibility handling, without browser reconstruction or a new dependency;
the reviewed-list and advisory-cache/fresh-acceptance rules are unchanged.
End tags cannot release an ancestor across native scope boundaries, including
tables, cells and captions. Generic inline closes stop at native structural
boundaries; document ends do not remove document ancestry. Withhold ambiguous
partial ancestor closes rather than reconstruct them. Genuine explicit and
implied table ends release cell/caption formatting markers so visible successors
remain usable. Hidden content and ambiguous text, links or pricing cannot
authorize fresh acceptance; refusal preserves the retained draft and project,
approval and original proposal bytes without reranking or launch.
Successful withdrawal also removes any retained guidance label used to identify
Anthropic prices during that check; it cannot attribute a new price row.
Rationale and limitations distinguish "No reviewed guidance yet for …" from
"Reviewed guidance withdrawn for …: provider wording changed since review".
Maintainers run `scripts/check-model-guidance.py` before a release.
Rates require the table's explicit enclosing tier (a heading or provider
switcher pane), not a nearby Standard label or a generic pricing URL. Batch,
other nonstandard tiers and ambiguous context cannot supply Standard estimates.
Single-context Standard tables require explicit short-context evidence; long-context
restrictions remain incompatible regardless of hyphenation or HTML whitespace;
unrecognized captions and negated context mentions do not establish provenance;
grouped short/long-context columns also require explicit context headers.
Anthropic base tables accept only recognized base/short-context labels in their
enclosing context and captions. Each model row must be exact or carry the
recognized `For coding` task suffix; any other `For ...` qualification is
ambiguous, not evidence of base applicability. Extended or long-context tables
and rows cannot provide `standard-base-uncached` rates or base subtotals.
Upstream markup or wording changes require new source-shape compatibility
checks before extending recognition; preserve user choices during any migration.
The reasoning guide is fetched separately but cannot supply task suitability;
without independently supported reasoning data, its check remains incomplete
and reasoning support comes only from authoritative host discovery.

`recommendations` contains one eligible suggestion or an explicit unknown for
each role, separately from `before`/`after` and their effective origins. Retain
all non-identity repair constraints and current approval/history bytes.
Eligibility precedes comparison: use role-admitted host discovery, existing
allowed runners and owning-gate constraints. Among eligible task-fit routes,
preserve discovery order (including the router's cross-runner Verify preference),
not an invented price/performance ranking. QA still inherits Verify.

Context may include `task: coding | analysis`, `risk: ordinary | high`,
`constraints` keyed by role, `workload`, `route_billing`, `observations` and
`outcomes`. Omitted task/risk can be conservatively inferred from a known goal;
the rationale labels that uncertainty. An unclassifiable goal yields no advice.
Typed `Task <task>` and `Risk <risk>` update only advice context. Explicit
task/risk is preferable for nuanced or high-stakes work. Context and evidence
are local conversation inputs, never fields in shared config or personal presets.

For lane `advise`, send `role`, optional approved `feature_choice`, context and
the same fresh `--discovery-command`. It returns `effective` unchanged and a
separate `recommendation`. `context.constraints[role]` must have owning-gate
`authority: true`, `permission: true`, and Verify `independent: true`, not
model-generated assertions. Discovery must already exclude incompatible
permissions and unauthorized routes. Optional `allowed_models`,
`allowed_reasoning` and `excluded_models` further narrow admission. Missing
checks yield no lane suggestion. This creates no selection/approval and never
amends `openai defaults`, active/pending routes or reusable preferences.

Keep the three classes separate:

- `guidance`: a reviewed provider statement confirmed on its official page:
  model, label, reviewed tasks/risks, text, source URL, successful `checked_at`,
  `reviewed_at`, `entry_fingerprint` and uncertainty. Host reasoning
  support remains availability evidence, not a claim derived from pricing.
- `cost.rates`: published API base rates, model/runner route, billing route,
  currency, unit, source URL, successful check date and exclusions. Estimates
  require `workload.input_tokens`, `output_tokens`, `retries` (nonnegative
  integers no greater than `2^53 - 1`) and the exact `billing_route`.
  Larger counts leave the subtotal unknown with an explicit numeric-bound limit,
  without conversion errors or writes. Every retry assumes the same tokens.
  Rates must be numeric integers or floats (not booleans), finite, nonnegative
  and no greater than `2^53 - 1` per 1M tokens. Invalid or oversized structured
  rates remain unknown; these rate and count bounds keep subtotal arithmetic
  finite before serialization. Nonfinite fixture JSON leaves source evidence
  incomplete under the existing retrieval boundary.
  Show a labelled token subtotal, not a bill or guaranteed verified outcome.
  Missing/mismatched inputs or rates mean unknown. For mixed billing,
  `route_billing["model_id@runner@reasoning"]` (or the runner-wide fallback)
  must identify API billing before rates apply; otherwise
  show only observable usage/limits or unknown. Subscription observations need
  their own `source_url`, `checked_at`, `uncertainty` and `usage_or_limit`, keyed
  by the same exact route identity or runner-wide fallback.
- `local_outcomes`: optional independently retained local observations with
  exact model/provider/runner/reasoning, task, risk and workload match, `verified:
  true`, portable `project-evidence://<id>` source, successful date, uncertainty
  and summary. Absence or incomparable data stays unknown. An observation is
  not proof of cross-model savings or the cheapest verified outcome. Do not
  export private summaries, billing, paths or project results into tracked logs.

Library callers inject `recommendation_sources` returning structured
`guidance`, `rates`, `sources`; wire `OfficialSources(...).retrieve` for live
initial use. Unwired callers report unknown rather than silently contacting
providers. Controlled CLI tests use `--evidence-fixture` with `--now`; fixture
values are synthetic, not current facts. The initial proposal retains evidence
through edits and Explain; neither operation reretrieves or invokes candidates.
The bounded 24-hour cache and draft-only replacement acceptance follow the
freshness and recovery rules above; no automatic change watcher runs.
Failed/incomplete checks retain only an actual previous
successful date supplied to the adapter; otherwise `checked_at` is null.
`retrieved_at` records a page fetch, not a successful claim check. Never redate
old claims, manufacture a new-model comparison or automatically change defaults.

Exit 0: decision required, proposal ready, applied, unchanged or resolved.
Exit 2: blocked/recovery required or invalid request; report the message and
reload/edit as directed. Argument syntax errors also exit 2.
No environment, credentials or host changes are needed.

Local Apply preference and paired project Apply both recheck newly added or
replaced personal defaults/preset job bindings against the current source,
retained proof, approval, resolution, job contract and reviewed catalog immediately
before each destination mutation and again at individual and paired completion.
Recommended resets only the project draft; pending personal saves still require this check. Drift blocks
before either destination is written when observed at the first publication
check, and retains the proposal for explicit editing and refreshed preview.
Drift observed after capture or publication requires the existing recovery
protocol; it never produces a validated success receipt or overwrites concurrent
bytes. These are bounded observations, not a lock on external skill sources;
changes after completion still invalidate eligibility at the stage invocation
gate. `Edit skills <job>` rereads that job's current
options, eligibility and rejection diagnostics while retaining selected bindings,
other role/context edits and pending personal data. Opening the editor or backing
out chooses nothing. Explicitly choose an eligible fallback or newly qualified
source, repeat Save defaults or Save preset <name> to replace the pending reusable
preview, then Apply preference or project Apply. Reopen each affected job editor
when its catalog changes; model Refresh and Reload are not skill-draft recovery.
Older unchanged reusable job bindings remain
inert during presentation, billing and model-only preference edits.

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
at this boundary, including injected storage checkpoints.
`test_config_repair_boundaries.py` covers directory identity and numeric recovery
through both the API and CLI. This coverage proves typed
read/edit/preview/Apply/cancel, migration, next-lane resolution, revision
conflicts, conflict-preserving recovery and runtime preservation. Fixture results are not direct
Codex or Conductor qualification; S8 remains separate. Upstream updates remain
maintenance work, with compatible migrations and retained customisations,
never a per-turn automatic updater.

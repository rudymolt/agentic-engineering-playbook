# Supported job bindings — contract version 1

Configure stores optional `skills: {contract_version: 1, jobs: {...}}` beside
schema-1 model preferences. Each job holds an ordered list of
`{source_id, source_sha256, contract_sha256}`. Logical collection/skill identities
and project-relative routes are portable; installed paths and names are not
configuration identities. An older model-only adoption stays model-only until
a skill edit is explicitly applied. First skill adoption previews all five
manual defaults as well as the edited job. Unsupported versions block writes;
they are not silently migrated. Existing runtime selections and approvals are
not destinations of this save.

## Job contracts

The executable contract is `JOBS` in `skill_bindings.py`. Every route retains
its owning stage's confirmation, tests, independent review/QA evidence, commits,
launches, permissions, configuration and maintenance boundaries. A preference
does not authorise any of those actions. Required inputs must already exist
before invocation; the stage validates outputs before advancing.

| Job / owner | Required inputs | Required output | Permitted effects / eligible forms |
| --- | --- | --- | --- |
| Alignment / 01 | User goal, project context, constraints, non-goals | Settled terminology, decisions, human-confirmed alignment | Reads and alignment/ADR documents. Manual or Playbook adapter; ordered context → decisions adapters. Confirmation remains after the entire composition. |
| Specification / 03 | Confirmed alignment, context and ADRs | Spec, acceptance criteria, human-confirmed test seams | Reads and specification documents. One manual or Playbook adapter. Tracker publication requires the existing stage authority. |
| Implementation / 07 | Approved spec, slice and test seams | Failing test, passing test and scoped implementation evidence | Scoped source/test edits and approved verification commands. One manual or Playbook red-green adapter; not upstream `/implement` with its nested review and commit. |
| Code review / 08 | Candidate diff, approved spec, independent verifier identity | Standards findings, spec-fidelity findings, evidence and verdict | Reads, verification commands and evidence output. One manual/Playbook adapter or exact-source compatible upstream report-only skill. Mandatory security/adversarial axes and fresh independence stay stage-owned. |
| Application QA / 09 | Candidate application, behavior contract, existing verified route | Browser evidence, defect reproductions and verdict | Reads, browser verification and evidence output. Manual or one already selected and independently eligible project report-only route. No harness generation, maintenance opt-in or doctor-as-pass. |

## Evidence and attribution

The local adapters refer to the authoritative stage documents, not modified
copies of upstream skills. Their source fingerprints bind those instructions;
contract fingerprints additionally bind obligations and provenance. They are
labelled `(Playbook adapter)` or `(Playbook manual)`, never as unmodified Matt
Pocock/gstack skills. Stage instructions retain their existing attribution.
No upstream-derived adaptation is endorsed by this contract version. Such a
source must obtain a separate contract audit, not borrow its original name,
registry category, source digest or upstream approval.

Registry provenance supplies collection identity, status, pin and attribution,
not job eligibility. For code review, the existing exact-installed-source
`check-upstream-compatibility.py` decision must permit report-only invocation,
and its required outputs/effects/prohibitions must satisfy the job contract.
The current production manifest marks upstream code review incompatible, so
only its named manual/adapter alternatives are offered. Equivalent bounded
embedded audits for upstream alignment, specification and implementation are
not recorded here; those stages explicitly offer the local fallback rather
than pretending installed `/grill-with-docs`, `/to-spec` or `/tdd` is endorsed.
Wayfinder remains attributed to Matt Pocock and user-invoked separately.

Discovery inspects supported project/user roots without executing skills. Two
distinct installed sources claiming one identity are a collision, even with
identical content. They are excluded, not resolved by search order. Separate
collection identities never alias by display name. A missing, changed, unknown,
colliding or incompatible saved source blocks invocation and Apply until the
user explicitly previews a fallback. Reload never substitutes a saved choice.
The explicit `Edit skills <job>` recovery checkpoint refreshes current options
and rejection diagnostics without replacing any selected identity or unrelated
draft. Choose a current eligible route, preview it again (including Save defaults
or Save preset <name> for pending reusable data), then explicitly Apply. Back or
Not now does not accept a fallback. Other changed job catalogs require their own
editor checkpoint. Compatibility evidence/invocation changes also invalidate
the contract digest.

## Portable custom sources

S4 adds `custom:<logical-identity>` and canonical
`project:<relative-path-to-SKILL.md>` identities without changing the shared
binding schema. A custom source is labelled `(Custom)`, not by its display name
or claimed author. An already qualified QA route keeps its verified
`(Project route)` label. Custom embedded upstream forms are excluded: copied
content, a matching hash, or a claimed `embedded_source_id` cannot obtain an
upstream label or bypass S3's uniquely installed-source and collision checks.
Select the existing supported upstream binding when those checks pass.

The read-only machine-local store defaults to
`~/.config/ai-playbook/custom-skills`; `--custom-bindings-dir` selects another
local store for both Configure and `job-route`. The store must be outside the
shareable project, including resolved directory aliases. Its bindings,
approvals, evidence directory and individual evidence files must not point
back into the project. Invalid locations block with explicit recovery and
create nothing. Discovery checks aliases again; a retargeted store cannot
make a pending proposal eligible. Never track, copy into a project, or publish
the store. Configure does not create it, install anything, or write audits.

The store has three separately retained inputs:

- `bindings.json`: `{version: 1, sources: {identity: {source, audits}}}`.
  `source` is the local absolute locator for a `custom:` identity; `audits`
  maps a job to a retained audit ID. For `project:` sources, the canonical
  identity is the locator, so no machine source binding is required; the
  stage-retained approvals discover that exact project identity. An explicit
  project binding, if supplied, must repeat the same canonical locator.
- `approvals.json`: `{version: 1, audits: {audit_id: approval}}`. Each
  stage-owned approval contains `source_id`, `job`, `owner`, `revision`,
  `evidence_sha256` and `resolution_sha256`. The last value is the SHA-256 of
  the resolved source's POSIX locator encoded as UTF-8. This machine-local
  pin prevents a same-content replacement or retargeted alias from borrowing
  its predecessor's local qualification. After local resolution changes,
  the owning stage must independently requalify and issue a new audit revision,
  followed by a new Configure preview/Apply; never edit the pin to keep an old
  approval alive.
- `evidence/<audit_id>.json`: the independently retained exact-source contract
  audit. It contains `contract_version`, `source_id`, `job`, `owner`,
  `source_sha256`, `inputs`, `outputs`, `effects`, `prohibited_effects`,
  `retained_authority`, `invocation`, `form`, `report_only`, `verdict` and
  `independent`. Inputs, outputs, prohibitions and retained authority match
  the exact S3 contract; effects are a nonempty subset of its permitted
  effects. The verdict is `pass`, independence is true, and the approval
  pins this separate audit's bytes. The form is `single`, except QA's
  `project route`. Invocation is the exact portable identity, with
  ` --report-only` for review/QA; it is not arbitrary shell text.

**Trust boundary:** these are retained inputs from the owning stage's existing
qualification gate, not a way to manufacture proof. A self-authored local JSON
assertion, a boolean `independent`, or a second self-authored approval file is
not proof of real independent execution or authenticated approval. Configure
checks structure and exact pins; it cannot authenticate who wrote local files
or establish that execution happened. The owning stage must check the real
independent execution artifacts and authoritative verifier provenance before
recording a qualifying audit and again at its existing invocation/advancement
gate. Missing authentic evidence blocks that gate even if the local summaries
match. The synthetic test audits exercise those input contracts only; they
are never live qualification. This does not expand S3's project-QA summary or
caller-provided `approved_binding` trust claims.

QA additionally passes the unchanged S3 project-route gate and must resolve
to that already selected route. A custom audit cannot create, select or
maintain a QA harness. Embedded QA remains inside the project's existing
exact-source report-only check, not custom upstream attribution.

Only portable identity and source/contract digests enter the project file.
Public proposals and stage JSON expose neither local locators nor local store
contents. Contract digests bind audit identity, revision, evidence bytes and
invocation, never the machine locator pin: two machines can share byte-identical
configuration and retain their own resolution pins for the same audited source.
An owner integrating programmatically can use
`JobBindings.invocation_source(saved, job, owner, identity)` immediately before
reading/invoking the source; it repeats eligibility and returns the private
locator only to that owner, not in the public result. This is source resolution,
not execution or approval. The stage still supplies required inputs, enforces
effects/permissions and validates outputs.

Discovery, Apply and stage entry reread the local resolution and retained audit.
Local inventory, approvals and each consumed retained evidence file must have
exactly one filesystem link, including when read through a symlink. Observable
hardlink aliases block discovery, Apply and invocation; remove published aliases
and restore independent external files before retrying. Configure does not repair
or write the store. This conservative guard also rejects links entirely outside
the project. It does not protect against an external actor physically relocating
an already opened directory inode during a read.
Installed-source read failures report a portable error class and recovery action,
not an absolute source locator; they do not authorize fallback or invocation.
Catalog construction failures, including denied store traversal, block with
portable recovery guidance before any proposal or route is produced. Custom
store and source diagnostics never include the exception's locator text.
Rejected noncanonical inventory keys use `custom:unresolved` in diagnostics.
Local inventory keys outside the `custom:` and `project:` namespaces use the
same redacted category rather than borrowing a supported collection's identity.
Identity path components cannot be empty or a single dot: leading/interior
`./` and trailing `/` are rejected, never normalized into a different source.
Canonical dotted names and hidden directories remain valid.
Missing binding/evidence, rejected contract, source drift or a new audit revision
leaves the saved selection unresolved, with unmet requirements and the named
manual fallback. Recovery restores that machine's binding and authentic stage
evidence or explicitly previews a fallback; it never rewrites the source,
acknowledges a warning as approval, or executes a candidate experimentally.
Reopening Configure retains custom selections and approved execution records.
Source/software updates require stage-owned compatibility requalification at
discovery and invocation, not a background updater or checks on unrelated turns.

## Stage-owned custom invocation

The five owning stages explicitly call the private source resolver immediately
before using a custom source. `job-route` remains a report-only descriptor seam,
not a launcher. When using a non-default external store, pass the same
`--custom-bindings-dir` to that helper and `custom_dir` to the stage's local
`JobBindings` catalog. Never interpret the portable invocation string as a
filesystem path or arbitrary shell command.

The programmatic entry is `Configuration.dispatch_job(job, owner, invoke=...)`.
Inside the owning stage's invocation callback, use the same `saved` skills
selection to call `catalog.invocation_source(saved, job, owner, route["source_id"])`
when `route["provenance"]["kind"] == "custom-retained-audit"`. It revalidates
the source and audit before returning the private path. Load that exact
`SKILL.md` through the host's existing skill reader, enforcing the descriptor's
report-only mode for review/QA. Standard S3 routes keep their existing handling.
Missing or changed local data raises a blocker before the skill reader is called.

For adopted defaults, `saved` is the skills snapshot used by that stage entry.
For a resumed execution, it is the retained approved snapshot already
authenticated by that stage, not new defaults or unauthenticated caller JSON.
Neither this callback nor source resolution generates qualification evidence:
the stage must establish real independent qualification, inputs, permissions
and invocation authority first and validate outputs before advancing. Private
paths stay within the stage's reader; never insert them in shareable settings
or public descriptor/proposal output.

## Already eligible project QA

Stage 09 may record `.playbook-qa-eligibility.json` only after its existing
route selection and independent qualification, outside Configure. It is an
attestation to retained evidence, not a skill's self-description. Its fields:
`contract_version: 1`, `owner: "09"`, `route` (selected project-relative harness
directory), `source_sha256` (its exact `SKILL.md`), `evidence` (project-relative
JSON artifact), `evidence_sha256`, and `mode: "project-report-only"`.
The route must match both existing `decisions.verification_harness_path` and
`decisions.verification_harness_binding`. Configure does not create this record,
select a harness, generate proof or enable maintenance.

The evidence artifact binds the same `source_sha256`, `verdict: "pass"`,
`independent: true`, the observed ordered lifecycle
`["Launch", "Doctor", "Drive", "Evidence", "Cleanup"]`, and the exact QA contract
`outputs` and bounded `effects` above. The stage must retain actual commands,
observations, revision/instance and artifact locators alongside these summary
fields; fixtures are not live qualification. JSON attestations are reviewed
stage evidence, not cryptographic authentication or a sandbox guarantee.
Missing proof, changed artifacts, source drift or unsafe locators exclude the
route and block any saved selection. No external locator is permitted.

If the selected project route embeds an unmodified upstream `qa-only`, the
record instead declares `mode: "embedded-report-only"` and
`embedded_source_id: "gstack:qa-only"`. Discovery and dispatch additionally run
the same exact-source compatibility checker on its unique installed source,
validate its QA output/effect contract and bind that evidence. The production
manifest currently rejects it. A copied/modified adaptation cannot use this
mode; it needs its own separately reviewed contract or the manual fallback.

## Stage-owned dispatch

Before selecting the primary job invocation, the owning stage runs the shared
helper, for example:

```sh
printf '%s' '{"job":"implementation","owner":"07"}' | python3 v0.5/scripts/configure-playbook.py --project . job-route
```

This returns descriptors only; it is not a launcher. `configured: false` keeps
the legacy stage route. A configured result supplies source-labelled routes in
saved order, required inputs/outputs and retained authority. The stage consumes
those descriptors at its existing invocation point, using its current approved
runner, permissions and tools. A blocked result means stop and edit explicitly;
do not invoke the old default as a hidden replacement. Tests use
`Configuration.dispatch_job(job, owner, stage_invoker)` at that same seam to
prove saved order reaches the owning invocation; every route is revalidated
before the first callback. A callback failure belongs to the stage's failure
protocol, not an invitation to replay a partially completed composition.

These stage entries resolve defaults for **new choices only**. When resuming an
approved execution, pass its retained complete `skills` snapshot as the request's
`approved_binding`; it takes precedence and is still exact-source validated.
Do not reconstruct it from current preferences. Older active executions without
a binding retain their already approved stage route instead of adopting a new
preference. Configuration never writes the execution snapshot or history.

At an explicit upstream maintenance/upgrade checkpoint, review changed source,
compatibility and job contracts together, preview migrations, and retain project
customisations. No per-turn updater or automatic preference rewrite is added.

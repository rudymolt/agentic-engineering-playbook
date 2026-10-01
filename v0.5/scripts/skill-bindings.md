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
Compatibility evidence/invocation changes also invalidate the contract digest.

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

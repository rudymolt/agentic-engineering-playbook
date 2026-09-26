# V0.5 maintainer cadence

> Maintainer-only procedure for upstream drift and release batching. Projects bootstrapped from the playbook do not copy this file or add these cadences to `playbook-cadences.yml`.

## Monthly upstream drift check

The **repository maintainer** owns this comparison. `.playbook-maintenance.yml` records `last_verified` and `next_due`; the weekly `.github/workflows/playbook-maintenance.yml` due-state check surfaces an overdue monthly comparison within seven days. The canonical release-readiness command also fails once `next_due` is reached.

Run once per month, and before a playbook release that changes an upstream skill contract.

0. Run `python3 v0.5/scripts/audit-upstream-installed.py` on the maintainer host and paste its
   report into the month's analysis note. It compares the installed skills and the gstack checkout
   with the pins in `upstream-skills.json`, re-derives every embedded reviewer digest, and lists
   skills installed but not registered (adoption candidates) and stale copies of renamed skills.
   It reports only; the decisions below remain human.

## Generated inventories

After editing `upstream-skills.json`, run `python3 v0.5/scripts/generate-upstream-inventory.py`
and commit the registry and generated inventories together.

1. Open the authoritative release page for each upstream dependency.
2. Compare the released/tagged skill tree with stage 00's accelerator inventory and the stage map.
3. Compare behaviour, not names alone: inputs, outputs, invocation ownership, dependencies, and removed/renamed commands. Update `upstream-integrations.json` only from the exact released or installed source that was inspected.
4. Re-check the release page on the day the sync is finalised. Main-branch trees and raw CDNs can lead or lag the released artefact.
5. If nothing diverged, update the verification date in stage 00 provenance plus `last_verified` and `next_due` in `.playbook-maintenance.yml`. If something diverged, update those dates and open one dated analysis note that identifies the source version, affected stages, correctness risk, and proposed batch.

For every embedded reviewer, run `scripts/check-upstream-compatibility.py` against the
resolved installed `SKILL.md`. A compatible result requires an official report-only mode
and the exact recorded digest. An incompatible or changed result keeps the manual route;
do not promote it by editing the digest alone. Exercise compatibility changes in a
disposable repository before recording them.

Completion criterion: every installed upstream command named by the live playbook is accounted for as current, renamed with compatibility, optional, or removed; the source versions, behavioural verdicts, source digests, fallbacks, and next due date are recorded; and `python3 v0.5/scripts/check-upstream-drift.py` passes. That checker now validates the integration manifest as well as the due date.

An integration entry's `last_verified` is the date that exact installed source was audited
for embedded behaviour. It does not advance `.playbook-maintenance.yml`: that file records
the separate released/tagged-source comparison, which still runs monthly and before a
release containing an upstream contract change.

## Release lanes

Classify each upstream-driven change before assigning a playbook version:

| Lane | Trigger | Timing |
|---|---|---|
| **Correctness** | Current guidance would make an agent run the wrong loop, violate an invariant, or fail a required install | Ship the smallest safe correction immediately |
| **Maintenance batch** | Vocabulary, provenance, ergonomics, optional integrations, or several compatible small changes | Batch normally no more than weekly |

The changelog `Why` paragraph names the lane. An explicit human request to release overrides the suggested calendar timing, but not verification or release invariants.

## Per-release evidence

Run the public release-readiness suite and record its result with the release.
The private historical benchmark runs are not part of this repository or a
public release gate. Add a public benchmark only after its fixtures and outputs
have their own privacy review.

## Source authority

- Release page and tagged source define what users can install now.
- Upstream `main` is an early-warning source, not a released contract.
- Cached repository pages and raw CDNs are corroboration, never the sole basis for declaring a release present or absent.
- Local installed skill files define what the current host will actually execute; record a version mismatch rather than silently blending behaviours.
- `upstream-integrations.json` is the executable allowlist for embedded behaviour; package presence alone never proves compatibility.

## Skill-quality audit

When a local skill changes:

1. Apply the invocation and information-hierarchy rules in `skills/README.md`.
2. Run `python3 v0.5/scripts/check-skill-metadata.py`.
3. Run the canonical `python3 v0.5/scripts/verify-playbook.py` release-readiness command.
4. Review the skill's completion criteria, references, and guardrails against the changed behaviour.

The audit is complete when metadata and prose agree on invocation ownership, every branch has a checkable completion criterion, and conditional reference is behind a pointer rather than on every run.

# Cloud skill provisioning — implementation slices

Status: breakdown approved and seven child tickets published on 2026-10-24.
The [specification](spec.md) and both test seams are approved. S1–S3 are
implemented and independently verified at the approved fixture seam, including
returned fixes and fresh CLI QA. S2 preserves explicitly retained tracked
customizations and supports repeatable installation recovery. S3 preserves local
sources and explicitly selects them through existing binding authority. S4 exact
adopted-release recovery is implemented with isolated fixture evidence and awaits
fresh independent review. S5–S7 remain future work.
No actual runtime qualification has occurred.

Read the [alignment](alignment.md), [glossary](../../GLOSSARY.md), and
[accepted distribution decision](../../docs/adr/0002-release-bundled-project-skills.md)
with the spec. Installed, discoverable, compatible, and customized are distinct
states; no slice may collapse them into a single success flag.

## Approved order

AFK means implementation can proceed from the approved contract without another
product decision. HITL means the slice needs human participation. These labels
do not select a model, authorize a live run, or waive independent verification.

| Slice | Type | Blocked by | Demoable outcome |
|---|---|---|---|
| S1 — Provision the complete reviewed inventory | AFK | None | A project installs and checks the bundled inventory from an available verified source; a repeat run changes nothing. |
| S2 — Preserve customizations and recover installations | AFK | S1 | A project retains its own skill edits through setup and an approved inventory change, and can recover the previous managed installation. |
| S3 — Preserve and explicitly select local sources | AFK | S2 | Local setup reports existing skills without changing them; explicit adoption respects bindings and keeps the Cloud pin unchanged. |
| S4 — Recover the exact adopted playbook release | AFK | S1 | A consumer whose saved playbook path is absent can provision from the verified release it already adopted. |
| S5 — Adopt through bootstrap and upgrade | AFK | S3, S4 | A consumer previews and adopts provisioning through the existing migration flow, preserving its settings and content. |
| S6 — Activate Conductor setup | AFK | S5 | One shared setup entry restores Cloud skills and performs discovery only locally, including in this maintainer repository. |
| S7 — Qualify actual runtime discovery and invocation | HITL | S6 | Recorded live evidence supports the first rollout for both runtimes in fresh and recreated Cloud workspaces, plus local coexistence. |

S2 and S4 become independently grabbable after S1. S3 follows S2 because explicit
project-bundle activation uses its preservation and recovery behavior. S5 needs
both safe local choices and exact consumer recovery. S6 composes these behaviors
into host startup; S7 exercises that complete path. The table lists direct
blockers only. Suggested serial order: S1, S2, S3, S4, S5, S6, S7.

No separate prefactor is justified by the inspected code. Reuse the existing
registry reader, release provenance, migration preservation, and binding
contracts inside the slices that need them. Each slice includes its meaningful
tests and user-facing instructions; S7 supplies evidence only a real runtime
can establish.

## 1. Provision the complete reviewed inventory

**Type:** AFK. **Blocked by:** none. **Spec coverage:** A1, A3, A8, A9, A12.

**What it delivers:** Given an available verified release, a project can preview,
install, and inspect the complete reviewed inventory through one public
provisioning interface. Maintainer candidate testing identifies the candidate
without claiming consumer release provenance.

- Bundle the eleven selected upstream skill directories, supporting references,
  required dependencies, invocation metadata, and notices. Derive the inventory
  and integrity records from the existing registry and reviewed source pin.
- Preserve the existing playbook-owned installation. Validate all material
  needed for an affected capability before activating it; reject damaged or
  missing material with a precise repair action.
- Report actual source identity and separate installation from discovery and
  qualification. Retain user-invoked controls and the existing incompatible
  embedded-review verdict and stage-owned fallback.
- An unchanged rerun makes no installation changes. Unknown or conflicting
  project content is preserved and reported. Failed or interrupted activation
  leaves a repairable project and never reports a complete capability falsely.
- Once the verified release is available, provisioning needs no upstream skill
  download. Document monthly upstream review and checks before adopting source,
  runtime, model, or setting changes; ordinary provisioning never updates pins.

**Verification target:** Through approved test seam 1, provision a clean isolated
project, inspect complete package contents and source reports, and rerun with
no filesystem changes. Exercise missing support material, invalid metadata,
integrity failure, conflicting content, and interrupted initial activation.
Assert unaffected content survives and no real user home or configuration changes.

## 2. Preserve customizations and recover installations

**Type:** AFK. **Blocked by:** S1. **Spec coverage:** A3, A7, A8, A12.

**What it delivers:** Setup and an approved inventory change preserve explicitly
retained project customizations; a user can recover a previous managed
installation without erasing subsequent edits.

- Distinguish managed unchanged material, retained customized material, and
  unknown project files. Retained version-controlled content survives byte for
  byte and remains separately qualified.
- Support the prior-installation recovery operation on the same public boundary.
  Interrupted replacement retains enough evidence to resume or recover; a
  partial state cannot become a successful adoption stamp.
- Restoration preserves edits made after installation, reports conflicts with
  exact repair choices, and does not commit or upload VM-only changes.
- Keep unaffected capabilities available. Offer the existing manual fallback
  without selecting it implicitly; accepting a fallback does not repair or
  qualify the broken route.

**Verification target:** Using seam 1, change a managed inventory, retain a
tracked customization, interrupt replacement, and recover. Compare customized
and unknown files before and after, including an edit made after the prior
installation. Verify repeated recovery, incomplete-state reporting, and explicit
fallback selection behavior.

## 3. Preserve and explicitly select local sources

**Type:** AFK. **Blocked by:** S2. **Spec coverage:** A4, A5, A6, A8, A9.

**What it delivers:** A local user sees which sources already exist and can make
an explicit source choice without a setup hook replacing newer skills or
changing the Cloud inventory.

- Default local execution discovers and reports only: no skill writes,
  discovery-configuration changes, bundle activation, or user-wide changes.
- Report exact, newer, customized, missing, and duplicate sources relative to
  the reviewed baseline. Unknown versions remain unknown; version ordering is
  never an eligibility rule.
- Explicit newer-source adoption or project-bundle activation uses the existing
  owning-stage and binding rules. Reuse those rules rather than introducing
  another approval or version resolver. Do not manufacture qualification.
- Preserve alias deduplication and distinct-source collision behavior. A
  changed saved source or unresolved runtime command collision blocks that
  affected route and presents recovery; it never silently substitutes a source.
- Record the chosen route and require actual invocation-source evidence before
  claiming runtime resolution. Fixture evidence remains synthetic until S7.
  Local selections do not implicitly change the Cloud pin.

**Verification target:** Seam 1 covers exact/newer/customized/missing/duplicate
sources, an alias of the same source, and a selected source that later changes.
Compare isolated home and skill configuration snapshots before and after
discovery. Exercise explicit adoption and project activation using retained
binding fixtures; assert rejection of ineligible review and unchanged Cloud
adoption. Actual local runtime resolution is an S7 acceptance gate.

## 4. Recover the exact adopted playbook release

**Type:** AFK. **Blocked by:** S1. **Spec coverage:** A1, A2, A8, A10.

**What it delivers:** A consumer can run the public provisioning interface when
its configured playbook path exists only on another machine, using exactly its
already adopted release.

- Reuse a clean available checkout only when it matches the recorded release's
  annotated tag object and commit under the existing provenance contract.
- Otherwise acquire that exact release, validate it before activation, and
  provision its bundle. Do not select the newest tag or substitute a candidate.
- Missing proof, changed tags, wrong commits, modified source, and unavailable
  acquisition produce precise recovery actions. An old release without the
  bundle requires explicit upgrade; recovery never performs the upgrade.
- Keep acquired source separate from project customizations and leave unrelated
  project capability usable when acquisition fails.

**Verification target:** Seam 1 uses isolated Git release fixtures and a consumer
with an absent saved path. Test exact acquisition and local reuse, missing
proof, moved annotated tag, wrong commit, dirty checkout, absent bundle, and
offline failure. An available verified release succeeds without an additional
upstream skill request; failed acquisition does not alter adoption.

## 5. Adopt through bootstrap and upgrade

**Type:** AFK. **Blocked by:** S3, S4. **Spec coverage:** A7, A9, A10, A12.

**What it delivers:** A new or existing consumer deliberately adopts an inventory
through bootstrap or explicit upgrade, then can replay it through the public
provisioner.

- Extend the existing preview and approval boundary with the selected inventory,
  release provenance, local discovery policy, customization treatment, and
  recovery implications. Preview alone does not install or change adoption.
- Preserve existing consumer content, settings, job bindings, and setup work.
  Withhold the new completion stamp while required migration review or a
  preservation conflict remains unresolved.
- Preserve existing playbook-owned skills, and keep old consumers unchanged
  until they explicitly adopt a release with the bundle. No fleet migration.
- Keep committed adoption portable and separate from machine-local source
  choices. Preserve the maintainer-checkout exception; this repository must not
  acquire synthetic consumer state.
- Integrate upgrade guidance with monthly maintenance and compatibility review,
  including how a newer local choice can be reviewed independently of the Cloud
  baseline. Automatic host startup integration follows in S6.

**Verification target:** Seam 1 runs bootstrap preview/apply and upgrade
preview/apply on clean and customized fixtures. Replay the adopted inventory;
exercise an older release and unresolved review; verify preserved settings,
bindings, content, and existing setup. Confirm no stamp advances on failure and
no consumer state is created for the maintainer path.

## 6. Activate Conductor setup

**Type:** AFK. **Blocked by:** S5. **Spec coverage:** A1, A3, A4, A7, A8, A10.

**What it delivers:** A Conductor workspace's shared setup runs the adopted
provisioner in Cloud and performs discovery only locally. Enable it first in
this maintainer repository and expose it through deliberate consumer adoption.

- Compose the hook with existing setup commands; do not replace or discard
  them. Dispatch from actual host environment evidence rather than guessing
  from filesystem paths or whether a home directory happens to contain skills.
- Preserve Cloud noninteractive setup and the documented local shell behavior.
  Define an actionable result when host environment or required source is
  unavailable, preserving a workspace the user can repair.
- Cloud startup replays adoption; local startup changes no skills or discovery
  configuration. Preserve customizations and report unresolved routes precisely.
- Maintainer setup identifies the development candidate and uses the same
  provisioner without inventing a consumer release or running bootstrap.
- Document Cloud creation-branch activation and local default-branch activation
  requirements. State that fixture success does not qualify either runtime.

**Verification target:** Seam 1 runs setup composition and both environment
branches with isolated project/home fixtures, pre-existing setup work, repeated
runs, and failures. Verify local non-mutation, Cloud bundle restoration,
preserved setup side effects, and the maintainer exception. Live host behavior
is verified in S7.

## 7. Qualify actual runtime discovery and invocation

**Type:** HITL. **Blocked by:** S6. **Spec coverage:** A1–A12, especially A6, A9, A11.

**What it delivers:** Maintainers have actual runtime evidence for the supported
rollout, with every unverified or failing route clearly identified.

- Before execution, establish host access, exact candidate identity, runtime
  versions, approved live-run ceilings, and explicit invocations for skills
  that require them. These are execution prerequisites, not new scope decisions.
- Complete the fresh/recreated Conductor Cloud × Claude Code/Codex matrix from
  approved seam 2. Verify the full inventory's discovery, selected sources,
  appropriate explicit invocations, dependency/reference access, and invocation
  policy. Recreated sessions must restore a retained tracked customization.
- Complete local coexistence checks in both runtimes: exact, newer, customized,
  absent, duplicate, and changed-selected sources; prove default non-mutation
  and actual invocation after explicit selection. Do not run an incompatible
  embedded reviewer; verify its refusal and selected stage fallback instead.
- Use disposable tasks suited to each skill's effects. Record runtime versions,
  source identity, failures, repair, and evidence without publishing personal
  paths, credentials, or private-project records. Carry the tested versions
  into the maintenance/requalification guidance.
- If access, a required invocation, or a matrix cell is unavailable, retain it
  as pending and make no support claim for it. Fix in-scope failures and rerun
  affected checks; local fixtures never stand in for actual runtime evidence.

**Verification target:** Approved seam 2 supplies the runtime evidence. Complete
fresh independent cross-slice review and the shipping gates on the final
candidate: relevant checks, attribution/privacy, changelog with a Why line,
regenerated manifests, and the canonical full verifier. Follow the existing PR
and release workflow; this breakdown does not authorize a merge or release.

## Coverage and advancement

| Criteria | Implementation slices | Actual-runtime confirmation |
|---|---|---|
| A1, A2 — Complete Cloud inventory and exact release recovery | S1, S4, S6 | S7 |
| A3, A7, A8 — Repeatability, preservation, repair | S1, S2, S4, S6 | S7 |
| A4, A5, A6 — Local coexistence and selected source | S3, S6 | S7 |
| A9 — Invocation and stage ownership | S1, S3, S5 | S7 |
| A10 — Deliberate consumer migration | S4, S5, S6 | S7 |
| A12 — Controlled future maintenance | S1, S2, S5 | S7 |
| A11 — Supported-runtime evidence | S7 | S7 |

Published one child issue per slice to the configured tracker in dependency
order. Readback confirmed all parent links, native blocking relationships,
and readiness labels. AFK slices are agent-ready and S7 is human-ready. The
parent's description and status were not edited. S1 is selected first because
it has no blockers and supplies the public boundary used by all later slices;
its ticket includes the spec criteria and approved test seam.

The selected Build and fresh Verify runtimes were identity-verified for S1–S3.
Those slices passed independent standards/spec review and CLI QA, including fresh
verification of returned fixes, and are complete. S4's portable public launcher
reuses the recorded adopted proof and existing provisioner. Isolated fixtures
cover clean offline reuse, exact acquisition despite a newer remote release,
missing/ambiguous proof, moved tag, wrong commit, dirty source, absent bundle,
offline failure, cache drift and preservation of conflicting project edits.
Fresh independent S4 standards/spec/adversarial/CLI review remains required.
S5–S7 are pending; actual runtime invocation remains unverified. Ordinary build
checkpoints, cumulative retry guards, independent verification, and the stage-06
architecture cadence still apply.

```yaml
playbook_result:
  outcome: fourth_slice_awaiting_independent_review
  next_stage: "08"
  required_actions:
    - Independently review the frozen S4 candidate before accepting or committing it.
    - Continue the approved batch only through coordinator dispatch after the slice commit.
    - Retain actual runtime qualification as pending until S7 evidence exists.
```

# Cloud skill provisioning — specification

Status: specification and both test seams approved by the human on 2026-10-24.
Alignment and the [implementation slices](slices.md) are accepted.
S1–S4 are implemented and independently verified at the approved fixture seam,
including returned fixes and fresh CLI QA. S5 bootstrap/upgrade inventory adoption
is implemented with isolated fixture evidence and awaits fresh independent review.
S6–S7 remain future work; no live runtime qualification has occurred.

Sources: [alignment](alignment.md), [domain glossary](../../GLOSSARY.md),
[ADR 0002](../../docs/adr/0002-release-bundled-project-skills.md).

## Problem statement

A fresh cloud workspace lacks the upstream skill inventory available on a
developer's machine. The current bootstrap installs playbook-owned skills but
does not provision the selected upstream skills and their supporting material.
Copying files alone cannot establish which source Claude Code or Codex invokes,
whether that source meets the owning stage's contract, or whether customized
files survive recreation. Local workspaces need to retain their existing skills,
including newer upstream versions, without a cloud setup hook silently changing
their selected source.

## Desired behavior

Provide a reusable project-scoped provisioner. Cloud setup restores the project's
adopted inventory from its verified playbook release; local setup discovers and
reports existing sources by default. Adoption belongs to bootstrap or explicit
upgrade, while ordinary workspace setup repeats that decision. Enable the first
rollout in this maintainer repository and qualify Conductor Cloud with Claude
Code and Codex. Maintainer candidate-source testing remains distinct from
consumer release verification.

Bundle the eleven agreed upstream skills, alongside the existing playbook-owned
installation: `grill-with-docs`, `grilling`, `domain-modeling`, `to-spec`,
`to-tickets`, `tdd`, `codebase-design`, `diagnosing-bugs`, `code-review`,
`setup-matt-pocock-skills`, and `writing-for-agents`. Include complete selected
directories, referenced supporting files, required skill dependencies,
invocation metadata, and notices. Source identity comes from the existing
registry; the initial reviewed Matt package is v1.3.1 at commit
`24fe0ef7737efae15c87225755e9f6f5965e4888`.

## User stories and acceptance criteria

| ID | User story | Acceptance criterion |
|---|---|---|
| A1 | As a Cloud user, I want the adopted skills ready in a fresh workspace. | The setup hook installs the complete inventory from the adopted release and reports each source; no separate upstream skill download occurs once that release is available. |
| A2 | As a consumer, I want setup to work when my configured playbook path belongs to another machine. | Recovery acquires only the recorded release and verifies its annotated tag object and commit before using it. Missing proof, mismatch, or unavailable source reports a repair action without silently choosing another release. |
| A3 | As a user, I want rerunning setup to be safe. | An unchanged second run makes no installation changes. An interrupted or failed install retains a repairable workspace, never reports partial success as a complete capability, and supports recovery to the previous installation. |
| A4 | As a local user, I want my installed skills preserved. | Default local setup reports existing sources and changes no skill files or discovery configuration. It does not activate a bundled duplicate, upgrade, downgrade, or modify user-wide settings. |
| A5 | As a local user with newer upstream skills, I want an informed adoption choice. | Report the actual source and its difference from the reviewed baseline. Reuse requires the owning stage's rules and any saved binding to pass. Newer-source adoption and project-bundle activation require explicit selection; neither changes the cloud pin implicitly. |
| A6 | As a user, I want the source I selected to be the source that runs. | Detect duplicate identities, changed saved sources, and runtime name collisions. Verify actual invocation source for the selected route; do not infer it from file presence, scope, name, or version. An unresolved affected route does not run silently. |
| A7 | As a project owner, I want my customized skills to survive recreation. | Preserve explicitly retained version-controlled project files byte-for-byte, identify customized source, and qualify it separately. Explain that VM-only edits are ephemeral; never automatically commit or upload them. |
| A8 | As a user, I want failures to leave useful work possible. | Identify the affected capability and precise repair, retain usable workspace access, and require explicit selection before using the existing manual fallback. Unaffected capabilities remain usable. |
| A9 | As a playbook user, I want stage and invocation controls preserved. | Preserve both runtimes' user-invoked metadata and supporting files. Installation grants no stage eligibility, model selection, commit authority, or embedded-review approval. The current incompatible `code-review` source retains its stage-owned fallback. |
| A10 | As a consumer, I want a deliberate migration. | Bootstrap and upgrade preview the adoption, preserve existing setup/configuration and custom content, and withhold completion while required review is unresolved. A release lacking the bundle requires explicit upgrade. Existing consumers are not upgraded as a fleet. |
| A11 | As a maintainer, I want support claims backed by actual runtime evidence. | Fresh and recreated Conductor Cloud workspaces pass discovery and explicit invocation checks for both Claude Code and Codex. Local coexistence checks establish the actual invoked source. Local fixtures alone cannot satisfy these criteria. |
| A12 | As a maintainer, I want future updates to remain controlled. | Monthly maintenance compares upstream changes; adoption of source, runtime, model, or setting changes checks affected compatibility, preserves customizations and recovery, and records the tested versions. Startup itself never updates pins. |

## Scope and implementation boundaries

- Keep one inventory authority: the existing upstream registry and its reader.
  Bundle integrity records may be derived from that inventory; they must not
  become an independently maintained skill catalog.
- Introduce one project-provisioning boundary that can report a plan, apply an
  adopted inventory, check installed state, and recover the previous managed
  installation. Exact CLI spelling and on-disk transaction layout are routine
  implementation choices, subject to the behavioral criteria above.
- Reuse existing release-provenance, bootstrap/upgrade preservation, and skill
  binding/compatibility contracts. Do not create a second approval or version
  resolver. A passed file-integrity check and a passed runtime/stage capability
  check remain different observations.
- Report installed, discoverable, compatible, customized, missing, and ambiguous
  states accurately. Unknown version or qualification remains unknown. Machine
  reports identify the source and required recovery without leaking personal
  paths or credentials into tracked records.
- Conductor's shared setup dispatches by actual environment. Cloud uses the
  adopted provisioning path; local uses discovery by default. Preserve existing
  setup work when adding this hook. Consumers' committed adoption contains no
  dependency on the maintainer's machine or personal installation.
- Determine which commands and dependencies the runtime resolves, not just the
  entry skill. User metadata and supporting-file lookup must survive copies,
  directory aliases, and recreation. Distinct copies that claim one saved
  identity remain subject to the existing collision rules.
- Validate the source before activation. Preserve project-owned and unknown
  files and retain sufficient evidence to repair interrupted work. Restoration
  must not erase customizations made since the previous install.

## Approved test seams

Use two high-level seams, with focused tests of reused helpers only where their
behavior changes. Assertions concern user-visible outcomes and filesystem
preservation, rather than mirroring internal helper calls.

### 1. Provisioner and adoption interface

Exercise the public commands against isolated temporary projects, homes, and
Git release fixtures. Use the existing bootstrap/upgrade fixture style and
release-provenance and binding tests as prior art. Cover:

- Fresh install and unchanged rerun; all selected support files, metadata, and
  notices present with the expected source identity.
- Verified local release reuse, exact-release acquisition, absent proof, moved
  tag, wrong commit, modified source, missing bundle, and offline acquisition
  failure. An already verified available release requires no extra upstream
  skill download.
- Local discovery with exact, newer, customized, absent, and duplicate sources;
  an unchanged home directory and skill configuration after discovery.
- Explicit local adoption, a selected source changing afterwards, existing
  bindings, and preservation of the cloud pin.
- Project customizations across reruns and upgrades, interrupted activation,
  partial failure, prior-installation recovery, and actionable diagnostics.
- Bootstrap/upgrade preview and preservation, existing setup composition, local
  versus cloud dispatch, and no consumer-state creation in this maintainer repo.

### 2. Actual runtime invocation

| Venue | Required evidence |
|---|---|
| Fresh Conductor Cloud / Claude Code | Complete discovery inventory, actual selected source, explicit invocation, supporting-file access, and invocation policy. |
| Recreated Conductor Cloud / Claude Code | The same behavior restored from adopted source, including an explicitly retained project customization. |
| Fresh Conductor Cloud / Codex | Complete discovery inventory, actual selected source, explicit invocation, supporting-file access, and invocation policy. |
| Recreated Conductor Cloud / Codex | The same behavior restored from adopted source, including an explicitly retained project customization. |
| Local Claude Code and Codex | Existing exact/newer/customized sources, same-name collisions, explicit selection, and later source drift; confirm default setup causes no installation changes. |

Use disposable qualification tasks appropriate to each skill's allowed effects.
Record runtime versions, candidate or release identity, inventory source,
observations, failures, and recovery. Do not execute an incompatible embedded
reviewer merely to test it; verify the refusal and stage-owned fallback instead.
No automatic invocation is permitted for a user-invoked skill.

Before live runs, establish actual host access and the approved qualification
ceilings required by the playbook. No cloud workspace or paid run has been
created during planning. If the venue is unavailable, retain a pending result;
do not replace it with simulated evidence or claim support.

## Out of scope

- Other cloud hosts or agent runtimes in the first rollout.
- Provisioning the entire upstream catalog, automatic upstream `implement`, or
  changing the existing embedded-compatibility verdicts.
- Global skill installation, automatic local upgrade/downgrade, automatic
  consumer migration, or a universal newest-version selector.
- Automatically publishing personal skill edits or runtime evidence containing
  private paths, credentials, or project records.
- Changing model, stage, review, commit, or approval ownership.

## Scope and coherence review

Scope-guardian: retain one provisioner, the existing registry, and existing
adoption and compatibility boundaries. The local behavior protects existing
workspaces affected by the shared hook; it is not a separate skill marketplace
or package manager. No additional runtimes, automatic updater, or new approval
framework is required.

Coherence: installed, discoverable, compatible, and customized retain the
glossary's distinct meanings. Local discovery-first behavior and pinned cloud
provisioning coexist because source adoption is explicit. Exact recovery never
upgrades an older release; maintainer candidate testing never stamps a consumer
release. Separate runtime evidence prevents a file-copy result being reported
as qualified support.

## Remaining review and execution gates

The scope decisions, specification, test seams, and stage-04 breakdown are
accepted. Child tickets are published and S1 is selected for implementation.
No new product decision is outstanding.
Runtime access, concrete qualification ceilings, and live results are execution
prerequisites, not assumed facts. Shipping additionally requires independent
review, the changelog Why line, regenerated manifests, privacy/attribution
checks, and the full verifier on the final candidate.

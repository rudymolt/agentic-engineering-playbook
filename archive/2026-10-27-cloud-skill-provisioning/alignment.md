# Cloud skill provisioning — alignment

Status: alignment settled on 2026-10-24. The human confirmed the consolidated
cloud scope and subsequently accepted the local discovery-first recommendation.
No design decisions remain open. The [specification](spec.md) is written for
review; implementation and cloud qualification have not begun.

## Confirmed scope

- First rollout: Conductor Cloud with Claude Code and Codex.
- A reusable project-scoped provisioner; initial activation in this playbook
  repository, with consumer adoption through bootstrap or explicit upgrade.
- Selected upstream skills: `grill-with-docs`, `grilling`, `domain-modeling`,
  `to-spec`, `to-tickets`, `tdd`, `codebase-design`, `diagnosing-bugs`,
  `code-review`, `setup-matt-pocock-skills`, and `writing-for-agents`.
- Include each selected skill's supporting files, invocation metadata,
  dependencies, and license. Keep the existing playbook-owned skill installation.
- Use reviewed pins, preserve customized files, and retain recovery to the
  previous installation. Do not implicitly upgrade consumers or global settings.
- Check upstream changes through the existing monthly maintenance cadence;
  validate compatibility before adopting source or runtime changes.
- Require actual discovery and explicit invocation evidence from fresh and
  recreated cloud workspaces for both supported runtimes.
- Preserve user-invoked policies and existing stage/model/approval ownership.
  Installed `code-review` remains subject to its embedded compatibility verdict
  and the stage-08 fallback.

## Route and evidence

The human explicitly invoked `/grill-with-docs` to test alignment. Its installed
instructions load `/grilling` and `/domain-modeling`; both instructions and the
glossary/ADR formats were read through the filesystem because this host exposes
no dedicated skill loader. No model switch was requested or performed.

This maintainer checkout uses its live edition source. It intentionally has no
consumer state file, as recorded in [the planning index](../STATUS.md).
The alignment job resolver returned `configured: false`; no adopted binding
was bypassed. Relevant project, user and runtime skill sources were inspected;
the local alignment skill is present, so this is not a missing-skill fallback.

Verified source facts:

- [Bootstrap](../../v0.5/scripts/bootstrap-project.py) installs registry-owned
  local skills and the delivery skill, but does not provision the selected
  upstream package.
- [The registry](../../v0.5/upstream-skills.json) pins Matt's skills at v1.3.1,
  commit `24fe0ef7737efae15c87225755e9f6f5965e4888`.
- Pinned `grill-with-docs` loads `grilling` and `domain-modeling`. The latter
  needs its glossary and ADR format references. TDD also refers to
  `codebase-design` and `code-review`.
- [Consumer instructions](../../v0.5/templates/AGENTS.md) refer to a configured
  playbook path. The bootstrap command itself requires a playbook path, so
  provisioning cannot assume a checkout from a different machine exists.
- [The compatibility manifest](../../v0.5/upstream-integrations.json) marks
  upstream `implement` and `code-review` as embedded-incompatible.
- Runtime discovery documentation identifies repository skill locations for
  [Codex](https://learn.chatgpt.com/docs/build-skills) and
  [Claude Code](https://code.claude.com/docs/en/skills). These documents support
  the proposed discovery wiring, not a claim of completed cloud qualification.
- [Conductor setup](https://conductor.build/docs/reference/scripts/setup)
  provides the project setup hook. No cloud provisioning or live runtime
  qualification has been performed during alignment.

## Accepted decisions — round 1

The human accepted all four recommendations on 2026-10-24.

1. **Recover the playbook checkout:** Cloud setup may acquire the consumer's
   exact adopted playbook release when its configured path is absent. Verify
   the recorded annotated tag object and commit before using it. Never select
   a newer release automatically; missing provenance requires an explicit
   recovery or adoption decision.
2. **Distribute the skill files:** Bundle the reviewed skill directories,
   invocation metadata, dependencies, and notices with the playbook release.
   Installing that inventory needs no separate upstream download once the
   release is available.
3. **Persist customizations:** Support explicitly retained project-owned skill
   files in version control. Preserve them during provisioning and qualify
   their actual source separately. Explain that changes confined to an
   ephemeral workspace do not survive recreation; never silently commit or
   upload them.
4. **Failure behavior:** Retain a repairable workspace and fail the affected
   capability with a precise diagnosis and recovery action. Require an explicit
   choice of the existing manual fallback. Unaffected work may continue.

## Consequences checked against the existing contracts

- Recovery reuses the exact-release contract in
  [release provenance](../../v0.5/scripts/release_provenance.py): a clean
  checkout, matching annotated tag object, and matching commit. An edition
  label, directory name, or available newer checkout is insufficient proof.
  A previously adopted release without the bundle needs explicit upgrade
  before it can provide this capability.
- The maintainer development checkout and a consumer's adopted release have
  distinct ownership. This repository can qualify its candidate source before
  release; that evidence must not stamp it as a published consumer release or
  create consumer state in the maintainer checkout.
- Bootstrap and upgrade remain the adoption boundaries. The existing
  [upgrade tiers](../../v0.5/skills/ai-playbook-upgrade-project/SKILL.md)
  preserve project-owned files and withhold completion while required manual
  review is unresolved. A successful file copy cannot certify an unresolved
  customization, name collision, or incompatible embedded skill.
- Monthly upstream maintenance proposes reviewed pin changes. Before adopting
  changed skill source, runtime behavior, models, or settings, check the
  affected discovery, invocation policy, stage ownership, and customization
  compatibility. Retain recovery to the previous installation; workspace
  creation itself is not an upgrade event.
- The selected inventory comes from the existing registry through
  [its reader](../../v0.5/scripts/upstream_registry.py). Bundling does not
  introduce a second source of truth or broaden the first rollout to other
  packages or runtimes.

## Qualification boundary

| Runtime | Fresh Conductor Cloud workspace | Recreated Conductor Cloud workspace |
|---|---|---|
| Claude Code | Pending live discovery and explicit invocation evidence | Pending live discovery and explicit invocation evidence |
| Codex | Pending live discovery and explicit invocation evidence | Pending live discovery and explicit invocation evidence |

Evidence must identify the actual runtime and version, source revision,
discovered inventory, invocation policy, and required supporting-file access.
Customized source must be distinguished from the reviewed bundled source.
Local provisioner tests and documentation checks support qualification but do
not replace these cloud observations. Repair, rerun, and previous-installation
recovery also need verification during implementation.

## Accepted decision — local coexistence

The human confirmed the preceding scope, then asked what happens in local
workspaces with existing upstream skills, especially newer versions. The human
accepted the following recommendation on 2026-10-24.

Verified facts:

- [Claude Code's name-resolution rules](https://code.claude.com/docs/en/skills#resolve-skills-that-share-a-name)
  give personal skills precedence over project skills with the same command
  name. Copying a pinned project skill cannot guarantee that command runs it.
- [Codex discovery](https://learn.chatgpt.com/docs/build-skills) permits both
  same-named skills to appear in selectors; it does not merge their contents.
  Neither runtime's documented behavior is a newest-version selection policy.
- Stage 00 already discovers project, user, and runtime-advertised skills.
  [Saved job bindings](../../v0.5/scripts/skill-bindings.md) reject distinct
  sources claiming one identity and reject changed saved sources. The
  [embedded reviewer check](../../v0.5/scripts/check-upstream-compatibility.py)
  requires the exact audited source and a compatible verdict. A newer source
  does not inherit that verdict. These specific gates must not be described
  as an implemented universal version resolver for every skill.

**Accepted policy:** local setup discovers and reports
existing sources by default, without automatically activating bundled
duplicates or changing user installations. Reuse an existing source only when
it satisfies the owning stage's discovery, invocation, and compatibility
requirements, including any saved binding. A newer source is preserved and
reported as differing from the reviewed baseline; its version alone does not
prove compatibility or justify a downgrade. Project bundle activation or
adoption of newer source is explicit, with source selection and collision
handling verified for the actual runtime. If the selected source cannot be
resolved or qualified, report the affected capability and offer the existing
explicit fallback. Local installation choices do not change the cloud pin.

This adds local non-regression cases to qualification: existing exact source,
newer source, customized source, name collisions, and a later change to a
previously selected source. Live evidence must prove which source is invoked;
finding files on disk is insufficient. It does not broaden the cloud runtime
matrix or change the already accepted distribution decision.

## Durable records

The agreed availability distinctions are recorded in [the glossary](../../GLOSSARY.md).
[ADR 0002](../../docs/adr/0002-release-bundled-project-skills.md) records the
accepted distribution and ownership tradeoff. It records the decision, not
completed implementation or qualification.

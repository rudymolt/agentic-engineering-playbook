# Project skill provisioning

The public `provision-skills.py` command discovers local sources and explicitly
previews, installs, checks, and recovers the
reviewed project inventory from an available Playbook checkout. Its selected
skills and dependencies come from [the registry](../upstream-skills.json), read
through [upstream_registry.py](upstream_registry.py). The initial bundle contains
eleven complete Matt Pocock skill directories from v1.3.1, commit
`24fe0ef7737efae15c87225755e9f6f5965e4888`, annotated tag object
`0b6cee10f260a2e048279cf737bfd3e37b1fce0b`. The
[bundle record](../bundles/mattpocock-skills/integrity.json) binds all packaged
bytes, invocation metadata, supporting files, and dependency declarations.

## Consumer commands

Use the previously verified release tag, annotated tag object, and commit from
the adopted release record. The existing [release checker](release_provenance.py)
requires the available source checkout to be clean at exactly that identity.
The command never acquires a checkout or upgrades an adoption.

```sh
python3 "$PLAYBOOK_PATH/v0.5/scripts/provision-skills.py" \
  --source "$PLAYBOOK_PATH" --project "$PROJECT_PATH" \
  --release "$PLAYBOOK_RELEASE" --tag-object "$PLAYBOOK_TAG_OBJECT" \
  --commit "$PLAYBOOK_COMMIT" preview
```

Omit the final action, or use `discover`, for read-only local discovery.
Change the final action to `install` for explicit project activation, or `check`
to inspect installed state. Preview and check write no project files. An install
with identical content changes no files. Omitting all three proof arguments
requests the existing public-tag provenance check; partial or mismatching proof
blocks. A release without the bundle needs an explicit release upgrade.

The commands emit JSON. Exit 0 means a successful discovery report, preview, completed install,
complete installation check, explicit retention, recovery, or fallback report. Exit 2 means a blocked operation, partial install, or incomplete
check. A successful discovery report may contain blocked jobs; inspect their
individual results. Discovery keeps `complete: false` because it does not assess
installation completion. For the other actions, `complete` describes file installation only. Per-skill reports contain
expected integrity hashes, actual installed hashes when readable, source
identity, invocation mode, dependencies, and compatibility/fallback observations.
Unretained conflicting bytes have unknown upstream identity; explicitly retained
customizations report `project-customization` and their actual integrity. Discovery and
qualification remain `unverified`, including when all files are installed.
Reports may identify local failure paths; retain runtime reports privately.

Installation writes only beneath the selected project's `.agents` directory.
Existing playbook-owned skills and unrelated content remain intact. Every skill
copy includes the unchanged upstream MIT LICENSE. Claude's explicit-invocation
frontmatter and Codex's explicit-invocation policy remain as upstream supplied
them. Installation grants no model, stage, review, invocation, or commit authority.
The bundled `code-review` source remains embedded-incompatible; its report names
the existing stage-08 manual standards/spec fallback. Selecting that fallback
remains stage-owned.

## Local discovery and explicit source choice

`discover` is the default action. With the same verified source proof (or
`--candidate` for maintainer fixtures), it reads only the registry's relevant
project and user skill roots. It never installs a bundled duplicate, rewrites
skills, changes discovery configuration, creates consumer state, or writes to
user-wide settings. Complete-directory aliases resolving to the same source count once;
distinct source paths remain duplicates even when their bytes match. An
individual `SKILL.md` link is unknown/blocked: discovery never treats its
target parent as the complete skill directory or reads unrelated siblings.

`local_sources` reports the actual resolved source paths, complete readable
file integrity and differences from the reviewed bundle, registry invocation
policy, and independent version observations:

- `exact`: complete directory bytes, including the notice, match the bundle.
- `newer`: differing material comes from a clean source directory at a Git
  descendant of the recorded reviewed commit. This is ancestry evidence, not a
  semantic-version eligibility rule. An exact HEAD tag supplies `version`;
  absent tags and unproven ancestry leave version unknown.
- `customized`: material differs from the reviewed baseline and is not a clean,
  proven successor. Added, missing and changed files are listed. This describes
  the observed difference; it does not establish who authored it or assert an
  upstream version. A dirty newer source retains its separate revision report.
- `missing`, `duplicate`, or `unknown`: no source, multiple distinct sources,
  or unreadable/linked material respectively. Named missing entrypoints,
  cyclic/dangling directories and access errors stay visible as unknown sources;
  they never become ordinary absence or disappear beside a readable competitor.
  Supporting-directory enumeration failures also make the source unknown; an
  omitted subtree is never reported as missing files in a completed observation.
  Restore file-read and directory-enumeration access before retrying.
  Duplicates and unknown material carry explicit repair instructions. Preserve
  them for inspection; unaffected capabilities keep their own observations.

The source paths are private runtime diagnostics: never commit or publish the
raw report. Version labels from a skills CLI lock, timestamps, directory names,
or the bundle's own pin are not proof of an installed source's version. The
Git observation disables repository-configured fsmonitor helpers and optional
index writes through process-local overrides; it never rewrites Git settings.
The status probe includes ignored local material. These protections apply to
both source provenance checks and installed-source observations. No upstream fetch or version selection takes place.

`job_options`, `job_rejections`, and `job_routes` come from the existing
[binding catalog and Configure boundary](skill-bindings.md). They show eligible
choices and the existing saved route, including changed, colliding, missing or
incompatible selections. The provisioner neither creates audits nor saves a
replacement. Inspect blocked jobs independently; unrelated routes keep their
own outcome. All routes remain `launched: false`; `runtime_resolution` and
qualification stay `unverified` until actual source/invocation evidence exists.

To choose a newer or customized source, have its owning stage independently
qualify the exact source under the existing retained-audit contract. Then use
Configure's `Edit skills <job>`, `Choose <number>`, preview, and explicit `Apply`.
Use the same external `--custom-bindings-dir` for Configure, discovery and
`job-route` when the retained store is not in its default location. Configure
records the existing portable binding and exact fingerprints; local paths stay
in the external store. Source drift or an unresolved same-command competitor blocks the selected job
without rewriting that choice, including an associated retained custom binding. Restore its recorded source/audit, or explicitly preview and Apply
an eligible manual/adapter fallback. Mere discovery selects no fallback.

To activate the project bundle, explicitly select the existing `install` action
in that project. It retains the preservation/recovery behavior below and never
adopts a job binding. Rediscover afterwards: a user copy plus a project copy is
still a collision until explicitly reconciled under the owning stage's rules.
Project activation and local binding selection do not change the consumer
release, Cloud inventory or pin. The current upstream `code-review` remains
embedded-incompatible even when exact and uniquely installed; choose its
stage-08 manual/adapter fallback explicitly. The dated qualification below records the selected runtime paths and their
limits; no general default-precedence or embedded-eligibility claim follows.

## Preservation and explicit retention

All bundle material is validated before activation. Missing material, altered
hashes, invalid metadata, or missing dependencies block activation. The provisioner
distinguishes exact installed bytes (`installed`), unchanged managed bytes from a
previous inventory (`update_available`), explicitly retained committed project
bytes (`customized`), missing directories (`missing`), and unknown or later
unretained edits (`conflict`). Preview and check report these states without writes.
A content conflict in a skill with no recorded installation withholds only that
skill: its directory stays untouched while
all unaffected skills install with their support files, LICENSE and invocation
metadata. The overall `install` and `check` results remain `complete: false` with
exit 2. Each conflicting row names `retain --skill NAME` or moving the edit aside;
withheld content is never reported as installed. After that explicit repair,
rerun `install` to complete the inventory. This isolation does not relax bundle
validation, unsafe-parent refusals or the refusal for a retained skill absent
from the registry. A later edit to an already installed skill instead refuses the
install and keeps the installation history unchanged, so `recover` still restores
the previous installation; the other installed skills remain available.

Unchanged reruns preserve file bytes, modes and modification times. Unrelated skills,
including playbook-owned skills, remain intact.

To retain a project customization, review and commit its complete skill directory
in the destination project's Git repository yourself. Then use the same source
proof arguments as above with the final action `retain --skill NAME`. Retention
requires the actual complete directory to match committed HEAD bytes; staged-only,
untracked, and later working-tree changes are preserved but rejected. The
unchanged upstream LICENSE and registry invocation controls remain required.

Retention writes `.agents/.skill-provisioning/retained.json`, containing relative
skill identities, integrity hashes, and the source on which the customization was
based. Review and commit this portable record yourself along with the retained
skill files so a recreated checkout carries the explicit choice. The provisioner
never commits or uploads them. VM-only edits remain ephemeral. Keep local
`state.json` and `work/` out of version control; they contain installation history
and working copies, including any retained project bytes. A retention record is
not a second inventory or a consumer adoption stamp: the registry still selects
the inventory and the existing adoption boundary still selects its source.

A subsequent explicit install preserves validated retained bytes even when the
approved inventory changes. A recreated project replays the tracked customization
and retention record against the same public interface. Changes after retention
require another deliberate commit and retain operation, or restoration of the
recorded bytes. Customized source stays separately unqualified; it never inherits
embedded compatibility from the bundle. The bundled `code-review` refusal and its
existing stage fallback remain in force.

## Replacement and recovery

An explicit install replaces only unchanged managed content. Each complete skill
is staged outside the discovery root, and `.agents/.skill-provisioning/state.json`
records the current installation, previous bytes/source, and pending transaction
before activation. Preview/check never create this record. S1 installations with
no history can be recognized only by exact bundle bytes; inspect and install from
their original verified source once to establish history before changing inventory.
Partial installation records contain only the managed skills in that transaction;
withheld directories are excluded from both its target and recovery inventory.
Repeating the same partial installation writes nothing, including its history.
History is local recovery evidence and grants no release or runtime authority.

A terminated process may leave complete skill directories, a renamed previous
copy, and staging under `.agents/.skill-provisioning/work/`. A pending transaction
always reports `complete: false`, even if the destination bytes already match.
For a pending install, use the identical source and `install` to resume, or
select `recover` to restore the installation from before that install. For a
pending recovery, retry `recover` to finish restoring its original saved target;
the interrupted recovery's starting installation never becomes the retry target.
After a completed replacement, `recover` restores the previous installation.
Recovery is repeatable and preserves valid retained customizations, including
ones deliberately retained since replacement. Retrying an interrupted rollback
of a pending install keeps that install's original recovery target as well.
Initial-install recovery returns the managed skills to their preceding
empty/missing inventory; any withheld project directories remain untouched.

Recovery reports `recovery_complete` separately from `complete`: restoring an older
installation need not match the currently requested source. `recovered_source`
names the restored source evidence; no adoption record changes. An unchanged
repeat recovery performs no writes; the exception is a recovery that rolled back
an interrupted completion, after which the next `recover` returns to the original
recovery target. Use an available verified source when
recovering an installation, or explicitly recover that exact source with the
launcher described below.

Later edits and unknown files in a transaction's managed skills block recovery,
interrupted transitions and new installs before replacement. Only skills without
a recorded installed copy (never installed, or absent after recovery) are isolated
per skill as described above. Completing a partial installation from the same
release, after retaining or moving a withheld skill aside, keeps the recovery
target of the original install, so `recover` still returns to the pre-upgrade
inventory. Rolling back an interrupted completion returns to that partial
installation and keeps the same recovery target.
The error identifies the affected skill and repair. For a completed installation,
commit and explicitly retain the customization, or move conflicting content out
of that skill directory and restore the recorded bytes before retrying. During
an interrupted replacement, move later edits aside, finish or recover the
transaction, then reapply, commit, and retain them. A changed source requires
recovery before starting a different install. Malformed history, symbolic links,
and unfamiliar staging material are preserved: inspect the named record or move
the named staging directory aside explicitly before retrying. This also repairs
a staging copy interrupted before it became a complete directory.

Unaffected installed capabilities remain available under their existing stage
rules. To explicitly select an offered manual fallback for this report, use
`fallback --skill NAME` with the same source proof. The returned
`fallback_selection` names the existing stage-owned route; it executes no skill
and saves no routing preference. The owning stage controls actual execution.
Selecting fallback does not repair installation, mark it complete, or qualify
its source. No fallback is selected by preview, check, install, or recover.

Conductor setup is available through the explicit adoption option below.

Local startup must continue preserving existing and newer sources. This command
adds no startup hook, changes no user-wide settings, and does not install skills
merely because the checkout exists. Use explicit `install` only in the project
where bundle activation has been selected. Actual Claude Code/Codex discovery
and invocation, including fresh/recreated Cloud support, require separate live
qualification; fixture success makes no support claim.

## Recover an absent adopted source

While the verified checkout is available, explicitly export a portable launcher
to an existing directory you control. Keep it available separately from that
checkout so a missing machine-local path does not hide the recovery interface:

```sh
python3 "$PLAYBOOK_PATH/v0.5/scripts/recover-playbook-source.py" \
  --write-launcher "$LAUNCHER_PATH"
```

`LAUNCHER_PATH` is a Python zipapp file, for example `provision.pyz`. It packages
the same release-provenance checker, state scalar reader and bundle reader with
their license. Identical export is a no-write operation; a linked destination or
different existing bytes block rather than overwrite a customized launcher.
Export from the available checkout, not from the zipapp itself.
Existing launcher output must be a regular file before its bytes are compared.
Nonregular endpoints, including FIFOs, return JSON repair without opening them;
preserve the endpoint and choose another output.

The launcher reads `playbook_release`, `playbook_release_tag_object` and
`playbook_release_commit` from the project's `.playbook-state.yml`. It accepts
no latest-release choice or maintainer-candidate substitution. Missing,
ambiguous or invalid proof requires restoring the recorded proof through the
existing owner/migration flow. An adoption without the bundle requires an
explicit upgrade; recovery never upgrades it.
The effective adoption-proof endpoint must also be a regular file before it is
read. A FIFO, including a link to one, blocks promptly with repair to restore a
readable regular adoption record. A link to regular proof remains readable;
the export command's direct launcher-link refusal is unchanged.

```sh
python3 -B "$LAUNCHER_PATH" --project "$PROJECT_PATH" \
  --source "$PLAYBOOK_PATH" --cache-dir "$SOURCE_CACHE" preview

python3 -B "$LAUNCHER_PATH" --project "$PROJECT_PATH" \
  --source "$PLAYBOOK_PATH" --cache-dir "$SOURCE_CACHE" --acquire install
```

The first command reuses a clean exact configured source or an already verified
cache offline. If neither exists, it reports repair without downloading. The
second explicitly acquires the adopted annotated tag, verifies its tag object
and peeled commit before checkout, then validates the clean release and bundle
before publishing the cache and invoking that release's public provisioner.
`--repository` can select an acquisition transport; the recorded proof remains
the authority. A later remote HEAD or newer tag is never selected. Acquisition
does not make a separate upstream skill request.

The cache must be outside the consumer project and its customizations. A linked
cache location, dirty existing source, changed tag, wrong commit, inaccessible
transport or invalid bundle blocks with repair instructions. Existing source
and cache edits are preserved; choose a separate location or restore their
recorded bytes explicitly. Failed acquisition changes no adoption, project
skills or user settings. It may leave an empty external cache directory.
The saved source path and all adoption/settings fields remain unchanged even
after success. Installation still uses the existing provisioner's conflict,
retention, recovery and invocation boundaries.

Omitting the action selects non-mutating `discover`; it rejects `--acquire`.
The other provisioner actions and their `--skill`/`--custom-bindings-dir` options
are forwarded unchanged. JSON adds `source_resolution` with the actual path,
release, tag object, commit, reuse/acquisition mode and `adoption_changed: false`.
Exit 2 still means a blocked or incomplete action; preserve reports privately.
The recovery launcher and the optional Conductor hook below require Python 3.9 or
newer and Git; Conductor Cloud currently provides Python 3.9. Bootstrap and upgrade
can adopt it through their existing preview/Apply boundary below. The optional
Conductor hook uses the same resolver; neither grants live runtime qualification.

## Adopt through bootstrap or upgrade

Select portable inventory adoption as part of the existing setup or migration
plan. Add `--adopt-skills` to bootstrap's read-only command, or preview an
existing consumer with:

```sh
python3 "$PLAYBOOK_PATH/v0.5/scripts/upgrade-project.py" "$PROJECT_PATH" \
  --plan --adopt-skills
```

The `Skill inventory adoption:` JSON line names the registry-derived inventory,
exact verified public release/tag object/commit, `local_policy: discover`,
customization/recovery implications, and an `inventory_revision`. Include all
of that in the same human-reviewed plan as managed files, settings and setup.
Apply uses the existing command with `--apply` for bootstrap or `--apply-safe`
for upgrade, adding the same `--adopt-skills` and
`--inventory-revision "$INVENTORY_REVISION"`. The revision binds the desired
inventory, source proof and launcher bytes; it is part of that single Apply
gate, not another approval. A missing or changed revision blocks before writes.
`--plan` alone previews upgrade policy without selecting a new inventory.

Successful adoption adds one inline JSON `skill_provisioning` field to the
existing `.playbook-state.yml`, and writes `.playbook/provision.pyz`. Its schema-1
record contains `bundle_sha256`, `launcher_sha256`, `launcher` and `local_policy`;
the existing root release proof remains authoritative. Hashes bind the reviewed
bundle integrity record and portable launcher, rather than storing a second
catalog or a personal source path. Commit these project files deliberately
through the normal review workflow; the helpers never commit or upload them.
The launcher and state remain usable after project recreation, including when
the original configured path is absent.

Adoption installs no bundled local duplicate and changes no saved model or job
binding, machine-local source choice, user settings or existing setup command unless `--conductor-setup` is also selected.
Use the public launcher with its default `discover` action to inspect local
sources. Explicit `install` is still required for bundle activation; it preserves
the existing retention/conflict rules and upstream invocation controls. Project
or newer local skill choices can be reviewed independently through Configure
without advancing the Cloud release proof.

An old consumer remains unadopted until this option is deliberately selected.
A release without the bundle or without verified public provenance cannot supply
an adoption. For a consumer that already adopted inventory, advancing its
release proof also requires the inventory in the existing upgrade preview/Apply
gate. An unchanged repeat Apply with the same revision changes no project bytes.
The maintainer checkout refuses consumer bootstrap/adoption; use isolated fixtures.

Required migration review, schema errors and preservation conflicts prevent the
new adoption and completion stamp. Resolve the named review and retry through
the same flow. A differing unrecorded/customized launcher, linked endpoint or
unsupported adoption record is preserved for explicit repair before writes.
Inventory Apply requires an unlinked regular project `.playbook-state.yml`.
A link to a regular state target remains readable in preview and exact-source
recovery checks, but mutating adoption refuses it before changing consumer files.
Preserve both endpoints and explicitly restore a regular project state file before
retrying Apply. If failed completion leaves a linked state endpoint, rollback
also refuses to write through it; retain the incomplete adoption and inspect the
reported recovery error before repairing the state and retrying.

An unchanged recorded launcher can be refreshed only through deliberate adoption.
If status computation or later bootstrap/upgrade work fails, restore the prior
certification and launcher while retaining safe migration edits for inspection.
An incomplete first bootstrap retains null edition/release completion fields
and requires the cold prerequisite path. Review the diff before retrying.

Bootstrap excludes source `__pycache__` directories and `.pyc` files from local
skill copies, consistently with template provenance. A cache created by another
source process must not turn a repeat bootstrap into a consumer state rewrite.
This behavior does not depend on suppressing bytecode generation.
For an already installed delivery skill, bootstrap calls the existing public
lifecycle `verify` action instead of reinstalling identical files. Verification
still checks the source manifest, installed pack digest, exact owned-file registry
and every owned file. Healthy repeated bootstrap preserves consumer file bytes,
modes and mtimes, including its manifest lock. Drift or a partial/stale pack
requires review; a lock's presence alone never establishes a healthy install.
A pending `install-state.json` remains incomplete even when file verification
passes. Bootstrap preserves that evidence and reports the existing lifecycle
install/upgrade repair for inspection rather than clearing it or certifying setup.
Explicit supported repair may write files; repeat bootstrap after repair verifies
them without rewriting. Delivery lifecycle policy and runtime remain unchanged.


## Optional Conductor setup adoption

Add `--conductor-setup` **together with** `--adopt-skills` to the existing
bootstrap preview or upgrade `--plan`. Include the same flags and the returned
`--inventory-revision` in its existing Apply command. This adds no approval gate
and does not change old consumers unless selected. Explicit setup configuration
composition needs Python 3.11+ (`tomllib`); the configured hook needs Python 3.9+,
its standard library, Git for source verification, and POSIX `sh`.
No toolchain, runtime, skill, model or setting is upgraded automatically.

```sh
python3 "$PLAYBOOK_PATH/v0.5/scripts/upgrade-project.py" "$PROJECT_PATH" \
  --plan --adopt-skills --conductor-setup
# After reviewing that same plan, use --apply-safe instead of --plan and add
# --inventory-revision with its exact returned value; retain both option flags.
```

The preview shows the composed `setup_after` command and binds the existing shared
settings and generated hook bytes to the inventory revision. Apply preserves the
prior shell body's meaning, exported variables, inline comments, other settings and
file modes while appending a guarded call to `.playbook/conductor-setup.sh`; the
composed string is rewritten as one escaped TOML string. A nonzero status from the
prior body's last command stops the hook with that status; earlier commands keep
their existing error handling unless the prior body sets its own `set -e`. The hook runs in a subshell rooted at `CONDUCTOR_WORKSPACE_PATH`, so prior
working-directory changes do not redirect its relative paths. Unchanged repeated
Apply/setup preserves bytes, modes and mtimes. Failed setup adoption restores the
previous hook and certification rather than leaving a newly active partial hook.

Composition supports a standalone `setup` assignment in `[scripts]` or a root
`scripts.setup` assignment, including quoted/multiline shell strings. Ambiguous
layouts, malformed or non-UTF-8 settings, prior bodies that cannot be scanned
safely (such as a heredoc with an unbalanced quote), terminating `exit`/`exec`/`return` tokens, customized
managed suffixes/hooks, linked endpoints and legacy `conductor.json` or
`.conductor/settings.json` require explicit reconciliation. The control-token
check is conservative and can also refuse those words as arguments; move such
commands into a reviewed project helper before adopting. Inputs are preserved on
refusal. An inventory re-adoption without `--conductor-setup` refreshes an
unmodified previously adopted hook together with its launcher; a customized hook
is preserved for explicit reconciliation. Legacy settings must be deliberately migrated with their actions/archive
and other values intact before creating shared TOML. Higher-precedence local or
managed settings can mask the shared command; inspect the effective host settings.
Static gitignored environment files belong to Conductor's Files to copy facility,
not automatic copying or credential handling in this hook.

The actual host-provided `CONDUCTOR_IS_LOCAL` selects behavior; paths and installed
home skills are never environment evidence. Missing/invalid values refuse setup:

- `1`: discover/report existing sources and directory aliases only. No acquisition,
  skill/discovery-configuration writes, bundle activation or user-wide changes.
  If the recorded source is absent or no longer the adopted release, the hook
  reuses an exact source already verified in the same separate cache; the
  configured checkout itself is never rewritten.
- `0`: validate the existing inventory record and regular launcher, then replay
  the exact adopted release through the same provisioner. The configured consumer
  hook deliberately enables `--acquire` to the separate absolute
  `$XDG_CACHE_HOME/agentic-engineering-playbook/sources` cache, or
  `$HOME/.cache/agentic-engineering-playbook/sources` when XDG is unset. An already
  available exact source/cache is reused offline. Recorded tag object and commit
  remain authoritative; setup never selects a newer release or upgrades adoption.

The portable launcher also accepts `setup` directly with the existing source and
cache options. Its `--source` can be explicit; the generated hook reads the same
rendered state-header Playbook location used by upgrade. An absent local source
reports its recorded path and an explicit `--acquire ... preview` recovery command
without downloading; after that separate recovery, local setup reuses the verified
cache. The recorded path is machine-specific, so a teammate either restores it or
uses that explicit recovery. Cloud missing proof, moved tags, offline
acquisition, damaged bundle or unavailable dependencies leave adoption and project
customizations repairable. Missing Python/shell/host inputs have actionable stderr;
source/inventory errors retain JSON repair reports. Follow that repair before
retrying; no fallback or user-only invocation happens automatically.

### Discovery wiring and activation

Codex uses the canonical `.agents/skills/NAME` directories. After Cloud
installation, including a completed partial install, setup creates missing `.claude/skills/NAME` **directory** aliases to
`../../.agents/skills/NAME` for installed or valid retained inventory skills and
present Playbook-owned skills. A conflicting inventory skill's alias is withheld
and named alongside its exact retention/move-aside repair; unrelated aliases
still appear. Its report lists `withheld` Codex and Claude rows, with any existing
Claude endpoint preserved and labelled. Pending transactions and refused operations
create no aliases. A completed install or recovery, partial or not, removes only
setup-owned aliases whose canonical directory is gone.
Content conflicts keep both `installation_complete` and `complete` false, with
setup exiting 2. Existing endpoints remain preserved for explicit reconciliation. Entire directories preserve references, dependency lookup,
licenses, `disable-model-invocation` and `agents/openai.yaml` invocation policy.
Correct existing links retain their literal targets and mtimes. Unknown content,
wrong/dangling links, legacy same-name Claude commands and linked discovery parents
are preserved and reported as conflicts; no alias is overwritten. Only conflicting
aliases are withheld and named in the repair; other missing aliases are still
created. A linked or nonregular `.claude` or `.claude/skills` parent withholds all
aliases. A later explicit `install` or `recover` removes only setup-owned aliases
whose canonical directory is gone. Local setup only
observes this wiring. JSON reports `discovery_aliases` separately and, in Cloud,
`installation_complete`; an alias conflict leaves overall setup incomplete while
unaffected installed capabilities remain available under their stage rules.

These filesystem observations are **not runtime discovery or invocation proof**.
The documented mechanisms come from [Codex skill discovery](https://learn.chatgpt.com/docs/build-skills)
and [Claude Code skills](https://code.claude.com/docs/en/skills.md). Actual selected
source, duplicate-name behavior, version compatibility and explicit invocation
remain the S7 gate for fresh/recreated Cloud and both local runtimes. An installed
incompatible embedded reviewer retains its existing stage-owned fallback.

Dated maintainer-candidate checks on 2026-10-26 used Conductor CLI 0.92.0,
Python 3.9.25, Claude Code 2.1.308 and Codex 0.164.0. Initial fresh starts lacked
provisioning outputs; manual installation passed, but Claude native discovery
still failed on a later turn. A subsequent explicit Cloud repository **Setup
script** setting, pinned to the reviewed candidate, provisioned all eleven skills
and aliases before agent startup. Targeted fresh/recreated checks then passed
in both runtimes: runtime-selected `tdd` and full references, explicit user-only
`grill-with-docs` and its dependencies, and incompatible-reviewer refusal with
explicit stage fallback. Recreated sessions loaded a committed, explicitly
retained TDD customization and its added reference. These runs qualify that
bounded maintainer setup route, not consumer release recovery or all skill behavior.

After the temporary setting was restored, the human approved durable Cloud
repository setup: run the checked-out maintainer hook when it exists, otherwise
report an older revision without provisioning and exit 0. The saved setting was
verified by navigation and readback. Fixtures cover its conditional guard; the
previous Cloud matrix covers the same hook/argument. Branch-TOML activation
remains unresolved, and host setup
logs did not establish the exact selection/activation cause. A missing Setup tab
also occurred on success and is not proof that setup was skipped. The recreated
Claude observer briefly wrote and removed a scratch file under `.git`, so its
observation does not prove whole-filesystem non-mutation. Retained bytes matched.

Capture runtime-selected sources before fallback reads, and use Codex dollar-form
explicit invocation for skills with `allow_implicit_invocation: false`. An
explicitly requested Claude native call succeeded for the user-only skill; this
is not proof about implicit triggering. Local Claude selected a personal duplicate
by name in the bounded coexistence check; do not infer project precedence from
alias presence. A later local round used Claude Code 2.1.284 / Opus 5.5 high
and Conductor-hosted Codex 0.164.0 / Sol high. Project-only native Claude calls
and explicit Codex file selection loaded exact/newer/customized sources and
full references; absent project sources were refused. Both observed retained
custom execution selections blocking after source drift and incompatible-reviewer
refusal/fallback. Default discovery preserved personal collisions; these runs
prove neither global skill absence nor default project precedence. Personal
skills/settings and the Cloud pin were unchanged. Standalone Codex account access
was not repaired. Consumer release coverage remains deferred until a release
contains the bundle. The qualification report retains the precise scope and
observation limitations.

The maintainer repository's shared `.conductor/settings.toml` calls
`sh v0.5/scripts/conductor-setup.sh --candidate`. This uses the same provisioner,
labels the current development candidate, and creates no consumer state or release
stamp. Candidate mode is limited to its own checkout without consumer state; it
never acquires a release. Its Cloud output (`.agents/` and `.claude/skills/`) is
reproducible from the reviewed bundle and ignored at the repository root, so the
candidate stays clean; public-content checks skip those paths only while they are
ignored and untracked. Test this only in disposable fixtures before the live
gate; do not bootstrap the real maintainer checkout.

Conductor documents Cloud shared setup as coming from the branch used to
**create** the workspace. The live observations above have not qualified that
activation path; the successful runs used the explicit Cloud repository setting.
Use a fresh/recreated workspace at the exact reviewed candidate for qualification.
The Mac app reads shared repository settings from the **remote default branch**,
so editing a feature worktree does not activate them locally. They must reach that
branch through the normal reviewed process before new local workspaces inherit
them. Nothing in fixture success authorizes publication, live runs, explicit
user-only invocations or claims of supported runtime qualification. See the
[Conductor scripts](https://conductor.build/docs/reference/scripts),
[settings](https://conductor.build/docs/reference/settings),
[environment](https://conductor.build/docs/reference/environment-variables) and
[repository schema](https://conductor.build/schemas/settings.repo.schema.json).

Monthly maintenance compares upstream/runtime/discovery changes. Any deliberate
source, runtime, model or settings migration must recheck affected contracts,
preserve customizations and recovery, and record actual tested versions. Startup
only replays the approved choice.

## Maintainer candidates and updates

For an isolated development fixture, substitute `--candidate` for all consumer
proof arguments. The report identifies `maintainer-candidate`, HEAD, dirty
status, and the actual bundle record hash; its consumer release stays null.
Candidate testing never creates consumer state in this maintainer repository.

The source packaging command is maintainer-only:

```sh
python3 v0.5/scripts/generate-skill-bundle.py --upstream "$REVIEWED_SOURCE"
python3 v0.5/scripts/generate-skill-bundle.py --check
```

Generation requires a clean upstream checkout at the registry pin and its
annotated tag. It copies every regular file in the selected directories and the
root license, then derives the integrity record through the registry reader.
An existing bundle is preserved; replacement is an explicit reviewed maintainer
change. CI checks the packaged record offline. Provisioning itself performs no
upstream skill download or pin update.

Follow [monthly maintenance](../MAINTENANCE.md) and recheck before adopting
source, skill, runtime, model, or setting changes. Compare complete directories,
dependency closure, invocation policy, licenses, and the existing compatibility
records. Preserve project customizations and recovery options; record tested
versions and rerun affected live discovery/invocation qualification before making
support claims. A newer local choice never implicitly advances the Cloud pin.
Review launcher compatibility at the same maintenance/adoption checkpoints.
Export a refreshed launcher to a separate path, preserve customized bytes, and
requalify the affected public interface before deliberately replacing it.

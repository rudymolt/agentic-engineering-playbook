# Project skill provisioning

The public `provision-skills.py` command previews, installs, checks, and recovers the
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

Change the final action to `install` for explicit project activation, or `check`
to inspect installed state. Preview and check write no project files. An install
with identical content changes no files. Omitting all three proof arguments
requests the existing public-tag provenance check; partial or mismatching proof
blocks. A release without the bundle needs an explicit release upgrade.

The commands emit JSON. Exit 0 means a successful preview, completed install,
complete installation check, explicit retention, recovery, or fallback report. Exit 2 means a blocked operation or incomplete
check. `complete` describes file installation only. Per-skill reports contain
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

## Preservation and explicit retention

All bundle material is validated before activation. Missing material, altered
hashes, invalid metadata, or missing dependencies block activation. The provisioner
distinguishes exact installed bytes (`installed`), unchanged managed bytes from a
previous inventory (`update_available`), explicitly retained committed project
bytes (`customized`), missing directories (`missing`), and unknown or later
unretained edits (`conflict`). Preview and check report these states without writes.
Unchanged reruns preserve file bytes and modification times. Unrelated skills,
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
Initial-install recovery returns to the preceding empty/missing inventory.

Recovery reports `recovery_complete` separately from `complete`: restoring an older
installation need not match the currently requested source. `recovered_source`
names the restored source evidence; no adoption record changes. An unchanged
repeat recovery performs no writes. Keep the available verified source when
recovering; exact-release acquisition remains a later slice.

Later edits and unknown files block destructive transitions before replacement.
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

Local source discovery/selection, exact release acquisition, bootstrap/upgrade
adoption, and automatic Conductor setup remain later slices.

Local startup must continue preserving existing and newer sources. This command
adds no startup hook, changes no user-wide settings, and does not install skills
merely because the checkout exists. Use explicit `install` only in the project
where bundle activation has been selected. Actual Claude Code/Codex discovery
and invocation, including fresh/recreated Cloud support, require separate live
qualification; fixture success makes no support claim.

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

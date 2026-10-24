# Project skill provisioning

The public `provision-skills.py` command previews, installs, and checks the
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
or complete installation check. Exit 2 means a blocked operation or incomplete
check. `complete` describes file installation only. Per-skill reports contain
expected integrity hashes, actual installed hashes when readable, source
identity, invocation mode, dependencies, and compatibility/fallback observations.
Conflicting installed bytes have unknown upstream identity. Discovery and
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

## Preservation and initial-install repair

All bundle material is validated before activation. Missing material, altered
hashes, invalid metadata, missing dependencies, or conflicting project skill
content block installation. Unknown files inside a selected skill are preserved
as conflicts; the provisioner neither merges nor replaces them. Symlinked
installation parents and skill directories are also preserved and blocked.
Reconcile conflicts explicitly before retrying. Existing unaffected skills
remain available.

Each missing skill is staged outside the discovery root and activated as a
complete directory. A killed process can leave staging material under
`.agents/.skill-provisioning/`, alongside some already installed complete skills.
Run `check` to see the incomplete inventory, then rerun the identical `install`
to finish it. Completed skill directories are preserved byte-for-byte. Abandoned
staging is outside runtime discovery and may be inspected and removed manually;
it is never treated as an installed skill. A failed install returns an incomplete
result with a repair action. Previous-installation recovery and retained
customization adoption are later slices, as are local source selection, exact
release acquisition, bootstrap/upgrade adoption, and automatic Conductor setup.

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

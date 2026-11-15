# Conductor setup metadata and receipt qualification

Use the existing [setup interface](skill-provisioning.md#optional-conductor-setup-adoption).
Installation, setup receipt completeness and automatic-startup qualification are
separate results. A consumer receipt wrapper must not impose optional display
metadata requirements on the installer.

## Required inputs by route

| Route | Required inputs | Optional identity metadata |
| --- | --- | --- |
| Public launcher `setup` | Explicit `CONDUCTOR_IS_LOCAL=0` or `1`, valid source/adoption proof and the existing toolchain | Workspace name and ID |
| Adopted shell hook | Those inputs, regular launcher, Python 3.9+ and POSIX shell; Cloud also needs absolute HOME/XDG cache location | Workspace name and ID |
| Composed setup command | Hook inputs and `CONDUCTOR_WORKSPACE_PATH` to enter the workspace | Workspace name and ID |
| Consumer receipt-required wrapper | Setup prerequisites and a valid workspace UUID captured in the setup process | Display name |

Keep existing source, inventory and dependency checks. Do not infer local/cloud
dispatch from paths or installed home skills. The installer does not validate
workspace IDs. The receipt-required wrapper is an external consumer contract;
no additional installer or maintained receipt writer/checker is shipped here.

## Environment variation

Treat absent, empty and whitespace-only `CONDUCTOR_WORKSPACE_NAME` as unavailable.
Represent this absence explicitly in the consumer receipt format. Never invent
a name or store an ID in a field claiming to be a verified display name.

| Setup-process metadata | Installer with other prerequisites met | Receipt-required consumer wrapper |
| --- | --- | --- |
| Name and valid ID | Proceed | Prepare receipt |
| Valid ID, name absent/empty/whitespace | Proceed | Prepare receipt with unavailable name |
| Invalid ID, with or without name | Proceed | Refuse preparation before child commands |
| ID absent/empty/whitespace, including name only | Proceed | Refuse preparation before child commands |

Preparation validates UUID syntax without contacting the host or adding API
credentials/network requirements. Syntax alone does not prove workspace binding.
For an unavailable/invalid ID, return a nonzero preparation status, for example:

```text
Setup receipt needs a valid CONDUCTOR_WORKSPACE_ID from the setup process;
setup was not run. Restore the host-provided setup environment and retry.
```

Never print metadata values, credentials or an environment dump. Preparation
failure means child setup was not run, not that the installer failed. A separate
manual installation may succeed without a receipt but cannot prove automatic
startup. Missing optional names never trigger this preparation failure.

Preserve composed commands, exports, order and child failure status. Receipts
cover the complete configured command, including package installs/generation,
not just the skill installer. If finalization fails after child execution,
retain the child outcome and report the evidence failure separately; never turn
a failed child into success.

## Qualification checklist

1. Read the effective saved Cloud Setup field from the intended host. Tracked
   local TOML alone does not establish Cloud activation. Record the exact command,
   revision, adopted release/tag proof and host/tool versions privately.
2. Use a fresh workspace; retain automatic setup evidence before the first agent
   session or any manual installation/repair. Agent-process metadata does not
   establish what the setup process received.
3. Check the whole-command receipt, child statuses and unavailable-name encoding
   against the consumer writer/checker contract. Deliberately update both writer
   and checker for ID-based acceptance; do not silently relax a name-based check.
4. Compare the original captured ID with the authoritative host record for the
   actual workspace. A UUID-shaped value or name alone is insufficient. Mismatch
   or unavailable comparison evidence withholds binding and qualification. Never
   backfill an original missing ID from a later agent process.
5. Report installation, receipt completeness, workspace binding and automatic
   startup separately. Record host, release, runtime and restart limits. Existing
   discovery/invocation qualification gates still apply.

Fixture tests prove only the routes exercised. The installer matrix covers
identity independence, local/cloud dispatch, sh/bash composition, child failure
and unchanged adopted state/customizations. It does not implement or qualify
an external receipt checker. Historical qualification keeps its original scope.

## Adoption and maintenance

Existing consumer wrappers need deliberate local repair or reviewed adoption.
Preserve custom scripts, composed commands and the complete provenance unit;
never overwrite customizations or automatically advance pins. Review writer and
checker together, including blank names, invalid/missing IDs, host mismatch and
child failures. Verify a published consumer fix before linking it; private
project records stay outside public documentation.

The motivating consumer repair is not verified as published here. No public
repair link or fresh automatic-startup support claim is supplied. Publication
and affected real-route qualification remain separate follow-ups; reviewed
guidance and installer tests may ship with this explicit limitation.

At monthly maintenance (next recorded checkpoint 2026-12-08) and explicit
host/skill/model/settings upgrades, compare upstream contracts, verify
compatibility and use reviewed adoption with customization/recovery preserved.
No per-turn update check or automatic pin change is added.

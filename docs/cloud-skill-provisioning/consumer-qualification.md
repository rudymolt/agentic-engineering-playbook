# Consumer release qualification

Status: **V0.5.3 published-release CLI qualification passed on 2026-10-27**.
Adoption, exact-source acquisition, offline replay, preservation and retained
customization recreation passed against the real public release. Conductor
consumer dispatch was simulated locally; actual consumer Cloud startup and
runtime invocation were not tested in this round. The
[maintainer report](runtime-qualification.md) supplies separate runtime evidence.

## Published release and results

The non-draft Latest release is `v0.5.3`, annotated tag object
`c8f62a177959bf9defb9ec4f80c2ffdc6dd5176c`, commit
`a3540cf5ca6dd3ef705d7d49fb4a2e7ce0da4bb0`, tree
`8cabe5fa4f3a510288680d85a3809390e934276f`. Local and public remote tag
objects and peeled commits agreed. The clean consumer clone used that exact
published tag from the canonical public origin. Bundle and edition manifest
checks passed. Bundle record SHA-256:
`040f1971c1fdb6fc28c565c97affaaa3630cea010c3906f05bd16ddcaab0401f`.
Portable launcher SHA-256:
`2aa935d34039447f87a9c0bef92614ff5eece45e82eb2aff1759c30fd484a486`.

PR #49 merged to that release commit with noreply author and committer identities.
Its tree equals the final candidate that passed the canonical verifier with
1,346 reported test executions, including the full delivery suite. Both required
PR CI jobs passed in run `40447966805`; main CI `40448792995` also passed both
required jobs. Automated review completed without findings. The release checker
passed with `--github --profile playbook-v0.5 --no-bench`; the private historical
benchmark remains outside the public release gate.

The consumer procedure below ran on macOS with Python 3.14.3 and
Git 2.50.1 (Apple Git-155), using disposable projects, isolated HOME/preferences
and Git configuration, and separate source caches. It launched no paid agent or
Cloud workspace and changed no personal or shared settings outside those
disposable projects.

| Check | Observed result |
| --- | --- |
| Bootstrap/adoption | Preview wrote no project or HOME files. Reviewed Apply recorded the exact release, bundle, launcher and composed setup. Edition stayed V0.5.0; installed release was v0.5.3. |
| Complete installation | All eleven inventory skills installed with matching complete-file hashes, support files, invocation metadata and LICENSE. Check returned complete. |
| Repetition | A fresh preview followed by repeat Apply, repeat install and repeat simulated setup preserved file bytes, modes, nanosecond mtimes and symlink targets. |
| Missing source | Relocating the configured source produced an actionable refusal without acquisition or project/adoption changes. Explicit acquisition from the public repository restored exactly the recorded tag and commit in an external cache. |
| Offline recovery | Verified cache replay succeeded without any Git transport attempt. An empty cache with blocked transport refused and preserved the project/adoption. |
| Altered proof | A changed tag-object field was refused before activation. The original recorded proof was restored with its original bytes and timestamp. |
| Retained recreation | A committed complete TDD customization and explicit portable retention record survived a new checkout. Public-release recovery installed ten skills and reported TDD as customized; all retained hashes, modes and recreated-checkout mtimes stayed unchanged. |
| Conductor dispatch simulation | The composed prior setup ran on all three checks. Simulated Cloud dispatch installed the selected inventory and eleven directory aliases. Repeat Cloud dispatch was unchanged; simulated local dispatch only discovered sources and wrote no project or HOME files. |
| Reviewer refusal/fallback | The exact installed code-review source returned incompatible, may_invoke false and exit 2. Explicit fallback selected stage 08 manual standards/spec review; the incompatible skill was never invoked. |

Project notes, saved adoption/source paths, settings and isolated HOME sentinels
survived the applicable operations. CLI success is exit 0; expected missing-source,
offline-acquisition, altered-proof and incompatible-reviewer refusals are exit 2.
Runtime discovery and skill behavior remain separately unverified by this run.

One qualification-runner correction is retained: it first reused the pre-adoption
inventory revision after setup composition changed the bound before hashes. Apply
correctly refused that stale token. A fresh preview showed identical desired bytes,
and repeat Apply then passed with no writes. The product required no fix.

Redacted command reports, hash/mode/mtime snapshots and recovery-point receipts
were retained privately before removing the owned disposable projects and caches.
This closes the published-release CLI follow-up. Future actual consumer Cloud or
runtime support claims still require their own scoped live evidence.

## Prerequisites and scope

Use the non-draft GitHub Release `v0.5.3`, its annotated tag object and peeled
commit from the canonical public repository in the
[release-provenance contract](../../v0.5/scripts/release_provenance.py).
Require local/remote agreement,
a clean checkout, valid bundle/manifests/notices, and the full release verifier on
the final release candidate. Never create a synthetic tag and report it as the
consumer release. Record exact Git/Python versions, command exits and hashes.

Run the CLI checks below in disposable consumer projects with an isolated HOME,
Git configuration and external source cache. Change no personal skills, login,
global settings, shared Cloud settings or real consumer project. The public
release read is required; no additional upstream skill download is needed.
These deterministic checks create no Cloud workspace or paid agent session.

If actual consumer Cloud/runtime invocation is needed beyond the already
qualified maintainer matrix, retain it as a separate untested route until an
explicit remaining live budget and host access are established. Existing Cloud
round capacity is exhausted. Do not restart those rounds or treat CLI success
as runtime startup evidence.

## Repeat against a published release

1. Clone the exact published tag and verify its annotated object, peeled commit,
   clean worktree and origin against the Release. Save that proof separately
   from the disposable project. Reject disagreement before adoption.
2. Preview bootstrap with `--adopt-skills --conductor-setup`, no UI, and an
   isolated preferences directory. Inspect the complete preview and apply its
   exact returned inventory revision to this disposable project. Check that
   root release proof, inventory proof, launcher and setup hook agree. Confirm
   the edition stamp stays V0.5.0 while the installed release is v0.5.3. For a
   repeated Apply after setup composition, obtain a fresh preview: its revision
   binds the current before hashes, even when the desired output is unchanged.
3. From the available verified source, run the public provisioner install/check.
   Require all eleven complete skill directories and matching bundle identity.
   Repeat install and compare bytes, modes and nanosecond mtimes. Keep project
   notes and existing setup effects in the preservation snapshot.
4. Make the recorded checkout unavailable by relocating this operation's owned
   source. Run the installed portable launcher without acquisition: require an
   actionable refusal and unchanged adoption/customizations. Then explicitly
   acquire from the public repository into a separate empty cache. Require the
   original annotated tag object and commit, complete installation and
   `adoption_changed: false`; saved source paths and settings must stay unchanged.
5. Replay using the verified cache and an unavailable transport. Require success
   without a new fetch or changed files. With a fresh cache and unavailable
   transport, require refusal and unchanged project/adoption. Alter only an owned
   copy of the recorded proof and require refusal before activation; preserve the
   original proof as the recovery point and restore it afterward.
6. Add a small complete TDD customization in the disposable project, commit it
   with noreply identity, run `retain --skill tdd`, and commit the portable
   retention record. Recreate an owned checkout from those tracked bytes, with
   the saved playbook path still absent. Recover the exact release and require
   ten installed skills plus TDD `customized`, with every retained hash unchanged.
7. Exercise the adopted hook's Cloud dispatch locally with explicit fixture host
   variables, and default local discovery without skill/configuration writes.
   Label this a dispatch simulation; actual Cloud startup remains a separate
   observation. Verify exact-source `code-review` refusal and the explicitly
   selected stage-08 fallback; do not invoke the incompatible reviewer.
8. Record pass/fail separately for adoption, acquisition, offline replay,
   preservation and recreation. Retain redacted reports and recovery-point
   identifiers. Remove only owned disposable copies after recording results.
   Update this document and the release follow-up; never silently widen support
   claims. Recheck the affected path before future runtime/source/settings updates.

The [provisioning guide](../../v0.5/scripts/skill-provisioning.md) owns command
syntax and recovery choices. The source recovery tests remain fixture evidence;
this procedure adds the real published release as the acquisition source.

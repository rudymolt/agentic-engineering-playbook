# Consumer release qualification

Status: pending publication of V0.5.3. No consumer pass is claimed by this
procedure. The [maintainer report](runtime-qualification.md) supplies separate
runtime evidence; candidate tests cannot prove published-release provenance.

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

## Execute after publication

1. Clone the exact published tag and verify its annotated object, peeled commit,
   clean worktree and origin against the Release. Save that proof separately
   from the disposable project. Reject disagreement before adoption.
2. Preview bootstrap with `--adopt-skills --conductor-setup`, no UI, and an
   isolated preferences directory. Inspect the complete preview and apply its
   exact returned inventory revision to this disposable project. Check that
   root release proof, inventory proof, launcher and setup hook agree. Confirm
   the edition stamp stays V0.5.0 while the installed release is v0.5.3.
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

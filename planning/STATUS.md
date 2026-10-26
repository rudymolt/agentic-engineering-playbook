# Planning status

active_features: 6

## Active features

[Cloud skill provisioning](cloud-skill-provisioning/slices.md) — alignment,
specification, both test seams, and seven implementation slices approved on
2026-10-24. All seven child tickets are published with verified dependencies;
S1–S6 are complete and independently verified at the approved fixture seam,
including returned fixes, fresh CLI QA, cross-slice review and canonical full
verification. The human selected option B on 2026-10-25 to isolate A8 content
conflicts per skill; that returned fix passed fresh independent review and
canonical full verification. The Python 3.9 setup fix passed fresh review and
full verification and was pushed. [S7 live results](cloud-skill-provisioning/runtime-qualification.md)
record targeted fresh/recreated Cloud success for both runtimes through an
explicit Cloud repository Setup setting, including tracked customization
restoration. All test workspaces are archived and the temporary setting was
restored to empty. Branch-TOML activation remains unresolved. S7 stays open for
complete local coexistence and consumer release recovery; the report records
observation limits and awaits the normal final-candidate review gates.

[Edition and installed release](edition-release-identity/slices.md) — aligned
and specified; implementation in progress on a separate branch.

[Verifier performance](verifier-performance/slices.md) — aligned and specified; five
ordered slices implemented; the measured slice 5 improvement is accepted,
with the remaining delivery performance targets tracked separately.

[Pstack result consistency](pstack-result-contract/slices.md) — approved;
terminal mappings and a separate deferred exploration scope implemented;
independent review and focused checks passed, PR review pending.

[Matt skills migration](matt-skills-migration/slices.md) — implemented;
independent review passed, verification and human review tracked in PR #27.

Other active feature: [Apply recovery artifact visibility](apply-recovery-gitignore/slices.md)
— approved single fix slice implemented; repair cycle 2 corrects a baseline
bytecode-race test assertion without changing production source. Product PR #23
merged as `5d5265c`; this feature's remaining closeout stays separately owned.

Playbook configuration UI: S8 accepted on `05de2a0` and shipped
in PR #20 as `0a3770e` on 2026-10-08. Planning artifacts archived; durable feature
entry points are [Configure](../v0.5/skills/ai-playbook-configure/SKILL.md),
[configuration boundary](../v0.5/scripts/playbook-config.md) and
[skill bindings](../v0.5/scripts/skill-bindings.md).

## Pending closeouts

This maintainer checkout intentionally has no root `.playbook-state.yml`.
The stage-10 closeout state is mirrored here; no consumer runtime state is created.

```yaml
last_updated: 2026-10-25T06:36:21Z
counters:
  features_shipped_total: 4
last_run:
  ship: 2026-10-25T06:19:18Z
  feature_ship: 2026-10-25T06:19:18Z
  doc_close: 2026-10-25T06:36:21Z
  retro: 2026-10-25T06:36:21Z
pending_closeouts: []
```


Capability and existing authority shipped in PR #46 as `8f6a2f0` on 2026-10-25.
The merge tree matches final candidate `a3b732c`; noreply merge identities and
both required main CI jobs are verified. Production verification means the
published repository, not an installed consumer upgrade. Doc-close and the
[feature retrospective](retros/2026-10-25-capability-and-authority.md) are
complete on this closeout branch, awaiting human merge. Its pending closeout
is cleared here; all other feature closeouts retain their existing ownership.
The [closeout record](../archive/2026-10-25-deployment-capability-and-authority/closeout.md)
preserves review exceptions, CI repair evidence and release limits. Current
release pointers stay at V0.5.2; the feature remains under Unreleased.

Checkpoint performance shipped in PR #41 as `20eeb04` on 2026-10-13.
Its tree matches verified head `084857c`; noreply merge identities are verified.
Complete final tests and required PR CI passed. Doc-close and the
[feature retrospective](retros/2026-10-13-checkpoint-performance.md) are
complete in this release closeout PR, awaiting human merge. V0.5.2 tagging
follows the final release gates. The numerical acceptance disposition and
[durable measurements](../bench/test-runtime/CHECKPOINT-PERFORMANCE.md) remain
explicit; unrelated feature closeouts are unchanged.

Main Playbook CI `37727464514` passed at `0a3770e`. Production verification,
doc-close and the [feature retro](retros/2026-10-08.md) are complete on this branch.
The `playbook-config-ui` retro was marked complete, then its entry removed because
all three closeout conditions are satisfied. This mirrored update reaches main
only after human merge of the retro PR. No other feature closeout is cleared.
[Archived closeout](../archive/2026-10-08-playbook-config-ui/closeout.md) preserves
the dated initial deferral, final gate receipts, historical limits and candidates.

Merge privacy confirmation shipped in PR #39 as `98886bd` on 2026-10-09.
Main Playbook CI `37989627022` passed both jobs on the merge.
The post-merge file tree matches verified candidate `9bcba3b`; ten privacy
tests and public-content verification pass. Noreply author and committer
readback covers the sole newly added main commit. Doc-close and the
[feature retro](retros/2026-10-09-merge-privacy-confirmation.md) are complete
on this closeout branch, awaiting human merge for publication on main.
Its pending closeout is cleared; no unrelated closeout is changed.
[Closeout receipts](../archive/2026-10-09-merge-privacy-confirmation/closeout.md)
preserve verification, provenance and release-scope limits.

## Separate follow-ups

- Apply recovery gitignore: product PR #23 merged as `5d5265c` on 2026-10-08.
  Its [feature tracking](apply-recovery-gitignore/alignment.md) remains separately
  owned; this retro clears only the configuration UI closeout.
- October upstream-drift comparison completed separately in PR #25, merged
  as `b55e02c` on 2026-10-08. The [comparison](../analysis/2026-10-08-upstream-drift.md)
  and maintainer state retain ownership under [MAINTENANCE.md](../v0.5/MAINTENANCE.md);
  next due 2026-11-08. This retro reconciles that landed state without rerunning
  the comparison or changing its pins or dates.

# Planning status

active_features: 6

## Active features

[Cloud skill provisioning](cloud-skill-provisioning/slices.md) — alignment,
specification, both test seams, and seven implementation slices approved on
2026-10-24. All seven child tickets are published with verified dependencies;
S1 and S2 are implemented and independently verified, including returned fixes
and fresh CLI QA. S2 adds retained customizations and installation recovery.
S3 local discovery and explicit source selection are implemented with fixture
evidence and returned source-observation corrections, including supporting-tree
traversal completeness; fresh independent verification of the latest candidate
is pending. S4–S7 remain future work;
actual runtime qualification remains pending.

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
last_updated: 2026-10-13T05:08:56Z
counters:
  features_shipped_total: 3
last_run:
  ship: 2026-10-13T05:03:43Z
  feature_ship: 2026-10-13T05:03:43Z
  doc_close: 2026-10-13T05:08:56Z
  retro: 2026-10-13T05:08:56Z
pending_closeouts: []
```

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

# Planning status

active_features: 5

## Active features

[Checkpoint and delivery verifier performance](checkpoint-performance/spec.md) —
`in-flight`; spec and [six-slice breakdown](checkpoint-performance/slices.md)
accepted. Build all six sequentially with Sol remains selected. S1 measurement
implementation and the actual reference baseline pass independent review;
S1's initial gate is complete. The [quantified savings gap](checkpoint-performance/evidence.md)
remains an experimental risk covered by the recorded approval.
Draft PR #41 checkpoints the measurement work; S2 is next and S3–S6 remain pending.
Same-path seed restoration, fixed comparators and all target/count invariants
remain binding; no performance target is certified.

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
last_updated: 2026-10-09T20:54:02Z
counters:
  features_shipped_total: 2
last_run:
  ship: 2026-10-09T20:50:13Z
  feature_ship: 2026-10-09T20:50:13Z
  doc_close: 2026-10-09T20:54:02Z
  retro: 2026-10-09T20:54:02Z
pending_closeouts: []
```

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

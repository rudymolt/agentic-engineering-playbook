# Archive status

archived_features: 6

## Shipped features

- **Consumer workflow reliability** — public behavior shipped 8 November 2026
  in PR #54 as `ba708b2`, released as v0.5.6. Archived at
  `2026-11-09-consumer-workflow-reliability/`; doc-close and
  [feature retro](../planning/retros/2026-11-09-consumer-workflow-reliability.md)
  share one closeout PR. The [durable report](../docs/cloud-skill-provisioning/checkpoint-and-startup-qualification.md)
  records separately verified adoption and bounded live startup evidence.

- **Cloud skill provisioning** — shipped 2026-10-27 in PR #48 as `b2262ef`;
  merged tree matches the final reviewed/verified candidate. Archived at
  `2026-10-27-cloud-skill-provisioning/`. Doc-close and
  [feature retro](../planning/retros/2026-10-27-cloud-skill-provisioning.md)
  merged in PR #49. V0.5.3 is published; the
  [consumer report](../docs/cloud-skill-provisioning/consumer-qualification.md)
  records passing published-release CLI checks and retained recreation. Actual
  consumer Cloud startup/runtime invocation remains outside that evidence.

- **Deployment capability and existing authority** — shipped 2026-10-25 in
  PR #46 as `8f6a2f0`; final verified head `a3b732c`. Archived at
  `2026-10-25-deployment-capability-and-authority/`. Doc-close and
  [feature retrospective](../planning/retros/2026-10-25-capability-and-authority.md)
  are complete in this closeout PR, awaiting human merge. Original review
  exceptions and failed verification attempts remain qualified in the
  [closeout record](2026-10-25-deployment-capability-and-authority/closeout.md).
  No tagged release or unrelated feature closeout is included.

- **Checkpoint and delivery verifier performance** — shipped 2026-10-13 in
  PR #41 as `20eeb04`; verified head `084857c`. Archived at
  `2026-10-13-checkpoint-performance/`. Doc-close and
  [feature retrospective](../planning/retros/2026-10-13-checkpoint-performance.md)
  are complete in the release closeout PR, awaiting human merge. The maintainer
  accepts measured gains while four original speed targets remain unmet;
  retain 512, stop further experiments, preserve compatibility limits.

- **Playbook configuration UI** — shipped 2026-10-08 in PR #20 as `0a3770e`;
  S8 accepted on final candidate `05de2a0`. Archived at
  `2026-10-08-playbook-config-ui/`. Doc-close complete; [feature retro](../planning/retros/2026-10-08.md) complete
  on the retro branch, awaiting human merge for publication on main.
  Historical failures and qualification limits remain retained.

- **Merge privacy confirmation** — shipped 2026-10-09 in PR #39 as `98886bd`;
  final product candidate `9bcba3b`. Archived at
  `2026-10-09-merge-privacy-confirmation/`. Doc-close and
  [feature retro](../planning/retros/2026-10-09-merge-privacy-confirmation.md)
  complete on the closeout branch, awaiting human merge for publication on main.
  No new release or unrelated feature closeout included.

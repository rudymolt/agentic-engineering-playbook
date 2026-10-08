# Playbook configuration UI — feature closeout

S8 accepted and feature shipped on 2026-10-08. PR #20 merged final candidate
`05de2a05e5feedde19cb1d7f0d72427b9d03b8ff` as
`0a3770e7306ec80fdf6b07aab88008cf2897aa77` at 04:26:06 UTC.

## Accepted gates

- Actual Mac Conductor cold/Configure/custom preset, differing-Plan draft
  cancellation, fresh ordinary native adopted Verify invocation/handoff and
  positive replacement on both actual hosts were independently admitted;
  owner acceptance was recorded on 2026-10-07.
- Fresh independent report-only final review passed on `05de2a0`. Claude
  Fable 5.1 substituted explicitly for GPT-6.1 Sol/high, which this Codex login
  rejected; PR #20 records the substitution. The review executed 14 adversarial
  CLI probes and found no blockers or documentation overclaim. Its macOS run's
  three Linux-only skips are separate from the unskipped Linux evidence below.
- Full actual-head CI `37719224062` passed: 794 edition tests in 44 shards and
  537 K4.1 delivery tests as root, with no skips or failures.
- The three Linux non-root permission tests passed as uid 1000 on Python 3.12,
  from the exact candidate archive, without network and without skips.
- Main Playbook CI `37727464514` passed at `0a3770e`. The delivery
  classifier passed with the expected unchanged-runtime suite skip; full K4.1
  credit comes from final-candidate run `37719224062`, not that skip.
- Post-merge noreply author/committer readback was already completed.

Historical rejections, unsuccessful repairs, interruptions, harness/network
failures, privacy capture failure and packaging diagnostics remain recorded in
[execution](execution.md) and [host qualification](host-qualification.md), with
private details retained off GitHub. Two qualification attempts are exhausted;
shipment grants no third attempt. Full-access host runs remain manually bounded,
not filesystem-enforced read-only. Provider parsing, allowances, comparative
performance and total costs retain their documented limits.

## Doc-close checklist

1. Started from a clean tree on one fresh closeout branch based on merged main.
2. ADR promotion: no additional decision needs promotion; the shipped
   configuration and binding contracts below already retain ownership,
   precedence, recovery, reviewed guidance and compatibility decisions.
3. Vocabulary promotion: existing digest, Configure guidance and contracts
   already carry the surviving terms; no additional vocabulary change.
4. Project rules: no new repository-wide rule or CLAUDE.md change identified.
5. Durable documents: the shipped source references below cover the feature;
   archived planning is historical evidence rather than required agent context.
   No adopted project verification harness exists in this maintainer checkout.
6. Release note: Unreleased changelog records closeout with a Why line.
   Current release stays V0.5.0; no new release/version/tag is requested.
7. Release checkpoint: deferred by the explicit instruction to stop at a PR.
8. Retro question raised; candidates and the pending retro are recorded below.
9. Feature folder moved to `archive/2026-10-08-playbook-config-ui/`; both status
   indexes updated. Earlier dated pending statements remain historical.
10. This maintainer checkout intentionally has no root `.playbook-state.yml`.
    `planning/STATUS.md` mirrors `last_run.feature_ship`, `last_run.doc_close`
    and `pending_closeouts` without bootstrapping consumer runtime state.
11. Closeout changes are kept in one intentional documentation commit and PR.

## Durable source references

- [Configure entry](../../v0.5/skills/ai-playbook-configure/SKILL.md) and
  [configuration boundary](../../v0.5/scripts/playbook-config.md).
- [Skill contracts and invocation](../../v0.5/scripts/skill-bindings.md),
  [model routing](../../v0.5/93-model-routing-track.md) and
  [agent digest](../../v0.5/AGENT-DIGEST.md).
- [Reviewed model guidance](../../v0.5/model-guidance.json) and
  [maintainer update cadence](../../v0.5/MAINTENANCE.md).

Future model/software/skill/host changes retain their owning checkpoints:
first discovery, new model/version and explicit refresh check official evidence;
ordinary advice reuses successful evidence for at most 24 hours; replacement
acceptance fetches the original reviewed source freshly. Source drift invalidates
admission; upgrades use preview and compatibility/qualification checks while
preserving customisations and active approvals. Monthly released-source drift
comparison stays separately owned by MAINTENANCE.md.

## Completed retro and candidate dispositions — 2026-10-08

The maintainer initially chose “Record candidates; defer retro” at doc-close.
That dated deferral remains historical; the later explicit authorisation completed
[stage 12](../../planning/retros/2026-10-08.md), with a
[field report](../../analysis/field-reports/2026-10-08-playbook-config-ui.md).
`planning/STATUS.md` now mirrors `last_run.retro` and removes only this feature's
pending-closeout entry after all three conditions were met. This change reaches
main through the human merge of the retro PR; no root runtime state is created.

Exact-candidate/actual-host boundaries and explicit unavailable-route/substitution
handling are already covered by owning rules; no duplicate process promotion.
Private recovery artifacts are a supported bounded product candidate owned by the
separate authorised Apply recovery gitignore cloud follow-up. No product fix,
maintenance comparison or new qualification is claimed by this retro. Historical
failures, two exhausted attempts and provider/cost/permission limits remain intact.

## Separate product follow-up proposal

Successful Apply intentionally retains `.playbook-config-<hex>` backup,
publication and receipt evidence, including `.receipt.complete/` seals.
[Bootstrap](../../v0.5/scripts/bootstrap-project.py) currently adds only
`.playbook-routing/` to project `.gitignore`. Proposed separate fix: add an
anchored `/.playbook-config-*` ignore rule through bootstrap and the supported
existing-project upgrade path, preserving user ignore entries and repeat
idempotence. Keep `.playbook-config.json` tracked. Test a successful Apply and
reopen, completion/conflict recovery, old-project migration, and Git's ignored
versus tracked paths. Do not delete retained evidence: receipt reconciliation
uses it. Product code changes are now separately authorised in the product cloud follow-up on
`conductor/apply-recovery-gitignore`; this retro neither edits nor claims that work.

Monthly upstream drift became due on 2026-10-08. The maintainer chose to keep
that comparison separate from this PR; the maintenance cloud follow-up on
`conductor/october-upstream-drift` owns the authorised follow-up. No audit, pin or
cadence reset is claimed here.

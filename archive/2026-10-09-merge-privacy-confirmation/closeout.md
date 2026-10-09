# Merge privacy confirmation — closeout

Shipped by human merge in PR #39 on 2026-10-09 at 20:50:13 UTC. Product
candidate: `9bcba3be9cca87a362a8f44cda4ce6bbb178c46a`; main merge:
`98886bd23203e1af8667b8bf91a7d2d4d6d77736`. This is ordinary human delivery,
not an autonomous delivery qualification or a tagged release.

## Verification receipts

The final product candidate passed the Python 3.12 canonical verifier with
`--jobs 3` and no skip flags: 1,237 tests in 65 shards, all content/generated
checks, delivery K4.1 and upstream drift cadence. Edition tests used ordinary
workspace permissions; only the delivery child used elevated permissions,
matching CI. Fresh Sol/high review passed six instruction scenarios and
66 executable privacy probes. Both PR CI jobs passed in run `37988754957`.

The automated review cited a non-candidate commit for an email finding.
GitHub's PR commits API and local Git prove the sole actual product commit
has noreply author and committer. Evidence was added to the PR description
and the incorrect thread resolved without posting comments.

Post-merge GitHub API and local Git readback found exactly one newly added
main commit. Its author uses the account's GitHub noreply address and its
committer uses GitHub's noreply address. The merged file tree is identical to
the verified product candidate; the ten privacy tests and public-content
check passed on the merged checkout. Both main CI jobs passed in run `37989627022`. No account setting was inspected through an API.

## Doc-close ritual

1. Started with a clean tree; used a fresh closeout branch after the human merge.
2. ADR promotion: n/a — this reversible policy and bounded exception are
   documented at their canonical instruction/checker sources.
3. Vocabulary/UI promotion: n/a — no new domain or UI vocabulary.
4. Project rules: root AGENTS already contains the surviving rule; CLAUDE
   delegates to it. No duplicate policy added.
5. Durable docs: [root instructions](../../AGENTS.md),
   [privacy checker](../../v0.5/scripts/check-public-content.py) and behavioral
   tests describe the shipped behavior without requiring archived plans.
   Verification harness: n/a — none adopted for this feature.
6. Release note: the feature's Unreleased changelog entry and Why line shipped
   in PR #39. Existing V0.5.1 release pointers stay current; no new release selected.
7. Release checkpoint: n/a — authorization excludes tags/releases; this PR
   closes one merged feature, without introducing a versioned milestone.
8. Human retro answer: no further promotion. The feature retro is included
   in this same closeout PR.
9. Planning artifacts moved here; only this feature removed from active status.
10. State mirrored in planning status; this maintainer checkout has no consumer
    state file. Other feature closeouts remain separately owned.
11. Closeout changes form one intentional commit and reviewable PR.

[Feature retro](../../planning/retros/2026-10-09-merge-privacy-confirmation.md)
records learning coverage and the observational evaluation.

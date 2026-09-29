# Playbook changelog

## Unreleased

- Repair S1 configuration races with durable capture and no-clobber publication, retain conflict evidence instead of destructive rollback, bind new escalated-Verify policy to immutable approvals while preserving historical routes, and require request-bound current-availability discovery separately from guidance caches.

*Why — confirmed S1 contract gaps:* arbitrary external edits must survive Apply and recovery; approved execution history must remain readable without rerouting; rereading cached guidance cannot establish current access. Regression tests cover both absent and pre-existing files, retained historical bytes, host dispatch, and adapter clocks without paid launches or S8 claims.

- Add the user-invoked S1 Configure chat path and a shared versioned project-default boundary. Import all legacy roles, preserve runtime records, preview Build edits, revalidate Apply, and roll back or report recovery. Existing lane gates resolve adopted defaults without changing approval or launch authority.

*Why — safe project defaults:* changing one future Build preference must preserve custom roles and active work, with one authoritative source and no silent fallback, substitution or model launch.

- Use GPT-6.1 Sol/high for Plan and Verify (including QA and escalated-candidate verification), and GPT-6.1 Sol/medium for Build. Retain GPT-6 Astra/high for escalated repair. Update bootstrap and upgrade defaults, preserving custom project routes and existing feature selections.

*Why — current model defaults:* the approved model policy now uses GPT-6.1 Sol for planning, implementation and independent verification while retaining bounded Astra escalation for difficult repairs.

- Keep the required `delivery` CI job fast for unrelated changes, while retaining the full delivery suite for runtime changes, delivery contract surfaces, workflow changes, classifier changes, and manual runs.

*Why — proportional verification:* documentation-only pull requests should still pass required public-edition checks without spending more than ten minutes exercising an unaffected delivery runtime.

- Link the public interactive guides from the README and permit that exact link in the root README privacy check. Other personal references remain blocked.

*Why — discoverability:* readers need a direct route to the human-facing guides without weakening the public-content boundary.

- Expand the README with skill sources and installation guidance, Wayfinder, customizable capability routes, coding-agent environments, and Conductor setup and autonomous delivery. Clarify that full bootstrap installs delivery, while capability checks and mission approval govern its use.

*Why — maintenance batch:* readers need to understand which tools are included, what to install separately, and how approved work can progress from planning to a verified pull request.

- Rewrite the root README with an ASCII wordmark, a plain-language overview, a pinned-release quick start, separate human and agent entry points, and acknowledgements including Lauren Tan's pstack.

*Why — maintenance batch:* readers need a self-contained introduction and actionable setup instructions, with clear credit for the upstream work behind the playbook.

- Match the release skill's playbook profile to the public repository name and require `noreply` identities for maintainer commits and GitHub-generated merges.

*Why — correctness and privacy:* the new repository name should not bypass the public release checks; local commit configuration alone does not control GitHub-generated merge metadata.

## V0.5.0 — 2026-09-26

Initial public edition from a reviewed adaptation of the private V0.4.2 source. It begins a new Git history, carries one live edition, and adds an independent public verification and upgrade contract.

*Why — public distribution:* earlier repository history and edition trees contain private records and cannot be exposed safely. A clean public edition makes bootstrap and stable tagged use possible without publishing that history.

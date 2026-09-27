# Playbook changelog

## Unreleased

- Expand the README with skill sources and installation guidance, Wayfinder, customizable capability routes, coding-agent environments, and Conductor setup and autonomous delivery. Clarify that full bootstrap installs delivery, while capability checks and mission approval govern its use.

*Why — maintenance batch:* readers need to understand which tools are included, what to install separately, and how approved work can progress from planning to a verified pull request.

- Rewrite the root README with an ASCII wordmark, a plain-language overview, a pinned-release quick start, separate human and agent entry points, and acknowledgements including Lauren Tan's pstack.

*Why — maintenance batch:* readers need a self-contained introduction and actionable setup instructions, with clear credit for the upstream work behind the playbook.

- Match the release skill's playbook profile to the public repository name and require `noreply` identities for maintainer commits and GitHub-generated merges.

*Why — correctness and privacy:* the new repository name should not bypass the public release checks; local commit configuration alone does not control GitHub-generated merge metadata.

## V0.5.0 — 2026-09-26

Initial public edition from a reviewed adaptation of the private V0.4.2 source. It begins a new Git history, carries one live edition, and adds an independent public verification and upgrade contract.

*Why — public distribution:* earlier repository history and edition trees contain private records and cannot be exposed safely. A clean public edition makes bootstrap and stable tagged use possible without publishing that history.

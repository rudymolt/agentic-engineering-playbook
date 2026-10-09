# Merge privacy confirmation — alignment

On 2026-10-09 the maintainer requested scope review followed by implementation
by a Sol agent. The selected outcome is to remember an existing human
confirmation for this repository and merging account, while preserving every
commit identity, review and CI check. Root `AGENTS.md` is the selected canonical
location; a separate policy file is not wanted.

At base `ec8e28a229eea56734a63bb0e1144aa518bd0a53`, only root `AGENTS.md`
contains the active repeated-confirmation requirement. `CLAUDE.md` delegates
to it. The public-content checker also rejects the public owner/login needed
by the selected record: an isolated two-line record fixture produces two
private-marker findings. The implementation therefore includes a narrowly
scoped checker exception and meaningful regression tests in the same slice.

The tracker records the prior human confirmation on 2026-10-09 before PR #38.
The implementation may seed that fact, with provenance, but must not describe
it as a live observation of the account setting. Account and repository
matching must use the actual merging identity and PR target, not the record
itself or a copied instruction file.

This maintainer checkout intentionally has no root `.playbook-state.yml`;
`planning/STATUS.md` owns feature visibility. Consumer bootstrap is out of scope.
The user has requested implementation; no unresolved product choice prevents
the single slice. Current authorization ends at a reviewable PR, without merge
or release. Routine returned fixes remain in scope.

Recheck relevant upstream behavior before a future change to this policy or
when changed behavior is reported. Verify matching and revocation compatibility
and preserve customized instructions during upgrades. No new dependency,
scheduled check, model setting or upstream pin is introduced.

# Conductor workspace metadata — specification

Status: accepted for implementation, verification and shipment on 2026-11-15.

## Problem

A consumer receipt wrapper treated an optional workspace display name as a
setup requirement. The Playbook installer succeeded separately. Existing
guidance separates installation from discovery, but does not define missing
metadata outcomes or the workspace binding required for a setup receipt.

## Acceptance criteria

1. A maintainer can identify required inputs for each route. The existing hook
   requires explicit `CONDUCTOR_IS_LOCAL`, its toolchain and launcher, and an
   absolute Cloud source-cache location. Composed setup additionally needs
   `CONDUCTOR_WORKSPACE_PATH`. Workspace name and ID remain unnecessary for
   installation itself. Preserve other existing source/inventory requirements.
2. Bootstrap, upgrade and setup/qualification guidance treats
   `CONDUCTOR_WORKSPACE_NAME` as optional display metadata. Absent, empty and
   whitespace-only names remain unavailable; never invent a name or substitute
   an ID while calling it a verified name.
3. Document the outcomes below. Installer acceptance means identity metadata
   does not block an otherwise valid route, not that other prerequisites pass.

| Metadata supplied | Existing installer | Consumer receipt-required wrapper |
| --- | --- | --- |
| Name and valid ID | Identity does not block | Preparation may proceed |
| Valid ID, name absent | Identity does not block | Proceed with unavailable name |
| Valid ID, empty or whitespace name | Identity does not block | Proceed with unavailable name |
| Malformed ID, with or without name | Identity does not block | Refuse preparation; setup not run |
| ID absent, empty or whitespace, with or without name | Identity does not block | Refuse preparation; setup not run |

4. Receipt-required preparation validates the supplied ID without contacting
   the host. Preparation success is not qualification. Qualification compares
   that captured ID with the authoritative host workspace record. Missing,
   mismatched or unavailable comparison evidence withholds qualification.
   Never repair original evidence with later process metadata.
5. Give an actionable safe preparation failure, for example:
   `Setup receipt needs a valid CONDUCTOR_WORKSPACE_ID from the setup process;
   setup was not run. Restore the host-provided setup environment and retry.`
   Do not print environment dumps, credential values or host identifiers.
6. Focused integration coverage explicitly sets/removes name and ID for every
   matrix case through existing setup interfaces. Cover local/cloud dispatch,
   adopted shell execution under sh and bash when available, composed-command
   success and preserved child failure. Verify existing pins and customizations
   remain unchanged. Do not impose receipt identity validation on the installer.
7. Keep three results separate: installation outcome, receipt completeness and
   automatic-startup qualification. Receipts cover the complete configured
   command and its child failures, not just the skill installation component.
8. Real-route support needs effective saved Cloud Setup readback, a fresh
   automatic run before agent/manual repair, the actual workspace binding,
   command/revision/release identity and child outcome. Record host and evidence
   limits. Fixtures or successful manual replay do not establish this result.
9. Preserve composed setup, child status, local/cloud behavior, customizations
   and release pins. Existing consumer wrappers need deliberate local repair or
   reviewed adoption; never automatically advance their pins. Verify a published
   consumer repair before linking it. If unavailable, state that limitation and
   keep its publication/qualification follow-up visible without a private link.
10. Update the changelog with a Why line, regenerate affected manifests, and
    pass relevant documentation/privacy/generated checks. Final shipping needs
    independent review and the complete canonical verifier on the final candidate.

## Existing seams and testing decisions

Use `test_conductor_setup.py`'s disposable adopted-consumer harness, the public
launcher `setup` action, adopted shell hook and composed setup command. These
exercise the supported interface rather than mocking internal metadata logic.
Strip inherited identity variables before setting each case. Expected outcomes
come from the table above. Run the existing preservation/failure tests alongside
the new matrix; add meaningful assertions at these seams as needed.

No new production module, receipt implementation or parallel installer is
needed. The external receipt/checker is reviewed against the documented contract
when its published repair is accessible. Do not create a fake receipt checker
in tests and present it as consumer coverage. New fixture coverage establishes
installer independence only; receipt enforcement is an external evidence gate.

Documentation-only contract additions use focused document checks and scenario
review; no tautological string-presence tests. Browser/device QA: n/a — no UI.

## Proposed work package

One agent-executable package: update guidance and add the deterministic setup
matrix, then run focused checks and fresh independent standards/spec review.
Review returned defects, rerun affected checks, and reserve the full verifier
for the final shipping candidate. Detailed proposed breakdown is in
[slices.md](slices.md); accepting this plan can also approve that single slice.

## Out of scope

Consumer source edits, automatic upgrades, settings changes, new receipt APIs,
live workspace creation, expanded historical support claims, and unrelated
active features. Publication, merge and live qualification remain separately
gated. The current repository remains a maintainer checkout without consumer
runtime state.

## Scope and coherence checks

Scope-guardian: one existing test harness and existing guidance entry points;
no new abstraction or installer. Coherence: installer identity independence is
distinct from strict consumer receipt preparation; format validity is distinct
from host binding; guidance can ship while qualification remains unproven.
Terms agree with [GLOSSARY.md](../../GLOSSARY.md).

## Open evidence and maintenance

No unresolved product decisions. Original automatic setup logs, effective saved
settings and a verified published consumer repair are unavailable. They block
claims about that live route, not this guidance/test work. Track private source
locators outside the public tree. Recheck host contracts at monthly maintenance
and explicit relevant upgrades, verify compatibility, then migrate through the
existing reviewed adoption path with customizations preserved.

Specification job binding returned `configured: false`. This is direct stage-03
synthesis of confirmed decisions, not an implicit invocation of an explicit-only
upstream skill. The owner accepted the plan and authorized implementation, verification, PR
merge, then a separate retrospective PR.

## Planning verification and handoff

Markdown conventions, edition link integrity, public-content checks, generated
manifest verification and diff whitespace checks pass with Python 3.11. Local
planning links were checked separately. No full shipping verifier or new
metadata integration matrix has run during planning. The earlier existing
host-dispatch regression passed; it is not coverage for the new matrix.

Maintainer tracking uses `planning/STATUS.md`; no consumer runtime state is
created. Existing unrelated features retain their owners and status.

```yaml
playbook_result:
  outcome: handoff
  next_stage: '08'
  required_actions:
    - Independently review the exact implementation candidate.
    - Verify shipping and PR review gates before the authorized merge.
    - Keep live startup qualification separate from guidance/test acceptance.
```

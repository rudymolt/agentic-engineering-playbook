# Playbook configuration — execution status

Build-all approval on 2026-09-29 supersedes planning snapshots saying build scope is unselected or implementation is unauthorised. The specification and slice criteria remain the approved product contract.

## Scope and route

- Implement S1–S7 sequentially, with tests and fresh independent verification for each exact candidate.
- Coordinator/Plan: GPT-6.1 Sol/high. Build and ordinary repairs: GPT-6.1 Sol/medium. Verify/review/QA: fresh GPT-6.1 Sol/high. Escalated repair: GPT-6 Astra/high.
- Standard pace; fast mode off. Runtime identity must match before dispatch; no silent model substitution.
- After three cumulative unsuccessful ordinary repairs on one slice, at most two Astra diagnose-and-implement cycles, each followed by fresh Sol/high Verify. Preserve failure history across workers.
- No invented time, token, cost or dispatch ceiling. User Stop, HITL, ambiguous requirements/evidence, human-owned decisions, repeated failure/no-progress guards, exhausted escalation and actual quotas remain stop conditions.
- Public-content and privacy checks precede commits and publication. No merge, release or deployment. No paid comparison benchmarks.
- This is the maintainer checkout, not a bootstrapped consumer project; do not create root runtime state to track this feature.

## Slice ledger

| Slice | Build | Independent verification | Candidate / evidence |
| --- | --- | --- | --- |
| S1 | Accepted after ordinary repair 3 | Pass (fresh independent Verify, all 10 criteria) | Candidate `9568126` replaces timestamp-dated conflict detection with one content-digest check after durability steps; that check is the completion point. Independent Verify: 37 focused tests and 11 new independent tests pass on Python 3.11 and 3.12; full unskipped canonical verifier passes. Earlier probe expectations that contradict the approved completion point, and a fabricated-discovery-adapter probe outside the documented adapter contract, are recorded in private evidence. Two unsuccessful ordinary repairs retained; no escalation used. |
| S2 | Ordinary repair 3 pending | Fresh re-verification pending | Candidate `ef19432` was rejected for S2-QA-001 (unsaved drafts lost after recovery); `00fd3d4` was rejected for S2-QA-002 (local preference write while project recovery was already pending); `2d27d4e` was rejected for S2-QA-003 (other-store recovery arising during staging did not stop publication). The latest verifier's existing 55 focused tests on both Python versions, 283 main-script tests, both prior boundary suites, privacy and manifest checks passed; its new mid-save test failed, so the full canonical verifier was not run. Two unsuccessful ordinary repairs are retained. A third, fresh repair must preserve role drafts, both-store recovery protection and S1 completion semantics. |
| S3 | Not started | Pending | Unblocked by S1; queued after S2 (configuration writes are integrated sequentially) |
| S4 | Not started | Pending | Blocked by S3 acceptance |
| S5 | Not started | Pending | Blocked by S2 and S3 acceptance |
| S6 | Not started | Pending | Blocked by S5 acceptance |
| S7 | Not started | Pending | Blocked by S6 acceptance |
| S8 preparation | Checklist drafted | Pending final gap review | Live human checks are not complete |

Public evidence contains only redacted commands, outcomes, candidate identifiers and acceptance summaries. Private host session, routing and tool-use evidence stays outside public commits. A verifier without enforced read-only permissions must be labelled prompt-instructed/report-only, not sandbox-enforced.

## Terminal gates

The endpoint is a reviewed feature PR to `main`, accurately describing any remaining qualification. Mark it draft when S8, CI or review gates prevent a ready claim. Complete an independent whole-diff specification/test-gap review and prepare the [S8 walkthrough](host-qualification.md). Do not call this feature shipped or mark S8 live qualification complete based on fixtures or the approved mockup.

Exactly one next action: send S2-QA-003 to a fresh Build session for ordinary repair 3, then submit its exact candidate to fresh Verify.

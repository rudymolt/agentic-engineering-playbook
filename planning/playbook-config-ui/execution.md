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
| S1 | Ordinary repair 2 implemented | Fresh re-verification pending | `b0fe8be` remains rejected for false completion. Repair adds explicit completion certification and reader reconciliation while preserving external bytes and legitimate future edits. Builder checks: 34 focused tests and 10 completion/history probes on Python 3.11 and 3.12, 262 main-script tests, privacy/manifests and scoped checks pass. One unsuccessful ordinary repair is retained; full independent canonical completion remains pending. |
| S2 | Not started | Pending | Blocked by S1 acceptance |
| S3 | Not started | Pending | Blocked by S1 acceptance |
| S4 | Not started | Pending | Blocked by S3 acceptance |
| S5 | Not started | Pending | Blocked by S2 and S3 acceptance |
| S6 | Not started | Pending | Blocked by S5 acceptance |
| S7 | Not started | Pending | Blocked by S6 acceptance |
| S8 preparation | Checklist drafted | Pending final gap review | Live human checks are not complete |

Public evidence contains only redacted commands, outcomes, candidate identifiers and acceptance summaries. Private host session, routing and tool-use evidence stays outside public commits. A verifier without enforced read-only permissions must be labelled prompt-instructed/report-only, not sandbox-enforced.

## Terminal gates

The endpoint is a reviewed feature PR to `main`, accurately describing any remaining qualification. Mark it draft when S8, CI or review gates prevent a ready claim. Complete an independent whole-diff specification/test-gap review and prepare the [S8 walkthrough](host-qualification.md). Do not call this feature shipped or mark S8 live qualification complete based on fixtures or the approved mockup.

Exactly one next action: submit the exact S1 repair-2 candidate to fresh Verify. Do not start S2 before acceptance.

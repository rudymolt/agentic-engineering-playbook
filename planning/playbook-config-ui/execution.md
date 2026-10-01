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
| S2 | Accepted after escalated repair cycle 2 | Pass (fresh independent Verify, all 10 criteria) | Candidate `507a5a8` preserves reviewed personal storage under directory-alias changes, retains recovery evidence and role drafts, and preserves S1's single content-digest completion point. A fresh Sol/high Verify passed 68 focused tests on each of Python 3.11/3.12, 21 independently written tests on each, and the full unskipped canonical verifier. Three unsuccessful ordinary repairs and both Astra cycles remain counted. An earlier review of this same candidate passed technical checks but disqualified itself for reading more prior-verdict content than its brief permitted; the qualifying review used only public contract/source/tests and its own evidence. External physical relocation of an already opened personal directory remains a documented filesystem limit: recovery is reported, but another actor can move the directory into the project. This is outside the specified configuration boundary, not an absolute ancestry-isolation claim. S8 live host qualification remains pending. |
| S3 | Accepted | Pass (fresh independent Verify, all 10 criteria) | Candidate `737c974` adds five versioned job contracts, source-labelled editing, exact-source eligibility and stage-owned `job-route` entries. A fresh Sol/high Verify passed 23 independent probes on each of Python 3.11/3.12, focused and prior-slice regressions, privacy/notices/manifest checks, and the full unskipped canonical verifier (386 main and 533 delivery test executions). Production upstream review/QA remain incompatible. Project QA attestations and retained approval snapshots are trusted stage-owned inputs, not independently authenticated by Configure; stage 09 and execution gates must review their real evidence before use. S8 live host qualification remains pending. |
| S4 | Repaired candidate `f1589b1`; escalated repair cycle 2 next | Blocked (fresh independent Verify 5, one mandatory finding) | Fresh probes on Python 3.11/3.12 pass all seven earlier hardlink and diagnostic failure shapes, plus portability and stage-owner checks. A cyclic selected QA source still raises an uncaught path-bearing `RuntimeError` on public read and QA job-route, exposing a private locator and credential marker on stderr without structured recovery. The same defect reproduces on the earlier public S3 baseline; S4's privacy/error contract still requires repair. The builder's full canonical verifier passed. Independent Verify stopped its canonical run with exit 130 after the blocker, so it is not an independent canonical pass. Three unsuccessful ordinary repairs and one unsuccessful Astra cycle remain counted. The second Astra/high diagnosis-and-repair cycle is the final approved escalation, followed by fresh Sol/high Verify. |
| S5 | Not started | Pending | Blocked by S2 and S3 acceptance |
| S6 | Not started | Pending | Blocked by S5 acceptance |
| S7 | Not started | Pending | Blocked by S6 acceptance |
| S8 preparation | Checklist drafted | Pending final gap review | Live human checks are not complete |

Public evidence contains only redacted commands, outcomes, candidate identifiers and acceptance summaries. Private host session, routing and tool-use evidence stays outside public commits. A verifier without enforced read-only permissions must be labelled prompt-instructed/report-only, not sandbox-enforced.

## Terminal gates

The endpoint is a reviewed feature PR to `main`, accurately describing any remaining qualification. Mark it draft when S8, CI or review gates prevent a ready claim. Complete an independent whole-diff specification/test-gap review and prepare the [S8 walkthrough](host-qualification.md). Do not call this feature shipped or mark S8 live qualification complete based on fixtures or the approved mockup.

Exactly one next action: run S4 escalated repair cycle 2 for cyclic QA-source path disclosure, retaining the seven verified prior protections, then submit the exact candidate to fresh Sol/high Verify.

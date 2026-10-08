# Apply recovery artifact visibility — slice

## S1 — managed ignores at bootstrap and upgrade

AFK; depends on nothing. Approved by maintainer handoff on 2026-10-08.

Diagnose at public bootstrap/upgrade plus Git. Add meaningful failing tests at
the existing seams, then the minimal managed-ignore change and accurate plan
guidance. Tests cover every acceptance item in [spec](spec.md).

Verification target: focused bootstrap, transition, seed and configuration
recovery tests; fresh independent report-only standards/spec review and QA;
public privacy gate; regenerated edition manifest; canonical
`python3 v0.5/scripts/verify-playbook.py` without a short timeout; actual-head
GitHub CI. Record strict drift and cloud privilege limitations truthfully.

Status: implemented with LF/CRLF matching and regression coverage. Repair cycle
2 corrects a baseline bytecode-race test assertion; production source stays
unchanged. Record fresh review, QA, canonical and actual-head CI outcomes in the
product PR and cloud artifacts before the ready-PR handback. Not merged.
Delivery endpoint: ready PR, never merge.

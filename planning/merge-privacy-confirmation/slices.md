# Merge privacy confirmation — slice

## Slice 1: reuse the confirmed repository/account pair

- Type: AFK; depends on nothing.
- Outcome: repeated merges by the confirmed pair avoid the repeated setting
  prompt, with all identity and privacy gates preserved.
- Contract: [spec](spec.md); rationale: [alignment](alignment.md).
- Build: implement the bounded instruction/record change and the privacy-gate
  exception with regression tests. Add the changelog Why line and regenerate
  affected manifests/status. Keep the existing branch name.
- Verify: execute all six instruction scenarios and positive/negative privacy
  cases, focused checks, fresh independent review, and the full final-candidate
  verifier. Inspect PR review threads/comments and required CI before readiness.
- Endpoint: verified implementation and reviewable PR against `main`; no merge
  or release. Findings return to the same scope with fresh verification.

Status: implemented; privacy TDD and focused checks pass. Fresh independent
review, full final-candidate verification and PR checks remain required before
readiness. Sol Build uses GPT-6.1 Sol/medium, standard pace. Runtime launch
evidence stays in local evidence, not this public planning record.

Report progress at ordinary checkpoints; no hard duration was selected. Stop
on explicit Stop, a real authority/quota boundary, or three identical failures
or no-progress attempts. Plan capacity for the full verifier and fresh review.

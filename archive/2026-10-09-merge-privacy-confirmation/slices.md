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

Status: shipped in PR #39 on 2026-10-09 as `98886bd`. Privacy TDD,
focused checks, fresh Sol/high review and the full canonical verifier passed
on candidate `9bcba3b`; both PR CI jobs passed and the addressed review thread
was resolved. Post-merge readback confirms noreply author and committer.
Runtime evidence remains local. Human feature retro: no further promotion.

Report progress at ordinary checkpoints; no hard duration was selected. Stop
on explicit Stop, a real authority/quota boundary, or three identical failures
or no-progress attempts. Plan capacity for the full verifier and fresh review.

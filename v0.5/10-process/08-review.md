# 08 · Review — post-code, pre-ship

> The stage-owned standards/spec axes cover fidelity; playbook adapters/manual routes cover the role reviews. Run before every PR.

**This stage in one breath:** Run the reviewers that find what the tests don't — security, performance, design, devex. Output: a PR judged safe to merge, or a concrete fix list.

---

## The verifier definition

This is the canonical definition for review and QA gates. A verifier is a checker that receives the goal, the diff or changed workspace, the tests, and relevant docs — not the implementer's reasoning transcript. Its stance is: assume the change is broken until proven; verify by executing (run tests and paste real output; for UI, drive the browser), never by reading alone.

At or above the ladder rung "new behaviour across modules", the verifier is mandatory and non-collapsible: it must be a different agent in a fresh context, never the implementing session. Security and irreversible-data checks are never self-certified. Below the mandatory rung, review may collapse into the implementer if the ladder allows it.

The stage-11 regression-test exception is also non-collapsible: a second, fresh
verifier independently runs the recorded alternative (or an equivalent runtime
check), inspects the retained reproduction and diagnosis, and accepts or rejects
the remaining gap. Reading the builder's report is not execution. If reliable
evidence is unavailable, the change is blocked.

The verifier runs in the strongest read-only / report-only mode the host supports. A checker that edits product code has become a generator, and its change re-enters independent verification.

Model independence reads in three steps, in this order:

- **Default:** same model, different agent, fresh context, no transcript. Most of the benefit comes from the checker never seeing the implementer's reasoning, and this default needs no second provider.
- **Escalation:** a different model (`/codex`) for security-sensitive, irreversible-data, or large-blast-radius changes. A different model is the strongest form of model independence; reserve it for the changes that justify it.
- **Non-mandate:** "always a different model" is never a requirement. A project without `/codex` fully meets this stage with the default plus the remaining ladder rungs: read-only enforcement, verify-by-acting, adversarial stance, deterministic gates, and the human checkpoint.

The independence fallback ladder, strongest available first (an availability ordering for degrading gracefully, not a preference order — the default above is rung 2):

1. Different model, fresh context, no transcript.
2. Same model, fresh context, no transcript.
3. Read-only enforcement: the checker cannot edit code.
4. Verify-by-acting: tests run, browser driven, real output pasted.
5. Adversarial stance: assume broken, demand evidence.
6. Deterministic gates: CI, lint, secret scan — no model at all.
7. A cheaper sibling model as checker where available.
8. The human merge, the permanent final checkpoint.

For an approved delivery mission, the checker additionally emits the manifest-
owned launcher and verdict receipts bound to the frozen head and tree.
Conductor checkpoint-writing checkers use Launcher V4 and its companion session
lifecycle record; exact commands and the monitor must complete before the turn-
end checkpoint. Any unowned write, missing provenance, later-produced artifact,
or identity mismatch is nonqualifying.

The human merge remains the default permanent checkpoint. Only a separately
admitted K4.1 fresh session may replace that click for an eligible exact head;
it performs a new review and verification from durable evidence and stops at
merge. K4.1 does not make a builder's review self-certifying.

At the Verify boundary, use [`../93-model-routing-track.md`](../93-model-routing-track.md). The OpenAI default is GPT-6 Sol/high; `models` exposes verified alternatives. Verification always starts in fresh context without builder chat. If the active Build run selected `fast`, inherit that pace only when the fresh Codex/host route proves fast mode available; pace never changes the Verify model, reasoning, read-only boundary, evidence, or gates, and it clears when verification hands control back. Show “read-only” only when the selected runner enforces it, and reject output when authoritative runtime metadata does not match the selected route. Never use the model's generated self-description as identity proof.

Findings and verdicts carry typed evidence scaled by the ladder. At or above cross-module, include scope/acceptance criteria checked, diff or commit range, exact commands or browser flows run, pass/fail with visible result, artefact paths (logs/screenshots) where relevant, severity + confidence per finding, and verdict (`pass` / `blocked` / `pass-with-accepted-risk`). Below cross-module, one line is enough: command + result. Evidence without provenance is narrative.

If review must resume in another session, worker, or host, use the conditional
[pickup brief](pickup-brief.md) with the exact candidate, verdict/evidence, and
remaining gates. The next verifier remains fresh and receives artifacts rather
than builder or reviewer transcripts.

For a disputed historical rationale, `/ai-playbook-why` returns cited evidence
with inference, contradiction, and unknown labels. For a bounded behavior path,
`/ai-playbook-how` distinguishes source-read interpretation from executed runtime
evidence. These investigations inform review; they do not replace execution.

For a concrete revision, `/ai-playbook-blast-radius` records each material
safety assumption with affected-code evidence or an explicit unproven risk. It
informs this review without changing risk classes, authority gates, mandatory
tests, or fresh-verifier requirements.

## When to run

- After stage 07 produces a green slice.
- Before opening a PR.
- Any time a user says "is this safe to merge?"

## First pass: standards and spec fidelity

Use a direct upstream reviewer only after
`../scripts/check-upstream-compatibility.py` confirms the resolved installed source has
report-only compatibility and prints the permitted embedded entry point. The tested Matt
`/code-review` source does not currently qualify because it can route into repository setup;
use the two manual axes below. An unknown or drifted source takes the same fallback. Run the
pass on the diff since the slice's fixed point before the role-specific reviewers:

- **Standards** — does the diff follow the repo's coding standards, plus a Fowler code-smell baseline?
- **Spec** — does it faithfully implement the originating issue/spec?

This natively implements two rules this stage already mandates: the verifier as a fresh context that never sees the implementer's transcript, and planning intent (spec/slice goal) as an explicit review input. It complements rather than replaces the gstack reviewers below — they still own security, design, and devex.

For an explicitly adopted verification harness, an entry-point change also names
the affected map entry for the owning stage-10 doc-close check. This is a
conditional review responsibility, not a watcher or a maintenance-audit pass;
the complete coverage route remains `/ai-playbook-maintain-verification-harness`.
Only an accepted complete clean/changed result from that route can later supply
maintenance-clock credit.

The two-axis dispatch is harness-neutral as of Matt v1.2.3. Use the host's available parallel-agent mechanism; do not require Claude Code's `Agent` tool or `general-purpose` agent type. If the host cannot run two parallel agents, run the same isolated briefs in separate fresh contexts and keep the reports separate.

The Fowler baseline (~12 named smells, always on) carries two binding rules that match this stage's severity/action-tag discipline: a documented repo standard **overrides** the baseline, and every smell is reported as a **judgement call**, never a hard violation — use `consider` for actionable optional improvement, `no-op` for information, or `ask-user` only for a decision that actually needs the human; never `auto-fix`. Note also that as of upstream v1.1.0, `/code-review` owns the **refactoring rules** that used to live in `/tdd` — structural improvement happens here, under review discipline, not mid-implementation.

## Which review to run

A decision tree, depending on what the change touches:

| Building for… | Pre-code (stages 01–03) | Post-code (this stage) |
|---|---|---|
| End users (UI) | `/plan-design-review` | `/ai-playbook-design-review` |
| Developers (API, CLI, SDK, docs) | `/plan-devex-review` | compatible report-only `/devex-review`, otherwise execute and time the flow manually |
| Architecture | `/plan-eng-review` | compatible report-only `/review`, otherwise use the adversarial lens below |
| All of the above | `/autoplan` | run every applicable report-only/manual route |

For UI work, `/ai-playbook-design-review` explicitly reports the responsive and URL-state floor: desktop/tablet/mobile, horizontal overflow, mobile tap targets, table wrapper readability, heading hierarchy, compact-control exceptions, drawer/filter/link/row-expansion transitions that affect scroll or focus, and live filters that avoid native form submission when context should remain in place.

**Run the security pass on ANY change** that touches:

- Authentication or authorisation
- Payments
- User data
- Public endpoints

…regardless of category. Use `/cso` only when its resolved source passes the embedded
compatibility check; otherwise perform the OWASP Top 10 + STRIDE pass manually using this
stage's security section. The evidence requirement is identical.

## Optional: second opinion

`/codex` for the cross-model rung of the verifier definition above. Use on high-stakes changes (security-sensitive, irreversible-data-touching, large-blast-radius). Doubles cost — use deliberately, and keep cross-model escalation and any multi-reviewer pattern under the §11 budget floor.

## The adversarial lens inside the single review pass

C1a remains the default: one independent verifier, fresh context, no implementer transcript. The V0.3 T8 run did not justify promoting a review panel to default, so the cheap part of the panel becomes a checklist inside the single pass:

- Break the change across boundaries: unauthorised caller, missing precondition, stale state, empty input, largest expected input, timeout, retry, rollback.
- Compare the diff to the stated spec/slice goal: what changed outside the goal, and what goal requirement has no code or test evidence?
- Probe trust boundaries: auth, public endpoints, user data, secrets, external APIs, schema or migration reversibility, irreversible data.
- Ask which tests can pass while the product still fails: untested path, boundary value, integration edge, browser flow, or deployment assumption.
- Deduplicate and rank the findings into one list with severity, confidence, action tag, and evidence.

## What the reviews produce

- Architecture/runtime pass — bugs that pass CI but fail across real boundaries.
- `/ai-playbook-design-review` — responsive, design-language, and URL-state evidence.
- Developer-experience pass — exercised onboarding and measured *time-to-hello-world*.
- Security pass — OWASP Top 10 + STRIDE threat model.
- `/codex` — optional cross-model independent review.

Every item above is report-only. A finding accepted for remediation becomes a separate
generator task owned by stages 07/09, uses the project-selected commit strategy, and returns
to a fresh verifier. An upstream auto-fix workflow may still be run when the human explicitly
requests it as the top-level workflow, but it does not certify its own output or serve as this
embedded gate.

Every finding carries severity and an action tag:

- `auto-fix` — objective and eligible for a separate generator task.
- `ask-user` — intent-sensitive or ambiguous; pause and relay.
- `consider` — actionable optional improvement; advisory, nonblocking, and
  never eligible for automatic remediation.
- `no-op` — informational.

For a constraint that exists only as a warning comment, require the cheapest
in-scope type, test, runtime check, or CI rule when practical; see foundations
§2. Retain licenses, external constraints, public API contracts, and rationale a
check cannot express. Do not turn this check into unrelated comment cleanup.

Auto-fix attempts are bounded (default 3). When the bound is hit, pause and escalate rather than loop. Reserve `ask-user` for judgement calls that need a human decision: questioning a deliberate product/design choice, undoing a deliberate addition, or insufficient test evidence. The planning intent (spec/slice goal) is an explicit review input: the reviewer checks "does this diff do what it set out to do?", not just "is this code clean?".

**Settled-decision triage.** Every intent-sensitive finding must state its relationship to the recorded decisions (spec, ADRs, approved slice goal): it *contradicts* a recorded decision, it *proves the decision cannot work* (with evidence), or it is *a preference* for a different approach. Only the middle case keeps full severity against the decision. A contradiction routes to `ask-user` and names the decision it conflicts with; an actionable preference is advisory `consider`, while information is `no-op`; neither blocks. A defect *inside* the agreed approach is unaffected — this rule reduces re-litigation churn without shielding settled decisions from real evidence.

Show evaluated but dismissed findings once, deduplicated, with a concise
evidence-based reason in the existing review output. Do not expose internal
deliberation transcripts. A concrete defect keeps its severity and cannot be
hidden as `consider`.

For `build all`, an `auto-fix` is eligible for automatic remediation only under stage 07's full bounded rule: concrete evidence, approved scope, reversible change, no human-owned decision, fewer than three identical failures, and continuing progress. Each fix is a fresh generator task and must return to fresh independent verification.

If a repository-wide check fails outside the diff, classify it rather than hand-wave it: run once on the feature branch and once at the merge base in an isolated temporary worktree, compare failure signatures, and require changed-path tests to pass. Record a matching baseline failure separately; block when it undermines reliable assessment.

## The security pass (every PR, V0.2.5)

Three questions, answered explicitly in the review output — not assumed because `/cso` exists:

1. **Boundaries:** does every input this change introduces (user input, file content, API response, env value) get validated where it enters?
2. **Secrets:** does the diff add any credential, token, or key to a tracked file, test, or fixture, and does any command, test, or captured evidence it introduces dump the environment or the process table? (The floor rules are `../00-foundations.md` §10 — report to a human, never just delete.)
3. **Dependencies:** does the diff add or bump a dependency, and if so is it named and justified in one line in the PR description, with the lockfile updated?

A "no" on any of these blocks the PR until resolved. PRs touching auth, payments, user data, or public endpoints additionally run the compatibility-gated or manual security pass (the event cadence enforces this).

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
last_run:
  review: {ISO timestamp}
  cso: {ISO timestamp if run}
```

---

## Next

- Review clean → open `09-qa.md`
- Issues found → return to `07-implementation-tdd.md` with the fix list
- Unsure → run `/whats-next`

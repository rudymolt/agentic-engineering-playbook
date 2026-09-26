# 91 · Optional delegation track — anchored specs, independent verification

> This track is optional. It is not one of the 13 stages, and it changes nothing about them. It defines how to execute a **multi-phase change** through two agents — an implementer and a verifier — with the human merging, when doing the whole change in one head would leave it unverified.

Use this track when a change spans many files or several releases, when the work will be executed by a less capable (cheaper) agent, or when the author of the plan should not be the only party checking the result. A single small change does not need it; just make the change and verify it on the ladder (`00-foundations.md` §4).

The unit of delegation is a **phase**: one coherent release with its own branch, CHANGELOG entry, and verification commands. Phases execute strictly in order, merged between.

## The four artefacts

The pattern runs on files, not on chat memory. All four live in the repo (this playbook keeps them in `analysis/`):

1. **The review** — findings with file-level evidence; every claim verified against the tree before the plan is written.
2. **The plan (anchored spec)** — per-phase numbered edits with exact old/new text, per-phase verification commands, and the ground rules. Decisions the human has already made are recorded in the header so no agent re-asks them.
3. **The runbook** — the operator's loop plus verbatim prompts: implementer prompt, verifier prompt, fix-cycle prompt, escalation prompt. Once it exists, a one-line pointer ("execute Prompt A for Phase N") is a sufficient instruction.
4. **The amendment log** — a dated line in the plan header for every spec change mid-execution, so no agent ever runs against silently-moved instructions.

## The roles and their rules

**The implementer** executes one phase exactly as written. Its governing rules: do only the named phase; never re-litigate recorded decisions; surgical edits only; **stop and report if the tree does not match the plan** — never improvise around a mismatch; run the phase's verification commands and paste real output before declaring done.

**The verifier** is the stage 08 verifier applied to a phase: fresh session, never shown the implementer's transcript, read-only on the implementation. It walks every numbered item against the diff, re-runs the verification commands, and **repeats the implementer's self-tests independently** — injected checker violations, fixture runs, exit codes — rather than trusting pasted output. Verdicts use the stage 08 shape: pass / blocked / pass-with-accepted-risk, findings with severity, evidence, and an action tag.

For read-only exploration that informs a phase, foundations §9 is canonical:
start with targeted reads, delegate only bulky independent work when useful,
keep summaries bounded with source locators and unresolved facts, and use
bounded serial reads when no subagent is available. The lead inspects cited
artifacts, relevant diffs, and evidence, resolves gaps, and writes its own
synthesis; a delegate's success claim is not proof and does not replace this
stage-08 verifier.

**The human** merges — every phase, no exceptions — and owns the two decisions the pattern cannot make: accepting a pass-with-accepted-risk, and changing a recorded decision.

**Fix cycles are bounded.** A blocked phase returns to the implementer with the verifier's findings attached, framed as fresh tasks (the stage 07 rule). After two blocked cycles, roles flip: the verifier (or a stronger agent) implements, and someone else — at minimum the human — checks the result, because a spec author must not be the sole checker of their own code.

## The three rules experience added

- **Execute the spec's verification commands against the current tree before handoff.** In this playbook's first full run of the pattern (V0.3.20–24), all four caught defects were in the spec — and every one would have surfaced by running the plan's own greps at authoring time. A verification command written from memory of the tree is a guess wearing a uniform.
- **An implementer that stops beats an implementer that improvises.** Both spec defects that reached execution were converted into cheap round-trips by the stop-on-mismatch rule. Select and prompt for stopping, not for pushing through.
- **The verdict is a committed artefact.** Stage 08 already rules that evidence without provenance is narrative; the same holds for the verdict itself. Record each phase's verdict — at minimum the verdict line and its findings — in the PR body or a committed report, never only in chat. (Added at this track's own independent review, which found the train's verdicts lived only in session transcripts.)

## Session hygiene

- One phase per implementer conversation; one review per verifier conversation; fresh both times.
- Never paste the implementer's transcript to the verifier — that separation is what makes the review independent. (A verifier with deep *spec* context is fine; it is implementer-reasoning contamination the pattern forbids.)
- Merge before starting the next phase. Stacked unmerged phases turn one bad merge decision into five.
- When a merge or rebase does conflict — the common case when provably-independent slices ran in parallel worktrees (stage 07's fan-out rule) — use `/resolving-merge-conflicts` (Matt; present and unchanged in the released v1.2.3 inventory): a standalone loop for resolving an in-progress conflict from primary-source intent, rather than ad-hoc conflict-marker surgery. The resolved merge still passes through the phase's verification commands before it counts as done.

## Relationship to the other tracks

This track is human-orchestrated and conversational — the human triggers each phase and each review. The loop track (`90-loop-track.md`) is the scheduled, unattended shape; a delegation phase can run *inside* a loop only after the loop track's own earned-autonomy conditions are met. Both tracks sit on the same rails: the stage 08 verifier and the §11 floor.

**Optional discovery track:** [`92-wayfinder-track.md`](92-wayfinder-track.md) uses `/wayfinder` (Matt, v1.2.3) to clarify efforts too big and foggy for one session through a tracker-resident map of *decision* tickets. Wayfinder discovers the route; this track executes an already anchored multi-phase route. A completed map may graduate into a delegation plan, but delegation phases are implementation work and never remain on the Wayfinder decision frontier.

## Provenance

Delegation uses an anchored spec, explicit handoff, and independent verification to keep multi-phase work reviewable. Record new public evidence before expanding its authority.

**Validation note:** record this track's use in public field reports; narrow or demote it if the documented handoff fails to transfer across projects.

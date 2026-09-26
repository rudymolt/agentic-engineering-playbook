# 90 · Optional autonomous loop track

> This track is optional and opt-in. It is not one of the 13 stages, and the default process remains human-led. A project earns it; it is never the entry point.

Use this only after the normal playbook has proved its brakes on the project itself. A loop is a scheduling shape around the existing stages, not a replacement for alignment, slicing, review, QA, shipping, or human judgement.

The loop does not make decisions for the project. It wakes up, checks the recorded state, runs the bounded work that is already eligible, verifies it through the existing gates, records evidence, and stops at a human decision.

The unit of work is still a slice or maintenance task with an explicit verification target. If the next action would require product judgement, missing acceptance criteria, a UI approval, or an irreversible operation, the loop stops before doing it.

Good loop candidates are repetitive, low-judgement, and already well-gated: dependency refresh checks, scheduled QA passes, stale-doc detection, or back-to-back AFK slices from one active feature.

Poor loop candidates are ambiguous, exploratory, or political: deciding product scope, changing architecture direction, designing a new UI surface, or touching production data without a rehearsed reverse.

## The shape of a loop

| Move | Loop part |
|---|---|
| Discovery | Automations or scheduled tasks notice due work and open the right stage. |
| Handoff | Git worktrees isolate implementation slices so parallel work cannot overwrite itself. |
| Verification | Sub-agents provide the §9 reviewer role: the stage 08 verifier checks with evidence. |
| Persistence | Memory lives on disk in state files, planning folders, and reports, not in chat. |
| Scheduling | Automations or cron decide when the next loop wakes up. |
| External reach | Connectors (MCP) let the loop read or update the outside systems it is allowed to touch. |

A healthy loop is boring. It has a small trigger, a narrow working set, a visible stop condition, and a report the human can audit without reconstructing the whole session.

The worktree is the isolation boundary for writes. State files and reports are the memory boundary for everything else.

Keep the loop narrow enough that a failed run can be understood from its report and diff. If the human must reconstruct several conversations to know what happened, the loop is too broad.

## Local vs cloud scheduling

Local scheduling means scheduled tasks or cron on the developer machine. It is simple, visible, and easy to stop; it also dies when the laptop sleeps, the repo moves, or local credentials expire.

Use local scheduling first when the task is personal, low-frequency, or still being tuned. It is the right place to prove that the loop pauses cleanly and produces a useful report before moving it anywhere more persistent.

Cloud scheduling means CI-hosted schedules. It survives the laptop and fits longer-running maintenance loops, but secrets and permissions must follow the §10 security floor before any connector or deploy key is available to the loop.

Use cloud scheduling only when the task has earned persistence. The extra reliability is useful only if the permissions, evidence trail, and human checkpoint are at least as clear as they were locally.

Moving a loop from local to cloud is a separate change. Review the trigger, secrets, write permissions, and stop report before trusting the schedule.

## Non-negotiables

- Per-slice independent review stays mandatory; use the stage 08 verifier.
- The §11 floor applies, including the four-part ceiling-stop report when a loop pauses.
- AFK/HITL slice gating holds; stage 04 decides what can run without the human.
- The UI preview gate still holds inside loops; use the frontend track before UI code.
- A permanent human checkpoint remains; every loop ends at a human decision.
- The merge is the human's act; stage 10 does not become an auto-merge step.
- The doc-close guard holds; a loop never archives a live planning folder.
- Earned, not granted: turn this track on only after project field evidence shows the verifier catching real defects and a ceiling stop working; `analysis/field-reports/` is the worked example of that evidence.

The shortest acceptable loop report says what woke the loop, what slice or task it touched, what evidence passed, where it stopped, and which human decision is now needed. Anything less invites the human to nod through work they cannot inspect.

Do not promote a loop because it feels convenient. Promote it because the project has already demonstrated the two brakes this track depends on: independent verification catches real defects, and the ceiling stop pauses with a usable report.

Do not widen a loop silently. New triggers, new write permissions, new connectors, or a broader slice set are scope changes and go back through the same human checkpoint.

Provenance: Addy Osmani's *Loop Engineering* and [Intelligent Internet's Zenith](https://github.com/Intelligent-Internet/zenith) informed the emphasis on independent verification, stopping discipline, and legible coordinator decisions. Zenith is an optional external tool for ultra-long tasks, never a dependency.

# Prerequisite capability profiles

> Reference for stage 00. The gate is capability-based: required outcomes must have either a verified tool route or the manual procedure named here. Skill packages accelerate the process; their names are not the invariant.

Last host-documentation verification: **2026-07-10**. Re-check through [`../MAINTENANCE.md`](../MAINTENANCE.md) when the monthly upstream cadence is due.

## The blocking rule

A session may proceed when every capability required by the work has a verified route. A route can be:

- **structural** — the host or repository enforces it;
- **tool-assisted** — an installed skill performs it;
- **manual** — the agent or human follows the named stage procedure and records the same output.

If none exists, halt at stage 00 and name the missing capability. An unavailable optional accelerator is reported as profile information, not as a failed gate.

## Required capability lanes

| Capability | Tool-assisted route | Manual route | Halt when |
|---|---|---|---|
| Read, edit, diff, and verify the repository | Host file/shell tools | Human runs the exact commands and returns the output | Neither the agent nor human can inspect the diff or execute the required verification |
| Human-owned decisions during alignment | `/grill-with-docs`, `/grill-me`, planning reviews | Follow stage 01's facts-versus-decisions checklist; ask decisions and wait | The agent cannot reach the human for a decision labelled HITL |
| Spec and vertical-slice contracts | `/to-spec`, `/to-tickets` | Write the required sections from stages 03 and 04, including acceptance criteria, test seams, dependencies, and verification targets | A build would begin without approved acceptance criteria or a verification target |
| Test-first implementation and diagnosis | `/tdd`, `/implement`, `/diagnosing-bugs`, `/investigate` | Run the red→green loop in stage 07 or the reproduce→hypothesise→verify loop in stage 11; redact displayed evidence | The stack's tests/reproduction cannot be run and no equivalent observable check exists |
| Independent verification at the ladder's required rung | Compatibility-gated report-only reviewer, `/ai-playbook-design-review`, host subagent in a fresh context | Start a separate context with only the spec/diff/evidence, or use a human checker; preserve the verdict | Cross-module or higher-risk work has no separate checker able to execute verification |
| Real-environment QA when the ladder requires it | Compatibility-gated report-only browser skill | Human or agent follows stage 09 in a real browser/device and records evidence | The acceptance criteria require an environment that nobody can exercise |
| Security and secret handling | Compatibility-gated security reviewer, host permission/sandbox controls | Apply stage 00 Check E and stage 08's security checklist; keep secrets in ignored environment storage and redact diagnostic evidence before display | Secret exposure cannot be contained or a required trust boundary cannot be reviewed |
| State and document lifecycle | `compute-status.py`, `/whats-next`, `/document-release` | Update the state/status blocks and run the doc-close checklist by hand | Project state cannot be reconciled with observable files and git evidence |
| Stage-aware model routing | `/model-router`, host model catalogs, provider CLIs | Use the OpenAI lane default in the current session, or perform the documented Conductor handoff and record identity evidence | The selected route cannot prove model identity, required permissions, fresh Verify context, or handoff delivery |

## Profiles

### Core profile — required

Every required lane above has a working route. This profile is sufficient to run the playbook. Manual routes are first-class only when they produce the same named artefact or evidence as the tool-assisted route.

### Accelerated profile — optional

Matt Pocock skills and gstack are installed and verified. Use their procedures at the stages that name them. A missing accelerator falls back to the manual route for that lane; it blocks only if the manual route is also unavailable.

For Matt v1.2+ skills, invocation metadata is dual-harness: Claude Code reads `disable-model-invocation`; Codex reads `agents/openai.yaml → policy.allow_implicit_invocation`. Verify both surfaces agree before treating a user-owned workflow as unavailable to model invocation. Picker metadata alone does not grant authority.

### Extended profile — situational

Optional tools such as persistent cross-project memory, design exploration, Wayfinder, benchmark runners, deployment canaries, or browser automation are enabled only when the project and stage need them. Their absence does not weaken unrelated stages.

Record the selected profile in `.playbook-state.yml → decisions.capability_profile`, the actual lane-by-lane routes under `capability_routes`, and the audit timestamp at `capability_routes.verified_at`. A route value names its kind and implementation, for example `tool: /tdd`, `structural: Codex workspace sandbox`, or `manual: stage 09`. Profiles describe available routes; they do not lower acceptance criteria or the verification ladder.

## Host enforcement matrix

| Host | Instruction discovery | Structural controls to verify | What remains prompt/manual unless configured |
|---|---|---|---|
| Claude Code | Project `CLAUDE.md`, `.claude/rules/`, and skills; `AGENTS.md` needs an import or symlink | Permission settings, sandbox settings, hooks, and separate subagents | `CLAUDE.md` is context rather than enforcement; independent review still needs a fresh subagent/session and executed evidence |
| Codex | Layered `AGENTS.md`/`AGENTS.override.md` plus skills | Approval policy, workspace sandbox/permission profile, hooks, worktrees, and subagents | A prose rule is guidance; verify the active sandbox/approval profile and give the checker a fresh context |
| Cursor | `.cursor/rules`, root `AGENTS.md`, and root `CLAUDE.md` in the CLI | Foreground CLI command approval | Do not assume a read-only background agent: Cursor documents that background agents auto-run commands and have internet access; use a separate foreground session or human checker when read-only isolation matters |
| Conductor | Loads the selected harness in one chat tab; tabs in a workspace share branch and files | Controls the workspace and tab selection; underlying harness may add stronger controls | Conductor is not a provider or read-only sandbox. Name the actual Codex, Claude Code, Cursor, or OpenCode route and use a manual new-tab handoff when no verified sidecar exists |
| OpenCode | Project instructions plus provider-qualified model catalog | Runner-specific permissions and provider authentication | Broad model availability does not prove isolation or identity; validate the reported provider/model and permission boundary |
| Generic agent | Only the instruction files and tools the host demonstrably loads | None assumed | Use the manual routes above; the human runs commands and acts as the independent checker when the host cannot enforce separation |

Primary host sources:

- Claude Code: [project memory and enforcement distinction](https://code.claude.com/docs/en/memory), [subagents](https://code.claude.com/docs/en/sub-agents), [settings](https://code.claude.com/docs/en/settings)
- Codex: [AGENTS.md discovery](https://developers.openai.com/codex/guides/agents-md), [CLI approvals and sandbox reference](https://developers.openai.com/codex/cli/reference)
- Cursor: [CLI rules and command approval](https://docs.cursor.com/en/cli/using), [rules](https://docs.cursor.com/context/rules-for-ai), [background-agent security model](https://docs.cursor.com/background-agent)

## Cold-path completion criterion

The cold path is complete only when the selected profile and all nine route values are recorded in state, `capability_routes.verified_at` is current, every required lane for the expected work has a route, host structural claims have been checked against the current runtime, any missing optional accelerator has a recorded fallback, and `prereqs_required` has been reset to false.

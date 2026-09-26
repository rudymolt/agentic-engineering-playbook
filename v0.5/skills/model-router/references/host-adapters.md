# Model-routing host adapters

Read only the active host and runner section.

## Conductor

Conductor is the shared workspace and coordinator, not a provider. Each chat tab has one harness/model while tabs share files and branch state. Prefer an automatic identity-verifiable sidecar. Otherwise write the handoff, tell the human which harness/model to choose in the model picker, and state that a new tab opens. Conductor alone does not enforce read-only files. Fast mode is an agent/session control, not a repository model default; preserve a selected run pace when opening the Build or Verify tab, and report when the chosen Codex route cannot apply it.

## Codex

Prefer project custom agents under `.codex/agents/` or a separate `codex exec -m <model>` invocation. Plan and Verify use read-only sandboxes; Build uses workspace-write. Discover the runtime's `fast_mode` capability before promising fast pace; when selected, apply it without changing model or reasoning and record `pace: fast` in the handoff. Verify spawned-session metadata before accepting output: correlate the emitted thread ID with the runtime's recorded model (`threads.model` in the current Codex CLI), or use an equivalent first-party metadata surface. Do not ask the agent to identify itself; generated self-description is not runtime evidence.

## Claude Code

Use `.claude/agents/` and native Claude subagents for available Claude models. Use an authenticated provider sidecar for non-Claude routes. Apply model, tools, permission mode, and isolation in agent metadata where supported.

## Cursor

Use `.cursor/agents/` or runtime model selection. Check host/session metadata because plan type, Max Mode, availability, or administrator policy can override the request. In Conductor, describe Grok as a Cursor route when discovery reports it that way.

## OpenCode

Prefer OpenCode for broad Conductor-native provider access when its live catalog contains the model. Preserve the provider-qualified model ID. Broad access does not prove isolation; enforce the same identity, permission, and fresh-context gates.

## Generic hosts

Use isolated provider CLI calls with explicit model and permission arguments. Make no native-subagent assumptions. Prefer provider response/session metadata for identity. Require human verification when fresh context or read-only operation cannot be enforced, and treat identity as unverifiable when neither the provider nor host exposes authoritative metadata.

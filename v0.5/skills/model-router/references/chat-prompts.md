# Model-routing chat prompts

Use these shapes in text-only agent chat. Replace examples with live model and runner data.

## Normal lane prompts

```text
Plan “{feature title}”

Model: {friendly label} (`{model id}`)
Launch: {uses this tab | launches <runner> as a sidecar; this chat remains the coordinator | choose <runner> in Conductor; opens a new tab}
OpenAI planning default · {reasoning} reasoning

Used for planning and planning retries. I’ll ask again before Build.

Reply:
- `plan` — start planning
- `models` — choose another verified model
- `openai defaults` — use the OpenAI defaults for this feature and start Plan
- `not now` — pause; start nothing
```

```text
Build “{feature title}”

Model: {friendly label} (`{model id}`)
Launch: {exact launch consequence}
OpenAI build default · can edit the workspace
Used for implementation and fixes returned from review.
Pace: standard (default while you do other work). Add `fast` when you are waiting; supported Codex routes provide 1.5× generation speed with increased usage.

{N} slices remain ({AFK} AFK, {HITL} need your input).

Reply:
- `build one` — build the next slice, then stop
- `build all` — build the remaining AFK slices within the declared ceilings
- `build to <slice>` — stop after that slice
- `models` — change the build model first

Append `fast` to a build action, for example `build all fast`. Pace carries through returned fixes and fresh Verify for this run only; model, reasoning, tests, and gates do not change.
```

```text
Verify “{feature title}”

Model: {friendly label} (`{model id}`)
Launch: {exact launch consequence}
OpenAI verification default · {reasoning} reasoning
Pace: {standard | fast inherited from the active Build run}

Starts with fresh context. Does not receive the builder’s chat.
Product files: read-only (show only when enforced by the route).

Reply:
- `verify` — start independent review and QA
- `models` — choose another verified model
- `not now` — pause; start nothing
```

## Expanded chooser

```text
Choose a model for {Plan | Build | Verify} “{feature title}”
Available now in this workspace

1. {label} — {default or preference note}
   `{model id}` · {exact launch consequence}

2. {label}
   `{model id}` · {exact launch consequence}

3. {label}
   `{model id}` · {exact launch consequence}

4. More verified models

Reply `1`–`4`, a model name, or `back`.
{Plan/Verify: Choosing 1–3 starts the stage immediately. | Build: Choosing a model returns to the Build menu; nothing starts yet.}
```

Omit `more` when no additional verified routes exist. If only one route is verified, offer that route, setup, or `not now`.

## Current-chat conflict

Show the current chat and OpenAI default together. Plan offers `plan here`, `plan with openai`, `openai defaults`, and `models`. Build offers `current`, `openai`, `models`, and `not now`, then returns to the build menu. Verify offers `verify here`, `verify with openai`, `models`, and `not now`.

Omit the current-chat action when it cannot satisfy identity, permission, or fresh-context requirements.

## Recovery prompts

Lead with the outcome: “{Lane} did not start” or “{Lane} stopped. Its output was not accepted.” Then name the verified cause and offer no more than three actions.

- Default unavailable: numbered verified replacement, `models`, `retry`.
- Identity mismatch: `retry`, `models`, `details`.
- Weak permission boundary: `safer default`, `continue`, `cancel`.
- Manual Conductor route: show the handoff path, model-picker steps, exact `Resume {Lane} from {path}` message, then `ready` or `models`.
- Fast mode unavailable: `standard` or `not now`. Never switch models or reasoning to imitate fast pace.

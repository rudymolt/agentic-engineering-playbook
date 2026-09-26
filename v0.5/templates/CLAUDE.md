# CLAUDE.md — {project name}

> Project governance for AI engineering agents. This is the contract. Read it before any work.

---

## ⛔ The first rule — a feature request is not a coding instruction

When a message describes a new feature or any non-trivial change ("add X", "build Y", "support Z"), your next action is **stage 01 alignment** (`{path-to-playbook}/v0.5/10-process/01-align.md`) — never code.

- Do **not** create or edit source files. Do **not** write implementation code in your reply — not even a sketch.
- Your first response names the feature, then starts the alignment grilling: goal, constraints, non-goals, vocabulary.
- Code is permitted only once alignment is recorded in `planning/{slug}/` and the feature has a spec and slices (stages 01 → 04).
- Sole exception: genuine one-liners (a typo, a comment, a broken link). If you're weighing up whether it qualifies, it doesn't.

This rule is first because it is the one agents break most: in benchmarking, agents that read this playbook and even cited its cadences correctly still jumped straight to implementation 20 times out of 20. Coding immediately *is* the failure mode, not a way of being helpful.

---

## What this project is

{One paragraph. The product, who it's for, the headline problem it solves.}

## Stack

{Languages, frameworks, datastore, hosting. Be specific — versions where they matter.}

## Dev commands

```bash
# install
{...}

# run dev
{...}

# test
{...}

# typecheck / lint
{...}

# build
{...}
```

## Editability tiers

| Tier | Folder(s) | Rule |
|---|---|---|
| **Frozen reference** | {e.g. `alpha-build/`} | Never edit. |
| **Generated output** | {e.g. `output/`} | Patch surgically only; never rewrite wholesale. |
| **Source of truth** | {e.g. `data/`, `content/`} | Free editing, with care — these drive generation. |
| **Active code** | {e.g. `src/`} | Free editing target. |

## Folders agents must not read

- `archive/` — shipped-feature planning artefacts. Stale by definition.
- `planning/{slug}/` where the slug is not in `active_features` of `.playbook-state.yml`.

If you need archive content for an incident investigation, ask the human to surface the relevant file.

## Playbook configuration

- **Session entry point:** read `{path-to-playbook}/v0.5/AGENT-DIGEST.md` first each session — stage map, routing rules, and hard rules in one read.
- **Playbook version:** V0.5 (`{path-to-playbook}/v0.5/`)
- **Intrusion level:** nudge   *# silent | nudge | insist*
- **Cadence config:** `./playbook-cadences.yml`
- **State file:** `./.playbook-state.yml`
- **Model routing:** gated — use `{path-to-playbook}/v0.5/93-model-routing-track.md` at Plan, Build, and Verify. The normal typed action accepts the displayed OpenAI default; `models` shows verified alternatives; every route states current tab, sidecar, or Conductor new-tab behavior.
- **Codex pace:** standard by default. When the human is waiting, they may append `fast` to a Build action (for example `build all fast`); carry fast pace through returned fixes and the fresh Verify handoff for that run only. Fast changes generation pace and usage, never the selected model, reasoning, tests, permissions, or safety gates.
- **Technical decisions:** ask by default. If `.playbook-state.yml → decisions.technical_decisions` is explicitly `auto_recommend`, choose only routine, reversible engineering details with a clear best option. Still ask about product/taste, scope, cost, credentials, external effects, destructive actions, security, and close trade-offs.
- **Budget floor (§11 — tune per project, never delete):**
  - _Loop guards (universal — set regardless of billing):_
    - productive-work budget: estimate from the verification plan before the run; for browser-heavy UI work, start near 60 tool calls and tune from evidence
    - verification reserve: plan the final 20% for verification, diff review, commit, and handoff; this estimate is not an ordinary-build halt
    - max-retry: 3 occurrences of the same failure signature, then escalate
    - time checkpoint: {e.g. 30 min} for ordinary issue-build progress reporting; declare any selected hard deadline separately
    - no-progress halt: {e.g. 3} consecutive iterations with the same failing test or no diff change → stop
  - _Cost/quota overlay (pick the row for your billing):_
    - API / per-token: per-run {e.g. $2 or 500k tokens}; session/day {e.g. $10}
    - Subscription / OAuth: no dollar cap available — the loop guards above are your quota protection; set them conservatively
  Ordinary issue builds include necessary reversible in-scope returned fixes and fresh independent verification through the selected endpoint. Inherited time checkpoints, effort estimates and verification reserves report progress and plan capacity; they do not require extension approval while progress continues. Explicitly selected hard limits, actual host/provider quotas, Stop, scope/authority/safety decisions and cumulative failure/no-progress guards still bind. Protected/autonomous delivery and live qualification retain mandatory approved limits. A ceiling stop **reports in four parts** — what it was doing, progress state (done/verified/incomplete), which ceiling at what value, and typed options for the human. Restate selected hard limits at run start; this rule grants no merge, activation, new service or spending authority.

## Constraints

Always, in every project:

- **Never write a credential, token, or key into a tracked file or echo one into chat.** If a task seems to need a secret, stop and ask — the answer is an environment variable and a `.gitignore` entry, not a hard-coded value "for now". Never run a diagnostic that dumps the environment or the process table (bare `env`, bare `printenv`, bare `set`, `ps -ef`, `ps aux`, `pgrep -a`, `top -c`, `htop`, `/proc/*/cmdline`, `/proc/*/environ`, or any `ps` invocation that prints a command line): the host runtime carries auth values there, and raw tool output reaches the transcript before any redaction. Identify processes with `ps -o pid,ppid,pgid,comm`, `pgrep -x`/`-f`/`-P` (pid-only), or an exact selector; find a port holder with `lsof -i :<port> -t` or `ss -ltn`. §10 holds the full rule. (Security floor: `{path-to-playbook}/v0.5/00-foundations.md` §10.)

- **Before modifying any database or doing a bulk data edit, create a timestamped backup** — and for schema changes, ship only with a rollback that has actually been run (stage 10, "Shipping a migration").

- **Match the length of every written deliverable to what the task needs.** Cover the substance, then stop — no filler sections, redundant summaries, or boilerplate. Documents written here become future agents' context, so inflation compounds.

{Things specific to this project that agents must not do. Example:}

- Do not invent {domain} rules. If something is unclear, mark it as an open question.
- Do not modify `{frozen-folder}/` — it is a snapshot for regression comparison.
- {…}

## Agent file roles

- **`CLAUDE.md`** (this file) — governance: stack, commands, tiers, constraints.
- **`AGENTS.md`** — quick-start: which files to read for which task.
- **`CONTEXT.md`** — domain vocabulary so agents don't re-derive it.
- **`DESIGN-GLOSSARY.md`** *or* **`design-glossary/`** (if UI) — the textual ubiquitous language for UI. A large glossary is split into `design-glossary/` (read `index.md` first, then the entries you need); see `{path-to-playbook}/v0.5/20-frontend-track.md`.
- **`ui-kitchen-sink.html`** (if UI) — the visual ubiquitous language for UI.
- **`frontend-design-language-guide.html`** (if UI) — the interaction language: application-level principles and surface decision rules (row vs card, drawer vs modal, history disclosure).

## UI rule (if the project has a UI)

When proposing or writing UI code, refer to elements only by names defined in the glossary (`DESIGN-GLOSSARY.md`, or `design-glossary/` when split — read `index.md` first and load only the entries the feature touches), use only styles that exist in `ui-kitchen-sink.html`, and use only surfaces and interaction patterns sanctioned by `frontend-design-language-guide.html`. If a new element, style, or pattern is needed, stop and propose an update to the relevant artefact first (for a split glossary, add a `components/<term>.md` entry and rebuild the index). If any of the three artefacts is missing, run the frontend bootstrap prompt in `{path-to-playbook}/v0.5/20-frontend-track.md` before any UI work.

## Where the playbook lives

The full playbook V0.5 is at `{path-to-playbook}/v0.5/`. The agent reads it for stage definitions, cadence rules, and the `/whats-next` skill.

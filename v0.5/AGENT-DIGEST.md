# AGENT-DIGEST — Playbook V0.5 in one read

> Machine-oriented entry point. Read this first; open the full documents only when a pointer below sends you there. Everything here is derived from the long-form docs — they remain the source of truth.

## What this playbook is

A 13-stage, per-feature engineering loop for human-led, agent-assisted software work. The human owns goals and judgement; the agent supplies disciplined execution. Do not invent process — route every request through the stages below.

## Stage map

```
stages[13]{id,file,when}:
  00, 10-process/00-prereqs.md,            every session, first thing
  01, 10-process/01-align.md,              any change larger than a one-liner
  02, 10-process/02-context-and-adrs.md,   side-effect of 01 (record decisions)
  03, 10-process/03-spec.md,                after alignment settles
  04, 10-process/04-breakdown.md,          after spec (vertical slices)
  05, 10-process/05-triage.md,             new issue, or "what should I work on?"
  06, 10-process/06-architecture.md,       nudge at 3 slices (cadence), or codebase feels heavy
  07, 10-process/07-implementation-tdd.md, any non-trivial feature or bug fix
  08, 10-process/08-review.md,             before every PR
  09, 10-process/09-qa.md,                 after implementation, before ship
  10, 10-process/10-ship-and-deploy.md,    feature ready to land
  11, 10-process/11-debug.md,              any non-trivial bug or regression
  12, 10-process/12-retro-and-learn.md,    weekly, and after every shipped feature
```

Every stage file opens with **"This stage in one breath"** (read that before committing to the full file) and ends with a **`## Next`** block routing you to the following stage by outcome. Follow those blocks; you should rarely need to return here mid-feature.

## Routing rules

```
routes{user_says,open}:
  "build / add / create X",        10-process/01-align.md   # NEVER straight to code — see hard rules
  "deliver to PR",                 10-process/delivery-mission.md, then /ai-playbook-deliver
  "K4.1 merge",                    10-process/delivery-mission.md # admitted fresh session only
  "models / openai defaults",      skills/model-router/SKILL.md, then 93-model-routing-track.md
  "goal known, route still foggy", offer user-invoked /wayfinder, then 92-wayfinder-track.md
  "test a UI / state-model idea",  /prototype during alignment; preserve its evidence off main
  "fix / debug X",                 10-process/11-debug.md
  "ship / deploy",                 10-process/10-ship-and-deploy.md
  "cut a GitHub release",          skills/ship-release/SKILL.md
  "what should I work on?",        10-process/05-triage.md
  "codebase feels messy / heavy",  10-process/06-architecture.md
  "is this safe to merge?",        10-process/08-review.md
  "how did this week go?",         10-process/12-retro-and-learn.md
  anything ambiguous,              run /whats-next (skills/whats-next/SKILL.md)
```

## Session start (bootstrapped project)

1. Run stage 00's warm/cold router. Normal sessions use the bounded warm path; bootstrap, upgrades, host/tool changes, and failed prerequisites take the cold capability-profile path.
2. Read the `status:` block, `pending_model_routes`, and `active_wayfinding_maps` in `.playbook-state.yml`. **Trust them; re-derive only when `status.computed_at` predates `last_updated` or the block is missing.**
3. Resume the oldest resumable pending Plan route before proposing new work; show its saved model/runner and exact current-tab, sidecar, or Conductor handoff action. If a portable pickup brief is supplied, reconcile its branch, revision, tracker, evidence, dependencies, budgets, and gates first; it never replaces current-state checks or fresh verification. Then surface the oldest open Wayfinder map — offer `/wayfinder {locator}` and wait for the human to invoke it; finishing an in-flight feature ranks first (`/whats-next` defines the full order). Otherwise raise `nudge` items as a one-line PS and `insist` items before new work, then route the request.

## Session start (project not yet bootstrapped)

Missing `.playbook-state.yml` means not bootstrapped (the file states this explicitly — absence is definitive, not ambiguous). Invoke `/ai-playbook-bootstrap-project`. It offers lite mode only when every criterion in `70-lite-mode.md` holds; otherwise it collects UI and CI choices, presents a dry-run, applies `scripts/bootstrap-project.py`, installs the playbook-local skills under `.agents/skills/`, stamps and computes state, then runs stage 00's cold path. **Conductor setup lane:** when Conductor environment variables are present or the human requests Conductor support, the bootstrap invokes the host's bundled `conductor` skill and adds an evidence-based setup, Run-command, copied-files, port/concurrency, validation, and activation plan to the same approval gate. Ask before applying; never impose UI defaults, Conductor settings scope, or overwrite existing project content.

## State conventions

```
files{path,role}:
  .playbook-state.yml,      counters, timestamps, status block; stages + /whats-next update it
  playbook-cadences.yml,    cadence rules (thresholds); tuned at retro, read rarely
  planning/STATUS.md,       index of active features + open Wayfinder maps ("0 active features" is definitive)
  planning/{slug}/,         one folder per in-flight feature (spec, slices, notes)
  archive/STATUS.md,        count of shipped features; do NOT read archive contents
  CLAUDE.md / AGENTS.md,    project-local operating rules (override this playbook)
  CONTEXT.md,               shared vocabulary + durable decisions; ADRs for the why
  .playbook-routing/,       gitignored pre-feature cross-tab handoffs; never durable planning docs
```

`active_wayfinding_maps` is a separate pre-spec list, not an active feature status. Each entry mirrors only map title, locator, one-line destination, and opened date; the tracker remains canonical.

`pending_model_routes` records a selected Plan route before stage 01 proves one normal feature exists. Resumable entries count in `status.pending_plan_routes` and appear under `planning/STATUS.md → Pending Plan routes`; `linked_wayfinder` entries re-enter through the map instead.

Empty-state rule: a `STATUS.md` saying "0 active features" is an answer, not an error. State updates are written at the moment a stage completes — and whoever changes state recomputes the `status:` block (see template comments in `templates/.playbook-state.yml`).

## Hard rules (from foundations — full version: 00-foundations.md)

- [precondition] **THE FIRST RULE — a feature request is not a coding instruction.** "Add X / build Y / support Z" routes to stage 01 alignment; you do not create or edit source files, or draft implementation code, until alignment is recorded in `planning/{slug}/` and the feature has a spec and slices. No acceptance criteria, no build — the agent never invents its own success criteria; route back to alignment instead. Sole exception: genuine one-liners. Benchmarked agents broke this 20/20 times by "helpfully" implementing — coding immediately is the failure mode.
- [precondition] The code is the source of truth, not the plan; planning docs die at ship (30-document-lifecycle.md).
- [evidence] An omitted applicable step in the selected workflow records `skip: <reason>` or `n/a: <reason>` beside that workflow's existing result; a reason never bypasses a required gate (00-foundations.md §1).
- [precondition] UI work: never invent vocabulary, variants, or interaction patterns in feature code — update the glossary (`DESIGN-GLOSSARY.md`, or `design-glossary/` when split: read `index.md` first, load only the entries you need) / `ui-kitchen-sink.html` / `frontend-design-language-guide.html` first; and show an approved ASCII diagram before UI code — HTML mockup first for interactive/non-trivial UI (20-frontend-track.md).
- [prompt] Agent-facing surfaces (CLIs, APIs, tool interfaces the product exposes) follow the agent-ergonomics checklist in `00-foundations.md`.
- [precondition] Ordinary issue builds use inherited time checkpoints and effort estimates for progress reporting, not extension-approval boundaries. Declare retry/no-progress guards and any explicitly selected hard time, cost, iteration or dispatch limit; selected limits and actual host/provider quotas stop. Necessary reversible in-scope returned fixes and fresh independent verification continue through the selected endpoint without a new prompt while progress is demonstrable. Do not reset cumulative failure history across handoffs. Protected/autonomous delivery and live qualification retain mandatory approved ceilings (00-foundations.md §11). A validated opt-in interim coordinator record selecting `hard_limits: none` has its own narrow forecast rule: forecasts report progress, while explicit Stop, three-failure/three-no-progress guards and human-selected limits remain binding. S1 remains checkpoint-only and dispatch-unavailable.
- [precondition] At or above cross-module changes, review/QA runs as a different agent in a fresh context (no implementer transcript), read-only where the host supports it, and verifies by executing with pasted evidence; checker auto-fixes re-enter verification (stage 08).
- [precondition] An embedded upstream reviewer runs only when its exact installed source passes `scripts/check-upstream-compatibility.py` in report-only mode. Unknown, incompatible, or drifted source takes the manifest's adapter/manual fallback; commits, setup, routing, configuration, and upgrades remain stage-owned.
- [precondition] TDD for any non-trivial change, verification scaled to risk (ladder, 00-foundations.md §4); no fixes without diagnosis (stage 11's iron law). A diagnosed bug's meaningful regression test may use only stage 11's documented, fresh-verifier-accepted exception; it never bypasses a required gate.
- [prompt] Start with targeted reads; use bounded read-only delegation only for useful bulky independent exploration, return locators and unresolved facts, and inspect delegate evidence before writing the lead synthesis. Without subagents, use bounded serial reads; coupled implementation stays one slice at a time (foundations §9; stage 07).
- [gate] Secrets never enter tracked files or replies — env var + .gitignore, or stop and ask; a committed or exposed secret is a human-handled incident — report the location, never delete or replace it yourself (00-foundations.md §10).
- [evidence] Debug commands, output, logs, traces, and captured artifacts are redacted before display; keep credentials in environment variables and quote only signal-bearing lines (stage 11). Never dump the environment or the process table (bare `env`, bare `printenv`, bare `set`, `ps -ef`, `ps aux`, `pgrep -a`, `top -c`, `htop`, `/proc/*/cmdline`, `/proc/*/environ`, or any `ps` invocation that prints a command line) — host runtimes carry auth values there; identify processes with `ps -o pid,ppid,pgid,comm`, `pgrep -x`/`-f`/`-P` (pid-only), or an exact selector. 00-foundations.md §10 holds the full rule.
- [handoff] A `/prototype` answers one design question and remains runnable primary-source evidence on a throwaway `prototype/<name>` branch with a tracker pointer; main keeps only the validated decision (20-frontend-track.md; 92-wayfinder-track.md).
- [precondition] Back-to-back builds are opt-in via the typed build choice (build one / build all / build to <slice>), run AFK slices only, keep per-slice independent review, and remediate necessary reversible in-scope findings as fresh fix tasks followed by fresh Verify. Pause on HITL, ambiguity, Stop, human-owned decisions, three identical failures/no-progress, explicitly selected hard limits or actual quotas. Plan verification capacity; an inherited reserve alone does not halt an ordinary build. End with a cross-slice review at a human checkpoint (stage 07). Standard pace is the default; appending `fast` requests available Codex fast mode for this Build → fix → fresh-Verify run only, with increased usage and unchanged quality/safety gates.
- [state] `pending_closeouts` and `last_run.feature_ship` keep shipped-feature production verification, doc-close, and retro visible; `/whats-next` ranks closeout before pending Plan, active work, Wayfinder, or new work.
- [prompt] Inline typed options are canonical. Structured question UI is optional; if absent or failed, ask the same options in text immediately. `decisions.technical_decisions: auto_recommend` applies only to routine reversible engineering choices.
- [gate] Before implementation, check host PR state as well as git state. A merged current branch is closed scope: update `main` and create a fresh branch.
- [handoff] Feature closeout ships as one PR: doc-close, current-release pointers, and a same-session feature retro share one fresh closeout branch (stage 10, document lifecycle) — never one docs PR per step.
- [gate] An insist-level overdue architecture review runs before the feature PR merges (stage 06 timing rule, stage 10 gate check); defer only to a named pre-merge point, never past the ship.
- [handoff] Every terminal stage/skill returns `playbook_result` with `outcome`, machine-readable `next_stage`, and ordered `required_actions`; recompute status after state writes and consume required closeout before unrelated work.
- [evidence] Every routed worker result includes authoritative model, effort, thread, runner, permission, tool-use, and wall-time metadata. Reject route mismatches automatically; never infer missing identity from generated prose.
- [handoff] A session/host/worker handoff uses the bounded `10-process/pickup-brief.md` reference: maximum-five-bullet capsule, per-thread status, failed/reverted evidence, and exactly one next action. It uses portable locators, flags Mac-only or inaccessible proof, and leaves mission re-entry and fresh review rules authoritative.
- [prompt] At Plan, Build, and Verify boundaries, use the text-only model prompt in `93-model-routing-track.md`: normal lane action accepts the effective project/feature preference with origin, `models` exposes only verified alternatives, `openai defaults` is a feature-scoped edition override, and every route states current tab, sidecar, or Conductor new-tab consequences. Never substitute an unavailable or identity-mismatched model.

## Escape hatches (full documents)

Project Build defaults: user-invoked `/ai-playbook-configure` provides typed
read/edit/preview/Apply without launching. Existing model-router resolves new
choices through `scripts/configure-playbook.py`: feature > adopted project >
legacy project > edition. Malformed adoption blocks; active/approved records
remain unchanged. See `scripts/playbook-config.md` for the shared boundary.

```
help{need,open}:
  full bootstrap + folder map,        README.md
  universal principles,               00-foundations.md
  stage detail,                       10-process/{stage file}
  frontend three-artefact discipline, 20-frontend-track.md
  planning -> archive lifecycle,      30-document-lifecycle.md
  resume work across a handoff,        10-process/pickup-brief.md
  retro / promotion / nudge levels,   40-self-improvement.md
  prerequisite capability profiles,   10-process/prereqs-capability-profiles.md
  local skill invocation contract,     skills/README.md
  small project? lite loop + tripwire, 70-lite-mode.md
  worked example of the full loop,    80-quickstart.md
  optional autonomous loop track,      90-loop-track.md
  process-attested delivery / K4.1,    10-process/delivery-mission.md + skills installed as /ai-playbook-deliver
  delegate a multi-phase change,       91-delegation-track.md
  clarify a foggy multi-session route, 92-wayfinder-track.md (offer; human invokes /wayfinder)
  choose models by feature lane,       93-model-routing-track.md + skills/model-router/SKILL.md
  upgrade an older project,           skills/ai-playbook-upgrade-project/SKILL.md
  publish a GitHub Release,           skills/ship-release/SKILL.md
  maintain upstream integrations,      MAINTENANCE.md
  human-facing guides,                index.html, 50-*.html, 60-*.html (do not parse; for humans)
```

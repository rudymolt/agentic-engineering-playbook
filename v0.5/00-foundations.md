# 00 · Foundations

> The universal principles every stage of the process assumes. Read this once at the start of a project; re-read the relevant section before any action that matters.
>
> Distilled from the full Sample Fitness agent playbook at `references/sample-athletics-ui/sample-agent-playbook.md` — go there for the long-form version and case studies.

---

## 1. The collaboration contract

You are working **with** the human, not for them. The goal is shared progress on something they care about, not the appearance of activity.

**Ask before you act.** Almost every non-trivial request is underspecified. The cost of a 30-second clarifying question is always less than the cost of building the wrong thing. Ask a concise typed question with at most four options when scope, audience, format, or depth is unclear. A host's structured-question UI is an optional rendering of that same prompt: if it is absent or fails, immediately print the options inline. Never stall or silently choose. If the user has already clarified earlier in the conversation, don't re-ask. Projects may explicitly set `decisions.technical_decisions: auto_recommend` for routine, reversible engineering choices with a clear best answer; product/taste, scope, cost, credentials, external effects, destructive actions, security, and close trade-offs always remain human decisions.

**Don't invent domain rules.** If you don't know something domain-specific, say so. Mark it as an open question. Never fabricate a rule that sounds plausible — the cost of an invented rule landing in production is much higher than the cost of pausing to ask.

**Match verification depth to the change.** Don't run the full test suite for a typo fix. Don't ship a parser rewrite with only a type-check. See §4 below for the verification ladder.

**Push back constructively.** If a proposal conflicts with the project's stated goals or architecture, say so briefly, offer the alternative, then defer to the user's judgement.

**Don't add what they didn't ask for.** A request to fix a parser bug is not a licence to refactor the parser. Spotted improvements are worth mentioning, not doing.

**Use the project's vocabulary.** Read `CONTEXT.md` before any domain work. The names the user uses for the nouns of the domain are the names you use too — in variable names, file names, test descriptions, and commit messages.

The agent has standing authority and obligation to halt work on objective triggers: missing or contradictory acceptance criteria, suspected security issue, irreversible-data risk, failing required gate, repeated blocked attempts, or conflict with an existing ADR/invariant. A halt always carries the evidence that triggered it and a specific ask.

**Make selected-workflow omissions visible.** When an applicable step in the
selected workflow is omitted, record `skip: <reason>` or `n/a: <reason>` in
that workflow's existing checklist or result. Do not list unrelated stages or
unused optional skills. A reason explains an omission; it never authorizes a
mandatory gate to be bypassed.

---

## 2. Architecture decisions that compound

A small number of decisions, made early, shape everything else.

**One source of truth.** For every piece of data the system handles, identify the canonical representation. Everything else either reads it or derives it. This forces surgical edits, eliminates sync bugs, and gives you exactly one place to debug.

**Split parsing from serialising.** Read once, work with structured values in memory, write back through a separate serialiser. Routes and screens become thin; the parser/serialiser pair becomes the seam where every domain rule lives.

**Adapters at the edges.** API routes are adapters. UI screens are adapters. Domain modules live in `src/lib/{domain}/` (or your stack's equivalent). The adapter's job is to translate to and from the canonical representation — nothing more.

**Deep modules over wide ones.** A deep module has a narrow interface and a lot of behaviour behind it. A wide module exposes everything. Prefer deep — they're easier for both humans and agents to use without understanding internals. Trust the architecture vocabulary defined in Matt Pocock's `codebase-design` skill (module, interface, depth, seam, adapter, leverage, locality) — since upstream v1.0.0 this shared skill holds the vocabulary that previously lived in `improve-codebase-architecture/LANGUAGE.md`, and `tdd` and `improve-codebase-architecture` both draw on it — and avoid the overloaded ones (component, service, API, boundary) when discussing structure.

**Make editability tiers explicit.** Every mature project has tiers:

| Tier | Examples | Rule |
|---|---|---|
| **Frozen reference** | Last known-good snapshot | Never edit. |
| **Generated output** | Files produced by a build pipeline | Patch surgically only. |
| **Source of truth** | Hand-edited config, content, schemas | Free editing, with care. |
| **Active code** | The product you're building | Free editing target. |

Declare these in `CLAUDE.md` at project kickoff. An agent reading them knows immediately where it's safe to act.

**Turn constraints into enforcement where practical.** During relevant
implementation and review work, when a constraint can be enforced practically
and in scope, enforce it with the cheapest type, test, runtime check, or CI rule
rather than leave it only as a warning comment. Remove redundant warning prose
only after that enforcement exists.
Keep license notices, external constraints, public API contracts, and rationale
that a check cannot express. This is not permission for a comment purge or
unrelated refactoring.

---

## 3. Slice-based delivery

**Vertical slices, not horizontal layers.** Every meaningful unit of work cuts through every layer of the stack end-to-end (schema → API → business logic → UI → tests) for one narrow capability. This is Matt Pocock's tracer-bullet pattern, enforced by `/to-tickets` (formerly `/to-issues`).

The horizontal anti-pattern — "build all the schemas, then all the APIs, then all the UI" — produces nothing usable until the very end and tests imagined behaviour rather than actual behaviour. Refuse it.

**Each slice is independently grabbable.** A slice has a single demoable outcome ("user can do X"). It either ships, or it's small enough that abandoning it costs nothing.

**AFK vs HITL.** Mark each slice as AFK (an agent can implement without human input) or HITL (human-in-the-loop required). `/to-tickets` does this for you.

**Back-to-back builds are opt-in and bounded.** A build loop (stage 07's "build all") runs AFK slices only, keeps per-slice independent review, and may remediate concrete in-scope verifier findings under stage 07's bounded rule. It pauses at HITL, ambiguity, scope expansion, three identical failures/no-progress, or another §11 ceiling, and always ends at a human checkpoint.

---

## 4. The verification ladder

Match verification depth to the cost of being wrong:

| Change type | Minimum verification |
|---|---|
| Typo / comment edit | Eyeball + save |
| Single-file local refactor | Type-check + relevant unit tests |
| New behaviour in one module | TDD red→green at the agreed seam + relevant unit tests; structural refactoring happens under stage 08 review |
| New behaviour across modules | TDD + integration test + report-only stage-09 browser/device pass + independent verifier (stage 08 verifier definition) |
| Change at a boundary with a sibling app or external API | All of the above + contract test (consumer expectations pinned; provider verified where owned) |
| Schema or data-shape change | TDD + integration test + manual smoke + backup + migration |
| Anything touching auth, payments, user data, or public endpoints | All of the above + compatibility-gated or manual stage-08 security pass |
| Production deploy | All of the above + `/canary` post-deploy monitoring + rollback rehearsed |

When in doubt, climb the ladder. The cost of over-verifying a small change is minutes; the cost of under-verifying a big one is hours or weeks.

A meaningful automated regression test is the default for a diagnosed bug. The
narrow exception for a misleading or impractical test is owned by stage 11: it
requires reproduction, diagnosis, an executable alternative, a recorded gap,
and fresh independent verifier acceptance. It never waives TDD for new
behaviour or a required gate.

---

## 5. Surgical edits over rewrites

**Patch the smallest unit you can.** Markdown files, generated outputs, and other "source of truth" tiers get patched line-by-line. Never rewrite a file wholesale unless the user has explicitly asked for it.

**Read before you write.** Always read the current file state before editing. Don't trust your memory of it from earlier in the conversation; another tool call may have changed it.

**One concern per commit.** Mixing a refactor with a feature in one commit makes both impossible to review. Split.

---

## 6. State and data flow

**One direction of data flow.** Upstream owns the data, downstream reads it. Bidirectional flow ("the UI also writes back into the parser cache") is where bugs breed.

**Derive, don't duplicate.** If a value can be computed from another, compute it. Caches are a last resort, with an explicit invalidation rule.

**Centralise domain helpers.** Date parsing, country codes, currency, etc. — one module owns each, every route and screen imports from it. See `references/sample-athletics-ui/SAMPLE-ATHLETICS-APP-ARCHITECTURE.md` §"Date Handling Contract" and §"Country And Nationality Contract" for worked examples.

**Prefer proposed-record agent lanes for AI-submitted data.** In local-first apps where agents can submit operational data, default to local-only agent routes that create proposed records for human review. Official mutation stays in the human-owned command path; requests prefer stable IDs; ambiguous human labels return clarification candidates; responses use the project's shared success/error envelopes. Direct agent writes need an explicit project rule, a clear safety boundary, and verification appropriate to the data being changed.

---

## 7. Memory and skills

This playbook assumes Matt Pocock's `skills` and Garry Tan's `gstack` are installed. The prereqs stage (`10-process/00-prereqs.md`) verifies this on every session. You also have your own per-user memory store at `~/.../memory/MEMORY.md` plus per-project memory in `CLAUDE.md`.

A skill pays off intent debt — the recurring cost of re-explaining the project every session.

When creating or editing a skill, `AGENTS.md`, `CLAUDE.md`, or another document an agent consumes, use `/writing-for-agents`. Treat repository config, task-runner scripts, directory layout, and command help as the environment's source of truth; document only the convention, rationale, or gotcha the agent cannot recover cheaply by looking.

**What goes in memory vs the playbook:**

- **Per-user memory** — preferences, recurring patterns, things you've learned about the human you work with. Promotes upward to skills if they generalise.
- **Per-project memory (`CLAUDE.md`)** — project stack, commands, tiers, constraints. Promotes upward to this playbook if a pattern appears in three+ projects.
- **This playbook** — universal principles and stage definitions. Tuned per project via `playbook-cadences.yml`, not by editing the playbook itself.

The retro stage (`12-retro-and-learn.md`) is where lessons flow upward through these layers.

---

## 8. Common pitfalls

A quick sanity check before doing something you're not sure about:

- About to rewrite a file? Stop. Can you patch it instead?
- About to "improve" something the user didn't ask about? Stop. Mention it, don't do it.
- About to invent a domain rule? Stop. Mark it as an open question.
- About to skip a meaningful regression test for a diagnosed bug? Stop. Use the
  narrow, independently accepted stage-11 exception only when the proposed test
  would be misleading or impractical; cost or convenience is not enough.
- About to mix a refactor with a feature in one commit? Stop. Split.
- About to ship without the report-only stage-09 browser/device pass? Only if the verification ladder allows it for this change type.
- About to merge a PR touching auth/payments without the compatibility-gated or manual stage-08 security pass? Stop. Run it.
- About to read every file in the repo to "understand it first"? Stop. Read only what the requested scope needs.
- About to use vocabulary that isn't in `CONTEXT.md`? Stop. Add the term first, then code.
- About to build or change UI? Stop — show the layout as a diagram the human approved first (`20-frontend-track.md`, UI preview gate).

---

## 9. Design the agent-facing surface

Adapted from the [AXI principles](https://axi.md/). The frontend track disciplines the human-facing surface; this section disciplines the surface **agents** consume. It applies whenever the product exposes a CLI, an API, an MCP server, or any tool interface that an AI agent will call — increasingly the default, not the exception.

**The principle:** treat the consuming agent's token budget and turn count as first-class design constraints, the way the frontend track treats visual vocabulary. An interface that forces an agent to take extra turns, parse walls of text, or guess at next steps is a defect, even if it works perfectly for humans.

**The checklist** (apply at stage 06 architecture when designing the interface, and at stage 08 review when checking it):

1. **Token-efficient output** — compact structured formats; no decorative output.
2. **Minimal default schemas** — return the 3–4 fields agents actually need; offer a `--fields`-style escape hatch for the rest.
3. **Content truncation** — cap large fields with a size hint and a way to fetch the remainder.
4. **Pre-computed aggregates** — include totals, counts, and rolled-up statuses so the agent never needs a second call to know "how many" or "did it pass".
5. **Definitive empty states** — print "0 results", never nothing. Silence is indistinguishable from failure.
6. **Preconditions and corrective errors** — state prerequisites before work,
   keep mutations idempotent, return machine-parseable errors without
   interactive prompts, and tell the caller the corrective action.
7. **Machine-readable output where appropriate** — document a JSON or other
   structured route when agents need to consume the result programmatically.
8. **Stable documented exit semantics** — distinguish success, failure, and
   meaningful states such as blocked where the interface already needs them;
   do not collapse every command into 0/1.
9. **Destructive-action preview** — provide a documented preview or dry-run
   that shows intended changes before execution and never performs the
   destructive action it previews. Verify and disclose actual ancillary effects
   such as network, scratch, or setup work; a name alone does not prove safety.
10. **Ambient context** — let a session start with relevant state already visible (a hook, a status file) rather than requiring discovery calls.
11. **Content first** — the no-argument invocation shows live state, not a wall of help text.
12. **Contextual disclosure** — append concrete next-step suggestions after output, parameterised with placeholders rather than guessed values.
13. **Consistent help** — every subcommand answers `--help` concisely, as the fallback when the contextual hints aren't enough.

**Litmus test:** could an agent complete the product's three most common workflows without ever reading full documentation, just by following what the interface itself discloses? If not, name the missing disclosure and fix the interface, not the docs.

This playbook practises what it preaches: `AGENT-DIGEST.md` is the minimal default schema, the stage files' `Next:` blocks are contextual disclosure, the `status:` block in `.playbook-state.yml` is a pre-computed aggregate, and `planning/STATUS.md` / `archive/STATUS.md` are definitive empty states.

`no-mistakes axi` is one external example of an ergonomic agent surface: compact machine-readable output plus an explicit waiting-vs-working signal. Its "AXI" command is unrelated to this playbook's AXI principles; cite the pattern, not the name.

The more serious an invariant, the lower it should live: deterministic hook or CI gate, then command precondition, then skill prompt, then prose reminder. If an invariant can be made deterministic at reasonable cost, make it so; do not mandate stack-specific hooks. `templates/ci-gates.md` is the project-level embodiment of this lens.

### Standard read-only sub-agent roles

Start with targeted reads. When genuinely independent exploration would be bulky,
use bounded read-only delegation when useful and available; return a concise
synthesis with source locators and unresolved facts, under the existing §11
budget. Do not fan out a tiny lookup. Without subagents, use bounded serial
reads and retain the same file-backed locators rather than copying full
transcripts into the main context.

Delegating context-heavy, read-only subtasks to fresh-window sub-agents keeps the orchestrating context lean: the agent-level form of the token-frugality thesis this playbook is built on. All three standard roles are read-only, return compact, evidence-bearing reports, and run under the §11 floor.

These roles are harness-neutral. Dispatch them through the current host's available parallel-agent mechanism; do not depend on Claude Code tool names or agent-type labels.

- **Explorer** — maps unfamiliar code and returns a one-page digest of the files, flows, and constraints relevant to the task.
- **Reviewer** — the stage 08 independent verifier; use stage 08 for the definition, evidence contract, and verdict shape.
- **Researcher** — checks external docs and prior art, returning findings with sources.

A lead inspects the returned artifacts, relevant diff, and cited evidence; resolves
contradictions or missing support; and writes its own synthesis. Passing a
delegate's success claim through verbatim is not verification. For read-only
exploration, inspect the facts relevant to the conclusion without repeating
every search. This lead responsibility complements, never replaces, the fresh
independent verifier.

A sub-agent that needs to write product code is not one of these roles. It is an implementer, and implementation follows stage 07's fan-out rule.

---

## 10. The security floor

New in V0.2.5 (improvement plan Area 5). These are minimums, not a security programme — they exist because their absence hurts without warning.

- **Secrets never enter tracked files.** Credentials, tokens, and keys live in environment variables or untracked env files covered by `.gitignore`. An agent that needs a secret to proceed stops and asks — it never writes one into code, config, tests, fixtures, or chat output "temporarily".
- **Diagnostic evidence is redacted before display.** Commands, outputs, logs, traces, HAR files, and other captured artifacts replace credentials with `<REDACTED>`; feedback loops read secrets from environment variables, and reports quote only the signal-bearing lines. If redaction removes evidence needed to investigate the bug, stop and ask for a safer access route.
- **Diagnostics never dump the environment or the process table.** Host runtimes (Conductor, Codex, CI runners) carry authentication values in environment variables and on infrastructure command lines, so `env` or `printenv` run for their output, bare `set`, `ps -ef`, `ps aux`, any `ps` invocation that prints a command line — an `args`, `command`, or `cmd` output format, or the `-f`, `w`/`ww`, and `ax` full formats — `top -c`, `htop`, `pgrep -a`, and reads of `/proc/*/cmdline` or `/proc/*/environ` put live credentials into tool output before any redaction can run. (`env VAR=value cmd` and `set -euo pipefail` are invocation prefixes, not dumps; they stay allowed.) Identify a process by its identity rather than its command line: `ps -o pid,ppid,pgid,comm`, `pgrep -x <name>`, `pgrep -f <pattern>` or `pgrep -P <ppid>` — both print pids only — or an exact fixture selector. To find a port holder use `lsof -i :<port> -t` or `ss -ltn`, which report a pid and at most a command name; if neither is installed, ask the human rather than reaching for a broader tool. Read a single named variable only when the task needs it. If a value surfaces anyway, hand it to a human as a security incident: report the workspace or session identifier and timestamp, never the value, and stop. The human decides on and performs any follow-up with the host; the agent does not.
- **A committed secret is a human-handled incident, not a deletion.** Removing the line does not remove it from history. Report the file, line, and commit to a human and stop; the human replaces the credential and decides whether the project's hosting requires history cleanup. The agent never performs, requests, or scripts credential replacement on its own.
- **Dependencies are deliberate.** Lockfiles are committed. Every new dependency is named in the PR description with a one-line justification. Prefer the standard library for trivial needs — a left-pad is not worth a supply chain.
- **Validate at every boundary the project owns.** Anything crossing into the system — user input, file contents, API responses, environment values — is validated where it enters, not where it breaks.
- **Least privilege by default.** Tokens and keys the project issues or requests get the narrowest scope that works, and an expiry where the platform supports one.

- **Irreversible operations get a rehearsed reverse.** Schema migrations, bulk data edits, and deletions are preceded by a timestamped backup, and their rollback has actually been executed against a copy before the forward change ships (stage 10, "Shipping a migration").

The review stage (08) carries the per-PR security pass; the prereqs stage (00, Check E) carries the per-session floor check.

---

## 11. The budget floor

New in V0.2.13; reframed in V0.3.13 to separate loop safety from cost. These are minimums, not a cost programme — their absence hurts without warning.

The floor has two layers. **Layer A (loop guards) is universal** — it applies to every project regardless of how the model is billed, and its job is to stop an agent thrashing. **Layer B (cost/quota overlay) depends on your billing model.** Values are project-tunable. A run that hits an explicitly selected hard limit or an actual host/provider quota pauses and reports. An inherited ordinary-build estimate is a progress checkpoint, not a hard limit.

**The ceiling-stop report has a required shape.** Stopping is half the job; a terse "I stopped" is a defect. Every ceiling stop reports four parts: (1) **what the run was doing** — the slice/goal in one line; (2) **progress state** — completed, verified, and incomplete items, so the human can judge the working tree; (3) **why it stopped** — which ceiling, at what value; (4) **options** — typed next steps (continue another tranche, raise the ceiling to a value, pause for review, revert). This applies to every stop, including drills and user-shortened tranches.

**Explicit selections govern.** When the human selects a hard limit for a run ("this run: max-iteration 5"), that value governs, not a `CLAUDE.md` estimate. Restate the selected limit at run start so a mismatch surfaces before work begins. Inherited time checkpoints and effort estimates in an ordinary issue build report progress, remaining work and a revised estimate; they do not require extension approval while the work makes demonstrable progress.

**Layer A — loop guards (always set these):**

- **Max-retry cap** — a bounded number of attempts at a failing step, then escalate rather than retry forever.
- **Progress checkpoint** — estimate turns, tool calls and elapsed time per ordinary issue-build slice; report at the checkpoint and revise the estimate as evidence changes. A selected hard iteration or wall-time cap still stops at its value.
- **Protected-run cap** — retain mandatory iteration and wall-time ceilings in protected delivery, autonomous-delivery and live-qualification envelopes. Their approved limits are not converted to checkpoints by ordinary-build authority.
- **No-progress halt** — stop when work stalls. Default trigger (tune per project): the same test fails on **3 consecutive iterations**, or **3 consecutive iterations** produce no change to the diff. A concrete number makes the halt checkable rather than a mood.

**Ordinary issue builds.** The approved build scope includes necessary reversible
in-scope returned fixes and fresh independent verification through the selected
endpoint. A concrete verifier finding re-enters Build and fresh Verify without a
time-extension prompt. Plan capacity for verification, but an inherited reserve
does not halt productive work when no hard cap was selected. Stop for an
explicitly selected hard time, cost or dispatch limit, an actual host/provider
quota, Stop, a scope/authority/safety decision, or the cumulative retry and
no-progress guards. A handoff does not reset those guards. Build one remains
build one; this rule grants no merge, activation, new service or spending
authority.

**Narrow interim-coordinator exception.** A validated `interim-run` approval may
select `hard_limits: none`. In that one opt-in mode, forecasts are progress
signals rather than an inferred overall deadline, dispatch cap, reserve cutoff,
or infinity-shaped budget. The coordinator still honors explicit stop,
three-failure/three-no-progress guards, and any human-selected limits. Ordinary
stage-07 runs use the ordinary issue-build rule above; protected continuation
retains its mandatory approved ceilings.
Disposable host qualification keeps its own human-approved outer test ceiling.
For S1 this is checkpoint-only and dispatch-unavailable: no worker may be
launched until later interim slices qualify execution support.

The approved `interim-run` S3 policy is a scoped diagnosis/repair exception, not
a replacement for these guards. It records an initial failing Build/Verify without
charging a repair cycle, then requires a concrete reversible in-scope finding,
evidence-only diagnosis, changed experiment, repair, and fresh Verify. A
no-progress batch remains eligible through its first two cycles and is `stuck`
on its third; productively failing evidence requires fresh diagnosis even for
different failures. Repeated or narrative evidence is not progress. No-cap
forecasts may be revised from
independent worker-result evidence without becoming an expiry, 80% cutoff, retry
cap, or fabricated unlimited ledger. Explicit selected ceilings remain binding;
unavailable capabilities, scope/requirement changes, uncertain effects, and
stagnation hand back truthfully. This interim policy does not rewrite ordinary
stage-07 authority or protected rules.

**Layer B — cost/quota overlay (set the row that matches your billing):**

- **API / per-token billing** — a per-run token-or-cost cap and a daily-or-session cost cap. The `bench/` harness's per-run cost cap is the working precedent.
- **Subscription / OAuth billing** — you cannot observe dollar cost. Estimate observable usage from turns, tool calls and elapsed time, and honor actual provider/host quotas. Select hard proxy limits explicitly when needed; an inherited estimate alone does not stop an ordinary issue build.

---

## 12. Delivery authority and protected-judge floor

Agent-owned execution begins only after collaborative alignment, spec, and
slicing produce a human-approved envelope. Ordinary Tier A delivery is capped
at `open-pr`. K4.1 is a separate, visibly process-attested bridge that permits
only a qualifying fresh session to expected-head merge an eligible PR. It is
role separation under shared repository credentials, not credential separation
or non-bypass protection.

Every K4.1 record says `process_attested_only: true`,
`non_bypass_protection: false`, and `tier_b_authority: false`. It never grants
deploy, release, rollback, production, billing, credentials, rulesets,
visibility, or repository administration. Protected/risky paths and unresolved
human judgement always route to human merge. See
[`10-process/delivery-mission.md`](10-process/delivery-mission.md).

Tier B/C retains the protected-judge floor: the delivery principal cannot
modify its evaluator, dispatcher, evidence store, or finalizer and cannot hold
the irreversible credential. If the host cannot enforce those controls, the
lane is unavailable; no human wording or process attestation can waive or
relabel the missing assurance. V0.5.0 ships without claiming that optional K5
lane.

## 13. Quick reference

A condensed checklist version of the above, suitable for the end of long sessions:

- Asked the user before assuming scope.
- Set the §11 retry/no-progress guards and ordinary-build progress checkpoints before a run; declare any selected hard limits. Protected and autonomous delivery retain their approved mandatory ceilings.
- Used `CONTEXT.md` vocabulary throughout.
- Matched verification depth to change type.
- Patched surgically; no wholesale rewrites without permission.
- Kept one direction of data flow.
- Marked anything domain-uncertain as an open question.
- Updated `.playbook-state.yml` counters if a stage was completed.
- Recomputed the `status:` block whenever state changed.
- Logged any cadence dismissals so the retro can tune them.
- Checked any agent-facing interface work against the §9 checklist.

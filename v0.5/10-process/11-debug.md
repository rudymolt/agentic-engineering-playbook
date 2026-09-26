# 11 · Debug — investigate before fixing

> Iron law: no fixes without investigation. For any non-trivial bug or performance regression.

**This stage in one breath:** Investigate before fixing — reproduce, isolate, name the root cause. Output: a diagnosis; the fix itself is a TDD slice.

> **Failed migration?** That is an incident-shaped debug with a rehearsed first move: the rollback you executed before shipping (stage 10, "Shipping a migration"). Roll back first, investigate second.

---

## When to run

- A test that used to pass is failing.
- Production is behaving unexpectedly.
- The user reports a bug.
- A previous fix didn't actually fix the thing.

## Primary skills

`/diagnosing-bugs` (Matt; named `/diagnose` before upstream v1.0.0) or `/investigate` (gstack). Largely substitutable — pick one and stick with it for a given bug.

For an explicitly adopted project harness, `/ai-playbook-verification-harness`
provides its Launch/Doctor/Drive/Evidence/Cleanup route; use it to reproduce a
declared journey, but keep product diagnosis and any fix under this stage.

Use `/ai-playbook-why` when a diagnosis needs cited historical motivation, and
`/ai-playbook-how` to trace the current code path. Treat their source-read
results as qualified interpretation until a reproduction or other execution
supplies runtime evidence.

For a paused or cross-host diagnosis, use the conditional
[pickup brief](pickup-brief.md) to retain the tested hypothesis, failed or
reverted attempts, reproduction evidence, and one next action. It does not make
a prior diagnosis or fix fresh evidence for this stage.

Matt v1.2.3 makes evidence handling part of the loop: replace every secret in a displayed command, output, log, trace, or captured artifact with `<REDACTED>`; keep credentials in environment variables; and quote only the lines that carry the diagnostic signal. Ask for a **redacted** HAR/log/core dump when access is missing. If the redacted evidence is insufficient, stop and ask for a safer access route rather than exposing the credential. Redaction cannot fix a command whose raw output is the leak: never dump the environment or the process table (bare `env`, bare `printenv`, bare `set`, `ps -ef`, `ps aux`, `pgrep -a`, `top -c`, `htop`, `/proc/*/cmdline`, `/proc/*/environ`, or any `ps` invocation that prints a command line) — host runtimes carry authentication values there; identify processes with `ps -o pid,ppid,pgid,comm`, `pgrep -x`/`-f`/`-P` (pid-only), or an exact selector, and find a port holder with `lsof -i :<port> -t` or `ss -ltn`. [`../00-foundations.md`](../00-foundations.md) §10 holds the full rule.

In a HITL feedback loop, use a `capture` prompt only for a redacted observation that is safe to echo into the transcript. Authentication and sign-in remain an ordinary human `step`, never a captured value, because capture output is diagnostic evidence too.

Both follow the same shape:

1. **Reproduce.** If you can't reproduce it, you don't have a bug, you have a story.
2. **Build a feedback loop.** Smallest reproduction that takes <30 seconds to run; show the invocation and its redacted output as evidence.
3. **Isolate.** Bisect, comment out, mock — whatever shrinks the search space fastest.
4. **Hypothesise.** State the hypothesis explicitly. "I think X is happening because Y."
5. **Test the hypothesis.** Not the fix — the *hypothesis*.
6. **Dispose of disproved speculation.** Remove changes made solely for a
   disproved hypothesis; preserve unrelated user work and evidence-supported
   changes. A "might help" guard does not survive without evidence.
7. **Only then write the fix.** At handback, link the retained fix to the
   diagnosed cause and an executed check.

## When the bug is UI-shaped

`/browse` — gives the agent a real Chromium browser. Eyes on the actual rendered UI, not just the DOM.

`/setup-browser-cookies` first if the bug needs an authenticated session.

Keep the same action/result evidence pattern as stage 09: retain the tested
revision/environment, exercised journey, action or trigger, stable result, and
an appropriate artifact locator. Record observable side effects and reload
round trips where persistence is expected; a missing required artifact leaves
the UI reproduction unverified.

## When you've been stuck for several cycles

`continue when blocked` is a named anti-pattern. After a bounded number of attempts (default 3, or the §11 retry ceiling), stop and escalate with: blocker, evidence, attempts made, current hypothesis, specific ask, safest next options.

`/codex` — second opinion from OpenAI Codex CLI. Fresh model, fresh hypotheses. Worth the cost when you've burnt several investigation cycles.

`/pair-agent` — shares the browser session with another agent, for genuinely hard bugs where parallel exploration helps. **Optional:** not part of the prereqs Check B verified list; confirm it exists in your gstack install before relying on it.

## What this stage forbids

- Writing a fix before you have a hypothesis you've tested.
- Trying random changes to see if they help.
- "Fixing" the symptom without finding the cause.
- Closing a bug without a meaningful automated regression test, except through
  the narrow recorded exception below.

## After the fix

A meaningful regression test gets written failing first to encode the bug, then
the fix makes it green; both land in the same commit. When the only available
test would be misleading or impractical, record in the existing result or PR:

- the behaviour and why a meaningful automated regression test is impractical;
- the closest executable alternative, how it ran, and its observed result; and
- the remaining coverage gap plus a fresh independent verifier's acceptance or
  rejection.

The exception preserves reproduction, diagnosis, and evidence of the fix. The
fresh verifier independently executes the alternative or an equivalent runtime
check; reading the report is insufficient. If reliable verification is
unavailable, the change is blocked. Time pressure, dislike of tests, or avoidable
setup work do not qualify. The exception cannot override an explicitly required
test, a failing required gate, or human-owned security/data risk; return those
conflicts to the human. Then the slice runs through stages 08 and 09 like any
other change.

## State update

> **V0.5:** after applying this update, set `last_updated`, recompute the `status:` block at the top of `.playbook-state.yml` (headline, overdue cadences, features by stage), and set `status.computed_at`. Every state write sets `last_updated` — not just `/whats-next`. Update `planning/STATUS.md` / `archive/STATUS.md` too if this stage opened, closed, or archived a feature folder. The recompute is scriptable: ``python3 {playbook-path}/v0.5/scripts/compute-status.py .`` — recompute by hand only if the project cannot run Python.

```yaml
last_run:
  diagnose: {ISO timestamp}  # historical state-key name
counters:
  bugs_diagnosed_total: +1
```

---

## Next

- Root cause named → fix it via `07-implementation-tdd.md`
- Root cause is structural → open `06-architecture.md`
- Unsure → run `/whats-next`

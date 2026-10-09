# 40 · Self-improvement loop

> How the playbook gets better with every project it's used on. This file defines the three intrusion levels, the cadence-tuning loop, and the promotion criteria for moving lessons up the stack.

---

## The three layers of improvement

```
  Universal (slow, deliberate)
       ▲
       │  promotion rule: 3+ projects, or prevented incident
       │
  This playbook (versions tracked in CHANGELOG.md)
       ▲
       │  promotion rule: stable across feature retros
       │
  Per-project (CLAUDE.md, GLOSSARY.md, playbook-cadences.yml)
       ▲
       │  promotion rule: appears in 2+ session retros
       │
  Per-session (MEMORY.md, in-conversation feedback)
```

Lessons flow upward. The lower layers churn fast; the upper layers change slowly and deliberately. If a lesson stops being useful, it's demoted or deleted in a retro — there's no archive for stale advice.

Below the per-session layer sits one faster rung (V0.3.19): **loop notes** — reusable techniques a build loop captures at the slice boundary where they're discovered (`planning/{feature-slug}/loop-notes.md`, stage 07), so later slices in the same run benefit immediately. The retro decides whether any loop note climbs the ladder; unpromoted notes die with the planning folder at doc-close.

Retros use five anti-pattern names as shared diagnostic vocabulary: **Nodding** (no independent verification), **Amnesiac** (no persistence), **Manual** (no scheduling), **Blind** (no discovery), and **Tangled** (no isolation/handoff). These names are our synthesis for spotting failure shapes, not source findings to cite as evidence.

---

## The three intrusion levels

How proactive should the agent be about cadences and process? Set this per project in `CLAUDE.md`.

### Silent

The agent only responds when `/whats-next` is invoked explicitly. No ambient nudges. Good for: focused work sessions where the human is driving and doesn't want interruptions.

### Nudge (default)

At the end of every response, if a cadence is overdue, the agent appends a one-line PS:

> *PS — architecture review is overdue (4 slices since last). Run `/whats-next` for context.*

Honest, low-noise, easy to ignore. Good for: most work.

### Insist

The agent refuses to start the next stage until any blocking-severity overdue cadence is resolved. Reserved for safety-critical work like the compatibility-gated or manual security pass on auth-touching PRs. Good for: high-stakes paths where forgetting is unacceptable.

---

## The cadence-tuning loop

Cadences in `playbook-cadences.yml` are tunable, not hard-coded. The loop is:

1. **`/whats-next` makes a recommendation** based on the current state.
2. **The user accepts, defers, or skips.** Every dismissal is logged in `.playbook-state.yml` under `dismissals:`.
3. **At the retro** (stage 12), the dismissal log is reviewed:
   - If a cadence has been dismissed three times in a row, the threshold is probably wrong. Discuss and update.
   - If a cadence has never been dismissed, it's either right or never overdue. Check the latter.
   - If a cadence was accepted but the resulting work was a waste, the trigger is wrong (count vs event vs time).
4. **Update `playbook-cadences.yml` for this project.**
5. **If the same change has now been made in 3+ projects**, promote the new default to this playbook (edit `templates/playbook-cadences.yml`) and log in `CHANGELOG.md`.

---

## Promotion criteria

What earns a lesson promotion from one layer to the next.

A playbook addition must reduce net cognitive load, prevent a realistic failure, or make an important invariant enforceable. If it only adds ceremony, reject or demote it. The best process is one you forget exists.

### Session → Project (`CLAUDE.md`)

A lesson learned in one session graduates to `CLAUDE.md` when:

- It has surfaced in **two or more sessions** in this project, **or**
- It's a hard rule the user explicitly wants enforced.

### Project → Playbook (this folder)

A project-level rule graduates to the playbook when **any** of:

- It has appeared in **three or more projects**.
- It would have prevented a **real incident**.
- It changes a stage's invariants (not just its parameters).

External terms and frameworks enter the playbook only with a local definition and a provenance note (source, date, and whether the framing is the source's or our synthesis).

### Playbook → New skill

A playbook addition graduates to a new skill (Matt-style or gstack-style) when:

- It's a procedure that should run identically every time.
- It's invoked frequently enough that the cost of writing a skill is amortised.
- Its inputs and outputs are well-defined.

## Learnings refresh

On a scheduled refresh, revisit existing learnings (`CLAUDE.md` rules, `GLOSSARY.md` terms, promoted items) and mark each **keep / update / replace / archive**. Stale compounded knowledge is worse than none.

Record the run: set `last_run.learnings_refresh` in `.playbook-state.yml`.

---

## The CHANGELOG discipline

Every change to this playbook gets a `CHANGELOG.md` entry at the playbook root. Format:

```markdown
## V0.X.Y — YYYY-MM-DD

### Added
- ...

### Changed
- ...

### Removed
- ...

### Why
One short paragraph on what evidence forced the change. Cite the projects, retros, or incidents that drove it.
```

The *Why* line is mandatory. A playbook change without a reason is just churn.

---

## What this loop deliberately doesn't do

- **Its quantitative layer is observational, not a scorecard.** Applicable retros record slices shipped, post-gate rework rate, time-to-merge median/maximum, verifier passes, and execution-proven catches. Missing evidence is named rather than estimated. No target or gate is introduced until three sample application retro periods establish the first baseline; narrative evidence and human judgement remain part of every promotion decision.
- **It doesn't auto-update the playbook.** Promotions are deliberate. An agent can propose changes; only the human merges them.
- **It doesn't enforce alignment across multiple humans.** This playbook is currently single-author. Multi-author governance is on the V0.3+ roadmap.

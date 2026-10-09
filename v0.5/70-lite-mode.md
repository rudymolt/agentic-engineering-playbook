# 70 · Lite mode — the playbook for small projects

> One page, deliberately. The full 13-stage loop earns its fixed costs on substantial projects; a small tool, a script, or an experiment skips the playbook entirely if the only alternative is the full bootstrap — and then generates no learnings. Lite mode is the subset that keeps the discipline that prevents rework, drops the machinery that manages scale, and names the exact moment to graduate.

**This mode in one breath:** Align → TDD → review → ship, with the first rule fully intact and almost no files. Output: small things built with discipline, and a tripwire that upgrades you to the full loop the moment the project stops being small.

---

## When lite mode applies

All of these should be true. If any is false, run the full bootstrap instead.

- One human. No second contributor, no handover planned.
- Expected life under ~2 weeks **or** under ~3 features of work.
- No UI beyond the trivial (a CLI, a script, a notebook — not screens).
- Nothing irreversible at stake (no production data, payments, auth, or migrations).

## What survives — non-negotiable even here

1. **The first rule.** A feature request is still not a coding instruction. Lite alignment (below) before any code, every time. This rule benchmarked as the single most-broken discipline; project size does not change that.
2. **Lite alignment** — five questions, asked and answered in chat before code: What is the goal in one sentence? What are the 2–3 hard constraints? What is explicitly out of scope? What words does the domain use (and do any clash)? How will we know it works, and at which public seam will we test it?
3. **TDD for anything non-trivial.** Red, then green at a pre-agreed public seam; one failing test and one minimal implementation at a time. The verification ladder still scales effort with risk (`00-foundations.md` §4).
4. **Review before merge.** One pass: correctness, structural refactoring while green, security on any input/output boundary, and "would a stranger understand this?"
5. **Surgical edits, one direction of data flow, no invented domain rules** — the foundations still apply; it's the *stage machinery* lite mode drops, not the principles.

## What lite mode drops

- **Files:** no `.playbook-state.yml`, no `playbook-cadences.yml`, no `planning/` or `archive/` folders, no spec documents. A single `CLAUDE.md` from `templates/CLAUDE.md` (keep the first rule and constraints sections; delete what doesn't apply) and — once the project survives more than one session — a minimal `GLOSSARY.md` for vocabulary.
- **Stages:** 03 Spec, 04 breakdown, 05 triage, 06 architecture cadence, 09 browser QA (no UI), 10's doc-close ritual, 12's formal retro. Alignment answers live in the chat and in commit messages.
- **Cadences and state:** nothing is tracked, so nothing is overdue. The cost of this is exactly why the graduation tripwire below exists.

## The lite loop

```
lite{step,what}:
  1 align,   five questions answered (see above) — no code before this
  2 tdd,     failing test → minimal code → green, at a pre-agreed seam
  3 review,  one honest pass before merge, including structural refactoring
  4 ship,    merge, tag or note the version, tell whoever cares
  5 ask,     "did I learn something the playbook should know?" → 40-self-improvement.md
```

## Graduation — the tripwire, checked at every ship

Graduate to the full playbook the first time **any** of these happens:

- A second human joins (or will within a fortnight).
- The project passes ~3 shipped features or ~2 weeks of life.
- The same bug class appears twice.
- A real UI appears (screens, not output).
- You catch yourself wanting a tracker, a planning doc, or "notes for next session".
- Anything irreversible enters scope: real users' data, auth, payments, migrations.

**How to graduate:** run the full bootstrap sequence (`README.md`), keeping your existing `CLAUDE.md` and `GLOSSARY.md` as the project-filled content the templates merge around. Backfill nothing else — the full loop starts from the next feature, not retroactively. Stamp `playbook_version` as normal; record `decisions.graduated_from_lite: {YYYY-MM-DD}` in the new `.playbook-state.yml`.

Graduation is one-way. If a graduated project feels heavy, tune `playbook-cadences.yml` at the retro — don't return to lite.

---

## Next

- Lite project, new piece of work → step 1 of the lite loop (five questions)
- Tripwire fired → run the full bootstrap in `README.md`, keeping `CLAUDE.md` + `GLOSSARY.md`
- Not sure lite applies → it probably doesn't; run the full bootstrap
- Want to see the full loop worked end-to-end first → `80-quickstart.md`

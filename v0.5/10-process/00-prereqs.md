# 00 · Prereqs

> Run before any other stage. Normal sessions take the short warm path; bootstrap, upgrades, and capability changes take the cold path. Halt only when a required capability has no verified route.

**This stage in one breath:** Select warm or cold, verify every required capability has a structural, tool-assisted, or manual route, and report the active profile. Output: a pass, or one named missing capability that halts the session.

---

## Choose the path

Take the **cold path** when `prereqs_required` is true or missing; `last_run.prereqs`, `decisions.capability_profile`, `capability_routes`, or `capability_routes.verified_at` is missing; the recorded playbook version is behind; a required file is missing; the host/runtime/tool installation changed; the project changed capability profile; or the previous prereq run failed. Otherwise take the warm path. Bootstrap and `/ai-playbook-upgrade-project` set `prereqs_required: true`, so even a same-day upgrade cannot take the warm path accidentally.

## Warm path — normal session

1. Confirm the nine required root entries still exist: `CLAUDE.md`, `AGENTS.md`, `GLOSSARY.md`, `.playbook-state.yml`, `playbook-cadences.yml`, `planning/`, `archive/`, `planning/STATUS.md`, `archive/STATUS.md`.
2. Confirm `playbook_version` is current and no cold-path trigger above fired.
3. Confirm every capability needed by today's work still has a non-empty route under `capability_routes`; read [`prereqs-capability-profiles.md`](prereqs-capability-profiles.md) only when a route is unclear.
4. Apply Check D for high-stakes work and run the three cheap Check E security checks.
5. Set `last_run.prereqs` to now and recompute the status block; leave `capability_routes.verified_at` unchanged because only the cold audit rewrites the inventory.

Pass with: *“Prereqs verified (warm — {core|accelerated|extended}; required lanes covered; safety {on|off}).”* A missing root entry or changed capability routes to cold; a required lane with no route halts.

---

## Cold path — bootstrap, upgrade, or capability change

Read [`prereqs-capability-profiles.md`](prereqs-capability-profiles.md). Select **core**, **accelerated**, or **extended**; record it in `.playbook-state.yml → decisions.capability_profile`; and record the actual structural, tool-assisted, or manual route for every required lane under `capability_routes`. Then run Checks A–E. Package names choose the route; required capability lanes decide pass/fail.

## Check A — Matt Pocock accelerator inventory

Check every supported agent-runtime location before declaring a skill unavailable:

- Project roots: `.claude/skills/`, `.codex/skills/`, `.agents/skills/`.
- User roots: `~/.claude/skills/`, `~/.codex/skills/`, `~/.agents/skills/`.
- Runtime-advertised skills in the current session.

The path list below mirrors upstream's bucketed Claude layout. A flattened install at
`~/.agents/skills/<name>/SKILL.md` or `.agents/skills/<name>/SKILL.md` counts name-for-name;
that is the layout verified on this host.

<!-- generated: upstream/check-a -->
```
.claude/skills/engineering/grill-with-docs/SKILL.md
.claude/skills/engineering/setup-matt-pocock-skills/SKILL.md
.claude/skills/engineering/to-spec/SKILL.md
.claude/skills/engineering/to-tickets/SKILL.md
.claude/skills/engineering/implement/SKILL.md
.claude/skills/engineering/triage/SKILL.md
.claude/skills/engineering/tdd/SKILL.md
.claude/skills/engineering/diagnosing-bugs/SKILL.md
.claude/skills/engineering/improve-codebase-architecture/SKILL.md
.claude/skills/engineering/prototype/SKILL.md
.claude/skills/engineering/domain-modeling/SKILL.md
.claude/skills/engineering/codebase-design/SKILL.md
.claude/skills/engineering/code-review/SKILL.md
.claude/skills/engineering/research/SKILL.md
.claude/skills/engineering/wayfinder/SKILL.md
.claude/skills/productivity/grill-me/SKILL.md
.claude/skills/productivity/handoff/SKILL.md
.claude/skills/productivity/grilling/SKILL.md
.claude/skills/productivity/writing-for-agents/SKILL.md
.claude/skills/engineering/pr/SKILL.md
```
<!-- /generated: upstream/check-a -->

In upstream v1.0.0, `/diagnose` was renamed `/diagnosing-bugs`, `write-a-skill` was replaced by `writing-great-skills`, and `caveman`/`zoom-out` were removed. In v1.1.0, `/to-prd` was renamed `/to-spec`; `/to-plan` and `/to-issues` were merged into `/to-tickets`; `/implement` and `/wayfinder` were added. In v1.2.0, `writing-great-skills` was renamed `/writing-for-agents` with no alias. Old paths count only as upgrade compatibility; new work cites current names.

For upstream skill invocation, verify both harness surfaces when present: Claude Code uses `disable-model-invocation: true`; Codex uses `agents/openai.yaml → policy.allow_implicit_invocation: false`. A user-invoked skill sets both, while a model-invoked skill omits both. `/writing-for-agents` is model-invoked as of v1.2.2. Codex `agents/openai.yaml` also carries picker metadata; its presence does not by itself change authority.

If a Matt skill is unavailable, name the manual route from the capability profile. Offer `npx skills@1.7.1 add https://github.com/mattpocock/skills/tree/v1.3.1` when the user wants the accelerated profile; after installation, `/setup-matt-pocock-skills` can configure tracker/domain files. The cold path passes without the package only when every required lane has an explicit manual route.

The installer command above pins both CLI 1.7.1 and Matt's v1.3.1 tag. Select
only the registered skills needed by the project; optional `/pr` is extended.
Do not select Matt's `retro` alongside gstack's bare `/retro` without an explicit
naming plan, or select `implement-spec` as the playbook build controller.
Preview with `--list` before installing, preserve customized installed files and
record per-skill bytes against commit `24fe0ef7737efae15c87225755e9f6f5965e4888`.
Avoid a generic update command that advances the installation beyond this pin.
Existing projects first follow the [domain migration](../skills/ai-playbook-upgrade-project/MIGRATIONS.md).

## Check B — gstack accelerator inventory

Check project/user `.claude`, `.codex`, and `.agents` skill roots plus runtime-advertised skills. Check for any of these skill commands being available to the agent:

<!-- generated: upstream/check-b -->
```
/office-hours        /plan-ceo-review     /plan-eng-review     /plan-design-review
/plan-devex-review   /autoplan            /design-consultation /design-shotgun
/design-html         /design-review       /review              /devex-review
/cso                 /qa                  /qa-only             /ship
/land-and-deploy     /canary              /benchmark           /browse
/connect-chrome      /setup-browser-cookies                    /setup-deploy
/setup-gbrain        /retro               /investigate         /document-release
/document-generate   /codex               /careful             /freeze
/guard               /unfreeze            /gstack-upgrade      /learn
```
<!-- /generated: upstream/check-b -->

If gstack is unavailable, select the manual stage procedures for the required lanes and report a **core** profile. Offer the canonical install from [garrytan/gstack](https://github.com/garrytan/gstack) when the user wants acceleration. Persistent memory (`/setup-gbrain`) and role-specific reviews are extended capabilities, not universal prerequisites.

Package presence is not sufficient for an embedded review route. For every stage-08/09
upstream reviewer that today's work may use, resolve the installed `SKILL.md` that the
current runtime would execute and run:

```bash
python3 {playbook-path}/v0.5/scripts/check-upstream-compatibility.py \
  --skill {manifest-key} --source {resolved-SKILL.md} \
  --fallback "{owning manual or adapter route}"
```

Exit 0 permits only the exact embedded entry point printed for the declared report-only
source. Exit 2 means use the named fallback;
it is a safe capability selection, not a failed prerequisite. Exit 1 means the manifest
itself is invalid and blocks the accelerated route until maintenance repairs it. Record the
result under the affected `capability_routes` lane. Do not invoke an unknown, incompatible,
missing, or source-drifted reviewer to discover its behaviour at feature time.

## Check B.1 — artifact write lane

Verify that the active browser/QA/design tool can persist screenshots or reports. When a home-directory report path is sandboxed, use a repository path or temporary directory and reference the evidence from the report. The lane passes when the evidence is durable and reviewable, regardless of its default output directory. For a project that explicitly adopted a verification harness, also confirm the selected `verify-<app>` route and evidence destination are available; this optional route is not a universal Cloud prerequisite.

## Check C — project bootstrap and version

Verify the nine required root entries from the warm path. Confirm `ci-gates.md` exists or the project records an explicit human deferral.

A missing required entry does not pass by inspection alone: restore uncustomised boilerplate through bootstrap or the upgrade tiers while preserving project content. Halt when restoration needs a human-owned choice that has not been made.

Compare `playbook_version` with the newest `CHANGELOG.md` entry. If behind, offer `/ai-playbook-upgrade-project`; an upgrade may wait until a clean boundary, but the nudge is recorded.

For UI projects, verify `DESIGN-GLOSSARY.md` (or a split `design-glossary/`), `ui-kitchen-sink.html`, and `frontend-design-language-guide.html`. A missing UI artefact routes to the bootstrap choice in `../20-frontend-track.md` before UI implementation. A recorded `decisions.no_ui: true` skips this branch.

## Check C.1 — model-routing route

Verify `capability_routes.model_routing` names the actual route available in this host: current tab, automatic sidecar, or manual Conductor new-tab handoff. Confirm discovery/authentication, requested-versus-runtime-reported model identity evidence, permission strength, fresh Verify context, handoff delivery, and one fallback. Generated model self-description does not count as identity evidence. Read [`../93-model-routing-track.md`](../93-model-routing-track.md) only when model routing is needed or the route changed. Add `.playbook-routing/` to the project `.gitignore`; it holds local cross-tab handoffs, never durable feature docs. When resuming a cross-session, worker, or host handoff, reconcile the supplied [pickup brief](pickup-brief.md) before treating its route or evidence as current.

## Check D — high-stakes safety route

For production code, customer data, or frozen reference tiers, prefer structural controls such as `/guard`, host sandbox/permission profiles, or an equivalent read/write boundary. When the host lacks them, state the allowed edit directory, require human approval for destructive operations, and use a separate read-only or human verifier. Halt when neither structural controls nor that manual boundary can be maintained.

## Check E — security floor

1. `.gitignore` covers `.env`, `.env.*`, and the stack's local credential carriers.
2. A quick tracked-file scan finds no obvious assigned API keys, secrets, tokens, or passwords. A hit follows the incident rule in `../00-foundations.md` §10: report it to a human and stop; history cleanup follows the human's replacement, never precedes it.
3. The stack's lockfile is present and tracked when the ecosystem uses one.

This floor is silent when green.

---

## When all checks pass

Set `capability_routes.verified_at` and `last_run.prereqs` to now, set `prereqs_required: false`, recompute the status block, and state: *“Prereqs verified (cold — {core|accelerated|extended}; required lanes covered; optional accelerators: {available/missing}; safety {on|off}).”* Then await the user's request.

## Provenance

<!-- generated: upstream/provenance -->
The Matt Pocock accelerator inventory and behaviour contracts were verified on 2026-10-08 against the released `mattpocock/skills` v1.3.1 tag. This source review does not qualify a host installation. The gstack inventory was last verified on 2026-09-08 against the installed checkout at 1.62.0.0 (d078622). Embedded reviewer source audits are dated 2026-09-08, 2026-10-08; every inspected upstream workflow currently falls back to a playbook-owned route. Host capability claims were verified on 2026-07-09 against the first-party sources linked in `prereqs-capability-profiles.md`. Maintainers re-check released-source inventory through `../MAINTENANCE.md`.
<!-- /generated: upstream/provenance -->

For mapped domains, `GLOSSARY-MAP.md` plus every resolved mapped glossary satisfies
the domain entry prerequisite. Do not create a competing root glossary.

The separate monthly released-source comparison completed on 2026-10-08;
next due 2026-11-08. See the [dated maintenance analysis](../../analysis/2026-10-08-upstream-drift.md)
for candidate-source drift, removed/renamed commands and manual fallbacks.
Matt source adoption is recorded separately from historical host-audit dates;
the comparison and source review do not qualify installed skills or upgrade a host.

---

## Next

- All checks pass, user described a feature → open `01-align.md`
- All checks pass, user reported a bug → open `11-debug.md`
- All checks pass, user said ship/deploy → open `10-ship-and-deploy.md`
- Project behind the playbook version → offer `/ai-playbook-upgrade-project`
- Required capability has no route → halt and name the missing lane
- Unsure → run `/whats-next`

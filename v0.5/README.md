# AI Engineering Playbook — V0.5

> Read [AGENT-DIGEST.md](AGENT-DIGEST.md) first. This folder is the live public edition.

**Current release:** V0.5.1 · [Changes](CHANGELOG.md#v051--2026-10-08)

V0.5 is a human-led, agent-assisted engineering process with 13 stages, optional tracks, project templates, local skills, deterministic checks, and an optional delivery runtime. This repository contains one edition and begins with a new public Git history.

## Start a project

Pin a public release tag in a stable local checkout. Ask an agent to invoke [`/ai-playbook-bootstrap-project`](skills/ai-playbook-bootstrap-project/SKILL.md), which runs a read-only plan before writing project files. The deterministic helper is `python3 v0.5/scripts/bootstrap-project.py PROJECT --playbook-path PLAYBOOK_CHECKOUT --project-name NAME --ui no --ci existing`; use the skill to choose options and inspect changes before applying them.

The bootstrap installs `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, state and cadence files, planning/archive scaffolding, and selected local skills. It records the absolute path to the pinned checkout. Application projects should not point at a development checkout, since changes there can alter the instructions they read before their recorded version changes.

## Use and maintain the playbook

- The [agent digest](AGENT-DIGEST.md) routes each request to the right stage. Stage files live under [`10-process/`](10-process/).
- [`index.html`](index.html) is the interactive guide for humans. The [operating guide](50-how-to-write-code-with-ai.html) and [theory guide](60-the-theory-behind-the-playbook.html) provide more detail.
- [`skills/`](skills/) contains bootstrap, upgrade, release, model-routing, and other local skills. [`delivery/`](delivery/) holds the optional process-attested delivery runtime.
- [`92-wayfinder-track.md`](92-wayfinder-track.md) covers user-invoked discovery; [`93-model-routing-track.md`](93-model-routing-track.md) covers verified Plan, Build, and Verify route choices.
- [`templates/`](templates/) is the source for project-managed files. Agents should use the bootstrap and upgrade tools rather than hand-copying from memory.
- [`MAINTENANCE.md`](MAINTENANCE.md) describes public maintenance and release checks. [`CHANGELOG.md`](CHANGELOG.md) starts with V0.5.0.

Run `python3 v0.5/scripts/verify-playbook.py` from the repository root before a release. The verifier covers unit tests, documentation and skill conventions, links, generated manifests, and the delivery checks supported by the host.

**Conductor setup lane:** when bootstrap runs in Conductor, the bootstrap skill inspects project-specific workspace settings and presents the exact setup and run-command changes in its read-only plan before applying them.

## Existing projects

Use `/ai-playbook-configure` to review and edit Plan, Build, Verify and escalated
repair defaults through guided or expert typed chat, with migration preview
and explicit Apply. QA inherits Verify; Coordinator is display-only. Configure keeps
escalation constraints and active work unchanged. Presentation, billing,
reusable personal defaults and named presets save only to an explicitly
previewed local destination; no model launches.

Use `Edit skills` to review the five stage-owned job bindings for alignment,
specification, implementation, code review and application QA. A selected
skill must pass its source and contract checks at Apply and again at its owning
stage; a saved binding does not grant permission to run it. `Presets` and
`Load preset <name>` change only the draft. `Save defaults` or
`Save preset <name>` followed by `Apply preference` saves reusable choices to
the reviewed personal destination; project `Apply` is a separate action.

The [configuration boundary](scripts/playbook-config.md) is also the
effective-default reader for existing lane gates. New projects still use the
existing bootstrap approval gate, which can preview seeding personal defaults
or a named preset without replacing existing project configuration. Loading a
preset edits a draft; only explicit Apply changes an existing project.
Explain shows claim-specific sources, successful check dates, uncertainty and
published API rates where established. Explicit Refresh rechecks advice; ordinary
checkpoints reuse it for up to 24 hours. An unavailable saved route stays visible
until an explicit replacement or another selection is previewed. Source outages
retain the last actual successful date and do not create new recommendations.

At Plan, Build and Verify boundaries, the agent shows the effective saved route
and any supported evidence-backed advice. The human selects the route; the
stage checks live availability and identity before launch. For an approved
feature, `build one`, `build all` and `build to <slice>` control how many eligible
slices run before the next handback. An optional `fast` suffix requests Codex
fast mode for that Build and its returned fixes and fresh Verify when available.
The [model routing track](93-model-routing-track.md) and
[build guide](10-process/07-implementation-tdd.md) contain the gates and limits.

Projects already using a private V0.4.2 checkout should use the tested [transition guide](skills/ai-playbook-upgrade-project/MIGRATIONS.md) to adopt a public V0.5 release without overwriting their content. Projects still on V0.3 first use their private migration bridge. No earlier edition source tree is distributed here.

## License and attribution

Original public work is under [Apache-2.0](../LICENSE). The adapted upstream skills carry their own `NOTICE` files; retain those notices when redistributing.

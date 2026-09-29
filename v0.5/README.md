# AI Engineering Playbook — V0.5

> Read [AGENT-DIGEST.md](AGENT-DIGEST.md) first. This folder is the live public edition.

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

Use `/ai-playbook-configure` to review project defaults and edit the Build
model through typed chat, with migration preview and explicit Apply. S1 keeps
other roles, escalation constraints and active work unchanged; it does not
launch a model. The [configuration boundary](scripts/playbook-config.md) is
also the effective-default reader for existing lane gates. Broader setup,
skills, presets and recommendations are not yet part of this narrow route.

Projects already using a private V0.4.2 checkout should use the tested [transition guide](skills/ai-playbook-upgrade-project/MIGRATIONS.md) to adopt a public V0.5 release without overwriting their content. Projects still on V0.3 first use their private migration bridge. No earlier edition source tree is distributed here.

## License and attribution

Original public work is under [Apache-2.0](../LICENSE). The adapted upstream skills carry their own `NOTICE` files; retain those notices when redistributing.

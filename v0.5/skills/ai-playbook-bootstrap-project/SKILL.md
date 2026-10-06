---
name: ai-playbook-bootstrap-project
description: Safely bootstrap a new or existing project with the current AI engineering playbook and, when applicable, its Conductor workspace setup. Use when starting a project, initializing playbook files, graduating from lite mode, or repairing an incomplete first-time setup.
---

# /ai-playbook-bootstrap-project

Set up one project without overwriting anything it already owns. The skill handles human choices; `bootstrap-project.py` performs deterministic copies, path resolution, state initialization, and local-skill installation.

## Procedure

1. **Inspect the target.** Confirm the target project path, infer its display name, inspect existing playbook files, and read `70-lite-mode.md`. Offer lite mode only when every lite criterion holds; otherwise recommend full mode. Completion criterion: the target, project name, and lite/full choice are explicit.
2. **Run the Conductor setup lane.** When `CONDUCTOR_WORKSPACE_PATH` or `CONDUCTOR_ROOT_PATH` is present, or the human explicitly asks for Conductor support, invoke the bundled `conductor` skill provided by the Conductor host. Inspect the project's README/onboarding docs, manifests and lockfiles, environment examples, generated files, local services and databases, fixed ports, normal development commands, and existing `.conductor/settings.toml`, `.conductor/settings.local.toml`, `.worktreeinclude`, or legacy `conductor.json`. Establish whether the project runs safely from a worktree, whether companion services fit within Conductor's allocated port range, and whether workspaces can run concurrently. If the bundled skill is unavailable, record a blocking manual review instead of inventing configuration. Completion criterion: either the lane is not applicable, or its evidence and remaining decisions are explicit.
3. **Collect choices.** For full mode, ask whether the project has a real UI. If yes, choose playbook defaults or stop for a custom design interview; if no, record `no_ui: true`. Ask whether to copy the portable CI gates or preserve/map existing CI. For an applicable Conductor lane, ask which approved scope to use: `shared` writes code-reviewed `.conductor/settings.toml` in the target project; `personal` writes `.conductor/settings.local.toml` at the repository root for this Mac only; `not now` leaves a named manual review. Do not infer this scope from the host. Completion criterion: `ui` is `no` or `defaults`, `ci` is `copy` or `existing`, and Conductor scope is settled when applicable; custom UI work remains a named manual decision.
4. **Present the dry-run.** Run `python3 {playbook-path}/v0.5/scripts/bootstrap-project.py {project-path} --playbook-path {playbook-path} --project-name "{name}" --ui {no|defaults} --ci {copy|existing}`. Show creates, safe merges, preserved files, local-skill installation, and remaining decisions. When the Conductor lane applies, append the bundled skill's exact proposed settings diff, setup command, named Run commands, `CONDUCTOR_PORT` or fixed-port behavior, run mode, Files to copy or `.worktreeinclude` changes, rationale, validation steps, and known limitations. Distinguish documented project facts from inferred recommendations. Do not use a generic framework template. Completion criterion: the user has seen and approved the complete plan, including every Conductor write and command.
   For a new project with explicitly selected personal defaults, add
   `--preferences-dir {reviewed-local-directory}` and Configure's current
   `--discovery-command` adapter, optionally `--preset {name}`. Show the plan's
   complete `.playbook-config.json` creation, model/skill origins, dependencies
   and `seed_revision`. Personal data is read-only; billing and local source
   resolution never enter the project file. Missing qualification or unknown
   fields block instead of silently dropping a binding. Existing projects use
   Configure's Load/preview/Apply; bootstrap never replaces their configuration.
5. **Apply safe setup.** Re-run the deterministic playbook command with `--apply`. Exit 0 means deterministic setup completed; exit 2 means safe files were written but manual reviews block certification; exit 1 means inspect possible partial changes before retrying. Apply the separately approved Conductor diff only at its chosen scope, preserving existing configuration for an explicit merge or legacy migration. Never put secrets in tracked settings. Completion criterion: every approved safe change is applied and diffed, with no existing project content overwritten.
   Seeded Apply also requires the same seeding options and exact
   `--seed-revision {approved-seed_revision}`. Exit 2 can instead mean the seed
   was blocked before writes; use the result's explicit message. Changed
   personal inputs, availability or eligibility require a new read-only plan
   and approval. Seed only after safe bootstrap completes without manual
   reviews. Report partial setup or recovery honestly. Subsequent ordinary
   bootstrap checks omit seeding flags, preserving the adopted configuration.
6. **Resolve manual reviews.** For each `manual review:` item, show the current content, expected behavior, and one minimal merge proposal. Apply only after explicit approval. Re-run until the deterministic bootstrap exits 0 and then once more to prove no changed files. Completion criterion: every review is accepted or recorded as an explicit deferral, and the project is not stamped current while required setup remains unresolved.
7. **Activate and validate Conductor.** A setup script added after workspace creation does not run retroactively; after approval, run its safe setup command once in the current workspace or state why it could not be run. Validate commands from the workspace directory in Conductor's non-interactive shell. Before shared settings activate, run each long-lived command directly with the approved Conductor environment, confirm the expected port or health signal, then stop it; after merge, use Conductor's Run action once to confirm the menu integration. Shared settings become active only after they are merged to the remote default branch; changing them on the workspace branch does not update project settings. A personal repository-root setting may provide immediate Run behavior on this Mac, but never write it without the explicit `personal` choice. Completion criterion: current-workspace setup is accounted for and the human knows exactly when future workspaces receive the configuration.
8. **Verify and hand off.** Run stage 00's cold path, confirm the project-local skills are discoverable under `.agents/skills/`, and confirm deterministic status with `python3 {playbook-path}/v0.5/scripts/compute-status.py {project-path} --check`. When the user has selected application verification, offer `/ai-playbook-verification-harness` as a separate scoped proposal after bootstrap; its installation never generates or adopts a harness by itself. Include the Conductor setup/Run validation result and any merge-to-activate action in the handoff. Completion criterion: prereqs pass, status is current, and the user receives “Playbook {version} bootstrapped” plus the first-feature or `/whats-next` handoff.

## Lite mode

When the user chooses lite mode, follow `70-lite-mode.md` directly. Preserve any existing `CLAUDE.md`; keep only the first rule and project constraints, add a minimal `CONTEXT.md` after the project survives one session, and do not create full-mode state, cadence, planning, or archive files. Graduation re-enters this skill in full mode.

## Guardrails

- Treat every differing existing file as project content: preserve it and require a minimal reviewed merge.
- Resolve `{path-to-playbook}` and `{playbook-path}` to the actual absolute playbook root during setup.
- Keep `.agents/skills/` synchronized only through explicit bootstrap or upgrade work; never silently replace a customized local skill.
- Copy UI defaults only after the user chooses them; custom UI setup stays human-led.
- Use `.worktreeinclude` or Files to copy for static gitignored inputs; use setup scripts for installs, generation, symlinks, and workspace-specific resources.
- Use named Conductor Run scripts for development servers, workers, watchers, and useful test loops. Select concurrent mode only when ports and shared resources are isolated; otherwise select nonconcurrent mode or Spotlight testing.
- Keep setup and Run commands self-contained for Conductor's non-interactive shell, and keep multi-process Run commands in one process group.
- A successful file copy is not a prereq pass. Stage 00 cold verification remains the final gate.

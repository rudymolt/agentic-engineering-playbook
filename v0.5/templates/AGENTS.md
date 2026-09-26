# AGENTS.md — {project name}

> Quick-start index for AI engineering agents. Read **only the files needed for the requested scope**. Don't try to read the whole repo "to understand it first" — that's the enemy of momentum.

---

## Before you do anything

1. Read `{playbook-path}/v0.5/AGENT-DIGEST.md` — the playbook entry point.
2. Read `CLAUDE.md` for the project contract — **including its first rule: a feature request routes to stage 01 alignment, never directly to code.**
3. Read `CONTEXT.md` for the domain vocabulary you'll need.
4. Run the prereqs check in `{playbook-path}/v0.5/10-process/00-prereqs.md`.

## Routing — which files to read for which task

| Task | Read first |
|---|---|
| Anything new | `CLAUDE.md`, `CONTEXT.md`, `.playbook-state.yml`, the relevant stage in `{playbook-path}/v0.5/10-process/` |
| New feature | `{playbook-path}/v0.5/10-process/01-align.md` — **mandatory first stop; no source edits before alignment is recorded** |
| Choose a Plan, Build, or Verify model | `{playbook-path}/v0.5/93-model-routing-track.md`, then `/model-router` |
| Bug fix | `{playbook-path}/v0.5/10-process/11-debug.md` |
| Refactor | `{playbook-path}/v0.5/10-process/06-architecture.md` |
| UI change | `{playbook-path}/v0.5/20-frontend-track.md`, then `DESIGN-GLOSSARY.md`, then `ui-kitchen-sink.html` |
| New screen design | `frontend-design-language-guide.html` (surface decision rules) before choosing components |
| Ship / deploy | `{playbook-path}/v0.5/10-process/10-ship-and-deploy.md` |
| "What should I work on?" | Run `/whats-next` |

## Project-specific file pointers

{Fill in as the project grows.}

- **Domain modules:** {e.g. `src/lib/{domain}/`}
- **API routes:** {e.g. `src/app/api/`}
- **UI components:** {e.g. `src/components/`}
- **Tests:** {e.g. `__tests__/`, `e2e/`}
- **Migrations:** {e.g. `migrations/`}

## What not to do

- Don't read `archive/`.
- Don't read planning folders of features not currently in `active_features`.
- Don't treat `.playbook-routing/` handoffs as durable feature docs; use them only to resume the named pending route.
- Don't invent vocabulary not in `CONTEXT.md`.
- Don't rewrite a file wholesale unless the user has explicitly asked.
- Don't run the full test suite for a typo fix; don't ship a parser rewrite with only a type-check (see verification ladder in `{playbook-path}/v0.5/00-foundations.md` §4).

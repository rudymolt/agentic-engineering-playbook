# ci-gates.md — {project name}

> The minimum machine-enforced gate set for any PR containing agent-authored changes. Stack-agnostic statement first; map it to your CI system in the table below. Copied at bootstrap (ask-first — never imposed on a project with existing CI).

---

## The minimum gates

Every PR with agent-authored changes must pass all of these before merge:

1. **Tests green.** The project's full relevant test suite, not a subset chosen by the author of the change.
2. **Lint / typecheck green.** Whatever static gates the stack has, at the project's configured strictness — never loosened within the PR being gated.
3. **No new high-severity dependency advisories.** If the diff touches dependencies, the advisory scan runs against the updated lockfile.
4. **Secrets scan clean.** No credential patterns in the diff (the stage 00 Check E heuristic at minimum; a real scanner when CI provides one).
5. **Acceptance criteria present.** The PR template records the slice's success target before review: feature → acceptance criteria + demoable outcome; bug → reproduction + expected behaviour; refactor → behaviour-preservation check; investigation/spike → named artefact or decision.
6. **One human approval.** The merge is the human's act, always. An agent never merges, never approves its own PR, and never marks a gate as passed.

The human-approval gate assumes an independent review pass, not self-review.

## Rules about the gates themselves

- **The agent never bypasses, force-merges, or disables a gate.** Not for a hotfix, not "temporarily".
- **CI configuration is itself gated.** A change to CI config goes through the same review as code — an agent editing the pipeline to make a failing gate pass is the exact failure mode this file exists to prevent.
- **Overrides are human and recorded.** If the human decides to ship past a failing gate, they say so explicitly in the PR (who, why, which gate) — a recorded override, never a silent skip. Stage 10 checks for this.
- **Local gates are allowed.** The minimum gate set may also run pre-push, not only in CI. `kunchenguid/no-mistakes` is one worked example of the pattern; using the tool is optional, and its "AXI" command is unrelated to this playbook's AXI principles.
- **Classification is mandatory; mechanisation is opportunistic.** The digest classifies hard rules by layer. This template only encodes portable gates; do not add stack-specific hooks here unless the project already owns that stack.

## Portable gate mappings

- **Secret scan:** run a diff-level secret scan in CI or pre-push. If no scanner exists, run the stage 00 heuristic manually and record the result in the PR body.
- **Never merge or approve your own PR:** enforce with branch protection where available. If the host lacks branch protection, record the human approver in the PR body and leave merge to the human.
- **Acceptance criteria presence:** add a PR template checkbox or equivalent field:
  - `[ ] Success target recorded: feature AC / bug reproduction / refactor preservation check / investigation artefact.`

## Mapping to this project's CI

| Gate | This project's implementation |
|---|---|
| Tests | {e.g. GitHub Actions: `test` job — `python3 -m unittest` / `npm test`} |
| Lint / typecheck | {e.g. `lint` job — `ruff check` / `tsc --noEmit`} |
| Dependency advisories | {e.g. `pip-audit` / `npm audit --audit-level=high` / Dependabot alerts} |
| Secrets scan | {e.g. `gitleaks` action / GitHub secret scanning} |
| Acceptance criteria presence | {e.g. PR template checkbox; manual check recorded in PR body} |
| Human approval | {e.g. branch protection: 1 review required, no self-approval, no force-push to main} |

{If the project has no CI yet: the gates still apply, run manually at stage 08/10 and recorded in the PR description, until CI exists. Note that decision here with a date.}

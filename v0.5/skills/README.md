# Local skill invocation contract

The playbook's local skills use the invocation mechanics from `/writing-for-agents`.

Provenance: [Matt Pocock's `writing-for-agents`](https://github.com/mattpocock/skills/tree/v1.2.3/skills/productivity/writing-for-agents), its skill-mechanics reference, and the locally installed skill were reviewed on 2026-08-08. The dual-harness metadata mechanics are the source contract; the reach analysis and authority framing below are this playbook's synthesis. `writing-great-skills` is the removed pre-v1.2 name and remains valid only in explicit upgrade history.

## Taxonomy

- **Model-invoked:** `description` is present, `disable-model-invocation` is absent, and `agents/openai.yaml` omits `policy.allow_implicit_invocation: false`. The agent may discover the skill from a natural-language trigger, and another skill may reach it. Discovery does not expand authority: external writes, releases, upgrades, and other consequential actions still require the user's request or the skill's own approval gate.
- **User-invoked:** `disable-model-invocation: true` and `agents/openai.yaml → policy.allow_implicit_invocation: false` agree. The human must type the skill name; neither the agent nor another skill can silently start it. Its description is a short human-facing label, not a trigger list.

Every local skill carries `agents/openai.yaml` with Codex picker metadata (`interface.display_name` and `interface.short_description`). Metadata and frontmatter must agree on invocation ownership; picker visibility never broadens the user's authority grant.

<!-- generated: upstream/local-skills -->
local_skills[12]{name,invocation}:
  whats-next, model
  model-router, model
  ai-playbook-upgrade-project, model
  ai-playbook-bootstrap-project, model
  ai-playbook-design-review, model
  ai-playbook-verification-harness, model
  ai-playbook-maintain-verification-harness, model
  ai-playbook-why, model
  ai-playbook-how, model
  ai-playbook-blast-radius, model
  ai-playbook-configure, user
  ship-release, model
<!-- /generated: upstream/local-skills -->

The manifest-owned `/ai-playbook-deliver` runtime is installed separately from
`delivery/MANIFEST.yml`. Its metadata keeps implicit invocation disabled: a
natural-language feature request still routes through stages 01–04, and only
an explicit approved **deliver to PR** or admitted K4.1 action starts it.

## Why all eleven are model-invoked

| Skill | Reach that earns model invocation | Authority boundary |
|---|---|---|
| `/whats-next` | Ambiguous routing and ambient cadence nudges must reach it without the human remembering a command | It recommends; the human accepts, defers, or skips |
| `/ai-playbook-bootstrap-project` | A first conversation or missing state must reach safe setup without relying on the human to remember the README or Conductor setup sequence | It presents one dry-run and applies only after the human chooses mode, UI, CI, any shared-or-personal Conductor scope, and approves the complete plan |
| `/ai-playbook-upgrade-project` | Stage 00 must reach it when a project's recorded version is behind | It presents the tiered plan before edits and asks for project-content decisions |
| `/ai-playbook-design-review` | Every UI-touching stage-08 gate must reach one transaction-safe evidence procedure | It reviews report-only; the stage owner decides and applies any remediation |
| `/ai-playbook-verification-harness` | A request to prove application behavior must reach a scoped, project-owned route without inventing a universal stack harness | It proposes before writing; a target, concrete scope approval, and fresh execution evidence remain required |
| `/ai-playbook-maintain-verification-harness` | An adopted harness needs complete maintenance coverage without turning a one-entry doc-close update into a sweeping claim | It reports first; only explicit scoped correction may change owned map/harness paths; the owning stage may refresh opt-in clock state only after an accepted complete clean/changed result |
| `/ai-playbook-why` | Historical questions need a discoverable evidence route rather than a plausible source-reading story | It returns cited evidence, inference, contradictions, and unknowns; it does not change the repository or establish intent from code alone |
| `/ai-playbook-how` | Current-behavior questions need a discoverable path trace that does not overclaim runtime proof | It separates source-read interpretation from executed runtime evidence; it does not mutate the repository or invent callers/tests |
| `/ai-playbook-blast-radius` | Concrete risky revisions need a discoverable route from material assumptions to executable affected-code evidence | It reports unproven risks and requests scoped proof helpers; it does not lower risk classes, authority gates, or fresh verification requirements |
| `/ship-release` | Natural-language requests such as “cut a release” must reach the release reconciler | Its description requires explicit release intent; it preserves approval, push, tag, and GitHub invariants |
| `/model-router` | Lane boundaries and typed `models` / `openai defaults` replies must reach one consistent chooser | It selects and launches a route only after the human's lane action; stage and external-mutation gates remain intact |

## Embedded upstream skill contract

`/ai-playbook-configure` is user-invoked. S2 edits all four project model roles
with typed migration preview and explicit Apply; it never starts a model.
QA inherits Verify and Coordinator is observed display-only. Guided/expert
presentation is saved locally through a separate explicit destination preview,
without applying the project draft. New projects retain the bootstrap gate.
The shared [configuration boundary](../scripts/playbook-config.md) supplies
effective preferences to model-router. Bootstrap/upgrade install the skill
through the registry without adopting or replacing project settings.

An upstream skill is **embedded** when a playbook stage selects it as one capability
inside a larger workflow. That differs from an explicit user request to run the upstream
skill as the top-level workflow: embedded execution does not transfer ownership of the
enclosing repository transaction.

Precedence is explicit user request → project-local `AGENTS.md` / `CLAUDE.md` / approved
slice contract → playbook stage → playbook adapter → upstream defaults. The adapter
declares:

- `commit_owner`: the playbook stage.
- `commit_strategy`: the project's approved strategy; an embedded reviewer never changes it.
- `mutation_mode`: `report-only`.
- `question_transport`: structured control when available, otherwise the identical inline typed options.
- permitted side effects: repository reads, verification commands, and evidence writes to the declared review location.
- prohibited side effects: product/source edits, commits, stash, push, routing/bootstrap/migration edits, configuration changes, telemetry opt-in, and upgrades.

Structured question controls are optional transport; the typed options and the human's
reply are the contract. The adapter waits when a decision is required and never infers
consent. Embedded skills do not self-upgrade or perform incidental setup; maintenance
owns upstream promotion.

`../upstream-integrations.json` records the exact source tested for each embedded
integration. Resolve the installed `SKILL.md` that the current runtime would execute and
run `../scripts/check-upstream-compatibility.py` before direct invocation. A compatible
decision names the only permitted embedded entry point. Unknown, missing, or source-drifted integrations take the manifest's fallback without invoking
the upstream skill. A known incompatible source also takes the fallback: this preserves
upstream safety invariants instead of trying to override executable instructions with
weaker prose.

A report that recommends a code change does not apply it. Accepted remediation becomes a
separate generator task owned by stages 07/09, follows the project commit strategy, and
returns to fresh independent verification.

## Agent-facing command guidance

When a skill authors or changes an agent-facing CLI, API, MCP server, or tool
interface, follow the canonical checklist in [foundations §9](../00-foundations.md#9-design-the-agent-facing-surface).
It covers preconditions and corrective errors, appropriate machine output,
stable documented exit semantics, and truthful destructive-action previews.
Do not copy that checklist into individual skills or retrofit unrelated existing
commands.

## Editing rule

Keep descriptions branch-complete and short, keep ordered steps in `SKILL.md`, and disclose branch-only reference in sibling files. Phrase the desired behaviour positively; reserve prohibitions for irreversible guardrails and pair them with the safe action.

Human questions remain portable: inline typed options are the canonical contract. A host structured-question control may render them, but if it is unavailable or errors the skill immediately asks the same options in text; it never stalls or infers consent.

Run `python3 v0.5/scripts/check-skill-metadata.py` after any local skill edit. It verifies the table above against frontmatter, bounds model-facing descriptions, and rejects the old negative-guardrail headings.

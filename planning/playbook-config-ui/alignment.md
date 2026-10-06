# Playbook configuration UI — alignment

Status: approved product decisions and interaction direction. The subsequent specification, breakdown and build-all S1–S7 approval supersede the historical authority statements below. See [execution status](execution.md); S8 live qualification remains human-owned.

## Confirmed decisions — round 1

1. First release covers choosing and editing model and skill defaults, presets, availability checks, and a preview before applying changes. Package/playbook update management and identity management are deferred.
2. The first interface is `/ai-playbook-configure` in chat, backed by a validated configuration file. Native host choices enhance a working typed-option interface. Terminal and browser interfaces are deferred until settings and questions are stable.
3. Optimise for an individual managing multiple projects, with reusable personal defaults and explicit project settings. Guided/expert preference is per user, retaining the prior brainstorm decision.

The user accepted all three recommendations explicitly. No implementation or publication is authorised by this planning session.

## Confirmed decisions — round 2

4. Personal defaults seed new projects. Existing projects keep their settings until the user explicitly applies updated defaults with a preview. Active feature selections are unchanged.
5. First-release model settings cover Plan, Build, Verify and escalated repair. QA inherits Verify; Coordinator identity is displayed rather than changed. Independent QA selection and Coordinator switching are deferred.
6. Skill choices are job-specific, such as alignment, specification, implementation, code review and application QA. Installed skills are eligible only when they meet the job's requirements.
7. Prove the first release in Codex directly and through Conductor. Typed choices are the reliable baseline; other hosts require separate verification before support is claimed.
Additional requirement: recommend models and explain why they suit what the user is trying to achieve, with cost efficiency as an explicit objective. The decisions below settle recommendation timing and billing support; the final round below settles the evidence approach; do not claim a model is objectively cheapest without supporting evidence.

## Confirmed decisions — round 3

8. Recommend role defaults during setup and allow task-aware recommendations at existing model-selection checkpoints. Feature-specific overrides do not rewrite project defaults. Optimise expected cost of a correct, verified result, including retries, rather than token price alone.
9. Support subscriptions and pay-per-token API billing. Use verified prices and labelled estimates for API costs. For subscriptions, discuss available limits and observable consumption. Unavailable cost information remains explicitly unknown.
10. Custom local skills and supported collections are both in scope. All must meet the selected job's requirements; installation alone does not prove eligibility.
11. Commit project model and skill choices in a dedicated, shareable configuration file. Personal preferences, billing details and machine-specific discovery remain local. Existing state records retain active selections and execution history.

## Confirmed decisions — round 4

12. Justify recommendations with maintained task-fit guidance, current verified pricing and relevant project results when available. Include the reason, evidence date and uncertainty. No automatic paid comparison benchmarks or unsupported claims of cheapest performance. Official AI-lab documentation is an explicit source of model recommendations.
13. Start with one Recommended setup adapted to available models and billing, plus user-saved presets. Defer additional named bundles until evidence supports meaningful differences.
14. Guided first-run setup asks only for missing preferences, then proposes a complete configuration with a short explanation beside each choice. Offer Apply, Edit, Explain or Not now. Expert mode presents the same choices more compactly. Applying configuration does not start a build.

## Additional confirmed requirement — model releases and documentation changes

15. When discovery finds a newly available model, check whether its provider's official model guidance and pricing have changed before making a new recommendation. Updated documentation can change the recommendation for existing models too; reassess the affected roles, not only the new model.

## Skill source labels

The user approved the mockup direction and requested source prefixes for skills by job. Show `(collection) skill-name` in proposals, editing choices and change previews, for example `(Matt Pocock) tdd` and `(gstack) qa`. Read provenance from the registry or installed metadata; do not guess from a skill name. `wayfinder` belongs to Matt Pocock’s collection. Label native workflows `(Playbook)`, project-owned routes `(Project)` and custom local skills `(Custom)` when no more specific verified source is available. Preserve adaptation attribution when a Playbook skill derives from another collection, such as pstack. Source labels do not imply eligibility.

## Unavailable-model recovery — mockup revision

User feedback: recommend a replacement when a model is unavailable, then ask whether to accept it. Offer **Accept replacement**, **Choose another model**, and **Not now**. Recommend only a route verified as available and suitable for the affected role; explain why, including cost implications and uncertainty. Acceptance changes the draft proposal, followed by the normal preview and Apply gate. Declining the recommendation opens the existing model editor for that role. No silent persistence, model launch or changes to active selections. If no eligible alternative exists, show the limitation and recovery action instead of inventing one. Cover discovery-time failures and unavailability detected again before Apply.

## Recommendation evidence

Keep three evidence classes separate: provider guidance on suitability, published pricing and billing facts, and results observed on comparable project work. Official recommendations are useful inputs, not independent proof of cross-provider superiority or current availability in the user's host. Saved settings remain preferences; actual launch availability is checked again.

Official source examples checked on 2026-09-29:

- [OpenAI model documentation](https://developers.openai.com/api/docs/models) distinguishes models by task suitability and cost priorities.
- [Anthropic model-selection guide](https://platform.claude.com/docs/en/about-claude/models/choosing-a-model) considers capabilities, speed, cost and effort, and calls for evaluation on the intended use case.

These are examples of source types, not fixed model rankings. The eventual implementation must attach claim-specific sources and dates to recommendations rather than treating this planning snapshot as current pricing or availability evidence.

## Documentation refresh plan

- Trigger during configuration and existing lane-boundary discovery when a new model or changed model version is observed. First use has no baseline and requires a source check. This is part of recommendation discovery, not the deferred package/playbook update manager or a background watcher.
- Retrieve the relevant official model-selection guidance, model-specific capabilities/reasoning guidance and pricing. Compare with the last successfully checked source using revision metadata where trustworthy and a content fingerprint otherwise. Record source URL, last successful check, available source revision and the evidence behind affected recommendations. Do not infer a publication date from the check date.
- Recompute affected task-fit and cost recommendations when guidance, prices or capabilities change. A new model triggers assessment, not an assumption that it is better. Show a short explanation of what changed and its implications, alongside the sources and uncertainty.
- Preserve current project defaults and active runs. Proposed changes follow the ordinary preview and explicit Apply flow; feature overrides follow the existing selection gate. Discovery never grants automatic switching authority.
- If a source is unavailable or incomplete, retain the last evidence with its actual date and mark the refresh incomplete. Do not silently present stale guidance as current or claim a new model is the best-value choice without adequate evidence. Existing approved choices can remain configured, subject to normal live route checks.
- Keep discovery fingerprints and recommendation-source cache local. Do not treat a persisted full catalog or prior availability check as launch authority. Coalesce refreshes within one discovery pass rather than fetching the same provider pages for every role.

Required scenarios for the future specification: new model with changed guidance; new model with unchanged guidance; changed guidance affecting an existing model; documentation/pricing temporarily unavailable; refreshed advice proposing different defaults while an active feature retains its approved route.

## Grounded constraints

- Existing model defaults and feature/run selections are separate. Changing defaults must not rewrite an active selection or execution history (`v0.5/templates/.playbook-state.yml`, `v0.5/skills/model-router/SKILL.md`).
- Current roles expose Plan, Build, Verify and escalated repair defaults. QA inherits Verify; the coordinator is the active chat (`v0.5/10-process/09-qa.md`, `v0.5/93-model-routing-track.md`). Independent QA configuration would change routing contracts.
- Registry capability categories are not interchangeable skill slots. Installed, registered, compatible and available are different properties (`v0.5/scripts/upstream_registry.py`, `v0.5/upstream-integrations.json`).
- The installed-skills audit is a maintainer report, not a project-aware pass/fail gate (`v0.5/scripts/audit-upstream-installed.py`).
- The current router requires live availability checks and forbids treating a saved full catalog as current proof. Saved preferences must be revalidated before launch (`v0.5/93-model-routing-track.md`).

## Next review

The user approved the revised interactive mockup, including skill-source labels and suggested replacements for unavailable models. The [specification](spec.md) and its technical recommendations are accepted for breakdown. The [implementation slices](slices.md) are approved and their local tickets are published. The mockup uses illustrative model placeholders and does not select models for this planning session.

The accepted specification defines migration, settings ownership and validation, custom-skill eligibility evidence, ordinary evidence freshness and acceptance criteria. The eight-slice breakdown is approved; S1 is the first available implementation target. Preserve the agreed preview, routing authority, privacy boundaries and immutable active selections.

Still deferred: updates and identity management; standalone terminal/browser interfaces; independent QA model selection; Coordinator switching; automatic paid benchmarks; unverified claims of support for other hosts. Current implementation and PR authority is recorded in [execution status](execution.md), not inferred from alignment alone.

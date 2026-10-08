# Playbook configuration UI — alignment

> Archived feature record: S8 accepted on 2026-10-08; shipped in PR #20 as
> `0a3770e7306ec80fdf6b07aab88008cf2897aa77`. Earlier pending gates and failures
> below are dated history, not current instructions. See [closeout](closeout.md)
> for final candidate evidence, durable source pointers and remaining closeout.

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

## Amendment — reviewed provider guidance (2026-10-05)

Five independently reviewed parser candidates inferred task fit from free-form provider pages. Each was rejected for prose the parser did not understand: enclosing or sibling conditions, raw newlines, split labels, subordinate headings, struck-through text and external quotations. Interpretation of provider prose is not a bounded problem, so the owner changed the evidence source.

Owner decisions:

1. Task-fit guidance comes only from a reviewed list shipped with the edition. A model absent from the list has no task recommendation until a reviewed release adds it; availability, pricing and a "no reviewed guidance yet" notice still appear. AC18 is narrowed accordingly.
2. The live official page only confirms a reviewed entry. The entry is withdrawn, with "provider wording changed since review", unless its section heading is immediately followed by a leaf block whose rendered text equals the reviewed paragraph and contains the entry's model link. Whitespace, invisible characters and inline formatting are ignored. Neither the heading nor the block may be inside or contain deleted, struck-through or quoted markup (`del`, `s`, `strike`, `blockquote`, `q`); inert template descendants never confirm. Added qualifiers inside the paragraph withdraw the entry.
3. The list is an edition data file changed only by a reviewed PR. Release checks flag entries the current page no longer confirms.
4. The first list holds one entry: GPT-6 Astra for coding, from OpenAI's model-selection onboarding paragraph, the only guidance verified against the retained current page.
5. Prose inference of task fit is removed. Official pricing-table parsing is unchanged.
6. Cycle 9 acceptance amendment: viewing advice retains the existing 24-hour evidence cache, but Accept replacement performs one fresh retrieval of the original reviewed entry's official source before editing the draft, including retained and recovered proposals. A saved confirmation alone cannot authorize acceptance. An unavailable source, withdrawal or changed current reviewed entry refuses acceptance with an explanation and preserves draft, project and approval bytes; it never reranks or chooses another model. Acceptance requires a newly confirmed current entry and all existing route gates. This fetch is an explicit acceptance boundary independent of cache publication success; cached advisory display keeps its existing freshness rules. No new durability or invalidation subsystem is requested.

Cycle 10 rendered-text clarification: markup-shaped text in raw-text/RCDATA bodies, conditional `noscript` content and `plaintext` supplies no actual heading, leaf paragraph or model link. HTML self-closing flags do not close nonvoid elements. Script escaped/double-escaped transitions and `plaintext` through EOF must preserve this boundary; visible entries after genuine closes remain usable. This clarifies decision 2, without prose inference or whole-page semantic analysis.

Cycle 11 visibility clarification: an HTML `hidden` attribute excludes the element and its descendants regardless of case or value, including `until-found`. Nonrendered inline text, links and blocks cannot supply reviewed text, required links or adjacency. Closed `dialog` content and closed `details` content outside its first direct `summary` are likewise excluded; `datalist` content, metadata elements, image-map areas and hidden inputs supply no rendered block. Visible content after genuine closes remains usable. This makes decision 2's existing rendered-block boundary explicit, without CSS/JavaScript rendering, a new dependency or whole-page semantics.

Cycle 12 visibility clarification: excluding hidden content must preserve structural boundaries that end paragraphs, headings, list items and table cells. A hidden block start can still end a visible paragraph; text outside that paragraph cannot be joined back into its reviewed leaf block. Withdraw interrupted source paragraphs instead of admitting a shorter repaired leaf block. Preserve empty structural barriers from stray paragraph closes. Withdraw ambiguous table content outside cells or captions rather than reconstructing a browser tree. Valid visible successors and hidden inline additions remain usable. This clarifies decision 2 without changing the reviewed list or fresh acceptance contract.

Cycle 13 visibility clarification: native control and fallback content models cannot turn apparent markup into confirming blocks. Withhold select/option/optgroup, button, meter/progress, embedded fallback and frameset subtrees; conservatively withhold SVG/MathML subtrees, including HTML integration points. Preserve an ambiguous boundary instead of deleting visible qualifiers or reconstructing ignored, relocated or reinterpreted markup. Nested controls, ignored document/table tokens and foreign breakout markup must not escape through unrelated closes or self-closing HTML flags. Correctly closed scopes retain usable visible successors, ordinary forms and hidden inline additions. This clarifies decision 2's existing rendered-block requirement; it adds no browser/CSS/JavaScript renderer or dependency and leaves cycle 9 acceptance unchanged.

Cycle 14 visibility clarification: a literal `hidden` attribute, including on an apparent ancestor, cannot suppress the native/foreign content-model ambiguity barrier. Nested selects or buttons, implicitly closed controls, ignored starts and foreign breakouts can expose qualifiers outside the apparent hidden scope. Withhold affected headings, leaf paragraphs, model links and pricing context rather than infer visibility from that attribute. Preserve ordinary hidden inline additions, raw-text/inert exclusions, structural boundaries and visible successors after correctly closed scopes. This clarifies decision 2 and cycle 13's bounded exclusion; the reviewed list and cycle 9 acceptance contract remain unchanged.

Cycle 15 visibility clarification: the same ambiguity barrier applies to every ignored or misplaced scope family, including table structural tokens outside a table, nested forms and repeated document tokens, even under apparent hidden or closed ancestors. Unrelated closes and nonvoid self-closing flags cannot erase visible qualifiers from reviewed units or pricing context. Preserve hidden inline additions, ordinary forms, raw-text/inert exclusions and correctly closed successors. This completes decision 2's existing bounded exclusion without a new contract or change to cycle 9 acceptance.

Cycle 16 visibility clarification: active HTML formatting, including anchors, can survive explicit or implied structural ends and reconstruct hidden or excluded context later. Retain a conservative ambiguity barrier for detached formatting and adoption/misnesting, including nested anchors and `nobr`, rather than certify affected text, links or pricing. Explicit own closes and genuine cell/caption or `marquee` formatting boundaries release correctly closed visible successors; raw/inert and withheld native/foreign descendants never enter this formatting state. Preserve genuine closed hidden-inline positives. This clarifies decision 2's existing nonrendered-content exclusion without a new contract, renderer, dependency or change to cycle 9 acceptance. An own close across open blocks can clone the formatting entry; repeated own closes alone cannot prove release, so retain that adoption barrier until a genuine formatting marker clears the affected context.

Cycle 17 visibility clarification: end tags cannot release hidden ancestors across native table, cell/caption or other scope boundaries. Generic closes across structural boundaries and ambiguous partial ancestor closes retain visibility or ambiguity barriers; document ends do not remove ancestry. Genuine explicit/implied closes retain usable visible successors, including cell/caption formatting-marker release. This clarifies decision 2's existing nonrendered-content exclusion without a renderer, dependency, new contract or change to cycle 9 acceptance.

Cycle 18 visibility clarification: ruby and its `rb`, `rp`, `rt` and `rtc` descendants are inline phrasing content. Hidden annotations contribute no text; visible annotation text still participates in exact matching. Apply bounded implied annotation ends before visibility filtering, preserving enclosing `rtc` for `rt`/`rp` starts and native scope boundaries. Genuine nested blocks and excluded or ambiguous descendants still withdraw affected units. This clarifies decision 2 without a new contract, renderer, dependency or change to cycle 9 acceptance.

Cycle 19 visibility clarification: normalize native HTML `image` starts to void `img` before visibility filtering. Legacy metadata starts `basefont` and `bgsound` and the legacy control `keygen` are void; native `frame` starts outside a frameset are ignored. Their attributes cannot hide following visible text. Preserve actual hidden containers and ancestors, withheld foreign/integration scopes and raw/inert boundaries, including usable visible successors and pricing. This clarifies decision 2 without a new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

Cycle 21 visibility clarification: in native HTML, CDATA-shaped and other marked declarations are bogus comments ending at their first `>`. Abrupt empty comment closes (`<!-->`, `<!--->`) take precedence over later full closes. Visible suffix text still participates in exact heading, leaf paragraph, required-link and pricing checks. Genuine comments and harmless closed bogus declarations do not withdraw unrelated visible units. Preserve raw/inert and foreign withholding, hidden/excluded descendants, native leaf/document-order rules and cycle 9 acceptance/cache/byte-preservation semantics. This clarifies decision 2 without a new contract, renderer or dependency.

Cycle 22 visibility clarification: withholding does not turn native template declarations into foreign CDATA. Native bogus comments end at the first `>`, preserving genuine template closes and visible successors. Only exact uppercase CDATA in an actual SVG/MathML declaration context consumes through `]]>`; its close-like text cannot release inert copies. Distinguish nesting, integration descendants, ignored native tokens, foreign breakouts and self-closing foreign elements; foreign names do not enter HTML raw-text or template mode. Foreign own closes cannot release an enclosing native template, and integration encodings use the first attribute. Native raw bodies and hidden/excluded descendants remain withheld. This clarifies decision 2 without a new contract, renderer, dependency or change to cycle 9 acceptance.

Cycle 23 visibility clarification: ignored native select end tokens, including premature foreign integration ancestor ends, cannot change declaration namespace. Option/optgroup ends affect only permitted current entries; genuine select/template closes preserve visible successors. A genuine select close restores foreign CDATA where appropriate, so close-like copies remain excluded. Preserve raw/inert and hidden descendants, ambiguity barriers, pricing and cycle 9 fresh acceptance/cache/byte-preservation rules at all four seams on both interpreters. This makes decision 2 precise without a new contract, renderer or dependency.

Cycle 24 visibility clarification: native `</br>` tokens are attribute-free `br` starts and separate rendered words in headings, leaf paragraphs and required links. Breaks between words preserve normalized whitespace; hidden starts and raw/inert descendants contribute no separator. Ignored select tokens and withheld foreign content retain their existing barriers. Cover pricing and all four seams on both interpreters with fresh-original-source-once and unchanged refusal bytes. This clarifies decision 2 without a new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

Cycle 25 visibility clarification: finish native EOF text before confirming guidance or extracting pricing. Bare `<` and `</` and buffered character references participate in rendered text; incomplete native start/end tags, comments and declarations supply no visible text. Valid unclosed visible elements retain their own text without invented closing tokens. Preserve raw/RCDATA, hidden, inert, foreign and select exclusions and interrupted-paragraph barriers. Verify all four seams on both interpreters, with usable nonfirst-link baselines, pinned clocks, one fresh original-source fetch and byte-preserving refusal. This clarifies decision 2 without a new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

Non-goals: no natural-language interpretation of provider pages, no automatic list updates and no project-local guidance lists.

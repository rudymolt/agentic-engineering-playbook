# Playbook configuration — specification

> Archived feature record: S8 accepted on 2026-10-08; shipped in PR #20 as
> `0a3770e7306ec80fdf6b07aab88008cf2897aa77`. Earlier pending gates and failures
> below are dated history, not current instructions. See [closeout](closeout.md)
> for final candidate evidence, durable source pointers and remaining closeout.

Status: approved specification, test boundary, separate host qualification and 24-hour recommendation-evidence freshness policy. The user subsequently approved build-all S1–S7 and a reviewed feature PR. See [execution status](execution.md); no merge, release or deployment is authorised, and S8 live qualification remains human-owned.

Source of product decisions: [alignment](alignment.md) and [approved chat flow](chat-flow.md). Current integration evidence: [engineering notes](engineering-notes.md).

## Problem statement

A person using the Playbook across several projects needs a clear way to choose suitable models and skills, understand their cost and capability trade-offs, and keep those choices useful as tools change. Today the relevant defaults, routing rules and compatibility evidence are spread across state, stage instructions and upstream registries. Editing them directly makes it difficult to see what will change or distinguish project defaults from choices already approved for an active feature.

## Solution

Provide `/ai-playbook-configure`, a guided chat conversation that discovers available routes, asks only for missing preferences, and presents a complete proposal. The user can Apply, Edit, Explain or leave without saving. Expert mode presents the same decisions more compactly. Typed replies work throughout; native host controls are optional.

Save shareable project defaults separately from personal preferences and execution state. Recommend a model for each supported role with an explanation of suitability, cost evidence and uncertainty. Show the source before each skill name. When a saved model becomes unavailable, recommend a verified replacement and offer acceptance or another choice before returning to the normal preview and Apply gate.

Initial host qualification covers Codex directly and through Conductor. The HTML mockup is an interaction review artifact, not a browser settings product.

## User stories and acceptance criteria

| ID | User story | Acceptance criterion |
| --- | --- | --- |
| AC01 | As a new user, I want a useful proposal without answering questions about every setting. | Read existing context and preferences; ask only missing goal, billing or presentation preferences. Present all four model roles and five skill jobs, with reasons, scope and destinations before Apply. |
| AC02 | As a returning user, I want to edit settings without repeating setup. | Display current values and their origins. Editing one choice preserves all unrelated draft values and returns to a complete before/after proposal. |
| AC03 | As a user in a text-only host, I want every decision to remain available. | Setup, role and skill selection, explanations, preset actions, recovery and Apply all have typed choices. Native controls are never required, including inside an editor. |
| AC04 | As an experienced user, I want a shorter presentation. | Expert mode changes presentation only; it retains the same choices, validation, scope preview and access to reasons. Presentation preference is personal. |
| AC05 | As a project owner, I want explicit defaults for each model role. | Configure model identity, supported runner and reasoning for Plan, Build, Verify and escalated repair. QA inherits Verify. Display the observed Coordinator identity without changing it. Preserve repair triggers, budgets and authority rules. |
| AC06 | As a cost-conscious user, I want recommendations connected to the work. | Explain project/task fit, relevant risk, available routes, reasoning choice, cost evidence, source dates and uncertainty. Do not equate cheapest tokens with cheapest verified outcome. |
| AC07 | As an API customer, I want honest cost information. | Use verified provider rates with units, currency and check date. Label workload estimates and assumptions, including retries when evidenced. If inputs are unavailable, show unknown rather than a fabricated total. |
| AC08 | As a subscription customer, I want advice relevant to my allowance. | Describe observable usage or limits where available. Missing consumption data is unknown; API token prices are not presented as the subscription bill. Support unknown or mixed billing across routes. |
| AC09 | As a user, I want to understand why a choice is recommended. | Explain identifies the role, model, runner, reasoning, evidence and limitations. Opening an explanation neither selects nor launches the candidate. |
| AC10 | As a user whose model is unavailable, I want a suggested replacement. | Keep the unavailable saved value visible, recommend one verified suitable route with reasons, and offer Accept replacement, Choose another model or Not now. Acceptance updates only the draft; another choice opens the affected role's editor. Saving still requires Apply. If no eligible route exists, explain recovery without inventing one. |
| AC11 | As a user, I want settings to remain reliable between preview and save. | Recheck file revisions, selected route availability and skill eligibility before Apply. Changed inputs invalidate the old proposal and require a refreshed preview or recovery choice. Never silently substitute a route. |
| AC12 | As a user, I want to know where each skill comes from. | Proposals, editors and change previews show verified source prefixes, such as `(Matt Pocock) tdd` and `(gstack) qa`. Label Playbook workflows, project routes, custom sources and adaptations accurately. Wayfinder is attributed to Matt Pocock. |
| AC13 | As a user, I want to choose skills by the job they perform. | Bind alignment, specification, implementation, code review and application QA to eligible skills or explicit approved fallback routes. A binding can be an ordered composition where the job contract supports it. Category membership or installation alone never proves eligibility. |
| AC14 | As a user with custom skills, I want to reuse them safely. | Apply the same input/output, invocation, side-effect and compatibility requirements as supported collections. Show unmet requirements and the existing approved fallback when evidence is missing. Configuration does not experimentally invoke a skill, install an adapter or grant it new authority. |
| AC15 | As a person managing several projects, I want reusable personal defaults and presets. | Start with one Recommended proposal plus user-saved presets. New projects can be seeded from personal defaults through bootstrap's preview. Loading a preset into an existing project produces a draft; saving a preset never changes another project. |
| AC16 | As a collaborator, I want portable project settings. | Share model and skill preferences using logical identities and project-relative references. Keep billing, personal preferences, machine discovery and source caches local. Missing local dependencies are reported on another machine rather than silently changed. |
| AC17 | As a user with work in progress, I want it protected from settings changes. | Configuration never rewrites pending approved routes, active feature selections, unattended-run approvals or historical execution records. Task-specific overrides remain feature-scoped. |
| AC18 | As a user, I want advice to reflect new models and changed documentation. | First discovery and newly observed model/version changes trigger official confirmation of reviewed guidance, capability/reasoning and pricing checks. Reassess affected existing models too. A model without a reviewed guidance entry shows availability, pricing and "no reviewed guidance yet" rather than inferred task fit. Explain changed advice and sources without automatically changing defaults. Accept replacement independently retrieves the original reviewed entry's official source once and requires a newly confirmed current entry plus complete route gates; saved confirmation alone cannot authorize a draft edit, including retained or recovered proposals. Unavailability or withdrawal refuses with an explanation and preserves draft, project and approval bytes without reranking. |
| AC19 | As a user during a provider outage, I want transparent limitations. | Retain the last successful evidence date; label incomplete or stale checks. Keep valid saved choices available subject to live route checks. Do not claim fresh best-value advice for a new model without evidence. |
| AC20 | As an existing Playbook user, I want migration to preserve my customisations. | Preview migration from legacy defaults, preserve supported custom model/runner/reasoning choices, and flag conflicts or unsupported settings. Do not modify runtime history, unrelated settings or project content. |
| AC21 | As a user, I want truthful save and cancellation results. | Not now performs no configuration/preset write. Successful Apply reports exact changed destinations and validation. On failure, report restored state or a specific incomplete transaction requiring recovery; never report partial success as completion. No build starts. |
| AC22 | As a maintainer, I want updates to preserve intentional choices. | Version configuration and job contracts; invalidate eligibility when a selected skill's source changes. Upgrades preview migrations and preserve customisations. Unsupported newer schemas block writes. No per-turn updater, package installation or automatic preset rewrite is introduced. |
| AC23 | As a user selecting a feature model, I want project defaults and task-specific advice to work together. | Existing lane-selection gates display the effective project preference with a task-aware recommendation when justified. Explicit feature choices and the feature-scoped `openai defaults` command retain their authority. Discovery, recommendations and configuration do not grant permission to launch. |

## Implementation decisions

Product behaviour above is approved in alignment and the mockup. The engineering choices below were accepted for breakdown with the specification review.

### One configuration boundary

Use one configuration service for read, propose, explain, validate and apply. The chat skill presents its structured results and collects choices. Reuse existing model discovery and routing authority, upstream provenance and compatibility checks, and bootstrap/upgrade managed-file mechanisms. Do not build a second launcher or turn the maintainer installed-skills audit into a project gate.

Keep persistence, evidence retrieval and host discovery behind this boundary. Expose stable result states: proposal ready, decision required, blocked, unchanged, applied and recovery required. Validation errors identify the affected setting and a corrective action. Model IDs and skill metadata are data, never executable commands or authority instructions.

### Ownership and resolution

| Owner | Contents | Resolution rule |
| --- | --- | --- |
| Versioned project configuration | Role preferences; logical skill bindings; schema version | Authoritative defaults for new choices after adoption. Shareable and separate from execution state. |
| Personal local configuration | Guided/expert preference; billing facts; reusable defaults and named presets | Seeds new projects. Never overlays an existing project's defaults implicitly. |
| Local discovery and evidence cache | Source URLs, check dates, content revisions/fingerprints, bounded recommendation evidence and discovery version fingerprints | Advisory only. No persisted full route catalogue or cache entry authorises launch. |
| Existing execution state | Approved pending/feature routes, runtime capability evidence, run approvals, history, counters and status | Remains owned by existing stage transitions. Configure does not rewrite these records. |

For a new lane selection, precedence is explicit approved feature choice, then adopted project default, then an unmigrated legacy project default, then the edition default. This is preference resolution, not an exemption from live availability and approval checks. Malformed adopted configuration is an error, not a reason to silently use a lower-precedence default.

A migrated project has one authoritative default source. Legacy default entries are retained as inert migration history where safe; updated consumers must not read them as a competing source. Mark adoption in the project configuration, not by rewriting active records. The feature-scoped `openai defaults` command remains an explicit override and does not modify project configuration.

The final consumer inventory and concrete filenames are implementation design details; source ownership and precedence above are contractual.

### Preview, acceptance and Apply

A proposal binds the complete before/after values, destinations, relevant input revisions and validation evidence. Edits or newly discovered changes invalidate that proposal. Presets and model-replacement acceptance are edits to the draft, not save operations.

Apply rechecks the relevant settings and availability, then validates the complete proposed configuration before writing. A proposed choice that becomes unavailable enters the same replacement conversation. Final route availability and authoritative model identity are checked again by the existing launcher at execution time.

Use staged writes and recoverable transaction bookkeeping for operations spanning project and personal settings. Readers must not accept an incomplete configuration transaction as a new valid configuration. After a failure, restore prior settings where possible; if recovery is incomplete, name the affected destination, preserve recoverable evidence and block further configuration writes until reconciliation. Do not overwrite concurrent edits during rollback. Runtime records remain outside the transaction.

Discovery may refresh a bounded local cache even if the user leaves without saving. The exit message distinguishes these read-side checks from changes to defaults or presets.

### Model recommendations and freshness

Filter by verified access, role requirements and existing permission/verification contracts before comparing candidates. Recommendations may select model, supported runner and reasoning, but cannot weaken independence, repair limits, stop rules or authority boundaries. Cost ranking is conditional on evidence; when comparable results are absent, present a reasoned starting choice without claiming a measured winner.

Keep provider suitability guidance, pricing facts and comparable project outcomes distinct. Attach claim-specific sources and successful check dates. Explain material changes in advice. Project observations stay local and must not be invented from unrelated benchmarks.

Provider suitability guidance comes only from a reviewed guidance list shipped with the edition; the playbook does not interpret provider prose. Each entry names the model, provider, tasks, risks, official source URL, section heading, the exact reviewed paragraph and the review date. A retrieval confirms an entry only when that section heading is immediately followed by a leaf block whose rendered text equals the reviewed paragraph and contains the entry's model link, ignoring whitespace, invisible characters and inline formatting. Neither may be inside or contain `del`, `s`, `strike`, `blockquote` or `q`; inert template descendants never confirm. An unconfirmed entry is withdrawn with "provider wording changed since review" and supplies no task fit or replacement. The list changes only through a reviewed edition release; release checks report entries the current page no longer confirms.

Accepted ordinary freshness policy: reuse successful guidance/pricing evidence for up to 24 hours during configuration or an existing lane-discovery checkpoint. First use, a newly observed model/version or an explicit refresh checks immediately. Check once per discovery pass; no background watcher and no checks on unrelated turns. A failed refresh remains visibly stale/incomplete, with the original successful date. This interval governs recommendation evidence, never model availability or launch identity.

Cycle 9 amendment: Accept replacement performs one fresh retrieval of the original reviewed entry's official source before editing the draft, independently of ordinary advisory cache reuse and publication success. A saved confirmation or stale fallback cannot authorize acceptance. Unavailability, withdrawal or a changed current reviewed entry refuses with an explanation, preserves draft, project and approval bytes, and never reranks or chooses another model. Acceptance requires a newly confirmed current entry and complete existing route gates. A cache write failure is nonfatal only when this attempt obtained an actual fresh source confirmation. Cached advisory data can still be displayed under its existing freshness rules; no new durability or invalidation subsystem is requested.

Cycle 10 clarification: literal bodies of `script`, `style`, `xmp`, `iframe`, `noembed`, `noframes`, `textarea` and `title`, conditional `noscript` content and `plaintext` cannot supply confirming heading, paragraph or link elements. Ignore self-closing flags on nonvoid HTML elements. Raw bodies end only at their own genuine close; `plaintext` continues through EOF. In script double-escaped text, a close-like `</script` token returns to escaped text instead of closing the element. Ordinary scripts and actual visible entries after genuine closes remain usable. The same boundary applies to pricing tables, Configuration, the public CLI and release checking on supported interpreters; no dependency or whole-page semantic inference is added.

Cycle 11 clarification: `hidden` attribute presence excludes an element and its descendants, regardless of attribute case or value (including `until-found`). Exclude hidden inline text, required links and intervening blocks from rendered text/link collection and block adjacency. Apply the same native visibility boundary to closed `dialog` content and closed `details` content except its first direct `summary`; `datalist` content, metadata elements, image-map areas and hidden inputs do not create rendered blocks. Preserve nested scopes and nonvoid self-closing behaviour, exclude ambiguous visible attributes, and retain usable visible guidance and pricing after genuine closes. This boundary applies at all four public seams and fresh acceptance; it adds no CSS/JavaScript renderer, dependency or whole-page semantics.

New model discovery can change advice about existing models. Unchanged source content produces no invented change notice. Evidence refresh never rewrites saved settings or active approvals. For an unavailable model, recommend a replacement only when availability and role suitability are established; missing pricing weakens cost claims rather than being hidden.

Cycle 12 visibility clarification: apply bounded implied paragraph, heading, list-item and table-cell ends before visibility filtering, including hidden and nonvoid self-closing starts. A hidden block that ends a paragraph cannot join its visible prefix and suffix into one reviewed leaf block. Withdraw interrupted source paragraphs instead of admitting a shorter repaired leaf block. A stray paragraph close supplies an empty structural barrier. Ambiguous table content outside cells or captions cannot confirm; withdraw it instead of reconstructing a browser tree. Preserve valid visible successors and hidden inline additions at all four seams, with the existing fresh acceptance, cache and byte-preservation rules unchanged.

Cycle 13 visibility clarification: withhold unproven confirming blocks in select/option/optgroup, button, meter/progress, embedded fallback and frameset scopes, and conservatively in SVG/MathML subtrees including HTML integration points. Retain ambiguous barriers rather than omit visible qualifiers. Nested controls, ignored document/table tokens and foreign breakout markup cannot escape through unrelated closes or self-closing HTML flags. Preserve ordinary forms, correctly closed visible successors, hidden inline additions and visible pricing. The same bounded exclusion applies at all four seams and fresh acceptance, without a browser/CSS/JavaScript renderer, dependency or change to the reviewed-list/cache/byte-preservation contract.

Cycle 14 visibility clarification: native/foreign content-model ambiguity barriers remain even when the scope or an apparent ancestor carries `hidden`. Nested selects/buttons, implicit control closes, ignored starts and foreign breakouts cannot erase potentially visible qualifiers in headings, leaf paragraphs, model links or prices. Conservatively withdraw affected units without reconstructing a browser tree. Ordinary hidden inline additions and correctly closed visible successors remain usable; raw-text/inert exclusions, cycle 12 structural boundaries and the reviewed-list/fresh acceptance/cache/byte-preservation contract remain unchanged.

Cycle 15 visibility clarification: retain that barrier consistently for ignored or misplaced table structural tokens, nested forms and repeated document tokens under apparent hidden or closed ancestors. Nested/misnested closes and nonvoid self-closing flags cannot erase visible qualifiers in matched headings, leaf paragraphs, required model links or pricing context. Preserve hidden inline additions, ordinary forms, correctly closed successors and raw-text/inert exclusions. This completes the existing rendered-text requirement; cycle 9 acceptance and advisory caching remain unchanged.

Cycle 16 visibility clarification: active formatting elements, including anchors, may survive structural ends and reconstruct context beyond the apparent visibility stack. Withhold affected reviewed units, links and pricing through detached formatting and adoption/misnesting, including nested anchors and `nobr`, even when visibility was inherited from hidden or closed ancestors. Do not reconstruct a browser tree. Explicit own closes and genuine cell/caption or `marquee` formatting boundaries retain usable visible successors; raw/inert and withheld native/foreign descendants supply no formatting state. Genuine closed hidden-inline additions remain usable. This clarifies the existing rendered-text exclusion at all four seams; the reviewed list and cycle 9 cache/fresh acceptance/byte-preservation contract are unchanged. An own close across open blocks can clone the formatting entry; repeated own closes alone cannot prove release, so retain that adoption barrier until a genuine formatting marker clears the affected context.

Cycle 17 visibility clarification: native end-tag scope must retain hidden ancestors across tables, cells/captions and other native boundaries. Generic closes cannot cross structural boundaries; document ends retain ancestry. Withhold ambiguous partial ancestor closes instead of rebuilding a browser tree. Genuine explicit/implied table closes release cell/caption formatting markers and preserve visible successors. Apply the same exclusion to reviewed text, links and pricing at all four seams; retain the reviewed list and cycle 9 cache/fresh acceptance/byte-preservation rules unchanged.

Cycle 18 visibility clarification: preserve ruby and `rb`, `rp`, `rt`, `rtc` as inline phrasing in headings, leaf paragraphs and required-link context. Exclude hidden annotations and ancestors while retaining visible annotation text in exact matching. Before filtering a ruby descendant start, apply implied annotation ends only at the stack top with ruby in native scope; `rt`/`rp` retain an enclosing `rtc`. Preserve genuine nested-block, excluded-content and ambiguity negatives at all four seams, with cycle 9 acceptance/cache/byte-preservation unchanged. No new renderer, dependency or contract is added.

Cycle 19 visibility clarification: normalize native HTML `image` starts to void `img` before visibility filtering; treat `basefont`/`bgsound` metadata and the legacy control `keygen` as void and ignore native `frame` starts outside a frameset. Following visible qualifiers still participate in exact matching regardless of attributes on those tokens. Preserve actual hidden ancestors/containers, withheld foreign/integration scopes, raw/inert boundaries and usable guidance/pricing successors at all four seams. No new contract, renderer, dependency or change to cycle 9 acceptance/cache/byte-preservation semantics.

Cycle 21 visibility clarification: native CDATA-shaped and marked declarations are bogus comments ending at the first `>`, not SGML sections ending at `]]>`. Abrupt empty comment closes (`<!-->`, `<!--->`) precede later full closes. Preserve visible suffix text in heading, paragraph, required-link and pricing context. Genuine comments and harmless closed bogus declarations leave unchanged visible units usable, including elsewhere on the page. Retain raw/inert and foreign withholding, hidden/excluded descendants and native leaf/document-order semantics at all four seams on both interpreters. The reviewed list and cycle 9 acceptance/cache/byte-preservation contract remain unchanged; no renderer or dependency is added.

Cycle 22 visibility clarification: native declarations inside inert templates still end at the first `>`, so genuine template closes retain usable visible successors. Exact uppercase CDATA consumes through `]]>` only in an actual SVG/MathML declaration context, preserving close-like inert copies. Distinguish nested namespaces, integration descendants, ignored native tokens, foreign breakouts and self-closing foreign elements; foreign names cannot enter HTML raw-text or template mode. Foreign own closes cannot release an enclosing native template, and integration encodings use the first attribute. Preserve native raw bodies, hidden/excluded descendants, leaf/order rules, pricing and fresh draft-only acceptance at all four seams on both interpreters. This clarifies the existing rendered-text requirement without a new contract, renderer, dependency or change to cycle 9 cache/byte-preservation semantics.

Cycle 23 visibility clarification: ignored or misplaced native select end tokens cannot unwind a foreign integration ancestor or change declaration namespace. Option/optgroup ends affect only permitted current entries, while genuine select/template closes preserve visible successors. After a genuine select close, actual foreign CDATA still consumes close-like text through `]]>`. Preserve raw/inert and hidden descendants, ambiguity barriers, pricing and fresh draft-only acceptance at all four seams on both interpreters. This clarifies the existing rendered-text requirement without a new contract, renderer, dependency or change to cycle 9 cache/byte-preservation semantics.

Cycle 24 visibility clarification: native `</br>` tokens supply the same word separator as attribute-free `br` starts in reviewed headings, leaf paragraphs and required links. Between-word breaks retain normalized whitespace positives. Hidden starts, raw/inert descendants, ignored select tokens and withheld foreign boundaries retain their existing exclusions; self-closing starts keep their visibility attributes. Verify pricing and all four seams on both interpreters, preserving cycle 9 fresh acceptance/cache/byte-preservation rules without a new contract, renderer or dependency.

Cycle 25 visibility clarification: finalize native EOF text before guidance and pricing extraction. Bare `<` and `</` become text and buffered character references resolve; incomplete native start/end tags, comments and declarations do not become visible text. Valid unclosed visible elements retain their text without synthetic closing tokens; incomplete pricing tables remain unknown. Preserve interrupted-paragraph barriers and raw/RCDATA, hidden, inert, foreign and select exclusions. Cover all four seams on both interpreters with usable nonfirst-link baselines, pinned source/Configuration clocks, one fresh original-source fetch, draft-only success and independent proposal/project/approval byte preservation on refusal. No new contract, renderer, dependency or change to cycle 9 cache/fresh acceptance semantics.

### Skill contracts and provenance

Define versioned contracts for the five jobs, using current stage requirements for inputs, outputs, invocation owner and permitted effects. Supported bindings may refer to a single skill, an ordered composition, a Playbook adapter or an explicit stage-owned manual/project route. A manually selected route still has verification obligations; it is not a bypass.

Use collection plus stable skill identity, not a display name alone. Show adaptation provenance without attributing a Playbook adapter to an upstream author as if it were the unmodified upstream skill. Store machine-specific resolution only locally; a custom skill outside the project uses a portable logical identity and a local binding, not an absolute path in shared settings.

For embedded reviewers, reuse exact-source report-only compatibility decisions. Unknown, changed or incompatible source uses the declared adapter/manual alternative or blocks that binding. Other jobs require equivalent evidence for their own contract rather than inheriting the reviewer's report-only constraint. An installed skill's self-description alone cannot certify compatibility. Proof generation or installing missing software is a separately scoped task.

### Adoption and future updates

Existing projects without the new configuration continue using the current rules. First configuration use offers a migration preview importing current project defaults; it must not replace them with personal defaults simply because a personal preset exists. A new project can use personal defaults through the existing bootstrap approval.

Upgrade integration preserves the managed-file merge base and project customisations. Unsupported schema versions, conflicting duplicate keys or invalid role/binding values produce actionable errors without rewriting the input. Repeated successful migration is idempotent. Validate selected skills against current source fingerprints on configuration discovery and at their existing invocation gate; source changes invalidate prior eligibility.

Configuration can describe preferences for portable hosts, but unsupported/unverified host routes are labelled explicitly and are not offered as verified execution choices. Initial release qualification is limited to Codex and Codex through Conductor.

## Testing decisions

**Primary test boundary:** the public configuration boundary. Supply a project fixture, personal preferences, discovery/evidence fixtures and a clock; inspect the proposal, errors and final persisted result. Assert externally visible behaviour rather than internal helper calls or incidental wording.

Use temporary project fixtures and command-level integration tests, following the existing bootstrap and upstream compatibility tests. Cover:

- First setup, returning edits, cancellation, unchanged Apply and all four role preferences.
- Resolution precedence; migration of custom legacy defaults; repeat migration; invalid/newer schema; preserved unrelated content and execution-state records.
- Personal-default seeding, preset loading/saving and isolation between two projects.
- All accepted replacement paths, no suitable replacement, unavailable route after preview, source changes and concurrent file edits.
- Eligibility by job, ordered bindings, provenance, name collisions, custom local resolution, incompatible embedded reviewers and declared fallbacks.
- Reviewed guidance confirmed, withdrawn when its paragraph, heading, link or markup context changes, and absent for unlisted models; guidance unchanged/changed after model discovery; changed guidance affecting existing models; expired evidence without a new model; unavailable docs/prices; API/subscription/unknown billing with no invented savings.
- Failure injection for validation, individual writes and recovery; no false completion and no overwrite of concurrent edits.
- Byte preservation of approved active selections, mission approvals and execution history across configuration changes.

**Host qualification:** run the same scripted conversation in Codex directly and through Conductor. Confirm typed-only completion, optional native-control fallback, observed Coordinator identity, configured defaults reaching the existing lane gate, replacement selection, and no build/dispatch from Apply. Use authoritative host evidence for availability; no paid cross-model comparison is part of these tests. Any billable launch needed for later execution qualification is separately scoped and budgeted.

**Verification scope:** browser checks apply to the local mockup only; they cannot establish correctness of the real chat skill, configuration persistence or host routing. The shipped feature needs independent review and risk-appropriate tests under the Playbook, followed by the repository's required release verification.

## Out of scope

- Installing or updating models, skills, packages, the Playbook or host software through this interface.
- Account/email identity management; storing credentials; automatic provider switching or new billing agreements.
- A standalone browser settings app or terminal wizard.
- Configurable Coordinator switching or an independent QA model.
- Automatic paid benchmarks, guaranteed cheapest-model claims or autonomous application of new recommendations.
- Creating a verification harness merely by selecting a QA route.
- Editing escalation authority, run ceilings, permission strength or active delivery approvals.
- Claiming verified support for other hosts before qualification.

## Review and open questions

Amendment (2026-10-05): after five rejected prose-parser candidates, the owner replaced inferred provider guidance with the reviewed list above and narrowed AC18; see the [alignment amendment](alignment.md#amendment--reviewed-provider-guidance-2026-10-05).

Product questions and the two engineering recommendations are settled: one configuration test boundary with separate host qualification, and a 24-hour ordinary evidence-freshness interval. The user accepted both after a plain-English explanation. Neither changes the approved interaction flow.

Scope-guardian check: keep one chat surface, one configuration boundary and existing routing/compatibility authorities. No parallel routing engine, automatic updater, general plugin marketplace or recommendation benchmarking service is required.

Coherence check: personal defaults seed; project defaults govern new choices; presets are starting points; recommendations are not selections; bindings require job eligibility. Source labels are attribution, not trust. Replacement acceptance edits a draft; Apply persists; existing lane gates authorise execution. These distinctions match the project vocabulary and approved mockup.

The [implementation slices](slices.md) are approved. Current build progress, independent verification and publication gates are recorded in [execution status](execution.md).

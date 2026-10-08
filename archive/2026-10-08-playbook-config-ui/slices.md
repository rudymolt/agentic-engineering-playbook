# Configuration UI — proposed implementation slices

> Archived feature record: S8 accepted on 2026-10-08; shipped in PR #20 as
> `0a3770e7306ec80fdf6b07aab88008cf2897aa77`. Earlier pending gates and failures
> below are dated history, not current instructions. See [closeout](closeout.md)
> for final candidate evidence, durable source pointers and remaining closeout.

Status: approved eight-slice breakdown. Build-all S1–S7 is subsequently approved; see [execution status](execution.md) for current progress. S8 live host qualification is a human stop gate, not an automated completion claim.

Contract: [specification](spec.md). Interaction reference: [chat flow](chat-flow.md). Source locators: [engineering notes](engineering-notes.md).

AFK means an agent can implement the slice without further product decisions once the breakdown and build scope are approved. HITL means human input is expected. These labels do not grant build, launch, publication or merge authority. Each slice includes its own behavioural tests and independent review; the last slice does not postpone testing of earlier work.

## Approved order

| ID | Outcome | Blocked by | Mode |
| --- | --- | --- | --- |
| S1 | Change a Build default safely in an existing project | None | AFK |
| S2 | Set up and edit all model roles through chat | S1 | AFK |
| S3 | Choose supported skills by job, with source labels | S1 | AFK |
| S4 | Use an eligible custom skill across machines | S3 | AFK |
| S5 | Reuse personal defaults and named presets | S2, S3 | AFK |
| S6 | Get model recommendations with reasons and honest costs | S5 | AFK |
| S7 | Refresh model advice and recover from unavailable models | S6 | AFK |
| S7a | Confirm reviewed provider guidance | S7 | AFK |
| S8 | Complete the workflow in Codex and Conductor | S4, S7a | HITL |

S3 can proceed after S1 without waiting for model-setup work. S4 is independent of the personal-default and recommendation work once S3 is complete. These are dependency facts, not an instruction to launch parallel builders; configuration changes share one boundary and should be integrated deliberately.

Each slice crosses the conversation, configuration behaviour and verification needed for its outcome. An intermediate slice may expose only its completed capability; it must not advertise the full configure experience before the remaining slices exist.

## S1 — Change a Build default safely in an existing project

**What it delivers:** a user opens configuration, sees the current Build choice and origin, selects an available alternative, reviews the change, and saves it without changing an active feature.

**Blocked by:** None.
**Mode:** AFK.
**Acceptance coverage:** AC02, AC11, AC16, AC17, AC20, AC21, AC22, AC23.

- [ ] Provide a narrow typed chat route through read → edit Build → preview → Apply or Not now. It uses the shared configuration boundary, not a second model launcher.
- [ ] Import all existing role preferences into the versioned project configuration so editing Build cannot reset another role. Show the migration and exact destination in the proposal. Leave unrelated legacy state untouched.
- [ ] Adopt one authoritative default source and update every existing reader needed to honour it. Preserve explicit feature choices, feature-scoped `openai defaults`, launch identity checks and existing gate semantics. Complete the consumer inventory before modifying consumers; do not ship a settings file ignored by routing.
- [ ] Only expose verified available alternatives. Until S7 adds the replacement conversation, an unavailable choice blocks Apply with an explanation and an edit route; no silent substitution.
- [ ] Bind proposals to their inputs, revalidate before Apply, reject conflicting changes, and report an unchanged request without a needless write.
- [ ] Validate schemas and values, preserve supported legacy customisations, reject unsupported newer schemas and malformed adopted configuration, and make successful adoption repeatable without additional changes.
- [ ] Stage and validate the save. Failure must restore the previous valid settings or explicitly enter recovery-required state without overwriting concurrent changes.
- [ ] Not now saves nothing; Apply does not launch a model. Pending/active selections, mission approvals and execution history remain byte-for-byte unchanged.

**Verification target:** temporary-project integration tests demonstrate an existing customised Build preference being migrated, edited and read by the next ordinary lane gate. Test cancellation, repeat adoption, invalid input, changed files, unavailable routes, failed writes and exact runtime-state preservation. Demo the typed conversation against fixture discovery.

**Boundary:** no personal presets, cost recommendation engine, full onboarding or custom skill binding yet. This is the first complete user path, not a schema-only foundation ticket.

## S2 — Set up and edit all model roles through chat

**What it delivers:** a new or returning user can review and edit Plan, Build, Verify and escalated repair choices using the approved guided or expert flow.

**Blocked by:** S1.
**Mode:** AFK.
**Acceptance coverage:** AC01, AC02, AC03, AC04, AC05, AC09, AC17, AC23.

- [ ] Extend the complete edit/preview/apply path to all four roles, including supported runner and reasoning choices. Changing a role preserves unrelated draft values.
- [ ] Display QA as inheriting Verify and the Coordinator as observed current-chat identity. Do not expose controls that switch either independently.
- [ ] Preserve escalation triggers, repair authority, ceilings and verification independence. A choice cannot weaken these existing contracts.
- [ ] Ask only for missing context and presentation preferences. Persist guided/expert preference locally with an explicit destination preview; returning users do not repeat onboarding.
- [ ] Show effective origins and a complete role proposal. Explain identifies the selected route and limitations without invoking it; deeper provider/cost evidence arrives in S6.
- [ ] Provide typed choices for every editor level, including picking role, model, runner and reasoning. Optional native controls must have an immediate text fallback.
- [ ] New project setup cooperates with the existing bootstrap gate; it does not perform a second bootstrap or apply unspecified settings.

**Verification target:** table-driven conversation tests complete each role edit through typed replies, check QA inheritance and Coordinator display, and compare guided/expert results for identical saved settings. Prove returning users skip known questions and Apply never dispatches work.

**Boundary:** until S6, use verified edition/project starting choices with clearly labelled missing recommendation evidence. Do not invent model rankings or pricing to make setup look complete.

## S3 — Choose supported skills by job, with source labels

**What it delivers:** a user selects an eligible supported skill or explicit fallback for a Playbook job, sees where it comes from, and the relevant stage honours that choice.

**Blocked by:** S1.
**Mode:** AFK.
**Acceptance coverage:** AC03, AC12, AC13, AC16, AC17, AC22.

- [ ] Define the five job contracts from existing stage requirements: alignment, specification, implementation, code review and application QA. Include inputs, outputs, invocation owner, permitted effects and eligible composition/fallback forms.
- [ ] Discover supported candidates using registry provenance and applicable compatibility evidence. Do not treat a capability category or installation as proof of job eligibility.
- [ ] Present source-prefixed names consistently in the proposal, editor and before/after changes. Distinguish Playbook adapters, project routes and upstream-derived adaptations from unmodified upstream skills.
- [ ] Save logical identities and ordered bindings when the contract permits composition. Detect ambiguous display names using the source identity.
- [ ] Integrate selected bindings into the corresponding stage-owned invocation without allowing the skill to own unrelated configuration, commits or launches.
- [ ] Reuse exact-source report-only checks for embedded reviewers. Changed, untested or incompatible source retains the approved adapter/manual route or blocks the binding; it cannot be approved merely by acknowledging a warning.
- [ ] A QA route points to an existing eligible project verification route. Selecting it does not create a harness or enable maintenance automatically.

**Verification target:** fixture candidates cover eligible and incompatible upstream sources, source/name collisions, composed alignment bindings, adapters and manual routes. Save a binding and demonstrate the stage selecting that route while retaining its original obligations. Modify a selected source fingerprint and prove the prior eligibility is invalidated.

**Boundary:** no package installation, source modification or broad upstream upgrades. Registry maintenance needed for a contract is scoped to this feature and preserves notices.

## S4 — Use an eligible custom skill across machines

**What it delivers:** a user assigns a custom local skill to a job and can share the project configuration without embedding their machine's path.

**Blocked by:** S3.
**Mode:** AFK.
**Acceptance coverage:** AC12, AC14, AC16, AC22.

- [ ] Resolve a project-relative custom skill or a portable logical identity with a separate local binding. Never store absolute machine paths or credentials in shareable project configuration.
- [ ] Show verified source attribution where known and `(Custom)` when no more specific verified source is available.
- [ ] Require evidence against the same job contract as a supported collection. The skill's own declaration is not certification.
- [ ] Missing evidence shows the unmet requirement and an approved fallback. Collecting additional proof remains a separately scoped task; configuration never executes a candidate experimentally.
- [ ] Another machine with a missing local binding sees an unresolved choice and explicit recovery, not an automatic replacement or path rewrite.
- [ ] A changed custom source invalidates prior eligibility; repeated configuration preserves intentional custom bindings.

**Verification target:** two isolated machine fixtures use the same shareable project file with different local bindings. Demonstrate successful eligible selection, unresolved binding, rejected evidence, changed source and no private path leakage.

## S5 — Reuse personal defaults and named presets

**What it delivers:** a user saves useful defaults once, seeds a new project, and explicitly previews applying a preset to an existing project.

**Blocked by:** S2, S3.
**Mode:** AFK.
**Acceptance coverage:** AC01, AC02, AC04, AC08, AC15, AC16, AC20, AC21.

- [ ] Add local reusable defaults and named presets, with the same validation as project configuration. Preserve source identities for any skill bindings supplied by S3; do not invent a second binding representation.
- [ ] Save local billing preferences for relevant routes, supporting subscription, API, mixed and unknown cases. Guided/expert preference remains local.
- [ ] Offer one Recommended entry plus user-saved presets. S6 supplies evidence-backed model advice for Recommended; it is not a static “cheap/balanced/premium” bundle list.
- [ ] Loading a preset modifies a draft and shows origins, changes and destinations. Saving a preset does not change any other project or active feature.
- [ ] Seed new projects through the existing bootstrap preview. Existing projects retain their current settings until explicit Apply, even when personal defaults have changed.
- [ ] Extend the recovery protocol to an operation spanning project and personal destinations. Prevent incomplete transactions being treated as valid and report recovery accurately.
- [ ] Unknown preset fields or unresolved local dependencies produce an actionable review requirement rather than silent omission.

**Verification target:** two-project fixtures prove seeding and deliberate reapplication, isolation of the other project and active selections, and absence of private billing information in shared settings. Inject failure after the first destination write and a concurrent edit during rollback; prove truthful recovery and no overwrite of that edit.

**Dependency note:** S2 supplies the full model-role conversation and S3 supplies eligible skill bindings. Both are needed to demonstrate a complete model-plus-skill preset without inventing a second representation or applying unknown bindings. S4 adds custom-skill portability independently; their combined behaviour is qualified in S8.

## S6 — Get model recommendations with reasons and honest costs

**What it delivers:** setup and existing lane checkpoints recommend suitable available models for the user's work and explain the evidence and cost trade-offs.

**Blocked by:** S5.
**Mode:** AFK.
**Acceptance coverage:** AC01, AC06, AC07, AC08, AC09, AC17, AC23.

- [ ] Filter candidates by verified availability, job suitability and existing authority/verification constraints before comparing them.
- [ ] Present one reasoned recommendation per role with model, runner, reasoning, project/task fit and limitations; preserve feature-specific selection gates and explicit overrides.
- [ ] Keep provider suitability guidance, published pricing and comparable project results distinct. Attach claim-specific official sources and successful check dates rather than a generic link used to support every claim.
- [ ] Support API rates with units and currency, labelled workload estimates, subscription consumption/limits when observable, and explicit unknowns. No paid benchmark, guaranteed saving or unsupported cheapest-model claim.
- [ ] Task-specific advice changes only the selected feature through its existing gate, not project or personal defaults. Recommendations and Explain never dispatch candidates.
- [ ] Retrieve current evidence during this initial implementation. Cache reuse and change-triggered refresh policy arrive in S7; stale evidence must already be labelled honestly on retrieval failure.

**Verification target:** controlled discovery/provider/clock fixtures exercise different tasks, billing modes, missing rates, unavailable routes and absent project history. Check every displayed cost claim against its evidence. Confirm the proposal and explanation create no provider invocation or new execution approval. Validate the retrieval adapter with read-only official-source samples without treating sample prices as current live facts.

## S7 — Refresh model advice and recover from unavailable models

**What it delivers:** advice stays current without checking on every turn, and an unavailable model leads to a helpful replacement proposal rather than a dead end.

**Blocked by:** S6.
**Mode:** AFK.
**Acceptance coverage:** AC10, AC11, AC17, AC18, AC19, AC22.

- [ ] Reuse successful guidance/pricing evidence for up to 24 hours only at configuration or existing lane-discovery checkpoints. First use, explicit refresh and new model/version discovery check immediately. No background or unrelated-turn checks.
- [ ] Record source revision/fingerprint and last successful check, coalescing duplicate source fetches within one discovery pass. Persist bounded evidence and discovery fingerprints, not a full catalogue treated as launch authority.
- [ ] Reassess affected existing models when guidance, capabilities or prices change; report what changed. Do not invent changes when a source remains the same.
- [ ] On refresh failure, preserve the previous successful date and label incomplete/stale evidence. Do not manufacture advice for a newly discovered model.
- [ ] For an unavailable saved choice, recommend one verified suitable replacement with a reason and honest cost limits. Offer Accept replacement, Choose another model or Not now.
- [ ] Accept replacement updates only the draft; choosing another opens the affected role editor. Neither saves nor launches. With no eligible alternative, show the limitation and recovery action.
- [ ] Use this recovery at discovery and when availability changes before Apply. Refresh the preview and require explicit Apply again; preserve active runs and approved feature choices.

**Verification target:** a fake clock checks evidence just inside and outside 24 hours. Source fixtures cover unchanged docs, new model with changed/unchanged docs, changes affecting an old model and unavailable pricing. Conversation tests cover all replacement choices, absence of alternatives and a candidate disappearing before Apply. Assert no automatic switch or per-turn/network watcher behaviour.

## S7a — Confirm reviewed provider guidance

**What it delivers:** task-fit advice and replacement suggestions rest on maintainer-reviewed provider statements that the live official page still confirms, instead of inferred page prose.

**Blocked by:** S7.
**Mode:** AFK.
**Acceptance coverage:** AC06, AC10, AC18.

- [ ] Ship a validated reviewed-guidance data file in the edition with the initial GPT-6 Astra coding entry; malformed entries fail closed.
- [ ] Confirm each entry against its retrieved official page: the section heading is immediately followed by a leaf block whose rendered text equals the reviewed paragraph and contains the model link, ignoring whitespace, invisible characters and inline formatting. Neither may be inside or contain `del`, `s`, `strike`, `blockquote` or `q`; inert template descendants never confirm. Otherwise withdraw it with "provider wording changed since review".
- [ ] Remove task-fit inference from provider prose; keep pricing-table parsing and existing freshness, cache and change-notice behaviour.
- [ ] Show "no reviewed guidance yet" for discovered models without an entry; no replacement is offered from pricing or availability alone.
- [ ] Provide a release check that reports entries a supplied or fetched official page no longer confirms.
- [ ] Cycle 9 amendment: viewing advice retains the existing 24-hour cache, but Accept replacement retrieves the original reviewed entry's official source once before editing the draft, including retained and recovered proposals. Require a newly confirmed current entry and complete existing route gates; saved confirmation and stale fallback cannot authorize acceptance. Refuse unavailability, withdrawal or a changed reviewed entry with an explanation and unchanged draft, project and approval bytes, without reranking or choosing another model. This acceptance boundary is independent of cache publication success: only an actual fresh confirmation makes a cache write failure nonfatal. Cached display retains its existing freshness rules; no new durability or invalidation subsystem.
- [ ] Cycle 10 clarification: literal raw-text/RCDATA bodies, conditional `noscript` content and `plaintext` supply no confirming elements. Respect nonvoid HTML self-closing flags, script escaped/double-escaped transitions and `plaintext` through EOF. Test ordinary/self-closing, nested/malformed and close-like copies at all four public seams, retained visible proposals refusing fresh hidden pages without mutation, genuine visible entries after closes and usable pricing positives on both supported interpreters.
- [ ] Cycle 11 clarification: exclude `hidden` elements and descendants for every attribute case/value, including `until-found`, from rendered text, links and adjacency. Respect closed `dialog` and closed `details` visibility (the first direct `summary` remains visible); `datalist` content, metadata, image-map areas and hidden inputs supply no rendered blocks. Cover ancestors, matched blocks, inline text/links, duplicates, nesting, malformed closes and nonvoid self-closing syntax at all four seams, with visible guidance/pricing positives and fresh refusal preserving retained drafts and project/approval bytes. No CSS/JavaScript renderer, dependency or whole-page semantics is added.

- [ ] Cycle 12 clarification: preserve implied paragraph, heading, list-item and table-cell boundaries before excluding hidden starts, including empty barriers from stray paragraph closes; withdraw ambiguous table content outside cells or captions. Withdraw interrupted source paragraphs instead of admitting a shorter repaired leaf block. Cover visible/hidden blocks, nonvoid self-closing flags, nested/misnested contexts and raw-text interactions with valid successor and hidden inline controls. Prove fresh refusal at all four seams on supported interpreters, with positive baselines, pinned source/Configuration clocks, one original-source fetch and unchanged draft/project/approval bytes. No browser-tree reconstruction or contract expansion.

- [ ] Cycle 13 clarification: withhold native control/fallback and foreign SVG/MathML subtrees, including HTML integration points, when their apparent markup cannot establish rendered confirming blocks. Retain ambiguous boundaries for ignored document/table tokens and nested forms; protect native nesting, malformed closes, self-closing flags, raw/inert bodies and foreign breakouts. Prove refusal at all four seams on both interpreters with pinned clocks, usable positive baselines, one fresh original-source fetch and unchanged draft/project/approval/original-proposal bytes. Preserve ordinary forms, correctly closed visible successors, hidden inline additions, pricing and cycle 12 boundaries. No browser/CSS/JavaScript renderer, dependency or contract expansion.

- [ ] Cycle 14 clarification: keep native/foreign ambiguity barriers regardless of literal `hidden` attributes on scopes or apparent ancestors. Cover nested selects/buttons, implicitly closed controls, ignored starts and foreign breakouts in reviewed headings, paragraphs, model links and pricing context. Prove refusal at all four seams on both interpreters with pinned clocks, usable positive baselines, one fresh original-source fetch and unchanged draft/project/approval/original-proposal bytes. Preserve ordinary hidden inline additions, correctly closed visible successors, raw-text/inert exclusions and cycle 12 boundaries; no browser simulation, dependency or change to the reviewed-list/cache/fresh acceptance contract.

- [ ] Cycle 15 clarification: retain ambiguity barriers for every ignored or misplaced scope family under apparent hidden or closed ancestors, including table structural tokens, nested forms and repeated document tokens. Cover nested/misnested and self-closing tokens in matched headings, paragraphs, required links and pricing qualifiers. Prove refusal at all four seams on both interpreters with pinned clocks, usable positive baselines, one fresh original-source fetch and unchanged draft/project/approval/original-proposal bytes. Preserve hidden inline additions, ordinary forms, correctly closed successors, native/foreign barriers, raw-text/inert exclusions and cycle 12 boundaries; no new contract or change to cycle 9 acceptance/cache semantics.

- [ ] Cycle 16 clarification: retain bounded ambiguity for active-formatting reconstruction and adoption/misnesting across explicit and implied structural ends, including anchors, inherited hidden/closed contexts and nonvoid self-closing flags. Test formatting families, paragraph/list/cell boundaries, nested anchors and `nobr`, raw/inert/native/foreign exclusions, genuine own closes and cell/caption or `marquee` markers, and pricing qualifiers. Prove refusal at all four seams on both interpreters with pinned source/Configuration clocks, usable positive baselines, one fresh original-source fetch and unchanged draft/project/approval/original-proposal bytes. Preserve genuine closed hidden-inline additions and ordinary visible blocks/forms/prices; no renderer, dependency or change to cycle 9 acceptance/cache semantics. An own close across open blocks can clone the formatting entry; repeated own closes alone cannot prove release, so retain that adoption barrier until a genuine formatting marker clears the affected context.

- [ ] Cycle 17 clarification: respect native end-tag scope across tables, cells/captions and other boundaries, including generic closes across structural boundaries and ambiguous partial ancestor closes. Preserve genuinely closed hidden ancestors and visible successors after explicit/implied table ends, including formatting-marker release. Test hidden negatives and visible guidance/pricing positives at all four seams on both interpreters, with pinned source/Configuration clocks, a usable baseline, one fresh original-source fetch and unchanged draft/project/approval/original-proposal bytes without reranking or launch. No new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

- [ ] Cycle 18 clarification: preserve inline ruby and its phrasing descendants in headings, paragraphs and required links. Test hidden annotations/ancestors, visible annotation qualifiers, native scope and implied annotation ends (including enclosing `rtc`), excluded descendants and genuine nested-block/ambiguity negatives. Prove all four seams on both interpreters with usable second-link baselines, pinned source/Configuration clocks, one fresh original-source fetch, draft-only success and byte-preserving refusal without reranking or launch. No new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

- [ ] Cycle 19 clarification: normalize native `image` to void `img` before visibility filtering; recognize void `basefont`/`bgsound` metadata, the void legacy control `keygen` and ignored `frame` starts outside a frameset. Test visible text successors in headings, paragraphs, required links and pricing, ordinary/self-closing flags, hidden ancestors and actual containers, foreign image/integration scopes and raw/inert boundaries with genuine closed successors. Prove all four seams on both interpreters with usable nonfirst-link baselines, pinned source/Configuration clocks, one fresh original-source fetch, draft-only success and byte-preserving refusal without reranking or launch. No new contract, renderer, dependency or change to cycle 9 acceptance/cache semantics.

- [ ] Cycle 21 clarification: preserve visible text after the first `>` of native CDATA-shaped/marked bogus declarations. Discriminate case-sensitive CDATA, marked/bogus declarations, processing instructions and genuine/abrupt/nested comment boundaries in headings, paragraphs, required links and pricing. Test harmless closed declarations/comments and genuine visible text separately from hidden/excluded, changed, nested and adjacency negatives; preserve raw/inert and foreign withholding. Prove all four seams on both interpreters with pinned source/Configuration clocks, usable nonfirst-link baselines, one original-source fetch, only the affected draft role changing on success and independent proposal/project/approval byte assertions on refusal without reranking, Apply or launch. No new contract, renderer, dependency or change to cycle 9 cache/fresh acceptance semantics.

- [ ] Cycle 22 clarification: separate native declaration boundaries from actual SVG/MathML CDATA contexts within withheld/inert scopes. Prove genuine native template closes and visible successors, and refusal of close-like copies in true foreign CDATA, including nesting, malformed/ignored tokens, integration descendants, foreign breakouts, native raw bodies, self-closing foreign elements, foreign own closes, duplicate integration encodings and hidden contexts. Preserve cycle 21 qualifier refusal and abrupt-comment precedence, pricing discrimination and deep iterative traversal. Test all four seams on both interpreters with pinned source/Configuration clocks, usable nonfirst-link baselines, one original-source fetch, only the affected draft role changing on success and independent proposal/project/approval bytes preserved on refusal without reranking, Apply or launch. No new contract, renderer, dependency or change to cycle 9 cache/fresh acceptance semantics.

- [ ] Cycle 23 clarification: keep declaration namespace native across ignored select ends, including premature foreign integration ancestor ends. Cover permitted and misplaced option/optgroup ends, unmatched ends, genuine select/template closes, integration descendants, raw/inert and hidden scopes, real foreign CDATA and pricing. Prove genuine visible successors and excluded copies at all four seams on both interpreters with pinned source/Configuration clocks, usable nonfirst-link baselines, one original-source fetch, draft-only success and independent proposal/project/approval byte preservation on refusal. Preserve ambiguity barriers and cycle 9 acceptance/cache rules; no new contract, renderer or dependency.

- [ ] Cycle 24 clarification: preserve native `br` start/end-token separator parity in headings, paragraphs and required links, including between-word whitespace positives and hidden/self-closing, raw/inert, excluded, foreign and select contexts. Exercise pricing and all four seams on both interpreters with pinned source/Configuration clocks, usable nonfirst-link baselines, one fresh original-source fetch, draft-only success and unchanged draft/project/approval/original-proposal bytes on refusal without reranking. Preserve the reviewed list and cycle 9 cache/acceptance rules; no new contract, renderer or dependency.

- [ ] Cycle 25 clarification: process native EOF text and character references before guidance and pricing extraction, retaining bare `<`/`</` as text without flushing discarded incomplete tags, comments or declarations. Preserve valid unclosed visible elements, unknown incomplete pricing tables, interrupted-paragraph barriers and raw/RCDATA, hidden, inert, foreign and select exclusions. Test all four seams on both interpreters with usable nonfirst-link baselines, pinned source/Configuration clocks, one fresh original-source fetch, draft-only success and unchanged draft/project/approval/original-proposal bytes on refusal. No new contract, renderer, dependency or change to cycle 9 cache/acceptance semantics.

**Verification target:** provider-page fixtures cover confirmation, every withdrawal condition, inert templates and unlisted models through OfficialSources, Configuration, the public CLI and release checking, with draft-only acceptance and byte preservation. Separate CLI processes prove that a confirmed proposal, a successful withdrawal whose cache publication fails, and retained acceptance cannot replay older confirmation. Cover unreachable sources despite a fresh confirmed cache, fresh confirming success, changed reviewed entries, one original-source fetch per acceptance boundary and consistent source/configuration fixture clocks with a usable positive baseline. Retained official page bytes confirm the initial entry.

## S8 — Complete the workflow in Codex and Conductor

**What it delivers:** a user can install/adopt the complete feature and finish the approved configuration experience in either supported host, with readable guidance and honest support claims.

**Dependencies:** S4 and S7a accepted (including S1–S7).
**Status:** accepted 2026-10-08 at `05de2a0`; shipped in PR #20 as `0a3770e`. Final gates and historical limits are recorded in [closeout](closeout.md).
**Mode:** HITL — final live-host walkthrough and any account-specific access require the maintainer; implementation and automated checks remain agent work.
**Acceptance coverage:** AC01–AC23, with emphasis on integration and actual host behaviour.

- [x] Run the complete typed-only first-run, edit, source-labelled skill/preset, Explain, unavailable-model and failed-Apply scenarios in Codex and Codex through Conductor. Verify optional host controls fall back to text.
- [x] Confirm the actual observed Coordinator identity and available routes. Show adopted defaults at the existing lane gate without launching a paid comparison or claiming model output as identity proof.
- [x] Exercise new bootstrap and an existing customised-project upgrade, including all role-default consumers, skill-job dispatch, personal presets and recovery. Complete the consumer inventory and resolve any remaining legacy readers.
- [x] Demonstrate a model-plus-skill preset across two projects/machines, preserving privacy and active selections. No unsupported host is described as verified.
- [x] Update human and agent guidance together, including first use, migration, skill attribution, freshness/replacements and troubleshooting. Preserve third-party notices and include the required process-change Why entry.
- [x] Regenerate release manifests and pass the canonical Playbook verifier and relevant changed-surface tests. Obtain independent final verification. Record any unavailable live proof explicitly instead of claiming completion.
- [x] Any billable execution beyond normal configuration discovery requires a separately scoped qualification decision. No release, push, merge or deployment is authorised by this ticket alone.

**Verification target:** retain redacted transcript/check evidence from both real hosts, migration and recovery fixtures, independent review results, manifest validation and privacy checks. Mockup screenshots alone cannot satisfy host qualification.

## Coverage and review

All 23 specification criteria have an implementing slice above and a final cross-feature check in S8. No standalone “write tests” ticket is needed; each outcome ships with its own verification.

Approved granularity: seven agent-implementable slices and one human-assisted qualification slice. S1 owns safe persistence from the first useful change; S5 expands it to multiple destinations. S6 owns recommendation evidence; S7 adds refresh policy and guided recovery. S7a (owner amendment, 2026-10-05) replaces inferred provider guidance with the reviewed list. Keeping these pairs separate avoids making the first deliverable depend on every later feature.

The user approved these outcome sizes and blocking edges. If implementation evidence shows a slice cannot fit a fresh context, return to breakdown and propose a split around another independently observable behaviour rather than a code layer. S1 is first because every later slice depends on its safe configuration boundary. The subsequent build-all approval is recorded in [execution status](execution.md).

## Ticket index

The slice sections above contain the complete approved acceptance criteria and verification targets. Local ticket copies remain private working artifacts; public consumers do not need those copies to review the contract.

- [S1 — Change a Build default safely in an existing project](#s1--change-a-build-default-safely-in-an-existing-project)
- [S2 — Set up and edit all model roles through chat](#s2--set-up-and-edit-all-model-roles-through-chat)
- [S3 — Choose supported skills by job, with source labels](#s3--choose-supported-skills-by-job-with-source-labels)
- [S4 — Use an eligible custom skill across machines](#s4--use-an-eligible-custom-skill-across-machines)
- [S5 — Reuse personal defaults and named presets](#s5--reuse-personal-defaults-and-named-presets)
- [S6 — Get model recommendations with reasons and honest costs](#s6--get-model-recommendations-with-reasons-and-honest-costs)
- [S7 — Refresh model advice and recover from unavailable models](#s7--refresh-model-advice-and-recover-from-unavailable-models)
- [S7a — Confirm reviewed provider guidance](#s7a--confirm-reviewed-provider-guidance)
- [S8 — Complete the workflow in Codex and Conductor](#s8--complete-the-workflow-in-codex-and-conductor)

Current ticket progress and accepted candidate evidence are recorded in [execution status](execution.md). S1–S7a require acceptance of their blockers; S8 additionally requires human-assisted host qualification.

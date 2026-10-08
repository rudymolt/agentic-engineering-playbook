# Default and skill consumer inventory

> Archived feature record: S8 accepted on 2026-10-08; shipped in PR #20 as
> `0a3770e7306ec80fdf6b07aab88008cf2897aa77`. Earlier pending gates and failures
> below are dated history, not current instructions. See [closeout](closeout.md)
> for final candidate evidence, durable source pointers and remaining closeout.

Completed before consumer edits on 2026-09-29. Scope: new project preferences,
not selection or execution authority. The approved baseline already present in
this checkout is preserved. The five planning documents and local interaction
mockup were read; mockup values are illustrative, not host evidence.

## Default readers and writers

S3 adds `scripts/skill_bindings.py` and the shared helper's public `job-route`
entry seam. Stages 01/03/07/08/09 resolve and consume configured primary
invocations there; confirmation, tests, review/QA evidence, commits, launches
and permissions remain stage-owned. Proposal, editor and before/after changes
share verified provenance. QA reads only an already selected, independently
eligible project route and creates no harness or maintenance selection.
Embedded checks reuse the exact-installed-source compatibility checker. The
public job-contract guide lists upstream exclusions and explicit fallbacks.

| Consumer | Ownership and S1 treatment |
| --- | --- |
| `v0.5/10-process/README.md`, `v0.5/10-process/prereqs-capability-profiles.md`, `v0.5/templates/CLAUDE.md`, `v0.5/scripts/upgrade-project.py:CLAUDE_ROUTING_RULE` | Stage navigation, capability fallback and installed policy also describe ordinary defaults. Align their labels with the same effective preference; do not let template/upgrade guidance revive a competing edition-only default. |
| `v0.5/93-model-routing-track.md`, `v0.5/skills/model-router/SKILL.md`, `v0.5/skills/model-router/references/chat-prompts.md` | Ordinary Plan/Build/Verify and repair preference readers. Resolve explicit feature > adopted `.playbook-config.json` > legacy state defaults > edition. Show resolved origin, not a hardcoded OpenAI label. `openai defaults` stays a feature-only edition override. |
| `v0.5/10-process/00-prereqs.md`, `01-align.md`, `07-implementation-tdd.md`, `08-review.md`, `09-qa.md`, `11-debug.md` | Stage entry points delegate model choice to model-router; QA inherits Verify; fixes retain selected Build; escalation preserves approved triggers and ceilings. Resolve only new choices. |
| `v0.5/AGENT-DIGEST.md`, `v0.5/skills/README.md`, `v0.5/templates/AGENTS.md`, `v0.5/templates/CLAUDE.md`, `v0.5/README.md` | Navigation/installed skill consumers, not launch authorities. Configure is a user-invoked preference editor; ordinary gates use the router. |
| `v0.5/templates/.playbook-state.yml` | Edition seeds for all four roles plus allowed runners. Retain as legacy bootstrap source. All existing model/runner/reasoning and repair constraints imported; state bytes never rewritten by Configure. |
| `v0.5/scripts/bootstrap-project.py`, `v0.5/skills/ai-playbook-bootstrap-project/SKILL.md`, `v0.5/scripts/template_base.py` | Existing bootstrap owns state and managed skill installation/provenance. No root bootstrap here. Install Configure through the existing registry; no implicit adoption. |
| `v0.5/scripts/upgrade-project.py`, `v0.5/skills/ai-playbook-upgrade-project/SKILL.md` | Existing three-way managed-file merge/provenance and legacy routing migration. Configure-owned project defaults are not a managed template and remain untouched. Upgrade does not adopt or reset them. |
| `v0.5/delivery/README.md`, `v0.5/10-process/delivery-mission.md`, `v0.5/delivery/skill/SKILL.md`, delivery descriptors/entry points | Pre-approval preference lookup uses the same resolver. Explicit submitted routes and immutable approval envelopes remain authoritative; Configure cannot amend a mission. |
| `v0.5/delivery/src/delivery_pilot/interim_routes.py`, `interim_conductor_host.py`, `interim_advance.py`, `interim_repair.py`, `authority.py`, `contracts.py`, `cloud.py` | Approved route execution/validation, not project-default readers. `configured_route` reads host routes already supplied; `route_for_operation` reads approved routes. Never replace either with live preferences mid-run. Escalated Verify's edition route is an execution constraint, not editable Build preference. |
| `v0.5/scripts/convention_checks.py`, `test_bootstrap_project.py`, `test_convention_checks.py`, delivery tests | Assertions of edition policy/immutable execution, not live default consumers. Preserve baseline. Add new boundary and next-lane integration coverage. |

## Immutable selection and execution records

`pending_model_routes`, `active_features[].routing`, feature-scoped
`defaults_for_feature`, Wayfinder route links, requested/runtime identity,
capability profiles, run pace, mission approvals, escalation policy, run
ceilings, history, counters and status belong to existing gates. Preserve their
files byte-for-byte. Adoption is marked only in `.playbook-config.json`.
Legacy defaults become inert history after adoption, never a competing source.
Malformed adoption blocks resolution instead of falling back.

## Discovery and identity authorities

Model-router step 1 and `93-model-routing-track.md` own live route discovery;
step 5 owns dispatch and authoritative identity/permission acceptance.
Delivery's `discovery.py`, `interim_identity.py`, `conductor_api.py` and
`interim_conductor_host.py` retain their existing host admission and correlation
checks. Availability supplied to Configure must come from these host surfaces,
not a persisted full catalogue or model-generated self-description. Recheck at
Apply, then independently at execution. Configure never dispatches. The S1
fixture interface proves configuration behaviour, not live-host qualification.

## Skill invocation consumers

The complete registry table below records every current invocation and its
stage consumers before S1. `v0.5/upstream-skills.json` owns provenance and
installation; `upstream_registry.py` resolves names; `skills/README.md` owns
local invocation transport; `upstream-integrations.json` and
`check-upstream-compatibility.py` own exact-source embedded eligibility.
`10-process/README.md`, prerequisites/capability profiles and stage files route
to these skills. Templates/bootstrap/upgrade render registry names and install
managed local skills. `retire-upstream-skill.py` and maintenance/audit scripts
manage the registry, not job bindings. No S1 skill binding or eligibility change.

| Skill | Source | Invocation | Stage consumers (registry) |
| --- | --- | --- | --- |
| `grill-with-docs` | mattpocock-skills | user | 01, 02, 10-process/README |
| `setup-matt-pocock-skills` | mattpocock-skills | user | 00, 03, 05, 10-process/README |
| `to-spec` | mattpocock-skills | user | 03, 07, 10-process/README, templates/planning-template/README |
| `to-tickets` | mattpocock-skills | user | 04, 00-foundations, 10-process/README, templates/planning-template/README |
| `implement` | mattpocock-skills | user | 07, 10-process/README |
| `triage` | mattpocock-skills | user | 05, 10-process/README |
| `tdd` | mattpocock-skills | model | 04, 07, 08, 10-process/README, prereqs-capability-profiles |
| `diagnosing-bugs` | mattpocock-skills | model | 11, 10-process/README, prereqs-capability-profiles |
| `improve-codebase-architecture` | mattpocock-skills | user | 04, 06, 10-process/README, templates/playbook-cadences |
| `prototype` | mattpocock-skills | model | 20-frontend-track, 92-wayfinder-track, AGENT-DIGEST |
| `domain-modeling` | mattpocock-skills | model | 02, 10-process/README |
| `codebase-design` | mattpocock-skills | model | 06, 00-foundations |
| `code-review` | mattpocock-skills | model | 07, 08 |
| `research` | mattpocock-skills | model | 03, 92-wayfinder-track, 10-process/README |
| `resolving-merge-conflicts` | mattpocock-skills | model | 91-delegation-track |
| `wayfinder` | mattpocock-skills | user | 01, 12, 92-wayfinder-track, 10-process/README, AGENT-DIGEST |
| `grill-me` | mattpocock-skills | user | prereqs-capability-profiles |
| `handoff` | mattpocock-skills | user | 12, 91-delegation-track |
| `grilling` | mattpocock-skills | model | 01 |
| `writing-for-agents` | mattpocock-skills | model | 00, 00-foundations, skills/README |
| `office-hours` | gstack | model | 01, 10-process/README |
| `plan-ceo-review` | gstack | model | 01, 10-process/README |
| `plan-eng-review` | gstack | model | 01, 03, 08, 10-process/README |
| `plan-design-review` | gstack | model | 01, 08, 10-process/README |
| `plan-devex-review` | gstack | model | 01, 08 |
| `autoplan` | gstack | model | 01, 08 |
| `design-consultation` | gstack | model | 20-frontend-track |
| `design-shotgun` | gstack | model | 20-frontend-track |
| `design-html` | gstack | model | 20-frontend-track |
| `design-review` | gstack | model | 01, 20-frontend-track |
| `review` | gstack | model | 08 |
| `devex-review` | gstack | model | 08 |
| `cso` | gstack | model | 08 |
| `qa` | gstack | model | 09 |
| `qa-only` | gstack | model | 09, 10-process/README |
| `ship` | gstack | model | 10, 10-process/README |
| `land-and-deploy` | gstack | model | 10, 10-process/README |
| `canary` | gstack | model | 10, 00-foundations, 10-process/README |
| `benchmark` | gstack | model | 10, 10-process/README |
| `browse` | gstack | model | 11, 10-process/README |
| `connect-chrome` | gstack | model | 00 |
| `setup-browser-cookies` | gstack | model | 00, 09, 11 |
| `setup-deploy` | gstack | model | 00 |
| `setup-gbrain` | gstack | model | 00 |
| `retro` | gstack | model | 12, 10-process/README, templates/playbook-cadences |
| `investigate` | gstack | model | 11, 10-process/README, prereqs-capability-profiles |
| `document-release` | gstack | model | 10-process/README, prereqs-capability-profiles |
| `document-generate` | gstack | model | No stage assignment |
| `codex` | gstack | model | 06, 08, 11, 10-process/README |
| `careful` | gstack | model | 00 |
| `freeze` | gstack | model | 00 |
| `guard` | gstack | model | 00 |
| `unfreeze` | gstack | model | 00 |
| `gstack-upgrade` | gstack | model | 00 |
| `learn` | gstack | model | 12, 10-process/README, templates/retro-template |
| `whats-next` | playbook | model | 00, 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, AGENT-DIGEST, 10-process/README |
| `model-router` | playbook | model | 00, 93-model-routing-track, templates/AGENTS |
| `ai-playbook-upgrade-project` | playbook | model | 00, AGENT-DIGEST |
| `ai-playbook-bootstrap-project` | playbook | model | 00, README |
| `ai-playbook-design-review` | playbook | model | 08, 20-frontend-track, templates/playbook-cadences |
| `ai-playbook-verification-harness` | playbook | model | 00, 09, 11 |
| `ai-playbook-maintain-verification-harness` | playbook | model | 08, 09, 30-document-lifecycle |
| `ai-playbook-why` | playbook | model | 02, 06, 08, 11 |
| `ai-playbook-how` | playbook | model | 06, 08, 11 |
| `ai-playbook-blast-radius` | playbook | model | 08 |
| `ship-release` | playbook | model | 10, AGENT-DIGEST, README |

## S1 integration decision

Use a stdlib-only public configuration boundary under `v0.5/scripts/` and a
user-invoked typed chat skill. JSON is the dedicated shareable schema-1 source;
no runtime file migration/write, launcher, browser product, personal settings,
recommendation engine or S2–S7 functionality. Upstream refresh/host qualification
remain separate maintenance/S8 work. The narrow parser accepts the existing
legacy routing mapping syntax and blocks unsupported/ambiguous input with a
corrective error instead of dropping custom preferences.

## S2 changed surfaces

The same `playbook_config.Configuration` boundary now edits all four model
roles and keeps QA derived from Verify. Entry guidance in `README.md`,
`AGENT-DIGEST.md`, `skills/README.md` and `93-model-routing-track.md` now
describes the same S2 role and presentation scope instead of S1 Build-only
editing. Existing model-router and delivery
readers still resolve through that boundary; no launcher or approval authority
was added. Configure's skill metadata and JSON helper now expose typed role,
model, runner and reasoning choices, plus compact expert rendering of the same
proposal. Discovery can report the observed current-chat Coordinator solely
for display; it is never a project preference or independently switchable role.

An explicit user-local preferences directory holds presentation only, outside
the project and under the same save/completion/recovery protocol. Local-only
Apply preference does not save the project draft. Project Apply remains a
separate reviewed transaction. Goal/billing context is conversation-local in
S2; reusable defaults, presets and billing persistence remain S5. Missing
runtime state routes setup to the existing bootstrap approval gate without
creating it or applying unspecified settings. No other default consumer needs
an S2 edit: role resolution and execution gates were already integrated in S1.

## Final integration inventory — 2026-10-06

The baseline tables above retain their historical S1/S2 scope. The completed S1–S7a boundary is `Configuration.resolve`/`advise` for new model preferences and `dispatch_job` for stage-owned job descriptors. The [full acceptance mapping](acceptance-evidence.md) identifies behavioural tests; final independent completeness review remains pending.

| Current seam | Readers/writers and ownership | Verification locator |
| --- | --- | --- |
| Model preference | `configure-playbook.py resolve` calls `Configuration.resolve`; `advise` uses that same result and adds advisory evidence. `model-router/SKILL.md` and its chat prompts, `93-model-routing-track.md`, stages 00/01/07/08/09/11 and template/navigation guidance consume that resolution for new selections. | `test_playbook_config.py`: typed adoption/next lane and explicit feature precedence; `test_model_refresh.py`: lane cache/feature isolation. |
| Adopted source | `.playbook-config.json` owns adopted model/job preferences; legacy state seeds only unadopted projects. Malformed adoption blocks. Edition state templates remain fallback seeds, not a second adopted default. | `test_playbook_config.py`: invalid/duplicate/newer adoption and per-role origins. |
| Job invocation | CLI `job-route` calls `Configuration.dispatch_job` and `JobBindings.dispatch`; alignment owner 01, specification 03, implementation 07, code review 08 and application QA 09 consume descriptors in their stage entry. Configure never experimentally invokes them. | `test_skill_bindings.py`: all public stage entries, approved execution override, source drift and retained stage obligations. |
| Custom/project route | `skill_bindings.py` resolves logical identities using project-relative sources or separate local bindings/audits; owners reread exact source before invoking. QA consumes an already selected project route without creating/maintaining a harness. | `test_custom_skill_bindings.py`: two-machine resolution, all five contracts, callback revalidation and private-path/permission failures. |
| Personal settings | `LocalPreferences` owns presentation, billing, reusable defaults and named presets outside the project. Load edits a draft; explicit preference Apply and project Apply have separate scopes and paired recovery when needed. | `test_personal_presets.py`: save/load isolation, drift at publication, recovery and unchanged active state. |
| New-project seeds | Bootstrap skill/script owns explicit preview/approval and current model/job admission at seed publication. Template-base helpers preserve managed-file provenance. | `test_personal_presets.py`, `test_bootstrap_seed_routes.py`: defaults/preset seeds, source drift and prewrite rejection. |
| Existing-project updates | Upgrade skill/script owns managed three-way merge and source-pointer migration; adopted defaults/history remain outside managed templates. No implicit adoption or preset reset. | Historical approved-base/normal-upgrade receipts in the execution ledger; bootstrap/upgrade public tests and final current-host cold check. |
| Delivery | `10-process/delivery-mission.md` resolves unselected preferences before envelope creation. Explicit envelope routes, host routes, repair triggers/ceilings, identity contracts and immutable approvals remain execution inputs. Delivery runtime does not reread defaults to reroute an approved operation. | Delivery authority/contracts/interim route tests plus canonical delivery checks. |
| Evidence | `model_recommendations.py` and `model_evidence_cache.py` supply reviewed task fit, pricing and dated advisory refresh to read/Explain/advise/replacement; no launch authority. Reviewed list changes only by edition review. | Recommendation/refresh/replacement/reviewed-guidance public suites; cycle 27 independent probes remain historical. |
| Registry/install/navigation | `upstream-skills.json`, registry helpers, bootstrap/upgrade managed skills, skills README, templates and digest expose Configure alongside existing skills. `ai-playbook-configure` is user-invoked, owns preferences only and is not an automatic stage replacement. Registry audits/maintenance do not certify a job binding. | Metadata/bootstrap/convention checks and source eligibility tests. |

The pre-existing skill invocation table remains the complete baseline registry inventory; add `/ai-playbook-configure` (Playbook, user invocation) for preference editing and stage-00/bootstrap/lane-navigation references. Existing commands not selected as one of the five bindings retain their owning stages, compatibility/permission gates and invocation transport. Active approvals, pending routes, feature overrides, capabilities, run pace and history remain outside all preference writes. The final reviewer must confirm these boundaries against the final diff and flag any competing reader before a ready claim.

Cloud final verification selects the stage-08 manual fallback explicitly. Historical copied custom-source/store receipts establish prior admission only; no new invocation, pin, audit or qualification occurs here. The fresh native Mac ordinary adopted-lane report-only invocation and real Conductor handoff were independently admitted and accepted on 2026-10-07; final S8 gates passed on `05de2a0` on 2026-10-08.

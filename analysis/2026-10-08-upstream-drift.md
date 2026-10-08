# Monthly upstream comparison — 2026-10-08

Owner: repository maintainer. Procedure: [V0.5 maintenance](../v0.5/MAINTENANCE.md).
Comparison completed on 2026-10-08; next comparison due **2026-11-08**, or before
a release changing an upstream contract. This is a maintenance batch: retain
existing pins and manual/adapter routes, and propose adoption work for human
selection. No installation, optional command adoption, model-guidance update,
host qualification, or feature retro is performed here.

## Source authority and dates

| Package | Retained contract | Inspected candidate | Authority and result |
|---|---|---|---|
| Matt Pocock skills | `v1.2.3`, `6acc160e4e0cd062dbbbd7a1b26ae92855edf07e` | `v1.3.1`, `24fe0ef7737efae15c87225755e9f6f5965e4888` | [Release page](https://github.com/mattpocock/skills/releases/tag/v1.3.1), published 2026-10-04 12:48:18 UTC; exact tag fetched and compared. `v1.3.0` was published at 12:47:22 UTC that day. |
| gstack | `1.62.0.0`, `d078622b73539fc1a7a27e709861e9b6b058ae98` | `VERSION` `1.91.54.0`, `9a1dc81a2b96e7b74a15e5911175bc04de7659e9` | [Releases](https://github.com/garrytan/gstack/releases) and [tags](https://github.com/garrytan/gstack/tags) returned no entries. Fallback: [immutable versioned source](https://github.com/garrytan/gstack/tree/9a1dc81a2b96e7b74a15e5911175bc04de7659e9), an unreleased early-warning snapshot, not a tagged release. |
| pstack | `93b00b89ef425a9c1bac0d0b317dfc49c930ac99` | latest `pstack` path commit `df581122cde17e6e27686b5a448bde23e4ad4318`, plugin version `0.15.15` | [Releases](https://github.com/cursor/plugins/releases) and [tags](https://github.com/cursor/plugins/tags) returned no entries. Fallback: [immutable source](https://github.com/cursor/plugins/tree/df581122cde17e6e27686b5a448bde23e4ad4318/pstack), dated 2026-10-06 01:05:41 UTC. Source-only dependency; no upstream plugin installation or qualification claimed. |

Release pages, APIs, refs and VERSION/plugin metadata were checked again on
2026-10-08 when the comparison was finalized. Absence of release/tag entries
does not establish absence of changes. The gstack and pstack fallback trees
record what was inspectable at the comparison cutoff; they do not grant a new
released contract. Neither package has a newer tagged artifact to qualify.

The [portable source ledger](2026-10-08-upstream-sources.json) records full
commit identities, every registered upstream command (including removals), five
pstack-derived routes, exact SKILL.md SHA-256 digests, skill-directory dependency
digests, all 22 compatibility-check decisions, and eight supplied host digest
observations. Missing files have null digests. These are source observations,
not execution approval. Registry `pin.verified`, integration `last_verified`,
and original stage-00 host claims remain **2026-09-08**; their historical
installed-source qualification was not rerun. Only the separate monthly
released-source comparison clock advances.

## Installed-host evidence, kept separate

The maintainer supplied a read-only Mac audit dated 2026-10-08 before cloud
handoff. Its complete JSON is retained privately in cloud artifacts. This
public summary removes host filesystem locators and lock records. It describes
that Mac, not cloud installations, and is not a newly executed Mac audit.

- Matt was installed through the skills CLI, with newest lock update
  2026-09-29. The CLI did not record an installed revision. Exact source hashing
  identifies `code-review` bytes as matching `v1.3.1`, while `implement` still
  matches the retained source. That does not identify the whole installation.
- gstack reported `VERSION` `1.91.8.0` at
  `943105f1099c058b34c4bffb9ed78730b856bbef`. Fetching that immutable upstream
  revision reproduced all six gstack reviewer digests from the supplied audit.
  It differs from both the retained pin and the latest inspected snapshot.
- pstack was not installed by design. Playbook-owned skills are local routes.
- All current registered Matt and gstack commands were reported installed.
  Removed `caveman` and `zoom-out` were still installed. Stale names were
  `diagnose → diagnosing-bugs`, `to-issues → to-tickets`,
  `to-prd → to-spec`, `write-a-skill → writing-for-agents`, and
  `writing-great-skills → writing-for-agents`. The registry also records
  historical `to-plan → to-tickets` and `decision-mapping → wayfinder`;
  the supplied audit did not report stale installed copies of those two.
- Mac-only unregistered commands: Matt `ask-matt`, `teach`; gstack
  `benchmark-models`, `context-restore`, `context-save`, `deslop-shared-libs`,
  `diagram`, `health`, `ios-clean`, `ios-design-review`, `ios-fix`, `ios-qa`,
  `ios-sync`, `landing-report`, `make-pdf`, `open-gstack-browser`, `pair-agent`,
  `plan-tune`, `scrape`, `skillify`, `spec`, `sync-gbrain`. These remain
  adoption candidates, never implied capabilities or prerequisites.

A separate read-only cloud audit was executed on 2026-10-08. No registered
Matt or gstack installation was resolved on this cloud host. Downloaded source
archives in private evidence are comparison material, not installed skills.
Embedded checks therefore ran against those exact fetched sources; no host
execution or installation claim is inferred from their presence.

## Command behavior against the stage map

In the tables, **current** means the command remains in the inspected tree;
it does not mean embedded-compatible. **Optional** means retain the existing
stage-owned capability decision. All changed or unqualified sources use the
owning playbook stage/manual route. `U` and `M` record the registry's user or
model invocation ownership; an upstream frontmatter rename is called out.
Dependency and output descriptions refer to the candidate tree. Historical
names are upgrade compatibility only, not new-work recommendations.

### Matt `v1.2.3` → released `v1.3.1`

All registered active skill invocation frontmatter remains consistent with
the registry; explicit Skill-tool calls replace some slash-name prose.
User-invoked setup is now requested from the human rather than silently
invoked by another skill. Several domain consumers now require `GLOSSARY.md`
instead of `CONTEXT.md`. That is a migration risk to existing playbook users;
do not rename their customized files automatically.

| Command | Owner / stages | Inputs → outputs; dependencies and verdict |
|---|---|---|
| `grill-with-docs` | U / 01, 02 | Plan discussion → interview plus domain docs; calls `grilling` and `domain-modeling` explicitly. Current, domain-file migration affects output; manual alignment/context route. |
| `setup-matt-pocock-skills` | U / 00, 03, 05 | Repo/tracker choices → agent rules and `docs/agents` files; `gh`/`glab` or local tracker templates. Current; now scaffolds glossary conventions. Keep setup human-owned. |
| `to-spec` | U / 03, 07 | Conversation/repo/ADRs → tracker spec; human confirms test seams, tracker config required. Current; missing setup asks the human. Manual spec route remains. |
| `to-tickets` | U / 04 | Spec/conversation → approved vertical tickets with blocking edges; tracker config/native links or local files. Current; missing setup asks the human; stage 04 owns breakdown approval. |
| `implement` | U / 07 | Spec/tickets → tested code, inline review, commit; `tdd` and `code-review`. Exact SKILL.md unchanged, still incompatible with stage-owned review and commit ownership. |
| `triage` | U / 05 | Issues and opt-in external PRs → state labels and durable briefs; tracker/config, glossary and ADRs. Current; scope now includes configured external PR handling. Keep stage-05 decisions and publication ownership. |
| `tdd` | M / 04, 07, 08 | Agreed seams → red/green public-interface tests; glossary, ADRs, `codebase-design`, testing/mocking references. Current; explicit tool calls and glossary input changed, review still owns refactoring. |
| `diagnosing-bugs` | M / 11 | Symptom → red-capable loop, diagnosis, fix and regression evidence; glossary/ADRs and optional HITL template. Current; setup/invocation and glossary changes need adaptation; stage 11 remains authoritative. |
| `improve-codebase-architecture` | U / 04, 06 | Scoped churn/source → deepening proposals; glossary/ADRs, `codebase-design`, investigations. Current; new glossary lookup can miss customized CONTEXT vocabulary. |
| `prototype` | M / alignment, frontend, Wayfinder | One design question → runnable throwaway evidence; UI/logic choice and relevant browser/code tools. Current; keep playbook throwaway-branch and tracker ownership. |
| `domain-modeling` | M / 02 | Resolved terminology/decisions → glossary and sparing ADRs; new glossary format/map references. Current; expands trigger to direct glossary/ADR edits and changes file names. Manual context route until migration selected. |
| `codebase-design` | M / 06, foundations | Interface/design question → shared module/depth/seam vocabulary; reference skill. Current; glossary convention changed; no permission to refactor through loading it. |
| `code-review` | M / 07, 08 | Fixed point, standards and spec → two separate parallel reports; tracker config, ref validation, subagents. Current but source-drifted; now asks for setup instead of invoking it, still lacks the playbook evidence/verdict envelope and explicit ceiling. Manual standards/spec axes. |
| `research` | M / 03, Wayfinder | Question → primary-source findings with citations. Current; prose changed, stage-owned research branch/evidence policy retained. |
| `resolving-merge-conflicts` | M / delegation | In-progress conflict → previously dedicated resolution workflow. Removed in `v1.3.1`, no replacement skill. Use ordinary conflict resolution under the delegation stage; retained `v1.2.3` contract stays available. |
| `wayfinder` | U / 01, 12, Wayfinder | Loose destination → tracker map/frontier tickets and research branches; grilling/domain-modeling, tracker, research workers. Current; explicit calls and human setup ownership changed. Keep one-ticket/session and playbook pickup authority. |
| `grill-me` | U / prerequisites | Idea → interview through explicit `grilling` call. Current; optional human-invoked interview, manual alignment fallback. |
| `handoff` | U / 12, delegation | Conversation → redacted OS-temporary handoff plus suggested skills. Current; that location alone is not portable cloud evidence. Use playbook pickup brief and accessible artifacts. |
| `grilling` | M / 01 | Decision tree → numbered frontier rounds and human confirmation; fact exploration can delegate. Current; punctuation/layout changed; stage 01 owns confirmation and build admission. |
| `writing-for-agents` | M / prerequisites, foundations, skills | Agent document → invocation/hierarchy guidance; `SKILL-MECHANICS.md`. Current; reference/prose changes, playbook skill metadata remains canonical. |
| `caveman`, `zoom-out` | historical U / no active stage | Removed before the retained pin; absent from both tagged trees. Still installed on the supplied Mac. Keep removed; no deletion of host copies in this task. |

Released additions beyond the registered set include `implement-spec`, `pr`,
`retro`, `wizard`, `ask-matt`, `teach`, `wait-what`, `to-questionnaire`, and
miscellaneous/in-progress skills. Directory presence, plugin exposure, and
installation are separate. In particular, `implement-spec` owns a parallel
worktree task graph/integration branch, `pr` shapes PR evidence, and Matt
`retro` proposes environment changes. These introduce ownership overlap with
stages 07/10/12 and gstack names. They are proposed candidates only.

### gstack retained → host snapshot → candidate `1.91.54.0`

All 35 registered directories remain in the candidate tree. Most workflow
files changed, including startup and dependencies. Shared startup now invokes
`gstack-skill-start` with gated onboarding/consent instruction blocks,
state/configuration helpers, artifact sync, learning and telemetry. New
headless/spawned decision rules affect human checkpoints. These dependencies
must be considered with the core workflow; a report-only title alone cannot
qualify a reviewer. Candidate README adds team auto-update/routing setup and
Bun/native-toolchain requirements. No such setup or upgrade ran here.

| Command | Owner / stages | Inputs → outputs; dependencies and verdict |
|---|---|---|
| `office-hours` | M / 01 | Product idea → diagnostic/design doc; brain context, web/design tools and optional outside voice. Current; changed shared startup, optional; manual alignment. |
| `plan-ceo-review` | M / 01 | Plan → scope choices and review log; startup, design/brain/outside voices. Current; scope changes and plan-mode exit gate remain human-owned. |
| `plan-eng-review` | M / 01, 03, 08 | Plan → architecture/test review and amended plan; scope gate, startup, review helpers. Current; optional planning route, no embedded admission implied. |
| `plan-design-review` | M / 01, 08 | UI plan → scored critique/mockups; scope gate, design setup and independent outside voice. Current; writes plan/artifacts; manual/adapter design planning. |
| `plan-devex-review` | M / 01, 08 | Developer-facing plan → DX scores/amended plan; product detection, runtime/docs investigation and startup. Current; optional, manual developer review. |
| `autoplan` | M / 01, 08 | Design doc → sequential CEO/design/DX/engineering reviews and final gate; restore point, outside-worker preflight, startup. Current; auto-decisions and plan writes require human adoption of this route. |
| `design-consultation` | M / frontend | Product context → design system/preview; Aside or bundled browser, design setup. Optional; keep glossary/mockup approval stage-owned. |
| `design-shotgun` | M / frontend | Design/taste feedback → variant comparison board; design generation/setup and startup. Optional; new variants do not become approved vocabulary automatically. |
| `design-html` | M / frontend | Selected design → Pretext HTML/CSS and preview server; framework/package manager/design helpers. Optional generator; approved frontend process remains authoritative. |
| `design-review` | M / 01, frontend | App URL → audit then fix/commit loop; browser, test-framework bootstrap, design/outside voices. Current, drifted; continue `/ai-playbook-design-review`. |
| `review` | M / 08 | Branch/base → risk review and fix-first edits; review checklist, platform CLI, context and startup. Current, drifted; manual adversarial lens. |
| `devex-review` | M / 08 | API/CLI/SDK/docs target → timed onboarding/DX evidence and review ledgers; runtime/browser and startup. Current, drifted; manual developer flow. |
| `cso` | M / 08 | Source/scope → supported security findings and coverage; trusted absolute CSO launcher, schema, runtime profiles and optional Docker. Current, drifted; candidate v3 removes shared startup and distinguishes static, runtime-tested and self-reported assurance. Promising compatibility candidate, unexecuted and unadopted; manual security pass. |
| `qa` | M / 09 | Browser/API/CLI/job/worker/webhook target → tests, fixes, regression evidence and commits; isolation/control helpers and shared startup. Current, drifted; broader surfaces and generation are not independent QA. Manual stage 09. |
| `qa-only` | M / 09 | Same target surfaces → report and repro artifacts; conditional browser/runtime isolation plus shared startup. Current, drifted; report-only core still requires dependency/effects qualification. Manual stage 09. |
| `ship` | M / 10 | Branch → merge-base update, tests, version/changelog, commit/push/PR; platform CLI, review/distribution helpers. Current; generator with shipment side effects. Manual PR workflow under authorized endpoint. |
| `land-and-deploy` | M / 10 | PR/deploy config → merge/deploy/canary/revert; host CLI, deploy runtime and browser. Current; protected actions remain human-owned and outside this task. |
| `canary` | M / 10 | Deployed URL → monitor/report, possible rollback; browser and deployment access. Optional; production authority prerequisite, manual monitoring. |
| `benchmark` | M / 10 | URL/baseline → performance comparison; browser and retained measurements. Optional; no measurements executed in this maintenance task. |
| `browse` | M / 11 | URL/action → live browser observation; now prefers Aside, bundled headless fallback. Optional; do not claim logged-in Mac browser access from cloud. |
| `connect-chrome` | M / 00 | Browser setup → Chromium/side panel; candidate file frontmatter is `open-gstack-browser`. Renamed route/alias candidate, not compatibility-qualified. Manual artifact/browser capability selection. |
| `setup-browser-cookies` | M / 00, 09, 11 | Explicit browser/source scope → cookie import; platform-supported local browser stores and browse runtime. Optional and sensitive; no import or Mac access here. |
| `setup-deploy` | M / 00 | Repo/platform choices → deployment configuration; provider files/CLI and confirmation. Optional setup remains human-owned. |
| `setup-gbrain` | M / 00 | Storage/trust/ingest choices → CLI/brain/MCP/routing configuration; PGLite or Supabase, doctor and policy. Optional; installation, sync and transcript consent remain outside scope. |
| `retro` | M / 12 | Git/PR metrics → engineering retrospective and learning artifacts; platform CLI/brain/startup. Current; changed global/compare flow. Deferred feature retro remains pending. |
| `investigate` | M / 11 | Bug → root-cause investigation/fix evidence; scope-lock hooks, runtime tests, optional browser/brain. Current; stage 11 controls diagnosis and repair. |
| `document-release` | M / lifecycle | Diff/release → doc coverage audit and edits; platform CLI and new ship-owned mode. Current; lifecycle ownership must not replace playbook doc-close. |
| `document-generate` | M / inventory only | Feature/module → Diataxis docs and commit; source archaeology, doc safety helpers. Optional generator; no live stage requirement added. |
| `codex` | M / 06, 08, 11 | Plan/review/question → outside voice/synthesis; CLI auth/model probe, portable roots and filesystem boundary. Current; identity and read-only strength need actual runner proof. Manual fresh reviewer route remains. |
| `careful` | M / 00 | Destructive-command risk → command hooks; host hook support and additive project patterns. Optional; not a substitute for filesystem enforcement. |
| `freeze` | M / 00 | Directory selection → edit boundary hooks/state; host hook support. Optional; cloud safety profile needs separate qualification. |
| `guard` | M / 00 | Safety/directory choice → combined careful/freeze setup. Optional; do not advertise unenforced read-only. |
| `unfreeze` | M / 00 | Existing boundary → cleared freeze state. Optional; permission changes stay human-owned. |
| `gstack-upgrade` | M / 00 | Install/update choice → checkout/setup replacement; Bun floor, backup/pre-advance validation. Optional and mutating; no host upgrade or customization overwrite here. |
| `learn` | M / 12 | Learning query/add/prune/export → persistent learning records; state root and helpers. Current; no global memory/configuration changes in this run. |

Latest-tree additions also include `test-audit` beyond the supplied Mac
candidate list. Browser, iOS, PDF, scrape, agent-pairing and context tools are
optional proposals. The source ledger includes every registered command;
unregistered commands are not silently added to the stage-00 generated inventory.

### pstack retained source → immutable candidate

The five borrowed sources remain present. No new pstack installation or routing
convention is adopted. Current playbook adapters continue to own budgets,
identity, report-only boundaries and evidence. pstack's internal playbooks
are now under `skills/poteto-mode/playbooks`; source-only inspection also
covered the plugin inventory and these orchestration/permission conventions.

| Playbook route / upstream source | Stages | Inputs → outputs; verdict and fallback |
|---|---|---|
| `ai-playbook-verification-harness` / `create-verification-skill` | 00, 09, 11 | Repo/control surface → launch/doctor/drive/evidence/cleanup skill and feature map; requires proving a mapped feature. Exact skill and reference directory unchanged. Keep playbook generator and adoption gate. |
| `ai-playbook-maintain-verification-harness` / `maintain-verification-skill` | 08, 09, lifecycle | Existing skill/map → complete source/live coverage and at most one proven correction PR; source workers plus serial live driving. Exact source unchanged. Keep playbook complete-coverage and clock rules. |
| `ai-playbook-why` / `why` | 02, 06, 08, 11 | Code anchor/history/MCP sources → calibrated rationale/constraints; investigator and synthesizer references. Drift: role defaults via `pstack-models.mdc`, agent-mode `readonly: false` for MCP access. Keep local cited-evidence adapter; do not relax verifier permissions or infer model availability. |
| `ai-playbook-how` / `how` | 06, 08, 11 | Code question → architectural explanation via explorers/explainer; complexity split and model rule. Drift: critique branch removed and reference set reduced. Keep local interpretation-versus-execution contract. |
| `ai-playbook-blast-radius` / `blast-radius` | 08 | Diff/safety assumptions → executed proof, risks and cleared facts; `why` and optional multi-model arena. Drift: prose/explicit unproven-risk wording changed. Keep local explicit unproven-evidence floor. |

## Embedded compatibility and execution boundary

Executed `check-upstream-compatibility.py --skill KEY --source EXACT-SKILL.md
--fallback ROUTE --json` for **all eight** integrations against retained and
candidate trees, plus all six gstack sources at the supplied Mac revision:
22 decisions, each exit **2** (`may_invoke: false`). Retained sources: eight
incompatible. Released Matt: `code-review` drifted; `implement` unchanged and
incompatible. gstack Mac and candidate: all six drifted. No exit 1 manifest
errors. Exact digests, reasons and fallbacks are in the portable ledger.

Fallbacks are stage 07 implementation; stage 08 standards/spec, adversarial,
developer and security passes; `/ai-playbook-design-review`; and stage 09 QA.
No manifest digest or compatible flag was edited to grant admission. No
compatibility change was selected, so disposable-repository execution of a
new embedded route is **not performed** and no compatible credit is claimed.
Any later compatible proposal requires that execution and independent reviewed
evidence before its exact source can enter the allowlist. The current monthly
comparison is source inspection plus fail-closed checker execution.

## First-party documentation comparison

The first-party URLs were retrieved on 2026-10-08, separately from tagged skill
trees. This is documentation comparison, not installed runtime qualification.
Historical dates in maintenance state and generated provenance stay unchanged.

- Claude [memory](https://code.claude.com/docs/en/memory) still distinguishes
  instructions from enforcement. [Subagents](https://code.claude.com/docs/en/sub-agents)
  now explicitly describe parent permission-mode overrides and ignored plugin
  permission fields. [Settings](https://code.claude.com/docs/en/settings) has
  expanded precedence/merge rules. Risk: a configured child permission mode
  does not prove an enforced read-only reviewer. Requalify at the next actual
  host/tool change; preserve local settings and human scope.
- The recorded Codex AGENTS and CLI URLs redirect to official ChatGPT Learn
  [instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
  and [developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli).
  Override discovery and sandbox/approval distinctions remain documented.
  Proposed batch: review canonical links at the next host-doc update, without
  changing model defaults or claiming cloud filesystem enforcement.
- Old Cursor links redirect to the docs index; inspect the current
  [CLI](https://cursor.com/docs/cli/using), [rules](https://cursor.com/docs/rules),
  and [cloud agents](https://cursor.com/docs/cloud-agent) pages instead. CLI
  command approval and noninteractive write access remain separate; rules
  now document nested AGENTS precedence. Proposed batch: canonical URL refresh
  and permission requalification. A cloud VM is not proof of read-only tools.

## Proposed adoption batch and future checkpoints

1. **Domain migration:** human-select a Matt upgrade; inventory customized
   CONTEXT/glossary maps and ADR links, preview a reversible migration, preserve
   edits and active approvals, then test the affected stages in a disposable
   repo. Keep `v1.2.3` until that batch is reviewed.
2. **Removed/renamed skills:** review retirement of conflict-resolution guidance
   and the browser alias; test actual command resolution before changing the
   registry. Existing installs are not deleted by maintenance.
3. **Embedded candidates:** separately qualify gstack CSO v3 and expanded QA
   surfaces, including helper/dependency closure, effects, budgets, output and
   privacy. Exact-source execution plus fresh review precede any digest update.
4. **Optional workflows:** human-select only useful new commands. Resolve
   Matt/gstack `retro` name collision, implement-spec branch/commit ownership,
   setup/auto-update and telemetry consent before adoption. No retrospective
   or closeout state changes are authorized by this note.
5. **Future updates:** recheck authoritative release pages monthly by 2026-11-08
   and before upstream-contract releases; check installed sources on the actual
   host at upgrade/tool/settings changes. Requalify compatibility after each
   source/dependency change, preserve user customizations and keep drifted
   routes manual. Model guidance follows its separate maintainer checkpoint.

## Verification and limitations

The monthly checker is a due/manifest gate; it does not prove this comparison.
The source ledger and behavior tables provide that evidence. Edition manifest
and generated inventories are regenerated/checked with this maintenance change.
Canonical release-readiness execution, fresh report-only review, privacy results
and actual PR-head CI are recorded in the PR/cloud artifacts. A skipped
privileged suite is not counted as a pass; unavailable Linux capabilities must
be reported and covered by actual GitHub CI without weakening tests.

Private evidence retains the transferred Mac JSON, separate cloud audit,
API responses, fetched source trees, compatibility output and command failures.
The initial `cursor/pstack` API request returned 404; the corrected
`cursor/plugins` request succeeded. A mistaken Matt path omitted `skills/`
and failed before the correct path was read. Browser markdown retrieval was
unsupported; the official HTML pages were inspected instead. None of those
failed attempts supplies comparison credit. No Mac-local supervisor is needed.

The cloud's initial Python 3.9 attempt was rejected by canonical verification
as below the supported minimum; a Markdown check also failed during import.
Python 3.12 is used for supported verification, with the canonical command
unchanged. Direct downloads of Claude Markdown pages returned HTTP 403;
the browser tool successfully retrieved the authoritative HTML pages.

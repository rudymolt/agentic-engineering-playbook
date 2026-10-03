# Playbook changelog

## Unreleased

- Bootstrap seeding now rechecks every selected seed skill at the same
  publication and completion points as Configure, and the shared saver requires
  that admission check from every caller.

*Why — one caller skipped the shared guard:* a personal defaults or preset seed
was validated only before saving, so a source, proof, contract, approval,
resolution or catalog change during the write could still publish an ineligible
binding and report a successful bootstrap. Earlier drift now leaves the seed
absent; later drift reports incomplete setup with retained recovery evidence.

- Recheck reviewed skill admission at each destination's publication and save
  completion boundary, including pending personal defaults/presets after
  Recommended and paired completion. Retain recovery evidence on later drift.

*Why — early validation leaves a publication window:* source, proof, approval,
resolution or catalog changes during staging could publish an ineligible reusable
binding and report validated success. Both destinations now use the same current
admission guard before mutation and completion, preserving concurrent bytes and
requiring explicit recovery instead of claiming a partially valid save.

- Refresh current skill options and rejection diagnostics on explicit job-editor
  entry, preserving selected identities and unrelated drafts through fallback
  choice, reusable-save preview and local or paired Apply.

*Why — retained drafts need a complete recovery route:* stale retained catalogs
blocked even an explicitly chosen eligible fallback after source or proof drift.
Job-editor discovery now renews that job's reviewed catalog without substitution,
invocation, weaker save checks or requalification of unchanged stored bindings.

- Recheck newly added or replaced personal defaults/preset job bindings before
  paired project Apply, including when Recommended resets the project draft.
  Retain blocked proposals and preserve older unchanged reusable bindings.

*Why — both save destinations need current eligibility:* a pending personal save
survives the project draft reset. Paired Apply now uses the same source, retained
proof and job-contract boundary as local Apply preference before writing either
destination, so stale bindings cannot be reported as validated reusable data.

- Recheck current skill source, retained contract proof and reviewed eligibility
  before local Apply preference adds or replaces a defaults/preset job binding.
  Preserve blocked drafts and leave older inert reusable bindings untouched.

*Why — local reuse needs the same eligibility boundary as project Apply:* a
source or audit can change after preview. Shape validation alone published stale
bindings as validated; fresh resolution now blocks before any preference write,
without requalifying unrelated presentation, billing or existing reusable data.

- Validate retained token subtotals against the selected rate and requested
  proposal workload before displaying them.

*Why — adequate rates do not establish a subtotal:* caller drafts could retain
an amount with a mismatched billing route, changed rates, boolean amount or
self-consistent assumptions for another workload. Projection now withholds the
unsupported subtotal while preserving suitable draft choices, valid rates and
original dates, without fetching, saving or substituting an amount.

- Project every advice cost payload, including estimate-only caller drafts, and
  require an adequate original selected rate before displaying a token subtotal.

*Why — integrity does not establish cost evidence:* a resealed malformed draft
could retain an unsupported estimate through Explain, Back, Presets and error
recovery. Missing, invalid or expired pricing now withholds the subtotal without
fetching, saving or substituting advice; explicit Refresh and editing remain
the recovery routes.

- Preserve root-selected guidance and independently dated pricing when rejecting
  a divergent or malformed replacement advice copy.

*Why — rejected copies cannot become original evidence:* failed Accept must not
replace the selected claim's text or date with a younger or older nested claim.
Partial roots retain their own evidence, and subsequent Explain and Back keep
it withheld with explicit Refresh/editor recovery instead of re-ranking.

- Retain selected advice through previews and rejected acceptance, and withhold
  nested advice when a persisted or caller-supplied proposal is malformed.

*Why — display recovery must not select new evidence:* Back and rejected Accept
must preserve the original claim and successful date instead of silently ranking
a younger sibling. Every public advice copy needs projection; a content checksum
cannot authorize malformed advice. Refresh and ordinary editing remain explicit.

- Recheck original recommendation claims when rendering delayed Explain,
  display replies and retained drafts, preserving dated limitations and recovery.

*Why — evidence can expire while a sealed proposal waits:* a fresh read does
not extend an individual claim beyond the inclusive 24-hour boundary. Withhold
inadequate suitability, rates and subtotals without substituting a candidate,
fetching on an unrelated reply, writing the cache or changing user choices.

- Revalidate the exact proposed replacement and its original guidance at
  acceptance time, retaining the draft when evidence expires or discovery changes.

*Why — a valid read can expire before acceptance:* the inclusive 24-hour boundary
must hold before editing the draft. Current role/task/risk and route checks keep
cached advice from granting selection; changed discovery requires explicit Refresh
or ordinary role editing. Missing pricing alone does not block suitability, and
Apply retains its independent availability, identity, revision and skill checks.

- Validate each guidance and pricing claim's original successful date on retrieval
  and reuse, independently of source metadata and sibling claims.

*Why — aggregate freshness cannot establish individual evidence:* expired claims
remain visibly stale, and future or missing dates remain incomplete. Withhold
unsupported suitability, replacement, rates and subtotals while preserving exact
successful dates, explicit Apply and intentional configuration choices.

- Reuse bounded local official recommendation evidence for at most 24 hours at
  discovery, checking immediately on first use, explicit Refresh or a changed
  model/version fingerprint. Offer draft-only recovery for unavailable models.

*Why — current advice must preserve intentional choices:* source changes can
affect existing models and costs without granting selection or launch authority.
Retain successful dates on failed refresh, explain material claim changes, and
require a refreshed preview and explicit Apply after replacement acceptance.
Preserve active approvals, personal presets, billing and repair constraints.

- Require exact Anthropic base-context eligibility at table and model-row
  boundaries, and bound numeric rates before validating or estimating costs.

*Why — applicability and arithmetic must both be proven:* extended/long-context
and ambiguous `For ...` qualifications cannot support base workload prices.
Oversized structured integers must remain unknown without conversion overflow,
CLI tracebacks or writes; preserve positive exact rates and task guidance.

- Require affirmative model-associated suitability predicates and explicit
  Standard short-context provenance; bound workload counts before token arithmetic.

*Why — source meaning and numerical limits are evidence boundaries:* unsuitable,
unproven and effort-setting statements must not become task-fit claims. Hyphenated
or HTML-spaced long-context restrictions cannot supply short-context rates, and
oversized JSON counts leave a labelled unknown subtotal rather than a traceback.
Preserve source dates, explicit choices, read-only bytes and private billing.

- Bound official task-fit evidence to the exact model description and pricing
  evidence to the exact table tier and token context. Control paragraphs,
  nonaffirmative wording and ambiguous table context remain unknown.

*Why — nearby text is not evidence:* unrelated catalogue sections and reasoning
controls must not recommend a model, and Batch rates must not become a Standard
workload subtotal. Keep claim-specific sources and successful check dates while
preserving read-only selection and private billing boundaries.

- Add read-only role recommendations at Configure and new lane-selection gates,
  with official-source retrieval, separate task-fit/rate/local-outcome evidence,
  labelled API assumptions and explicit subscription or incomplete-data unknowns.

*Why — advice must not become authority or a fabricated bill:* filter verified
routes and existing gate constraints before comparing, retain effective
preferences and approvals, and keep private billing and outcome evidence local.
No candidate invocation, automatic switch, paid comparison or savings promise
is part of discovery; source dates distinguish retrieval from successful checks.

- Isolate paired rollback publication from mutable backup evidence, report the
  exact reviewed local completion destination and preserve unanswered
  Guided/Expert choices while drafting reusable defaults or presets.

*Why — recovery and reuse must preserve reviewed intent:* a late backup edit
must not become live configuration, completion must identify the actual local
store without leaking it into project files, and saving reusable data must not
silently choose a presentation preference.

- Add local reusable defaults, named presets and billing preferences without
  changing active selections, approvals or history. Preset loading previews a
  draft; explicit Apply revalidates model/skill identities. Bootstrap previews
  new-project seeding and requires the exact reviewed seed revision.

*Why — reuse must not become implicit execution or cross-project mutation:*
keep presentation, billing and local source resolution private, preserve
existing projects and custom qualification, and reject unknown data without
lossy fallback. Combined personal/project saves retain paired recovery evidence,
validate both destinations before completion and preserve concurrent edits
during rollback. Failure results omit unreviewed exception text while keeping
the reviewed personal destination available for local recovery.

- Contain filesystem resolution errors at the path boundary, including cyclic
  QA sources, evidence, installed sources and personal storage. Retain portable
  rejection and explicit recovery at Configure and stage-owned invocation.

*Why — symlink loops can raise path-bearing runtime errors:* expected resolution
failures must not escape as private tracebacks. Preserve saved choices, approvals,
history and local bytes, block affected invocation and Apply, and require explicit
revalidation without automatic fallback, rewriting or execution.

- Guard custom binding catalog construction and public filesystem errors with
  portable recovery diagnostics. Reject dot and empty identity path components
  before publishing inventory rejections, without normalizing saved sources.

*Why — privacy applies before discovery and on rejection:* denied local stores
and noncanonical project keys must not disclose private locators. Preserve
saved choices and external bytes, block unresolved invocation and Apply, and
require explicit recovery without fallback or execution.

- Redact rejected noncanonical local inventory identities with one shared
  portable-identity predicate. Block early selection-state read and parse
  failures with logical artifact, error class and explicit recovery guidance.

*Why — rejection and snapshot failures are public output:* rejecting an unsafe
identity or unreadable state must not disclose its private locator or parser
text. Preserve exact-source choices, saved QA qualification and stored bytes;
require deliberate recovery rather than fallback, execution or rewriting.

- Keep project QA read and qualification rejections portable: name the logical
  artifact and error class, require stage 09 revalidation or an explicitly
  selected fallback, and never echo filesystem or untrusted parser diagnostics.

*Why — QA diagnostics are public configuration output:* unreadable eligibility,
retained evidence and skill sources must block without revealing local locators
or changing saved choices, exact-source checks or stage-owned qualification.

- Reject multiple-link local inventory, approvals and retained evidence at
  discovery, Apply and stage invocation. Redact installed-source read failures
  to a portable error class and exact-source recovery action.

*Why — local isolation includes inode aliases and diagnostics:* external paths
alone do not rule out project hardlinks, and raw filesystem errors can publish
private source locators. These guards block observable aliases and retain
actionable recovery without changing saved choices or execution authority.

- Add portable custom job identities with separately retained machine-local
  bindings and stage-owned exact-source contract audits. Reject project-local
  audit stores, source/resolution drift, unpinned evidence and custom embedded
  upstream claims; preserve stage QA selection and existing execution approvals.

*Why — portable choices without portable private paths:* collaborators can
retain byte-identical project settings while resolving their own qualified
sources, or recover an unresolved choice explicitly. Local audit assertions
do not authenticate independent execution or approval; those gates remain
stage-owned, with no experimental candidate execution or authority expansion.

- Add versioned source-labelled bindings for alignment, specification,
  implementation, code review and application QA through Configure's existing
  save boundary. Stage entry resolves saved choices and blocks source/contract
  drift or collisions; embedded review/QA reuse exact-source report-only checks.
  QA reads only an already selected eligible project route.

*Why — preferences without transferred authority:* users can choose supported
routes or honest manual/adapter fallbacks while preserving active approvals,
history, customisations and stage obligations. Configuration does not execute
candidate skills, create harnesses or enable maintenance. Live host
qualification remains separate.

- Bind personal preference previews to the resolved local and project directory identities. Use descriptor-relative personal writes and recovery bookkeeping so retargeted aliases cannot redirect transaction files into the project; preserve drafts and require a new destination preview after a directory change.

*Why — preserve personal storage isolation:* a one-time directory check allowed a long-lived Configure service to publish personal settings inside a project after an alias changed. Rechecking identity and anchoring storage operations closes that alias race while preserving the existing content completion and paired recovery protocol. External relocation of the opened directory itself still requires filesystem coordination.

- Check paired recovery after the final configuration content-digest comparisons before sealing success. Keep the single content completion point, retained recovery evidence and Back/Edit drafts; cover final-check entry and last-read recovery through both public save directions.

*Why — close the final-check gap:* the preceding paired guard could miss recovery arising during the completing receipt check. A final paired veto catches recovery pending at the content completion point without rechecking later content edits or using timestamps.

- Recheck paired configuration stores throughout either save's staging, capture, publication and completion window. New locks, recovery journals and unfinished/conflicting receipts prevent publication or retain truthful recovery evidence after publication, without discarding sealed role drafts or overwriting concurrent bytes.

*Why — recovery can arise after admission:* checking both stores only before a save allowed the other store's newly pending recovery to coexist with a successful write. Repeated paired checks preserve the active transaction's protocol and the approved content-digest completion point while requiring reconciliation before continuation.

- Extend Configure to all four model roles with typed role/model/runner/reasoning choices, read-only explanations, QA inheritance and observed display-only Coordinator identity. Preview and save guided/expert presentation locally through the accepted content-completion/recovery protocol, separately from project Apply; retain sealed role drafts when a save requires recovery. A shared write guard checks both project and local recovery evidence before either save or local directory creation; Back/Edit preserves the draft until reconciliation permits Apply. Route new projects back to the existing bootstrap gate.

*Why — complete role editing without new execution authority:* users need a complete model proposal that retains project customisations, unrelated drafts and approved execution history, without repeating known onboarding, silently substituting a route or confusing presentation saves with project saves. Recommendation evidence, skill bindings and live host qualification remain separate slices.

- Complete S1 configuration saves with a final content-digest check after durability steps, not filesystem timestamps. Completed receipts permit later edits; unfinished saves and detectable older-receipt conflicts still require non-destructive reconciliation.

*Why — content-based completion:* metadata-only changes cannot date content edits or hide a conflict. A single completion check preserves concurrent bytes and reviewed evidence without retroactively rejecting successful saves.

- Separate S1 journal promotion from certified transaction completion, reconcile pending/conflicting receipts in every preference reader, and retain independent reviewed candidate bytes alongside captured and published inodes. Define the completion seal's linearization boundary so ordinary later project edits remain allowed.

*Why — truthful transaction completion:* an external destination or old-open-inode write before receipt promotion must not become a successful Apply merely because recovery markers disappear. Completion-window and marker-loss regressions require actionable reconciliation without deleting external bytes or mutating approved history.

- Repair S1 configuration races with durable capture and no-clobber publication, retain conflict evidence instead of destructive rollback, bind new escalated-Verify policy to immutable approvals while preserving historical routes, and require request-bound current-availability discovery separately from guidance caches.

*Why — confirmed S1 contract gaps:* arbitrary external edits must survive Apply and recovery; approved execution history must remain readable without rerouting; rereading cached guidance cannot establish current access. Regression tests cover both absent and pre-existing files, retained historical bytes, host dispatch, and adapter clocks without paid launches or S8 claims.

- Add the user-invoked S1 Configure chat path and a shared versioned project-default boundary. Import all legacy roles, preserve runtime records, preview Build edits, revalidate Apply, and roll back or report recovery. Existing lane gates resolve adopted defaults without changing approval or launch authority.

*Why — safe project defaults:* changing one future Build preference must preserve custom roles and active work, with one authoritative source and no silent fallback, substitution or model launch.

- Use GPT-6.1 Sol/high for Plan and Verify (including QA and escalated-candidate verification), and GPT-6.1 Sol/medium for Build. Retain GPT-6 Astra/high for escalated repair. Update bootstrap and upgrade defaults, preserving custom project routes and existing feature selections.

*Why — current model defaults:* the approved model policy now uses GPT-6.1 Sol for planning, implementation and independent verification while retaining bounded Astra escalation for difficult repairs.

- Generate concrete Actions evidence links for runtime history and allow this public repository's run URLs only in the two runtime evidence outputs.

*Why — usable evidence:* placeholder owner links prevented readers from opening the measured runs; scoped link validation keeps unrelated private markers blocked.

- Profile delivery tests with revision-bound repeated timings, retain a reviewed-test ledger, and reuse successful Git ref syntax probes within three selected advance tests. Every record validator, Git checkpoint operation, and existing assertion still runs.

*Why — test runtime:* repeated input-only syntax subprocesses add measurable overhead; a cache confined to each selected test reduces that cost without sharing mutable fixtures or bypassing rejection checks.

- Keep the required `delivery` CI job fast for unrelated changes, while retaining the full delivery suite for runtime changes, delivery contract surfaces, workflow changes, classifier changes, and manual runs.

*Why — proportional verification:* documentation-only pull requests should still pass required public-edition checks without spending more than ten minutes exercising an unaffected delivery runtime.

- Link the public interactive guides from the README and permit that exact link in the root README privacy check. Other personal references remain blocked.

*Why — discoverability:* readers need a direct route to the human-facing guides without weakening the public-content boundary.

- Expand the README with skill sources and installation guidance, Wayfinder, customizable capability routes, coding-agent environments, and Conductor setup and autonomous delivery. Clarify that full bootstrap installs delivery, while capability checks and mission approval govern its use.

*Why — maintenance batch:* readers need to understand which tools are included, what to install separately, and how approved work can progress from planning to a verified pull request.

- Rewrite the root README with an ASCII wordmark, a plain-language overview, a pinned-release quick start, separate human and agent entry points, and acknowledgements including Lauren Tan's pstack.

*Why — maintenance batch:* readers need a self-contained introduction and actionable setup instructions, with clear credit for the upstream work behind the playbook.

- Match the release skill's playbook profile to the public repository name and require `noreply` identities for maintainer commits and GitHub-generated merges.

*Why — correctness and privacy:* the new repository name should not bypass the public release checks; local commit configuration alone does not control GitHub-generated merge metadata.

## V0.5.0 — 2026-09-26

Initial public edition from a reviewed adaptation of the private V0.4.2 source. It begins a new Git history, carries one live edition, and adds an independent public verification and upgrade contract.

*Why — public distribution:* earlier repository history and edition trees contain private records and cannot be exposed safely. A clean public edition makes bootstrap and stable tagged use possible without publishing that history.

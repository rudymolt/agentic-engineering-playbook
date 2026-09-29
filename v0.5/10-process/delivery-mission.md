# Delivery mission — process-attested agent ownership

> Optional runbook reached from stages 04 and 07. It is not a fourteenth
> stage: the mission owns execution across stages 07–10 and returns ordinary
> stage results.

**This runbook in one breath:** after collaborative planning produces an exact
human-approved envelope, `/ai-playbook-deliver` may own bounded Build → Verify →
QA → PR handback, and an separately admitted fresh K4.1 session may merge the
exact head. Output: a Tier A `pr_ready` handback or a visibly process-attested
K4.1 merge receipt; never deploy or release.

## Assurance boundary

Before creating an approval envelope, resolve unselected preferences through
the [shared project reader](../scripts/playbook-config.md), including repair
preferences and retained escalation constraints. Explicit envelope choices
override preferences. After approval, routes, escalation policy and execution
records are immutable: Configure cannot amend/re-resolve an active mission.
Existing discovery, identity and gate checks admit every launch independently.

V0.5.0 ships two process-attested routes:

| Route | Maximum action | What it proves | What it never proves |
|---|---|---|---|
| Tier A delivery | `open-pr` | Resumable agent-owned build, fresh verification, QA, and exact PR handback | Merge, deploy, release, or non-bypass protection |
| K4.1 bridge | `merge` | A clean-context session independently decided and expected-head dispatched under current project authority | Tier B/C, credential separation, protected judge, deploy, or release |

K4.1 is a rollout milestone, not an A/B/C tier. Every K4.1 authority and receipt
states `process_attested_only: true`, `non_bypass_protection: false`, and
`tier_b_authority: false`. K5/Tier B is a separate optional higher-assurance
lane and is unavailable until its protected-host contract is independently
approved and proven.

## Entry contract

Stages 01–04 remain collaborative and human-led. Before any delivery-owned
feature write, durable planning must contain:

- accepted spec and dependency-ordered slices;
- `pilot-observation-contract.json` declaring the attempt window, signals,
  raw-evidence locators, defect route, issuer, and declaration timestamp;
- Delivery Envelope V2 binding the exact planning prefix, approved
  implementation paths, risk class, evidence plan, ceilings, and maximum
  action;
- Approval V2 from the human's durable source event; and
- project policy and capability evidence for the selected local or Cloud
  venue.

The historical `pilot-` contract filename and schema names remain stable so
existing records are not relabelled. They do not make this a second edition.

The envelope must cap ordinary delivery at Tier A/`open-pr`. Selecting K4.1
adds the bridge authority class but does not give the builder or coordinator
merge authority; PR and candidate facts bind only after the authorized feature
write creates them.

## Start and resume

Invoke `/ai-playbook-deliver`. The installed skill is manifest-owned at
`.agents/skills/ai-playbook-deliver/`; the source is
[`../delivery/skill/scripts/deliver.py`](../delivery/skill/scripts/deliver.py).
Use that installed command boundary and never reconstruct commands from chat.

Preflight validates the observation contract, envelope, approval, policy,
venue, ceilings, and runtime. New missions register Attempt V3 before feature
writes and initialize Mission Control. Existing missions resume observer-only:
reconcile dispatched or ambiguous operations first, then claim a new
controller generation by compare-and-set. Loss of authority, stale generation,
unknown evidence, or another controller winning stops the run.

A conditional [pickup brief](pickup-brief.md) may carry portable context into a
new session, but it cannot substitute for this observer/re-entry sequence,
Mission Control, or the durable receipt.

## Build, check, and QA

The mission follows stage 07's TDD and budget contracts. One mutable builder
may execute approved slices. Every checker is a fresh session with exact model,
effort, runner, permission, command, candidate, tree, and wall-time evidence.
Use Launcher V2 normally, V3 for the exact macOS FSEvents Seatbelt allowance,
and V4 only for Conductor turns whose host creates the bound start/end
checkpoint refs. Any unowned checkout or Git mutation makes the checker
nonqualifying.

Freeze one complete candidate, close every finding, run fresh stage 09 QA, and
evaluate process-attested G1–G8. Tier A simulates G9 without dispatch. The
handback must bind the exact PR, head, tree, policy, checks, QA, finding ledger,
and required actions and end at `pr_ready`.

## Optional K4.1 fresh merge

K4.1 is disabled without project admission and an exact, current standing-
authority receipt from the default branch. Its fresh session receives policy,
locators, exact PR/base/head/method, and verification commands—but no builder
or coordinator transcript.

The fresh session resolves host truth, reads the complete diff, classifies
risk, executes verification, reconciles findings/reviews/actions, and persists
an allow or deny decision to a durable GitHub PR comment with byte-for-byte
readback attestation. An allow decision then requires an immediate re-query of
the current head, paths, reviews, checks, mergeability, standing authority,
kill switch, and remote Mission Control generation.

An empty GitHub status rollup means only that no failing host check was
reported. Every reported check must be `SUCCESS`; independently executed fresh
verification remains mandatory. The PR must separately be open, non-draft,
`MERGEABLE`, and `CLEAN`.

Dispatch atomically claims the full decision digest, uses GitHub's expected-
head merge, observes before retry, and persists `process-attested-merge/v1`.
Any ambiguous host result remains ambiguous even if a later external merge is
observed. The session stops immediately after merge.

## Mandatory human route

Human merge remains mandatory for unresolved taste, auth, authorization,
secrets, privacy, payments, billing, data-loss risk, migrations, deploy,
rollback, production, repository administration, rulesets, credentials,
delivery policy/tooling, or any unclear path. Candidate edits to policy cannot
authorize themselves.

## Terminal routing

Every command returns `outcome`, `next_phase`, `required_actions`, and durable
receipt/evidence locators. A blocked or denied mission returns to the owning
stage; it does not consume an unobserved retry. Tier A stops at stage 10's human
merge handoff. K4.1 stops at merge, after which closeout, deploy, release,
archive, and retro remain human-owned unless a future separately approved lane
defines them.

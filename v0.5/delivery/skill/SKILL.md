---
name: ai-playbook-deliver
description: Run or resume V0.5 process-attested delivery after stages 00–06 approve its envelope. Use for /ai-playbook-deliver, Tier A PR delivery, recovery, fresh checking, QA, handback, and an explicitly admitted K4.1 merge. Never use it for deploy, release, or Tier B/C.
disable-model-invocation: true
---

# AI Playbook Deliver

Operate only the digest-bound Tier A pack installed beside this file. Do not
reconstruct its workflow from chat or from another playbook edition.

1. Require `planning/{feature}/pilot-observation-contract.json` before approval.
   It must declare the attempt/mission IDs, merge- or release-based window,
   duration, non-empty signals and raw-evidence locators, defect route, receipt
   issuer, and declaration time. Put its canonical digest and ref in the V2
   envelope; never treat the envelope's old planning provenance as a contract.
   For the process-attested lane, declare either `process-attested:linear:<issue-id>` or an
   already-proven `protected-store:<store-id>` as the issuer. Never invent a
   protected store. A process-attested issuer is Tier A evidence only.
2. Run `python3 scripts/deliver.py preflight --project <project-root>`.
3. If preflight returns `blocked`, report its typed reasons and required actions.
   Do not offer a Cloud venue without a current admission receipt.
   For Cloud, first validate `.playbook/cloud-readiness.yml`, run CR1–CR10 in a
   fresh Cloud workspace, and validate the resulting admission receipt. Require
   exact build/setup epochs; absent or ambiguous epochs forbid reuse. Probe
   secret environment names for presence only. Retain redacted raw evidence.
   On wake, observe health before using the digest-bound resume command and
   re-establish CR7/CR8. Never treat a forwarded human port as a checker route,
   switch silently to local, or infer process survival from retained files.
4. If no mission exists, require the validated envelope, observation contract,
   and Approval V2 receipt. Register Pilot Attempt V3 with both envelope and
   observation-contract digests:

   ```bash
   python3 scripts/deliver.py register-attempt --input <attempt> --contract <contract> --envelope <envelope> --approval <approval>
   ```

   Then initialize its control ref/record before any feature write or external
   operation.
5. If a mission exists, enter observer-only recovery first. Reconcile every
   dispatched or ambiguous operation, then claim a new controller generation by
   compare-and-set. Stop if another controller wins.
6. Follow the mission's aggregate phase and checked transition output. Keep one
   mutable builder, use fresh checker sessions, freeze the exact candidate, run
   the process-attested G1–G8 oracle, and simulate G9 without dispatch.
   Before each checker launch, require Launcher V2 for providers that need no
   host exception, Launcher V3 for a macOS checker that exercises filesystem
   watching, or Launcher V4 for a Cloud Conductor session whose host creates
   automatic Git checkpoints. All require Python bytecode disabled by environment
   and `-B`, repository
   temp/cache paths outside the checkout, repository writes forbidden, and a
   transient-write monitor enabled. Invoke checker-side Python through
   `python3 scripts/checker-python.py ...`; use `canonical-digest` instead of
   importing the installed runtime from `python -c`. Any transient checkout
   write invalidates the launch even when the file is later removed.
   Launcher V3 additionally requires exactly
   `macos_mach_lookup_allowlist: [com.apple.FSEvents]` and the digest of the
   complete effective Seatbelt profile. Apply it only through
   `scripts/checker-launcher-v3.py`, validate the receipt through both
   `validate --schema launcher-v3` and `validate-launcher`, and compare its
   execution policy with the exact envelope-bound object. Never reinterpret a
   Launcher V2 receipt as V3.
   Launcher V4 permits only the exact
   `refs/conductor-checkpoints/session-<session-id>-turn-<turn-id>-start` and
   `-end` refs for one common session/turn pair,
   their `Checkpointer <checkpointer@noreply>` commits, and their exclusive Git
   objects. Bind both refs, commits, candidate-equal trees, timestamps, and the
   metadata-inventory digest. Require identical start/end HEAD, candidate tree,
   index, staged diff, worktree, untracked inventory, and non-checkpoint refs.
   On Linux, require `monitor_backend: linux-inotify` and
   `git_writer_attribution_backend: linux-fanotify-pid`. Every Git lock event
   must carry its exact kernel-reported writer PID plus the redacted
   monitor-owned/external identity record. Missing attribution, attribution
   overflow, or attribution-backend unavailability is nonqualifying; never
   infer a writer from timing or a later-clean fingerprint.
   Validate through both `validate --schema launcher-v4` and
   `validate-launcher`. Any other Git or checkout mutation invalidates the
   launch. Never reinterpret V2 or V3 as V4.
   A Launcher V4 checker qualifies only with a companion
   `checker-session-lifecycle/v1` record. The record binds the launch, session,
   candidate tree, complete command-manifest digest and locator, positive
   command count, explicit completion of every required command, observed exit
   codes, reaped child processes, last-command completion, monitor stop, and the exact
   `checker-session-complete/v1` marker. Validate it with both
   `validate --schema checker-session-lifecycle` and
   `validate-checker-lifecycle --launcher <launcher-v4> --lifecycle <record>`.
   Start and stop the required source monitor only through the manifest-owned
   harness from the project root:

   ```bash
   python3 .agents/skills/ai-playbook-deliver/scripts/checker-python.py \
     .agents/skills/ai-playbook-deliver/scripts/checker-monitor.py start \
     --repository "$PWD" --evidence-dir "$CHECKER_EXTERNAL_ROOT/source-monitor"

   python3 .agents/skills/ai-playbook-deliver/scripts/checker-python.py \
     .agents/skills/ai-playbook-deliver/scripts/checker-monitor.py stop \
     --evidence-dir "$CHECKER_EXTERNAL_ROOT/source-monitor"
   ```

   On a Launcher V4 Linux Cloud checker, the start command returns success only
   after recursive inotify coverage is armed and the first complete Git
   fingerprint matches. Periodic fingerprints are a second control, not the
   transient-write detector. Event-queue overflow or any non-checkpoint
   filesystem event invalidates the run, including a create/remove cycle wholly
   between fingerprint intervals. The stop command returns success only after a
   final fingerprint, terminal monitor outcome, and actual process exit. Never
   generate a shell fingerprint helper, use a polling-only substitute, invoke
   the monitor directly, repair an early monitor exit, or count a run whose
   start/stop result is not successful. Preserve
   `monitor-state.json`, `source-baseline.json`, `monitor-ready.json`,
   `monitor-events.jsonl`, and `monitor-outcome.json` in the launch evidence.
   The last command and monitor MUST finish before the host-owned turn-end
   checkpoint. `working → idle` without a final agent reply is pending, never
   completion. Later files or passing output cannot repair an early provider
   turn end; preserve that launch as nonqualifying.
   A Cloud candidate additionally reruns CR5–CR9 and every CR selected by the
   frozen invalidation matrix. Reuse from admission is valid only while its
   30-day TTL, profile/setup digests, environment-name set, review route, and
   observed build/setup epochs remain exact.
7. Publish deterministic taste or safety questions once, checkpoint, and park.
   Never poll Linear. On manual resume, reconcile the current revision once.
8. Finish ordinary Tier A only with a validated handback receipt whose outcome
   is `pr_ready`. The builder and coordinator never merge, deploy, archive as a
   full-delivery finalizer, or claim Tier B/C authority.

## K4.1 fresh-agent merge bridge

K4.1 is disabled unless the project has an exact current standing-authority
receipt and the approved envelope selects
`authority_class: process-attested-fresh-merge`. It does not widen Tier A.
The exact receipt must also be current at its declared default-branch
`authority_path`; a local or superseded copy is not authority.

At the mandatory pre-write approval boundary, bind the exact repository,
project, mission, base, merge method, risk class,
`planning/{feature-slug}/` prefix, and sorted exact non-planning implementation
paths. Declare `candidate_binding: post-freeze` and `pr_binding: post-pr`.
Never place a PR number or candidate tuple in this envelope: they are bound only
after the authorized implementation creates and freezes them.

Only a new clean-context merge-agent session may enter this route. Its identity
must come from the validated launcher receipt. It must read
`references/k41-policy.json` from the host-observed default branch at the exact
standing-authority path and follow the fixed prompt in
`references/k41-merge-agent.md`. The builder and coordinator remain capped
at `open-pr`; their session IDs cannot equal the merge-agent session ID.

Before dispatch, resolve every durable receipt, independently read the complete
diff, execute fresh verification, require G1–G8 and every finding/action/thread
closed, use `k41-persist-decision` to persist `merge-decision/v1` as an exact
GitHub PR comment, read the canonical body back exactly, and bind that readback in
`merge-decision-attestation/v1`. The decision digest, readback digest, durable
source event, and fresh-session ID must validate by re-reading GitHub before immediately re-querying
the exact PR tuple. A local file alone is not persistence authority.
Require the gate, handback, launcher, remote Mission Control record, host facts,
and decision to bind one actual PR and complete frozen candidate. Compare every
host-observed changed path with the envelope scope: feature planning files may
exist only under its exact planning prefix, and all other paths must equal the
approved implementation paths exactly. Any scope or risk-class drift denies.
Fresh-agent verification is the mandatory evidence floor; host checks are an
additional veto only when present. An empty host status-check rollup therefore
means only that no failing check was reported; do not create a synthetic status.
Every reported check must resolve exactly to `SUCCESS`, and the PR must
separately remain open, non-draft, `MERGEABLE`, and `CLEAN` before decision and
dispatch.
Merge only with the declared method and expected head. Observe before any retry
after an ambiguous response. Before the host call, atomically claim the
full-decision-digest operation ref; an existing ref forbids redispatch. Persist
`process-attested-merge/v1` afterward.
Candidate edits to the policy cannot authorize themselves.
Any timeout or failed dispatch remains ambiguous even if an external merge of
the expected head is later observed; never attribute that merge to this agent.

Protected/risky paths, unresolved taste or safety, auth, secrets, privacy,
billing, migrations, deployment, delivery-policy changes, or repository admin
always route to human merge. Every decision and merge receipt states
`process_attested_only: true`, `non_bypass_protection: false`, and
`tier_b_authority: false`. Stop immediately after merge; K4.1 grants no deploy,
release, closeout, cleanup, archive, Tier B, or Tier C authority.

Use `k41-decide` to produce the canonical decision. Persist every `allow` or
`deny` decision with `k41-persist-decision` and read it back. Only an `allow`
decision may proceed: validate its separate attestation before invoking
`k41-merge`. The merge command uses
GitHub's expected-head field, re-reads changed paths, unresolved review threads,
and the remote Mission Control ref, and emits the
canonical merge receipt. A persisted `deny` or an `ambiguous` outcome is a
stop, not a retry instruction.
Only the fresh session named by the decision may call `k41-merge`; a missing or
different `CONDUCTOR_SESSION_ID` fails before dispatch. Observation failure
after a host call emits an ambiguous receipt rather than losing retry state.

After a human merge, wait through the exact declared window. Accept a
`pilot-observation` V4 receipt only when this passes:

```bash
python3 scripts/deliver.py validate-observation --observation <receipt> --contract <contract> --attempt <attempt>
```

For a `process-attested:linear:<issue-id>` route, store the exact canonical
contract, attempt receipt, observation receipt, and their digests on that
canonical Linear issue. Retain the source actor, event/comment ID, timestamp,
and stable Linear locator. The observation must also carry the exact Git host
merge/release event, its canonical digest and stable locator, plus every
declared raw-evidence locator. Read the posted record back before accepting it.
Keep the provenance visibly labelled `process-attested`; it cannot satisfy a
Tier B/C protected-evidence gate. Independent maintainer replay remains
required for qualification.

Never create, backdate, or amend a contract after dispatch or merge to qualify
an earlier attempt.

All commands emit JSON with `outcome`, `next_phase`, `required_actions`, and
receipt/evidence locators. A missing registry object, unknown enum/version,
digest mismatch, dirty checker checkout, stale tuple, open finding, ambiguity,
ceiling, or exhausted fresh-checker route fails closed.

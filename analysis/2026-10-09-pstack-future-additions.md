# Pstack additions — for further exploration

**Status:** deferred exploration; no implementation selected or authorized.
**Candidates:** recurring-mistake prevention (`correct`) and performance evidence
(`benchmark-checklist`). Evaluate them independently; either may be rejected.

## Why revisit these

The October 9 source comparison found no upstream refresh required for the five
existing pstack adaptations after the Matt/glossary migration. Two newer ideas
could improve how we act on retro findings and substantiate performance claims.
This document scopes that investigation. It does not add a skill, cadence, model
choice, plugin installation or agent workflow.

Source snapshot: pstack plugin metadata `0.15.15`, immutable commit
`df581122cde17e6e27686b5a448bde23e4ad4318` (2026-10-06). The upstream repository
had no tags or GitHub releases at comparison time. Recheck the authoritative
release/tag inventory and exact source before making an adoption decision.

## A. Recurring-mistake prevention

Source: [pstack correct](https://github.com/cursor/plugins/blob/df581122cde17e6e27686b5a448bde23e4ad4318/pstack/skills/correct/SKILL.md).

### Question

Can we turn an accepted retro finding into a durable, demonstrably effective
check with less instruction growth and repeated rework?

### Candidate scope

- Gather repeated mistake classes from actual corrections, reviews and failures.
  Upstream uses two occurrences; evaluate whether that is a useful default here
  while retaining the playbook's existing incident-based promotion rules.
- Rank prevention by the strongest practical mechanism: architecture and ownership,
  types, lint/CI, behavioral tests, then prose for judgment calls.
- Prove a proposed check rejects an actual prior mistake and accepts the corrected
  behavior. Prefer existing project controls; examine false positives and upkeep.
- Treat Matt retro as a source of candidates. Stage 12 selects/presents findings;
  accepted implementation goes through stages 01–04, 07 and 08/09 as appropriate.

### Decisions to explore

1. Is a short stage-12 reference sufficient, or does a separately callable local
   skill earn its installation and maintenance cost?
2. What qualifies as recurrence, and how are one-off incidents handled?
3. What evidence justifies architecture/type changes instead of a cheaper check?
4. Where should enforcement ownership be recorded without creating a second
   hand-maintained rule inventory?

### Boundaries

Do not import automatic commits, automatic mutation after every correction,
mandatory rule tables in AGENTS.md, or blanket exception-approval mechanics.
Separate diagnosis/recommendations from scoped edits. Preserve caller authority,
report-only review, fresh verification and project customization.

### Evaluation

Use a small controlled repository with a reproducible recurring error and a
judgment-only counterexample. Compare the existing Matt retro → ordinary change
path with the proposed addition. Record the prevention mechanism, failing and
passing evidence, false positives, added instruction size and maintenance work.
Recommend adoption only if it adds observable value beyond current guidance.

## B. Performance evidence checklist

Source: [pstack benchmark-checklist](https://github.com/cursor/plugins/blob/df581122cde17e6e27686b5a448bde23e4ad4318/pstack/skills/benchmark-checklist/SKILL.md).

### Question

Can an optional checklist reduce unsupported speedup/regression claims without
adding work to changes that make no performance claim?

### Candidate scope

- State the performance claim and inspect what the measurement actually times.
- Confirm useful work ran, outputs are correct, and errors/retries are counted.
- Check limiting resources, representative configuration and data, machine noise,
  repeatability, and relevance to the user's end-to-end experience.
- Distinguish a requested rough estimate from a comparison used to choose an
  implementation. Report faster/slower/no measurable difference/inconclusive
  with units, run counts, spread, conditions and limitations.
- Consider a reference reached from implementation, review and QA only when
  performance evidence is part of the selected task.

### Decisions to explore

1. Is a stage reference, optional skill or project-owned benchmark template best?
2. Which checks are essential for a claim, and which depend on its risk and scope?
3. How should noisy hosts, inaccessible production settings and small samples
   narrow a claim rather than prompt invented certainty or endless reruns?
4. Can the existing benchmark/harness provide the evidence without new tooling?

### Boundaries

Keep measurements bounded and use synthetic/non-sensitive data. Adapt upstream
process inspection to the playbook's privacy rules: inspect known processes with
safe selectors rather than exposing command lines or environment values. Do not
install profilers, change production settings or broaden network access implicitly.
Preserve declared time/cost limits and evidence locations. No universal benchmark
requirement, automatic tuning, or performance target is introduced.

### Evaluation

Use a controlled benchmark with a genuine effect, a no-op/error-fast result and
an inconclusive noisy comparison. Require correct classification and retained raw
runs. Compare conclusions and effort with current review/QA guidance. A benchmark
result qualifies only its tested revision, inputs, settings and environment.

## Exploration deliverables and decision gate

For each candidate, produce:

- A comparison with existing playbook behavior, with a concrete gap or redundancy.
- The smallest proposed integration and its invocation, authority and output rules.
- Controlled positive and negative evidence, limitations and estimated upkeep.
- An explicit **adopt / adapt / defer / reject** recommendation with reasons.

Return those findings for a human decision. An adoption decision starts its own
alignment/spec/slices and independent review; this exploration is not build-ready.
Do not select consuming projects or claim live host qualification from fixtures.

## Future updates and customization

Recheck upstream before exploration, before any adoption release, and under the
existing monthly maintenance cadence (next recorded comparison: 2026-11-08).
Compare the full selected skill and references, invocation policy, helper/model
assumptions, license and host compatibility. Use an immutable source identity if
no tagged release exists. Preserve attribution and separate source inspection
from installed-host qualification.

Any adopted local adapter uses a distinct name, recorded source provenance and
base-aware bootstrap/upgrade handling. Review conflicts with customized files;
never replace project rules, checks or model preferences merely to match upstream.

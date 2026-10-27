# Field report — Cloud skill provisioning

Project: public Agentic Engineering Playbook maintainer repository.
Edition: V0.5; installed consumer release: n/a, maintainer source.
Period: 2026-10-24 through 2026-10-27. Seven slices shipped in PR #48,
with S7 limited to selected maintainer routes. Consumer release proof is pending.

## Observational eval baseline

| Period | Slices shipped | Rework rate | Time-to-merge (med/max) | Verifier passes | Catches |
|---|---:|---|---|---|---|
| 2026-10-24 → 2026-10-27 | 7 (S7 selected maintainer scope) | unavailable — passed-gate timing is not normalized per slice | 54h 53m 57s / 54h 53m 57s (one feature PR) | 4 sampled; total unavailable | 2 sampled passes with confirmed medium+ catches; total unavailable |

Feature-level timing replaces per-slice timing. The four sampled attempts are
S3/S4 standards, the final A8 recovery review and the final feature review;
S3/S4 independently executed medium+ findings. These are sampled counts,
not complete-period denominators. See the
[retro](../../planning/retros/2026-10-27-cloud-skill-provisioning.md) for provenance.

## Proof events

### 1. Independent verifier caught a real defect

On 2026-10-25, S3 standards execution demonstrated that default discovery
could launch a configured Git fsmonitor helper and change skill files. The
public CLI reported no changes despite the side effect. A process-local
fsmonitor-disabled control preserved the snapshot. Severity: medium/P2.
S4 standards execution also found medium/P2 hangs on FIFO launcher and proof
endpoints: both independent CLI probes timed out without a JSON repair report.
Later fixes reject those endpoints before reading. Fresh verification followed.
Self-review might have caught them, but the original passing suites did not;
the executed adversarial probes materially expanded coverage.

### 2. A run-level ceiling tripped and paused correctly

The first Cloud round used its four workspaces and eight sessions. Continuation
used a separately approved round instead of resetting the old count. This is
session/workspace ceiling evidence, not proof of a cost-metering or watchdog
implementation. The later local round used 10 of 16 sessions and 60 of 120
execution units; the ceiling was not reached there.

### 3. Acceptance-criteria gate refused a build

None observed in the reviewed records. Refusing incompatible `code-review`
or an unqualified source audit is not a stage-07 missing-criteria refusal and
is not counted here.

### 4. Structured escalation instead of thrashing

The third cumulative startup failure stopped dispatch. The report identified
missing startup outputs, successful manual hook execution, unavailable host
logs and a bounded hypothesis about setup activation. The human approved one
controlled retry with a temporary exact-commit Setup setting. That startup
worked; continuation, restoration of the temporary setting, and later durable
activation each retained their own authority and readback evidence. No new
product fix was invented to explain an unobserved host internal cause.

## Friction

Repeated handoffs mixed lifecycle status with accepted evidence; archived build
plans still contained pending-final-review language after the final review had
passed. Durable closeout now points to exact merged-tree and gate receipts.
Requiring publication before real consumer acquisition is useful evidence
separation, but it leaves a visible post-release follow-up that must not vanish
when the maintainer feature is archived. Same-name skill precedence and limited
host logs created real investigation work. No cadence-dismissal evidence exists.

## Verdict

The controls caught real defects and bounded retries. Preserve the current
independence, exact-source and cumulative-limit rules. Collect more evidence
before broader claims or new global requirements. Future qualification should
close observer stdin, compare full-precision metadata within one process, and
budget from native runtime receipts. The durable setup wrapper's guard fixtures
and live hook matrix remain distinct evidence. No autonomous merge qualification
or consumer runtime support is inferred from the human's merge.

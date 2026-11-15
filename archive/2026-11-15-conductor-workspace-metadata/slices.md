# Conductor workspace metadata — proposed breakdown

Status: shipped in PR #58 as `4dd4f1a`; independent review and final gates passed.

## S1 — Setup remains usable without an optional workspace name

Type: AFK. Depends on nothing after specification/breakdown acceptance and the
Build selection. Outcome: maintainers can follow accurate setup guidance and
run regression coverage proving the existing installer tolerates all documented
identity variations while preserving existing behavior.

Scope: `v0.5/scripts/test_conductor_setup.py`, the existing
`v0.5/scripts/skill-provisioning.md` guide, bootstrap/upgrade skill guidance and
migration reference, scoped qualification documentation, glossary, changelog,
planning status and affected generated outputs. Keep production installer
interfaces unchanged; a discovered defect requires diagnosis before a fix.

Verification target: all ten [specification criteria](spec.md), demonstrated
through the existing disposable-consumer launcher/hook/composition seams and
documentation scenarios. Explicitly exercise name+ID, ID-only, empty/whitespace
names, invalid ID and unavailable identity. Cover sh/bash and local/cloud routes
without inherited metadata concealing an omission. Existing command-failure,
pin and customization checks remain authoritative.

Receipt-required refusal and later host comparison are documented external
contracts; they are not implementation claims about the independent installer.
Publish a clear limitation when the actual external repair or live evidence is
unavailable. Do not replace missing real-route proof with a fixture checker.

Review/QA: fresh independent standards and spec review with executed evidence,
including missing-coverage and privacy checks. Run focused setup/documentation
checks during iteration; run the full canonical verifier on the final shipping
candidate. No live setup/settings changes or publication are part of this slice.

Progress: use a scaled estimate of 60–100 calls for this slice and its focused
review, plus 20–40 for final verification coordination. Report revisions when
evidence changes; these are checkpoints, not hard caps. Stop on user Stop,
actual quota/selected hard limits, three identical failures or three no-progress
iterations. No new paid runner, model substitution or live qualification is
implicitly approved. Preflight the selected fresh verifier before relying on it.

## Separate qualification follow-up

HITL / external evidence; not an extra automatic Build slice. Requires the
published consumer repair, effective saved setup command, bounded authority for
a fresh automatic setup run and host workspace readback. Its outcome is a
scoped support claim or a named remaining limitation, never a retroactive
rewrite of historical results. It does not block shipping this reviewed
guidance/test improvement under the confirmed alignment.

## Implementation notes

The new regression locks existing behavior; no production installer change was
needed. Initial test-harness failures exposed terminating-command adoption
guards, multiline JSON and the intentional local discovery-only result. The
fixture now uses a returning project helper, parses the complete JSON payload,
and checks discover/install separately. These are harness corrections, not
installer fixes. The metadata matrix includes nine cases over both host modes
and available sh/bash shells, with child exit 7 and unchanged state checks.

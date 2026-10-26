# Cloud skill provisioning — runtime qualification

Status: **partially qualified; S7 remains open**. Live maintainer-candidate
qualification ran on 2026-10-26. Manual Cloud installation and Codex invocation
passed the bounded checks below. Automatic startup and Claude Code discovery
did not pass. Fixture success does not qualify the remaining runtime matrix.

## Candidate and scope

The first two Cloud workspaces tested `4c1e02e` and found that the setup hook
required Python 3.10 while Cloud supplied 3.9.25. Commit
`01170f1b8db5fc7bc6119085430cd0ea450fac50` lowers the execution gate to 3.9.
Fresh independent review passed with no findings: 34 setup, 33 provisioning
and 10 recovery tests passed without skips, including execution on Python
3.9.6 and independent failures of both new regressions against the old hook.
The canonical verifier passed the fix's exact tree
`3367f67fbf2f13740227716a473cc01f5dbe9566` before commit and push.
Explicit setup configuration composition still requires Python 3.11+.

The two fresh reruns used that exact commit, Conductor CLI 0.92.0, Python
3.9.25 and the unchanged reviewed skill bundle v1.3.1 at upstream commit
`24fe0ef7737efae15c87225755e9f6f5965e4888`:

| Runtime | CLI version | Selected model | Effort |
|---|---|---|---|
| Claude Code | 2.1.308 | `opus-5-5-1m` | high |
| Codex | 0.164.0 | `gpt-6.1-sol` | high |

These are dated observations, not new default model choices or a general
compatibility promise. The approved ceiling was four Cloud workspaces, eight
sessions, 120 minutes and 60 agent turns. All four workspaces were used and
archived. Counting the fresh local fix reviewer conservatively, eight sessions
were used; follow-up turns reused the two rerun sessions. Raw transcripts and
host receipts remain private; this report contains the sanitized findings.

## Observed results

| Check | Claude Code Cloud | Codex Cloud |
|---|---|---|
| Fresh-start provisioning | No installation state, canonical skill directories or aliases when the agent began; no project runtime catalog entries. | Same missing provisioning outputs; runtime catalog contained only four system skills. |
| One manual setup execution | Exit 0, complete inventory: 11 skills and 11 directory aliases; provisioner check passed; Git clean. | Same result on Python 3.9.25. |
| Discovery after that install | Native `Skill(tdd)` and `Skill(grill-with-docs)` returned `Unknown skill`, including on the next turn. | Next turn's runtime catalog selected all seven model-invocable project skills. |
| `tdd` and supporting file | Manual reads succeeded; native invocation failed. | Next-turn catalog selected the project source; its instructions and `tests.md` loaded successfully. |
| Explicit user-only `grill-with-docs` | Native call failed; manual reads of it and its dependencies are file-access evidence only. | A subsequent explicit `$grill-with-docs` turn injected the project skill; its selected instructions and project `grilling`/`domain-modeling` dependencies loaded, then the first naming question was produced. |
| Embedded `code-review` | Exact-source gate refused with exit 2, `incompatible`, `may_invoke=false`; explicit manual fallback selection exited 0 and launched nothing. | Same expected refusal and fallback selection. |

The startup observation establishes that automatic provisioning was not ready
when the agents began. It does **not** establish whether the hook was skipped,
failed or ran at another time: host setup execution logs were not available in
this evidence. Manual installation success does not repair that startup verdict.
Claude's failure after a later turn also does not establish what a new session
started after installation would discover; that check was not run.

Codex uses a runtime-selected instruction source loaded through file reads;
a dedicated `Skill` tool is not required for that mechanism. The initial
reads, before runtime catalog selection was demonstrated, were manual access
only. Earlier slash-form grill prompts did not prove explicit loading. The
correct dollar-form invocation did, consistent with
[OpenAI's invocation policy documentation](https://learn.chatgpt.com/docs/build-skills#optional-metadata).
Both invocation-policy files retained the user-only controls. The four
user-only skills stayed out of Codex's model-invocable catalog; only
`grill-with-docs` received this explicit invocation check. No glossary, ADR or
application code was written. A runtime catalog entry for `code-review` grants
no permission to bypass its incompatible-source gate.

## Local results and incomplete coverage

Local maintainer setup exited 0 without changing skills or discovery wiring.
The bounded local Claude Code coexistence check saw both project and personal
copies and selected the personal copy when invoked by name. Project-file
access succeeded by explicit path. Record this as observed precedence for that
run, not proof that a project alias controls duplicate-name selection.
Local Codex was blocked by account/model rejection before skill qualification.
No login or global configuration was changed.

The full S7 acceptance matrix is incomplete:

- Recreated Cloud workspaces and retained-customization restoration were not
  run: all four approved workspace slots were consumed by the initial failures
  and fresh reruns.
- Claude discovery in a fresh session after successful setup remains untested.
- Local exact/newer/customized/absent/duplicate/changed-source coverage is
  incomplete, and local Codex remains blocked.
- The consumer exact-release path remains deferred until a release includes
  the bundle; these maintainer-candidate runs claim no consumer provenance.
- Other skills' actual invocation behavior is not established by their
  installation or catalog presence.

## Next qualification step

First obtain host setup execution evidence for the fresh-start failure and
verify the order of checkout, setup and agent startup. Reproduce and repair the
identified cause before spending another fresh-workspace run. Under renewed
live-run capacity, check both runtimes from startup, then the recreated and
local matrix cells above. Use explicit `$skill` syntax for Codex user-only
skills and capture the source selected by the runtime before manual reads.
Preserve the review refusal and stage-owned fallback during every rerun.

Follow the existing monthly upstream review, and requalify affected contracts
before deliberate runtime, model, settings or skill-source migrations. Preserve
customizations and existing source pins. See the
[provisioning guide](../../v0.5/scripts/skill-provisioning.md) and
[S7 acceptance criteria](slices.md#7-qualify-actual-runtime-discovery-and-invocation).

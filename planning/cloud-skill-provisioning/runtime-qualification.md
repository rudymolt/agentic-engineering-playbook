# Cloud skill provisioning — runtime qualification

Status: **targeted fresh/recreated Cloud checks passed with an explicit Cloud
repository Setup setting; S7 remains partially qualified**. The maintainer-candidate
runs on 2026-10-26 establish the selected setup route, runtime source loading and
retained-customization restoration. They do not qualify branch-TOML activation,
the full local coexistence matrix, or consumer release recovery.

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

The successful startup round used candidate
`6e8d31147abb725333b460261067273551b9499e`, Conductor CLI 0.92.0, Python
3.9.25 and the unchanged reviewed skill bundle v1.3.1 at upstream commit
`24fe0ef7737efae15c87225755e9f6f5965e4888`:

| Runtime | CLI version | Selected model | Resolved model | Effort |
|---|---|---|---|---|
| Claude Code | 2.1.308 | `opus-5-5-1m` | `claude-opus-5-5[1m]` | high |
| Codex | 0.164.0 | `gpt-6.1-sol` | `gpt-6.1-sol` | high |

These are dated observations, not new defaults or a general compatibility
promise. The initial round used and archived four workspaces and consumed its
eight-session ceiling. A separately approved second round kept the same ceilings:
four workspaces, eight sessions, 120 minutes, 60 agent turns, and a stop after
three identical failures. The third cumulative startup failure triggered that
stop; the human approved one controlled retry, then continuation on the successful
setup route. The second round used four workspaces, six sessions and seven
submitted user turns. Native runtime accounting is different: Claude reports
38 turns; Codex records 18 command cycles across three completed user turns.
A conservative combined execution count is 59; no further agent dispatch followed.
All test workspaces are archived. Raw transcripts, identities and host receipts
remain private; this report contains sanitized findings.

## Startup diagnosis and selected setup route

The two initial reruns on the Python fix started without provisioning state,
canonical skill directories or aliases. One manual hook execution installed all
eleven skills and aliases in each workspace, with clean Git state. On a later
turn Codex discovered seven model-invocable project skills and loaded `tdd`;
explicit `$grill-with-docs` loaded its dependencies. Claude native invocations
still returned `Unknown skill`, including on a later turn. A second-round
observation at `6e8d311` again found startup outputs missing and stopped without
repair.

The controlled retry temporarily set the Cloud repository's **Setup script**
field to run `sh v0.5/scripts/conductor-setup.sh --candidate` only when HEAD
matched the reviewed candidate. This produced installation state and all eleven
aliases before Claude initialized. Native `tdd` loaded successfully. The subsequent
fresh Codex workspace reproduced startup readiness; a new Claude session in that
workspace confirmed the complete targeted invocation sequence.

This narrows the problem to host setup selection/activation. It does **not** prove
which settings layer took precedence, whether the host selected the default
branch, or a particular internal host defect. Direct host setup logs and exit
status were unavailable. The host UI lacked a Setup tab even for the successful
retry, so absence of that tab is not evidence that setup did not execute.
No source-code change was justified by this experiment.

The temporary setting was pinned to the retained fixture commit for the final
recreation, then restored to its original empty value and verified by navigation
and readback. The successful setting is **not permanently enabled**. Branch-TOML
activation remains unqualified; do not promise equivalent behavior with only the
tracked `.conductor/settings.toml` present.

## Successful targeted Cloud matrix

All four cells below used automatic provisioning through that explicit Setup
setting. Observers did not run setup or installation to repair startup.

| Runtime and checkout | Startup and inventory | Selected source and explicit invocation | Review boundary |
|---|---|---|---|
| Fresh Claude Code | 11 installed; initial catalog exposes 7 model-invocable skills. | Native `Skill(tdd)` and `Skill(grill-with-docs)` load project sources; native `grilling` and `domain-modeling` dependencies load. | Exact-source refusal and explicit manual fallback pass. |
| Fresh Codex | Same installation and initial 7-skill catalog, before manual reads. | Explicit `$tdd` and `$grill-with-docs` select project sources; both grill dependencies load through the runtime's file-based mechanism. | Same expected refusal and fallback. |
| Recreated Claude Code | 10 installed plus retained TDD `customized`; all 11 aliases restored. | Native TDD injection includes the retained instruction; its marker and full references are read. Explicit grill and both dependencies load. | Same expected refusal and fallback. |
| Recreated Codex | Same restored inventory and catalog. | Runtime-selected TDD contains the retained instruction; marker and full references are read. Explicit grill and dependencies load. | Same expected refusal and fallback. |

Each complete observation read both `tdd/tests.md` and `tdd/mocking.md` in full.
The earlier controlled retry read only the first 20 lines of `tests.md`; its hash
check did not establish a full read. Each complete observation produced the first
interview question for the disposable todo example. No application, glossary or
ADR changes were made during these invocations.

Claude selected `.claude/skills/<name>` aliases resolving to the canonical
`.agents/skills/<name>` directories. Codex advertised those canonical project
sources before manual reads and used its supported file-loading mechanism;
a dedicated `Skill` tool was unavailable. Explicit dollar syntax supplied the
user-only Codex skill. Claude's user-only native call was made at the explicit
user request; it is not evidence of implicit invocation permission or enforcement.

Both metadata formats preserved the four user-only entries: `grill-with-docs`,
`setup-matt-pocock-skills`, `to-spec` and `to-tickets`. Those four were absent from
the default model-visible catalogs. Only `grill-with-docs` received the explicit
user-only invocation check; installation/catalog evidence does not establish
all other skills' behavior.

Every review compatibility check exited 2 with exact matching source hashes,
`incompatible` and `may_invoke=false`. Explicit `fallback` selection exited 0,
selected the stage-08 manual standards/spec route and launched nothing.
`code-review` was never invoked. A catalog entry grants no review authority.

## Retained-customization recreation

The fresh workspace committed a complete six-file TDD directory, including a
small added reference and an instruction to read it, then used the public
`retain --skill tdd` command and committed the portable retention record. Both
commits used noreply author and committer identities. The source workspace was
archived before a new workspace checked out fixture commit
`845885288f7f5687f5a82ad6c15f50977bf8125e`.

Independent inspection of the pushed fixture confirmed that only the complete
TDD directory and `.agents/.skill-provisioning/retained.json` differed from
`6e8d311`; provisioning code and the bundle were unchanged. No installation
state or working history was tracked. LICENSE, invocation metadata and both
existing references matched the bundle. The fixture remains isolated from the
feature branch.

In the recreated checkout, `check` exited 0 with `complete: true`, ten skills
`installed`, TDD `customized`, and no retention error. All six actual TDD file
hashes matched the tracked retention record. Both runtimes loaded the added
instruction and read marker `S7_RETAINED_TDD_2026_10_26`. The changed entrypoint
hash was `15c6b77a5ef8b858008bc02174b3f813e9cf338f4d7d5e92722c8ad8b17f97cd`;
the new reference hash was
`510e7920148d1970786c1ad9525c1c54cadc3146b359afa096a99b25467739c8`.
This qualifies restoration and source loading of these bytes, not general
embedded compatibility of customized skills. Reports correctly retained their
separate bundled and installed integrity records and `qualification: unverified`.

Observation limits are retained rather than hidden:

- The recreated Claude observer briefly redirected check output to a scratch
  file under `.git`, then removed it. This violated its no-write brief; the run
  cannot establish whole-filesystem non-mutation. Retained files, installation
  state and final tracked content remained unchanged in the captured checks.
- Codex's first cross-command timestamp comparison suffered JSON nanosecond
  rounding. Initial hashes and aliases matched; initial timestamps matched only
  at transport precision. A later in-process before/after comparison around the
  review refusal and fallback proved exact unchanged hashes, mtimes and aliases.
- Runtime receipts, rather than worker prose, supply execution counts. The
  fresh and recreated Claude observers exceeded their requested per-observer
  targets; the round's approved cumulative ceiling was not exceeded.

## Remaining S7 work

Local maintainer setup previously exited 0 without changing skills or discovery
wiring. The bounded local Claude duplicate check selected the personal copy by
name; project-file access succeeded by explicit path. Keep this as a precedence
limitation, not proof that aliases control duplicate-name selection. Local Codex
remains blocked by the observed account/model rejection; no login or global
configuration was changed.

The full local exact/newer/customized/absent/duplicate/changed-source matrix
remains incomplete. Consumer exact-release recovery remains deferred until a
release includes the bundle; maintainer-candidate runs claim no consumer
provenance. These gaps keep S7 open. A permanent host setup configuration still
needs deliberate selection; the temporary successful route was restored, and
the branch-TOML path remains unresolved.

Review this evidence update, retain the remaining gaps, and follow the normal
final-candidate verification and review gates before shipping. Follow the existing
monthly upstream review; before deliberate runtime, model, settings or source
migrations, requalify affected contracts while preserving customizations and pins.
See the [provisioning guide](../../v0.5/scripts/skill-provisioning.md) and
[S7 acceptance criteria](slices.md#7-qualify-actual-runtime-discovery-and-invocation).

# Cloud skill provisioning — runtime qualification

Status: **selected maintainer Cloud and local routes qualified; consumer release
qualification deferred**. The 2026-10-26 runs establish fresh/recreated Cloud
startup through the explicit repository Setup setting, retained customization,
and bounded local source selection/refusal. The approved durable Cloud setting
is now enabled. Branch-TOML activation and default project precedence under
personal-name collisions remain unqualified. These are scoped observations,
not universal runtime or embedded-skill compatibility claims.

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
recreation, then restored to its original empty value. The human subsequently
approved permanent Cloud repository setup. The saved setting now runs the
checked-out `v0.5/scripts/conductor-setup.sh --candidate` through `sh` when that
file exists; older revisions report that provisioning is unavailable and exit 0.
Navigation away and back confirmed the exact saved value. Local repository
settings were unchanged. Guard fixtures passed older-revision skip, hook success,
and hook exit-2 propagation. No additional Cloud workspace tested this conditional
wrapper; the same hook/argument is covered by the successful live matrix.
Branch-TOML activation remains unqualified; do not promise equivalent behavior
with only the tracked `.conductor/settings.toml` present.

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

## Bounded local qualification

A separately approved local round allowed 16 sessions, 120 active minutes and
120 agent turns/tool cycles, stopping after three identical failures. It used
10 sessions, 60 conservative runtime execution units and less than 20 elapsed
minutes, with zero additional Cloud workspaces. Claude's nine native receipts
account for 45 turns; the one Codex session accounts for 11 tool calls and four
completed user turns. No personal skill, login or global-setting change occurred.

The local candidate was `8d949d6d61218c9b583bdadfa80c742d67c9a10e`.
Claude Code CLI 2.1.284 used `claude-opus-5-5` at high effort. Conductor-hosted
Codex 0.164.0 used `gpt-6.1-sol` at high effort. Native runtime metadata supplies
these identities. The supported Conductor route succeeded despite the earlier
standalone Codex account/model rejection; that failing route was not retried.

| Local source case | Claude Code | Conductor-hosted Codex |
|---|---|---|
| Exact | Process-local project-only settings expose `tdd`; native Skill loads the project alias and full references. | Explicit project path loads and applies the exact entrypoint and full references. Default catalog still names the personal source. |
| Newer | Native project-only invocation loads the clean upstream successor and full references. | Explicit file-based invocation loads and applies that same successor and full references. |
| Customized | Native project-only invocation loads the changed entrypoint and added reference. | Explicit file-based invocation loads the changed entrypoint and added reference. |
| Absent project source | Project-only catalog lacks `tdd`; invocation is refused without substitution. | Missing explicitly requested project path is refused; no personal source is applied. |
| Duplicate | Normal user/project lookup selects the personal copy; project aliases do not control precedence. | Catalog/payload names the personal copy; public discovery reports competing project/personal sources and no project route is inferred. |
| Changed selected source | An independently audited custom execution selection loads through the stage gate; after controlled drift, the same selection is refused before application. | The same before/after sequence passes through the public stage boundary and exact-source accessor. |

The newer source is a clean upstream descendant at
`5beb35b040e3de97e54fa9e386d7e42d15c295c2`; its entrypoint hash is
`5505d25bbaa8fc14a79e4d20163936958992a2995b7f1dd1d6197edc9ed722e0`.
The customized entrypoint hash is
`407bc249b44a1d8d6f8c9483d30b7c61a4b0134e8aee2c46529aa349c96d6626`;
both runtimes read its required marker `LOCAL_TDD_CUSTOM_2026_10_26`.
Each positive invocation applied the selected instructions to a one-test
`add(2,3) == 5` red-to-green plan. No test or implementation was executed;
these tasks qualify source loading and application only.

Public default discovery retained the actual personal collisions in every case:
one readable source and one unresolved entry. Overall status therefore remained
`duplicate`, even when an individual project source was correctly classified as
exact, newer or customized. Absence means **project-source absence**, not an
empty personal installation. Project-only Claude settings affect that process's
native catalog; they do not hide personal roots from the provisioner. Codex's
explicit file-loading result is not proof of automatic catalog selection.
Unresolved same-command job routes remain blocked; these observations grant no
embedded stage eligibility to bundled or newer TDD.

The drift test used a separately authored, disposable custom implementation
fixture outside registry discovery roots. A fresh source-contract audit rejected
using the original TDD source as a stage-owned route; a fresh audit then passed
the bounded custom fixture with stage authority retained. The coordinator bound
its exact bytes to that real audit and retained a separate approved execution
selection for each runtime. Public `job-route` and the stage's `invocation_source`
accessor resolved the same selection before loading. After only the selected
entrypoint changed, `job-route` exited 2, reported `blocked` and `launched: false`,
and neither runtime applied the changed or remembered source. This tests retained
execution selection, not project preference adoption or generalized eligibility.

Both runtimes also observed exact-source `code-review` refusal (exit 2,
`incompatible`, `may_invoke: false`) and explicitly selected the manual fallback
(exit 0). The fallback response omits `launched`; native traces establish that
no reviewer ran. Repeated discovery and gate probes preserved protected bytes,
modes, nanosecond mtimes and aliases. The coordinator's default-discovery check
compared 361 entries; Codex's repeated case checks compared 125 protected entries.
Before/after personal skill and settings hashes matched. These checks exclude
unrelated home files and do not claim whole-filesystem non-mutation. The Cloud
pin remains v1.3.1 at `24fe0ef7737efae15c87225755e9f6f5965e4888`.

One observation defect is retained: the first Claude exact-source launcher
inherited its parent's stdin, so launcher text appeared after the prompt. The
observer declined to execute that text; native source/reference reads still
occurred. Subsequent launches used closed stdin. Observer self-reported turn
counts were not used for budget accounting.

## Release follow-up and support limits

S7's selected maintainer paths now have actual runtime evidence. Consumer
exact-release recovery remains deferred by agreement until a published release
contains the bundle; maintainer-candidate runs establish no consumer provenance.
Keep that release follow-up open and requalify before claiming consumer support.
Do not claim branch-TOML-only startup, automatic project precedence under
collisions, globally absent local skills, standalone Codex login repair, or all
bundled skills' behavior from this matrix.

Complete normal final-candidate review, privacy/attribution and full verification
before shipping the PR. Follow the existing monthly upstream review; before
deliberate runtime, model, settings or source migrations, requalify affected
contracts while preserving customizations and pins. See the
[provisioning guide](../../v0.5/scripts/skill-provisioning.md) and
[S7 acceptance criteria](slices.md#7-qualify-actual-runtime-discovery-and-invocation).

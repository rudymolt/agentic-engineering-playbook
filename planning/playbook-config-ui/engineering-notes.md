# Configuration planning — current integration evidence

These are source locators inspected while drafting the specification, not promises that the present code already supports configuration. Subsequent build-all approval and current progress are recorded in [execution status](execution.md).

| Surface | Current source | Consequence for the feature |
| --- | --- | --- |
| Defaults and runtime selections | `v0.5/templates/.playbook-state.yml` | `model_routing.defaults` holds four role defaults; pending and feature routes are separate. Import defaults without changing runtime records. |
| Lane gates and launch identity | `v0.5/93-model-routing-track.md`; `v0.5/skills/model-router/SKILL.md` | Currently teach edition defaults and feature-scoped `openai defaults`. Update all default consumers consistently while preserving explicit selection, discovery and identity checks. |
| Skill provenance | `v0.5/upstream-skills.json`; `v0.5/scripts/upstream_registry.py` | Provides collection identities and categories; categories are not job-binding contracts. |
| Exact-source embedded checks | `v0.5/upstream-integrations.json`; `v0.5/scripts/check-upstream-compatibility.py` | Existing compatibility decisions include source hashes, permitted/prohibited effects and fallback routes. Reuse rather than bypass. |
| Bootstrap and upgrades | `v0.5/scripts/bootstrap-project.py`; `v0.5/scripts/upgrade-project.py` | Integrate managed-file adoption and preserve customised state; do not introduce an unrelated updater. |
| Test patterns | `v0.5/scripts/test_bootstrap_project.py`; `v0.5/scripts/test_upstream_compatibility.py` | Reuse temporary-project and command-level behavioural testing patterns. |
| Prototype evidence | `.lavish/playbook-config-ui-mockup.html` (local review artifact) | Demonstrates the approved conversation, skill source prefixes and replacement acceptance. It is not production implementation or host proof. |

Before implementation, inventory every consumer of legacy model defaults and skill invocations. The specification's precedence rule must apply across bootstrap, upgrades, lane prompts, feature-scoped overrides and delivery entry points; a new settings file alone cannot complete the feature.

## Planning checks

- Scope-guardian: completed as a bounded specification review; no separate skill with this name was located in the installed catalogue. Result recorded in the specification.
- Coherence: checked against `CONTEXT.md`, alignment and chat flow; draft decisions and remaining engineering review points are labelled.
- Runtime-state update: n/a for this maintainer planning checkout; no `.playbook-state.yml` exists. Track the feature in `planning/STATUS.md`; do not bootstrap the repository merely to record this draft.
- Tracker publication: local planning documents only, consistent with the authorised planning scope. No remote issues, commits or pull requests created.
- Implementation slices: eight approved slices, with the criteria in the public [breakdown](slices.md). The later build-all S1–S7 handoff supersedes the planning-time unselected build scope; progress is tracked separately.

# Agentic Engineering Playbook

Terms for skill provisioning, agent authority, capability evidence, and work
that can continue while a dependency is blocked.

## Language

**Capability evidence**:
Observed evidence that the intended tool or runner can perform a required
action against the intended target under the required constraints. It is
distinct from the user's authorization to perform that action.

**Existing authorization**:
The user's already-given authority for an operation within its stated scope,
target and effects, including necessary constituent steps covered by that
operation. It is distinct from possession of credentials or tool access.

**Independent work**:
Work whose correctness and authorized effects do not depend on a currently
missing capability or unresolved decision.

**Isolated restore verification**:
Restoring an identified recovery point into an isolated disposable target and
checking that the affected data/schema is usable. Successful backup creation
alone does not establish this evidence, and verification does not authorize a
restore against live data.

**Recovery coverage**:
Evidence that the recovery method covers the actual pre-change state and
preserves or can replay intervening writes. A recent backup timestamp alone
does not establish coverage.

**Skill inventory**:
The selected set of skills a project expects, including their required skill
dependencies and supporting material.
_Avoid_: All skills, optional package collection

**Provisioning**:
Preparing a workspace with its adopted skill inventory and the discovery
connections required by its supported agent runtimes.
_Avoid_: Invocation, upgrade

**Installed skill**:
A skill whose required files are present in the workspace. Installation alone
does not establish runtime discovery or permission to use it.

**Discoverable skill**:
An installed skill that the active agent runtime exposes through its supported
discovery mechanism.
_Avoid_: Usable skill

**Compatible skill**:
A skill whose reviewed source and behavior meet the requirements of the
selected runtime and the owning playbook stage.
_Avoid_: Installed skill, discoverable skill

**Customized skill**:
A skill with project- or user-owned changes relative to its adopted upstream
source.
_Avoid_: Corrupt installation, disposable copy

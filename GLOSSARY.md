# Playbook skill provisioning

The language used to describe skill availability in projects that adopt the
playbook. Availability is specific to a workspace, an agent runtime, and the
playbook stage that would use the skill.

## Language

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

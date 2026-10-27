# Maintainer decisions

- [Checkpoint fixture ownership and measured acceptance](adr/0001-checkpoint-fixtures-and-acceptance.md)
- [Release-bundled project skill inventory](adr/0002-release-bundled-project-skills.md)
- [Cloud and local skill qualification](cloud-skill-provisioning/runtime-qualification.md)
- [Consumer release qualification follow-up](cloud-skill-provisioning/consumer-qualification.md)
- [Checkpoint performance measurements and limits](../bench/test-runtime/CHECKPOINT-PERFORMANCE.md)

Release consumers stay pinned to a tag. Recheck compatibility when the relevant
Git/Python versions, runner image or capture source changes; preserve project
customizations during upgrades. These records document the retained behavior,
not permission to weaken tests or add a new optimization experiment.

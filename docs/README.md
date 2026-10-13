# Maintainer decisions

- [Checkpoint fixture ownership and measured acceptance](adr/0001-checkpoint-fixtures-and-acceptance.md)
- [Checkpoint performance measurements and limits](../bench/test-runtime/CHECKPOINT-PERFORMANCE.md)

Release consumers stay pinned to a tag. Recheck compatibility when the relevant
Git/Python versions, runner image or capture source changes; preserve project
customizations during upgrades. These records document the retained behavior,
not permission to weaken tests or add a new optimization experiment.

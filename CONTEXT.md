# Playbook vocabulary

## Edition

A versioned, self-contained tree that a project uses for its agent workflow. This public repository starts with V0.5.

## Stable checkout

A local clone pinned to a released tag. Application projects point here until their owners choose an upgrade.

## Development checkout

A separate local clone used for public `main` and feature-branch work.

## Managed file

A project file installed from a playbook template and tracked with a pristine merge base so upgrades can preserve project changes.

## Personal defaults

A person's preferred playbook settings used to initialise new projects. Applying later changes to an existing project is an explicit choice.

## Project defaults

The preferred playbook settings for one project. They are distinct from choices already made for an active feature and the record of what actually ran.

## Configuration preset

A named collection of playbook defaults that a person can use as a starting point and customise.

## Skill binding

The assignment of an eligible skill to a specific playbook job, such as alignment or code review. A job's requirements determine which skills can fill it.

## Model recommendation

A suggested model choice with an explanation of its suitability and expected cost trade-offs. It is distinct from the model selection the user has approved.

## Reviewed guidance

A provider statement about a model's task fit that a maintainer has reviewed and shipped with the edition. A live official page can confirm or withdraw it but never creates it; the playbook does not infer task fit from provider prose.

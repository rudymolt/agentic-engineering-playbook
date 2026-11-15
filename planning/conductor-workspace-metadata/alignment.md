# Conductor workspace metadata — alignment

Status: alignment confirmed on 2026-11-15; specification and single-slice Build accepted; shipment and merge authorized.

The owner confirmed that a missing workspace display name must not block setup,
that missing required identity must produce a clear safe failure, and that
installation and automatic-startup qualification are separate outcomes. Routine
engineering details belong to the agent; human questions use plain language.

## Agreed decisions

1. Publish reusable guidance and regression coverage through existing setup
   routes. Do not introduce a parallel installer or a maintained receipt
   writer/checker in this repository. The consumer repair remains separately
   owned and is reviewed as external evidence once published.
2. Display names are optional. New qualification requires a valid workspace ID
   matched with the actual host workspace record. Neither a name nor a UUID's
   format alone proves workspace binding. Preserve historical claims' scope.
3. A consumer wrapper that requires a receipt stops preparation before running
   child commands when its ID is absent, blank or malformed. Report setup as
   not run and name the missing requirement without printing private values.
   Missing names never block it. The standalone installer needs no such ID.
4. Validate the captured ID's format during receipt preparation; compare it
   with the host record during qualification. Do not add API credentials or
   network requirements to setup solely for this comparison. Missing original
   identity cannot be backfilled from a later agent process.
5. Reviewed guidance and tests may ship before fresh consumer automatic-startup
   qualification. Claim affected-route startup support only after verifying the
   effective saved command and fresh automatic setup evidence. A manual run
   cannot satisfy that gate.

## Source findings

- [Shell hook](../../v0.5/scripts/conductor-setup.sh): explicit local/cloud
  dispatch, toolchain, launcher and Cloud cache requirements; no name/ID check.
- [Setup composition](../../v0.5/scripts/conductor_setup.py): requires the
  workspace path and preserves previous command failure and customized inputs.
- [Public setup entry](../../v0.5/scripts/recover-playbook-source.py): release
  and source proof are distinct from workspace identity.
- [Existing integration tests](../../v0.5/scripts/test_conductor_setup.py):
  inherit host environment; metadata cases must explicitly replace/remove it.
- [Historical qualification](../../docs/cloud-skill-provisioning/checkpoint-and-startup-qualification.md):
  bounded prior evidence remains intact, without implying support elsewhere.

The reported custom receipt failure occurred outside the Playbook installer.
The current agent process has an ID without a name; that is not evidence about
the automatic setup process. Effective original settings and startup logs are
unavailable. Private consumer details and raw host records stay outside this
public tree.

## Process record

The owner selected Plan and explicitly invoked `grill-with-docs`; its grilling
and domain-modeling procedures were followed. All five decisions above were
accepted, followed by explicit shared-understanding confirmation. The alignment
job binding returned `configured: false`; repository stage guidance governed.
The offered edition preference was GPT-6.1 Sol/high. Runtime identity was not
independently established; a preference is not execution identity evidence.

New terms are in [the glossary](../../GLOSSARY.md). ADR: n/a — these reversible
guidance and coverage decisions do not meet the hard-to-reverse criterion.
UI preview and application deployment/recovery: n/a — neither is in scope.

At the monthly upstream checkpoint (next recorded due date 2026-12-08), and
after host, skill, model or settings changes, recheck affected contracts and
compatibility. Adopt changes deliberately while preserving customizations and
recoverable prior configuration. No per-turn upstream check is added.

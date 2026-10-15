# Edition and installed release — specification

## Behavior

- `playbook_version` remains the compatible edition migration stamp. A V0.5.2
  installation continues to use `V0.5.0` for edition migration decisions.
- `playbook_release` records the exact installed release tag only when the
  source checkout or package provides verified release provenance. Otherwise
  it is `null` and user-facing output says `unknown (unverified source)`.
- The verified tag object and commit are recorded alongside a proved release.
  Warm sessions compare all three with the clean local checkout without a
  network request. Missing proof takes the cold prerequisite path.
- Stage 00 compares editions with editions. It evaluates release drift only
  from verified release evidence, never by comparing `V0.5.0` to `v0.5.2`.
- Bootstrap and upgrade preserve customisations, retain existing edition
  certification and conflict behavior, and migrate older state files missing
  `playbook_release` without fabricating a historical value.
- Patch-release upgrades update the release and cold-path trigger even when the
  edition stamp remains unchanged. A second run is a no-op.

## Test seams

Cover release proof and its unknown cases at the source-provenance helper;
bootstrap and upgrade at their existing project fixture seams; stage-00/status
wording through focused documentation and CLI output checks. Include a
V0.5.1-to-V0.5.2 style transition with edition `V0.5.0` throughout.

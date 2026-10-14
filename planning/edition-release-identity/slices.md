# Edition and installed release — slices

## S1 — prove and display installed release

Depends on nothing. Add exact release provenance resolution, a separately
validated state field, bootstrap and status behavior, and tests for a verified
tag plus missing, dirty, or unverifiable sources. Preserve the edition stamp.

Verification: focused provenance, bootstrap, state, and status tests.

## S2 — migrate upgrades and guidance

Depends on S1. Migrate existing projects and patch-release upgrades, update
stage 00 and the human-facing bootstrap/upgrade guidance, and test successful,
unknown, and blocked upgrade outcomes. Preserve customisations and no-op reruns.

Verification: focused upgrade/transition and docs checks, independent review,
privacy check, regenerated manifest, full final-candidate verifier, and both
required CI jobs before merge. The maintainer merges through review.

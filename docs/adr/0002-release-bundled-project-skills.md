# ADR 0002 — Bundle project skill inventory with the adopted release

Status: Accepted; provisioning and adoption are implemented. Selected maintainer
Cloud/local routes are qualified; consumer release qualification remains deferred.
Date: 2026-10-24

Fresh cloud workspaces cannot rely on a developer's global skill installation
or playbook checkout. Distribute the selected, reviewed skill inventory with
each playbook release, including complete supporting files, dependencies,
runtime metadata, and notices. A reusable project-scoped provisioner installs
the adopted inventory; Conductor Cloud with Claude Code and Codex is the first
rollout. Bundling ties recovery to a reproducible release and avoids a second
upstream download during setup, at the cost of maintaining the bundled source
and its attribution with each release.

If a consumer's configured checkout is unavailable, recover only its recorded
release and verify the annotated tag object and commit under the existing
[release-provenance contract](../../v0.5/scripts/release_provenance.py).
Missing proof requires explicit recovery or adoption; an older release without
the bundle requires explicit upgrade. Setup never silently selects a newer
release. Maintainer development qualification does not certify a published
consumer release.

Project customizations remain project-owned. Explicitly retained,
version-controlled skill files survive recreation and receive separate
qualification; provisioning must preserve them and never silently commit or
upload workspace edits. A failed capability retains a repairable workspace,
reports the specific repair needed, and requires explicit selection of the
existing manual fallback. Unaffected work may continue. File installation does
not establish discovery, embedded compatibility, or invocation authority.

Local setup discovers existing skills first and does not automatically activate
bundled duplicates. Preserve user installations, including newer versions;
reuse them only under the owning stage's requirements and any saved binding.
A newer version is a review candidate, not proof of compatibility or a reason
to downgrade. Project bundle activation and newer-source adoption are explicit,
and neither silently changes the cloud pin. Resolve the actual invoked source
and report collisions or changed selections before using the affected route.
This preserves local workflows while retaining reproducible cloud setup.

The existing registry remains authoritative. Monthly upstream maintenance and
compatibility checks before adoption govern source and runtime changes;
upgrades preserve customizations and retain recovery to the previous
installation. Revisit this decision if distribution size, licensing, runtime
discovery changes, or maintenance cost makes bundling unsuitable. Require
actual fresh and recreated cloud evidence for each supported runtime before
claiming support.

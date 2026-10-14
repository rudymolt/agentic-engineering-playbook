# Edition and installed release — alignment

The V0.5.2 public upgrader records `playbook_version: V0.5.0` because that is
the edition's migration stamp. Stage 00 currently compares that stamp with the
latest changelog release, so a current project can appear behind. The user
identified that comparison as the source of the confusion on 2026-10-14.

Keep edition-based migration behavior and preserve project customisations.
Record a separate installed release only when exact checkout or package
provenance proves it. An unverified source reports an unknown release without
inventing one from the directory name, changelog, or edition stamp. Bootstrap,
upgrade, status, and instructions use explicit edition and release labels.

This is a public developer-facing change without UI. The existing monthly
upstream maintenance and pinned-release upgrade checkpoints continue to own
future software, skill, model, and settings compatibility. A future release
must verify its source tag and preview migrations before updating project
files, preserving local choices and customisations.

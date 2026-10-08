# Matt v1.3.1 adoption

This follows the [October comparison](2026-10-08-upstream-drift.md), whose
retained-pin conclusions remain historical. The maintainer selected the Matt
migration on 2026-10-08. gstack qualification remains a separate batch.

## Source and selected changes

Adopt released [v1.3.1](https://github.com/mattpocock/skills/releases/tag/v1.3.1),
commit `24fe0ef7737efae15c87225755e9f6f5965e4888`. The
[source receipt](2026-10-08-matt-migration-sources.json) records each selected
skill and every file in its directory. These are tagged-source observations,
not receipts from a user's installed skills or permission to invoke a reviewer.

The three newly added skills relative to v1.2.3 are implement-spec, pr and retro.
Adopt optional pr at stage 10 and the environment-improvement practices from
Matt's retro at stage 12, retaining gstack's existing bare retro name. Direct
implement-spec orchestration remains unadopted. The release removes the conflict
skill with no replacement; stage-owned conflict handling keeps intent inspection,
tests and required fresh review.

GLOSSARY.md and GLOSSARY-MAP.md become the domain convention. The root migration
moves project content, pristine base and provenance together; the ordinary
template merge then updates managed references. Project-authored maps and
ambiguous content use the reviewed procedure in the
[migration guide](../v0.5/skills/ai-playbook-upgrade-project/MIGRATIONS.md).
The delivery policy protects both new and historical domain filenames.

## Source checks and limits

The exact v1.3.1 code-review SHA-256 is
`47f4e52c21694def9c7c11cbfbf891ca35eac7a93e395797515be3c8a409ae50`;
implement remains
`6d3fd9e83b8f36e5213854779db49b256a457a7ebb4a503e53fa7dcff696adc3`.
Both compatibility checks return exit 2, `may_invoke: false`, with the
stage-08/stage-07 manual routes. Source records advance without granting embedded
permission. No compatible-route runtime qualification is claimed.

The pinned installer discovery command was executed successfully:

```bash
npx --yes skills@1.7.1 add https://github.com/mattpocock/skills/tree/v1.3.1 --list
```

It lists the tagged skills without installing them. Actual host rollout still
requires reviewing local customizations, selecting the intended commands and
scope, checking installed bytes, and running stage 00 cold. A source archive or
successful discovery does not prove Mac, Codex or Claude execution compatibility.

Repository regression and fresh review results are recorded in
[the migration slices](../planning/matt-skills-migration/slices.md). Release
consumers remain on a stable playbook tag; publication and project rollout follow
review. Recheck sources before an upstream-contract release and monthly, next
due 2026-11-08. Changed helpers, skills, host settings or model profiles invalidate
the relevant qualification and trigger a new source/host audit.

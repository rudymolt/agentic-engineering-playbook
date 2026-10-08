# Matt skills migration — alignment

The maintainer approved implementation of the reviewed upstream migration plan
on 2026-10-08. Plan source: the exact Matt v1.3.1 release and the October upstream
comparison. The first delivery is Matt's coordinated migration; gstack remains
a separately qualified follow-up at a fixed source revision.

Adopt GLOSSARY.md and GLOSSARY-MAP.md for domain vocabulary, preserve customized
project content and template provenance, retire the removed conflict skill, and
incorporate useful PR and retrospective practices under the existing stages.
Keep UI DESIGN-GLOSSARY.md separate. Do not enable incompatible embedded reviewers
or adopt implement-spec's orchestration as part of this migration.

The existing conversation supplies alignment and approval. This maintainer
checkout deliberately has no consumer state file. No UI interaction changes;
UI mockup is not applicable. Implementation uses the current session; independent
review follows implementation. No host installation or public merge is authorized
by this repository migration.

Future changes: recheck released sources monthly (next due 2026-11-08) and before
an upstream-contract release. Re-audit installed sources on host, skill, model
profile or settings changes; preserve customizations and retain manual routes
until the exact changed dependencies have been qualified.

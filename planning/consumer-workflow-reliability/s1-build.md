# S1 build handoff

- Scope: checkpoint examples, bootstrap/upgrade adoption guidance and public CLI
  regressions for contract 1–3. Implementation is ready for fresh review; this
  report is implementer evidence, not independent verification or release proof.
- Ordinary examples now use 250 aggregate calls per substantive slice, separate
  300-call broad final verification and a 300-minute multi-slice forecast.
  Explicit caps, protected ceilings, Stop, actual quotas and cumulative failure
  guards remain binding. No provisioning, runtime, shared settings or consumer
  operations changed.
- Public CLI fixtures exercise pristine bootstrap and replay, preserved existing
  hard-cap/ambiguous instructions, inherited-estimate upgrade, read-only preview,
  conflicting project customizations, retained release proof, reviewed conversion,
  deliberately retained caps and byte-identical second upgrade. Owner choices
  are simulated in disposable fixtures; no consumer adoption is claimed.
- Red evidence: pristine bootstrap lacked the new estimates; conflicting upgrade
  cleared prior release/tag-object/commit proof. Green changes update the docs
  and preserve starting release proof on unresolved reviews regardless of
  inventory selection. No new prose classifier or policy engine was added.
- Next action: coordinator dispatches fresh independent S1 review against the
  approved contract and this branch. S2–S4, maintenance, live qualification,
  final-candidate verification, CI, release and consumer adoption remain separate.

## Focused verification

All 51 tests in the five focused modules below passed, along with the listed
content/generated-file checks and diff check.

Use Python 3.12 (the CI interpreter); the VM's default Python 3.9 cannot load the
existing Markdown convention module. No repository interpreter setting changed.

```bash
python3.12 -m unittest discover -s v0.5/scripts -p test_public_upgrade_transition.py
python3.12 -m unittest discover -s v0.5/scripts -p test_bootstrap_project.py
python3.12 -m unittest discover -s v0.5/scripts -p test_template_base.py
python3.12 -m unittest discover -s v0.5/scripts -p test_release_provenance.py
python3.12 -m unittest discover -s v0.5/scripts -p test_skill_adoption.py
python3.12 v0.5/scripts/check-md-conventions.py
python3.12 v0.5/scripts/check-links.py
python3.12 v0.5/scripts/check-public-content.py
python3.12 v0.5/scripts/check-skill-metadata.py
python3.12 v0.5/scripts/check-interactive-docs.py
python3.12 v0.5/scripts/generate-status.py --check
python3.12 v0.5/delivery/scripts/generate.py --check
python3.12 v0.5/scripts/generate-manifest.py --check
git diff --check
```

The edition manifest was regenerated. Status and delivery generated artifacts
were regenerated without content changes. No full verifier or embedded upstream
reviewer was run. Bootstrap/upgrade guidance requires manual review of prose
intent; a generic helper preview is not evidence of that review. The CLI tests
prove preservation and replay, not an agent's future interpretation of arbitrary
custom instructions. Runtime model/thread metadata is owned by the coordinator;
aggregate worker/coordinator usage counters are unavailable to this report.

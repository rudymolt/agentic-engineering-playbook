# Apply recovery artifact visibility — specification

Bootstrap and supported upgrades manage `.playbook-routing/` and anchored
`/.playbook-config-*`. Append only missing exact managed entries. Preserve
existing user text, including whitespace and an absent final newline, adding
a line separator when needed. Repeated runs must not duplicate entries or
rewrite an already complete ignore file.

Bootstrap's read-only plan must accurately show each missing addition and
existing managed entry. The upgrade skill's approval plan must disclose these
safe additive changes; its CLI continues to require `--apply-safe`.

At the existing public bootstrap/upgrade and real Git seams, verify:

- Real Apply retains publication/backup evidence, receipts and completion
  seals; these root artifacts are ignored while configuration stays trackable.
- Reopen and subsequent Apply preserve successful receipt reconciliation.
  Completion/conflict recovery still blocks unsafe reads and retains evidence.
- Existing user entries, whitespace and missing final newline survive; routing
  already present does not prevent adding the artifact rule.
- Old-project supported migration adds the rule, preserves retained bytes and
  customisations, and a second run is a no-op.
- Bootstrap plan and seed preview are read-only; a seeded config is visible.
- Nested `.playbook-config-*`, unrelated receipts and dot-named configuration
  control files are not hidden by this anchored rule.

No deletion of artifacts, blanket receipt rules or ignore of the configuration.

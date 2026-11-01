# Pinned gstack provisioning — execution

Parent slice: make the pinned gstack package replayable for both hosts.

1. **Package proof.** Extend the existing generator CLI to record and validate
   the pinned archive, frozen lock, exact generator and selected host outputs.
   Verify source changes, symlinks, host-name exceptions and explicit exclusions.
2. **Runtime acquisition and build.** Acquire the exact source and reviewed Bun
   artifact; build only frozen dependencies in an isolated store. Exercise cold
   build, complete warm-cache replay, interrupted work and damaged inputs through
   the provisioner CLI.
3. **Host activation and integration.** Publish selected adapted endpoints from
   off-discovery support storage. Wire adoption/setup/reporting; exercise repair,
   conflict preservation and rollback. Preserve original and adapted identities.
4. **Parent review.** Fresh independent execution against a disposable Linux
   consumer, followed by fixes and fresh verification across the complete slice.

Each sub-slice receives a fresh independent review and atomic commit. Splitting
the original replay/activation step keeps source proof, native build state and
host-discovery state independently reviewable; the parent acceptance is unchanged.

Status: package proof passed fresh independent verification (14 focused tests,
offline archive verification and 13 additional public-CLI rejection probes).
The real Linux frozen install and five native binary builds passed; offline
generation matched all 34 selected Codex endpoints. Runtime acquisition/build
also passed fresh independent verification: 12 runtime tests, five related tests
and 28 adversarial probes (44 public CLI invocations). The revised Linux arm64
cold build passed in 279 seconds and complete warm replay passed with networking
disabled in 170 seconds. Both reports retain unverified discovery and behavior.
Host activation/integration and the local support-file repair are implemented.
Independent cross-slice review identified preservation/reporting defects; the
fixes now pass focused fresh review. Final full Linux verification is in progress.
See [verification evidence](evidence.md). Actual Cloud qualification and public
release remain later gates.

# Pinned skill provisioning verification

## Candidate coverage

The source/package and runtime commits are `b36de0f` and `831ff36`.
The subsequent activation and local-support changes retain the existing source
pins. Source integrity, installation, host discovery and behavioral qualification
remain separate claims.

Real isolated Linux arm64 execution verified the frozen Bun build and all five
native outputs, then replayed the complete cache with networking disabled.
A disposable adopted consumer installed 35 Claude and 34 Codex gstack endpoints;
the upstream Codex wrapper exclusion remains explicit. Repeated setup wrote no
files. Removing template support, a delivery-owned file and a Matt skill triggered
repair. Moving the exact source updated rendered references while retaining a
project customization; repeating relocated setup again wrote nothing.

## Independent review and returned fixes

Fresh reviewers executed package/runtime, activation, adoption, local-support and
cross-slice tests without the implementer transcript. Returned findings were
reproduced and corrected before the focused follow-up review:

- Preserve concurrent state edits at both validation and atomic publication.
- Bind direct local repair to the destination's exact adopted release.
- Preserve hardlinks, symlinks, unknown files and unknown directories.
- Require the full readable source inventory and strict delivery ownership locks.
- Keep coordinated host rollback targets through interruption and repair.
- Keep completion false when recovery or final observation remains unresolved.
- Record successful file publication before reading displaced bytes.
- Preserve ambiguous partial staging instead of adopting a matching prefix.

The final local transaction suite passed all 14 tests. Fresh independent review
passed five focused regression methods plus a recovery probe covering empty and
partial staging. Before/after hashes matched for all three reviewed files.
Native atomic publication ran on macOS; final Linux coverage is tracked below.

```sh
python3 -B -m unittest discover -s v0.5/scripts -p test_local_skill_transactions.py
```

The earlier independent local-support pass executed 17 requested tests and seven
boundary probes. Its two failing probes drove the final publication/staging fixes;
it is not recorded as a passing verdict. The focused fresh review passed the
returned-fix acceptance, ordinary interruption/recovery and concurrency checks.

## Final gate

PR CI exposed a stale source-recovery assertion that required byte-identical
state despite relocation intentionally refreshing managed skill base hashes.
The reproduced delta contained only eight such hashes. The corrected test checks
the relocated file bytes, pristine bases and hashes, retains template/version
identity, and requires all state outside provenance to remain byte-identical.
The corrected hook test and the related offline-reuse test pass locally.

The full `python3 v0.5/scripts/verify-playbook.py --jobs 3` run is in progress in
an isolated Linux container with no network, UID 0 and the fanotify capability
required by delivery-monitor tests. Earlier snapshots predate either the final
publication fixes or the corrected source-recovery assertion; their partial
results cannot certify this candidate.

Public release, consumer adoption and actual Cloud lifecycle/discovery/invocation
remain pending. These fixture results do not establish those acceptance criteria.

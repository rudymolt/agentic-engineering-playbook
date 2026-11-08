# Consumer workflow reliability — slices

Status: S1 independently verified; startup diagnosis confirmed and consumer repair
in progress. Release and final both-host qualification remain open.

| Slice | Outcome | Acceptance and dependencies |
|---|---|---|
| S1 | Checkpoint examples and migration review | Contract 1–3; public bootstrap/upgrade fixtures; fresh review |
| S2 | Startup diagnosis | Contract 4; inspect original evidence before replay; independent of S1 |
| S3 | Conditional minimal repair | Only after S2 reproduces a defect; regression, preservation and fresh verification; otherwise record not applicable |
| S4 | Both-host qualification and adoption | Contract 5–7; S2/S3 disposition, final release gates, separate reviewed consumer adoption |

Use focused checks while iterating. Run the full canonical verifier on the final
candidate. Record measured evidence and remaining gaps at each slice boundary.
S1 may release independently, but does not complete the wider acceptance alone.
Live qualification uses separately recorded finite resource limits and isolated
fixtures. Preserve cumulative failure history through all workers and handoffs.

## S1 review disposition

A fresh verifier passed the implementation at `ca90dee` against contract 1–3:
69 focused tests, six content/generated checks and public CLI scenarios using
actual prior templates. Read-only previews, retained caps, reviewed conversion,
prior-proof preservation and unchanged replay passed. Tracked hashes, refs,
index and status remained unchanged. The runner lacked an enforced read-only
sandbox; controller metadata attested the selected Sol/high route.

An initial pending-marker probe assumed behavior the unchanged base does not
provide. The base/candidate comparison dismissed it as an existing limitation;
exit zero alone does not certify interrupted-operation recovery. Full release
verification and final consumer acceptance are separate gates.

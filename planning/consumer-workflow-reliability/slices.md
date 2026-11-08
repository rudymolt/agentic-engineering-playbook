# Consumer workflow reliability — slices

Status: authorized for autonomous completion; implementation pending.

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

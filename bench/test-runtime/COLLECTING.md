# Track totals from normal feature CI

Use existing successful Playbook CI logs as the primary daily runtime source.
Do not run the full suite again just to fill a timing row. Select the final
successful feature/batch head consistently, rather than the fastest retry.
Read [the totals](TOTAL-RUNTIME.md) alongside [the review ledger](REVIEW-LEDGER.md).

For a selected completed run, get its edition and delivery job IDs from GitHub.
Confirm both jobs succeeded and delivery actually ran the full K4.1 command.
Use the connected GitHub tool to download each job log, or use the CLI:

```sh
mkdir -p .context/runtime-logs
gh run view RUN_ID --log --job EDITION_JOB_ID > .context/runtime-logs/edition.log
gh run view RUN_ID --log --job DELIVERY_JOB_ID > .context/runtime-logs/delivery.log
python3 bench/collect_ci_runtime.py collect \
  --edition-log .context/runtime-logs/edition.log \
  --delivery-log .context/runtime-logs/delivery.log \
  --repository OWNER/REPOSITORY \
  --head-sha FULL_HEAD_SHA --run-id RUN_ID \
  --edition-job-id EDITION_JOB_ID --delivery-job-id DELIVERY_JOB_ID \
  --history bench/test-runtime/suite-history.json
python3 bench/collect_ci_runtime.py report \
  --history bench/test-runtime/suite-history.json \
  --output bench/test-runtime/TOTAL-RUNTIME.md
```

The collector is offline: run/job association comes from the caller's verified
GitHub metadata. It checks the logged checkout against the supplied head,
including the synthetic merge checkout used by pull-request CI. Both raw job
logs and the job/step-prefixed `gh run view --log` format are supported. It rejects
partial commands, failed/skipped unittest groups, missing success markers,
unexpected group counts, mismatched checkouts and conflicting duplicate run IDs.
Legacy commands keep the default of one edition group and 15 delivery groups.
Commands with the reviewed `--jobs N` suffix (1–4) require `--suite-manifest`:
a JSON inventory bound to the exact head, with ordered module names and expected
execution counts for each suite. Parallel runs must contain exactly one schedule,
zero-exit completion and clean summary per expected module. Changing a group
count alone cannot admit parallel logs. Unknown formats remain fail-closed.
For serial legacy discovery growth, inspect the runner before changing
`--delivery-groups`; never lower it to admit incomplete evidence. Same-evidence duplicate
collection is idempotent. Logs with a different format require parser review.

Keep raw logs in ignored context storage. Commit only sanitized history, the
rendered summary, relevant review-ledger updates, reviewed discovery manifests
and minimal public-safe fixture excerpts. Excerpt hashes differ from raw hashes;
fixtures test parsing and never replace the raw source of a recorded observation. Input-log hashes bind the
extraction; runner image/version, Python/Git versions, commands, counts, head and
checkout SHAs and source run/job IDs remain in the JSON. Supply the actual public
repository slug for `--repository`. Evidence links are
concrete GitHub Actions URLs; collection and rendering reject unresolved owner
placeholders. The public-content check permits this repository's Actions links
only in the two runtime evidence outputs.
None of the three initial runs had downloadable timing artifacts, so their
ordinary job logs are the evidence source.

Keep three distinct measures:

- Summed unittest runner seconds: fixture/test/cleanup work across both suites.
  This excludes process startup and standalone validation commands.
- Verification log span: the canonical command header through its success line.
  This includes CLI checks and shell/log overhead and is an elapsed-time proxy.
- Parallel jobs log span: earliest job log to latest job log. Do not add parallel
  job durations and call the result elapsed CI time. Queue time and exact total
  workflow wall time are unknown from these logs and remain null.

A partial local feature check or scope-skipped delivery job is not a full-suite
row. Retain it separately with its exact selection/count; do not replace the
latest full-suite total with a partial result. Collector self-tests are bench
maintenance checks outside the canonical edition/K4.1 counts; neither this tool
nor its documentation changes the suite being measured.

Initial history: baseline `a57af6d` has 756 executions; September 30 `f5cad4f` and
October 1 `bf85806` have 760. Four cache guard tests account for that growth.
All use Python 3.12.14/Git 2.55.0 in hosted Ubuntu 24.04 CI, but runner images
and unreported hardware differ. The untouched coordinator group fell from
257.258 s to 137.680 s across the original/current runs. The observed 43.02%
total drop therefore cannot be presented as a measured optimization effect.
The narrower repeated comparisons establish the actual batch evidence.

Daily use: append each completed batch's normal full-suite CI result, review its
count and environment changes, regenerate the table, and explain any suite-growth
or runner change in the ledger. Positive saved seconds mean faster; negative
values retain regressions. No per-test normalization hides added coverage. This
is a reusable collection procedure, not a new schedule or automatic background job.

Verify the collector without exercising delivery fixtures:

```sh
python3 -m unittest discover -s bench -p 'test_collect_ci_runtime.py' -v
```

## Parallel format admission

The first supported parallel revision is `a89fd242ae2e87caed987359e65e7a454203c5cf`.
Its inventory is in `manifests/` and minimal real-log excerpts are in `fixtures/`.
Pass the matching manifest explicitly with `--suite-manifest PATH` when collecting.
A new head requires a freshly reviewed manifest; copying an old head field or
inferring expected counts from the log under admission is not verification.

To prepare an inventory without a timing run, inspect the exact revision in an
isolated source checkout. Enumerate edition `test_*.py` files in sorted order and
read delivery `verify.py`'s `SETS["K4.1"]`. For each module, use a fresh Python
process with `unittest.TestLoader().discover(directory, pattern=module)`, require
no loader errors, and call `countTestCases()` without running the suite. Review
imports before discovery. Record ordered names, independent counts, test-file
SHA-256 values, and hashes of both verifiers, the parallel runner and edition
manifest. Review the runner's label/exit/output-buffering contract. The supplied
manifest is trusted evidence reviewed by the caller, not an attestation produced
by the collector. Hashes preserve provenance; the offline collector does not
fetch or execute revision sources.

`--jobs 1` retains serial duration semantics. With multiple workers, the sum of
unittest durations includes overlap and scheduling contention. Reports start a
separate comparison cohort for each edition/delivery worker-count combination,
leave cross-cohort duration deltas blank, and retain execution-count changes.
Do not interpret this as a serial baseline or a measured parallel speedup.
GitHub API job timestamps, if independently verified, belong in the history's
`supplemental_evidence`; distinguish them from log-derived spans. The gate span
between earliest job start and latest job completion excludes queue time.

The October 3 parallel run is supplemental evidence, not a replacement for the
original daily observation. Its preceding failed run is never a successful
baseline. CI action majors are action versions, not playbook edition labels.

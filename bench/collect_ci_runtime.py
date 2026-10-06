#!/usr/bin/env python3
"""Collect full-suite timing from existing successful CI logs; never run tests."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import hashlib
from pathlib import Path
import re

STAMP = re.compile(r"^(?:[^\t\n]*\t[^\t\n]*\t)?\ufeff?(\d{4}-\d\d-\d\dT[\d:.]+Z) (.*)$")
SUMMARY = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s$")
SHA = re.compile(r"^[0-9a-f]{40}$")
COMMANDS = {
    "edition": "python3 v0.5/scripts/verify-playbook.py --skip-drift --skip-delivery",
    "delivery": 'sudo "$(command -v python3)" v0.5/delivery/scripts/verify.py --set K4.1',
}
MARKERS = {"edition": "Playbook release-readiness checks passed.",
           "delivery": "V0.5 delivery K4.1 checks passed."}


def seconds(start, end):
    return round((datetime.fromisoformat(end.replace("Z", "+00:00")) -
                  datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds(), 6)


def manifest_modules(manifest, suite, head_sha):
    """A reviewed discovery inventory is independent of the log being admitted."""
    if not manifest or manifest.get("schema_version") != 1 or manifest.get("head_sha") != head_sha:
        raise ValueError("revision-bound suite manifest required for --jobs")
    modules = manifest["suites"][suite]["modules"]
    names = [m["module"] for m in modules]
    if (not names or len(set(names)) != len(names) or
            any(not re.fullmatch(r"test_[A-Za-z0-9_]+\.py", name) for name in names) or
            any(type(m["executions"]) is not int or m["executions"] < 1 for m in modules) or
            sum(m["executions"] for m in modules) != manifest["suites"][suite]["executions"]):
        raise ValueError("invalid suite module/count manifest")
    return modules


def parse_job(raw, suite, head_sha, expected_groups, *, suite_manifest=None):
    if expected_groups < 1:
        raise ValueError("positive expected group count required")
    lines = [(m[1], m[2]) for line in raw.splitlines() if (m := STAMP.match(line))]
    if not lines:
        raise ValueError("timestamped GitHub job log required")
    pattern = re.compile(re.escape("##[group]Run " + COMMANDS[suite]) + r"(?: --jobs ([1-4]))?$")
    commands = [(stamp, text, match) for stamp, text in lines if (match := pattern.fullmatch(text))]
    starts = [stamp for stamp, _, _ in commands]
    ends = [stamp for stamp, text in lines if text == MARKERS[suite]]
    if len(starts) != 1 or len(ends) != 1 or seconds(starts[0], ends[0]) < 0:
        raise ValueError(f"{suite}: one complete canonical successful command required")
    command = commands[0][1].removeprefix("##[group]Run ")
    workers = int(commands[0][2][1] or 1)
    modules = manifest_modules(suite_manifest, suite, head_sha) if commands[0][2][1] or suite_manifest else None
    parallel = workers > 1
    if modules:
        expected_groups = len(modules) if parallel or suite == "delivery" else 1
    body = [(stamp, text) for stamp, text in lines if starts[0] <= stamp <= ends[0]]
    if any("##[error]" in text or text.startswith("FAILED") for _, text in lines):
        raise ValueError(f"{suite}: failed command cannot enter full-suite history")
    groups = []
    scheduled, completed = set(), set()
    active = None
    for index, (_, text) in enumerate(body):
        if text.startswith(("Scheduled test shard ", "Test shard ")):
            if not parallel:
                raise ValueError(f"{suite}: shard output contradicts serial command")
            label = re.fullmatch(r"(Scheduled test shard|Test shard) ([1-9][0-9]*)/([1-9][0-9]*): (test_[A-Za-z0-9_]+\.py)(?: \(exit (-?[0-9]+)\))?", text)
            if not label:
                raise ValueError(f"{suite}: malformed shard label")
            number, total = int(label[2]), int(label[3])
            if total != len(modules) or not 1 <= number <= total or label[4] != modules[number - 1]["module"]:
                raise ValueError(f"{suite}: shard identity does not match manifest")
            target = scheduled if label[1] == "Scheduled test shard" else completed
            if number in target or (target is scheduled and label[5] is not None):
                raise ValueError(f"{suite}: duplicate/invalid shard")
            if target is completed:
                if label[5] != "0" or number not in scheduled or active is not None:
                    raise ValueError(f"{suite}: failed or incomplete shard")
                active = number
            target.add(number)
        match = SUMMARY.fullmatch(text)
        if match:
            following = next((t for _, t in body[index + 1:] if t.strip()), "")
            if following != "OK":
                raise ValueError(f"{suite}: failed/skipped/ambiguous unittest group")
            group = {"executions": int(match[1]), "test_seconds": float(match[2])}
            if parallel:
                if active is None or group["executions"] != modules[active - 1]["executions"]:
                    raise ValueError(f"{suite}: missing shard or mismatched execution count")
                group["module"] = modules[active - 1]["module"]
                active = None
            elif modules:
                counts = [sum(m["executions"] for m in modules)] if suite == "edition" else [m["executions"] for m in modules]
                if len(groups) >= len(counts) or group["executions"] != counts[len(groups)]:
                    raise ValueError(f"{suite}: mismatched serial execution count")
            groups.append(group)
    if parallel and (active is not None or scheduled != set(range(1, len(modules) + 1)) or completed != scheduled):
        raise ValueError(f"{suite}: incomplete scheduled/completed module inventory")
    if len(groups) != expected_groups or any(g["executions"] < 1 for g in groups):
        raise ValueError(f"{suite}: expected {expected_groups} complete unittest groups, got {len(groups)}")
    checkouts = [lines[i + 1][1] for i, (_, text) in enumerate(lines[:-1])
                 if text.endswith("git log -1 --format=%H") and SHA.fullmatch(lines[i + 1][1])]
    if len(set(checkouts)) != 1:
        raise ValueError(f"{suite}: unambiguous checkout identity required")
    checkout = checkouts[0]
    if checkout != head_sha and not any(re.search(r"Merge " + re.escape(head_sha) + r" into [0-9a-f]{40}$", text) for _, text in lines):
        raise ValueError(f"{suite}: checkout does not attest supplied head SHA")
    def first(pattern):
        return next((m[1] for _, text in lines if (m := re.search(pattern, text))), None)
    image_index = next((i for i, (_, text) in enumerate(lines) if text.startswith("Image: ")), None)
    image_version = None
    if image_index is not None:
        image_version = next((text.removeprefix("Version: ") for _, text in lines[image_index + 1:]
                              if text.startswith("Version: ")), None)
    result = {
        "command": command, "checked_out_sha": checkout,
        "source_log_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "python": first(r"Successfully set up CPython \(([^)]+)\)"),
        "git": first(r"^git version (\S+)"),
        "runner_image": first(r"^Image: (.+)$"), "runner_image_version": image_version,
        "runner_hardware": None, "privileged": suite == "delivery",
        "groups": groups, "executions": sum(g["executions"] for g in groups),
        "test_seconds": round(sum(g["test_seconds"] for g in groups), 6),
        "verification_log_span_seconds": seconds(starts[0], ends[0]),
        "first_log_at": lines[0][0], "last_log_at": lines[-1][0],
        "job_log_span_seconds": seconds(lines[0][0], lines[-1][0]),
        "successful": True, "skipped_executions": 0,
    }

    if modules:
        result.update(concurrent_workers=workers,
                      duration_semantics="summed_unittest_durations_overlap" if parallel else "serial_unittest_durations",
                      suite_manifest_sha256=hashlib.sha256(json.dumps(suite_manifest, sort_keys=True).encode()).hexdigest())
    return result


def run_url(repository, run_id):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9_.-]+", repository):
        raise ValueError("concrete GitHub owner/repository required; placeholders are not evidence links")
    if type(run_id) is not int or run_id < 1:
        raise ValueError("positive integer run ID required")
    return f"https://github.com/{repository}/actions/runs/{run_id}"


def validate_run_url(row):
    match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/actions/runs/([1-9][0-9]*)", row["run_url"])
    if not match or run_url(match[1], row["run_id"]) != row["run_url"]:
        raise ValueError("concrete GitHub evidence URL matching run ID required")


def collect(head_sha, run_id, edition_log, delivery_log, delivery_groups=15, *, repository, suite_manifest=None):
    evidence_url = run_url(repository, run_id)
    if not SHA.fullmatch(head_sha) or run_id < 1:
        raise ValueError("full lowercase SHA and positive run ID required")
    jobs = {"edition": parse_job(edition_log, "edition", head_sha, 1, suite_manifest=suite_manifest),
            "delivery": parse_job(delivery_log, "delivery", head_sha, delivery_groups, suite_manifest=suite_manifest)}
    if len({j["checked_out_sha"] for j in jobs.values()}) != 1:
        raise ValueError("edition and delivery must test the same checkout")
    return {
        "head_sha": head_sha, "run_id": run_id,
        "observed_date": min(j["first_log_at"] for j in jobs.values())[:10],
        "evidence_kind": "observed_normal_ci_not_controlled_benchmark",
        "coverage": "full_edition_and_K4.1", "jobs": jobs,
        "executions": sum(j["executions"] for j in jobs.values()),
        "summed_test_seconds": round(sum(j["test_seconds"] for j in jobs.values()), 6),
        "parallel_jobs_log_span_seconds": seconds(min(j["first_log_at"] for j in jobs.values()),
                                                   max(j["last_log_at"] for j in jobs.values())),
        "queue_seconds": None, "overall_workflow_wall_seconds": None,
        "run_url": evidence_url,
    }


def comparison_cohort(record):
    workers = [record["jobs"][suite].get("concurrent_workers", 1) for suite in ("edition", "delivery")]
    return "serial_unittest" if workers == [1, 1] else f"parallel_unittest:{workers[0]}+{workers[1]}"


def annotate(records):
    """Compare each run with its cohort; keep cross-record growth separate."""
    if not records:
        return []
    result = []
    originals = {}
    previous = None
    previous_by_cohort = {}
    for record in records:
        row = dict(record)
        cohort = comparison_cohort(record)
        original = originals.setdefault(cohort, record)
        for name, base in (("daily", previous_by_cohort.get(cohort)), ("cumulative", original)):
            if name == "cumulative" and original is record and previous is not None:
                base = None
            count_base = base
            row[name + "_observed_saved_seconds"] = None if base is None else round(base["summed_test_seconds"] - record["summed_test_seconds"], 6)
            row[name + "_observed_reduction_percent"] = None if base is None else round(100 * (1 - record["summed_test_seconds"] / base["summed_test_seconds"]), 4)
            row[name + "_execution_count_change"] = None if count_base is None else record["executions"] - count_base["executions"]
        row["cross_record_execution_count_change"] = None if previous is None else record["executions"] - previous["executions"]
        result.append(row)
        previous = record
        previous_by_cohort[cohort] = record
    return result


def render(records):
    lines = ["# Observed full-suite runtime history", "",
        "Collected from ordinary successful feature CI logs; no extra suite runs.",
        "These are observations, not controlled or causal optimization estimates.", "",
        "Test time sums unittest runner durations across edition and K4.1, including",
        "test fixtures but excluding interpreter startup and standalone CLI checks.",
        "The jobs run in parallel: their overall log span is an elapsed-time proxy,",
        "not the sum of their durations. It excludes queue and pre-log setup; exact",
        "workflow wall time and queue time are unknown. Verification log spans in",
        "the JSON include CLI checks and shell/log overhead, not just test time.", "",
        "| Date / revision | Executions | Summed tests | Observed saved vs previous | Observed saved vs original | Parallel jobs log span | Evidence |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
    cohorts = {}
    for row in annotate(records):
        cohorts.setdefault(comparison_cohort(row), []).append(row)
    for cohort_index, (current_cohort, rows) in enumerate(cohorts.items()):
        if cohort_index:
            lines += ["", f"Comparison baseline: `{current_cohort}` (separate from serial durations).", "",
                      "| Date / revision | Executions | Summed tests | Observed saved vs previous | Observed saved vs original | Parallel jobs log span | Evidence |",
                      "| --- | ---: | ---: | ---: | ---: | ---: | --- |"]
        for row in rows:
            validate_run_url(row)
            def delta(kind):
                value = row[kind + "_observed_saved_seconds"]
                return "—" if value is None else f'{value:+.3f} s ({row[kind + "_observed_reduction_percent"]:+.2f}%)'
            lines.append(f'| {row["observed_date"]} / `{row["head_sha"][:12]}` | {row["executions"]} | {row["summed_test_seconds"]:.3f} s | {delta("daily")} | {delta("cumulative")} | {row["parallel_jobs_log_span_seconds"]:.3f} s | [run {row["run_id"]}]({row["run_url"]}) |')
    lines += ["", "Execution-count changes remain part of the observed totals. No duration is",
        "subtracted for suite growth; per-test averages do not establish equivalence.",
        "Counts are canonical executions, not unique IDs: imported tests can be",
        "intentionally discovered in more than one module.", "",
        "Runner image, Python/Git versions, canonical commands, exact head and",
        "checked-out (possibly synthetic PR merge) SHAs, module counts and durations",
        "are retained in [suite-history.json](suite-history.json). Hosted hardware",
        "is not identified in these logs. The October 1 delivery image changed, and",
        "untouched coordinator tests also became much faster; the observed drop",
        "must not be attributed wholly to the optimizations. Targeted repeated",
        "comparisons in [the review ledger](REVIEW-LEDGER.md) support narrower claims.", "",
        "A row is one selected full-suite run, not a daily median. The previous-row",
        "delta is the daily batch comparison only while one representative completed",
        "run is retained per batch. Keep selection consistent (final successful head);",
        "do not pick the fastest retry. Retain additional runs as separate evidence.", ""]
    if any(comparison_cohort(r) != "serial_unittest" for r in records):
        lines += ["With concurrent unittest workers, summed durations overlap. They are not",
                  "suite, job, or gate elapsed time and cannot measure speedup against the",
                  "serial baseline. Cross-concurrency duration deltas are intentionally blank.",
                  "The supplemental concurrency baseline does not replace the original daily",
                  "observation; retain suite growth and runner changes when interpreting it.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("collect")
    add.add_argument("--edition-log", type=Path, required=True)
    add.add_argument("--delivery-log", type=Path, required=True)
    add.add_argument("--head-sha", required=True)
    add.add_argument("--repository", required=True, help="concrete GitHub owner/repository")
    add.add_argument("--run-id", type=int, required=True)
    add.add_argument("--edition-job-id", type=int, required=True)
    add.add_argument("--delivery-job-id", type=int, required=True)
    add.add_argument("--delivery-groups", type=int, default=15)
    add.add_argument("--suite-manifest", type=Path, help="reviewed revision-bound module/count inventory; required with --jobs")
    add.add_argument("--history", type=Path, required=True)
    report = sub.add_parser("report")
    report.add_argument("--history", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        history = json.loads(args.history.read_text()) if args.history.exists() else {"schema_version": 1, "records": []}
        if history.get("schema_version") != 1:
            raise ValueError("unsupported history schema")
        if args.action == "collect":
            row = collect(args.head_sha, args.run_id, args.edition_log.read_text(), args.delivery_log.read_text(), args.delivery_groups, repository=args.repository, suite_manifest=json.loads(args.suite_manifest.read_text()) if args.suite_manifest else None)
            for suite, job_id in (("edition", args.edition_job_id), ("delivery", args.delivery_job_id)):
                if job_id < 1:
                    raise ValueError("positive job IDs required")
                row["jobs"][suite]["job_id"] = job_id
            existing = next((r for r in history["records"] if r["run_id"] == row["run_id"]), None)
            if existing is not None and existing != row:
                raise ValueError("run already recorded with different evidence")
            if existing is None:
                history["records"].append(row)
                history["records"].sort(key=lambda r: (r["observed_date"], r["run_id"]))
            args.history.parent.mkdir(parents=True, exist_ok=True)
            args.history.write_text(json.dumps(history, indent=2) + "\n")
            print(f'Collected {row["executions"]} executions, {row["summed_test_seconds"]:.3f} test seconds')
        else:
            args.output.write_text(render(history["records"]))
    except (ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

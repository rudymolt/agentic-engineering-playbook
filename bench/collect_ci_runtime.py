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


def parse_job(raw, suite, head_sha, expected_groups):
    if expected_groups < 1:
        raise ValueError("positive expected group count required")
    lines = [(m[1], m[2]) for line in raw.splitlines() if (m := STAMP.match(line))]
    if not lines:
        raise ValueError("timestamped GitHub job log required")
    starts = [stamp for stamp, text in lines if text == "##[group]Run " + COMMANDS[suite]]
    ends = [stamp for stamp, text in lines if text == MARKERS[suite]]
    if len(starts) != 1 or len(ends) != 1 or seconds(starts[0], ends[0]) < 0:
        raise ValueError(f"{suite}: one complete canonical successful command required")
    body = [(stamp, text) for stamp, text in lines if starts[0] <= stamp <= ends[0]]
    if any("##[error]" in text or text.startswith("FAILED") for _, text in body):
        raise ValueError(f"{suite}: failed command cannot enter full-suite history")
    groups = []
    for index, (_, text) in enumerate(body):
        match = SUMMARY.fullmatch(text)
        if match:
            following = next((t for _, t in body[index + 1:] if t.strip()), "")
            if following != "OK":
                raise ValueError(f"{suite}: failed/skipped/ambiguous unittest group")
            groups.append({"executions": int(match[1]), "test_seconds": float(match[2])})
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
    return {
        "command": COMMANDS[suite], "checked_out_sha": checkout,
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


def collect(head_sha, run_id, edition_log, delivery_log, delivery_groups=15):
    if not SHA.fullmatch(head_sha) or run_id < 1:
        raise ValueError("full lowercase SHA and positive run ID required")
    jobs = {"edition": parse_job(edition_log, "edition", head_sha, 1),
            "delivery": parse_job(delivery_log, "delivery", head_sha, delivery_groups)}
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
        "run_url": "https://github.com/{owner}/agentic-engineering-playbook/actions/runs/" + str(run_id),
    }


def annotate(records):
    """Positive saved seconds mean faster; raw changes are not causal estimates."""
    if not records:
        return []
    result = []
    original = records[0]
    previous = None
    for record in records:
        row = dict(record)
        for name, base in (("daily", previous), ("cumulative", original)):
            row[name + "_observed_saved_seconds"] = None if base is None else round(base["summed_test_seconds"] - record["summed_test_seconds"], 6)
            row[name + "_observed_reduction_percent"] = None if base is None else round(100 * (1 - record["summed_test_seconds"] / base["summed_test_seconds"]), 4)
            row[name + "_execution_count_change"] = None if base is None else record["executions"] - base["executions"]
        result.append(row)
        previous = record
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
    for row in annotate(records):
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
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("collect")
    add.add_argument("--edition-log", type=Path, required=True)
    add.add_argument("--delivery-log", type=Path, required=True)
    add.add_argument("--head-sha", required=True)
    add.add_argument("--run-id", type=int, required=True)
    add.add_argument("--edition-job-id", type=int, required=True)
    add.add_argument("--delivery-job-id", type=int, required=True)
    add.add_argument("--delivery-groups", type=int, default=15)
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
            row = collect(args.head_sha, args.run_id, args.edition_log.read_text(), args.delivery_log.read_text(), args.delivery_groups)
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
    except (ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

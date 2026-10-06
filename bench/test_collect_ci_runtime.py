"""Guards against misleading runtime histories from ordinary CI logs."""
import copy
import unittest
import json
from pathlib import Path
from functools import partial

from collect_ci_runtime import COMMANDS, MARKERS, annotate, collect, parse_job, render, run_url

collect = partial(collect, repository="example/playbook")

HEAD = "a" * 40
MERGE = "b" * 40


def log(suite, duration=5, start=0, checkout=HEAD, merge_head=None, status="OK", complete=True):
    values = [(0, "Current runner version: 'fixture'"), (0, "Image: ubuntu-24.04"),
              (0, "Version: fixture-image"), (0, "git version 2.55.0"),
              (0, "[command]/usr/bin/git log -1 --format=%H"), (0, checkout),
              (0, "Successfully set up CPython (3.12.14)")]
    if merge_head:
        values.append((0, "HEAD is now at fixture Merge " + merge_head + " into " + "c" * 40))
    values += [(1, "##[group]Run " + COMMANDS[suite]),
               (duration, "Ran 2 tests in 3.000s"), (duration, status)]
    if complete:
        values.append((duration, MARKERS[suite]))
    values.append((duration + 1, "Complete job"))
    return "\n".join(f"2026-10-01T00:00:{start + t:02d}.0000000Z {value}" for t, value in values)


class RuntimeCollectorTests(unittest.TestCase):
    def test_parallel_elapsed_is_union_not_sum_and_test_time_is_separate(self):
        row = collect(HEAD, 10, log("edition", duration=5), log("delivery", duration=9, start=2), 1)
        self.assertEqual(row["summed_test_seconds"], 6)
        self.assertEqual(row["parallel_jobs_log_span_seconds"], 12)
        self.assertEqual(sum(j["job_log_span_seconds"] for j in row["jobs"].values()), 16)
        self.assertEqual(row["jobs"]["delivery"]["verification_log_span_seconds"], 8)
        self.assertIsNone(row["queue_seconds"])
        self.assertIsNone(row["overall_workflow_wall_seconds"])

    def test_partial_failed_skipped_and_changed_commands_are_rejected(self):
        cases = [log("delivery", complete=False), log("delivery", status="FAILED (failures=1)"),
                 log("delivery", status="OK (skipped=1)"),
                 log("delivery").replace("--set K4.1", "--set A-cloud")]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_job(raw, "delivery", HEAD, 1)
        with self.assertRaisesRegex(ValueError, "expected 15"):
            parse_job(log("delivery"), "delivery", HEAD, 15)

    def test_synthetic_merge_requires_head_attestation_and_same_checkout(self):
        for attested in (None, "d" * 40):
            with self.assertRaises(ValueError):
                parse_job(log("delivery", checkout=MERGE, merge_head=attested), "delivery", HEAD, 1)
        raw = log("delivery", checkout=MERGE, merge_head=HEAD)
        self.assertEqual(parse_job(raw, "delivery", HEAD, 1)["checked_out_sha"], MERGE)
        with self.assertRaisesRegex(ValueError, "same checkout"):
            collect(HEAD, 10, log("edition"), raw, 1)

    def test_missing_timestamp_or_checkout_is_rejected(self):
        for raw in ("Ran 2 tests in 3.000s\nOK", log("edition").replace(HEAD, "unknown")):
            with self.assertRaises(ValueError):
                parse_job(raw, "edition", HEAD, 1)

    def test_growth_and_regression_are_not_hidden_or_normalized(self):
        first = collect(HEAD, 10, log("edition"), log("delivery"), 1)
        second = copy.deepcopy(first)
        second.update(run_id=11, run_url=run_url("example/playbook", 11), executions=5, summed_test_seconds=9)
        rows = annotate([first, second])
        self.assertEqual(rows[1]["daily_observed_saved_seconds"], -3)
        self.assertEqual(rows[1]["cumulative_observed_reduction_percent"], -50)
        self.assertEqual(rows[1]["daily_execution_count_change"], 1)
        self.assertEqual(first["executions"], 4)
        self.assertIn("not controlled or causal", render([first, second]))

    def test_gh_run_view_job_and_step_prefixes_are_supported(self):
        raw = log("edition")
        prefixed = "\n".join("edition\tVerify public edition\t" + line for line in raw.splitlines())
        expected = parse_job(raw, "edition", HEAD, 1)
        actual = parse_job(prefixed, "edition", HEAD, 1)
        self.assertNotEqual(actual.pop("source_log_sha256"), expected.pop("source_log_sha256"))
        self.assertEqual(actual, expected)

    def test_evidence_urls_are_concrete_and_match_run_ids(self):
        row = collect(HEAD, 10, log("edition"), log("delivery"), 1)
        self.assertEqual(row["run_url"], "https://github.com/example/playbook/actions/runs/10")
        self.assertIn("[run 10](" + row["run_url"] + ")", render([row]))
        for repository in ("{owner}/playbook", "example/{repository}", "example/playbook?other", ""):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                run_url(repository, 10)
        for url in ("https://github.com/{owner}/playbook/actions/runs/10",
                    "https://github.com/example/playbook/actions/runs/11"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                render([{**row, "run_url": url}])

    def test_checked_in_history_has_renderable_evidence_links(self):
        root = Path(__file__).parent / "test-runtime"
        records = json.loads((root / "suite-history.json").read_text())["records"]
        report = render(records)
        self.assertEqual(report, (root / "TOTAL-RUNTIME.md").read_text())
        self.assertNotIn("{owner}", report)
        for row in records:
            self.assertIn(f'[run {row["run_id"]}]({row["run_url"]})', report)

    def test_public_metadata_and_source_binding(self):
        job = parse_job(log("edition"), "edition", HEAD, 1)
        self.assertEqual(job["python"], "3.12.14")
        self.assertEqual(job["runner_image_version"], "fixture-image")
        self.assertEqual(len(job["source_log_sha256"]), 64)
        self.assertNotIn("source_path", job)


class ParallelRuntimeTests(unittest.TestCase):
    root = Path(__file__).parent / "test-runtime"
    head = "a89fd242ae2e87caed987359e65e7a454203c5cf"

    def setUp(self):
        self.manifest = json.loads((self.root / "manifests" / (self.head + ".json")).read_text())
        self.logs = {s: (self.root / "fixtures" / ("pr14-" + s + ".log")).read_text()
                     for s in ("edition", "delivery")}

    def row(self, **kwargs):
        return collect(self.head, 37138186128, self.logs["edition"], self.logs["delivery"],
                       suite_manifest=kwargs.get("manifest", self.manifest))

    def test_real_parallel_excerpts_are_complete(self):
        row = self.row()
        self.assertEqual(row["executions"], 1153)
        self.assertEqual(row["summed_test_seconds"], 2218.484)
        self.assertEqual([len(row["jobs"][s]["groups"]) for s in self.logs], [41, 15])
        self.assertEqual([row["jobs"][s]["executions"] for s in self.logs], [616, 537])
        self.assertEqual(row["jobs"]["edition"]["concurrent_workers"], 3)
        self.assertGreater(row["summed_test_seconds"], row["parallel_jobs_log_span_seconds"])

    def test_manifest_is_required_and_bound_to_revision_and_counts(self):
        with self.assertRaises(ValueError):
            self.row(manifest=None)
        for change in ("head", "count", "missing", "duplicate"):
            manifest = copy.deepcopy(self.manifest)
            if change == "head": manifest["head_sha"] = "e" * 40
            if change == "count": manifest["suites"]["edition"]["modules"][0]["executions"] += 1
            if change == "missing": manifest["suites"]["edition"]["modules"].pop()
            if change == "duplicate": manifest["suites"]["edition"]["modules"][1] = manifest["suites"]["edition"]["modules"][0]
            with self.subTest(change=change), self.assertRaises(ValueError): self.row(manifest=manifest)

    def test_missing_duplicate_failed_skipped_mislabelled_shards_rejected(self):
        raw = self.logs["edition"]
        cases = [raw.replace("Test shard 1/41:", "Test shard 2/41:"),
                 raw.replace("test_audit_upstream_installed.py", "test_unknown.py"),
                 raw.replace("(exit 0)", "(exit 1)", 1),
                 raw.replace("OK", "OK (skipped=1)", 1),
                 raw.replace("Ran 3 tests in 0.019s", "Ran 2 tests in 0.019s"),
                 raw.replace("Playbook release-readiness checks passed.", ""),
                 raw.replace("--jobs 3", "--jobs 0"),
                 raw.replace("--jobs 3", "--jobs 3 --other"),
                 raw.replace("Scheduled test shard 1/41:", "Missing test shard 1/41:")]
        for value in cases:
            self.logs["edition"] = value
            with self.subTest(value=value[:30]), self.assertRaises(ValueError): self.row()

    def test_real_failed_run_never_enters_history(self):
        raw = (self.root / "fixtures" / "pr14-failed-edition.log").read_text()
        self.assertIn("FAILED (failures=12)", raw)
        with self.assertRaises(ValueError):
            parse_job(raw, "edition", self.head, 1)

    def test_missing_and_duplicate_summaries_and_schedules(self):
        original = self.logs["edition"]
        schedule = next(line for line in original.splitlines() if "Scheduled test shard 1/41:" in line)
        summary = next(line for line in original.splitlines() if "Ran 3 tests in 0.019s" in line)
        for raw in (original.replace(schedule, ""), original.replace(schedule, schedule + "\n" + schedule),
                    original.replace(summary, ""), original.replace(summary, summary + "\n" + summary),
                    original.replace("--skip-delivery --jobs 3", "--skip-delivery"),
                    original + "2026-10-03T16:58:00.0000000Z ##[error]Post step failed\n"):
            self.logs["edition"] = raw
            with self.assertRaises(ValueError): self.row()

    def test_parallel_cli_prefixes_preserve_extraction(self):
        expected = self.row()
        self.logs = {s: "\n".join(s + "\tVerify suite\t" + line for line in raw.splitlines())
                     for s, raw in self.logs.items()}
        actual = self.row()
        for suite in self.logs:
            actual["jobs"][suite].pop("source_log_sha256")
            expected["jobs"][suite].pop("source_log_sha256")
        self.assertEqual(actual, expected)

    def test_historical_serial_records_are_unchanged(self):
        records = json.loads((self.root / "suite-history.json").read_text())["records"]
        daily = next(r for r in records if r["run_id"] == 37086875919)
        self.assertEqual(daily["summed_test_seconds"], 803.053)
        self.assertFalse(any(r["run_id"] == 37135602912 for r in records))
        parallel = next(r for r in annotate(records) if r["run_id"] == 37138186128)
        self.assertEqual(parallel["daily_execution_count_change"], 391)

    def test_serial_comparison_survives_interleaved_parallel_record(self):
        records = json.loads((self.root / "suite-history.json").read_text())["records"]
        rows = annotate(records)
        oct4 = next(r for r in rows if r["run_id"] == 37169647763)
        self.assertEqual(oct4["daily_observed_saved_seconds"], -188.309)
        report = render(records)
        self.assertLess(report.index("[run 37169647763]"), report.index("[run 37138186128]"))

    def test_concurrency_starts_separate_comparison_baseline(self):
        serial = collect(HEAD, 10, log("edition"), log("delivery"), 1)
        parallel = self.row()
        rows = annotate([serial, parallel])
        self.assertIsNone(rows[1]["daily_observed_saved_seconds"])
        self.assertIsNone(rows[1]["cumulative_observed_reduction_percent"])
        self.assertEqual(rows[1]["daily_execution_count_change"], 1149)


if __name__ == "__main__":
    unittest.main()

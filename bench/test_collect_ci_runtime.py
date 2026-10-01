"""Guards against misleading runtime histories from ordinary CI logs."""
import copy
import unittest

from collect_ci_runtime import COMMANDS, MARKERS, annotate, collect, parse_job, render

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
        second.update(run_id=11, executions=5, summed_test_seconds=9)
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

    def test_public_metadata_and_source_binding(self):
        job = parse_job(log("edition"), "edition", HEAD, 1)
        self.assertEqual(job["python"], "3.12.14")
        self.assertEqual(job["runner_image_version"], "fixture-image")
        self.assertEqual(len(job["source_log_sha256"]), 64)
        self.assertNotIn("source_path", job)


if __name__ == "__main__":
    unittest.main()

"""Behaviour checks at the profiler's fresh-process CLI seam."""
import json
from contextlib import contextmanager
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROFILER = Path(__file__).with_name("profile_delivery_tests.py")


class ProfilerCLI(unittest.TestCase):
    @contextmanager
    def fixture(self, source, *options):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "v0.5/delivery/tests"
            tests.mkdir(parents=True)
            scripts = root / "v0.5/delivery/scripts"
            scripts.mkdir()
            (root / "v0.5/scripts").mkdir()
            scripts.joinpath("verify.py").write_text('SETS = {"K4.1": ("test_probe.py",)}\n')
            tests.joinpath("test_probe.py").write_text(source)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Profiler Fixture",
                            "-c", "user.email=fixture@users.noreply.github.com", "commit", "-q",
                            "--allow-empty", "-m", "Fixture"], check=True)
            output = root / "report.json"
            result = subprocess.run([sys.executable, str(PROFILER), "--root", str(root),
                                     "--repeat", "1", "--output", str(output), *options],
                                    text=True, capture_output=True)
            yield result, json.loads(output.read_text())

    def test_valid_subprocess_call_forms_and_failed_attempts(self):
        source = '''import subprocess
import unittest
class Probe(unittest.TestCase):
    def test_forms(self):
        for argv in (["git", "--version"], [b"git", b"--version"]):
            result = subprocess.run(args=argv, capture_output=True, check=True)
            self.assertTrue(result.stdout.startswith(b"git version"))
        with self.assertRaises(subprocess.CalledProcessError) as error:
            subprocess.run(["git", "clone", "/missing-private-canary"], capture_output=True, check=True)
        self.assertEqual(error.exception.returncode, 128)
'''
        with self.fixture(source, "--git-diagnostics") as (result, report):
            self.assertEqual(result.returncode, 0, result.stderr)
            measured = report["repetitions"][0][0]
            self.assertEqual(len(measured["git_samples"]), 3)
            self.assertEqual(measured["git_counts"]["clone"], 1)
            self.assertEqual(measured["git_samples"][-1]["returncode"], 128)
            self.assertNotIn("private-canary", json.dumps(report))

    def test_os_metadata_is_bounded_and_has_no_urls(self):
        with self.fixture('import unittest\nclass Probe(unittest.TestCase):\n def test_pass(self): pass\n') as (result, report):
            self.assertEqual(result.returncode, 0)
            self.assertLessEqual(set(report["runner"]["os"]), {"ID", "VERSION_ID", "NAME", "VERSION", "PRETTY_NAME"})
            self.assertNotIn("https://", json.dumps(report))

    def test_empty_file_and_missing_guidance_group_fail(self):
        for options in (("--pattern", "test_missing_*.py"), ("--group", "guidance")):
            with self.subTest(options=options), self.fixture('', *options) as (result, report):
                self.assertEqual(result.returncode, 1)
                self.assertTrue(all(not row["successful"] for row in report["repetitions"][0]))
                self.assertTrue(all(row["selection_error"] == "empty-selection" for row in report["repetitions"][0]))

    def test_class_identity_survives_failed_class_setup(self):
        source = '''import subprocess
import unittest
class A(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        raise RuntimeError("private-error")
    def test_pass(self): pass
class B(A): pass
'''
        with self.fixture(source, "--git-diagnostics") as (result, report):
            self.assertEqual(result.returncode, 1)
            measured = report["repetitions"][0][0]
            self.assertEqual(measured["errors"], 2)
            self.assertEqual(measured["tests"], [])
            self.assertEqual([s["class_id"] for s in measured["git_samples"]], ["test_probe.A", "test_probe.B"])
            self.assertTrue(all(s["phase"] == "class-setup" for s in measured["git_samples"]))

    def test_concurrent_git_calls_have_unique_ordered_samples(self):
        source = '''import subprocess, sys
from concurrent.futures import ThreadPoolExecutor
import unittest
class Probe(unittest.TestCase):
    def test_calls(self):
        sys.setswitchinterval(0.000001)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: subprocess.run(["git", "--version"], capture_output=True, check=True), range(80)))
        self.assertEqual(len(results), 80)
'''
        with self.fixture(source, "--git-diagnostics") as (result, report):
            self.assertEqual(result.returncode, 0)
            samples = report["repetitions"][0][0]["git_samples"]
            self.assertEqual([s["sequence"] for s in samples], list(range(1, 81)))
            self.assertTrue(all(s["returncode"] == 0 for s in samples))

    def test_real_git_attribution_subtest_failure_and_private_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "v0.5/delivery/tests"
            tests.mkdir(parents=True)
            scripts = root / "v0.5/delivery/scripts"
            scripts.mkdir()
            scripts.joinpath("verify.py").write_text('SETS = {"K4.1": ("test_probe.py",)}\n')
            scripts.joinpath("generate.py").write_text('')
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Profiler Fixture",
                            "-c", "user.email=fixture@users.noreply.github.com", "commit", "-q",
                            "--allow-empty", "-m", "Fixture"], check=True)
            tests.joinpath("test_probe.py").write_text('''import subprocess
import tempfile
from pathlib import Path
import unittest
class Probe(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="private-marker-")
        self.addCleanup(self.temp.cleanup)
        self.remote = Path(self.temp.name) / "secret-remote.git"
        subprocess.run(["git", "init", "--bare", str(self.remote)], capture_output=True, check=True)
    def test_matrix(self):
        for value in ("secret-subtest-one", "secret-subtest-two"):
            with self.subTest(value=value):
                result = subprocess.run(["git", "ls-remote", str(self.remote)], capture_output=True, check=True)
                self.assertEqual(result.stdout, b"")
                self.assertEqual(value, "secret-subtest-one")
''')
            output = root / "report.json"
            result = subprocess.run([sys.executable, str(PROFILER), "--root", str(root),
                                     "--repeat", "1", "--git-diagnostics", "--output", str(output)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            report = json.loads(output.read_text())
            measured = report["repetitions"][0][0]
            self.assertFalse(measured["successful"])
            self.assertEqual(measured["tests"][0]["outcome"], "failed")
            self.assertEqual(measured["git_counts"]["ls-remote"], 2)
            samples = measured["git_samples"]
            self.assertEqual([s["category"] for s in samples], ["init", "ls-remote", "ls-remote"])
            self.assertEqual([s["phase"] for s in samples], ["setup", "test", "test"])
            self.assertEqual([s["subtest"] for s in samples], [None, 1, 2])
            self.assertGreaterEqual(measured["wall_seconds"], measured["seconds"])
            self.assertEqual(report["measurement_mode"], "diagnostic")
            for private in (directory, "private-marker-", "secret-remote", "secret-subtest"):
                self.assertNotIn(private, output.read_text())
                self.assertNotIn(private, result.stdout)

    def test_uninstrumented_complete_selection_and_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            result = subprocess.run([sys.executable, str(PROFILER), "--test",
                                     "test_core.CanonicalTests.test_nonexistent", "--repeat", "1",
                                     "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            report = json.loads(output.read_text())
            self.assertEqual(report["measurement_mode"], "timing")
            self.assertEqual(report["workers"], 1)
            measured = report["repetitions"][0][0]
            self.assertNotIn("git_samples", measured)
            self.assertGreater(measured["wall_seconds"], measured["seconds"])


if __name__ == "__main__":
    unittest.main()

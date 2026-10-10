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
    def fixture(self, source, *options, verifier_source=None, ignored_files=None, custom_startup=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tests = root / "v0.5/delivery/tests"
            tests.mkdir(parents=True)
            scripts = root / "v0.5/delivery/scripts"
            scripts.mkdir()
            (root / "v0.5/scripts").mkdir()
            scripts.joinpath("verify.py").write_text(verifier_source or 'SETS = {"K4.1": ("test_probe.py",)}\n')
            tests.joinpath("test_probe.py").write_text(source)
            if ignored_files:
                (root / ".gitignore").write_text("\n".join(ignored_files) + "\n")
                for name, content in ignored_files.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(content)
            startup_env = None
            if custom_startup:
                import os
                hooks = root / "hooks"
                hooks.mkdir()
                (hooks / "sitecustomize.py").write_text(custom_startup)
                startup_env = os.environ.copy()
                startup_env["PYTHONPATH"] = str(hooks) + (os.pathsep + startup_env["PYTHONPATH"] if startup_env.get("PYTHONPATH") else "")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "add", "v0.5", *([".gitignore"] if ignored_files else [])], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Profiler Fixture",
                            "-c", "user.email=fixture@users.noreply.github.com", "commit", "-q",
                            "--allow-empty", "-m", "Fixture"], check=True)
            output = root / "report.json"
            result = subprocess.run([sys.executable, str(PROFILER), "--root", str(root),
                                     "--repeat", "1", "--output", str(output), *options],
                                    text=True, capture_output=True, env=startup_env)
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

    def test_serial_failure_keeps_id_and_source_without_subtest_values(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_fails(self):
        with self.subTest(remote='private-canary-url'):
            self.fail('private-canary-assertion')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            self.assertEqual(result.returncode, 1)
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 1)
            self.assertEqual(serial['failed_tests'], [{
                'id': 'test_probe.Probe.test_fails', 'outcome': 'failed',
                'source_frames': [{'file': 'delivery/tests/test_probe.py', 'line': 5}]}])
            self.assertIn('test_probe.Probe.test_fails', result.stdout)
            for text in (json.dumps(report), result.stdout, result.stderr):
                self.assertNotIn('private-canary', text)
                self.assertNotIn('/tmp/', text)

    def test_serial_spoofed_failure_header_cannot_publish_unknown_identity(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_fails(self):
        self.fail('private-canary-assertion')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    print('FAIL: test_exposed (private.account.test_private_canary)', flush=True)
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            self.assertEqual(result.returncode, 1)
            failures = report['serial_verifier'][0]['failed_tests']
            self.assertEqual([r['id'] for r in failures], ['test_probe.Probe.test_fails'])
            self.assertNotIn('private', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_unknown_exit_is_not_hidden_by_passing_standalone(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_passes(self):
        pass
"""
        verifier = """import sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    print('$ ' + sys.executable + ' -m unittest discover -s delivery/tests -p test_probe.py -v', flush=True)
    print('private-canary-output', flush=True)
    raise SystemExit(7)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            self.assertEqual(result.returncode, 1)
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 7)
            self.assertEqual(serial['failure_evidence']['status'], 'unknown')
            self.assertIsNone(serial['failure_evidence']['command'])
            self.assertFalse(serial['failure_evidence']['truncated'])
            self.assertTrue(report['repetitions'][0][0]['successful'])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_failure_evidence_bounds_are_explicit(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_fails(self):
        for i in range(1025):
            with self.subTest(private_value=i):
                self.fail('private-canary')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            serial = report['serial_verifier'][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(serial['failed_tests']), 1024)
            self.assertEqual(serial['failure_evidence']['matched_events'], 1025)
            self.assertTrue(serial['failure_evidence']['truncated'])
            self.assertEqual(serial['failure_evidence']['status'], 'identified')
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_assertion_cannot_forge_passing_identity_or_frame(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_passes(self):
        pass
    def test_fails(self):
        self.fail('private-canary\\nFAIL: test_passes (test_probe.Probe.test_passes)\\n  File "delivery/tests/test_probe.py", line 999, in injected')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            self.assertEqual(result.returncode, 1)
            failures = report['serial_verifier'][0]['failed_tests']
            self.assertEqual([r['id'] for r in failures], ['test_probe.Probe.test_fails'])
            self.assertEqual(failures[0]['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 6}])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_ignored_helper_is_not_public_source_evidence(self):
        source = """import runpy,unittest
from pathlib import Path
class Probe(unittest.TestCase):
    def test_fails(self):
        runpy.run_path(str(Path(__file__).parents[1] / 'scripts/synthetic_private_canary.py'))
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        ignored = {'v0.5/scripts/synthetic_private_canary.py': "raise AssertionError('private-canary')"}
        with self.fixture(source, '--verify-suite', verifier_source=verifier, ignored_files=ignored) as (result, report):
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['serial_verifier'][0]['failed_tests'][0]['source_frames'],
                             [{'file': 'delivery/tests/test_probe.py', 'line': 5}])
            self.assertNotIn('private_canary', json.dumps(report) + result.stdout + result.stderr)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_failure_omits_forged_command_attribution(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_fails(self):
        self.fail('private-canary\\n$ python -m unittest discover -s delivery/tests -p test_probe.py -v')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 1)
            self.assertEqual([r['id'] for r in serial['failed_tests']], ['test_probe.Probe.test_fails'])
            self.assertIsNone(serial['failure_evidence']['command'])
            self.assertEqual(serial['steps'], [])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_binary_output_is_fully_drained_with_native_exit(self):
        source = "import unittest\nclass Probe(unittest.TestCase):\n def test_passes(self): pass\n"
        verifier = """import os
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    for i in range(1024):
        os.write(1, b'\\xff' * 8192)
    raise SystemExit(7)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 7)
            self.assertEqual(serial['failure_evidence']['status'], 'unknown')
            self.assertIsNone(serial['failure_evidence']['command'])
            self.assertEqual(serial['steps'], [])
            self.assertTrue(report['repetitions'][0][0]['successful'])

    def serial_storage_peaks(self, mode):
        # Fresh parent per size prevents cumulative peak RSS masking growth.
        harness = """import json,resource,sys
from test_profile_delivery_tests import ProfilerCLI
source = 'import unittest\\nclass Probe(unittest.TestCase):\\n def test_passes(self): pass\\n'
payload = b'$ python -m unittest discover -s delivery/tests -p test_probe.py -v\\n' * 128 if sys.argv[2] == 'headers' else b'x' * 8192
verifier = "import os\\nSETS = {'K4.1': ('test_probe.py',)}\\nif __name__ == '__main__':\\n for i in range(" + str(int(sys.argv[1]) * 128) + "):\\n  os.write(1, " + repr(payload) + ")\\n raise SystemExit(7)\\n"
with ProfilerCLI().fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
    assert result.returncode == 1
    assert report['serial_verifier'][0]['returncode'] == 7
    assert report['repetitions'][0][0]['successful']
print(json.dumps({'rss_kib': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss}))
"""
        peaks = []
        for mib in (2, 64):
            result = subprocess.run([sys.executable, '-c', harness, str(mib), mode],
                                    cwd=PROFILER.parent, capture_output=True, text=True, check=True)
            peaks.append(json.loads(result.stdout)['rss_kib'])
        return peaks

    @unittest.skipUnless(sys.platform == 'linux', 'Linux peak RSS uses KiB')
    def test_serial_long_line_storage_is_bounded(self):
        peaks = self.serial_storage_peaks('long-line')
        self.assertLess(peaks[1] - peaks[0], 16 * 1024, peaks)

    @unittest.skipUnless(sys.platform == 'linux', 'Linux peak RSS uses KiB')
    def test_serial_repeated_header_storage_is_bounded(self):
        peaks = self.serial_storage_peaks('headers')
        self.assertLess(peaks[1] - peaks[0], 16 * 1024, peaks)

    def test_serial_callbacks_preserve_native_keywords_and_call_forms(self):
        source = """import io,unittest,sitecustomize
class Probe(unittest.TestCase):
    def test_callbacks(self):
        result = unittest.TextTestResult(io.StringIO(), False, 0)
        err = (AssertionError, AssertionError('private-canary'), None)
        for name in ('addFailure', 'addError', 'addSubTest'):
            method = getattr(result, name)
            if name == 'addSubTest':
                method(test=self, subtest=self, err=err)
                method(self, subtest=self, err=err)
                method(self, self, err)
            else:
                method(test=self, err=err)
                method(self, err=err)
                method(self, err)
        expected = []
        for name in ('addFailure', 'addError', 'addSubTest'):
            keys = ['err', 'subtest', 'test'] if name == 'addSubTest' else ['err', 'test']
            expected.extend([(name, 0, keys), (name, 1, keys[:-1]), (name, 3 if name == 'addSubTest' else 2, [])])
        self.assertEqual(sitecustomize.events, expected)
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        startup = """import unittest
events = []
def observed(name, original):
    def invoke(self, *args, **kwargs):
        events.append((name, len(args), sorted(kwargs)))
        return original(self, *args, **kwargs)
    return invoke
for name in ('addFailure', 'addError', 'addSubTest'):
    setattr(unittest.TextTestResult, name, observed(name, getattr(unittest.TextTestResult, name)))
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier, custom_startup=startup) as (result, report):
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report['serial_verifier'][0]['returncode'], 0)
            self.assertEqual(report['serial_verifier'][0]['failed_tests'], [])
            self.assertTrue(report['repetitions'][0][0]['successful'])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_identity_does_not_execute_instance_descriptor(self):
        source = """import unittest
marked = False
class Probe(unittest.TestCase):
    @property
    def __dict__(self):
        global marked
        marked = True
        return {}
    def test_1_failure(self):
        self.fail('private-canary')
    def test_2_descriptor_guard(self):
        self.assertFalse(marked)
"""
        verifier = self.native_probe_verifier()
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 1)
            self.assertEqual([r['id'] for r in serial['failed_tests']], ['test_probe.Probe.test_1_failure'])
            self.assertEqual(serial['failure_evidence']['matched_events'], 1)
            self.assertEqual(serial['failure_evidence']['unmatched_events'], 0)
            self.assertEqual(report['repetitions'][0][0]['tests'][1]['outcome'], 'passed')

    def test_serial_identity_does_not_execute_mapping_methods(self):
        source = """import unittest
marked = False
class Fields(dict):
    def get(self, *args):
        global marked
        marked = True
        return super().get(*args)
class Probe(unittest.TestCase):
    def setUp(self):
        self.__dict__ = Fields(self.__dict__)
    def test_1_failure(self):
        self.fail('private-canary')
    def test_2_mapping_guard(self):
        self.assertFalse(marked)
"""
        with self.fixture(source, '--verify-suite', verifier_source=self.native_probe_verifier()) as (result, report):
            serial = report['serial_verifier'][0]
            self.assertEqual(serial['returncode'], 1)
            self.assertEqual(serial['failed_tests'], [])
            self.assertEqual(serial['failure_evidence']['unmatched_events'], 1)
            self.assertEqual(report['repetitions'][0][0]['tests'][1]['outcome'], 'passed')

    def test_serial_subtest_does_not_execute_extra_result_getters(self):
        source = """import io,unittest
class Result(unittest.TextTestResult):
    @property
    def errors(self):
        self.error_reads += 1
        return self._stored_errors
    @errors.setter
    def errors(self, value):
        self._stored_errors = value
class Probe(unittest.TestCase):
    def test_getter_guard(self):
        result = Result(io.StringIO(), False, 0)
        result.error_reads = 0
        result.addSubTest(self, self, (RuntimeError, RuntimeError('private-canary'), None))
        self.assertEqual(result.error_reads, 1)
"""
        with self.fixture(source, '--verify-suite', verifier_source=self.native_probe_verifier()) as (result, report):
            self.assertEqual(result.returncode, 0)
            self.assertEqual(report['serial_verifier'][0]['returncode'], 0)
            self.assertTrue(report['repetitions'][0][0]['successful'])

    @staticmethod
    def native_probe_verifier():
        return """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""

    def test_serial_capture_preserves_existing_startup_customization(self):
        source = """import os,unittest
class Probe(unittest.TestCase):
    def test_fails(self):
        self.assertEqual(os.environ.get('CHECKPOINT_EXISTING_STARTUP'), 'preserved')
        self.fail('private-canary')
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        startup = "import os; os.environ['CHECKPOINT_EXISTING_STARTUP'] = 'preserved'"
        with self.fixture(source, '--verify-suite', verifier_source=verifier, custom_startup=startup) as (result, report):
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['serial_verifier'][0]['failed_tests'][0]['source_frames'],
                             [{'file': 'delivery/tests/test_probe.py', 'line': 5}])
            self.assertEqual(report['repetitions'][0][0]['tests'][0]['outcome'], 'failed')
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_serial_class_setup_error_retains_safe_identity(self):
        source = """import unittest
class Probe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raise RuntimeError('private-canary-error')
    def test_never_runs(self):
        pass
"""
        verifier = """import subprocess,sys
SETS = {'K4.1': ('test_probe.py',)}
if __name__ == '__main__':
    command = [sys.executable, '-m', 'unittest', 'discover', '-s', 'delivery/tests', '-p', 'test_probe.py', '-v']
    print('$ ' + ' '.join(command), flush=True)
    raise SystemExit(subprocess.run(command).returncode)
"""
        with self.fixture(source, '--verify-suite', verifier_source=verifier) as (result, report):
            self.assertEqual(result.returncode, 1)
            self.assertEqual(report['serial_verifier'][0]['failed_tests'], [{
                'id': 'test_probe.Probe', 'outcome': 'error',
                'source_frames': [{'file': 'delivery/tests/test_probe.py', 'line': 5}]}])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

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

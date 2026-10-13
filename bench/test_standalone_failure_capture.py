"""Standalone native failure evidence at the fresh-process profiler CLI seam."""
import json
import unittest

import test_profile_delivery_tests as existing


class StandaloneEvidence(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def test_native_error_receipt_preserves_suite_and_process_distinction(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_error(self):
        raise RuntimeError('private-canary-error')
"""
        with self.fixture(source) as (result, report):
            self.assertEqual(result.returncode, 1)
            measured = report['repetitions'][0][0]
            self.assertEqual(measured['worker_returncode'], 0)
            self.assertFalse(measured['successful'])
            self.assertEqual((measured['errors'], measured['failures']), (1, 0))
            self.assertEqual(measured['failed_tests'], [{
                'id': 'test_probe.Probe.test_error', 'outcome': 'error',
                'module_id': 'test_probe', 'class_id': 'test_probe.Probe',
                'phase': 'test', 'exception_type': 'RuntimeError',
                'source_frames': [{'file': 'delivery/tests/test_probe.py', 'line': 4}]}])
            self.assertEqual(measured['failure_evidence']['matched_events'], 1)
            self.assertEqual(measured['failure_evidence']['unmatched_events'], 0)
            self.assertFalse(measured['failure_evidence']['truncated'])
            self.assertEqual(measured['failure_evidence']['status'], 'identified')
            self.assertIn('test_probe.Probe.test_error', result.stdout)
            self.assertIn('RuntimeError', result.stdout)
            self.assertGreaterEqual(measured['wall_seconds'], measured['seconds'])
            self.assertNotIn('git_samples', measured)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)


class NativeBoundaries(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture
    def test_failure_and_failing_subtest_have_native_kinds(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_failure(self):
        self.fail('private-canary-assertion')
    def test_subtest_error(self):
        with self.subTest(secret='private-canary-subtest'):
            raise ValueError('private-canary-value')
    def test_subtest_failure(self):
        with self.subTest(secret='private-canary-subtest'):
            self.assertEqual(1, 2, 'private-canary-assertion')
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual((row['failures'], row['errors']), (2, 1))
            events = row['failed_tests']
            self.assertEqual([e['id'] for e in events], [
                'test_probe.Probe.test_failure', 'test_probe.Probe.test_subtest_error',
                'test_probe.Probe.test_subtest_failure'])
            self.assertEqual([e['outcome'] for e in events], ['failed', 'error', 'failed'])
            self.assertEqual([e['exception_type'] for e in events], ['AssertionError', 'ValueError', 'AssertionError'])
            self.assertTrue(all(e['phase'] == 'test' for e in events))
            self.assertEqual([e['source_frames'][-1]['line'] for e in events], [4, 7, 10])
            self.assertTrue(all(e['outcome'] == 'failed' for e in row['tests']))
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_native_fixture_phases(self):
        cases = [
            ('setUpClass', 'class', 'setUpClass', 'test_probe.Probe'),
            ('tearDownClass', 'class', 'tearDownClass', 'test_probe.Probe'),
            ('setUpModule', 'module', 'setUpModule', 'test_probe'),
            ('tearDownModule', 'module', 'tearDownModule', 'test_probe'),
            ('setUp', 'instance', 'setup', 'test_probe.Probe.test_pass'),
            ('tearDown', 'instance', 'teardown', 'test_probe.Probe.test_pass'),
        ]
        for name, scope, phase, identity in cases:
            fixture = (f'def {name}():\n    raise RuntimeError("private-canary")\n'
                       if scope == 'module' else
                       ('    @classmethod\n' if scope == 'class' else '') +
                       f'    def {name}({"cls" if scope == "class" else "self"}):\n        raise RuntimeError("private-canary")\n')
            source = 'import unittest\n' + (fixture if scope == 'module' else '') + 'class Probe(unittest.TestCase):\n' + (fixture if scope != 'module' else '') + '    def test_pass(self): pass\n'
            with self.subTest(phase=phase), self.fixture(source) as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual(result.returncode, 1)
                self.assertEqual(row['worker_returncode'], 0)
                self.assertEqual(row['errors'], 1)
                event, = row['failed_tests']
                self.assertEqual((event['id'], event['phase'], event['exception_type']),
                                 (identity, phase, 'RuntimeError'))
                self.assertEqual(event['module_id'], 'test_probe')
                self.assertEqual(event['class_id'], None if scope == 'module' else 'test_probe.Probe')
                self.assertTrue(event['source_frames'])
                self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_native_cleanup_and_import_error(self):
        cleanup = """import unittest
class Probe(unittest.TestCase):
    def cleanup(self):
        raise OSError('private-canary')
    def test_pass(self):
        self.addCleanup(self.cleanup)
"""
        for source, identity, phase, kind in [
            (cleanup, 'test_probe.Probe.test_pass', 'cleanup', 'OSError'),
            ('raise RuntimeError("private-canary-import")\n',
             'unittest.loader._FailedTest.test_probe', 'import', 'ImportError')]:
            with self.subTest(phase=phase), self.fixture(source) as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual(result.returncode, 1)
                self.assertEqual(row['worker_returncode'], 0)
                self.assertEqual(row['errors'], 1)
                event, = row['failed_tests']
                self.assertEqual((event['id'], event['phase'], event['exception_type']), (identity, phase, kind))
                if phase == 'cleanup':
                    self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 4}])
                else:
                    # unittest wraps import failures and discards their traceback.
                    self.assertEqual(event['source_frames'], [])
                self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_private_and_symlink_frames_and_unknown_types_are_excluded(self):
        source = """import unittest
import hidden
class Probe(unittest.TestCase):
    def test_error(self):
        hidden.fail()
"""
        hidden = "class PrivateCanaryError(RuntimeError): pass\ndef fail():\n    raise PrivateCanaryError('private-canary-secret')\n"
        with self.fixture(source, ignored_files={'v0.5/delivery/tests/hidden.py': hidden}) as (result, report):
            event, = report['repetitions'][0][0]['failed_tests']
            self.assertEqual(event['exception_type'], 'unknown')
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 5}])
            self.assertNotIn('PrivateCanary', json.dumps(report) + result.stdout + result.stderr)
            self.assertNotIn('hidden.py', json.dumps(report) + result.stdout + result.stderr)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)
        source = """import os, pathlib, unittest
class Probe(unittest.TestCase):
    def test_error(self):
        target = pathlib.Path(__file__).resolve()
        link = target.parent / 'private-canary-link.py'
        link.symlink_to(target)
        exec(compile('raise RuntimeError("private-canary")', str(link), 'exec'))
"""
        with self.fixture(source) as (result, report):
            event, = report['repetitions'][0][0]['failed_tests']
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 7}])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_force_tracked_ignored_source_is_still_ineligible(self):
        source = """import unittest, hidden
class Probe(unittest.TestCase):
    def test_error(self): hidden.fail()
"""
        startup = """import subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[1]
subprocess.run(['git', '-C', str(root), 'add', '-f', 'v0.5/delivery/tests/hidden.py'], check=True)
"""
        with self.fixture(source, custom_startup=startup, ignored_files={
                'v0.5/delivery/tests/hidden.py': "def fail(): raise RuntimeError('private-canary')\n"}) as (result, report):
            event, = report['repetitions'][0][0]['failed_tests']
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 3}])
            self.assertNotIn('hidden.py', json.dumps(report) + result.stdout + result.stderr)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_event_and_frame_caps_remain_explicit(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_errors(self):
        for index in range(1025):
            with self.subTest(secret=index):
                raise RuntimeError('private-canary')
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['errors'], 1025)
            self.assertEqual(len(row['failed_tests']), 1024)
            self.assertEqual(row['failure_evidence']['matched_events'], 1025)
            self.assertTrue(row['failure_evidence']['truncated'])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)
        source = """import unittest
def recurse(n):
    if n: recurse(n-1)
    else: raise RuntimeError('private-canary')
class Probe(unittest.TestCase):
    def test_error(self): recurse(80)
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(len(row['failed_tests'][0]['source_frames']), 64)
            self.assertTrue(row['failure_evidence']['truncated'])

    def test_native_called_process_error_exports_only_trusted_returncode(self):
        source = """import subprocess, unittest
class Probe(unittest.TestCase):
    def test_error(self):
        raise subprocess.CalledProcessError(17, ['private-canary-argv'], output='private-canary-output', stderr='private-canary-stderr')
"""
        with self.fixture(source) as (result, report):
            event, = report['repetitions'][0][0]['failed_tests']
            self.assertEqual(event['exception_type'], 'CalledProcessError')
            self.assertEqual(event['subprocess_returncode'], 17)
            self.assertNotIn('git_category', event)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_callback_arguments_return_values_and_success_are_preserved(self):
        startup = """import unittest
calls = []
for name in ('addFailure', 'addError', 'addSubTest'):
    original = getattr(unittest.TextTestResult, name)
    def observe(self, *args, _name=name, _original=original, **kwargs):
        calls.append((_name, args, kwargs))
        _original(self, *args, **kwargs)
        return 73
    setattr(unittest.TextTestResult, name, observe)
"""
        source = """import io, sys, unittest, sitecustomize
class Probe(unittest.TestCase):
    def test_callbacks(self):
        result = unittest.TextTestResult(io.StringIO(), False, 0)
        error = (RuntimeError, RuntimeError('private-canary'), None)
        failure = (AssertionError, AssertionError('private-canary'), None)
        expected = [('addError', (), dict(test=self, err=error)),
                    ('addFailure', (self, failure), {}),
                    ('addSubTest', (), dict(test=self, subtest=self, err=error)),
                    ('addSubTest', (self, self, None), {})]
        for name, args, kwargs in expected:
            self.assertEqual(getattr(result, name)(*args, **kwargs), 73)
        self.assertEqual(sitecustomize.calls, expected)
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            self.assertEqual(result.returncode, 0, result.stderr)
            row = report['repetitions'][0][0]
            self.assertEqual(row['worker_returncode'], 0)
            self.assertTrue(row['successful'])
            self.assertEqual(row['tests'][0]['outcome'], 'passed')
            self.assertEqual(row['failure_evidence']['matched_events'], 0)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertEqual(row['failed_tests'], [])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_unsupported_native_fields_are_counted_without_getters(self):
        source = """import unittest
marked = False
class Fields(dict):
    def get(self, *args):
        global marked
        marked = True
        return super().get(*args)
class Probe(unittest.TestCase):
    def setUp(self): self.__dict__ = Fields(self.__dict__)
    def test_1_error(self): raise RuntimeError('private-canary')
    def test_2_guard(self): self.assertFalse(marked)
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['failed_tests'], [])
            self.assertEqual(row['failure_evidence']['status'], 'unknown')
            self.assertEqual(row['failure_evidence']['unmatched_events'], 1)
            self.assertEqual(row['tests'][1]['outcome'], 'passed')


    def test_instance_descriptor_is_not_read_by_capture(self):
        source = """import unittest
marked = False
class Probe(unittest.TestCase):
    @property
    def __dict__(self):
        global marked
        marked = True
        return {}
    def test_1_error(self): raise RuntimeError('private-canary')
    def test_2_guard(self): self.assertFalse(marked)
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['failure_evidence']['matched_events'], 1)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertEqual(row['tests'][1]['outcome'], 'passed')

    def test_pass_skip_expected_failure_and_unexpected_success_gates(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_pass(self): pass
    @unittest.skip('private-canary')
    def test_skip(self): pass
    @unittest.expectedFailure
    def test_expected(self): self.fail('private-canary')
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 0)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual([e['outcome'] for e in row['tests']], ['expected-failure', 'passed', 'skipped'])
            self.assertEqual(row['failed_tests'], [])
            self.assertEqual(row['failure_evidence']['status'], 'passed')
            self.assertEqual(row['failure_evidence']['matched_events'], 0)
            self.assertNotIn('git_samples', row)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)
        source += "    @unittest.expectedFailure\n    def test_unexpected(self): pass\n"
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertFalse(row['successful'])
            self.assertEqual(row['tests'][-1]['outcome'], 'unexpected-success')
            self.assertEqual(row['failure_evidence']['status'], 'unknown')
            self.assertEqual(row['failed_tests'], [])

    def test_serial_shim_preserves_ineligible_interpreter_initial_modules(self):
        from pathlib import Path
        import os
        import subprocess
        import sys
        import tempfile
        import profile_delivery_tests as profiler
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'root': str(root), 'owner': str(root/'owner'),
                      'verifier': str(root/'verify.py'), 'output': str(root/'events.json'),
                      'identities': [], 'sources': []}
            (root/'config.json').write_text(json.dumps(config))
            (root/'sitecustomize.py').write_text(
                'CAPTURE_PATH = ' + repr(str(Path(profiler.__file__).with_name('serial_failure_capture.py'))) +
                '\n' + profiler.SERIAL_STARTUP)
            source = "import json,sys\nprint(json.dumps({name:name in sys.modules for name in ('unittest','subprocess')}))\n"
            (root/'verify.py').write_text(source)
            env = dict(os.environ, PYTHONPATH=str(root),
                       CHECKPOINT_SERIAL_FAILURE_CONFIG=str(root/'config.json'))
            for tail in ([str(root/'verify.py')], ['-c', source]):
                with self.subTest(tail=tail[:1]):
                    result = subprocess.run([sys.executable, *tail], cwd=root, env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stderr, '')
                    self.assertEqual(json.loads(result.stdout), {'unittest': False, 'subprocess': False})
            self.assertFalse((root/'events.json').exists())

    def test_partial_cleanup_customization_preserves_native_cli_and_unknown_phase(self):
        startup = """import functools, unittest
def cleanup(function, *args, **kwargs):
    function(*args, **kwargs)
unittest.TestCase._callCleanup = staticmethod(functools.partial(cleanup))
"""
        source = """import unittest
calls = []
def cleanup(): calls.append(1)
class Probe(unittest.TestCase):
    def test_pass(self):
        self.addCleanup(lambda: self.assertEqual(calls, [1]))
        self.addCleanup(cleanup)
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 0)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertTrue(row['successful'])
            self.assertEqual(row['failed_tests'], [])
        source = """import unittest
def cleanup(): raise RuntimeError('private-canary')
class Probe(unittest.TestCase):
    def test_pass(self): self.addCleanup(cleanup)
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            event, = row['failed_tests']
            self.assertEqual(event['id'], 'test_probe.Probe.test_pass')
            self.assertEqual(event['phase'], 'unknown')
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 2}])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_unsupported_traceback_never_inspects_getter_and_preserves_native_callbacks(self):
        startup = """import unittest
calls = []
for name in ('addFailure', 'addError', 'addSubTest'):
    def native(self, *args, _name=name, **kwargs):
        calls.append((_name, args, kwargs))
        return 73
    setattr(unittest.TextTestResult, name, native)
"""
        source = """import io, unittest, sitecustomize
reads = []
class UnsupportedTraceback:
    @property
    def __class__(self):
        reads.append(1)
        raise SystemExit(71)
class NonraisingTraceback:
    @property
    def __class__(self):
        reads.append(1)
        return object
class Probe(unittest.TestCase):
    def test_callbacks(self):
        result = unittest.TextTestResult(io.StringIO(), False, 0)
        expected = []
        for traceback in (UnsupportedTraceback(), NonraisingTraceback()):
            err = (RuntimeError, RuntimeError('private-canary'), traceback)
            for name, args, kwargs in [
                ('addError', (self, err), {}),
                ('addFailure', (), dict(test=self, err=err)),
                ('addSubTest', (), dict(test=self, subtest=self, err=err))]:
                expected.append((name, args, kwargs))
                self.assertEqual(getattr(result, name)(*args, **kwargs), 73)
        self.assertEqual(reads, [])
        self.assertEqual(sitecustomize.calls, expected)
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 0)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertTrue(row['successful'])
            self.assertEqual(row['failed_tests'], [])
            self.assertEqual(row['failure_evidence']['matched_events'], 0)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_descriptor_callback_metadata_is_not_read_and_native_returns_are_preserved(self):
        from pathlib import Path
        import subprocess
        import sys
        source = "import functools, io, json, sys, unittest\nsys.path.insert(0, sys.argv[1])\nfrom serial_failure_capture import installed_capture\nfrom functools import partial\nclass Owned(unittest.TextTestResult):pass\nfor _name in ('addError','addFailure','addSubTest'):setattr(Owned,_name,unittest.TextTestResult.__dict__[_name])\ninstalled_capture=partial(installed_capture,target=Owned)\ncalls = []\nreads = []\nclass Callback:\n    @property\n    def __module__(self):\n        reads.append(1)\n        raise SystemExit(81)\n    def __get__(self, instance, owner):\n        return self if instance is None else functools.partial(self, instance)\n    def __call__(self, result, *args, **kwargs):\n        calls.append((result, args, kwargs))\n        return 123\nclass Probe(unittest.TestCase):\n    def test_ok(self): pass\nresult = Owned(io.StringIO(), False, 0)\ntest = Probe('test_ok')\nerr = (RuntimeError, RuntimeError('private-canary'), None)\nfor name in ('addError', 'addFailure', 'addSubTest'):\n    original = getattr(Owned, name)\n    callback = Callback()\n    setattr(Owned, name, callback)\n    args = (test, test, err) if name == 'addSubTest' else (test, err)\n    kwargs = dict(test=test, subtest=test, err=err) if name == 'addSubTest' else dict(test=test, err=err)\n    try:\n        calls.clear()\n        assert getattr(result, name)(*args) == 123\n        assert getattr(result, name)(**kwargs) == 123\n        expected = calls[:]\n        calls.clear()\n        with installed_capture({'root': sys.argv[2], 'identities': ['__main__.Probe.test_ok'], 'sources': []}, detailed=True) as state:\n            assert getattr(result, name)(*args) == 123\n            assert getattr(result, name)(**kwargs) == 123\n        assert calls == expected\n        assert reads == []\n        assert getattr(Owned, name) is callback\n        assert state['matched_events'] == 0\n        assert state['unmatched_events'] == 0 and state['failed_tests'] == []\n    finally:\n        setattr(Owned, name, original)\n# Exact native function metadata remains available without copying custom dicts.\noriginal = Owned.addError\nwith installed_capture({'root': sys.argv[2], 'identities': [], 'sources': []}, detailed=True):\n    wrapped = Owned.addError\n    assert wrapped is original\n    assert wrapped.__name__ == original.__name__\n    assert wrapped.__module__ == original.__module__\n    assert wrapped.__doc__ == original.__doc__\nassert Owned.addError is original\nprint(json.dumps({'native_callbacks_preserved': True, 'metadata_getter_reads': len(reads)}))\n"
        result = subprocess.run([sys.executable, '-c', source,
                                 str(Path(__file__).resolve().parent),
                                 str(Path(__file__).resolve().parents[1]/'v0.5')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'native_callbacks_preserved': True, 'metadata_getter_reads': 0})
        self.assertNotIn('private-canary', result.stdout + result.stderr)

    def test_descriptor_callback_metadata_preserves_native_cli_error_and_guard(self):
        startup = """import functools, unittest
calls = []
reads = []
original = unittest.TextTestResult.addError
class Callback:
    @property
    def __module__(self):
        reads.append(1)
        raise SystemExit(81)
    def __get__(self, instance, owner):
        return self if instance is None else functools.partial(self, instance)
    def __call__(self, result, *args, **kwargs):
        calls.append(1)
        original(result, *args, **kwargs)
        return 123
unittest.TextTestResult.addError = Callback()
"""
        source = """import unittest, sitecustomize
class Probe(unittest.TestCase):
    def test_1_error(self): raise RuntimeError('private-canary')
    def test_2_guard(self):
        self.assertEqual(sitecustomize.calls, [1])
        self.assertEqual(sitecustomize.reads, [])
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertFalse(row['successful'])
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([r['outcome'] for r in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['id'], 'test_probe.Probe.test_1_error')
            self.assertEqual(event['exception_type'], 'RuntimeError')
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 3}])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_non_descriptor_callbacks_preserve_native_binding_and_call_forms(self):
        from pathlib import Path
        import subprocess
        import sys
        source = "import io, json, sys, unittest\nsys.path.insert(0, sys.argv[1])\nfrom serial_failure_capture import installed_capture\nfrom functools import partial\nclass Owned(unittest.TextTestResult):pass\nfor _name in ('addError','addFailure','addSubTest'):setattr(Owned,_name,unittest.TextTestResult.__dict__[_name])\ninstalled_capture=partial(installed_capture,target=Owned)\nreads = []\ncalls = []\nclass Callback:\n    @property\n    def __module__(self):\n        reads.append(1)\n        raise SystemExit(81)\n    def __call__(self, *args, **kwargs):\n        calls.append((args, kwargs))\n        return 321\nclass Probe(unittest.TestCase):\n    def test_ok(self): pass\nresult = Owned(io.StringIO(), False, 0)\ntest = Probe('test_ok')\nerr = (RuntimeError, RuntimeError('private-canary'), None)\nconfig = {'root': sys.argv[2], 'identities': ['__main__.Probe.test_ok'], 'sources': []}\nfor name in ('addError', 'addFailure', 'addSubTest'):\n    original = getattr(Owned, name)\n    callback = Callback()\n    args = (test, test, err) if name == 'addSubTest' else (test, err)\n    kwargs = dict(test=test, subtest=test, err=err) if name == 'addSubTest' else dict(test=test, err=err)\n    setattr(Owned, name, callback)\n    try:\n        calls.clear()\n        assert getattr(result, name)(*args) == 321\n        assert getattr(result, name)(**kwargs) == 321\n        expected = calls[:]\n        calls.clear()\n        with installed_capture(config, detailed=True) as state:\n            assert getattr(result, name)(*args) == 321\n            assert getattr(result, name)(**kwargs) == 321\n        assert calls == expected\n        assert len(calls) == 2 and reads == []\n        assert getattr(Owned, name) is callback\n        assert state['matched_events'] == 0\n        assert state['unmatched_events'] == 0 and state['failed_tests'] == []\n        assert name in state['unsupported_callbacks']\n        # Fixed native signatures must accept exactly the same call forms.\n        if name == 'addSubTest':\n            def fixed(self, test, subtest, err): return 321\n            def keyword(self, *, test, subtest, err): return 321\n        else:\n            def fixed(self, test, err): return 321\n            def keyword(self, *, test, err): return 321\n        for invoke, forms in ((fixed, [args, kwargs]), (keyword, [kwargs])):\n            class FixedCallback(Callback): __call__ = invoke\n            fixed_callback = FixedCallback()\n            setattr(Owned, name, fixed_callback)\n            for form in forms:\n                native = getattr(result, name)(**form) if type(form) is dict else getattr(result, name)(*form)\n                with installed_capture(config, detailed=True):\n                    observed = getattr(result, name)(**form) if type(form) is dict else getattr(result, name)(*form)\n                assert observed == native == 321\n                assert getattr(Owned, name) is fixed_callback\n    finally:\n        setattr(Owned, name, original)\nassert reads == []\nprint(json.dumps({'native_arguments_returns_restoration': True, 'metadata_getter_reads': 0}))\n"
        result = subprocess.run([sys.executable, '-c', source,
                                 str(Path(__file__).resolve().parent),
                                 str(Path(__file__).resolve().parents[1]/'v0.5')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'native_arguments_returns_restoration': True, 'metadata_getter_reads': 0})
        self.assertNotIn('private-canary', result.stdout + result.stderr)

    def test_non_descriptor_callback_preserves_native_cli_error_and_guard(self):
        startup = 'import unittest\ncalls = []\nreads = []\ntarget = None\noriginal = unittest.TextTestResult.addError\nclass Callback:\n    @property\n    def __module__(self):\n        reads.append(1)\n        raise SystemExit(81)\n    def __call__(self, test, err):\n        calls.append(1)\n        original(target, test, err)\n        return 321\nunittest.TextTestResult.addError = Callback()\n'
        source = "import unittest, sitecustomize\nclass Probe(unittest.TestCase):\n    def test_1_error(self): raise RuntimeError('private-canary')\n    def test_2_guard(self):\n        self.assertEqual(sitecustomize.calls, [1])\n        self.assertEqual(sitecustomize.reads, [])\n    def setUp(self):\n     sitecustomize.target = self._outcome.result\n"
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertFalse(row['successful'])
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([r['outcome'] for r in row['tests']], ['failed', 'passed'])
            self.assertEqual(row['failed_tests'], [])
            self.assertEqual(row['failure_evidence']['status'], 'unknown')
            self.assertEqual(row['failure_evidence']['matched_events'], 0)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertIn('addError', row['failure_evidence']['unsupported_callbacks'])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)

    def test_descriptor_getter_slots_preserve_native_class_resolution(self):
        from pathlib import Path
        import subprocess
        import sys
        source = "import io, json, sys, unittest\nsys.path.insert(0, sys.argv[1])\nfrom serial_failure_capture import installed_capture\nfrom functools import partial\nclass Owned(unittest.TextTestResult):pass\nfor _name in ('addError','addFailure','addSubTest'):setattr(Owned,_name,unittest.TextTestResult.__dict__[_name])\ninstalled_capture=partial(installed_capture,target=Owned)\ncalls = []\nreads = []\nclass StaticGetter:\n    @property\n    def __module__(self): reads.append(1); raise SystemExit(81)\n    @staticmethod\n    def __get__(descriptor, instance, owner):\n        def invoke(*args, **kwargs):\n            calls.append((descriptor, instance, owner, args, kwargs))\n            return 321\n        return invoke\nclass Probe(unittest.TestCase):\n    def test_ok(self): pass\nresult = Owned(io.StringIO(), False, 0)\ntest = Probe('test_ok')\nerr = (RuntimeError, RuntimeError('private-canary'), None)\nconfig = {'root': sys.argv[2], 'identities': ['__main__.Probe.test_ok'], 'sources': []}\nfor name in ('addError', 'addFailure', 'addSubTest'):\n    original = Owned.__dict__[name]\n    for callback in (StaticGetter(),):\n        setattr(Owned, name, callback)\n        args = (test, test, err) if name == 'addSubTest' else (test, err)\n        kwargs = dict(test=test, subtest=test, err=err) if name == 'addSubTest' else dict(test=test, err=err)\n        try:\n            calls.clear()\n            assert getattr(result, name)(*args) == 321\n            assert getattr(result, name)(**kwargs) == 321\n            expected = calls[:]\n            calls.clear()\n            with installed_capture(config, detailed=True):\n                assert getattr(result, name)(*args) == 321\n                assert getattr(result, name)(**kwargs) == 321\n            assert calls == expected and reads == []\n            assert Owned.__dict__[name] is callback\n        finally:\n            setattr(Owned, name, original)\nprint(json.dumps({'native_slot_binding_preserved': True, 'metadata_getter_reads': 0}))\n"
        result = subprocess.run([sys.executable, '-c', source,
                                 str(Path(__file__).resolve().parent),
                                 str(Path(__file__).resolve().parents[1]/'v0.5')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'native_slot_binding_preserved': True, 'metadata_getter_reads': 0})
        self.assertNotIn('private-canary', result.stdout + result.stderr)


    def test_public_case_alias_metaclass_metadata_is_not_read(self):
        startup = """import unittest
reads = []
armed = False
class Meta(type):
    @property
    def __dict__(cls):
        if armed:
            reads.append(1)
            raise SystemExit(85)
        return type.__dict__['__dict__'].__get__(cls, type(cls))
class CompatibleCase(unittest.TestCase, metaclass=Meta): pass
unittest.TestCase = CompatibleCase
armed = True
"""
        source = """import sitecustomize
from unittest.case import TestCase
class Probe(TestCase):
    def test_1_error(self): raise RuntimeError('private-canary')
    def test_2_guard(self): self.assertEqual(sitecustomize.reads, [])
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertFalse(row['successful'])
            self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['id'], 'test_probe.Probe.test_1_error')
            self.assertEqual(event['phase'], 'unknown')
            self.assertEqual(event['exception_type'], 'RuntimeError')
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 4}])
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)


    def test_class_and_instance_callback_binding_match_native_matrix(self):
        from pathlib import Path
        import subprocess
        import sys
        source = "import functools,io,json,pathlib,sys,unittest\nROOT=pathlib.Path.cwd();OUT=ROOT;sys.path.insert(0,str(ROOT/'bench'))\nfrom serial_failure_capture import installed_capture\nfrom functools import partial\nclass Owned(unittest.TextTestResult):pass\nfor _name in ('addError','addFailure','addSubTest'):setattr(Owned,_name,unittest.TextTestResult.__dict__[_name])\ninstalled_capture=partial(installed_capture,target=Owned)\nreads=[];calls=[];rows=[]\nclass Probe(unittest.TestCase):\n def test_ok(self):pass\nclass HostileMeta(type):\n @property\n def __dict__(cls):reads.append('dict');raise SystemExit(81)\n @property\n def __mro__(cls):reads.append('mro');raise SystemExit(82)\nclass Callable(metaclass=HostileMeta):\n @property\n def __module__(self):reads.append('module');raise SystemExit(83)\n @property\n def __dict__(self):reads.append('object-dict');raise SystemExit(84)\n def __call__(self,*args,**kwargs):calls.append((args,kwargs));return token\nclass Descriptor(Callable):\n def __get__(self,instance,owner):\n  calls.append(('bind',instance,owner));return functools.partial(self,instance) if instance is not None else self\nclass StaticGetter:\n @staticmethod\n def __get__(descriptor,instance,owner):\n  calls.append(('bind',instance,owner));return lambda *args,**kwargs:(calls.append((args,kwargs)),token)[1]\nclass ClassGetter:\n @classmethod\n def __get__(cls,descriptor,instance,owner):\n  calls.append(('bind',cls,instance,owner));return lambda *args,**kwargs:(calls.append((args,kwargs)),token)[1]\ndef callback(*args,**kwargs):calls.append((args,kwargs));return token\ntoken=object();test=Probe('test_ok');err=(RuntimeError,RuntimeError('SYNTHETIC_PRIVATE_CANARY'),None)\nconfig={'root':str(ROOT/'v0.5'),'identities':['__main__.Probe.test_ok'],'sources':[]}\ncls=Owned\noriginals={n:next(b.__dict__[n] for b in cls.__mro__ if n in b.__dict__) for n in ('addError','addFailure','addSubTest')}\noriginal_local={n:n in cls.__dict__ for n in originals}\nfor name in originals:\n args=(test,test,err) if name=='addSubTest' else (test,err)\n kwargs={'test':test,'subtest':test,'err':err} if name=='addSubTest' else {'test':test,'err':err}\n forms=[('function',callback),('static',staticmethod(callback)),('class',classmethod(callback)),('callable',Callable()),('descriptor',Descriptor()),('static-getter',StaticGetter()),('class-getter',ClassGetter())]\n for label,cb in forms:\n  setattr(cls,name,cb)\n  result=cls(io.StringIO(),False,0)\n  for access in ('instance','class'):\n   def invoke():\n    target=result if access=='instance' else cls\n    prefix=(result,) if access=='class' and label=='function' else ()\n    return [getattr(target,name)(*prefix,*args),getattr(target,name)(*prefix,**kwargs)]\n   calls.clear()\n   try: native=invoke(); expected=calls[:];valid=True\n   except BaseException as exc: valid=False; native_error=type(exc).__name__\n   calls.clear();observed_error=None\n   if valid:\n    try:\n     with installed_capture(config,detailed=True):observed=invoke()\n     equal=observed==native and all(v is token for v in observed) and calls==expected\n    except BaseException as exc:equal=False;observed_error=type(exc).__name__\n   else:equal=None\n   row={'callback':name,'binding':label,'access':access,'native_valid':valid,'same_calls_args_returns':equal,'candidate_exception_type':observed_error,'metadata_reads':len(reads),'restoration':cls.__dict__[name] is cb}\n   rows.append(row)\n  setattr(cls,name,originals[name])\n# Inherited raw attributes must regain absent local presence.\nfor name in originals:\n delattr(cls,name)\n result=cls(io.StringIO(),False,0)\n inherited=getattr(cls,name)\n with installed_capture(config,detailed=True):pass\n rows.append({'callback':name,'binding':'inherited','restoration':name not in cls.__dict__ and getattr(cls,name) is inherited})\n setattr(cls,name,originals[name])\nassert reads==[]\n\nassert all(r['same_calls_args_returns'] for r in rows if r.get('native_valid'))\nassert all(r['restoration'] for r in rows)\nprint(json.dumps({'valid_cases':sum(bool(r.get('native_valid')) for r in rows),'metadata_reads':len(reads)}))\n"
        result = subprocess.run([sys.executable, '-c', source],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'valid_cases': 36, 'metadata_reads': 0})

    def test_class_static_successful_subtest_preserves_cli_error_and_guard(self):
        startup = "import unittest\ncalls = []\ntarget = None\nfor name in ('addError', 'addFailure', 'addSubTest'):\n    original = getattr(unittest.TextTestResult, name)\n    def native(*args, _name=name, _original=original, **kwargs):\n        calls.append(_name)\n        return _original(target, *args, **kwargs)\n    setattr(unittest.TextTestResult, name, staticmethod(native))\n"
        source = "import unittest, sitecustomize\nclass Probe(unittest.TestCase):\n    def test_1_error(self): raise RuntimeError('private-canary')\n    def test_2_guard(self):\n        self.assertEqual(sitecustomize.calls, ['addError'])\n        self.assertIsNone(unittest.TextTestResult.addSubTest(test=self, subtest=self, err=None))\n        self.assertEqual(sitecustomize.calls, ['addError', 'addSubTest'])\n    def setUp(self):\n     sitecustomize.target = self._outcome.result\n"
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([r['outcome'] for r in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['exception_type'], 'RuntimeError')
            self.assertEqual(event['id'], 'test_probe.Probe.test_1_error')
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)


    def test_native_data_protocol_owned_scope_and_conditional_restoration(self):
        from pathlib import Path
        import subprocess
        import sys
        source = "import io,json,sys,unittest\nfrom unittest import mock\nsys.path.insert(0, 'bench')\nfrom serial_failure_capture import installed_capture\nR=unittest.TextTestResult\nnames=('addError','addFailure','addSubTest')\noriginals={n:R.__dict__[n] for n in names}\nconfig={'root':sys.argv[1],'identities':['__main__.Probe.test_ok'],'sources':[]}\nclass Probe(unittest.TestCase):\n def test_ok(self):pass\ncase=Probe('test_ok');err=(RuntimeError,RuntimeError('private-canary'),None)\nlog=[];token=object()\nclass Data:\n def __get__(self,instance,owner):\n  log.append(('get',instance,owner))\n  def call(*args,**kwargs):log.append(('call',args,kwargs));return token\n  return call\n def __set__(self,instance,value):log.append(('set',instance,value));return token\n def __delete__(self,instance):log.append(('delete',instance));return token\nclass SetOnly:\n def __call__(self,*args,**kwargs):log.append(('raw',args,kwargs));return token\n def __set__(self,instance,value):log.append(('set',instance,value))\nfor name in names:\n raw=Data();setattr(R,name,raw)\n result=R(io.StringIO(),False,0);result.__dict__[name]=lambda *a,**k:None\n args=(case,case,err) if name=='addSubTest' else (case,err)\n kwargs=dict(test=case,subtest=case,err=err) if name=='addSubTest' else dict(test=case,err=err)\n def exercise():\n  log.clear()\n  assert getattr(result,name)(*args) is token\n  assert getattr(R,name)(**kwargs) is token\n  setattr(result,name,token);delattr(result,name)\n  return log[:]\n expected=exercise()\n with installed_capture(config,detailed=True):assert exercise()==expected\n assert R.__dict__[name] is raw\n setattr(R,name,originals[name])\n# Read-only native property remains read-only, and class access stays raw.\nraw=property(lambda self:lambda *a,**k:token);R.addError=raw\nwith installed_capture(config,detailed=True):\n result=R(io.StringIO(),False,0)\n assert result.addError(case,err) is token and R.addError is raw\n try:result.addError=token\n except AttributeError:pass\n else:raise AssertionError('readonly property became writable')\nR.addError=originals['addError']\n# No getter means no observable interposition seam; preserve raw object.\nraw=SetOnly();R.addError=raw\nwith installed_capture(config,detailed=True) as state:\n result=R(io.StringIO(),False,0)\n assert R.__dict__['addError'] is raw and result.addError is raw\n assert result.addError(case,err) is token\n assert state['matched_events']==0 and 'addError' in state['unsupported_callbacks']\n result.__dict__['addError']=token\n assert result.addError is token\nR.addError=originals['addError']\n# Mid-run user raw reassignment survives, including inherited absence.\nclass Owned(R):pass\nreplacement=lambda *a,**k:token\nwith installed_capture(config,detailed=True,target=Owned):\n assert all(R.__dict__[n] is originals[n] for n in names)\n with mock.patch.object(R,'addError',autospec=True) as native:\n  R(io.StringIO(),False,0).addError(case,err)\n  assert native.call_count==1\n Owned.addError=replacement\nassert Owned.__dict__['addError'] is replacement\nassert 'addFailure' not in Owned.__dict__ and 'addSubTest' not in Owned.__dict__\nassert all(R.__dict__[n] is originals[n] for n in names)\nprint(json.dumps({'protocol_preserved':True,'base_untouched':True,'user_reassignment_preserved':True}))\n"
        result = subprocess.run([sys.executable, '-c', source, str(Path.cwd()/'v0.5')],
                                cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {'protocol_preserved': True,
                         'base_untouched': True, 'user_reassignment_preserved': True})

    def test_owned_cli_capture_excludes_private_result_errors(self):
        startup = """import unittest
base = {name: unittest.TextTestResult.__dict__[name]
        for name in ('addError', 'addFailure', 'addSubTest')}
"""
        source = """import io, sitecustomize, unittest
class Probe(unittest.TestCase):
    def test_1_error(self): raise RuntimeError('private-canary')
    def test_2_guard(self):
        for name, raw in sitecustomize.base.items():
            self.assertIs(unittest.TextTestResult.__dict__[name], raw)
        private = unittest.TextTestResult(io.StringIO(), False, 0)
        private.addError(self, (RuntimeError, RuntimeError('private-canary'), None))
        self.assertEqual(len(private.errors), 1)
"""
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual(result.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([r['outcome'] for r in row['tests']], ['failed', 'passed'])
            self.assertEqual([e['id'] for e in row['failed_tests']], ['test_probe.Probe.test_1_error'])
            self.assertNotIn('private-canary', json.dumps(report) + result.stdout + result.stderr)


class SourceIntegration(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def test_owned_capture_preserves_native_callback_code_and_error_guard(self):
        source = """import unittest
class Probe(unittest.TestCase):
    def test_1_error(self):
        raise RuntimeError('native error')
    def test_2_guard(self):
        result = self._outcome.result
        for name in ('addError', 'addFailure', 'addSubTest'):
            self.assertIs(getattr(result, name).__func__, getattr(unittest.TextTestResult, name))
            self.assertNotIn(name, type(result).__dict__)
"""
        with self.fixture(source) as (process, report):
            row = report['repetitions'][0][0]
            self.assertEqual(process.returncode, 1)
            self.assertEqual(row['worker_returncode'], 0)
            self.assertFalse(row['successful'])
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([r['outcome'] for r in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['id'], 'test_probe.Probe.test_1_error')
            self.assertEqual(event['exception_type'], 'RuntimeError')
            self.assertEqual(event['phase'], 'test')
            self.assertEqual(event['source_frames'], [{'file': 'delivery/tests/test_probe.py', 'line': 4}])
            self.assertNotIn('native error', json.dumps(report) + process.stdout + process.stderr)


if __name__ == '__main__':
    unittest.main()


class ExceptionClassification(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def test_mutable_subprocess_alias_never_authorizes_custom_metadata(self):
        definition = "import subprocess\nclass UnsupportedError(Exception): pass\n"
        for startup in (False, True):
            body = ("error = UnsupportedError('redacted')\n"
                    "error.returncode = 7\nraise error\n")
            source = ("import unittest\n" + (definition if not startup else '') +
                      "class Probe(unittest.TestCase):\n def test_1_error(self):\n" +
                      ("  subprocess.CalledProcessError = UnsupportedError\n" if not startup else '') +
                      ''.join('  ' + line + '\n' for line in body.splitlines()) +
                      " def test_2_guard(self): pass\n")
            hook = (definition + "subprocess.CalledProcessError = UnsupportedError\n"
                    "import builtins\nbuiltins.UnsupportedError = UnsupportedError\n") if startup else None
            with self.subTest(startup=startup), self.fixture(source, custom_startup=hook) as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
                self.assertEqual((row['errors'], row['failures']), (1, 0))
                self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
                event, = row['failed_tests']
                self.assertEqual(event['exception_type'], 'unknown')
                self.assertNotIn('subprocess_returncode', event)
                self.assertNotIn('UnsupportedError', json.dumps(report) + result.stdout + result.stderr)

    def test_native_subprocess_label_and_exact_integer_returncode(self):
        for expression, expected in (('7', 7), ('True', None), ("'redacted'", None)):
            source = ("import subprocess, unittest\nclass Probe(unittest.TestCase):\n"
                      " def test_1_error(self):\n"
                      f"  raise subprocess.CalledProcessError({expression}, 'redacted')\n"
                      " def test_2_guard(self): pass\n")
            with self.subTest(expression=expression), self.fixture(source) as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
                self.assertEqual((row['errors'], row['failures']), (1, 0))
                self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
                event, = row['failed_tests']
                self.assertEqual(event['exception_type'], 'CalledProcessError')
                if expected is None:
                    self.assertNotIn('subprocess_returncode', event)
                else:
                    self.assertEqual(event['subprocess_returncode'], expected)

    def test_mutable_builtin_alias_never_authorizes_custom_label(self):
        source = """import builtins, unittest
class UnsupportedError(Exception): pass
class Probe(unittest.TestCase):
 def test_1_error(self):
  builtins.RuntimeError = UnsupportedError
  raise UnsupportedError('redacted')
 def test_2_guard(self): pass
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['exception_type'], 'unknown')
            self.assertNotIn('subprocess_returncode', event)
            self.assertNotIn('UnsupportedError', json.dumps(report) + result.stdout + result.stderr)

    def test_unsupported_metaclass_metadata_getters_are_not_evidence(self):
        source = """import subprocess, sys, unittest
class UnsupportedMeta(type):
 @property
 def __name__(cls):
  if sys._getframe(1).f_code.co_filename.endswith('serial_failure_capture.py'):
   raise SystemExit(89)
  return type.__dict__['__name__'].__get__(cls, type)
 @property
 def __dict__(cls):
  if sys._getframe(1).f_code.co_filename.endswith('serial_failure_capture.py'):
   raise SystemExit(90)
  return type.__dict__['__dict__'].__get__(cls, type)
class UnsupportedError(Exception, metaclass=UnsupportedMeta): pass
class Probe(unittest.TestCase):
 def test_1_error(self):
  subprocess.CalledProcessError = UnsupportedError
  error = UnsupportedError('redacted')
  error.returncode = 7
  raise error
 def test_2_guard(self): pass
"""
        with self.fixture(source) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
            event, = row['failed_tests']
            self.assertEqual(event['exception_type'], 'unknown')
            self.assertNotIn('subprocess_returncode', event)
            self.assertNotIn('UnsupportedError', json.dumps(report) + result.stdout + result.stderr)

    def test_live_subprocess_module_metadata_changes_are_unknown(self):
        for field in ('__name__', '__file__'):
            source = ("import subprocess, unittest\nclass Probe(unittest.TestCase):\n"
                      " def test_1_error(self):\n"
                      f"  subprocess.{field} = 'unsupported'\n"
                      "  raise subprocess.CalledProcessError(7, 'redacted')\n"
                      " def test_2_guard(self): pass\n")
            with self.subTest(field=field), self.fixture(source) as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
                self.assertEqual((row['errors'], row['failures']), (1, 0))
                self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
                event, = row['failed_tests']
                self.assertEqual(event['exception_type'], 'unknown')
                self.assertNotIn('subprocess_returncode', event)


class ModuleMetadata(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def _direct(self, kind, timing, module='runner'):
        import subprocess
        import sys
        from pathlib import Path
        code = r"""
import builtins, contextlib, io, json, sys, types, unittest
kind, timing, module = sys.argv[1:]
reads = []
class CheckedModule(types.ModuleType):
    @property
    def __dict__(self):
        if sys._getframe(1).f_code.co_filename.endswith('serial_failure_capture.py'):
            reads.append(1)
            if kind == 'raising-builtin':
                raise SystemExit(93)
        return types.ModuleType.__dict__['__dict__'].__get__(self, type(self))
class UnsupportedPath:
    def __fspath__(self):
        reads.append(1)
        raise SystemExit(94)
class Owned(unittest.TextTestResult): pass
class Probe(unittest.TestCase):
    def test_1_error(self):
        if timing == 'during-test': change()
        raise RuntimeError('redacted')
    def test_2_guard(self): self.assertEqual(reads, [])
subject = getattr(unittest, module)
raw = types.ModuleType.__dict__['__dict__'].__get__(subject, type(subject))
old_file = raw.get('__file__'); old_class = type(subject)
def change():
    if kind.endswith('builtin'):
        builtins.__class__ = CheckedModule
    elif kind == 'module-subclass':
        subject.__class__ = CheckedModule
    elif kind == 'unreadable':
        pass
    elif kind == 'missing':
        raw.pop('__file__', None)
    else:
        raw['__file__'] = {'none': None, 'pathlike': UnsupportedPath(),
                          'malformed': 17, 'unavailable': '/unavailable-native-source.py'}[kind]
if timing == 'before-import': change()
from serial_failure_capture import installed_capture
if timing == 'before-entry': change()
runner = unittest.TextTestRunner(stream=io.StringIO(), resultclass=Owned)
config = {'root': '.', 'identities': ['__main__.Probe.test_1_error'], 'sources': []}
from unittest.mock import patch
source_reader = patch('pathlib.Path.read_text', side_effect=OSError('unavailable')) if kind == 'unreadable' else contextlib.nullcontext()
try:
    with source_reader, installed_capture(config, detailed=True, target=Owned, runner=runner) as state:
        if timing == 'after-entry': change()
        result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(Probe))
    summary = {'errors': len(result.errors), 'failures': len(result.failures),
               'testsRun': result.testsRun, 'getter_calls': len(reads),
               'matched': state['matched_events'], 'events': len(state['failed_tests']),
               'restored_constructor': '__init__' not in Owned.__dict__,
               'restored_formatter': '_exc_info_to_string' not in Owned.__dict__}
finally:
    builtins.__class__ = types.ModuleType
    subject.__class__ = old_class
    raw['__file__'] = old_file
print(json.dumps(summary))
"""
        result = subprocess.run([sys.executable, '-B', '-c', code, kind, timing, module],
                                cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        data = json.loads(result.stdout)
        self.assertEqual({k: data[k] for k in ('errors', 'failures', 'testsRun', 'getter_calls')},
                         {'errors': 1, 'failures': 0, 'testsRun': 2, 'getter_calls': 0})
        self.assertTrue(data['restored_constructor'])
        self.assertTrue(data['restored_formatter'])
        if kind.endswith('builtin'):
            self.assertEqual((data['matched'], data['events']), (1, 1))
        else:
            self.assertEqual((data['matched'], data['events']), (0, 0))

    def test_builtin_module_raw_dictionary_avoids_getter(self):
        for timing in ('before-import', 'before-entry', 'after-entry', 'during-test'):
            with self.subTest(timing=timing): self._direct('plain-builtin', timing)

    def test_builtin_module_raising_getter_preserves_native_run(self):
        for timing in ('before-import', 'before-entry', 'after-entry', 'during-test'):
            with self.subTest(timing=timing): self._direct('raising-builtin', timing)

    def test_unittest_none_source_metadata_declines_observation(self):
        for module in ('runner', 'result', 'case'):
            for timing in ('before-import', 'before-entry', 'after-entry', 'during-test'):
                with self.subTest(module=module, timing=timing): self._direct('none', timing, module)

    def test_unittest_unsupported_source_fields_preserve_native_run(self):
        for kind in ('pathlike', 'missing', 'malformed', 'unavailable'):
            for timing in ('before-import', 'before-entry', 'after-entry', 'during-test'):
                with self.subTest(kind=kind, timing=timing): self._direct(kind, timing)

    def test_unittest_module_subclass_declines_without_dictionary_getter(self):
        for timing in ('before-import', 'before-entry', 'after-entry', 'during-test'):
            with self.subTest(timing=timing): self._direct('module-subclass', timing)

    def test_module_metadata_cli_preserves_error_guard_and_report(self):
        hook = """import builtins, types, sys, unittest
reads = []
class CheckedModule(types.ModuleType):
    @property
    def __dict__(self):
        if sys._getframe(1).f_code.co_filename.endswith('serial_failure_capture.py'):
            reads.append(1)
            raise SystemExit(93)
        return types.ModuleType.__dict__['__dict__'].__get__(self, type(self))
"""
        source = """import unittest, sitecustomize
class Probe(unittest.TestCase):
    def test_1_error(self):
        if timing == 'during-test': change()
        raise RuntimeError('redacted')
    def test_2_guard(self): self.assertEqual(sitecustomize.reads, [])
"""
        for change, observed in [('builtins.__class__ = CheckedModule', True),
                                 ('unittest.runner.__file__ = None', False),
                                 ('unittest.case.__file__ = None', False)]:
            with self.subTest(change=change), self.fixture(source, custom_startup=hook + change + '\n') as (result, report):
                row = report['repetitions'][0][0]
                self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
                self.assertEqual((row['errors'], row['failures']), (1, 0))
                self.assertEqual([t['outcome'] for t in row['tests']], ['failed', 'passed'])
                self.assertEqual(len(row['failed_tests']), 1 if observed else 0)
                self.assertEqual(row['failure_evidence']['matched_events'], 1 if observed else 0)
                if not observed: self.assertEqual(row['failure_evidence']['status'], 'unknown')

    def test_unavailable_native_source_read_declines_observation(self):
        self._direct('unreadable', 'before-entry')


class SubprocessSourceAvailability(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def _startup(self, kind):
        return ("from pathlib import Path\nimport sysconfig\n"
                "expected = Path(sysconfig.get_path('stdlib')) / 'subprocess.py'\n"
                "reader = Path.read_text\n"
                "def read(path, *args, **kwargs):\n"
                " if path == expected:\n" +
                ("  return 'def :\\n'\n" if kind == 'SyntaxError' else
                 f"  raise {kind}('unavailable')\n") +
                " return reader(path, *args, **kwargs)\n"
                "Path.read_text = read\n")

    def _check(self, startup, expression, label, observed=True):
        source = ("import subprocess, unittest\nclass Probe(unittest.TestCase):\n"
                  f" def test_1_error(self): raise {expression}\n"
                  " def test_2_guard(self): pass\n")
        with self.fixture(source, custom_startup=startup) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
            if not observed:
                self.assertEqual(row['failed_tests'], [])
                self.assertEqual(row['failure_evidence']['status'], 'unknown')
                return
            event, = row['failed_tests']
            self.assertEqual(event['exception_type'], label)
            self.assertNotIn('subprocess_returncode', event)
            self.assertEqual(row['failure_evidence']['matched_events'], 1)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)

    def test_unavailable_subprocess_source_preserves_builtin_and_guard(self):
        for kind in ('OSError', 'UnicodeError', 'SyntaxError'):
            with self.subTest(kind=kind):
                self._check(self._startup(kind), "RuntimeError('redacted')", 'RuntimeError')

    def test_unavailable_subprocess_source_declines_cpe_metadata(self):
        for kind in ('OSError', 'UnicodeError', 'SyntaxError'):
            with self.subTest(kind=kind):
                self._check(self._startup(kind),
                            "subprocess.CalledProcessError(7, 'redacted')", 'unknown')

    def test_optional_subprocess_path_availability_declines_evidence(self):
        hooks = (
            "from pathlib import Path\nimport sysconfig\n"
            "expected = Path(sysconfig.get_path('stdlib')) / 'subprocess.py'\n"
            "original = Path.is_symlink\n"
            "def check(path):\n"
            " if path == expected: raise OSError('unavailable')\n"
            " return original(path)\nPath.is_symlink = check\n",
            "import sysconfig\noriginal = sysconfig.get_path\n"
            "def path(name, *args, **kwargs):\n"
            " if name == 'stdlib': return None\n"
            " return original(name, *args, **kwargs)\nsysconfig.get_path = path\n",
        )
        for index, hook in enumerate(hooks):
            with self.subTest(index=index):
                self._check(hook, "subprocess.CalledProcessError(7, 'redacted')", 'unknown',
                            observed=index == 0)


class UnittestPathAvailability(unittest.TestCase):
    fixture = existing.ProfilerCLI.fixture

    def _startup(self, boundary):
        if boundary == 'stdlib-query':
            return ("import sysconfig\noriginal = sysconfig.get_path\n"
                    "def get_path(name, *args, **kwargs):\n"
                    " if name == 'stdlib': raise OSError('unavailable')\n"
                    " return original(name, *args, **kwargs)\n"
                    "sysconfig.get_path = get_path\n")
        return ("from pathlib import Path\nimport sysconfig\n"
                "expected = Path(sysconfig.get_path('stdlib')) / 'unittest'" +
                ("\n" if boundary == 'directory' else f" / '{boundary}.py'\n") +
                "original = Path.is_symlink\n"
                "def is_symlink(path):\n"
                " if path == expected: raise OSError('unavailable')\n"
                " return original(path)\nPath.is_symlink = is_symlink\n")

    def _check(self, boundary):
        import subprocess
        import sys
        from pathlib import Path
        source = ("import unittest\nclass Probe(unittest.TestCase):\n"
                  " def test_1_error(self): raise RuntimeError('redacted')\n"
                  " def test_2_guard(self): pass\n")
        direct = ("import io, json, unittest\n"
                  "from serial_failure_capture import installed_capture\n"
                  "class Owned(unittest.TextTestResult): pass\n" + source +
                  "runner = unittest.TextTestRunner(stream=io.StringIO(), resultclass=Owned)\n"
                  "before = dict(Owned.__dict__)\n" + self._startup(boundary) +
                  "with installed_capture({'root': '.', 'identities': ['__main__.Probe.test_1_error'], 'sources': []}, detailed=True, target=Owned, runner=runner) as state:\n"
                  " result = runner.run(unittest.defaultTestLoader.loadTestsFromTestCase(Probe))\n"
                  "print(json.dumps({'testsRun': result.testsRun, 'errors': len(result.errors), 'failures': len(result.failures), 'successful': result.wasSuccessful(), 'events': state['failed_tests'], 'matched': state['matched_events'], 'unmatched': state['unmatched_events'], 'restored': dict(Owned.__dict__) == before}))\n")
        result = subprocess.run([sys.executable, '-B', '-c', direct],
                                cwd=Path(__file__).resolve().parent,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {
            'testsRun': 2, 'errors': 1, 'failures': 0, 'successful': False,
            'events': [], 'matched': 0, 'unmatched': 0, 'restored': True})
        with self.fixture(source, custom_startup=self._startup(boundary)) as (result, report):
            row = report['repetitions'][0][0]
            self.assertEqual((result.returncode, row['worker_returncode']), (1, 0))
            self.assertFalse(row['successful'])
            self.assertEqual((row['errors'], row['failures']), (1, 0))
            self.assertEqual([test['outcome'] for test in row['tests']], ['failed', 'passed'])
            self.assertEqual(row['failed_tests'], [])
            self.assertEqual(row['failure_evidence']['status'], 'unknown')
            self.assertEqual(row['failure_evidence']['matched_events'], 0)
            self.assertEqual(row['failure_evidence']['unmatched_events'], 0)
            self.assertFalse(row['failure_evidence']['truncated'])
            self.assertNotIn('redacted', json.dumps(report) + result.stdout + result.stderr)

    def test_unavailable_stdlib_query_preserves_native_error_and_guard(self):
        self._check('stdlib-query')

    def test_unavailable_unittest_directory_preserves_native_error_and_guard(self):
        self._check('directory')

    def test_unavailable_result_path_preserves_native_error_and_guard(self):
        self._check('result')

    def test_unavailable_runner_path_preserves_native_error_and_guard(self):
        self._check('runner')

    def test_unavailable_case_path_preserves_native_error_and_guard(self):
        self._check('case')

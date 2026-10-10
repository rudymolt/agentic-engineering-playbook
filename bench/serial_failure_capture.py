"""Failure-only unittest events for the delivery profiler's owned subprocesses.

No exception text, subtest values, command arguments or arbitrary output is read.
The startup shim is ephemeral; native commands and existing startup hooks remain.
"""
import atexit
from functools import wraps
import json
import os
from pathlib import Path
import re
import sys
import types


def startup(config_path):
    config = json.loads(Path(config_path).read_text())
    original = sys.orig_argv
    owner = Path(config['owner'])
    if len(original) > 1 and original[1] == config['verifier']:
        try:
            with owner.open('x') as stream:
                stream.write(str(os.getpid()))
        except FileExistsError:
            pass
        return
    if original[1:3] != ['-m', 'unittest'] or Path.cwd().resolve() != Path(config['root']):
        return
    try:
        if int(owner.read_text()) != os.getppid():
            return
    except (OSError, ValueError):
        return
    import unittest
    root = Path(config['root'])
    identities = set(config['identities'])
    sources = set(config['sources'])
    state = {'failed_tests': [], 'matched_events': 0, 'unmatched_events': 0, 'truncated': False}
    holder = re.compile(r'^(?:setUpClass|tearDownClass|setUpModule|tearDownModule) \(([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)\)$')

    def plain_fields(value, base):
        # Invoke only the trusted stdlib descriptor, never a user property/get.
        try:
            fields = base.__dict__['__dict__'].__get__(value, type(value))
            return fields if type(fields) is dict else None
        except (TypeError, AttributeError):
            return None

    def capture(test, error, outcome):
        try:
            if type(error) is not tuple or len(error) != 3:
                state['unmatched_events'] += 1
                return
            cls = type(test)
            identity = None
            if type(cls) is type:
                base = unittest.suite._ErrorHolder if cls is unittest.suite._ErrorHolder else unittest.TestCase
                fields = plain_fields(test, base)
                if fields is not None and cls is unittest.suite._ErrorHolder:
                    description = fields.get('description')
                    match = holder.fullmatch(description) if type(description) is str else None
                    identity = match.group(1) if match else None
                elif fields is not None:
                    method = fields.get('_testMethodName')
                    module = type.__getattribute__(cls, '__dict__').get('__module__')
                    qualname = type.__getattribute__(cls, '__qualname__')
                    if all(type(part) is str for part in (module, qualname, method)):
                        identity = module + '.' + qualname + '.' + method
            if identity not in identities:
                state['unmatched_events'] += 1
                return
            state['matched_events'] += 1
            if len(state['failed_tests']) >= 1024:
                state['truncated'] = True
                return
            frames = []
            traceback = error[2]
            while isinstance(traceback, types.TracebackType):
                filename = traceback.tb_frame.f_code.co_filename
                if type(filename) is not str:
                    traceback = traceback.tb_next
                    continue
                path = Path(filename)
                try:
                    relative = path.resolve().relative_to(root).as_posix()
                except (ValueError, OSError, RuntimeError):
                    relative = None
                if relative in sources:
                    if len(frames) < 64:
                        frames.append({'file': relative, 'line': traceback.tb_lineno})
                    else:
                        state['truncated'] = True
                traceback = traceback.tb_next
            state['failed_tests'].append({'id': identity, 'outcome': outcome, 'source_frames': frames})
        except Exception:
            # Evidence must never replace or suppress the native result.
            state['unmatched_events'] += 1

    real_failure = unittest.TextTestResult.addFailure
    real_error = unittest.TextTestResult.addError
    real_subtest = unittest.TextTestResult.addSubTest

    @wraps(real_failure)
    def failure(self, *args, **kwargs):
        result = real_failure(self, *args, **kwargs)
        test = args[0] if args else kwargs.get('test')
        err = args[1] if len(args) > 1 else kwargs.get('err')
        capture(test, err, 'failed')
        return result

    @wraps(real_error)
    def error(self, *args, **kwargs):
        result = real_error(self, *args, **kwargs)
        test = args[0] if args else kwargs.get('test')
        err = args[1] if len(args) > 1 else kwargs.get('err')
        capture(test, err, 'error')
        return result

    @wraps(real_subtest)
    def subtest(self, *args, **kwargs):
        err = args[2] if len(args) > 2 else kwargs.get('err')
        if err is None:
            return real_subtest(self, *args, **kwargs)
        fields = plain_fields(self, unittest.TestResult)
        errors = fields.get('errors') if fields is not None else None
        errors_before = len(errors) if type(errors) is list else None
        result = real_subtest(self, *args, **kwargs)
        if errors_before is None or fields.get('errors') is not errors:
            state['unmatched_events'] += 1
            return result
        test = args[0] if args else kwargs.get('test')
        capture(test, err, 'error' if len(errors) > errors_before else 'failed')
        return result

    unittest.TextTestResult.addFailure = failure
    unittest.TextTestResult.addError = error
    unittest.TextTestResult.addSubTest = subtest

    def finish():
        try:
            Path(config['output']).write_text(json.dumps(state))
        except OSError:
            pass
    atexit.register(finish)

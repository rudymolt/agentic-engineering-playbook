"""Scoped, input-only Git syntax caching for explicitly selected tests."""
from functools import wraps
import subprocess
from unittest import mock

from delivery_pilot import interim as interim_module


def memoized_control_refs(test):
    """Reuse only successful, input-only Git syntax probes within one test.

    Every validator still runs on every call. Selected tests must keep the Git
    executable and environment fixed. check-ref-format without options depends
    only on its ref argument, not on repository state. Distinct refs and failures
    still invoke real Git. All other subprocess calls remain real and uncached.
    """
    @wraps(test)
    def run(*args, **kwargs):
        original = interim_module.subprocess
        successful = {}

        class SyntaxProbes:
            def __getattr__(self, name):
                return getattr(original, name)

            def run(self, command, *positional, **options):
                eligible = (not positional and isinstance(command, (list, tuple))
                            and len(command) == 3 and command[:2] == ["git", "check-ref-format"]
                            and isinstance(command[2], str)
                            and options == {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "check": False})
                if not eligible:
                    return original.run(command, *positional, **options)
                key = tuple(command)
                if key not in successful:
                    result = original.run(command, **options)
                    if result.returncode:
                        return result
                    successful[key] = (result.returncode, result.stdout, result.stderr)
                return subprocess.CompletedProcess(list(command), *successful[key])

        with mock.patch.object(interim_module, "subprocess", SyntaxProbes()):
            return test(*args, **kwargs)
    return run

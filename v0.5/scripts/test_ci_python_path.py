#!/usr/bin/env python3
"""Exercise the delivery workflow across sudo's reset PATH boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CiPythonPathTests(unittest.TestCase):
    def test_delivery_subprocess_finds_setup_python_after_sudo_resets_path(self) -> None:
        workflow = (ROOT / ".github/workflows/playbook-ci.yml").read_text()
        step = workflow.split("- name: Verify delivery contracts and fault tests\n", 1)[1]
        command = next(line.strip().removeprefix("run: ")
                       for line in step.splitlines() if line.strip().startswith("run: "))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            selected = root / "tool cache" / "bin"
            selected.mkdir(parents=True)
            for name in ("python3", "python3.12"):
                (selected / name).symlink_to(sys.executable)

            # Model sudo's secure_path without invoking sudo or requiring root.
            # Only env is available after the boundary; Python must be restored
            # by the actual workflow command, even if the host has Python 3.12.
            secure = root / "secure-bin"
            secure.mkdir()
            (secure / "env").symlink_to(shutil.which("env"))
            wrappers = root / "wrappers"
            wrappers.mkdir()
            sudo = wrappers / "sudo"
            sudo.write_text("#!/bin/sh\n"
                            f"PATH={shlex.quote(str(secure))}\nexport PATH\n"
                            'exec "$@"\n')
            sudo.chmod(0o755)

            verifier = root / "v0.5/delivery/scripts/verify.py"
            verifier.parent.mkdir(parents=True)
            verifier.write_text(
                "import subprocess, sys\n"
                "assert sys.argv[1:] == ['--set', 'K4.1', '--jobs', '3']\n"
                "subprocess.run(['python3.12', '-c', "
                "'import json, os, sys; print(json.dumps(os.path.realpath(sys.executable)))'], "
                "check=True)\n"
            )
            environment = dict(os.environ,
                               PATH=os.pathsep.join((str(wrappers), str(selected), str(secure))),
                               pythonLocation=str(selected.parent))
            result = subprocess.run(["/bin/bash", "-e", "-o", "pipefail", "-c", command],
                                    cwd=root, env=environment, capture_output=True, text=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), os.path.realpath(sys.executable))


if __name__ == "__main__":
    unittest.main()

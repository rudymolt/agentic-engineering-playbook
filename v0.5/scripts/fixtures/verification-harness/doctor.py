#!/usr/bin/env python3
"""Observe prerequisites only: 0 ready, 1 command error, 2 blocked."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def check():
    root = Path(__file__).resolve().parent
    try:
        target = json.loads((root / "target.json").read_text())
        cli = root / target["cli"]
        if not cli.is_file() or not (root / "drive.py").is_file():
            return 2, {"error": "restore the selected application CLI and generated driver"}
        result = subprocess.run(
            [sys.executable, str(cli), "status"], cwd=root,
            text=True, capture_output=True, timeout=10,
        )
        if result.returncode != 0:
            return 1, {"error": "application status command failed; inspect fixture configuration",
                       "status_exit": result.returncode, "stderr": result.stderr}
        observed = json.loads(result.stdout)
        for field in ("instance", "revision"):
            if observed.get(field) != target[field]:
                return 2, {"error": f"select the intended application {field}; target.json is the approved baseline",
                           "observed": observed}
        if observed.get("authorized") is not True:
            return 2, {"error": "provide VERIFY_HARNESS_AUTH fixture test authorization", "observed": observed}
        if observed.get("ready") is not True:
            return 2, {"error": "restore the fixture application's readiness before driving", "observed": observed}
        if not os.environ.get("VERIFY_EVIDENCE_DIR"):
            return 2, {"error": "set VERIFY_EVIDENCE_DIR to a writable evidence directory"}
        evidence = Path(os.environ["VERIFY_EVIDENCE_DIR"])
        try:
            evidence.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=evidence, prefix=".doctor-probe-") as handle:
                handle.write(b"probe")
                handle.flush()
        except OSError as error:
            return 2, {"error": f"choose a usable evidence destination: {error}"}
        return 0, {"ready": True, "observed": observed,
                   "cli_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
                   "command": ["python3", target["cli"], "status"],
                   "evidence": str(evidence)}
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        return 1, {"error": f"inspect the target configuration/status command: {error}"}


if __name__ == "__main__":
    if sys.argv[1:] == ["--help"]:
        print(__doc__ + " Usage: doctor.py; requires VERIFY_HARNESS_AUTH and VERIFY_EVIDENCE_DIR.")
        raise SystemExit(0)
    if len(sys.argv) != 1:
        print("error: Doctor takes no arguments; use --help", file=sys.stderr)
        raise SystemExit(1)
    code, result = check()
    print(json.dumps(result), file=sys.stdout if code == 0 else sys.stderr)
    raise SystemExit(code)

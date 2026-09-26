#!/usr/bin/env python3
"""Apply an exact macOS Seatbelt profile for a Launcher V3 checker command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


sys.dont_write_bytecode = True
FSEVENTS_SERVICE = "com.apple.FSEvents"
PROFILE_DELTA = b'(allow mach-lookup (global-name "com.apple.FSEvents"))\n'
SHA256_PREFIX = "sha256:"
EXTERNAL_ENVIRONMENT_KEYS = (
    "TMPDIR",
    "TMP",
    "TEMP",
    "XDG_CACHE_HOME",
    "NPM_CONFIG_CACHE",
    "JEST_CACHE_DIRECTORY",
)
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


class LauncherError(ValueError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(raw).hexdigest()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def effective_profile(base: bytes) -> bytes:
    if not base.strip():
        raise LauncherError("Seatbelt base profile is empty")
    if FSEVENTS_SERVICE.encode() in base:
        raise LauncherError("Seatbelt base profile already mentions com.apple.FSEvents")
    return base.rstrip(b"\n") + b"\n" + PROFILE_DELTA


def _outside(child: Path, repository: Path, label: str) -> None:
    if child == repository or child.is_relative_to(repository):
        raise LauncherError(f"{label} must be outside the repository")


def _require_external_environment(external_root: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for key in EXTERNAL_ENVIRONMENT_KEYS:
        value = os.environ.get(key)
        if not value:
            raise LauncherError(f"{key} must be set")
        resolved = Path(value).resolve()
        if resolved != external_root and not resolved.is_relative_to(external_root):
            raise LauncherError(f"{key} must be beneath the external root")
        observed[key] = str(resolved)
    if os.environ.get("PYTHONDONTWRITEBYTECODE") != "1":
        raise LauncherError("PYTHONDONTWRITEBYTECODE must equal 1")
    return observed


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="checker-launcher-v3")
    cli.add_argument("--repository", type=Path, required=True)
    cli.add_argument("--base-profile", type=Path, required=True)
    cli.add_argument("--expected-profile-digest", required=True)
    cli.add_argument("--external-root", type=Path, required=True)
    cli.add_argument("--evidence-dir", type=Path, required=True)
    cli.add_argument("command", nargs=argparse.REMAINDER)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if platform.system() != "Darwin":
            raise LauncherError("Launcher V3 Seatbelt execution requires macOS")
        if not args.command:
            raise LauncherError("checker command is required after --")
        command = args.command[1:] if args.command[0] == "--" else args.command
        if not command:
            raise LauncherError("checker command is empty")
        repository = args.repository.resolve(strict=True)
        external_root = args.external_root.resolve(strict=True)
        base_profile = args.base_profile.resolve(strict=True)
        evidence_dir = args.evidence_dir.resolve()
        _outside(external_root, repository, "external root")
        _outside(base_profile, repository, "Seatbelt base profile")
        _outside(evidence_dir, repository, "evidence directory")
        if evidence_dir != external_root and not evidence_dir.is_relative_to(external_root):
            raise LauncherError("evidence directory must be beneath the external root")
        environment = _require_external_environment(external_root)
        profile = effective_profile(base_profile.read_bytes())
        profile_digest = sha256_bytes(profile)
        if profile_digest != args.expected_profile_digest:
            raise LauncherError("effective Seatbelt profile digest does not match the approved digest")
        sandbox_exec = SANDBOX_EXEC
        if not sandbox_exec.exists():
            raise LauncherError("/usr/bin/sandbox-exec is unavailable")
        evidence_dir.mkdir(parents=True, exist_ok=False)
        profile_path = evidence_dir / "effective-profile.sbpl"
        stdout_path = evidence_dir / "stdout.log"
        stderr_path = evidence_dir / "stderr.log"
        result_path = evidence_dir / "launcher-execution.json"
        profile_path.write_bytes(profile)
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        completed = subprocess.run(
            [str(sandbox_exec), "-f", str(profile_path), *command],
            cwd=repository,
            env=os.environ.copy(),
            capture_output=True,
            check=False,
        )
        ended_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        stdout_path.write_bytes(completed.stdout)
        stderr_path.write_bytes(completed.stderr)
        evidence = {
            "schema_version": 1,
            "allowlist": [FSEVENTS_SERVICE],
            "command": command,
            "cwd": str(repository),
            "ended_at": ended_at,
            "environment": {**environment, "PYTHONDONTWRITEBYTECODE": "1"},
            "exit_code": completed.returncode,
            "profile_digest": profile_digest,
            "profile_locator": str(profile_path),
            "sandbox_runtime_digest": sha256_bytes(sandbox_exec.read_bytes()),
            "started_at": started_at,
            "stderr_digest": sha256_bytes(completed.stderr),
            "stdout_digest": sha256_bytes(completed.stdout),
        }
        result_path.write_bytes(canonical_bytes(evidence))
        sys.stdout.buffer.write(canonical_bytes(evidence))
        return completed.returncode if 0 <= completed.returncode <= 125 else 125
    except (OSError, LauncherError, ValueError) as exc:
        sys.stdout.buffer.write(canonical_bytes({
            "error_class": type(exc).__name__,
            "outcome": "blocked",
            "required_actions": [str(exc)],
        }))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

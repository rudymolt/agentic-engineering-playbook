"""Git-backed Tier A control ref with commit/ref compare-and-set."""

from __future__ import annotations

import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, digest, load_strict
from .state import CasMismatch


ZERO_SHA = "0" * 40


@dataclass(frozen=True)
class GitSnapshot:
    value: dict[str, Any]
    digest: str
    commit_sha: str


class GitControlStore:
    def __init__(self, repository: Path, control_ref: str, control_path: str = "mission.yml"):
        self.repository = repository
        self.control_ref = control_ref
        self.control_path = control_path
        if not control_ref.startswith("refs/heads/delivery-control/"):
            raise ValueError("control ref must use refs/heads/delivery-control/")
        if control_path != "mission.yml":
            raise ValueError("pilot control path is fixed at mission.yml")

    def _git(self, *args: str, input_bytes: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repository,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def _resolve(self) -> str | None:
        result = self._git("rev-parse", "--verify", self.control_ref, check=False)
        return result.stdout.decode().strip() if result.returncode == 0 else None

    def _commit(self, value: dict[str, Any], parent: str | None, message: str) -> str:
        blob = self._git("hash-object", "-w", "--stdin", input_bytes=canonical_bytes(value) + b"\n").stdout.decode().strip()
        tree_line = f"100644 blob {blob}\t{self.control_path}\n".encode()
        tree = self._git("mktree", input_bytes=tree_line).stdout.decode().strip()
        # A per-write id keeps every commit unique.  Two writers publishing the
        # same value from the same parent in the same second would otherwise
        # create one identical commit, and the stale writer's lease push would
        # succeed as a no-op, letting both believe they won the CAS.
        args = ["commit-tree", tree, "-m", message, "-m", "Delivery-Write-Id: " + secrets.token_hex(16)]
        if parent:
            args.extend(["-p", parent])
        return self._git(*args).stdout.decode().strip()

    def create(self, genesis_payload: dict[str, Any]) -> GitSnapshot:
        if self._resolve() is not None:
            raise CasMismatch("control ref already exists")
        commit = self._commit(genesis_payload, None, "delivery control genesis")
        result = self._git("update-ref", self.control_ref, commit, ZERO_SHA, check=False)
        if result.returncode:
            raise CasMismatch("control ref creation lost compare-and-set")
        return GitSnapshot(genesis_payload, digest(genesis_payload), commit)

    def read(self) -> GitSnapshot:
        commit = self._resolve()
        if commit is None:
            raise FileNotFoundError(self.control_ref)
        raw = self._git("show", f"{commit}:{self.control_path}").stdout
        value = load_strict(raw)
        return GitSnapshot(value, digest(value), commit)

    def write(self, expected_commit: str, expected_digest: str, value: dict[str, Any]) -> GitSnapshot:
        current = self.read()
        if current.commit_sha != expected_commit or current.digest != expected_digest:
            raise CasMismatch("control ref or projection digest moved")
        commit = self._commit(value, current.commit_sha, "delivery control checkpoint")
        result = self._git("update-ref", self.control_ref, commit, expected_commit, check=False)
        if result.returncode:
            raise CasMismatch("control checkpoint lost compare-and-set")
        return GitSnapshot(value, digest(value), commit)

    def push(self, remote: str, expected_remote_commit: str | None, commit: str) -> None:
        lease = expected_remote_commit or ZERO_SHA
        result = self._git(
            "push",
            f"--force-with-lease={self.control_ref}:{lease}",
            remote,
            f"{commit}:{self.control_ref}",
            check=False,
        )
        if result.returncode:
            raise CasMismatch("remote control ref lost compare-and-set")

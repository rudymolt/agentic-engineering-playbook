"""Non-interactive CR1-CR10 runner for a project Cloud readiness profile."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import stat
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .canonical import canonical_bytes, digest, load_strict
from .cloud import CR_IDS, validate_readiness_profile
from .contracts import ContractError, ContractRegistry


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _version_matches(actual: tuple[int, int, int], constraint: str) -> bool:
    for operator, major, minor, patch in re.findall(r"(>=|<=|>|<|==)\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", constraint):
        expected = (int(major), int(minor or 0), int(patch or 0))
        if not {">=": actual >= expected, "<=": actual <= expected, ">": actual > expected, "<": actual < expected, "==": actual == expected}[operator]:
            return False
    return True


def _version_ok(output: str, constraint: str) -> bool:
    candidates = [
        tuple(int(item or 0) for item in found.groups())
        for found in re.finditer(r"(?<![\w/])[vV]?(\d+)\.(\d+)(?:\.(\d+))?(?![\w/])", output)
    ]
    return bool(candidates) and _version_matches(candidates[-1], constraint)


def _environment_presence(environ: dict[str, str], required: list[dict[str, Any]]) -> dict[str, bool]:
    return {item["name"]: bool(environ.get(item["name"])) for item in required}


class CloudReadinessRunner:
    def __init__(self, project: Path, profile: dict[str, Any], evidence_dir: Path, registry: ContractRegistry, environ: dict[str, str] | None = None):
        self.project = project.resolve()
        self.profile = profile
        self.evidence_root = evidence_dir.resolve()
        self.evidence_dir: Path | None = None
        self.registry = registry
        self.environ = dict(os.environ if environ is None else environ)
        self.locators: list[str] = []
        self.conditions = {item: {"outcome": "not-run", "evidence_locators": []} for item in CR_IDS}
        self.expected_evidence: dict[str, str] = {}
        self.evidence_root_fd: int | None = None
        self.evidence_dir_fd: int | None = None
        self.evidence_root_identity: tuple[int, int] | None = None
        self.evidence_dir_identity: tuple[int, int] | None = None
        self.evidence_dir_name: str | None = None
        self.evidence_root.mkdir(parents=True, exist_ok=True)

    def __del__(self) -> None:
        for attribute in ("evidence_dir_fd", "evidence_root_fd"):
            descriptor = getattr(self, attribute, None)
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                setattr(self, attribute, None)

    @staticmethod
    def _readiness_component(readiness_id: Any) -> str:
        if not isinstance(readiness_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", readiness_id):
            raise ContractError("readiness_id must be a safe single path component")
        if readiness_id in {".", ".."}:
            raise ContractError("readiness_id must be a safe single path component")
        return readiness_id

    def _prepare_evidence_dir(self, readiness_id: Any) -> None:
        component = self._readiness_component(readiness_id)
        name = f"{component}-evidence"
        root_fd = os.open(self.evidence_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.mkdir(name, mode=0o700, dir_fd=root_fd)
            directory_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
        except FileExistsError as exc:
            os.close(root_fd)
            raise ContractError("readiness evidence directory already exists") from exc
        except OSError:
            os.close(root_fd)
            raise
        root_stat = os.fstat(root_fd)
        directory_stat = os.fstat(directory_fd)
        self.evidence_root_fd = root_fd
        self.evidence_dir_fd = directory_fd
        self.evidence_root_identity = (root_stat.st_dev, root_stat.st_ino)
        self.evidence_dir_identity = (directory_stat.st_dev, directory_stat.st_ino)
        self.evidence_dir_name = name
        target = self.evidence_root / name
        self.evidence_dir = target

    def _evidence_path(self, condition: str, label: str) -> Path:
        if self.evidence_dir is None:
            raise ContractError("readiness evidence directory is not initialized")
        filename = f"{condition.lower()}-{label}.log"
        if not re.fullmatch(r"[a-z0-9][A-Za-z0-9._-]*\.log", filename):
            raise ContractError("readiness evidence label is not a safe path component")
        return self.evidence_dir / filename

    def _evidence_inventory_retained(self) -> bool:
        if None in (
            self.evidence_dir_fd, self.evidence_root_fd, self.evidence_root_identity,
            self.evidence_dir_identity, self.evidence_dir_name,
        ):
            return False
        try:
            root_path_stat = os.stat(self.evidence_root, follow_symlinks=False)
            root_fd_stat = os.fstat(self.evidence_root_fd)
            directory_path_stat = os.stat(self.evidence_dir_name, dir_fd=self.evidence_root_fd, follow_symlinks=False)
            directory_fd_stat = os.fstat(self.evidence_dir_fd)
        except OSError:
            return False
        if not stat.S_ISDIR(root_path_stat.st_mode) or not stat.S_ISDIR(directory_path_stat.st_mode):
            return False
        if (root_path_stat.st_dev, root_path_stat.st_ino) != self.evidence_root_identity:
            return False
        if (root_fd_stat.st_dev, root_fd_stat.st_ino) != self.evidence_root_identity:
            return False
        if (directory_path_stat.st_dev, directory_path_stat.st_ino) != self.evidence_dir_identity:
            return False
        if (directory_fd_stat.st_dev, directory_fd_stat.st_ino) != self.evidence_dir_identity:
            return False
        try:
            actual = set(os.listdir(self.evidence_dir_fd))
        except OSError:
            return False
        if actual != set(self.expected_evidence):
            return False
        verified_entries: dict[str, tuple[int, int, int, int, int]] = {}
        for name, expected_digest in self.expected_evidence.items():
            try:
                entry_stat = os.stat(name, dir_fd=self.evidence_dir_fd, follow_symlinks=False)
                if not stat.S_ISREG(entry_stat.st_mode):
                    return False
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.evidence_dir_fd)
                with os.fdopen(descriptor, "rb") as handle:
                    opened_stat = os.fstat(handle.fileno())
                    if not stat.S_ISREG(opened_stat.st_mode):
                        return False
                    if (opened_stat.st_dev, opened_stat.st_ino) != (entry_stat.st_dev, entry_stat.st_ino):
                        return False
                    actual_digest = _sha(handle.read())
                    final_opened_stat = os.fstat(handle.fileno())
            except OSError:
                return False
            try:
                final_entry_stat = os.stat(name, dir_fd=self.evidence_dir_fd, follow_symlinks=False)
            except OSError:
                return False
            opened_identity = (opened_stat.st_dev, opened_stat.st_ino)
            if (final_opened_stat.st_dev, final_opened_stat.st_ino) != opened_identity:
                return False
            if (final_entry_stat.st_dev, final_entry_stat.st_ino) != opened_identity:
                return False
            if (
                final_opened_stat.st_size != opened_stat.st_size
                or final_opened_stat.st_mtime_ns != opened_stat.st_mtime_ns
                or final_opened_stat.st_ctime_ns != opened_stat.st_ctime_ns
            ):
                return False
            if actual_digest != expected_digest:
                return False
            verified_entries[name] = (
                opened_stat.st_dev, opened_stat.st_ino, opened_stat.st_size,
                opened_stat.st_mtime_ns, opened_stat.st_ctime_ns,
            )
        try:
            final_root_stat = os.stat(self.evidence_root, follow_symlinks=False)
            final_directory_stat = os.stat(self.evidence_dir_name, dir_fd=self.evidence_root_fd, follow_symlinks=False)
            final_actual = set(os.listdir(self.evidence_dir_fd))
        except OSError:
            return False
        if (final_root_stat.st_dev, final_root_stat.st_ino) != self.evidence_root_identity:
            return False
        if (final_directory_stat.st_dev, final_directory_stat.st_ino) != self.evidence_dir_identity:
            return False
        if final_actual != set(self.expected_evidence):
            return False
        # Revalidate every directory entry only after every digest has been
        # read. This makes the accepted inventory one coherent final snapshot
        # rather than allowing an already-checked entry to be exchanged while
        # a later entry is being hashed.
        for name, identity in verified_entries.items():
            try:
                final_entry_stat = os.stat(name, dir_fd=self.evidence_dir_fd, follow_symlinks=False)
            except OSError:
                return False
            if not stat.S_ISREG(final_entry_stat.st_mode):
                return False
            final_identity = (
                final_entry_stat.st_dev, final_entry_stat.st_ino, final_entry_stat.st_size,
                final_entry_stat.st_mtime_ns, final_entry_stat.st_ctime_ns,
            )
            if final_identity != identity:
                return False
        return True

    def _record(self, condition: str, label: str, raw: bytes) -> str:
        # Never persist an environment value named as a secret. This is a
        # last-resort guard in addition to presence-only CR4 probing.
        for item in self.profile["cloud"]["required_environment"]:
            if item["kind"] == "secret":
                secret = self.environ.get(item["name"])
                if secret:
                    raw = raw.replace(secret.encode(), b"[REDACTED]")
        path = self._evidence_path(condition, label)
        if self.evidence_dir_fd is None:
            raise ContractError("readiness evidence directory is not initialized")
        try:
            descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.evidence_dir_fd)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
        except FileExistsError as exc:
            raise ContractError("readiness evidence entry already exists") from exc
        self.expected_evidence[path.name] = _sha(raw)
        locator = (
            "artifact:" + path.relative_to(self.project).as_posix()
            if path.is_relative_to(self.project)
            else "artifact:external/" + path.relative_to(self.evidence_root).as_posix()
        )
        self.locators.append(locator)
        self.conditions[condition]["evidence_locators"].append(locator)
        return _sha(raw)

    def _command(self, condition: str, label: str, command: str, timeout: int = 900) -> tuple[bool, str]:
        try:
            completed = subprocess.run(
                command, cwd=self.project, env=self.environ, shell=True, executable="/bin/bash",
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False,
            )
            return completed.returncode == 0, self._record(condition, label, completed.stdout + f"\nexit={completed.returncode}\n".encode())
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b"") + (exc.stderr or b"") + b"\ntimeout=true\n"
            return False, self._record(condition, label, output)

    def _fingerprint_paths(self, paths: list[str]) -> str:
        items = []
        for relative in sorted(paths):
            path = self.project / relative
            if path.is_file():
                items.append({"path": relative, "digest": _sha(path.read_bytes())})
            elif path.is_dir():
                for child in sorted(item for item in path.rglob("*") if item.is_file()):
                    items.append({"path": child.relative_to(self.project).as_posix(), "digest": _sha(child.read_bytes())})
            else:
                items.append({"path": relative, "missing": True})
        return digest(items)

    @staticmethod
    def _healthy(url: str, attempts: int = 20) -> bool:
        for _ in range(attempts):
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if 200 <= response.status < 400:
                        return True
            except OSError:
                time.sleep(0.25)
        return False

    def _start_service(self, condition: str, label: str, command: str, log_path: str) -> subprocess.Popen[bytes]:
        target = self.project / log_path
        target.parent.mkdir(parents=True, exist_ok=True)
        handle = target.open("ab")
        process = subprocess.Popen(
            command, cwd=self.project, env=self.environ, shell=True, executable="/bin/bash",
            stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
        )
        handle.close()
        self._record(condition, label, canonical_bytes({"command_digest": _sha(command.encode()), "pid": process.pid}))
        return process

    def _finish(self, condition: str, passed: bool) -> None:
        self.conditions[condition]["outcome"] = "pass" if passed else "fail"

    def run(self, facts: dict[str, Any]) -> dict[str, Any]:
        self._prepare_evidence_dir(facts.get("readiness_id"))
        started = _now()
        profile_digest = validate_readiness_profile(self.profile, self.project, self.registry, facts.get("expected_profile_digest"))
        self._record("CR1", "profile", canonical_bytes({"profile_digest": profile_digest}))
        self._finish("CR1", True)

        cloud = self.profile["cloud"]
        epoch_ok = (
            self.environ.get(cloud["build_epoch_name"]) == cloud["expected_build_epoch"]
            and self.environ.get(cloud["setup_epoch_name"]) == cloud["expected_setup_epoch"]
        )
        host_os = (platform.platform() + " " + Path("/etc/os-release").read_text(errors="replace")).lower()
        os_ok = cloud["os_family"].lower().replace("-", " ") in host_os.replace("-", " ")
        tool_digests: dict[str, str] = {}
        tools_ok = True
        for probe in cloud["tool_probes"]:
            ok, evidence_digest = self._command("CR2", "tool-" + probe["name"], probe["command"])
            raw = self._evidence_path("CR2", "tool-" + probe["name"]).read_text(errors="replace")
            tools_ok = tools_ok and ok and _version_ok(raw, probe["version"])
            tool_digests[probe["name"]] = evidence_digest
        self._record("CR2", "epochs", canonical_bytes({"build": epoch_ok, "os": os_ok}))
        repository_present = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=self.project,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        ).returncode == 0
        self._finish("CR2", epoch_ok and os_ok and tools_ok and repository_present)

        setup = cloud["repository_setup_ref"]
        state_paths = facts.get("dependency_state_paths")
        if not isinstance(state_paths, list) or not state_paths:
            raise ContractError("Cloud runner facts require dependency_state_paths")
        first, _ = self._command("CR3", "setup-1", setup)
        first_state = self._fingerprint_paths(state_paths)
        second, _ = self._command("CR3", "setup-2", setup)
        second_state = self._fingerprint_paths(state_paths)
        self._record("CR3", "dependency-state", canonical_bytes({
            "after_first": first_state,
            "after_second": second_state,
            "identical": first_state == second_state,
        }))
        self._finish("CR3", first and second and first_state == second_state)

        presence = _environment_presence(self.environ, cloud["required_environment"])
        self._record("CR4", "presence", canonical_bytes(presence))
        self._finish("CR4", all(presence.values()))

        data_ok = True
        for name in ("reset", "migrate", "seed"):
            ok, _ = self._command("CR5", name, self.profile["data"][name])
            data_ok = data_ok and ok
        self._finish("CR5", data_ok and facts.get("data_environment") == "isolated-qa" and self.profile["data"]["test_accounts_ref"].startswith("secret-ref:"))

        verify_ok = True
        verify_digests: dict[str, str] = {}
        for index, command in enumerate(self.profile["verification"]["commands"]):
            ok, evidence_digest = self._command("CR6", f"verify-{index + 1}", command)
            verify_ok = verify_ok and ok
            verify_digests[str(index + 1)] = evidence_digest
        self._finish("CR6", verify_ok)

        service_ok = True
        for service in self.profile["services"]:
            process = self._start_service("CR7", service["id"] + "-start", service["start"], service["log_paths"][0])
            healthy = self._healthy(service["healthcheck"])
            logs = all((self.project / path).is_file() and (self.project / path).stat().st_size > 0 for path in service["log_paths"])
            stopped, _ = self._command("CR7", service["id"] + "-stop", service["stop"])
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            exited = process.poll() is not None
            self._record("CR7", service["id"] + "-observation", canonical_bytes({
                "healthy": healthy, "logs_ready": logs, "stopped": stopped, "process_exited": exited,
            }))
            service_ok = service_ok and healthy and logs and stopped and exited
        self._finish("CR7", service_ok)

        review_ok = facts.get("review_principal") in {"qa", "checker"}
        restart_processes: list[subprocess.Popen[bytes]] = []
        for service in self.profile["services"]:
            restart_process = self._start_service("CR8", service["id"] + "-restart", service["restart"], service["log_paths"][0])
            restart_processes.append(restart_process)
            service_healthy = self._healthy(service["healthcheck"])
            self._record("CR8", service["id"] + "-health", canonical_bytes({"healthy": service_healthy}))
            review_ok = review_ok and service_healthy
            try:
                restart_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # A legitimate foreground service remains live for CR8/CR9;
                # CR10 cleanup owns its termination.
                pass
        preview_healthy = self._healthy(self.profile["preview"]["health_url"])
        self._record("CR8", "preview-health", canonical_bytes({"healthy": preview_healthy}))
        review_ok = review_ok and preview_healthy
        self._finish("CR8", review_ok)

        journeys = load_strict((self.project / self.profile["browser_review"]["journeys_ref"]).read_bytes())
        journey_list = journeys.get("journeys") if isinstance(journeys, dict) else None
        browser_ok = isinstance(journey_list, list) and bool(journey_list)
        if browser_ok:
            for index, journey in enumerate(journey_list):
                if not isinstance(journey, dict) or set(journey) != {"id", "command", "evidence_paths"}:
                    browser_ok = False
                    break
                ok, _ = self._command("CR9", f"journey-{index + 1}", journey["command"])
                paths = journey["evidence_paths"]
                required_evidence = {"assertions", "screenshots", "console", "failed-network", "trace"}
                evidence_ok = isinstance(paths, dict) and set(paths) == required_evidence and all((self.project / path).is_file() for path in paths.values())
                if evidence_ok:
                    for evidence_type, path in paths.items():
                        self._record(
                            "CR9", f"journey-{index + 1}-browser-{evidence_type}",
                            (self.project / path).read_bytes(),
                        )
                browser_ok = browser_ok and ok and evidence_ok
        self._finish("CR9", browser_ok)

        loss_ok, _ = self._command("CR10", "process-loss", self.profile["recovery"]["process_loss_probe"])
        resume_ok, _ = self._command("CR10", "resume", self.profile["recovery"]["resume"])
        post_resume_health = {
            service["id"]: self._healthy(service["healthcheck"])
            for service in self.profile["services"]
        } if resume_ok else {service["id"]: False for service in self.profile["services"]}
        recovered = resume_ok and all(post_resume_health.values())
        cleanup_ok, _ = self._command("CR10", "cleanup", self.profile["cleanup"])
        for restart_process in restart_processes:
            if restart_process.poll() is None:
                try:
                    restart_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    restart_process.terminate()
                    restart_process.wait(timeout=5)
        residue_paths = facts.get("cleanup_residue_paths", [])
        no_residue = isinstance(residue_paths, list) and all(not (self.project / path).exists() for path in residue_paths)
        self._record("CR10", "recovery-observation", canonical_bytes({
            "process_loss_exit_zero": loss_ok,
            "resume_exit_zero": resume_ok,
            "post_resume_health": post_resume_health,
            "cleanup_exit_zero": cleanup_ok,
            "residue_absent": no_residue,
        }))
        evidence_retained = self._evidence_inventory_retained()
        self._finish("CR10", loss_ok and recovered and cleanup_ok and no_residue and evidence_retained)

        ended = _now()
        receipt = {
            "schema_version": 1, "readiness_id": facts["readiness_id"], "mode": facts["mode"],
            "profile_id": self.profile["profile_id"], "profile_digest": profile_digest,
            "observed_build_epoch": self.environ.get(cloud["build_epoch_name"], ""),
            "observed_setup_epoch": self.environ.get(cloud["setup_epoch_name"], ""),
            "repository": facts["repository"], "base_sha": facts["base_sha"], "head_sha": facts["head_sha"], "tree_sha": facts["tree_sha"],
            "dependency_lock_digest": facts["dependency_lock_digest"],
            "bound_digests": {"setup": cloud["repository_setup_digest"], "journeys": self.profile["browser_review"]["journeys_digest"], "resume": self.profile["recovery"]["resume_digest"], "cleanup": self.profile["cleanup_digest"]},
            "environment_presence": presence,
            "fingerprints": {
                "tools": tool_digests,
                "verification": verify_digests,
                "evidence": dict(sorted(self.expected_evidence.items())),
            },
            "conditions": self.conditions, "raw_evidence_locators": self.locators,
            "review_route": self.profile["preview"]["review_route"], "started_at": _stamp(started), "ended_at": _stamp(ended),
            "expires_at": _stamp(ended + timedelta(days=30)), "issuer": facts["issuer"],
        }
        if facts["mode"] == "candidate":
            receipt["candidate"] = facts["candidate"]
        return receipt

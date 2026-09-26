#!/usr/bin/env python3
"""Continuously fingerprint a read-only checker checkout from external evidence storage."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import select
import signal
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True
SHA256_PREFIX = "sha256:"
CHECKPOINT_PREFIX = "refs/conductor-checkpoints/"
STATE_NAME = "monitor-state.json"
BASELINE_NAME = "source-baseline.json"
READY_NAME = "monitor-ready.json"
STOP_NAME = "monitor.stop"
OUTCOME_NAME = "monitor-outcome.json"
EVENTS_NAME = "monitor-events.jsonl"
STDOUT_NAME = "monitor-stdout.log"
STDERR_NAME = "monitor-stderr.log"
MONITOR_BACKEND = "linux-inotify"
GIT_WRITER_ATTRIBUTION_BACKEND = "linux-fanotify-pid"
IN_MODIFY = 0x00000002
IN_ATTRIB = 0x00000004
IN_CLOSE_WRITE = 0x00000008
IN_MOVED_FROM = 0x00000040
IN_MOVED_TO = 0x00000080
IN_CREATE = 0x00000100
IN_DELETE = 0x00000200
IN_DELETE_SELF = 0x00000400
IN_MOVE_SELF = 0x00000800
IN_Q_OVERFLOW = 0x00004000
IN_IGNORED = 0x00008000
WATCH_MASK = (
    IN_MODIFY
    | IN_ATTRIB
    | IN_CLOSE_WRITE
    | IN_MOVED_FROM
    | IN_MOVED_TO
    | IN_CREATE
    | IN_DELETE
    | IN_DELETE_SELF
    | IN_MOVE_SELF
    | IN_Q_OVERFLOW
)
INOTIFY_EVENT = struct.Struct("iIII")
FAN_CLOEXEC = 0x00000001
FAN_NONBLOCK = 0x00000002
FAN_CLASS_NOTIF = 0x00000000
FAN_MARK_ADD = 0x00000001
FAN_MARK_ONLYDIR = 0x00000008
FAN_MODIFY = 0x00000002
FAN_CLOSE_WRITE = 0x00000008
FAN_OPEN = 0x00000020
FAN_Q_OVERFLOW = 0x00004000
FAN_EVENT_ON_CHILD = 0x08000000
FANOTIFY_METADATA_VERSION = 3
FANOTIFY_EVENT = struct.Struct("=IBBHQii")


class MonitorError(RuntimeError):
    pass


class InotifyWatcher:
    def __init__(self, repository: Path, git_dir: Path) -> None:
        if platform.system() != "Linux":
            raise MonitorError("checker monitor requires Linux inotify for Launcher V4")
        self.repository = repository
        self.git_dir = git_dir
        self.paths: dict[int, Path] = {}
        libc = ctypes.CDLL(None, use_errno=True)
        self._add_watch = libc.inotify_add_watch
        self._add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
        self._add_watch.restype = ctypes.c_int
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            error = ctypes.get_errno()
            raise MonitorError(f"inotify_init1 failed: {os.strerror(error)}")
        try:
            self._watch_tree(repository, prune_git=True)
            self._watch_tree(git_dir, prune_git=False)
        except Exception:
            os.close(self.fd)
            raise

    def close(self) -> None:
        os.close(self.fd)

    def _allowed_git_subtree(self, path: Path) -> bool:
        relative = path.relative_to(self.git_dir)
        parts = relative.parts
        return (
            (parts and parts[0] == "objects")
            or parts[:2] == ("refs", "conductor-checkpoints")
            or parts[:3] == ("logs", "refs", "conductor-checkpoints")
        )

    def _watch_tree(self, root: Path, *, prune_git: bool) -> None:
        for current, directories, _files in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            retained: list[str] = []
            for name in directories:
                child = current_path / name
                if child.is_symlink():
                    continue
                if prune_git and child == self.git_dir:
                    continue
                if not prune_git and self._allowed_git_subtree(child):
                    continue
                retained.append(name)
            directories[:] = retained
            descriptor = self._add_watch(self.fd, os.fsencode(current_path), WATCH_MASK)
            if descriptor < 0:
                error = ctypes.get_errno()
                raise MonitorError(f"inotify_add_watch failed for {current_path}: {os.strerror(error)}")
            self.paths[descriptor] = current_path

    def _allowed_path(self, path: Path) -> bool:
        if path == self.git_dir or path.is_relative_to(self.git_dir):
            return self._allowed_git_subtree(path)
        return False

    def read_events(self) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        while True:
            try:
                raw = os.read(self.fd, 1024 * 1024)
            except BlockingIOError:
                break
            if not raw:
                break
            offset = 0
            while offset < len(raw):
                if len(raw) - offset < INOTIFY_EVENT.size:
                    raise MonitorError("malformed inotify event header")
                descriptor, mask, cookie, name_length = INOTIFY_EVENT.unpack_from(raw, offset)
                offset += INOTIFY_EVENT.size
                if name_length > len(raw) - offset:
                    raise MonitorError("malformed inotify event name")
                name = raw[offset:offset + name_length].split(b"\0", 1)[0]
                offset += name_length
                base = self.paths.get(descriptor)
                path = (base / os.fsdecode(name)) if base is not None and name else base
                overflow = bool(mask & IN_Q_OVERFLOW)
                allowed = path is not None and self._allowed_path(path)
                events.append({
                    "observed_at": now(),
                    "path": str(path) if path is not None else None,
                    "mask": mask,
                    "cookie": cookie,
                    "allowed_checkpoint_metadata": allowed,
                    "invalidating": overflow or bool(mask & IN_IGNORED) or not allowed,
                })
        return events


class GitWriterAttributor:
    """Bind Git-directory opens to the writer PID reported by the kernel."""

    def __init__(self, git_dir: Path, monitor_processes: dict[int, dict[str, object]]) -> None:
        if platform.system() != "Linux":
            raise MonitorError("Git writer attribution requires Linux fanotify")
        self.git_dir = git_dir
        self.monitor_processes = monitor_processes
        libc = ctypes.CDLL(None, use_errno=True)
        self._mark = libc.fanotify_mark
        self._mark.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_ulonglong, ctypes.c_int, ctypes.c_char_p]
        self._mark.restype = ctypes.c_int
        libc.fanotify_init.argtypes = [ctypes.c_uint, ctypes.c_uint]
        libc.fanotify_init.restype = ctypes.c_int
        self.fd = libc.fanotify_init(
            FAN_CLOEXEC | FAN_NONBLOCK | FAN_CLASS_NOTIF,
            os.O_RDONLY | os.O_CLOEXEC,
        )
        if self.fd < 0:
            error = ctypes.get_errno()
            raise MonitorError(f"fanotify_init failed: {os.strerror(error)}")
        try:
            self._mark_git_directories()
        except Exception:
            os.close(self.fd)
            raise

    def close(self) -> None:
        os.close(self.fd)

    def _allowed_git_subtree(self, path: Path) -> bool:
        relative = path.relative_to(self.git_dir)
        parts = relative.parts
        return (
            (parts and parts[0] == "objects")
            or parts[:2] == ("refs", "conductor-checkpoints")
            or parts[:3] == ("logs", "refs", "conductor-checkpoints")
        )

    def _mark_git_directories(self) -> None:
        mask = FAN_OPEN | FAN_MODIFY | FAN_CLOSE_WRITE | FAN_EVENT_ON_CHILD
        for current, directories, _files in os.walk(self.git_dir, topdown=True, followlinks=False):
            current_path = Path(current)
            directories[:] = [
                name
                for name in directories
                if not (current_path / name).is_symlink()
                and not self._allowed_git_subtree(current_path / name)
            ]
            result = self._mark(
                self.fd,
                FAN_MARK_ADD | FAN_MARK_ONLYDIR,
                mask,
                -100,
                os.fsencode(current_path),
            )
            if result < 0:
                error = ctypes.get_errno()
                raise MonitorError(
                    f"fanotify_mark failed for {current_path}: {os.strerror(error)}"
                )

    @staticmethod
    def _proc_bytes(pid: int, name: str) -> bytes:
        try:
            return (Path("/proc") / str(pid) / name).read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            return b""

    @staticmethod
    def _safe_name(raw: bytes) -> str | None:
        if not raw:
            return None
        rendered = raw.decode(errors="replace").strip().replace("\x00", "")
        return rendered[:128] or None

    def _writer(self, pid: int) -> dict[str, object]:
        owned = self.monitor_processes.get(pid)
        command = self._proc_bytes(pid, "cmdline")
        comm = self._safe_name(self._proc_bytes(pid, "comm"))
        stat = self._proc_bytes(pid, "stat").decode(errors="replace")
        parent_pid: int | None = None
        start_ticks: int | None = None
        closing = stat.rfind(")")
        if closing >= 0:
            fields = stat[closing + 2:].split()
            try:
                parent_pid = int(fields[1])
                start_ticks = int(fields[19])
            except (IndexError, ValueError):
                parent_pid = None
                start_ticks = None
        if owned is not None:
            registered_at = owned.get("registered_at_monotonic")
            registered_start = owned.get("process_start_ticks")
            recent = isinstance(registered_at, float) and time.monotonic() - registered_at <= 5
            same_process = (
                registered_start is None
                or start_ticks is None
                or registered_start == start_ticks
            )
            if not recent or not same_process:
                owned = None
        try:
            executable = os.readlink(Path("/proc") / str(pid) / "exe")
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            executable = ""
        return {
            "status": "attributed",
            "backend": GIT_WRITER_ATTRIBUTION_BACKEND,
            "writer_pid": pid,
            "actor_kind": "monitor-owned" if owned is not None else "external-process",
            "monitor_role": owned.get("monitor_role") if owned is not None else None,
            "process_name": comm,
            "parent_pid": parent_pid,
            "process_start_ticks": start_ticks,
            "executable_digest": sha256_bytes(executable.encode()),
            "command_digest": sha256_bytes(command),
        }

    def read_events(self) -> list[dict[str, object]]:
        events: list[dict[str, object]] = []
        while True:
            try:
                raw = os.read(self.fd, 1024 * 1024)
            except BlockingIOError:
                break
            if not raw:
                break
            offset = 0
            while offset < len(raw):
                if len(raw) - offset < FANOTIFY_EVENT.size:
                    raise MonitorError("malformed fanotify event header")
                event_length, version, _reserved, metadata_length, mask, event_fd, pid = FANOTIFY_EVENT.unpack_from(raw, offset)
                if (
                    event_length < FANOTIFY_EVENT.size
                    or metadata_length < FANOTIFY_EVENT.size
                    or event_length > len(raw) - offset
                ):
                    raise MonitorError("malformed fanotify event length")
                offset += event_length
                if version != FANOTIFY_METADATA_VERSION:
                    raise MonitorError(f"unsupported fanotify metadata version: {version}")
                if mask & FAN_Q_OVERFLOW or event_fd < 0:
                    raise MonitorError("fanotify attribution queue overflow")
                try:
                    raw_path = os.readlink(Path("/proc/self/fd") / str(event_fd))
                    if raw_path.endswith(" (deleted)"):
                        raw_path = raw_path.removesuffix(" (deleted)")
                    path = str(Path(raw_path).resolve(strict=False))
                    events.append({
                        "observed_at": now(),
                        "path": path,
                        "mask": mask,
                        "writer": self._writer(pid),
                    })
                finally:
                    os.close(event_fd)
        return events


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def sha256_bytes(raw: bytes) -> str:
    return SHA256_PREFIX + hashlib.sha256(raw).hexdigest()


def write_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(canonical_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise MonitorError(f"{path.name} must contain an object")
    return value


def run_git(
    repository: Path,
    *args: str,
    monitor_processes: dict[int, dict[str, object]] | None = None,
) -> bytes:
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    process = subprocess.Popen(
        ["git", "-C", str(repository), *args],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if monitor_processes is not None:
        stat = GitWriterAttributor._proc_bytes(process.pid, "stat").decode(errors="replace")
        closing = stat.rfind(")")
        fields = stat[closing + 2:].split() if closing >= 0 else []
        try:
            process_start_ticks: int | None = int(fields[19])
        except (IndexError, ValueError):
            process_start_ticks = None
        monitor_processes[process.pid] = {
            "monitor_role": "source-fingerprint",
            "command_digest": sha256_bytes(canonical_bytes(list(args))),
            "process_start_ticks": process_start_ticks,
            "registered_at_monotonic": time.monotonic(),
        }
    stdout, stderr = process.communicate()
    if process.returncode:
        message = stderr.decode(errors="replace").strip()
        raise MonitorError(f"git {' '.join(args)} failed: {message}")
    return stdout


def source_fingerprint(
    repository: Path,
    monitor_processes: dict[int, dict[str, object]] | None = None,
) -> dict[str, object]:
    def git(*args: str) -> bytes:
        return run_git(repository, *args, monitor_processes=monitor_processes)

    head = git("rev-parse", "HEAD").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    index = git("ls-files", "--stage", "-z")
    staged = git("diff", "--cached", "--binary", "--no-ext-diff")
    worktree = git("diff", "--binary", "--no-ext-diff")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")
    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    raw_refs = git("for-each-ref", "--format=%(refname)%00%(objectname)")
    noncheckpoint_refs = b"\n".join(
        line for line in raw_refs.splitlines()
        if line and not line.decode(errors="strict").startswith(CHECKPOINT_PREFIX)
    )
    return {
        "head_sha": head,
        "tree_sha": tree,
        "index_digest": sha256_bytes(index),
        "staged_diff_digest": sha256_bytes(staged),
        "worktree_diff_digest": sha256_bytes(worktree),
        "untracked_inventory_digest": sha256_bytes(untracked),
        "noncheckpoint_refs_digest": sha256_bytes(noncheckpoint_refs),
        "clean": status == b"",
    }


def absolute_git_dir(repository: Path) -> Path:
    return Path(run_git(repository, "rev-parse", "--absolute-git-dir").decode().strip()).resolve(strict=True)


def fingerprint_digest(value: dict[str, object]) -> str:
    return sha256_bytes(canonical_bytes(value))


def require_external(evidence_dir: Path, repository: Path) -> None:
    if evidence_dir == repository or evidence_dir.is_relative_to(repository):
        raise MonitorError("evidence directory must be outside the repository")


def require_external_to_git(evidence_dir: Path, git_dir: Path) -> None:
    if evidence_dir == git_dir or evidence_dir.is_relative_to(git_dir):
        raise MonitorError("evidence directory must be outside the repository Git directory")


def require_python_policy() -> None:
    if (
        os.environ.get("AI_PLAYBOOK_CHECKER_PYTHON_WRAPPER") != "1"
        or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
        or sys.flags.dont_write_bytecode != 1
    ):
        raise MonitorError("checker monitor must run through scripts/checker-python.py")


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def append_event(path: Path, value: object) -> None:
    with path.open("ab") as handle:
        handle.write(canonical_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())


def is_git_lock(path: object, git_dir: Path) -> bool:
    if not isinstance(path, str):
        return False
    candidate = Path(path)
    return candidate.name.endswith(".lock") and candidate.is_relative_to(git_dir)


def monitor_process(repository: Path, evidence_dir: Path, interval_ms: int) -> int:
    events = evidence_dir / EVENTS_NAME
    stop = evidence_dir / STOP_NAME
    outcome = evidence_dir / OUTCOME_NAME
    started_at = now()
    checks = 0
    violations = 0
    event_count = 0
    attribution_event_count = 0
    log_sequence = 0
    interrupted: list[str] = []
    monitor_processes: dict[int, dict[str, object]] = {}
    writer_attributions: dict[str, dict[str, object]] = {}
    active_lock_attributions: dict[str, dict[str, object]] = {}

    def terminate(signum: int, _frame: object) -> None:
        interrupted.append(signal.Signals(signum).name)

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    watcher: InotifyWatcher | None = None
    writer_attributor: GitWriterAttributor | None = None
    git_dir: Path | None = None

    def record_writer_events() -> None:
        nonlocal attribution_event_count, log_sequence
        if writer_attributor is None:
            return
        for writer_event in writer_attributor.read_events():
            attribution_event_count += 1
            log_sequence += 1
            record = {
                "schema_version": 1,
                "event_type": "git-writer-attribution",
                "sequence": log_sequence,
                **writer_event,
            }
            append_event(events, record)
            writer_attributions[str(writer_event["path"])] = {
                **dict(writer_event["writer"]),
                "attribution_sequence": log_sequence,
                "attributed_at": writer_event["observed_at"],
                "unbound": True,
            }

    def record_source_events(source_events: list[dict[str, object]]) -> list[dict[str, object]]:
        nonlocal event_count, log_sequence
        if git_dir is None:
            raise MonitorError("Git directory unavailable during event recording")
        for source_event in source_events:
            if is_git_lock(source_event.get("path"), git_dir):
                record_writer_events()
                path = str(source_event["path"])
                attribution = writer_attributions.get(path)
                if attribution is None and writer_attributor is not None:
                    select.select([writer_attributor.fd], [], [], 0.05)
                    record_writer_events()
                    attribution = writer_attributions.get(path)
                begins_lock_generation = bool(
                    int(source_event.get("mask", 0)) & (IN_CREATE | IN_MOVED_TO)
                )
                if begins_lock_generation:
                    if attribution is not None and attribution.get("unbound") is True:
                        active_lock_attributions[path] = attribution
                        attribution["unbound"] = False
                    else:
                        attribution = None
                else:
                    attribution = active_lock_attributions.get(path) or (
                        attribution if attribution is not None and attribution.get("unbound") is True else None
                    )
                    if attribution is not None and path not in active_lock_attributions:
                        active_lock_attributions[path] = attribution
                        attribution["unbound"] = False
                source_event["git_writer_attribution"] = (
                    {key: value for key, value in attribution.items() if key != "unbound"}
                    if attribution is not None
                    else {
                        "status": "unattributed",
                        "backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                        "writer_pid": None,
                        "actor_kind": "unknown",
                    }
                )
                if int(source_event.get("mask", 0)) & IN_DELETE:
                    active_lock_attributions.pop(path, None)
            event_count += 1
            log_sequence += 1
            append_event(events, {
                "schema_version": 1,
                "event_type": "filesystem",
                "sequence": log_sequence,
                **source_event,
            })
        return source_events

    try:
        git_dir = absolute_git_dir(repository)
        watcher = InotifyWatcher(repository, git_dir)
        writer_attributor = GitWriterAttributor(git_dir, monitor_processes)
        baseline = source_fingerprint(repository, monitor_processes)
        if baseline["clean"] is not True:
            raise MonitorError("checker source checkout must be clean before monitor readiness")
        record_writer_events()
        armed_events = record_source_events(watcher.read_events())
        invalid_armed = [event for event in armed_events if event["invalidating"]]
        if invalid_armed:
            raise MonitorError("source mutation observed while arming the monitor")
        baseline_record = {
            "schema_version": 1,
            "captured_at": now(),
            "monitor_backend": MONITOR_BACKEND,
            "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
            "watch_count": len(watcher.paths),
            "fingerprint": baseline,
            "fingerprint_digest": fingerprint_digest(baseline),
        }
        write_atomic(evidence_dir / BASELINE_NAME, baseline_record)
        next_fingerprint_at = time.monotonic()
        while True:
            record_writer_events()
            source_events = record_source_events(watcher.read_events())
            invalid_events = [event for event in source_events if event["invalidating"]]
            if invalid_events:
                violations += len(invalid_events)
                write_atomic(outcome, {
                    "schema_version": 1,
                    "outcome": "invalidated",
                    "reason": "transient-mutation-observed",
                    "monitor_backend": MONITOR_BACKEND,
                    "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                    "checks": checks,
                    "event_count": event_count,
                    "attribution_event_count": attribution_event_count,
                    "violation_count": violations,
                    "started_at": started_at,
                    "stopped_at": now(),
                    "invalidating_events": invalid_events,
                })
                return 2
            if checks == 0 or time.monotonic() >= next_fingerprint_at:
                observed = source_fingerprint(repository, monitor_processes)
                checks += 1
                matches = observed == baseline
                if not matches:
                    violations += 1
                log_sequence += 1
                append_event(events, {
                    "schema_version": 1,
                    "event_type": "fingerprint",
                    "sequence": log_sequence,
                    "observed_at": now(),
                    "fingerprint_digest": fingerprint_digest(observed),
                    "matches_baseline": matches,
                })
                next_fingerprint_at = time.monotonic() + interval_ms / 1000
            if violations:
                write_atomic(outcome, {
                    "schema_version": 1,
                    "outcome": "invalidated",
                    "reason": "transient-mutation-observed",
                    "monitor_backend": MONITOR_BACKEND,
                    "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                    "checks": checks,
                    "event_count": event_count,
                    "attribution_event_count": attribution_event_count,
                    "violation_count": violations,
                    "started_at": started_at,
                    "stopped_at": now(),
                    "last_fingerprint": observed,
                })
                return 2
            if checks == 1 and not (evidence_dir / READY_NAME).exists():
                write_atomic(evidence_dir / READY_NAME, {
                    "schema_version": 1,
                    "outcome": "ready",
                    "monitor_backend": MONITOR_BACKEND,
                    "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                    "checks": checks,
                    "event_count": event_count,
                    "attribution_event_count": attribution_event_count,
                    "observed_at": now(),
                    "baseline_digest": fingerprint_digest(baseline),
                })
            if interrupted:
                write_atomic(outcome, {
                    "schema_version": 1,
                    "outcome": "blocked",
                    "reason": "monitor-interrupted",
                    "monitor_backend": MONITOR_BACKEND,
                    "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                    "signal": interrupted[0],
                    "checks": checks,
                    "event_count": event_count,
                    "attribution_event_count": attribution_event_count,
                    "violation_count": violations,
                    "started_at": started_at,
                    "stopped_at": now(),
                })
                return 2
            if stop.exists():
                record_writer_events()
                final_events = record_source_events(watcher.read_events())
                invalid_final_events = [event for event in final_events if event["invalidating"]]
                final_fingerprint = source_fingerprint(repository, monitor_processes)
                checks += 1
                final_matches = final_fingerprint == baseline
                log_sequence += 1
                append_event(events, {
                    "schema_version": 1,
                    "event_type": "fingerprint",
                    "sequence": log_sequence,
                    "observed_at": now(),
                    "fingerprint_digest": fingerprint_digest(final_fingerprint),
                    "matches_baseline": final_matches,
                    "final": True,
                })
                record_writer_events()
                post_fingerprint_events = record_source_events(watcher.read_events())
                invalid_final_events.extend(
                    event for event in post_fingerprint_events if event["invalidating"]
                )
                if invalid_final_events or not final_matches:
                    violations += len(invalid_final_events) + (0 if final_matches else 1)
                    write_atomic(outcome, {
                        "schema_version": 1,
                        "outcome": "invalidated",
                        "reason": "transient-mutation-observed",
                        "monitor_backend": MONITOR_BACKEND,
                        "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                        "checks": checks,
                        "event_count": event_count,
                        "attribution_event_count": attribution_event_count,
                        "violation_count": violations,
                        "started_at": started_at,
                        "stopped_at": now(),
                        "invalidating_events": invalid_final_events,
                        "last_fingerprint": final_fingerprint,
                    })
                    return 2
                write_atomic(outcome, {
                    "schema_version": 1,
                    "outcome": "pass",
                    "monitor_backend": MONITOR_BACKEND,
                    "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                    "checks": checks,
                    "event_count": event_count,
                    "attribution_event_count": attribution_event_count,
                    "violation_count": 0,
                    "started_at": started_at,
                    "stopped_at": now(),
                })
                return 0
            select.select(
                [watcher.fd, writer_attributor.fd],
                [],
                [],
                min(0.05, max(0, next_fingerprint_at - time.monotonic())),
            )
    except (MonitorError, OSError, ValueError) as exc:
        write_atomic(outcome, {
            "schema_version": 1,
            "outcome": "blocked",
            "reason": "monitor-error",
            "monitor_backend": MONITOR_BACKEND,
            "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
            "error": str(exc),
            "checks": checks,
            "event_count": event_count,
            "attribution_event_count": attribution_event_count,
            "violation_count": violations,
            "started_at": started_at,
            "stopped_at": now(),
        })
        return 2
    finally:
        if writer_attributor is not None:
            writer_attributor.close()
        if watcher is not None:
            watcher.close()


def start(repository: Path, evidence_dir: Path, interval_ms: int, ready_timeout: float) -> dict[str, object]:
    require_python_policy()
    repository = repository.resolve(strict=True)
    evidence_dir = evidence_dir.resolve()
    require_external(evidence_dir, repository)
    require_external_to_git(evidence_dir, absolute_git_dir(repository))
    if interval_ms < 10 or interval_ms > 1000:
        raise MonitorError("interval-ms must be between 10 and 1000")
    if platform.system() != "Linux":
        raise MonitorError("checker monitor requires Linux inotify for Launcher V4")
    evidence_dir.mkdir(parents=True, exist_ok=False)
    stdout = (evidence_dir / STDOUT_NAME).open("wb")
    stderr = (evidence_dir / STDERR_NAME).open("wb")
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "_run",
            "--repository", str(repository),
            "--evidence-dir", str(evidence_dir),
            "--interval-ms", str(interval_ms),
        ],
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        env=environment,
        start_new_session=True,
    )
    stdout.close()
    stderr.close()
    state = {
        "schema_version": 1,
        "repository": str(repository),
        "evidence_dir": str(evidence_dir),
        "pid": child.pid,
        "interval_ms": interval_ms,
        "monitor_backend": MONITOR_BACKEND,
        "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
        "baseline_digest": None,
        "started_at": now(),
    }
    write_atomic(evidence_dir / STATE_NAME, state)
    deadline = time.monotonic() + ready_timeout
    ready_path = evidence_dir / READY_NAME
    outcome_path = evidence_dir / OUTCOME_NAME
    while time.monotonic() < deadline:
        if ready_path.exists():
            ready = read_json(ready_path)
            if child.poll() is not None:
                raise MonitorError("monitor exited after its first probe")
            baseline_record = read_json(evidence_dir / BASELINE_NAME)
            if (
                ready.get("monitor_backend") != MONITOR_BACKEND
                or ready.get("git_writer_attribution_backend") != GIT_WRITER_ATTRIBUTION_BACKEND
                or baseline_record.get("monitor_backend") != MONITOR_BACKEND
                or baseline_record.get("git_writer_attribution_backend") != GIT_WRITER_ATTRIBUTION_BACKEND
            ):
                raise MonitorError("monitor readiness backend identity mismatch")
            state["baseline_digest"] = baseline_record["fingerprint_digest"]
            write_atomic(evidence_dir / STATE_NAME, state)
            return {
                "schema_version": 1,
                "outcome": "started",
                "pid": child.pid,
                "checks": ready["checks"],
                "event_count": ready["event_count"],
                "monitor_backend": MONITOR_BACKEND,
                "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
                "baseline_digest": baseline_record["fingerprint_digest"],
                "evidence_dir": str(evidence_dir),
            }
        if outcome_path.exists() or child.poll() is not None:
            observed = read_json(outcome_path) if outcome_path.exists() else {"outcome": "blocked", "reason": "monitor-exited-before-ready"}
            raise MonitorError(f"monitor failed before readiness: {observed.get('reason', observed.get('outcome'))}")
        time.sleep(0.01)
    child.terminate()
    try:
        child.wait(timeout=2)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=2)
    if not outcome_path.exists():
        write_atomic(outcome_path, {
            "schema_version": 1,
            "outcome": "blocked",
            "reason": "monitor-readiness-timeout",
            "monitor_backend": MONITOR_BACKEND,
            "git_writer_attribution_backend": GIT_WRITER_ATTRIBUTION_BACKEND,
            "checks": 0,
            "violation_count": 0,
            "started_at": state["started_at"],
            "stopped_at": now(),
        })
    raise MonitorError("monitor did not complete its first probe before the readiness timeout")


def stop(evidence_dir: Path, timeout: float) -> tuple[dict[str, object], int]:
    require_python_policy()
    evidence_dir = evidence_dir.resolve(strict=True)
    state = read_json(evidence_dir / STATE_NAME)
    if (
        state.get("monitor_backend") != MONITOR_BACKEND
        or state.get("git_writer_attribution_backend") != GIT_WRITER_ATTRIBUTION_BACKEND
    ):
        raise MonitorError("monitor state backend identity mismatch")
    repository = Path(str(state["repository"])).resolve(strict=True)
    require_external(evidence_dir, repository)
    require_external_to_git(evidence_dir, absolute_git_dir(repository))
    (evidence_dir / STOP_NAME).touch(exist_ok=True)
    outcome_path = evidence_dir / OUTCOME_NAME
    deadline = time.monotonic() + timeout
    while not outcome_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not outcome_path.exists():
        raise MonitorError("monitor did not produce a terminal outcome before timeout")
    monitor = read_json(outcome_path)
    if (
        monitor.get("monitor_backend") != MONITOR_BACKEND
        or monitor.get("git_writer_attribution_backend") != GIT_WRITER_ATTRIBUTION_BACKEND
    ):
        raise MonitorError("monitor outcome backend identity mismatch")
    pid = state.get("pid")
    if not isinstance(pid, int) or pid < 1:
        raise MonitorError("monitor state has an invalid pid")
    while process_exists(pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    if process_exists(pid):
        raise MonitorError("monitor produced an outcome but did not terminate before timeout")
    if monitor.get("outcome") != "pass" or monitor.get("violation_count") != 0 or not isinstance(monitor.get("checks"), int) or monitor["checks"] < 1:
        return {
            "schema_version": 1,
            "outcome": "blocked",
            "reason": monitor.get("reason", "monitor-did-not-pass"),
            "monitor": monitor,
        }, 2
    return {**monitor, "evidence_dir": str(evidence_dir)}, 0


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="checker-monitor")
    sub = cli.add_subparsers(dest="command", required=True)
    start_parser = sub.add_parser("start")
    start_parser.add_argument("--repository", type=Path, required=True)
    start_parser.add_argument("--evidence-dir", type=Path, required=True)
    start_parser.add_argument("--interval-ms", type=int, default=100)
    start_parser.add_argument("--ready-timeout-seconds", type=float, default=10)
    run_parser = sub.add_parser("_run")
    run_parser.add_argument("--repository", type=Path, required=True)
    run_parser.add_argument("--evidence-dir", type=Path, required=True)
    run_parser.add_argument("--interval-ms", type=int, required=True)
    stop_parser = sub.add_parser("stop")
    stop_parser.add_argument("--evidence-dir", type=Path, required=True)
    stop_parser.add_argument("--timeout-seconds", type=float, default=10)
    return cli


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "start":
            result = start(args.repository, args.evidence_dir, args.interval_ms, args.ready_timeout_seconds)
            code = 0
        elif args.command == "_run":
            return monitor_process(args.repository.resolve(strict=True), args.evidence_dir.resolve(strict=True), args.interval_ms)
        else:
            result, code = stop(args.evidence_dir, args.timeout_seconds)
    except (KeyError, OSError, MonitorError, ValueError) as exc:
        result = {
            "schema_version": 1,
            "outcome": "blocked",
            "required_actions": [str(exc)],
        }
        code = 2
    sys.stdout.buffer.write(canonical_bytes(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

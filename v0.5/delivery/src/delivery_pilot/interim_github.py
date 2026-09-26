"""Validated, inactive GitHub delivery adapters for TASK-409.

They parse only locators.  Repository Actions templates check out ``main`` and
invoke this package from that checkout; no event payload is executable code.
"""
from __future__ import annotations

import argparse
import http.client
import io
import json
import os
import re
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import HTTPError, URLError
from .interim_disposition import ObservationFailure
from urllib.request import Request, urlopen
from urllib.parse import urlsplit

from .interim import InterimCheckpointError, InterimCheckpointStore
from .interim_monitor import MonitorAdapter, MonitoringPolicyError, locator, reconcile


DISPATCH_TYPE = "interim_recovery_v1"
MAX_REGISTERED_REFS = 32
MAX_REGISTERED_REF_LINE = 512
MAX_REGISTERED_OUTPUT_BYTES = MAX_REGISTERED_REFS * MAX_REGISTERED_REF_LINE
MAX_EVENT_FILE_BYTES = 131072
_CONTROL_REF = re.compile(r"^refs/heads/delivery-control/issue-[A-Za-z0-9][A-Za-z0-9._-]{0,191}$")


def repository_dispatch(payload: object) -> dict[str, str]:
    """Extract only client_payload from GitHub's larger platform envelope."""
    if not isinstance(payload, dict) or payload.get("action") != DISPATCH_TYPE or "client_payload" not in payload:
        raise MonitoringPolicyError("GitHub dispatch payload is malformed")
    return locator(payload["client_payload"])


def workflow_dispatch(locator_json: object) -> dict[str, str]:
    if not isinstance(locator_json, str):
        raise MonitoringPolicyError("workflow locator must be JSON text")
    try:
        return locator(json.loads(locator_json))
    except (json.JSONDecodeError, RecursionError) as exc:
        raise MonitoringPolicyError("workflow locator is malformed") from exc


def load_event_file(path: Path, event_name: object) -> dict[str, str]:
    """Read GitHub's bounded runner event file without logging its payload."""
    if event_name not in ("repository_dispatch", "workflow_dispatch"):
        raise MonitoringPolicyError("GitHub event type is unsupported")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_EVENT_FILE_BYTES + 1)
    except OSError as exc:
        raise MonitoringPolicyError("GitHub event file is unavailable") from exc
    if len(raw) > MAX_EVENT_FILE_BYTES:
        raise MonitoringPolicyError("GitHub event file exceeds the bounded limit")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise MonitoringPolicyError("GitHub event file is malformed") from exc
    if event_name == "repository_dispatch":
        return repository_dispatch(payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("inputs"), dict):
        raise MonitoringPolicyError("GitHub workflow dispatch inputs are malformed")
    return workflow_dispatch(payload["inputs"].get("locator"))


def backup_registry(value: object) -> list[dict[str, str]]:
    """Validate an operator-provided registry; empty is a successful zero-call scan."""
    if not isinstance(value, list):
        raise MonitoringPolicyError("monitoring registry must be a list")
    result: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in value:
        current = locator(item)
        identity = (current["run_id"], current["control_ref"], current["generation"])
        if identity in seen:
            raise MonitoringPolicyError("monitoring registry has a duplicate locator")
        seen.add(identity); result.append(current)
    return result


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise MonitoringPolicyError("Conductor " + label + " is malformed")
    return value


JsonRequest = Callable[[str, str, Optional[dict[str, Any]]], dict[str, Any]]


class _DeadlineSocket:
    """Per-request socket reads clipped to an event's monotonic deadline.

    HTTPResponse reads headers through ``makefile().readline()``. A regular
    socket timeout measures inactivity and can be defeated by drip-fed
    headers, so every underlying recv must recompute the remaining budget.
    """
    def __init__(self, sock: socket.socket, deadline: float, clock: Callable[[], float], timeout: float):
        self.sock, self.deadline, self.clock, self.timeout = sock, deadline, clock, timeout
        self._io_refs = 0
        self._closed = False

    def _clip(self) -> None:
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("event re-check elapsed budget exhausted")
        self.sock.settimeout(min(self.timeout, remaining))

    def recv_into(self, buffer: Any) -> int:
        self._clip()
        return self.sock.recv_into(buffer)

    def sendall(self, data: bytes) -> None:
        self._clip()
        self.sock.sendall(data)

    def makefile(self, mode: str = "rb") -> io.BufferedReader:
        if mode != "rb":
            raise OSError("unsupported bounded HTTP stream mode")
        self._io_refs += 1
        return io.BufferedReader(socket.SocketIO(self, "r"))

    def _decref_socketios(self) -> None:
        self._io_refs -= 1
        if self._closed and self._io_refs == 0:
            self.sock.close()

    def close(self) -> None:
        self._closed = True
        if self._io_refs == 0:
            self.sock.close()

    def fileno(self) -> int:
        return self.sock.fileno()


def _deadline_http(url: str, method: str, body: bytes | None, headers: dict[str, str],
                   expected_status: int, deadline: float, clock: Callable[[], float],
                   timeout: float) -> dict[str, Any]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise OSError("Conductor API URL is malformed")
    base_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    class DeadlineConnection(base_class):
        def connect(self):
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError("event re-check elapsed budget exhausted")
            self.timeout = min(timeout, remaining)
            super().connect()
            self.sock = _DeadlineSocket(self.sock, deadline, clock, timeout)
    connection = DeadlineConnection(parsed.hostname, parsed.port, timeout=min(timeout, max(deadline - clock(), 0)))
    response: http.client.HTTPResponse | None = None
    try:
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        connection.request(method, target, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != expected_status:
            raise _http_observation_failure(response.status, response.headers.get("Retry-After"))
        chunks: list[bytes] = []
        while True:
            if clock() >= deadline:
                raise TimeoutError("event re-check elapsed budget exhausted")
            part = response.read1(4096)
            if not part:
                break
            chunks.append(part)
        if clock() >= deadline:
            raise TimeoutError("event re-check elapsed budget exhausted")
        return json.loads(b"".join(chunks).decode())
    finally:
        if response is not None:
            response.close()
        connection.close()


class ConductorHttpAdapter:
    """Supported Conductor ``/v0`` monitor adapter.

    The public status endpoint deliberately exposes only status/liveness.  We
    derive the stricter admission facts from that status, the bounded official
    transcript envelope, and the already validated durable checkpoint.  Any
    missing transcript identity or ambiguous working state is a refusal.
    """
    def __init__(self, workspace_id: str, request: JsonRequest):
        self.workspace_id, self.request = _text(workspace_id, "workspace identity"), request
        self.deadline: float | None = None
        self.monotonic: Callable[[], float] = time.monotonic

    def set_event_deadline(self, deadline: float | None, monotonic: Callable[[], float]) -> None:
        self.deadline, self.monotonic = deadline, monotonic
        if hasattr(self.request, "set_event_deadline"):
            self.request.set_event_deadline(deadline, monotonic)

    def _request(self, method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        if self.deadline is not None and self.monotonic() >= self.deadline:
            raise TimeoutError("event re-check elapsed budget exhausted")
        return self.request(method, path, body)

    def _session(self, session_id: str) -> dict[str, Any]:
        session_id = _text(session_id, "session identity")
        value = self._request("GET", "/v0/sessions/" + session_id + "/status", None)
        allowed = {"workspaceId", "sessionId", "status", "updatedAt", "errorMessage", "lastError", "lastErrorAt"}
        if (not isinstance(value, dict) or not {"workspaceId", "sessionId", "status", "updatedAt"} <= set(value)
                or not set(value) <= allowed or not isinstance(value.get("sessionId"), str) or value["sessionId"] != session_id
                or not isinstance(value.get("workspaceId"), str) or value["workspaceId"] != self.workspace_id
                or not isinstance(value.get("status"), str) or value["status"] not in {"working", "idle", "error"}
                or not isinstance(value.get("updatedAt"), str) or not value["updatedAt"]):
            raise OSError("Conductor session identity or status could not be verified")
        return value

    def _transcript(self, session_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []; offset = 0; seen: set[str] = set(); previous_index = -1
        for _ in range(20):
            page = self._request("GET", f"/v0/sessions/{session_id}/messages?limit=100&offset={offset}", None)
            if not isinstance(page, dict) or set(page) != {"data", "offset", "hasMore"} or not isinstance(page["data"], list) or type(page["hasMore"]) is not bool or type(page["offset"]) not in {int, float}:
                raise OSError("Conductor transcript envelope was malformed")
            for item in page["data"]:
                if (not isinstance(item, dict) or set(item) != {"id", "sessionId", "sessionIndex", "type", "content", "receivedAt"}
                        or not isinstance(item["id"], str) or not item["id"] or item["id"] in seen
                        or not isinstance(item["sessionId"], str) or item["sessionId"] != session_id
                        or type(item["sessionIndex"]) is not int or item["sessionIndex"] < 0 or item["sessionIndex"] < previous_index
                        or not isinstance(item["type"], str) or item["type"] not in {"userMessage", "agent"}
                        or not isinstance(item["content"], dict)
                        or not isinstance(item["receivedAt"], str) or not item["receivedAt"]):
                    raise OSError("Conductor transcript item was malformed")
                seen.add(item["id"]); previous_index = item["sessionIndex"]; records.append(item)
            if not page["hasMore"]:
                return records
            if not page["data"]:
                raise OSError("Conductor transcript pagination made no progress")
            offset += len(page["data"])
        raise OSError("Conductor transcript exceeded bounded pagination")

    @staticmethod
    def _message(records: list[dict[str, Any]], observation: dict[str, str]) -> tuple[dict[str, Any], str] | None:
        matches = []
        for item in records:
            content = item["content"]
            if item["type"] != "userMessage" or not isinstance(content, dict) or content.get("id") != observation["message_id"]:
                continue
            if (not isinstance(content.get("state"), str) or content["state"] not in {"queued", "sent"}
                    or not isinstance(content.get("turnId"), str) or content["turnId"] != observation["terminal_turn_id"]):
                raise OSError("Conductor message identity or turn correlation was malformed")
            matches.append((item, content["turnId"]))
        if len(matches) > 1:
            raise OSError("Conductor transcript has conflicting message identities")
        return matches[0] if matches else None

    @staticmethod
    def _turn_events(records: list[dict[str, Any]], message_id: str, turn_id: str) -> set[str]:
        events: set[str] = set()
        for item in records:
            content = item["content"]
            raw = content.get("rawPayload") if isinstance(content, dict) else None
            event = raw.get("event") if isinstance(raw, dict) else None
            if item["type"] != "agent" or not isinstance(content, dict):
                continue
            correlated = "turnId" in content or "userMessageId" in content
            if not correlated:
                continue
            if content.get("turnId") != turn_id or content.get("userMessageId") != message_id:
                continue
            if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                raise OSError("Conductor correlated turn event was malformed")
            if event["type"] in {"turn.started", "turn.completed"}:
                events.add(event["type"])
        return events

    @classmethod
    def _unconsumed_prompt(cls, records: list[dict[str, Any]]) -> bool:
        """Validate every user prompt, not merely a known durable wake.

        A queued prompt is always unconsumed.  A sent prompt needs its exact
        correlated start and completion events; a missing or conflicting event
        is unsafe rather than evidence of idleness.  This bounded official
        transcript is the only source for this conclusion.
        """
        pending = False
        message_turns: dict[str, str] = {}
        turn_messages: dict[str, str] = {}
        for item in records:
            if item["type"] != "userMessage":
                continue
            content = item["content"]
            if (not isinstance(content, dict)
                    or not isinstance(content.get("id"), str) or not content["id"]
                    or not isinstance(content.get("state"), str) or content["state"] not in {"queued", "sent"}
                    or not isinstance(content.get("turnId"), str) or not content["turnId"]):
                raise OSError("Conductor user message content/state/turn identity was malformed")
            if content["id"] in message_turns or content["turnId"] in turn_messages:
                raise OSError("Conductor transcript has conflicting user message identities")
            message_turns[content["id"]] = content["turnId"]
            turn_messages[content["turnId"]] = content["id"]
            events = cls._turn_events(records, content["id"], content["turnId"])
            if content["state"] == "queued":
                if events:
                    raise OSError("Conductor queued prompt has conflicting turn events")
                pending = True
            elif "turn.started" not in events:
                raise OSError("Conductor sent prompt lacks a correlated started turn")
            elif "turn.completed" not in events:
                pending = True
        return pending

    def monitoring_observation(self, record: dict[str, Any]) -> dict[str, Any]:
        session = self._session(record["monitoring"]["coordinator_session_id"])
        records = self._transcript(session["sessionId"])
        transcript_pending = self._unconsumed_prompt(records)
        awaited = None
        if record["state"]["next_action"] == "await-worker":
            operation = next(item for item in record["usage"]["operations"]
                             if item["id"] == record["state"]["operation_id"])
            identity = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
            worker_session = self._session(operation["session_id"])
            worker_records = self._transcript(operation["session_id"])
            found = self._message(worker_records, identity)
            if worker_session["status"] == "error":
                state = "error"
            elif found is None:
                state = "unknown"
            elif found[0]["content"]["state"] == "queued":
                state = "queued"
            elif worker_session["status"] == "working":
                state = "active"
            elif "turn.completed" in self._turn_events(worker_records, identity["message_id"], identity["terminal_turn_id"]):
                state = "terminal"
            else:
                state = "unknown"
            awaited = {**identity, "state": state}
        # A durable non-wake operation is an active worker/effect until it has
        # a correlated terminal/accounted outcome.  We never scan other runs.
        active_workers = any(item.get("phase") not in {"wake", "coordinator"}
                             and item.get("id") != record["state"].get("operation_id")
                             and item.get("status") not in {"result", "reconciled", "accounted", "unfinished-cancelled"}
                             for item in record["usage"]["operations"])
        pending_effects = any(item.get("phase") == "wake" and item.get("status") != "accounted" for item in record["usage"]["operations"])
        pending_messages = transcript_pending
        for item in record["usage"]["operations"]:
            if item.get("phase") != "wake":
                continue
            observation = {name: item[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
            found = self._message(records, observation)
            if found is not None and (found[0]["content"].get("state") == "queued" or "turn.completed" not in self._turn_events(records, found[0]["content"]["id"], found[1])):
                pending_messages = True
        observation = {"current_turn": "interrupted" if session["status"] == "idle" else "unknown",
                "pending_messages": pending_messages, "pending_effects": pending_effects,
                "active_workers": active_workers, "working_ambiguous": session["status"] != "idle"}
        if awaited is not None:
            observation["awaited_worker"] = awaited
        return observation

    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]:
        session_id = _text(approval["coordinator"]["session_id"], "coordinator identity")
        self._session(session_id)
        return [{"session_id": session_id}]

    def send_wake(self, operation: dict[str, Any]) -> dict[str, Any]:
        observed = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        value = self._request("POST", "/v0/sessions/" + observed["session_id"] + "/messages", {"messageId": observed["message_id"], "message": "Run your approved python -m delivery_pilot.interim advance command once for durable wake " + observed["id"] + ", then report its outcome."})
        if (not isinstance(value, dict) or set(value) != {"messageId", "state", "deepLink"}
                or not isinstance(value.get("messageId"), str) or value["messageId"] != observed["message_id"]
                or not isinstance(value.get("state"), str) or value["state"] not in {"queued", "sent"}
                or not isinstance(value.get("deepLink"), str) or not value["deepLink"]):
            raise OSError("Conductor wake receipt was malformed")
        return {"observation": observed, "transport": "accepted", "worker_state": "queued", "elapsed_seconds": 0}

    def observe(self, operation: dict[str, Any]) -> dict[str, Any]:
        observed = {name: operation[name] for name in ("id", "session_id", "message_id", "terminal_turn_id")}
        session = self._session(observed["session_id"])
        records = self._transcript(observed["session_id"])
        self._unconsumed_prompt(records)
        found = self._message(records, observed)
        if found is None:
            state = "unknown"
        elif session["status"] == "error":
            state = "error"
        elif session["status"] == "working":
            state = "active"
        elif session["status"] == "idle" and "turn.completed" in self._turn_events(records, found[0]["content"]["id"], found[1]):
            state = "terminal"
        else:
            state = "unknown"
        return {"observation": observed, "transport": "accepted", "worker_state": state, "elapsed_seconds": 0}


def http_request(base_url: str, token: str, timeout: float = 15.0) -> JsonRequest:
    """Real HTTP boundary; caller gets token from env, never argv or logs."""
    base, token = _text(base_url, "API base URL").rstrip("/"), _text(token, "API token")
    # Cloud exposes a versioned URL; callers may supply either its origin or
    # the documented /v0 base without accidentally issuing /v0/v0 requests.
    if base.endswith("/v0"):
        base = base[:-3]
    deadline: float | None = None
    monotonic = time.monotonic
    def set_event_deadline(value: float | None, clock: Callable[[], float]) -> None:
        nonlocal deadline, monotonic
        deadline, monotonic = value, clock
    def request(method: str, path: str, body: dict[str, Any] | None) -> dict[str, Any]:
        expected_status = {"GET": 200, "POST": 201}.get(method)
        if expected_status is None:
            raise OSError("Conductor HTTP method is not supported by the monitor")
        remaining = timeout if deadline is None else min(timeout, deadline - monotonic())
        if remaining <= 0:
            raise TimeoutError("event re-check elapsed budget exhausted")
        raw = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "playbook-recovery/1"}
        call = Request(base + path, data=raw, method=method, headers=headers)
        try:
            if deadline is None:
                with urlopen(call, timeout=remaining) as response:
                    if response.status != expected_status:
                        raise OSError("Conductor HTTP response had an unexpected success status")
                    value = json.loads(response.read().decode())
            else:
                value = _deadline_http(base + path, method, raw, headers, expected_status,
                                       deadline, monotonic, timeout)
        except HTTPError as exc:
            raise _http_observation_failure(exc.code, exc.headers.get("Retry-After") if exc.headers else None) from exc
        except (URLError, TimeoutError, http.client.HTTPException,
                UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSError("Conductor HTTP request was unavailable or invalid") from exc
        if not isinstance(value, dict):
            raise OSError("Conductor HTTP response was not an object")
        return value
    request.set_event_deadline = set_event_deadline
    return request


def _http_observation_failure(status: int, retry_after: str | None = None) -> ObservationFailure:
    if status == 401:
        return ObservationFailure("credentials-revoked")
    if status == 403:
        return ObservationFailure("authority-denied")
    if status == 404:
        return ObservationFailure("ambiguous-missing-session")
    eligible_at = None
    if isinstance(retry_after, str) and len(retry_after) <= 128:
        if retry_after.isdecimal():
            try:
                eligible_at = datetime.now(timezone.utc) + timedelta(seconds=int(retry_after))
            except (ValueError, OverflowError):
                eligible_at = None
        else:
            try:
                eligible_at = parsedate_to_datetime(retry_after)
                if eligible_at.tzinfo is None:
                    eligible_at = None
            except (ValueError, TypeError, OverflowError):
                pass
    return ObservationFailure("transient-outage", eligible_at)


def repository_dispatch_emitter(repository: str, token: str, timeout: float = 15.0) -> Callable[[dict[str, str]], None]:
    """Return the optional post-checkpoint GitHub notification seam.

    It is intentionally not called by this inactive package.  A coordinator
    wires it only after a durable transition; failures are handled by the
    lifecycle helper and scheduled exact-ref discovery remains the recovery
    path.  The token is closure-only, never part of argv or diagnostics.
    """
    repository = _text(repository, "GitHub repository")
    token = _text(token, "GitHub token")
    if "/" not in repository or repository.startswith("/") or repository.endswith("/"):
        raise MonitoringPolicyError("GitHub repository is malformed")
    def emit(where: dict[str, str]) -> None:
        payload = json.dumps({"event_type": DISPATCH_TYPE, "client_payload": locator(where)}, separators=(",", ":")).encode()
        request = Request("https://api.github.com/repos/" + repository + "/dispatches", data=payload, method="POST",
                          headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                   "Content-Type": "application/json", "User-Agent": "playbook-recovery/1"})
        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status != 204:
                    raise OSError("GitHub repository_dispatch was not accepted")
        except (HTTPError, URLError, TimeoutError) as exc:
            raise OSError("GitHub repository_dispatch was unavailable") from exc
    return emit


def worker_done_locator(repository: Path, remote: str, run_id: str, control_ref: str,
                        operation_id: str) -> dict[str, str] | None:
    """Derive a worker's current hint from the registered durable operation.

    The brief carries only the immutable run/ref/operation identity.  In
    particular its pre-send checkpoint generation is never used: Build and
    Verify publish await-worker after the host accepts the initial message.
    """
    target = _worker_done_target(repository, remote, run_id, control_ref, operation_id)
    return None if target is None else target[0]


def _worker_done_target(repository: Path, remote: str, run_id: str, control_ref: str,
                        operation_id: str) -> tuple[dict[str, str], str | None] | None:
    if not _CONTROL_REF.fullmatch(control_ref):
        return None
    snapshot = InterimCheckpointStore(repository, remote, control_ref).reload_registered()
    record = snapshot.value
    monitoring = record.get("monitoring")
    if (record["approval"]["run_id"] != run_id or record["approval"]["checkpoint"]["ref"] != control_ref
            or not isinstance(monitoring, dict) or monitoring.get("state") != "active"
            or record["state"].get("next_action") != "await-worker"
            or record["state"].get("operation_id") != operation_id):
        return None
    matches = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
    if (len(matches) != 1 or matches[0]["phase"] not in {"build", "verify", "diagnosis", "repair", "repair-verify"}
            or not isinstance(monitoring.get("pending_wake"), dict)):
        return None
    repository_approval = record["approval"]["repository"]
    github_url = r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?"
    fetch = re.fullmatch(github_url, repository_approval["fetch_url"])
    push = re.fullmatch(github_url, repository_approval["push_url"])
    owner = fetch.group(1) if fetch and push and fetch.group(1) == push.group(1) else None
    return (locator({"run_id": run_id, "control_ref": control_ref,
                     "generation": monitoring["pending_wake"]["generation"]}),
            owner)


def emit_worker_done(repository: Path, remote: str, run_id: str, control_ref: str,
                     operation_id: str) -> None:
    """One silent, best-effort notification; the timer remains authoritative backup."""
    try:
        target = _worker_done_target(repository, remote, run_id, control_ref, operation_id)
        if target is not None and target[1] is not None:
            where, owner = target
            # Reuse an existing gh login; only the exact locator enters stdin.
            payload = json.dumps({"event_type": DISPATCH_TYPE, "client_payload": where}, separators=(",", ":"))
            subprocess.run(["gh", "api", "--method", "POST", "repos/" + owner + "/dispatches", "--input", "-"],
                           cwd=repository, input=payload, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=15, check=True)
    except Exception:
        # This last worker step cannot spoil a valid structured worker result.
        pass


class RegisteredRunner:
    """Discover registered refs and use the one shared monitor/reconciler."""
    def __init__(self, repository: Path, remote: str, adapter_factory: Callable[[str], MonitorAdapter],
                 monotonic: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.repository, self.remote, self.adapter_factory = repository, remote, adapter_factory
        self.monotonic, self.sleep = monotonic, sleep
        self.discovery_outcomes: list[dict[str, str]] = []

    @staticmethod
    def _refusal(run_id: str, control_ref: str, boundary: str, exc: Exception) -> dict[str, str]:
        # Only fixed boundary and failure codes enter Actions logs.
        # Provider text, subprocess stderr and credential-bearing URLs do not.
        failure_kind = ("git-subprocess" if isinstance(exc, subprocess.SubprocessError) else
                        "checkpoint" if isinstance(exc, InterimCheckpointError) else
                        "policy" if isinstance(exc, MonitoringPolicyError) else "io")
        return {"run_id": run_id, "control_ref": control_ref, "action": "refuse",
                "reason": "checkpoint-reload-refused", "failure_boundary": boundary,
                "failure_kind": failure_kind,
                "failure_detail": exc.code if isinstance(exc, InterimCheckpointError) else "none"}

    def one(self, untrusted: object, source: str, now: datetime | None = None) -> dict[str, str]:
        where = locator(untrusted)
        if not _CONTROL_REF.fullmatch(where["control_ref"]):
            raise MonitoringPolicyError("locator control ref is malformed")
        store = InterimCheckpointStore(self.repository, self.remote, where["control_ref"])
        try:
            snapshot = store.reload_registered()
        except (InterimCheckpointError, MonitoringPolicyError, OSError, subprocess.SubprocessError) as exc:
            return self._refusal("unavailable", "unavailable", "registered-reload", exc)
        record = snapshot.value
        run_id, control_ref = record["approval"]["run_id"], record["approval"]["checkpoint"]["ref"]
        try:
            adapter = self.adapter_factory(record["monitoring"]["coordinator_workspace_id"])
        except (InterimCheckpointError, MonitoringPolicyError, OSError, subprocess.SubprocessError) as exc:
            return self._refusal(run_id, control_ref, "adapter-initialization", exc)
        try:
            _, decision = reconcile(store, record, where, source, adapter, now,
                                    monotonic=self.monotonic, sleep=self.sleep)
        except (InterimCheckpointError, MonitoringPolicyError, OSError, subprocess.SubprocessError) as exc:
            return self._refusal(run_id, control_ref, "reconciliation", exc)
        return {"run_id": record["approval"]["run_id"], "action": decision["action"], "reason": decision.get("reason", "accepted")}

    def run(self, locators: list[dict[str, str]], source: str, now: datetime | None = None) -> list[dict[str, str]]:
        """Reconcile each bounded locator without letting one lost ref stop overlaps.

        Discovery namespace limits are enforced before this loop and deliberately
        escape it.  Per-locator validation or an exact-checkpoint reload/access
        failure is instead a typed refusal, allowing a later independent run to
        continue through the same bounded batch.
        """
        outcomes: list[dict[str, str]] = []
        for untrusted in locators:
            try:
                where = locator(untrusted)
                outcomes.append(self.one(where, source, now))
            except (InterimCheckpointError, MonitoringPolicyError, OSError, subprocess.SubprocessError) as exc:
                outcomes.append(self._refusal("unavailable", "unavailable", "locator", exc))
        return outcomes

    def discover(self) -> list[dict[str, str]]:
        """Discover only main-owned exact control refs, never sessions/workspaces.

        The ref prefix is the registry.  Each candidate is reloaded from its
        own ref and its generation is taken from the validated checkpoint, not
        from an operator-maintained list or from a GitHub event payload.
        """
        prefix = "refs/heads/delivery-control/"
        result = subprocess.run(["git", "ls-remote", "--heads", self.remote, prefix + "*"], cwd=self.repository,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, text=True)
        if result.returncode:
            raise InterimCheckpointError("registered control refs could not be listed")
        if len(result.stdout.encode()) > MAX_REGISTERED_OUTPUT_BYTES:
            raise InterimCheckpointError("registered control-ref namespace exceeded bounded output")
        lines = result.stdout.splitlines()
        if len(lines) > MAX_REGISTERED_REFS:
            raise InterimCheckpointError("registered control-ref namespace exceeded candidate limit")
        locators: list[dict[str, str]] = []
        seen_refs: set[str] = set()
        self.discovery_outcomes = []
        for line in lines:
            if not line or len(line) > MAX_REGISTERED_REF_LINE:
                self.discovery_outcomes.append({"control_ref": "unavailable", "action": "refuse", "reason": "malformed-ref-listing"})
                continue
            fields = line.split("\t")
            if (len(fields) != 2 or len(fields[0]) not in {40, 64}
                    or any(char not in "0123456789abcdef" for char in fields[0])
                    or not _CONTROL_REF.fullmatch(fields[1]) or fields[1] in seen_refs):
                self.discovery_outcomes.append({"control_ref": "unavailable",
                                                "action": "refuse", "reason": "malformed-or-duplicate-control-ref"})
                continue
            control_ref = fields[1]
            seen_refs.add(control_ref)
            try:
                store = InterimCheckpointStore(self.repository, self.remote, control_ref)
                snapshot = store.reload_registered(); record = snapshot.value
                monitoring = record.get("monitoring")
                if not isinstance(monitoring, dict) or monitoring.get("state") != "active" or not isinstance(monitoring.get("pending_wake"), dict):
                    self.discovery_outcomes.append({"control_ref": record["approval"]["checkpoint"]["ref"],
                                                    "action": "refuse", "reason": "monitoring-inactive-or-unenrolled"})
                    continue
                locators.append({"run_id": record["approval"]["run_id"], "control_ref": control_ref,
                                 "generation": monitoring["pending_wake"]["generation"]})
            except (InterimCheckpointError, OSError, subprocess.SubprocessError) as exc:
                # One corrupt/inaccessible checkpoint never turns a bounded
                # backup scan into a batch-wide failure or a session scan.  The
                # ref name came from the validated remote listing, not a payload.
                refusal = self._refusal("unavailable", control_ref, "discovery-reload", exc)
                del refusal["run_id"]
                self.discovery_outcomes.append(refusal)
        return locators


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        # argparse includes unknown argument values in its default error text.
        # A stale caller may pass the former raw-payload option, so never echo
        # that text into an Actions log or operator terminal.
        self.exit(2, "TASK-409 recovery input refused\n")


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(description="Run deterministic TASK-409 event/backup recovery")
    parser.add_argument("--repository", type=Path, default=Path(".")); parser.add_argument("--remote", default="origin")
    parser.add_argument("--api-base-url", default=os.environ.get("PLAYBOOK_RECOVERY_CONDUCTOR_API_URL", ""))
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_SafeArgumentParser)
    event = sub.add_parser("event")
    event.add_argument("--event-file", required=True, type=Path)
    sub.add_parser("backup")
    worker = sub.add_parser("worker-done")
    worker.add_argument("--run-id", required=True)
    worker.add_argument("--control-ref", required=True)
    worker.add_argument("--operation-id", required=True)
    args = parser.parse_args(argv)
    if args.command == "worker-done":
        emit_worker_done(args.repository, args.remote, args.run_id, args.control_ref, args.operation_id)
        return 0
    try:
        factory = lambda workspace: ConductorHttpAdapter(workspace, http_request(args.api_base_url, os.environ.get("PLAYBOOK_RECOVERY_CONDUCTOR_TOKEN", "")))
        runner = RegisteredRunner(args.repository, args.remote, factory)
        if args.command == "event":
            current = load_event_file(args.event_file, os.environ.get("GITHUB_EVENT_NAME"))
            result = runner.run([current], "event")
        else:
            discovered = runner.discover()
            result = runner.discovery_outcomes + runner.run(discovered, "backup")
    except (json.JSONDecodeError, MonitoringPolicyError, InterimCheckpointError, OSError, subprocess.SubprocessError) as exc:
        parser.error("refused recovery input or provider boundary: " + str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

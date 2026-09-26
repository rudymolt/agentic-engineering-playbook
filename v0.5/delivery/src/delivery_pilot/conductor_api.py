"""Minimal fail-closed adapter for the beta Conductor Cloud API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .canonical import digest
from .contracts import ContractError


Transport = Callable[[str, str, dict[str, str], dict[str, Any] | None], tuple[int, dict[str, Any]]]
MAX_RECONCILIATION_PAGES = 10


class ConductorApiError(ContractError):
    def __init__(self, method: str, path: str, status: int):
        super().__init__(f"Conductor API {method} {path} failed with HTTP {status}")
        self.status = status


def normalize_api_url(value: str) -> tuple[str, str]:
    """Return (origin, v0 base), accepting either documented environment form."""

    value = value.rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise ContractError("invalid CONDUCTOR_API_URL")
    if parsed.path in ("", "/"):
        origin = value
        return origin, origin + "/v0"
    if parsed.path == "/v0":
        return value[:-3], value
    raise ContractError("CONDUCTOR_API_URL must be an origin or end exactly in /v0")


def _urllib_transport(method: str, url: str, headers: dict[str, str], body: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
    raw = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(url, data=raw, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"error": "non-json API error"}
        return exc.code, payload


@dataclass
class ConductorApiClient:
    api_url: str
    credential: str
    session_id: str | None = None
    transport: Transport = _urllib_transport
    user_agent: str = "ai-engineering-playbook-k3/1"

    @classmethod
    def from_environment(cls, transport: Transport = _urllib_transport) -> "ConductorApiClient":
        credential = os.environ.get("CONDUCTOR_API_KEY") or os.environ.get("CONDUCTOR_API_TOKEN")
        if not credential:
            raise ContractError("CONDUCTOR_API_KEY or CONDUCTOR_API_TOKEN is required")
        return cls(os.environ.get("CONDUCTOR_API_URL", ""), credential, os.environ.get("CONDUCTOR_SESSION_ID"), transport)

    def __post_init__(self) -> None:
        self.origin, self.v0 = normalize_api_url(self.api_url)
        if not self.credential:
            raise ContractError("Conductor API credential is empty")

    @property
    def headers(self) -> dict[str, str]:
        result = {"Authorization": f"Bearer {self.credential}", "Content-Type": "application/json", "User-Agent": self.user_agent}
        if self.session_id:
            result["X-Conductor-Session-Id"] = self.session_id
        return result

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None, *, versioned: bool = True) -> dict[str, Any]:
        base = self.v0 if versioned else self.origin
        status, payload = self.transport(method, base + path, self.headers, body)
        if status < 200 or status >= 300:
            raise ConductorApiError(method, path, status)
        if not isinstance(payload, dict):
            raise ContractError("Conductor API returned a non-object")
        return payload

    def capability_preflight(self) -> dict[str, Any]:
        identity = self._call("GET", "/me", versioned=False)
        spec_status, spec = self.transport("GET", self.v0 + "/openapi.json", self.headers, None)
        if spec_status != 200 or not isinstance(spec, dict) or not spec.get("openapi"):
            raise ContractError("Conductor OpenAPI capability preflight failed")
        auth = identity.get("authMethod")
        if auth not in {"api-key", "access-jwt", "legacy-api-token"}:
            raise ContractError("unsupported Conductor authentication method")
        scope = "workspace" if identity.get("workspaceId") else "organization"
        return {
            "outcome": "ready", "auth_method": auth, "credential_scope": scope,
            "workspace_id": identity.get("workspaceId"), "openapi_version": spec.get("openapi"),
            "api_version": spec.get("info", {}).get("version"), "openapi_digest": digest(spec),
        }

    def create_workspace(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._call("POST", "/workspaces", body)

    def observe_workspace(self, workspace_id: str) -> dict[str, Any]:
        return self._call("GET", f"/workspaces/{workspace_id}/status")

    def launch_checker(self, workspace_id: str, prompt: str, agent: str, model: str, effort: str, message_id: str) -> dict[str, Any]:
        body = {"workspaceId": workspace_id, "agent": agent, "model": model, "effort": effort, "message": prompt, "messageId": message_id}
        try:
            result = self._call("POST", "/sessions", body)
            self._validate_launch_receipt(result, workspace_id, agent, model, effort)
            initial = result.get("initialMessage")
            return {
                **result,
                "logicalMessageId": message_id,
                "initialMessage": {**initial, "messageId": message_id} if isinstance(initial, dict) else {"messageId": message_id},
            }
        except ConductorApiError as exc:
            if exc.status < 500:
                raise
            return self._reconcile_launch(workspace_id, prompt, agent, model, effort, message_id)
        except OSError:
            # The stable message ID is the idempotency/reconciliation key. Do
            # not blindly repeat a potentially accepted POST.
            return self._reconcile_launch(workspace_id, prompt, agent, model, effort, message_id)

    @staticmethod
    def _validate_launch_receipt(
        result: dict[str, Any], workspace_id: str, agent: str, model: str, effort: str, *, require_route: bool = False,
    ) -> None:
        if not _nonempty_text(result.get("id")):
            raise ContractError("Conductor launched session identity is malformed")
        for field, expected in (("workspaceId", workspace_id), ("agent", agent), ("model", model), ("resolvedModel", model), ("effort", effort)):
            if field not in result:
                continue
            value = result[field]
            if not _nonempty_text(value):
                raise ContractError(f"Conductor launched session {field} identity is malformed")
            if value != expected:
                if require_route:
                    if field == "workspaceId":
                        raise ContractError("Conductor reconciled session workspace mismatch")
                    raise ContractError("Conductor reconciled session route mismatch")
                raise ContractError(f"Conductor launched session {field} identity mismatch")
        if require_route and (("model" not in result and "resolvedModel" not in result) or "effort" not in result):
            raise ContractError("Conductor reconciled session route mismatch")

    @staticmethod
    def _validate_reconciled_session_record(result: dict[str, Any], workspace_id: str) -> None:
        """Reject malformed or cross-workspace listed records before message reads."""

        if not _nonempty_text(result.get("id")):
            raise ContractError("Conductor reconciled session identity is malformed")
        for field in ("workspaceId", "agent", "model", "resolvedModel", "effort"):
            if field in result and not _nonempty_text(result[field]):
                raise ContractError(f"Conductor reconciled session {field} identity is malformed")
        if "workspaceId" in result and result["workspaceId"] != workspace_id:
            raise ContractError("Conductor reconciled session workspace mismatch")

    def send_message(self, session_id: str, message: str, message_id: str) -> dict[str, Any]:
        try:
            return {**self._call("POST", f"/sessions/{session_id}/messages", {"message": message, "messageId": message_id}), "logicalMessageId": message_id}
        except ConductorApiError as exc:
            if exc.status < 500:
                raise
            return self._reconcile_message(session_id, message, message_id)
        except OSError:
            return self._reconcile_message(session_id, message, message_id)

    def observe_message(self, transcript_id: str) -> dict[str, Any]:
        """Observe a known transcript-record ID; logical IDs are not lookup keys."""

        return self._call("GET", f"/messages/{transcript_id}")

    def _paginated_data(
        self, path: Callable[[str | None], str], label: str, after: str | None = None,
        read_budget: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        cursor = after
        cursors = {after} if after is not None else set()
        for _ in range(MAX_RECONCILIATION_PAGES):
            if read_budget is not None:
                if read_budget[0] <= 0:
                    raise ContractError(f"Conductor {label} pagination exhausted its combined read bound")
                read_budget[0] -= 1
            page = self._call("GET", path(cursor))
            data = page.get("data")
            has_more = page.get("hasMore")
            if not isinstance(data, list) or not isinstance(has_more, bool) or not all(isinstance(item, dict) for item in data):
                raise ContractError(f"Conductor {label} pagination is malformed")
            records.extend(data)
            if not has_more:
                return records
            if not data or not isinstance(data[-1].get("id"), str) or not data[-1]["id"]:
                raise ContractError(f"Conductor {label} pagination made no progress")
            cursor = data[-1]["id"]
            if cursor in cursors:
                raise ContractError(f"Conductor {label} pagination cursor cycle")
            cursors.add(cursor)
        raise ContractError(f"Conductor {label} pagination exhausted its bound")

    @staticmethod
    def _message_receipt(record: dict[str, Any], session_id: str, logical_message_id: str) -> dict[str, Any]:
        transcript_id = record.get("id")
        content = record.get("content")
        if not isinstance(transcript_id, str) or not transcript_id or not isinstance(content, dict):
            raise ContractError("Conductor transcript record is malformed")
        return {
            "id": transcript_id,
            "transcriptId": transcript_id,
            "logicalMessageId": logical_message_id,
            "sessionId": session_id,
            "state": content.get("state"),
            "reconciled": True,
        }

    def _find_reconciled_message(
        self, session_id: str, message: str, logical_message_id: str, read_budget: list[int] | None = None,
    ) -> dict[str, Any] | None:
        """Find one matching user transcript record only in the target session."""

        observed = self.observe_session(session_id, read_budget=read_budget, include_status=False)
        matches: list[dict[str, Any]] = []
        for record in observed["messages"]["data"]:
            if record.get("type") != "userMessage":
                continue
            content = record.get("content")
            if not isinstance(content, dict) or content.get("id") != logical_message_id:
                continue
            if record.get("sessionId") != session_id:
                raise ContractError("Conductor transcript message destination mismatch")
            if content.get("message") != message:
                raise ContractError("Conductor transcript message payload mismatch")
            matches.append(record)
        if len(matches) > 1:
            raise ContractError("Conductor transcript message reconciliation is conflicting")
        if not matches:
            return None
        return self._message_receipt(matches[0], session_id, logical_message_id)

    def _reconcile_message(self, session_id: str, message: str, logical_message_id: str) -> dict[str, Any]:
        """Find one matching user transcript record only in the target session."""

        receipt = self._find_reconciled_message(session_id, message, logical_message_id)
        if receipt is None:
            raise ContractError("Conductor transcript message reconciliation is ambiguous")
        return receipt

    def _reconcile_launch(self, workspace_id: str, prompt: str, agent: str, model: str, effort: str, logical_message_id: str) -> dict[str, Any]:
        """Recover a session create only with exact workspace, route, and prompt evidence."""

        def path(offset: str | None) -> str:
            return f"/workspaces/{workspace_id}/sessions?limit=100&offset={offset or '0'}&includeArchived=false"

        read_budget = [MAX_RECONCILIATION_PAGES]
        sessions: list[dict[str, Any]] = []
        offset = 0
        for _ in range(MAX_RECONCILIATION_PAGES):
            if read_budget[0] <= 0:
                raise ContractError("Conductor workspace sessions pagination exhausted its combined read bound")
            read_budget[0] -= 1
            page = self._call("GET", path(str(offset)))
            data, has_more = page.get("data"), page.get("hasMore")
            if not isinstance(data, list) or not isinstance(has_more, bool) or not all(isinstance(item, dict) for item in data):
                raise ContractError("Conductor workspace sessions pagination is malformed")
            sessions.extend(data)
            if not has_more:
                break
            if not data:
                raise ContractError("Conductor workspace sessions pagination made no progress")
            offset += len(data)
        else:
            raise ContractError("Conductor workspace sessions pagination exhausted its bound")

        candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for session in sessions:
            self._validate_reconciled_session_record(session, workspace_id)
            receipt = self._find_reconciled_message(session["id"], prompt, logical_message_id, read_budget)
            if receipt is None:
                continue
            self._validate_launch_receipt(session, workspace_id, agent, model, effort, require_route=True)
            candidates.append((session, receipt))
        if len(candidates) != 1:
            if len(candidates) > 1:
                raise ContractError("Conductor reconciled session is conflicting")
            raise ContractError("Conductor reconciled session is ambiguous")
        session, receipt = candidates[0]
        return {
            "id": session["id"],
            "logicalMessageId": logical_message_id,
            "initialMessage": {
                "messageId": logical_message_id,
                "transcriptId": receipt["transcriptId"],
                "state": receipt["state"],
            },
            "reconciled": True,
        }

    def observe_session(
        self, session_id: str, after_message_id: str | None = None, *, read_budget: list[int] | None = None,
        include_status: bool = True,
    ) -> dict[str, Any]:
        def path(cursor: str | None) -> str:
            suffix = "?limit=100" + ("" if cursor is None else "&after=" + urllib.parse.quote(cursor, safe=""))
            return f"/sessions/{session_id}/messages{suffix}"

        messages = {"data": self._paginated_data(path, "messages", after_message_id, read_budget), "hasMore": False, "offset": 0}
        status: dict[str, Any] = {}
        if include_status:
            status = self._call("GET", f"/sessions/{session_id}/status")
            if status.get("sessionId") not in (None, session_id):
                raise ContractError("Conductor session status destination mismatch")
        return {"status": status, "messages": messages}

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        result = self._call("POST", f"/sessions/{session_id}/cancel")
        if result.get("status") == "error":
            raise ContractError("Conductor cancellation entered adapter error state")
        return {**result, "cancellation_outcome": "complete" if result.get("status") == "idle" else "pending"}

    def sleep_workspace(self, workspace_id: str) -> dict[str, Any]:
        result = self._call("POST", f"/workspaces/{workspace_id}/sleep")
        if result.get("status") == "archived":
            raise ContractError("workspace became archived; parking did not succeed")
        return result

    def request_archive(self, workspace_id: str) -> dict[str, Any]:
        return self._call("POST", f"/workspaces/{workspace_id}/archive")


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _raw_payload(message: dict[str, Any]) -> dict[str, Any] | None:
    content = message.get("content")
    if not isinstance(content, dict):
        return None
    payload = content.get("rawPayload")
    return payload if isinstance(payload, dict) else None


def _event_value(event: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in event:
            return event[name]
    return None


def _identity_value(record: dict[str, Any], *names: str) -> str | None:
    """Return one explicit identity, refusing malformed or conflicting aliases."""

    supplied = [record[name] for name in names if name in record]
    if not supplied:
        return None
    if not all(_nonempty_text(value) for value in supplied):
        raise ContractError("Conductor completion identity is malformed")
    if len(set(supplied)) != 1:
        raise ContractError("Conductor completion identity aliases conflict")
    return supplied[0]


def _nested_identity(label: str, *values: str | None) -> str | None:
    supplied = [value for value in values if value is not None]
    if len(set(supplied)) > 1:
        raise ContractError(f"Conductor raw event {label} identities conflict")
    return supplied[0] if supplied else None


def _raw_event_identities(
    content: dict[str, Any], payload: dict[str, Any], event: dict[str, Any], item: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    """Validate identity aliases at every supported raw-event nesting boundary."""

    content_thread = _identity_value(content, "threadId", "thread_id")
    content_turn = _identity_value(content, "turnId", "turn_id")
    wrapper_thread = _identity_value(payload, "threadId", "thread_id")
    wrapper_turn = _identity_value(payload, "turnId", "turn_id")
    event_thread = _identity_value(event, "threadId", "thread_id")
    event_turn = _identity_value(event, "turnId", "turn_id")
    item_thread = _identity_value(item, "threadId", "thread_id") if item is not None else None
    item_turn = _identity_value(item, "turnId", "turn_id") if item is not None else None
    return (
        _nested_identity("thread", content_thread, wrapper_thread, event_thread, item_thread),
        _nested_identity("turn", content_turn, wrapper_turn, event_turn, item_turn),
    )


def _validate_completion_messages(messages: list[dict[str, Any]]) -> None:
    """Reject malformed supported records before incomplete evidence becomes pending."""

    for message in messages:
        kind = message["type"]
        content = message.get("content")
        if kind in {"user", "userMessage"}:
            if not isinstance(content, (str, dict)):
                raise ContractError("Conductor user message content is malformed")
            if isinstance(content, dict):
                if "id" in content and not _nonempty_text(content["id"]):
                    raise ContractError("Conductor user message identity is malformed")
                _identity_value(content, "threadId", "thread_id")
                _identity_value(content, "turnId", "turn_id")
            continue
        if kind == "assistant":
            if not isinstance(content, str):
                raise ContractError("Conductor normalized assistant content is malformed")
            continue
        if kind != "agent":
            continue
        if not isinstance(content, dict):
            raise ContractError("Conductor agent message content is malformed")
        _identity_value(content, "threadId", "thread_id")
        _identity_value(content, "turnId", "turn_id")
        if "rawPayload" not in content:
            continue
        payload = content["rawPayload"]
        if not isinstance(payload, dict):
            raise ContractError("Conductor raw payload is malformed")
        if "event" not in payload:
            continue
        event = payload["event"]
        if not isinstance(event, dict):
            raise ContractError("Conductor raw event is malformed")
        if "type" in event and not _nonempty_text(event["type"]):
            raise ContractError("Conductor raw event kind is malformed")
        item = event.get("item")
        if "item" in event and not isinstance(item, dict):
            raise ContractError("Conductor raw event item is malformed")
        if isinstance(item, dict) and not _nonempty_text(item.get("type")):
            raise ContractError("Conductor raw event item kind is malformed")
        _raw_event_identities(content, payload, event, item if isinstance(item, dict) else None)


def _raw_current_turn_complete(messages: list[dict[str, Any]]) -> bool:
    """Accept only a current, correlated raw reply followed by turn completion.

    This is intentionally narrower than the normalized assistant reply compatibility
    below. Raw agent events also carry tool starts, partial output, and cancellation
    shapes, none of which prove a completed reply.
    """

    current_index = -1
    current_turn: str | None = None
    current_thread: str | None = None
    for index, message in enumerate(messages):
        if message.get("type") not in {"user", "userMessage"}:
            continue
        content = message.get("content")
        if isinstance(content, dict) and isinstance(content.get("id"), str) and content["id"]:
            current_index = index
            current_turn = _identity_value(content, "turnId", "turn_id") or content["id"]
            current_thread = _identity_value(content, "threadId", "thread_id")
    if current_turn is None:
        return False

    state = "awaiting-start"
    thread_id: str | None = None
    final_item_id: str | None = None
    for message in messages[current_index + 1:]:
        if message.get("type") in {"user", "userMessage"}:
            # A later prompt is a new boundary even when its retained content is
            # normalized text rather than the object form used for correlation.
            return False
        content = message.get("content")
        payload = _raw_payload(message)
        event = payload.get("event") if isinstance(payload, dict) else None
        if not isinstance(event, dict):
            return False
        event_type = _event_value(event, "type")
        if not isinstance(event_type, str):
            return False
        item = event.get("item")
        observed_thread, turn_id = _raw_event_identities(
            content if isinstance(content, dict) else {}, payload, event, item if isinstance(item, dict) else None,
        )
        explicit_turn = _identity_value(content, "turnId", "turn_id") if isinstance(content, dict) else None
        if explicit_turn is not None and explicit_turn != current_turn:
            raise ContractError("Conductor raw message turn conflicts with the current user message")
        if current_thread is not None and observed_thread != current_thread:
            raise ContractError("Conductor raw event thread conflicts with the current user message")
        if turn_id is not None and turn_id != current_turn:
            return False
        if state == "awaiting-start":
            if not isinstance(observed_thread, str) or not observed_thread:
                return False
            if event_type == "thread.started":
                thread_id, state = observed_thread, "awaiting-turn-start"
            elif event_type == "turn.started":
                thread_id, state = observed_thread, "awaiting-final-message"
            else:
                return False
        elif state == "awaiting-turn-start":
            if event_type != "turn.started" or observed_thread != thread_id:
                return False
            state = "awaiting-final-message"
        elif state == "awaiting-final-message":
            if observed_thread != thread_id or event_type == "turn.started" or event_type == "turn.completed":
                return False
            terminal_part = event_type.rsplit(".", 1)[-1]
            if event_type == "error" or terminal_part in {"aborted", "canceled", "cancelled", "error", "failed"}:
                return False
            if isinstance(item, dict) and not isinstance(item.get("type"), str):
                raise ContractError("Conductor raw event item kind is malformed")
            is_final_message = (
                isinstance(item, dict)
                and item.get("type") in {"agentMessage", "assistantMessage"}
                and item.get("phase") == "final_answer"
            )
            if event_type == "item.started" and is_final_message:
                item_id = item.get("id")
                if item_id is not None and (not isinstance(item_id, str) or not item_id):
                    return False
                final_item_id = item_id
            elif event_type == "item.completed" and is_final_message and _nonempty_text(_event_value(item, "text", "message", "content")):
                item_id = item.get("id")
                if final_item_id is not None and item_id != final_item_id:
                    return False
                state = "awaiting-completed-turn"
        elif state == "awaiting-completed-turn":
            if event_type != "turn.completed" or observed_thread != thread_id:
                return False
            state = "complete"
        else:
            # No raw event may follow the completed current turn.
            return False
    return state == "complete"


def session_completion(status_history: list[str], messages: list[dict[str, Any]]) -> str:
    """Classify transport completion only; it never verifies the requested task."""

    if (
        not isinstance(status_history, list)
        or not all(isinstance(status, str) and status for status in status_history)
    ):
        raise ContractError("Conductor session status history is malformed")
    if (
        not isinstance(messages, list)
        or not all(isinstance(message, dict) and _nonempty_text(message.get("type")) for message in messages)
    ):
        raise ContractError("Conductor session messages are malformed")
    _validate_completion_messages(messages)
    if "error" in status_history:
        raise ContractError("Conductor session entered adapter error state")
    if not status_history or status_history[-1] != "idle" or "working" not in status_history:
        return "pending"

    # Compatibility for the established normalized terminal-reply interface.
    # Raw `agent` dictionaries deliberately do not use this path.
    normalized_terminal = bool(
        messages
        and messages[-1].get("type") == "assistant"
        and _nonempty_text(messages[-1].get("content"))
    )
    if normalized_terminal or _raw_current_turn_complete(messages):
        return "complete"
    return "pending"


def validate_runtime_review(
    workspace: dict[str, Any], session: dict[str, Any], *, workspace_id: str,
    session_id: str, agent: str, model: str, effort: str,
) -> dict[str, Any]:
    if workspace.get("workspaceId") != workspace_id or workspace.get("status") != "ready":
        raise ContractError("Cloud workspace identity or readiness mismatch")
    if session.get("id") != session_id:
        raise ContractError("Cloud session identity mismatch")
    if session.get("agent") not in (None, agent):
        raise ContractError("Cloud session agent mismatch")
    if session.get("model") != model or session.get("effort") != effort:
        raise ContractError("Cloud session model/effort mismatch")
    return {"outcome": "pass", "workspace_id": workspace_id, "session_id": session_id, "agent": agent, "model": model, "effort": effort}

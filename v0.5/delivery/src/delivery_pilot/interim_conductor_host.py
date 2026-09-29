"""Maintained Conductor CLI adapter for separately-authorized S7 fixtures.

This module deliberately has no executable entry point and creates no Routine,
workspace, session, message, PR, or checkpoint by itself.  A fixture driver
must first persist an operation intent through the interim coordinators, then
may pass that exact intent to this adapter.  The adapter accepts only the JSON
envelopes observed from Conductor CLI 0.1.0 and returns the narrow receipts the
interim recovery policy understands.
"""
from __future__ import annotations

import json
import hashlib
import shlex
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from uuid import UUID

from .interim_coordinator import InterimDispatchError
from .canonical import digest
from .interim_routes import configured_route
from .interim_disposition import ObservationFailure

MAX_TRANSCRIPT_PAGES = 20
PAGE_SIZE = 100
WATCHDOG_TITLE_PREFIX = "UNATTENDED_INTERIM_V1 "
Command = Callable[[list[str]], dict[str, Any]]
ResultParser = Callable[[dict[str, Any], list[dict[str, Any]], str], Optional[dict[str, Any]]]


class EscalationRouteError(InterimDispatchError):
    """Authoritative host readback definitively refuses this fallback route."""
    category = "route-mismatch"


def _uuid(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise InterimDispatchError(f"Conductor {label} must be a UUID")
    try:
        UUID(value)
    except ValueError as exc:
        raise InterimDispatchError(f"Conductor {label} must be a UUID") from exc
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise InterimDispatchError(f"Conductor {label} is malformed")
    return value


def _operation_observation(operation: dict[str, Any]) -> dict[str, str]:
    return {name: _text(operation.get(name), name) for name in ("id", "session_id", "message_id", "terminal_turn_id")}


def _candidate_checkout(record: dict[str, Any], repository: Path) -> Path:
    """Resolve both approved relative workspaces from their shared parent."""
    coordinator = Path(record["approval"]["workspaces"]["coordinator"])
    repository = repository.resolve()
    if tuple(repository.parts[-len(coordinator.parts):]) != coordinator.parts:
        raise InterimDispatchError("repository is not the approved coordinator checkout")
    root = repository.parents[len(coordinator.parts) - 1]
    approved_candidate = root / record["approval"]["workspaces"]["candidate"]
    candidate = approved_candidate.resolve()
    # The approval binds a location beneath this shared root, not a symbolic
    # name that may redirect to another checkout after approval.
    if (candidate != approved_candidate or not candidate.is_relative_to(root)
            or candidate == repository or not candidate.is_dir() or not (candidate / ".git").exists()):
        raise InterimDispatchError("approved candidate Git checkout is unavailable")
    approved = record["approval"]["repository"]
    for flag, expected in (((), approved["fetch_url"]), (("--push",), approved["push_url"])):
        result = subprocess.run(["git", "remote", "get-url", *flag, "--all", approved["remote"]], cwd=candidate,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if result.returncode or result.stdout.decode().splitlines() != [expected]:
            raise InterimDispatchError("candidate checkout repository differs from approval")
    return candidate


def _candidate_work(record: dict[str, Any], checkout: Path) -> dict[str, Any]:
    """Fingerprint known scoped edits without moving or serializing their content."""
    status = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                            cwd=checkout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    diff = subprocess.run(["git", "diff", "--binary", "HEAD", "--"], cwd=checkout,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if status.returncode or diff.returncode or head.returncode:
        raise InterimDispatchError("failed worker candidate work readback unavailable")
    head_sha = head.stdout.decode().strip()
    if len(head_sha) != 40 or any(char not in "0123456789abcdef" for char in head_sha):
        raise InterimDispatchError("failed worker candidate head is malformed")
    approved = record["approval"].get("implementation_paths")
    if not isinstance(approved, list) or not approved:
        raise InterimDispatchError("failed worker implementation scope is unavailable")
    names: list[str] = []
    material = hashlib.sha256(status.stdout + b"\0" + diff.stdout)
    for entry in status.stdout.split(b"\0"):
        if not entry:
            continue
        if len(entry) < 4 or entry[2:3] != b" " or any(letter in entry[:2] for letter in (ord("R"), ord("C"))):
            raise InterimDispatchError("failed worker candidate status is ambiguous")
        try:
            name = entry[3:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InterimDispatchError("failed worker candidate path is not portable") from exc
        path = Path(name)
        if (path.is_absolute() or ".." in path.parts or ".git" in path.parts
                or not any(name == scope or name.startswith(scope.rstrip("/") + "/") for scope in approved)):
            raise InterimDispatchError("failed worker candidate work is outside approved scope")
        target = checkout / path
        if target.is_symlink() or target.exists() and not target.is_file():
            raise InterimDispatchError("failed worker candidate work has unsafe file type")
        material.update(name.encode() + b"\0")
        if target.exists():
            material.update(target.read_bytes())
        else:
            material.update(b"<deleted>")
        names.append(name)
    if len(names) != len(set(names)):
        raise InterimDispatchError("failed worker candidate work path is duplicated")
    return {"paths": sorted(names), "digest": "sha256:" + material.hexdigest(), "head": head_sha}


def _run_cli(arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(["conductor", "--json", *arguments], text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise InterimDispatchError("Conductor CLI host command was unavailable or rejected")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InterimDispatchError("Conductor CLI returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise InterimDispatchError("Conductor CLI returned a non-object envelope")
    return value


def _terminal_result(operation: dict[str, Any], records: list[dict[str, Any]], turn_id: str) -> dict[str, Any] | None:
    """Read exactly one structured worker-result from the terminal host event.

    The worker prompt requires this object to be the existing interim result
    contract, including candidate/runtime/evidence/handoff when applicable.
    The adapter never manufactures those task-success facts from an idle turn.
    """
    terminal_seen = False
    matches: list[dict[str, Any]] = []
    for item in records:
        content = item.get("content")
        raw = content.get("rawPayload") if isinstance(content, dict) else None
        event = raw.get("event") if isinstance(raw, dict) else None
        if item.get("type") != "agent" or not isinstance(content, dict) or not isinstance(event, dict):
            continue
        if content.get("turnId") != turn_id or content.get("userMessageId") != turn_id:
            continue
        if event.get("type") == "turn.completed":
            terminal_seen = True
            continue
        item_result = event.get("item")
        if event.get("type") == "item.completed" and isinstance(item_result, dict) and item_result.get("type") == "agentMessage" and item_result.get("phase") == "final_answer":
            text = item_result.get("text")
            if not isinstance(text, str):
                raise InterimDispatchError("Conductor final-answer result contract is malformed")
            try:
                result = json.loads(text)
            except json.JSONDecodeError as exc:
                raise InterimDispatchError("Conductor final-answer result is not JSON") from exc
            if not isinstance(result, dict):
                raise InterimDispatchError("Conductor final-answer result contract is malformed")
            matches.append(result)
    if not terminal_seen:
        return None
    if len(matches) > 1:
        raise InterimDispatchError("Conductor terminal result contract is conflicting")
    return matches[0] if matches else None


@dataclass
class ConductorHostAdapter:
    """Translate real Conductor session/message facts into interim receipts.

    ``command`` is injectable solely for deterministic contract tests.  It
    receives arguments following ``conductor --json`` and must return decoded
    JSON; production uses the CLI runner above.
    """

    workspace_id: str
    agent: str = ""
    routes: dict[str, dict[str, str]] = field(default_factory=dict)
    command: Command = _run_cli
    result_parser: ResultParser | None = None
    operations: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancellations: dict[str, dict[str, Any]] = field(default_factory=dict)
    worker_hints: dict[str, tuple[str, str, Path, str, str, Path, tuple[str, ...]]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _uuid(self.workspace_id, "workspace identity")
        if self.agent and not isinstance(self.agent, str):
            raise InterimDispatchError("Conductor agent identity is malformed")
        if self.result_parser is None:
            self.result_parser = _terminal_result

    def _call(self, *arguments: str) -> dict[str, Any]:
        value = self.command(list(arguments))
        if not isinstance(value, dict):
            raise InterimDispatchError("Conductor CLI returned a non-object envelope")
        return value

    def bind_worker_hint(self, record: dict[str, Any], operation_id: str, repository: Path) -> None:
        """Bind only an enrolled, durable worker operation before host dispatch."""
        from .interim import validate_record
        record = validate_record(record)
        if record.get("monitoring", {}).get("state") != "active":
            raise InterimDispatchError("worker hint requires active enrollment")
        matches = [item for item in record["usage"]["operations"] if item["id"] == operation_id]
        if len(matches) != 1 or matches[0]["phase"] not in {"build", "verify", "diagnosis", "repair", "repair-verify"}:
            raise InterimDispatchError("worker hint requires one durable worker operation")
        if not isinstance(repository, Path):
            raise InterimDispatchError("worker hint requires the coordinator's repository path")
        candidate = _candidate_checkout(record, repository)
        self.worker_hints[operation_id] = (record["approval"]["run_id"], record["approval"]["checkpoint"]["ref"],
                                           repository.resolve(), digest(matches[0]),
                                           record["approval"]["repository"]["remote"],
                                           candidate,
                                           tuple(record["approval"]["implementation_paths"]))

    @staticmethod
    def _message_created(operation: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        observation = _operation_observation(operation)
        message_id = _uuid(result.get("messageId"), "message-create messageId")
        if message_id != observation["message_id"]:
            raise InterimDispatchError("Conductor message-create identity differs from durable intent")
        state = result.get("state")
        if state not in {"queued", "sent"} or not isinstance(result.get("deepLink"), str):
            raise InterimDispatchError("Conductor message-create envelope is malformed")
        # ``sent`` only means host transport acceptance; it is not a completed
        # worker turn.  Both accepted states remain queued until a later read.
        return {"observation": observation, "transport": "accepted", "worker_state": "queued",
                "host_message_id": message_id, "message_state": state, "elapsed_seconds": 0}

    def send_wake(self, operation: dict[str, Any]) -> dict[str, Any]:
        observation = _operation_observation(operation)
        self.operations[observation["id"]] = dict(operation)
        _uuid(observation["session_id"], "wake session identity")
        _uuid(observation["message_id"], "wake message identity")
        result = self._call("message", "create", "--session", observation["session_id"],
                            "--message-id", observation["message_id"],
                            "--message", "Run your approved python -m delivery_pilot.interim advance command once for durable wake " + observation["id"] + ", then report its outcome.")
        return self._message_created(operation, result)

    def send(self, operation: dict[str, Any]) -> dict[str, Any]:
        """Create a worker session with the UUIDs already persisted in intent."""
        observation = _operation_observation(operation)
        self.operations[observation["id"]] = dict(operation)
        _uuid(observation["session_id"], "worker session identity")
        _uuid(observation["message_id"], "worker message identity")
        phase = operation.get("phase")
        try:
            route = configured_route(self.routes, operation)
        except (KeyError, TypeError, ValueError):
            route = None
        if not self.agent or not isinstance(route, dict) or not all(isinstance(route.get(key), str) and route[key] for key in ("model", "effort")):
            raise InterimDispatchError("Conductor session-create lacks an approved agent/model/effort route")
        if "route" in operation and operation["route"] != route:
            raise InterimDispatchError("Conductor configured route differs from durable approval")
        task = operation.get("task")
        if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not isinstance(task.get("criteria"), list):
            raise InterimDispatchError("Conductor session-create lacks a bounded durable task")
        try:
            task_json = json.dumps(task, sort_keys=True, separators=(",", ":"))
            operation_json = json.dumps(operation, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise InterimDispatchError("Conductor session-create task is not portable JSON") from exc
        brief = (f"Execute only durable interim {phase} operation {observation['id']}. "
                 f"The complete immutable bounded task is {task_json}. "
                 f"The persisted operation, identities, candidate and phase context are {operation_json}. "
                 "Return exactly one JSON interim worker-result contract correlated to this operation; "
                 "transport acceptance, an idle session, and a terminal turn alone are not success. "
                 "Use the maintained delivery_pilot validators as the exact output schema: "
                 "interim_repair._diagnosis for diagnosis; interim_semantics.validate_worker_result "
                 "for accepting Build/Verify/repair/stack-Verify results; "
                 "interim_semantics.validate_ordinary_verify_failure for a complete ordinary Verify "
                 "that reports task_success=true, verdict=fail and approved pass/fail criteria; "
                 "this retained failure is never a PR-ready handoff. Use interim_repair._worker "
                 "for repair-Verify, including its complete failing-verdict contract. "
                 "Use interim_stack._final_phase_evidence "
                 "for final QA/CI; interim_stack._final_review_evidence for final review. "
                 "Final phases additionally require runtime, wall_time_seconds and tools, validated "
                 "by interim_stack_dispatch._final_runtime. Include the exact observation identity "
                 "(id, session_id, message_id, terminal_turn_id) from this operation. "
                 "Run only the task's approved commands on its exact candidate. If restack_operation_id "
                 "is present, use the operation's candidate base as the effective Verify base. "
                 "Report observed runtime and evidence; never invent success or execution metadata.")
        if "escalated_slot" in operation:
            brief += (" This repair is one reserved escalated slot. Start with a fresh, evidence-based diagnosis "
                      "before implementation. Return diagnosis fields exactly as interim_repair._diagnosis validates: "
                      "id, operation_id, criteria, revisions, execution_evidence, prior_hypotheses, "
                      "conclusion {cause or eliminated_hypothesis}, next_experiment {id, approach, finding_id}, "
                      "actionable, and blocker when not actionable. Record observed failed hypotheses and a "
                      "discriminating experiment. In the same slot you may fix an in-scope prerequisite or "
                      "implement a new hypothesis within the approved slice. If a candidate exists, include "
                      "the complete bounded Build result and exact SHA; fresh Sol/high Verify follows as a "
                      "separate worker. If no candidate exists, report task_success false with diagnosis "
                      "and execution evidence. Do not launch another worker or return to ordinary repair. "
                      "Use only the compact retained evidence in this operation; no prior reasoning transcript.")
        if "escalated_verify" in operation:
            brief += (" Run fresh GPT-6.1 Sol/high Verify on the operation's exact candidate SHA using its "
                      "approved task, commands, criteria and verify_context artifact ID. Read the candidate "
                      "and report independently executed evidence and pass/fail findings. Do not include or "
                      "request the escalated worker's diagnosis or reasoning transcript; builder_transcript must be false.")
        bound = self.worker_hints.pop(observation["id"], None)
        if bound is not None:
            if digest(operation) != bound[3]:
                raise InterimDispatchError("worker hint operation differs from durable intent")
            package_root = Path(__file__).resolve().parents[1]
            repository_root = bound[2]
            brief += (" Use only the approved candidate checkout " + json.dumps(str(bound[5]))
                      + " for source edits and commands. Approved implementation paths are "
                      + json.dumps(list(bound[6]), separators=(",", ":"))
                      + "; refuse source edits outside those paths. The coordinator checkout is used only "
                      "to read the durable control ref and emit the completion hint.")
            if phase == "verify":
                pr_command = " ".join(shlex.quote(part) for part in
                                      ("env", "PYTHONPATH=" + str(package_root), "python3.12", "-m",
                                       "delivery_pilot.interim_pr", "--repository", str(repository_root),
                                       "--remote", bound[4], "--control-ref", bound[1],
                                       "--operation-id", observation["id"]))
                brief += (" Before the final result, open or read the approved PR by running exactly once: `"
                          + pr_command + "`. Use its observed URL, head and base in handoff.pr. "
                          "If it reports unresolved, do not create another PR or claim PR-ready. "
                          "The helper persists a create intent in the coordinator control ref; "
                          "all source work remains in the approved candidate checkout.")
            command = " ".join(shlex.quote(part) for part in
                               ("env", "PYTHONPATH=" + str(package_root), "python3.12", "-m",
                                "delivery_pilot.interim_github", "--repository", str(repository_root),
                                "--remote", bound[4], "worker-done",
                                "--run-id", bound[0], "--control-ref", bound[1],
                                "--operation-id", observation["id"]))
            brief += (" As the final best-effort step before your JSON final answer, run exactly once: "
                      + "`" + command + "`. It emits only a locator hint from the current registered "
                      "checkpoint; failure or no hint must not change the worker result. "
                      "Do not put credentials in the brief, command, or logs.")
        if "escalated_slot" in operation:
            if operation.get("route_preflight") != {"session_id": observation["session_id"], **route}:
                raise InterimDispatchError("escalated send lacks durable authoritative session preflight")
            return self._message_created(operation, self._call("message", "create", "--session", observation["session_id"],
                                                                 "--message-id", observation["message_id"], "--message", brief))
        result = self._call("session", "create", "--workspace", self.workspace_id, "--agent", self.agent,
                            "--session-id", observation["session_id"], "--name", f"interim {phase} {observation['id']}",
                            "--model", route["model"], "--effort", route["effort"],
                            "--message-id", observation["message_id"], "--message", brief)
        if _uuid(result.get("id"), "session-create id") != observation["session_id"]:
            raise InterimDispatchError("Conductor session-create identity differs from durable intent")
        initial = result.get("initialMessage")
        if not isinstance(initial, dict):
            raise InterimDispatchError("Conductor session-create lacks its initial message receipt")
        return self._message_created(operation, {"messageId": initial.get("messageId"), "state": initial.get("state"), "deepLink": initial.get("deepLink", result.get("deepLink"))})

    def preflight_escalated(self, operation: dict[str, Any]) -> dict[str, str]:
        """Provision the exact idle session; no AI turn exists until final admission.

        An ambiguous create is read back by its durable UUID. A mismatch is a
        concrete refusal, not authority to create another session or model.
        """
        if "escalated_slot" not in operation:
            raise InterimDispatchError("route preflight requires an escalated operation")
        session_id = _uuid(operation.get("session_id"), "escalated session identity")
        try:
            route = configured_route(self.routes, operation)
        except (KeyError, TypeError, ValueError) as exc:
            raise InterimDispatchError("approved escalation route is unavailable") from exc
        if operation.get("route") != route or self.agent != "codex":
            raise EscalationRouteError("escalated route differs from configured Codex route")
        try:
            created = self._call("session", "create", "--workspace", self.workspace_id, "--agent", self.agent,
                                 "--session-id", session_id, "--name", f"interim escalated {operation['id']}",
                                 "--model", route["model"], "--effort", route["effort"])
        except InterimDispatchError:
            # Create can succeed while its receipt is lost. The exact-ID read
            # below decides whether the same idle session exists.
            created = None
        if created is not None and (_uuid(created.get("id"), "idle session-create id") != session_id or created.get("initialMessage") is not None):
            raise EscalationRouteError("escalated idle session identity or no-message contract differs")
        return self.confirm_escalated(operation)

    def confirm_escalated(self, operation: dict[str, Any]) -> dict[str, str]:
        """Read exact idle host route; restart recovery never provisions a new session."""
        session_id = _uuid(operation.get("session_id"), "escalated session identity")
        try:
            route = configured_route(self.routes, operation)
        except (KeyError, TypeError, ValueError) as exc:
            raise InterimDispatchError("approved escalation route is unavailable") from exc
        try:
            observed = self._call("session", "get", session_id)
            status = self._call("session", "status", session_id)
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            raise ObservationFailure("uncertain-effect") from exc
        if (observed.get("id") != session_id or status.get("workspaceId") != self.workspace_id
                or status.get("sessionId") != session_id
                or observed.get("model") != route["model"] or observed.get("effort") != route["effort"]
                or observed.get("resolvedModel") != route["model"]
                or status.get("status") != "idle"):
            raise EscalationRouteError("authoritative Conductor idle session route is unavailable or mismatched")
        try:
            transcript = self._call("session", "message", session_id, "--limit", "1", "--offset", "0")
        except (InterimDispatchError, OSError, TimeoutError, ConnectionError) as exc:
            raise ObservationFailure("transient-outage") from exc
        if transcript.get("data") != [] or transcript.get("hasMore") is not False:
            raise EscalationRouteError("escalated session has prior conversation or lacks fresh-context proof")
        return {"session_id": session_id, **route}

    def _status(self, session_id: str, require_dispatch_workspace: bool = True) -> dict[str, Any]:
        result = self._call("session", "status", session_id)
        workspace_id = _uuid(result.get("workspaceId"), "status workspaceId")
        if (require_dispatch_workspace and workspace_id != self.workspace_id) or _uuid(result.get("sessionId"), "status sessionId") != session_id:
            raise InterimDispatchError("Conductor session-status identity differs from requested session")
        if result.get("status") not in {"working", "idle", "error"} or not isinstance(result.get("updatedAt"), str):
            raise InterimDispatchError("Conductor session-status envelope is malformed")
        return result

    def _transcript(self, session_id: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for offset in range(0, MAX_TRANSCRIPT_PAGES * PAGE_SIZE, PAGE_SIZE):
            page = self._call("session", "message", session_id, "--limit", str(PAGE_SIZE), "--offset", str(offset))
            data = page.get("data")
            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                raise InterimDispatchError("Conductor transcript envelope is malformed")
            for item in data:
                event_id = _uuid(item.get("id"), "transcript event id")
                if event_id in seen:
                    raise InterimDispatchError("Conductor transcript pagination repeated an event")
                if _uuid(item.get("sessionId"), "transcript session id") != session_id:
                    raise InterimDispatchError("Conductor transcript event belongs to another session")
                seen.add(event_id); records.append(item)
            more = page.get("hasMore")
            if more is False or (more is None and len(data) < PAGE_SIZE):
                return records
            if more is not True and more is not None:
                raise InterimDispatchError("Conductor transcript pagination marker is malformed")
            if not data:
                raise InterimDispatchError("Conductor transcript pagination made no progress")
        raise InterimDispatchError("Conductor transcript pagination exceeded its bounded read limit")

    @staticmethod
    def _matching_message(records: list[dict[str, Any]], observation: dict[str, str]) -> tuple[dict[str, Any], str] | None:
        matches = []
        for item in records:
            content = item.get("content")
            if item.get("type") != "userMessage" or not isinstance(content, dict) or content.get("id") != observation["message_id"]:
                continue
            if content.get("message") is not None and not isinstance(content["message"], str):
                raise InterimDispatchError("Conductor transcript message content is malformed")
            state = content.get("state")
            if state not in {"queued", "sent"}:
                raise InterimDispatchError("Conductor transcript message state is malformed")
            turn_id = _uuid(content.get("turnId"), "transcript turn identity")
            if turn_id != observation["terminal_turn_id"]:
                raise InterimDispatchError("Conductor transcript turn identity differs from durable message identity")
            matches.append((item, turn_id))
        if len(matches) > 1:
            raise InterimDispatchError("Conductor transcript has conflicting exact message identities")
        return matches[0] if matches else None

    @staticmethod
    def _terminal_turn(records: list[dict[str, Any]], turn_id: str) -> bool:
        """Only an explicit completed raw turn is terminal; idle is insufficient."""
        terminal = False
        for item in records:
            content = item.get("content")
            if not isinstance(content, dict) or content.get("turnId") != turn_id:
                continue
            raw = content.get("rawPayload")
            event = raw.get("event") if isinstance(raw, dict) else None
            if item.get("type") == "agent" and isinstance(content, dict) and isinstance(event, dict) and event.get("type") == "turn.completed" and content.get("turnId") == turn_id and content.get("userMessageId") == turn_id:
                terminal = True
        return terminal

    def observe(self, operation: dict[str, Any]) -> dict[str, Any]:
        if operation.get("phase") == "coordinator":
            return self.observe_coordinator(operation)
        observation = _operation_observation(operation)
        self.operations[observation["id"]] = dict(operation)
        session_id = _uuid(observation["session_id"], "session identity")
        cancellation = self.cancellations.get(observation["id"])
        status = self._status(session_id, require_dispatch_workspace=cancellation is None)
        if status["status"] == "idle" and isinstance(cancellation, dict) and cancellation.get("state") == "cancelled" and cancellation.get("observation") == observation:
            # A confirmed cancelled session need not emit turn.completed. Its
            # cancellation + fresh idle readback prove cessation, never success.
            return {"observation": observation, "transport": "accepted", "worker_state": "terminal", "cancellation": dict(cancellation), "host_status": "idle", "elapsed_seconds": 0}
        if status["status"] == "error":
            # The exact dispatched session failed even when its turn never
            # emitted completion. Keep it as a failed attempt, never success.
            return {"observation": observation, "transport": "accepted", "worker_state": "error",
                    "host_status": "error", "elapsed_seconds": 0}
        records = self._transcript(session_id)
        matched = self._matching_message(records, observation)
        if matched is None:
            return {"observation": observation, "transport": "accepted", "worker_state": "unknown", "elapsed_seconds": 0}
        event, turn_id = matched
        if status["status"] == "working":
            state = "active"
        elif self._terminal_turn(records, turn_id):
            state = "terminal"
        else:
            # An idle session or a transport receipt never fabricates success.
            state = "unknown"
        receipt = {"observation": observation, "transport": "accepted", "worker_state": state,
                "host_event_id": event["id"], "host_turn_id": turn_id, "elapsed_seconds": 0}
        if state != "terminal" or self.result_parser is None:
            if state == "terminal":
                return {**receipt, "terminal_turn": True, "task_success": False,
                        "result_unusable": "terminal-answer-missing"}
            return receipt
        try:
            structured = self.result_parser(dict(operation), records, turn_id)
        except InterimDispatchError:
            # The exact completed turn is already proven by host identity.
            # A broken answer is failed work, not an unresolved host read.
            return {**receipt, "terminal_turn": True, "task_success": False,
                    "result_unusable": "terminal-answer-malformed"}
        if not isinstance(structured, dict):
            return {**receipt, "terminal_turn": True, "task_success": False,
                    "result_unusable": "terminal-answer-missing"}
        if structured.get("observation") != observation:
            return {**receipt, "terminal_turn": True, "task_success": False,
                    "result_unusable": "terminal-answer-identity-conflict"}
        return structured

    def reconcile(self, operation: dict[str, Any]) -> dict[str, Any]:
        return self.observe(operation)

    def reconcile_failed(self, operation: dict[str, Any], record: dict[str, Any], repository: Path) -> dict[str, Any]:
        """Read exact worker cessation and candidate, branch, and PR effects.

        Every read is observational. Unknown or conflicting facts refuse a
        replacement worker; no task-success envelope is manufactured here.
        """
        observation = _operation_observation(operation)
        status = self._status(observation["session_id"])
        if status["status"] != "error":
            if status["status"] != "idle":
                raise InterimDispatchError("failed worker cessation is unconfirmed")
            records = self._transcript(observation["session_id"])
            if not self._terminal_turn(records, observation["terminal_turn_id"]):
                raise InterimDispatchError("failed worker terminal turn is unconfirmed")
        candidate_checkout = _candidate_checkout(record, Path(repository))
        task = operation.get("task")
        if not isinstance(task, dict) or not isinstance(task.get("candidate_ref"), str):
            raise InterimDispatchError("failed worker lacks approved branch identity")
        def git(*args: str) -> str:
            result = subprocess.run(["git", *args], cwd=candidate_checkout, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
            if result.returncode:
                raise InterimDispatchError("failed worker candidate Git readback unavailable")
            return result.stdout.strip()
        candidate_work = _candidate_work(record, candidate_checkout)
        branch = git("symbolic-ref", "--quiet", "--short", "HEAD")
        if branch != task["candidate_ref"]:
            raise InterimDispatchError("failed worker candidate branch differs from approval")
        head = git("rev-parse", "HEAD")
        if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
            raise InterimDispatchError("failed worker candidate head is malformed")
        remote = record["approval"]["repository"]["remote"]
        branch_ref = "refs/heads/" + branch
        remote_line = git("ls-remote", "--heads", remote, branch_ref)
        if remote_line:
            parts = remote_line.split()
            if len(parts) != 2 or parts[1] != branch_ref or parts[0] != head:
                raise InterimDispatchError("failed worker pushed branch differs from candidate")
            branch_head = head
        else:
            branch_head = None
        from .interim_advance import _repository_name, github_pr_readback
        repository_name = _repository_name(record)
        base_ref = record["approval"]["repository"].get("base_ref")
        if not isinstance(base_ref, str) or not base_ref.startswith("refs/heads/"):
            raise InterimDispatchError("failed worker approved base ref is unavailable")
        from urllib.parse import urlencode
        query = urlencode({"state": "open", "head": repository_name.split("/", 1)[0] + ":" + branch,
                           "base": base_ref.removeprefix("refs/heads/")})
        response = subprocess.run(["gh", "api", f"repos/{repository_name}/pulls?{query}"],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if response.returncode:
            raise InterimDispatchError("failed worker PR readback unavailable")
        try:
            listed = json.loads(response.stdout)
        except json.JSONDecodeError as exc:
            raise InterimDispatchError("failed worker PR readback malformed") from exc
        if not isinstance(listed, list) or len(listed) > 1:
            raise InterimDispatchError("failed worker PR readback ambiguous")
        pr = None
        if listed:
            claimed = listed[0].get("html_url") if isinstance(listed[0], dict) else None
            if not isinstance(claimed, str) or branch_head is None:
                raise InterimDispatchError("failed worker PR lacks confirmed pushed branch")
            pr = github_pr_readback(record, claimed)
            if pr["head"] != head or pr["base"] != task["base"]:
                raise InterimDispatchError("failed worker PR differs from candidate")
        return {"observation": observation, "ceased": True, "candidate": {"head": head, "base": task["base"]},
                "branch_head": branch_head, "pr": pr, "candidate_work": candidate_work,
                "effects_complete": True}

    def preflight_repair_candidate(self, record: dict[str, Any], repository: Path,
                                   expected: dict[str, Any]) -> None:
        checkout = _candidate_checkout(record, Path(repository))
        if _candidate_work(record, checkout) != expected:
            raise InterimDispatchError("candidate work changed after failed-worker reconciliation")

    def observe_coordinator(self, operation: dict[str, Any]) -> dict[str, Any]:
        observation = _operation_observation(operation)
        self.operations[observation["id"]] = dict(operation)
        status = self._status(_uuid(observation["session_id"], "coordinator session identity"))
        # This is an observation of an existing session, not a message send.
        # There is no worker message/turn to search for in its transcript.
        return {"observation": observation, "transport": "accepted", "current_coordinator": observation["session_id"],
                "state": "active" if status["status"] == "working" else "unknown",
                "worker_state": "active" if status["status"] == "working" else "terminal" if status["status"] == "idle" else "unknown",
                "host_status": status["status"], "host_updated_at": status["updatedAt"], "elapsed_seconds": 0}

    def coordinators(self, approval: dict[str, Any]) -> list[dict[str, Any]]:
        session_id = _uuid(approval.get("coordinator", {}).get("session_id"), "coordinator identity")
        self._status(session_id)
        return [{"session_id": session_id}]

    def remove_prefix(self, session_id: str, stop_policy: str) -> dict[str, Any]:
        """Remove the exact watchdog opt-in marker and confirm it by readback."""
        session_id = _uuid(session_id, "coordinator identity")
        _text(stop_policy, "whole-run stop policy")
        before = self._call("session", "get", session_id)
        if _uuid(before.get("id"), "session-get id") != session_id:
            raise InterimDispatchError("Conductor session-get identity differs from requested session")
        name = _text(before.get("name"), "session name")
        if name.startswith(WATCHDOG_TITLE_PREFIX):
            replacement = name.removeprefix(WATCHDOG_TITLE_PREFIX) or "stopped interim coordinator"
            renamed = self._call("session", "rename", session_id, "--name", replacement)
            if _uuid(renamed.get("id"), "session-rename id") != session_id:
                raise InterimDispatchError("Conductor session-rename identity differs from requested session")
        after = self._call("session", "get", session_id)
        if _uuid(after.get("id"), "session-get id") != session_id:
            raise InterimDispatchError("Conductor session-get identity differs from requested session")
        readback = _text(after.get("name"), "session name")
        return {"prefix": stop_policy, "readback_removed": not readback.startswith(WATCHDOG_TITLE_PREFIX)}

    def cancel(self, operation: dict[str, Any]) -> dict[str, Any]:
        observation = _operation_observation(operation)
        result = self._call("session", "cancel", observation["session_id"])
        # Later phases may run in a dedicated verifier workspace. The exact
        # durable session UUID is the cancellation authority; retain the host
        # workspace as evidence without requiring the dispatch workspace.
        host_workspace_id = _uuid(result.get("workspaceId"), "cancel workspaceId")
        if _uuid(result.get("sessionId"), "cancel sessionId") != observation["session_id"]:
            raise InterimDispatchError("Conductor cancellation identity differs from durable intent")
        state = result.get("status")
        if state == "idle":
            outcome = "cancelled"
        elif state == "working":
            outcome = "queued"
        else:
            outcome = "uncertain"
        receipt = {"observation": observation, "state": outcome, "host_status": state,
                   "host_workspace_id": host_workspace_id}
        self.cancellations[observation["id"]] = dict(receipt)
        return receipt

    def owned_workers(self, run_id: str) -> list[dict[str, Any]]:
        # Ownership comes from the loaded durable ledger, never titles or a
        # transient workspace inventory. A run may dispatch later phases in a
        # separate verifier workspace, so cessation readback binds the exact
        # durable session identity without assuming one workspace for the run.
        # Stop needs host liveness only; parsing an old task result here would
        # let an unusable historical result prevent cancellation of live work.
        if not isinstance(run_id, str) or not run_id:
            raise InterimDispatchError("durable run identity is malformed")
        result = []
        for operation in self.operations.values():
            if operation.get("phase") == "wake":
                continue
            observation = _operation_observation(operation)
            status = self._call("session", "status", observation["session_id"])
            _uuid(status.get("workspaceId"), "status workspaceId")
            if _uuid(status.get("sessionId"), "status sessionId") != observation["session_id"]:
                raise InterimDispatchError("Conductor session-status identity differs from requested session")
            host_status = status.get("status")
            if host_status not in {"working", "idle", "error"} or not isinstance(status.get("updatedAt"), str):
                raise InterimDispatchError("Conductor session-status envelope is malformed")
            cancellation = self.cancellations.get(observation["id"])
            durable_terminal = operation.get("status") in {"result", "result-unusable", "reconciled", "unfinished-cancelled", "accounted"}
            if host_status == "working":
                state = "active"
            elif host_status == "idle" and (durable_terminal or isinstance(cancellation, dict) and cancellation.get("state") == "cancelled"):
                state = "terminal"
            else:
                state = "unknown"
            receipt = {"observation": observation, "transport": "accepted", "worker_state": state,
                       "host_status": host_status, "host_workspace_id": status["workspaceId"],
                       "host_updated_at": status["updatedAt"], "elapsed_seconds": 0}
            if isinstance(cancellation, dict):
                receipt["cancellation"] = dict(cancellation)
            result.append({"operation_id": operation["id"], "state": state, "receipt": receipt})
        return result

    def load_checkpoint(self, record: dict[str, Any]) -> None:
        """Restore owned operation identities from the durable shared ledger."""
        usage = record.get("usage") if isinstance(record, dict) else None
        operations = usage.get("operations") if isinstance(usage, dict) else None
        if not isinstance(operations, list):
            raise InterimDispatchError("checkpoint has no operation ledger")
        restored: dict[str, dict[str, Any]] = {}
        for operation in operations:
            observation = _operation_observation(operation) if isinstance(operation, dict) else None
            if observation is None or observation["id"] in restored:
                raise InterimDispatchError("checkpoint operation identity is malformed")
            restored[observation["id"]] = dict(operation)
        self.operations = restored
        self.cancellations = {}
        receipts = [operation["cancellation"] for operation in operations if isinstance(operation.get("cancellation"), dict)]
        stop = record.get("recovery", {}).get("stop")
        if isinstance(stop, dict):
            receipts.extend(item.get("receipt") for item in stop.get("cancellations", []) if isinstance(item, dict))
        for receipt in receipts:
            if not isinstance(receipt, dict) or not isinstance(receipt.get("observation"), dict):
                raise InterimDispatchError("checkpoint cancellation lacks a correlated observation")
            operation = restored.get(receipt["observation"].get("id"))
            if operation is None or receipt["observation"] != _operation_observation(operation):
                raise InterimDispatchError("checkpoint cancellation differs from durable operation")
            self.cancellations[operation["id"]] = dict(receipt)


def fixture_envelope(*, main_workspaces: int, routine_deliveries: int, named_sessions: int,
                     session_limit: int, workspace_limit: int) -> dict[str, int]:
    """Compute the conservative S7 envelope; each Routine delivery has a workspace."""
    if any(type(value) is not int or value < 0 for value in (main_workspaces, routine_deliveries, named_sessions, session_limit, workspace_limit)):
        raise ValueError("fixture envelope values must be non-negative integers")
    workspaces = main_workspaces + routine_deliveries
    if workspaces > workspace_limit or named_sessions > session_limit:
        raise ValueError("fixture envelope exceeds its separately approved host limits")
    return {"workspaces": workspaces, "sessions": named_sessions, "routine_workspaces": routine_deliveries}

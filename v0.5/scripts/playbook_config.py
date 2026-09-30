"""Public project-preference boundary; execution remains owned by lane gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Callable

from playbook_state import parse_scalar, strip_inline_comment


DESTINATION = ".playbook-config.json"
ROLES = ("planning", "implementation", "verification", "escalated_repair")
IDENTITY = ("model_id", "runner", "reasoning", "provider", "label", "thinking")


class ConfigError(ValueError):
    """A corrective error which must never cause silent default fallback."""


class RecoveryRequired(ConfigError):
    """A save could not restore prior defaults; retained evidence needs reconciliation."""


def strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ConfigError(f"Duplicate key {key}; remove the duplicate and reload.")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda value: invalid(value))
    except (ValueError, TypeError) as error:
        raise ConfigError(f"Invalid configuration JSON; correct it and reload: {error}") from error


def invalid(value):
    raise ConfigError(f"Unsupported value {value}; correct it and reload.")


def split_values(text):
    parts = []
    start = 0
    depth = 0
    quote = None
    escaped = False
    for index, character in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif character == "\\" and quote == '"':
                escaped = True
            elif character == quote:
                quote = None
        elif character in {'"', "'"}:
            quote = character
        elif character in "[{":
            depth += 1
        elif character in "]}":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    if quote or depth:
        raise ConfigError("Malformed legacy routing value; correct it before adoption.")
    parts.append(text[start:].strip())
    return parts


def legacy_value(raw):
    raw = strip_inline_comment(raw)
    if raw.startswith("{") and raw.endswith("}"):
        entries = split_values(raw[1:-1]) if raw[1:-1].strip() else []
        result = {}
        for entry in entries:
            key, separator, value = entry.partition(":")
            key = key.strip().strip('"\'')
            if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", key) or key in result:
                raise ConfigError("Invalid or duplicate legacy routing key; correct it before adoption.")
            result[key] = legacy_value(value)
        return result
    if raw.startswith("[") and raw.endswith("]"):
        return [legacy_value(value) for value in split_values(raw[1:-1])] if raw[1:-1].strip() else []
    if not raw or raw[0] in "{[&*!>|" or raw.endswith(("}", "]")) or raw.startswith("-"):
        raise ConfigError("Unsupported legacy routing syntax; use scalar or mapping values before adoption.")
    return parse_scalar(raw)


def legacy_routing(text):
    routing = None
    stack = []
    for original in text.splitlines():
        line = strip_inline_comment(original)
        if not line:
            continue
        indent = len(original) - len(original.lstrip(" "))
        if indent == 0:
            stack = []
            if line.startswith("model_routing:"):
                if routing is not None:
                    raise ConfigError("Duplicate model_routing; remove the duplicate and reload.")
                raw = line.partition(":")[2].strip()
                routing = legacy_value(raw) if raw else {}
                if not isinstance(routing, dict):
                    raise ConfigError("model_routing must be a mapping; correct legacy state.")
                stack = [(0, routing)]
            continue
        if not stack:
            continue
        while stack and indent <= stack[-1][0]:
            stack.pop()
        key, separator, raw = line.partition(":")
        if not stack or indent != stack[-1][0] + 2 or not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
            raise ConfigError("Unsupported legacy routing indentation/syntax; correct it before adoption.")
        parent = stack[-1][1]
        if key in parent:
            raise ConfigError(f"Duplicate legacy routing key {key}; remove it and reload.")
        value = legacy_value(raw.strip()) if raw.strip() else {}
        parent[key] = value
        if not raw.strip():
            stack.append((indent, value))
    return routing or {}


def validate_choice(choice, location):
    if not isinstance(choice, dict):
        raise ConfigError(f"{location} must be a route mapping; edit and reload.")
    for key in ("model_id", "runner", "reasoning"):
        value = choice.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}", value):
            raise ConfigError(f"{location}.{key} must be a nonempty portable identity; edit and reload.")
    supported = set(IDENTITY) | {"trigger_unsuccessful_repairs", "cycles_per_slice", "scope", "authority"}
    for key, value in choice.items():
        if key not in supported:
            raise ConfigError(f"{location} has unsupported preference fields; reconcile them without copying secrets or local settings.")
        if not isinstance(key, str) or not isinstance(value, (str, int, bool, type(None))):
            raise ConfigError(f"{location}.{key} is unsupported; preserve it manually before adoption.")
    if location.endswith("escalated_repair"):
        for key in ("trigger_unsuccessful_repairs", "cycles_per_slice"):
            if type(choice.get(key)) is not int or choice[key] < 1:
                raise ConfigError(f"{location}.{key} must be a positive integer; correct it before adoption.")
        if choice.get("scope") != "approved_slice" or choice.get("authority") != "diagnose_and_implement":
            raise ConfigError(f"{location} has unsupported escalation constraints; reconcile before adoption.")


def validate_config(config):
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ConfigError("Unsupported configuration schema; use a compatible editor or restore schema 1.")
    if set(config) != {"schema_version", "adopted", "models"} or config["adopted"] is not True:
        raise ConfigError("Invalid adoption record; reconcile .playbook-config.json before continuing.")
    if not isinstance(config["models"], dict) or set(config["models"]) != set(ROLES):
        raise ConfigError("Configuration must retain all four model roles; correct it and reload.")
    for role, choice in config["models"].items():
        validate_choice(choice, f"models.{role}")
    return config


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone required")
        return parsed
    except (ValueError, TypeError, AttributeError) as error:
        raise ConfigError("Discovery check date must be a timezone-aware ISO timestamp; rediscover routes.") from error


class Configuration:
    def __init__(self, project: Path, discover: Callable, clock: Callable = None, checkpoint: Callable = None):
        self.project = Path(project)
        self.discover = discover
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.path = self.project / DESTINATION
        self.state_path = self.project / ".playbook-state.yml"
        self.lock = self.project / ".playbook-config.lock"
        self.recovery = self.project / ".playbook-config.recovery"
        self.checkpoint = checkpoint or (lambda point: None)

    def _bytes(self, path):
        if path.is_symlink():
            raise ConfigError(f"{path.name} is a symlink; reconcile the destination before editing.")
        return path.read_bytes() if path.exists() else None

    def _snapshot(self):
        if self.lock.exists() or self.recovery.exists():
            raise ConfigError("Configuration transaction/recovery pending; reconcile before reading or writing defaults.")
        self._reconcile_receipts()
        saved = self._bytes(self.path)
        runtime = self._bytes(self.state_path)
        if saved is not None:
            config = validate_config(strict_json(saved.decode()))
            origins = {role: "adopted project" for role in ROLES}
        else:
            edition = legacy_routing((Path(__file__).parent.parent / "templates/.playbook-state.yml").read_text())["defaults"]
            routing = legacy_routing(runtime.decode()) if runtime is not None else {}
            defaults = routing.get("defaults", {})
            if not isinstance(defaults, dict) or set(defaults) - set(ROLES):
                raise ConfigError("Unknown or invalid legacy role preferences; reconcile them before adoption.")
            models = {role: deepcopy(defaults.get(role, edition[role])) for role in ROLES}
            config = validate_config({"schema_version": 1, "adopted": True, "models": models})
            origins = {role: "legacy project" if role in defaults else "edition" for role in ROLES}
        if self.lock.exists() or self.recovery.exists():
            raise ConfigError("Configuration changed during read; wait for the transaction or reconcile recovery.")
        self._reconcile_receipts()
        return config, origins, {DESTINATION: digest(saved), ".playbook-state.yml": digest(runtime)}

    def _receipt_conflicts(self, receipt, marker, completing=False):
        seal = receipt.with_name(receipt.name + ".complete")
        if receipt.with_name(receipt.name + ".conflict").exists():
            raise RecoveryRequired(f"Unresolved configuration completion conflict in {receipt.name}; reconcile retained evidence.")
        if not completing and marker.get("completion_protocol") in (2, 3):
            if not seal.is_dir() or seal.is_symlink():
                raise RecoveryRequired(f"Unfinished configuration receipt {receipt.name}; reconcile retained files before continuing.")
            if marker["completion_protocol"] == 3:
                return
        if marker.get("completion_protocol") in (2, 3):
            evidence = [(self.project / marker["attempted"], marker["attempted_digest"])]
            if marker.get("previous"):
                evidence.append((self.project / marker["previous"], marker["previous_digest"]))
            for path, expected in evidence:
                if digest(self._bytes(path)) != expected:
                    raise RecoveryRequired(f"Retained configuration evidence changed in {receipt.name}; reconcile {path.name}.")
        observations = [(self.path, marker["attempted_digest"])]
        if marker.get("published"):
            observations.append((self.project / marker["published"], marker["attempted_digest"]))
        if marker.get("captured"):
            observations.append((self.project / marker["captured"], marker["previous_digest"]))
        if "runtime_digest" in marker:
            observations.append((self.state_path, marker["runtime_digest"]))
        for path, expected in observations:
            if digest(self._bytes(path)) != expected:
                raise RecoveryRequired(f"Configuration completion conflict in {receipt.name} ({path.name}); reconcile reviewed, captured and attempted evidence before continuing.")

    def _reconcile_receipts(self):
        for receipt in self.project.glob(".playbook-config-*.receipt"):
            try:
                marker = strict_json(self._bytes(receipt).decode())
                if marker.get("destination") != DESTINATION or marker.get("completion_protocol") not in (None, 2, 3):
                    raise ConfigError("Unsupported configuration receipt; reconcile its completion protocol.")
                for key in ("captured", "previous", "attempted", "published"):
                    name = marker.get(key)
                    if name is not None and (not isinstance(name, str) or Path(name).name != name or not name.startswith(".playbook-config-")):
                        raise ConfigError("Invalid retained evidence name.")
                self._receipt_conflicts(receipt, marker)
            except (ConfigError, OSError, UnicodeError, KeyError, TypeError, AttributeError) as error:
                raise RecoveryRequired(f"Reconcile configuration receipt {receipt.name}: {error}") from error

    def resolve(self, role, feature_choice=None):
        if role not in ROLES:
            raise ConfigError("Unknown model role; use planning, implementation, verification or escalated_repair.")
        config, origins, _ = self._snapshot()
        if feature_choice is not None:
            validate_choice(feature_choice, f"feature.{role}")
            return {"origin": "feature", "choice": deepcopy(feature_choice)}
        return {"origin": origins[role], "choice": deepcopy(config["models"][role])}

    def _available(self):
        request = {"request_id": uuid.uuid4().hex, "started_at": self.clock(),
                   "roles": list(ROLES), "purpose": "current-availability"}
        evidence = deepcopy(self.discover(deepcopy(request)))
        finished_at = self.clock()
        if not isinstance(evidence, dict) or evidence.get("authority") not in {
            "host-reported-selection", "provider-response-metadata", "session-thread-metadata",
        } or not isinstance(evidence.get("revision"), str) or not evidence["revision"]:
            raise ConfigError("Authoritative current host discovery is missing; rediscover through model-router.")
        if (evidence.get("request_id") != request["request_id"]
                or not instant(request["started_at"]) <= instant(evidence.get("checked_at")) <= instant(finished_at)):
            raise ConfigError("Discovery must freshly observe role/model/runner/reasoning for this request; cached guidance is not availability.")
        if not isinstance(evidence.get("routes"), list):
            raise ConfigError("Discovery routes must be a verified list; rediscover.")
        routes = []
        seen = set()
        for route in evidence["routes"]:
            if not isinstance(route, dict) or set(route) - set(IDENTITY) - {"roles"}:
                raise ConfigError("Invalid discovered route fields; rediscover.")
            choice = {key: value for key, value in route.items() if key != "roles"}
            validate_choice(choice, "discovery.route")
            roles = route.get("roles")
            if not isinstance(roles, list) or not roles or any(role not in ROLES for role in roles):
                raise ConfigError("Discovery must identify supported roles; rediscover.")
            identity = tuple(choice.get(key) for key in IDENTITY)
            if identity in seen:
                raise ConfigError("Duplicate discovered route; reconcile discovery.")
            seen.add(identity)
            if "implementation" in roles:
                routes.append(choice)
        return routes, evidence

    def read(self):
        try:
            config, origins, inputs = self._snapshot()
            routes, evidence = self._available()
            proposal = {
                "state": "decision_required", "step": "read", "destination": DESTINATION,
                "origin": origins["implementation"], "origins": origins, "migration": inputs[DESTINATION] is None,
                "before": deepcopy(config["models"]), "after": deepcopy(config["models"]),
                "inputs": inputs, "discovery": evidence, "alternatives": routes,
                "choices": ["Edit Build", "Apply", "Explain", "Not now"],
                "message": "Project defaults only. All four roles are retained. No active selection changes; no model launches.",
            }
            proposal["proposal_revision"] = self._revision(proposal)
            return proposal
        except (ConfigError, OSError, UnicodeError, TypeError) as error:
            return self._blocked(error)

    def _blocked(self, error):
        return {"state": "recovery_required" if self.recovery.exists() or isinstance(error, RecoveryRequired) else "blocked", "message": str(error), "choices": ["Edit Build", "Reload", "Not now"], "launched": False}

    def _revision(self, proposal):
        return digest(encoded({key: proposal[key] for key in ("destination", "origins", "migration", "before", "after", "inputs", "discovery", "alternatives")}))

    def _discovery_revision(self, evidence):
        return digest(encoded({key: value for key, value in evidence.items() if key not in {"checked_at", "request_id"}}))

    def reply(self, proposal, text):
        if not isinstance(proposal, dict) or not isinstance(text, str):
            return self._blocked("Reply requires a structured proposal and a typed choice; reload.")
        reply = text.strip().lower()
        if reply == "not now":
            return {"state": "unchanged", "message": "Nothing applied. No defaults, runtime records or presets changed.", "launched": False}
        if reply == "reload":
            return self.read()
        if reply == "edit build" and proposal.get("state") == "blocked":
            refreshed = self.read()
            return self.reply(refreshed, text) if refreshed.get("state") == "decision_required" else refreshed
        if proposal.get("state") not in {"decision_required", "proposal_ready"}:
            return self._blocked("Reload and review a valid proposal before continuing.")
        draft = deepcopy(proposal)
        if reply == "edit build":
            draft.update(step="edit", state="decision_required", choices=[str(index + 1) for index in range(len(draft["alternatives"]))] + ["Reload", "Not now"])
            draft["message"] = "Choose a verified Build route by number. Availability is not suitability or cost evidence." if draft["alternatives"] else "No verified Build route is available; rediscover and Reload, or Not now."
            return draft
        if reply.isdigit() and draft.get("step") == "edit":
            index = int(reply) - 1
            if not 0 <= index < len(draft["alternatives"]):
                return self._blocked("Invalid choice; edit Build or reload the proposal.")
            previous = draft["after"]["implementation"]
            draft["after"]["implementation"] = {**{key: value for key, value in previous.items() if key not in IDENTITY}, **draft["alternatives"][index]}
            draft.update(step="preview", state="proposal_ready", choices=["Apply", "Edit Build", "Explain", "Not now"])
            draft["proposal_revision"] = self._revision(draft)
            return draft
        if reply == "explain":
            draft["message"] = "Verified access only; task suitability and comparable total cost are unknown. No recommendation or paid benchmark. Discovery authority: " + draft["discovery"]["authority"] + "; checked " + draft["discovery"]["checked_at"]
            return draft
        if reply == "apply" and draft.get("step") in {"read", "preview"}:
            return self.apply(draft)
        return self._blocked("Use the typed choices shown; reload if the draft is stale.")

    def apply(self, proposal):
        try:
            if proposal.get("proposal_revision") != self._revision(proposal):
                raise ConfigError("Proposal changed outside the editor; reload and preview before Apply.")
            config, _, inputs = self._snapshot()
            routes, evidence = self._available()
            if inputs != proposal.get("inputs") or config["models"] != proposal.get("before"):
                raise ConfigError("Inputs changed since preview; reload and review the new proposal.")
            candidate = validate_config({"schema_version": 1, "adopted": True, "models": deepcopy(proposal["after"])})
            for role in ROLES:
                if role != "implementation" and candidate["models"][role] != config["models"][role]:
                    raise ConfigError("S1 edits Build only; reload without other role changes.")
            constraints = lambda choice: {key: value for key, value in choice.items() if key not in IDENTITY}
            if constraints(candidate["models"]["implementation"]) != constraints(config["models"]["implementation"]):
                raise ConfigError("Build constraints are not editable preferences; reload without changing them.")
            build = {key: value for key, value in candidate["models"]["implementation"].items() if key in IDENTITY}
            if build not in routes:
                raise ConfigError("Build choice is unavailable; edit Build and review again. No substitution.")
            if self._discovery_revision(evidence) != self._discovery_revision(proposal["discovery"]):
                raise ConfigError("Discovery changed since preview; reload and review current available choices.")
            if not proposal["migration"] and candidate == config:
                return {"state": "unchanged", "destination": DESTINATION, "message": "Already adopted; no write needed.", "launched": False}
            self._save(candidate, inputs, evidence)
            return {"state": "applied", "destination": DESTINATION, "message": "Project defaults saved and validated. Runtime records unchanged. No build starts.", "launched": False}
        except (ConfigError, OSError, UnicodeError, KeyError, TypeError) as error:
            return self._blocked(error)

    def _save(self, candidate, inputs, evidence):
        with self.lock.open("x"):
            pass
        staged = None
        publication = None
        backup = None
        captured_path = None
        committed = False
        completed = False
        recover = False
        captured = False
        journaled = False
        receipt = None
        candidate_bytes = encoded(candidate)
        try:
            self._check_inputs(inputs)
            previous = self._bytes(self.path)
            if digest(previous) != inputs[DESTINATION]:
                raise ConfigError("Configuration changed before staging; reload without overwriting it.")
            if previous is not None:
                backup = self._stage(previous)
                captured_path = self._stage(b"")
            staged = self._stage(candidate_bytes)
            publication = self._stage(candidate_bytes)
            self.checkpoint("staged")
            validate_config(strict_json(staged.read_text()))
            self.checkpoint("before_replace")
            self._check_inputs(inputs)
            _, current_evidence = self._available()
            if self._discovery_revision(current_evidence) != self._discovery_revision(evidence):
                raise ConfigError("Availability evidence changed before save; reload and review current choices.")
            marker = {"destination": DESTINATION, "previous": backup.name if backup else None,
                      "captured": captured_path.name if captured_path else None,
                      "attempted": staged.name, "attempted_digest": digest(candidate_bytes),
                      "published": publication.name,
                      "previous_digest": inputs[DESTINATION],
                      "runtime_digest": inputs[".playbook-state.yml"], "completion_protocol": 3}
            with self.recovery.open("x") as stream:
                stream.write(encoded(marker).decode())
                stream.flush()
                os.fsync(stream.fileno())
            journaled = True
            self._sync_directory()
            if backup is not None:
                os.replace(self.path, captured_path)
                captured = True
                self._sync_directory()
                if digest(self._bytes(captured_path)) != inputs[DESTINATION]:
                    raise ConfigError("Concurrent configuration captured intact; reconcile recovery before continuing.")
            self.checkpoint("before_publish")
            try:
                os.link(publication, self.path)
            except FileExistsError as error:
                raise ConfigError("Destination changed during publication; external file retained, reload or reconcile recovery.") from error
            committed = True
            self.checkpoint("committed")
            actual = self._bytes(self.path)
            if actual != candidate_bytes:
                raise ConfigError("Saved configuration changed during validation; recovery is required.")
            validate_config(strict_json(actual.decode()))
            if digest(self._bytes(self.state_path)) != inputs[".playbook-state.yml"]:
                raise ConfigError("Runtime inputs changed during Apply; retained defaults require reconciliation.")
            if captured_path is not None and digest(self._bytes(captured_path)) != inputs[DESTINATION]:
                raise ConfigError("Captured configuration changed during Apply; retained bytes require reconciliation.")
            self._sync_directory()
            receipt = self.project / (staged.name + ".receipt")
            os.replace(self.recovery, receipt)
            journaled = False
            self._sync_directory()
            self.checkpoint("before_completion")
            self._receipt_conflicts(receipt, marker, completing=True)
            seal = receipt.with_name(receipt.name + ".complete")
            seal.mkdir()
            completed = True
        except (OSError, ConfigError, UnicodeError) as error:
            if committed or captured:
                recover = True
                if receipt is not None and receipt.exists():
                    try:
                        receipt.with_name(receipt.name + ".conflict").mkdir(exist_ok=True)
                        self._sync_directory()
                    except OSError:
                        pass
                if not self.recovery.exists() and receipt is not None:
                    try:
                        os.link(receipt, self.recovery)
                    except OSError:
                        pass
                try:
                    self.checkpoint("rollback")
                    self._bytes(self.path)
                    if not committed and captured_path is not None:
                        try:
                            os.link(captured_path, self.path)
                        except FileExistsError:
                            pass
                    self._sync_directory()
                except (OSError, ConfigError):
                    pass
                raise RecoveryRequired(f"Save incomplete ({error}); no destructive rollback attempted. Reconcile {self.recovery.name} and retained files before continuing.") from error
            if journaled:
                self.recovery.unlink()
                self._sync_directory()
            raise
        finally:
            if publication is not None and not committed and not recover:
                publication.unlink(missing_ok=True)
            if staged is not None and not recover and not completed:
                staged.unlink(missing_ok=True)
            if backup is not None and not captured and not recover:
                backup.unlink(missing_ok=True)
            if captured_path is not None and not captured and not recover:
                captured_path.unlink(missing_ok=True)
            if not recover:
                self.lock.unlink()

    def _check_inputs(self, inputs):
        if digest(self._bytes(self.path)) != inputs[DESTINATION] or digest(self._bytes(self.state_path)) != inputs[".playbook-state.yml"]:
            raise ConfigError("Inputs changed before save; reload without overwriting them.")

    def _stage(self, data):
        staged = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.project, prefix=".playbook-config-", delete=False) as stream:
                staged = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return staged
        except OSError:
            if staged is not None:
                staged.unlink(missing_ok=True)
            raise

    def _sync_directory(self):
        descriptor = os.open(self.project, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

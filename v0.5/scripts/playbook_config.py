"""Public project-preference boundary; execution remains owned by lane gates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import uuid
from typing import Callable

from playbook_state import parse_scalar, strip_inline_comment


DESTINATION = ".playbook-config.json"
ROLES = ("planning", "implementation", "verification", "escalated_repair")
ROLE_LABELS = dict(zip(ROLES, ("Plan", "Build", "Verify", "Repair")))
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
    if set(config) not in ({"schema_version", "adopted", "models"}, {"schema_version", "adopted", "models", "skills"}) or config["adopted"] is not True:
        raise ConfigError("Invalid adoption record; reconcile .playbook-config.json before continuing.")
    if not isinstance(config["models"], dict) or set(config["models"]) != set(ROLES):
        raise ConfigError("Configuration must retain all four model roles; correct it and reload.")
    for role, choice in config["models"].items():
        validate_choice(choice, f"models.{role}")
    if "skills" in config:
        from skill_bindings import validate_bindings
        validate_bindings(config["skills"])
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
    def __init__(self, project: Path, discover: Callable, clock: Callable = None, checkpoint: Callable = None,
                 preferences_dir: Path = None, context: dict = None, bindings=None):
        self.project = Path(project)
        self.discover = discover
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        self.path = self.project / DESTINATION
        self.destination = DESTINATION
        self.state_path = self.project / ".playbook-state.yml"
        self.lock = self.project / ".playbook-config.lock"
        self.recovery = self.project / ".playbook-config.recovery"
        self.checkpoint = checkpoint or (lambda point: None)
        self.context = deepcopy(context)
        self.bindings = bindings
        self.preferences = None
        self._write_stores = (self,)
        self._directory_fd = None
        if preferences_dir is not None:
            local = Path(preferences_dir)
            if local.resolve().is_relative_to(self.project.resolve()):
                raise ConfigError("Personal preferences require a user-local directory outside the project; preview it explicitly.")
            self.preferences = LocalPreferences(local, discover, self.clock, self.checkpoint)
            self.preferences.state_path = self.state_path
            self.preferences.owner_project = self.project
            self._write_stores = (self, self.preferences)
            self.preferences._write_stores = self._write_stores

    def _guard_write(self, active=False):
        for store in self._write_stores:
            store._check_directory()
            if active and store is self:
                continue
            if store._exists(store.lock) or store._exists(store.recovery):
                if active:
                    raise RecoveryRequired("Paired configuration transaction/recovery pending; reconcile its retained evidence.")
                if store.destination == DESTINATION:
                    raise ConfigError("Configuration transaction/recovery pending; reconcile before reading or writing defaults.")
                raise RecoveryRequired("Local preferences transaction/recovery pending; reconcile its retained evidence.")
            store._reconcile_receipts()
            store._check_directory()

    def _validate_candidate(self, candidate):
        return validate_config(candidate)

    def _check_directory(self):
        pass

    def _filename(self, path):
        if self._directory_fd is None:
            return path
        return path.name if path.parent == self.project else path.absolute()

    def _open(self, path, mode):
        if self._directory_fd is None or path.parent != self.project:
            return path.open(mode)
        return open(path, mode, opener=lambda name, flags: os.open(
            path.name, flags | os.O_NOFOLLOW, 0o600, dir_fd=self._directory_fd))

    def _stat(self, path):
        return os.stat(self._filename(path), dir_fd=self._directory_fd, follow_symlinks=False)

    def _exists(self, path):
        if self._directory_fd is None:
            return path.exists()
        try:
            self._stat(path)
            return True
        except FileNotFoundError:
            return False

    def _unlink(self, path, missing_ok=False):
        if self._directory_fd is None:
            return path.unlink(missing_ok=missing_ok)
        try:
            os.unlink(self._filename(path), dir_fd=self._directory_fd)
        except FileNotFoundError:
            if not missing_ok:
                raise

    def _mkdir(self, path, exist_ok=False):
        if self._directory_fd is None:
            return path.mkdir(exist_ok=exist_ok)
        try:
            os.mkdir(self._filename(path), dir_fd=self._directory_fd)
        except FileExistsError:
            if not exist_ok or not stat.S_ISDIR(self._stat(path).st_mode):
                raise

    def _link(self, source, destination):
        if self._directory_fd is None:
            return os.link(source, destination)
        os.link(self._filename(source), self._filename(destination),
                src_dir_fd=self._directory_fd, dst_dir_fd=self._directory_fd)

    def _replace(self, source, destination):
        if self._directory_fd is None:
            return os.replace(source, destination)
        os.replace(self._filename(source), self._filename(destination),
                   src_dir_fd=self._directory_fd, dst_dir_fd=self._directory_fd)

    def _bytes(self, path):
        if self._directory_fd is None:
            if path.is_symlink():
                raise ConfigError(f"{path.name} is a symlink; reconcile the destination before editing.")
            return path.read_bytes() if path.exists() else None
        if not self._exists(path):
            if path.is_symlink():
                raise ConfigError(f"{path.name} is a symlink; reconcile the destination before editing.")
            return None
        if stat.S_ISLNK(self._stat(path).st_mode):
            raise ConfigError(f"{path.name} is a symlink; reconcile the destination before editing.")
        with self._open(path, "rb") as stream:
            return stream.read()

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
        if self._exists(receipt.with_name(receipt.name + ".conflict")):
            raise RecoveryRequired(f"Unresolved configuration completion conflict in {receipt.name}; reconcile retained evidence.")
        if not completing and marker.get("completion_protocol") in (2, 3):
            if not self._exists(seal) or not stat.S_ISDIR(self._stat(seal).st_mode):
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
        if completing:
            self._guard_write(active=True)

    def _reconcile_receipts(self):
        receipts = self.project.glob(".playbook-config-*.receipt") if self._directory_fd is None else (
            self.project / name for name in os.listdir(self._directory_fd)
            if name.startswith(".playbook-config-") and name.endswith(".receipt"))
        for receipt in receipts:
            try:
                marker = strict_json(self._bytes(receipt).decode())
                if marker.get("destination") != self.destination or marker.get("completion_protocol") not in (None, 2, 3):
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
        routes = {role: [] for role in ROLES}
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
            for role in roles:
                if choice not in routes[role]:
                    routes[role].append(choice)
        return routes, evidence

    def read(self):
        try:
            config, origins, inputs = self._snapshot()
            routes, evidence = self._available()
            proposal = {
                "state": "decision_required", "step": "read", "destination": DESTINATION,
                "origin": origins["implementation"], "origins": origins, "migration": inputs[DESTINATION] is None,
                "before": deepcopy(config["models"]), "after": deepcopy(config["models"]),
                "inputs": inputs, "discovery": evidence, "alternatives": routes["implementation"],
                "role_alternatives": routes, "edited_roles": [],
                "qa": {"inherits": "verification", "choice": deepcopy(config["models"]["verification"])},
                "coordinator": {"observed": False, "message": "Current-chat identity not observed; display unknown, never switch."},
                "choices": self._proposal_choices(),
                "message": "Project defaults only. All four roles are retained. No active selection changes; no model launches.",
                "context": self.context, "personal": self._personal_snapshot(),
                "bootstrap": {"required": inputs[".playbook-state.yml"] is None,
                              "action": "Use the existing bootstrap preview/approval gate; configuration never bootstraps."},
            }
            bindings = self._bindings()
            bindings.rejections = []
            starting = deepcopy(config.get("skills", bindings.defaults()))
            proposal.update(skill_before=deepcopy(starting), skill_after=deepcopy(starting),
                            skills_adopted="skills" in config, edited_jobs=[],
                            skill_alternatives={job: bindings.options(job) for job in starting["jobs"]},
                            skill_rejections=deepcopy(bindings.rejections))
            if evidence.get("coordinator") is not None:
                validate_choice(evidence["coordinator"], "coordinator")
                proposal["coordinator"] = {"observed": True, "choice": deepcopy(evidence["coordinator"]),
                                           "authority": evidence["authority"], "checked_at": evidence["checked_at"],
                                           "message": "Current chat observed during this discovery; display-only, not launch proof."}
            self._present(proposal)
            proposal["proposal_revision"] = self._revision(proposal)
            return proposal
        except (ConfigError, OSError, UnicodeError, TypeError) as error:
            return self._blocked(error)

    def _blocked(self, error):
        return {"state": "recovery_required" if self.recovery.exists() or isinstance(error, RecoveryRequired) else "blocked", "message": str(error), "choices": ["Edit", "Edit Build", "Reload", "Not now"], "launched": False}

    def _proposal_choices(self):
        return ["Apply", "Edit", "Edit Plan", "Edit Build", "Edit Verify", "Edit Repair", "Edit skills", "Explain", "Not now"]

    def _bindings(self):
        if self.bindings is None:
            from skill_bindings import JobBindings
            self.bindings = JobBindings(self.project)
        return self.bindings

    def dispatch_job(self, job, owner, invoke=None, approved_binding=None):
        config, _, _ = self._snapshot()
        if approved_binding is not None:
            result = self._bindings().dispatch(approved_binding, job, owner, invoke)
            result["origin"] = "approved execution"
            return result
        if "skills" not in config:
            from skill_bindings import JOBS
            if job not in JOBS or owner != JOBS[job]["owner"]:
                raise ConfigError("Only the owning stage may consume this job binding.")
            return {"configured": False, "job": job, "owner": owner, "launched": False,
                    "message": "No adopted job binding; retain the existing stage route and compatibility checks."}
        result = self._bindings().dispatch(config["skills"], job, owner, invoke)
        result["origin"] = "adopted project"
        return result

    def _personal_snapshot(self):
        if self.preferences is None:
            return None
        before, inputs = self.preferences.snapshot()
        resolved = Path(inputs["directories"]["personal"]["resolved"]) / self.preferences.destination
        return {"destination": str(self.preferences.path), "resolved_destination": str(resolved),
                "before": before, "after": deepcopy(before), "inputs": inputs}

    def _refresh_personal_destination(self, draft):
        if self.preferences is None or draft.get("personal") is None:
            return False
        try:
            self._guard_write()
            current = self._personal_snapshot()
        except (ConfigError, OSError):
            return False
        previous = draft["personal"]
        content = lambda inputs: {key: value for key, value in inputs.items() if key != "directories"}
        if (current["destination"] == previous["destination"] and current["before"] == previous["before"]
                and content(current["inputs"]) == content(previous["inputs"])
                and current["inputs"] != previous["inputs"]):
            current["after"] = previous["after"]
            draft["personal"] = current
            return True
        return False

    def _present(self, proposal):
        context = proposal["context"]
        if context is not None:
            if not isinstance(context, dict) or set(context) - {"goal", "billing"}:
                raise ConfigError("Supply only known goal and billing context; keep private evidence outside project settings.")
            if "goal" in context and (not isinstance(context["goal"], str) or not context["goal"].strip()):
                raise ConfigError("Known goal must be nonempty text.")
            if "billing" in context and context["billing"] not in {"api", "subscription", "mixed", "unknown"}:
                raise ConfigError("Billing context must be api, subscription, mixed or unknown.")
        personal = proposal["personal"]
        preference = personal["after"] if personal else None
        proposal["presentation"] = preference["presentation"] if preference else "guided"
        missing = [key for key in ("goal", "billing") if context is not None and key not in context]
        if personal is not None and preference is None:
            missing.append("presentation")
        proposal["missing_context"] = missing
        proposal["questions"] = {key: {"goal": "Goal <project context>", "billing": "Billing api / subscription / mixed / unknown", "presentation": "Guided / Expert"}[key] for key in missing}
        proposal["qa"] = {"inherits": "verification", "choice": deepcopy(proposal["after"]["verification"])}
        proposal["role_proposal"] = [{"role": role, "label": ROLE_LABELS[role], "origin": proposal["origins"][role],
                                      "before": deepcopy(proposal["before"][role]), "after": deepcopy(proposal["after"][role]),
                                      "reason": "Retained starting choice or explicit edit, not a recommendation. Task-fit and cost evidence unavailable until S6."} for role in ROLES]
        def labels(job, selection):
            options = proposal["skill_alternatives"][job]
            return [next((option["label"] for option in options if option["binding"] == binding),
                         "Unverified source " + binding["source_id"] + " — blocked; edit to an explicit fallback")
                    for binding in selection["jobs"][job]]
        proposal["skill_proposal"] = [{"job": job, "before": labels(job, proposal["skill_before"]),
                                       "after": labels(job, proposal["skill_after"]),
                                       "origin": "adopted project" if proposal["skills_adopted"] else "explicit stage fallback preview"}
                                      for job in proposal["skill_after"]["jobs"]]
        proposal["skill_changes"] = deepcopy(proposal["skill_proposal"])
        proposal["choices"] = self._proposal_choices() + list(proposal["questions"].values())
        if personal is not None:
            proposal["choices"] += ["Guided", "Expert"]
        proposal["launched"] = False

    @staticmethod
    def _revision(proposal):
        return digest(encoded({key: value for key, value in proposal.items() if key != "proposal_revision"}))

    def _seal(self, proposal):
        proposal["proposal_revision"] = self._revision(proposal)
        return proposal

    def _discovery_revision(self, evidence):
        return digest(encoded({key: value for key, value in evidence.items() if key not in {"checked_at", "request_id", "coordinator"}}))

    def reply(self, proposal, text):
        try:
            result = self._reply(proposal, text)
        except (ConfigError, OSError, UnicodeError, KeyError, TypeError, AttributeError) as error:
            result = self._blocked(error)
        return self.retain_proposal(result, proposal)

    @staticmethod
    def retain_proposal(result, proposal):
        retained = proposal
        if isinstance(proposal, dict) and proposal.get("state") in {"blocked", "recovery_required"}:
            retained = proposal.get("retained_proposal")
        if (result.get("state") in {"blocked", "recovery_required"} and isinstance(retained, dict)
                and retained.get("state") in {"decision_required", "proposal_ready"}
                and retained.get("proposal_revision") == Configuration._revision(retained)):
            result["retained_proposal"] = deepcopy(retained)
            result.setdefault("choices", ["Reload", "Not now"]).append("Back")
        return result

    def _reply(self, proposal, text):
        if not isinstance(proposal, dict) or not isinstance(text, str):
            return self._blocked("Reply requires a structured proposal and a typed choice; reload.")
        reply = text.strip().lower()
        if reply == "not now":
            return {"state": "unchanged", "message": "No pending changes applied. Project defaults, runtime records and presets unchanged; any previously saved local presentation remains saved.", "launched": False}
        if reply == "reload":
            return self.read()
        if (proposal.get("state") in {"blocked", "recovery_required"} and proposal.get("retained_proposal")
                and (reply == "back" or reply == "edit" or reply.startswith("edit "))):
            retained = proposal["retained_proposal"]
            if retained.get("proposal_revision") == self._revision(retained):
                if reply != "back":
                    return self._reply(retained, text)
                restored = deepcopy(retained)
                if self._refresh_personal_destination(restored):
                    restored["message"] = "Directory identity changed; review the resolved personal destination. Role drafts are retained."
                return self._seal(restored)
            return self._blocked("Retained draft changed; reload and review it.")
        if reply == "edit build" and proposal.get("state") == "blocked":
            refreshed = self.read()
            return self.reply(refreshed, text) if refreshed.get("state") == "decision_required" else refreshed
        if proposal.get("state") not in {"decision_required", "proposal_ready"}:
            return self._blocked("Reload and review a valid proposal before continuing.")
        try:
            if proposal.get("proposal_revision") != self._revision(proposal):
                raise ConfigError("Proposal changed outside the editor; reload and preview before continuing.")
        except (ConfigError, KeyError, TypeError) as error:
            return self._blocked(error)
        draft = deepcopy(proposal)
        if reply.startswith("goal ") or reply.startswith("billing "):
            key, _, value = text.strip().partition(" ")
            key = key.lower()
            draft["context"] = draft["context"] or {}
            draft["context"][key] = value.strip() if key == "goal" else value.strip().lower()
            try:
                self._present(draft)
            except ConfigError as error:
                return self._blocked(error)
            draft["proposal_revision"] = self._revision(draft)
            return draft
        if reply in {"guided", "expert"}:
            if draft["personal"] is None:
                return self._blocked("Supply an explicit user-local preferences directory before changing presentation.")
            draft["personal"]["after"] = {"schema_version": 1, "presentation": reply}
            changed_directory = self._refresh_personal_destination(draft)
            draft.update(step="preference_preview", choices=["Apply preference", "Back", "Not now"],
                         message="Only local presentation will be saved to the displayed personal destination. Project drafts remain unsaved; no launch.")
            if changed_directory:
                draft["message"] += " Directory identity changed; review the resolved personal destination before Apply preference."
            draft["proposal_revision"] = self._revision(draft)
            return draft
        if reply == "apply preference" and draft.get("step") == "preference_preview":
            return self._apply_preference(draft)
        if reply == "back":
            if draft.get("step") == "preference_preview":
                draft["personal"]["after"] = deepcopy(draft["personal"]["before"])
            return self._preview(draft)
        if reply == "edit skills":
            draft.update(step="skill_job", choices=["Edit skills " + job for job in draft["skill_after"]["jobs"]] + ["Back", "Not now"])
            return self._seal(draft)
        if reply.startswith("edit skills "):
            job = reply[len("edit skills "):].replace(" ", "_")
            if job not in draft["skill_after"]["jobs"]:
                raise ConfigError("Choose alignment, specification, implementation, code review or application QA.")
            draft.update(step="skill", edit_job=job, skill_options=deepcopy(draft["skill_alternatives"][job]),
                         choices=["Choose " + str(index + 1) for index in range(len(draft["skill_alternatives"][job]))] + ["Back", "Reload", "Not now"],
                         message="Choose a source-labelled route by number. Alignment permits ordered comma-separated adapter choices. Source labels are attribution, not authority.")
            return self._seal(draft)
        if draft.get("step") == "skill" and (reply.startswith("choose ") or reply.isdigit()):
            raw = reply[len("choose "):] if reply.startswith("choose ") else reply
            parts = raw.split(",")
            if any(not part.strip().isdigit() for part in parts):
                raise ConfigError("Choose displayed numbers separated by commas, in invocation order.")
            indexes = [int(part.strip()) - 1 for part in parts]
            if any(not 0 <= index < len(draft["skill_options"]) for index in indexes):
                raise ConfigError("Choose only a displayed eligible skill or explicit fallback.")
            job = draft["edit_job"]
            draft["skill_after"]["jobs"][job] = [deepcopy(draft["skill_options"][index]["binding"]) for index in indexes]
            self._bindings().resolve(draft["skill_after"], job)
            if job not in draft["edited_jobs"]:
                draft["edited_jobs"].append(job)
            return self._preview(draft)
        if reply.startswith("explain skills "):
            from skill_bindings import JOBS
            job = reply[len("explain skills "):].replace(" ", "_")
            if job not in JOBS:
                raise ConfigError("Explain skills requires a named Playbook job.")
            draft["explanation"] = {"job": job, "contract": deepcopy(JOBS[job]),
                                    "choices": deepcopy(draft["skill_alternatives"][job]),
                                    "rejections": deepcopy(draft["skill_rejections"]),
                                    "limitations": "Exact-source contract evidence, not installation or a warning acknowledgement, establishes eligibility. No candidate executes during configuration."}
            return self._seal(draft)
        if reply == "edit":
            draft.update(step="role", choices=[str(index + 1) + " " + ROLE_LABELS[role] for index, role in enumerate(ROLES)] + ["Edit skills", "Back", "Not now"])
            return self._seal(draft)
        if reply.isdigit() and draft.get("step") == "role":
            index = int(reply) - 1
            if not 0 <= index < len(ROLES):
                return self._blocked("Invalid role; reload and choose Plan, Build, Verify or Repair.")
            reply = "edit " + ROLE_LABELS[ROLES[index]].lower()
        role = next((role for role in ROLES if reply in {"edit " + role, "edit " + role.replace("_", " "), "edit " + ROLE_LABELS[role].lower()}), None)
        if role:
            draft["edit_role"] = role
            draft["alternatives"] = draft["role_alternatives"][role]
            draft.update(step="edit", state="decision_required", choices=[str(index + 1) for index in range(len(draft["alternatives"]))] + ["Pick model", "Back", "Reload", "Not now"])
            draft["message"] = "Choose a verified " + ROLE_LABELS[role] + " route by number. Availability is not suitability or cost evidence." if draft["alternatives"] else "No verified route is available; rediscover and Reload, or Not now."
            return self._seal(draft)
        if reply == "pick model" and draft.get("step") == "edit":
            return self._component(draft, "model")
        if reply.isdigit() and draft.get("step") in {"model", "runner", "reasoning", "identity"}:
            index = int(reply) - 1
            if not 0 <= index < len(draft["options"]):
                return self._blocked("Invalid editor choice; reload and select a displayed number.")
            step = draft["step"]
            if step == "identity":
                return self._select(draft, draft["component_routes"][index])
            key = {"model": "model_id", "runner": "runner", "reasoning": "reasoning"}[step]
            draft["component_selection"][key] = draft["options"][index]
            if step != "reasoning":
                return self._component(draft, "runner" if step == "model" else "reasoning")
            eligible = self._component_routes(draft)
            if len(eligible) == 1:
                return self._select(draft, eligible[0])
            draft.update(step="identity", component_routes=eligible, options=eligible,
                         choices=[str(index + 1) for index in range(len(eligible))] + ["Back", "Not now"],
                         message="Several verified identities share these settings; choose the complete identity explicitly.")
            return self._seal(draft)
        if reply.isdigit() and draft.get("step") == "edit":
            index = int(reply) - 1
            if not 0 <= index < len(draft["alternatives"]):
                return self._blocked("Invalid choice; edit Build or reload the proposal.")
            return self._select(draft, draft["alternatives"][index])
        if reply == "explain" or reply.startswith("explain "):
            role = "implementation" if reply == "explain" else next((role for role in ROLES if reply[8:] in {role, role.replace("_", " "), ROLE_LABELS[role].lower()}), None)
            if role is None:
                return self._blocked("Explain Plan, Build, Verify or Repair; QA inherits Verify and Coordinator is display-only.")
            draft["explanation"] = {"role": role, "choice": deepcopy(draft["after"][role]),
                                    "available": {key: value for key, value in draft["after"][role].items() if key in IDENTITY} in draft["role_alternatives"][role],
                                    "authority": draft["discovery"]["authority"], "checked_at": draft["discovery"]["checked_at"],
                                    "limitations": "Availability is a bounded observation, not live launch proof. Suitability, costs, access consumption and comparison evidence remain unknown. No recommendation or paid benchmark."}
            draft["message"] = draft["explanation"]["limitations"]
            return self._seal(draft)
        if reply == "apply" and draft.get("step") in {"read", "preview"}:
            return self.apply(draft)
        return self._blocked("Use the typed choices shown; reload if the draft is stale.")

    def _component_routes(self, draft):
        return [route for route in draft["role_alternatives"][draft["edit_role"]]
                if all(route[key] == value for key, value in draft["component_selection"].items())]

    def _component(self, draft, step):
        if step == "model":
            draft["component_selection"] = {}
        key = {"model": "model_id", "runner": "runner", "reasoning": "reasoning"}[step]
        options = list(dict.fromkeys(route[key] for route in self._component_routes(draft)))
        draft.update(step=step, options=options, choices=[str(index + 1) for index in range(len(options))] + ["Back", "Reload", "Not now"],
                     message="Choose " + step + " by number from verified routes; no substitutions.")
        return self._seal(draft)

    def _select(self, draft, choice):
        role = draft["edit_role"]
        previous = draft["after"][role]
        draft["after"][role] = {**{key: value for key, value in previous.items() if key not in IDENTITY}, **choice}
        if role not in draft["edited_roles"]:
            draft["edited_roles"].append(role)
        return self._preview(draft)

    def _preview(self, draft):
        changed_directory = self._refresh_personal_destination(draft)
        draft.update(step="preview", state="proposal_ready")
        self._present(draft)
        if changed_directory:
            draft["message"] = "Directory identity changed; review the resolved personal destination. Role drafts are retained."
        draft["proposal_revision"] = self._revision(draft)
        return draft

    def _apply_preference(self, draft):
        saved = False
        try:
            self._guard_write()
            if self.preferences is None or draft["personal"]["destination"] != str(self.preferences.path):
                raise ConfigError("Personal destination changed; reload and preview the local destination.")
            before, inputs = self.preferences.snapshot()
            if before != draft["personal"]["before"] or inputs != draft["personal"]["inputs"]:
                raise ConfigError("Personal preferences or runtime changed since preview; reload without overwriting them.")
            self.preferences._validate_candidate(draft["personal"]["after"])
            if before != draft["personal"]["after"]:
                self.preferences._save(draft["personal"]["after"], inputs, draft["discovery"], create_directory=True)
                saved = True
            draft["personal"] = self._personal_snapshot()
            draft["message"] = "Local presentation saved and validated. Project draft remains unsaved; no model launches."
            return self._preview(draft)
        except (ConfigError, OSError, UnicodeError, KeyError, TypeError) as error:
            if saved:
                error = ConfigError(f"Personal save completed at {draft['personal']['resolved_destination']}, but its destination could not be revalidated ({error}). Inspect that location before retrying; the project draft remains unsaved.")
            return self._blocked(error)

    def apply(self, proposal):
        try:
            self._guard_write()
            if proposal.get("proposal_revision") != self._revision(proposal):
                raise ConfigError("Proposal changed outside the editor; reload and preview before Apply.")
            if proposal["bootstrap"]["required"]:
                raise ConfigError("New project setup must use the existing bootstrap approval gate first; no second bootstrap or unspecified writes.")
            if proposal["missing_context"]:
                raise ConfigError("Answer only the displayed missing context/preferences before project Apply.")
            if self._personal_snapshot() != proposal["personal"]:
                raise ConfigError("Personal preferences changed since preview; reload and review them.")
            config, _, inputs = self._snapshot()
            routes, evidence = self._available()
            if inputs != proposal.get("inputs") or config["models"] != proposal.get("before"):
                raise ConfigError("Inputs changed since preview; reload and review the new proposal.")
            candidate = validate_config({"schema_version": 1, "adopted": True, "models": deepcopy(proposal["after"])})
            if proposal["skills_adopted"] or proposal["edited_jobs"]:
                starting = config.get("skills", self._bindings().defaults())
                if starting != proposal["skill_before"]:
                    raise ConfigError("Skill inputs changed since preview; reload without replacing intentional choices.")
                candidate["skills"] = deepcopy(proposal["skill_after"])
                validate_config(candidate)
                for job in candidate["skills"]["jobs"]:
                    self._bindings().resolve(candidate["skills"], job)
                    if self._bindings().options(job) != proposal["skill_alternatives"][job]:
                        raise ConfigError("Skill eligibility evidence changed; reload and explicitly review the new routes.")
            constraints = lambda choice: {key: value for key, value in choice.items() if key not in IDENTITY}
            for role in ROLES:
                choice = candidate["models"][role]
                if constraints(choice) != constraints(config["models"][role]):
                    raise ConfigError("Role constraints are not editable preferences; reload without changing them.")
                if (role == "implementation" and not proposal["edited_roles"]) or role in proposal["edited_roles"] or choice != config["models"][role]:
                    identity = {key: value for key, value in choice.items() if key in IDENTITY}
                    if identity not in routes[role]:
                        raise ConfigError(ROLE_LABELS[role] + " choice is unavailable; edit the role and review again. No substitution.")
            if self._discovery_revision(evidence) != self._discovery_revision(proposal["discovery"]):
                raise ConfigError("Discovery changed since preview; reload and review current available choices.")
            if not proposal["migration"] and candidate == config:
                return {"state": "unchanged", "destination": DESTINATION, "message": "Already adopted; no write needed.", "launched": False}
            if self.preferences is not None:
                self.preferences._expected_directory = proposal["personal"]["inputs"]["directories"]
            try:
                self._save(candidate, inputs, evidence)
            finally:
                if self.preferences is not None:
                    self.preferences._expected_directory = None
            return {"state": "applied", "destination": DESTINATION, "message": "Project defaults saved and validated. Runtime records unchanged. No build starts.", "launched": False}
        except (ConfigError, OSError, UnicodeError, KeyError, TypeError) as error:
            return self._blocked(error)

    def _save(self, candidate, inputs, evidence, create_directory=False):
        self._guard_write()
        if create_directory:
            self.project.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._open(self.lock, "x"):
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
            if digest(previous) != inputs[self.destination]:
                raise ConfigError("Configuration changed before staging; reload without overwriting it.")
            if previous is not None:
                backup = self._stage(previous)
                captured_path = self._stage(b"")
            staged = self._stage(candidate_bytes)
            publication = self._stage(candidate_bytes)
            self.checkpoint("staged")
            self._guard_write(active=True)
            self._validate_candidate(strict_json(self._bytes(staged).decode()))
            self.checkpoint("before_replace")
            self._guard_write(active=True)
            self._check_inputs(inputs)
            _, current_evidence = self._available()
            if self._discovery_revision(current_evidence) != self._discovery_revision(evidence):
                raise ConfigError("Availability evidence changed before save; reload and review current choices.")
            self._guard_write(active=True)
            marker = {"destination": self.destination, "previous": backup.name if backup else None,
                      "captured": captured_path.name if captured_path else None,
                      "attempted": staged.name, "attempted_digest": digest(candidate_bytes),
                      "published": publication.name,
                      "previous_digest": inputs[self.destination],
                      "runtime_digest": inputs[".playbook-state.yml"], "completion_protocol": 3}
            with self._open(self.recovery, "x") as stream:
                stream.write(encoded(marker).decode())
                stream.flush()
                os.fsync(stream.fileno())
            journaled = True
            self._sync_directory()
            self._guard_write(active=True)
            if backup is not None:
                self._replace(self.path, captured_path)
                captured = True
                self._sync_directory()
                if digest(self._bytes(captured_path)) != inputs[self.destination]:
                    raise ConfigError("Concurrent configuration captured intact; reconcile recovery before continuing.")
            self.checkpoint("before_publish")
            self._guard_write(active=True)
            try:
                self._link(publication, self.path)
            except FileExistsError as error:
                raise ConfigError("Destination changed during publication; external file retained, reload or reconcile recovery.") from error
            committed = True
            self.checkpoint("committed")
            self._guard_write(active=True)
            actual = self._bytes(self.path)
            if actual != candidate_bytes:
                raise ConfigError("Saved configuration changed during validation; recovery is required.")
            self._validate_candidate(strict_json(actual.decode()))
            if digest(self._bytes(self.state_path)) != inputs[".playbook-state.yml"]:
                raise ConfigError("Runtime inputs changed during Apply; retained defaults require reconciliation.")
            if captured_path is not None and digest(self._bytes(captured_path)) != inputs[self.destination]:
                raise ConfigError("Captured configuration changed during Apply; retained bytes require reconciliation.")
            self._sync_directory()
            receipt = self.project / (staged.name + ".receipt")
            self._replace(self.recovery, receipt)
            journaled = False
            self._sync_directory()
            self.checkpoint("before_completion")
            self._guard_write(active=True)
            self._receipt_conflicts(receipt, marker, completing=True)
            seal = receipt.with_name(receipt.name + ".complete")
            self._mkdir(seal)
            completed = True
        except (OSError, ConfigError, UnicodeError) as error:
            if committed or captured:
                recover = True
                if receipt is not None and self._exists(receipt):
                    try:
                        self._mkdir(receipt.with_name(receipt.name + ".conflict"), exist_ok=True)
                        self._sync_directory()
                    except OSError:
                        pass
                if not self._exists(self.recovery) and receipt is not None:
                    try:
                        self._link(receipt, self.recovery)
                    except OSError:
                        pass
                try:
                    self.checkpoint("rollback")
                    self._bytes(self.path)
                    if not committed and captured_path is not None:
                        try:
                            self._link(captured_path, self.path)
                        except FileExistsError:
                            pass
                    self._sync_directory()
                except (OSError, ConfigError):
                    pass
                raise RecoveryRequired(f"Save incomplete ({error}); no destructive rollback attempted. Reconcile {self.recovery.name} and retained files before continuing.") from error
            if journaled:
                self._unlink(self.recovery)
                self._sync_directory()
            raise
        finally:
            if publication is not None and not committed and not recover:
                self._unlink(publication, missing_ok=True)
            if staged is not None and not recover and not completed:
                self._unlink(staged, missing_ok=True)
            if backup is not None and not captured and not recover:
                self._unlink(backup, missing_ok=True)
            if captured_path is not None and not captured and not recover:
                self._unlink(captured_path, missing_ok=True)
            if not recover:
                self._unlink(self.lock)

    def _check_inputs(self, inputs):
        if digest(self._bytes(self.path)) != inputs[self.destination] or digest(self._bytes(self.state_path)) != inputs[".playbook-state.yml"]:
            raise ConfigError("Inputs changed before save; reload without overwriting them.")

    def _stage(self, data):
        staged = None
        try:
            if self._directory_fd is None:
                stream = tempfile.NamedTemporaryFile(dir=self.project, prefix=".playbook-config-", delete=False)
                staged = Path(stream.name)
            else:
                destination = self.project / (".playbook-config-" + uuid.uuid4().hex)
                stream = self._open(destination, "xb")
                staged = destination
            with stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            return staged
        except OSError:
            if staged is not None:
                self._unlink(staged, missing_ok=True)
            raise

    def _sync_directory(self):
        if self._directory_fd is not None:
            os.fsync(self._directory_fd)
            return
        descriptor = os.open(self.project, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class LocalPreferences(Configuration):
    def __init__(self, directory, discover, clock, checkpoint):
        super().__init__(directory, discover, clock, checkpoint)
        self.destination = "preferences.json"
        self.path = self.project / self.destination
        self.owner_project = None
        self._expected_directory = None

    def _directory_identity(self, path):
        resolved = path.resolve()
        anchor = resolved
        while not anchor.exists():
            anchor = anchor.parent
        info = anchor.stat()
        if not stat.S_ISDIR(info.st_mode):
            raise ConfigError("Personal storage requires a directory; reconcile its destination.")
        return {"resolved": str(resolved), "anchor": str(anchor), "device": info.st_dev, "inode": info.st_ino}

    def _directory_inputs(self):
        local = self._directory_identity(self.project)
        project = self._directory_identity(self.owner_project)
        if Path(local["resolved"]).is_relative_to(Path(project["resolved"])):
            raise ConfigError("Personal preferences require a user-local directory outside the project; reload and preview it explicitly.")
        return {"personal": local, "project": project}

    def _check_directory(self):
        current = self._directory_inputs()
        if self._expected_directory is not None and current != self._expected_directory:
            raise ConfigError("Personal or project directory changed since preview; reload and review the destination.")

    def _save(self, candidate, inputs, evidence, create_directory=False):
        self._guard_write()
        expected = inputs.get("directories")
        if self._directory_inputs() != expected:
            raise ConfigError("Personal or project directory changed since preview; reload and review the destination.")
        local = expected["personal"]
        anchor = Path(local["anchor"])
        descriptor = os.open(anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != (local["device"], local["inode"]) or self._directory_inputs() != expected:
                raise ConfigError("Personal directory changed while opening storage; reload and preview it again.")
            for name in Path(local["resolved"]).relative_to(anchor).parts:
                os.mkdir(name, mode=0o700, dir_fd=descriptor)
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            info = os.fstat(descriptor)
            self._expected_directory = deepcopy(expected)
            self._expected_directory["personal"].update(anchor=local["resolved"], device=info.st_dev, inode=info.st_ino)
            self._directory_fd = descriptor
            self._check_directory()
            super()._save(candidate, inputs, evidence)
        except (ConfigError, OSError) as error:
            error_type = RecoveryRequired if isinstance(error, RecoveryRequired) else ConfigError
            raise error_type(f"{error} Reviewed personal storage: {local['resolved']}; inspect retained files there before retrying.") from error
        finally:
            self._directory_fd = None
            self._expected_directory = None
            os.close(descriptor)

    def _validate_candidate(self, candidate):
        if (not isinstance(candidate, dict) or set(candidate) != {"schema_version", "presentation"}
                or type(candidate["schema_version"]) is not int or candidate["schema_version"] != 1
                or candidate["presentation"] not in {"guided", "expert"}):
            raise ConfigError("Unsupported local presentation preferences; reconcile without dropping other personal settings.")
        return candidate

    def snapshot(self):
        directories = self._directory_inputs()
        if self.lock.exists() or self.recovery.exists():
            raise RecoveryRequired("Local preferences transaction/recovery pending; reconcile its retained evidence.")
        self._reconcile_receipts()
        saved = self._bytes(self.path)
        runtime = self._bytes(self.state_path)
        candidate = self._validate_candidate(strict_json(saved.decode())) if saved is not None else None
        if self.lock.exists() or self.recovery.exists():
            raise RecoveryRequired("Local preferences changed during read; reconcile recovery.")
        self._reconcile_receipts()
        if self._directory_inputs() != directories:
            raise ConfigError("Personal or project directory changed during preview; reload and review its destination.")
        return candidate, {self.destination: digest(saved), ".playbook-state.yml": digest(runtime), "directories": directories}

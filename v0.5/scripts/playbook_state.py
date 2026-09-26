"""Shared parsing and editing primitives for playbook state files.

Single home for the hand-rolled `.playbook-state.yml` / `playbook-cadences.yml`
text handling that `compute-status.py` and `upgrade-project.py` previously each
maintained. Deliberately stdlib-only: projects consume these scripts without a
YAML dependency.

Two layers:

- **Typed parsing** (`parse_scalar`, `parse_top_level_map`,
  `parse_top_level_list`, …) — values become int/bool/float/str/None with
  quote-aware inline-comment stripping. Used by status computation, where
  thresholds and counters must be numbers.
- **Raw text handling** (`parse_top_level_list_raw`, `top_level_scalar_value`,
  `replace_top_level_scalar`, `insert_before`, `insert_after_line`) — values
  stay strings and edits are position-preserving. Used by the safe migrator,
  which must rewrite user files without reformatting anything it didn't touch.

Phase 2 also unified list parsing: the migrator previously used a raw variant
whose regex silently DROPPED any field whose line contained a `#` (comment or
not, even inside quotes). Both scripts now share the quote-aware typed
`parse_top_level_list`, and `validate_state`/`validate_cadences` provide the
schema layer — type/enum checks on known fields with line numbers and
remedies, never complaints about unknown customized fields.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, NamedTuple


# ------------------------------------------------------------ typed parsing

def strip_inline_comment(value: str) -> str:
    """Remove a YAML inline comment without mistaking quoted content for one."""
    quote: str | None = None
    index = 0
    while index < len(value):
        character = value[index]
        if quote == '"':
            if character == "\\":
                index += 2
                continue
            if character == '"':
                quote = None
        elif quote == "'":
            if character == "'" and index + 1 < len(value) and value[index + 1] == "'":
                index += 2
                continue
            if character == "'":
                quote = None
        elif character in {"'", '"'}:
            quote = character
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].strip()
        index += 1
    return value.strip()


def parse_scalar(raw: str) -> Any:
    value = strip_inline_comment(raw)
    if value in {"", "null", "Null", "NULL", "~"}:
        return None
    if value == "[]":
        return []
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        inner = value[1:-1]
        if value[0] == '"':
            inner = re.sub(r'\\(["\\])', r"\1", inner)
        return inner
    if value in {"true", "True", "TRUE"}:
        return True
    if value in {"false", "False", "FALSE"}:
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_datetime(value: Any) -> datetime | None:
    # ``parse_scalar`` represents a YAML empty list as ``[]``.  Do not let an
    # unhashable malformed timestamp make state/status checking crash: callers
    # need ``None`` so they can surface a typed, actionable configuration error.
    if value is None or value == "":
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1] + "+00:00")
        if "T" in text:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        return datetime.combine(date.fromisoformat(text), datetime.min.time(), timezone.utc)
    except ValueError:
        return None


def parse_top_level_map(text: str, block_name: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    in_block = False
    header = re.compile(rf"^{re.escape(block_name)}:\s*(?:#.*)?$")
    for line in text.splitlines():
        if header.match(line):
            in_block = True
            continue
        if not in_block:
            continue
        # YAML comments do not change a mapping's indentation scope.  Preserve
        # unindented local comments between a mapping header and its fields;
        # the position-preserving editor relies on this parser seeing the same
        # block as validation does.
        if not line or line.startswith("#"):
            continue
        if not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            values[match.group(1)] = parse_scalar(match.group(2))
    return values


def parse_top_level_list(text: str, block_name: str) -> list[dict[str, Any]]:
    inline = re.search(rf"^{re.escape(block_name)}:\s*\[\]\s*$", text, re.M)
    if inline:
        return []

    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    in_block = False
    header = re.compile(rf"^{re.escape(block_name)}:\s*(?:#.*)?$")
    for line in text.splitlines():
        if header.match(line):
            in_block = True
            continue
        if not in_block:
            continue
        if not line or line.startswith("#"):
            continue
        if not line.startswith(" "):
            break
        item_match = re.match(r"^  - ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if item_match:
            current = {item_match.group(1): parse_scalar(item_match.group(2))}
            items.append(current)
            continue
        field_match = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if field_match and current is not None:
            current[field_match.group(1)] = parse_scalar(field_match.group(2))
    return items


def quote_yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ------------------------------------------------------------ raw text handling

def replace_top_level_scalar(text: str, key: str, value: str) -> str:
    pattern = rf"(?m)^{re.escape(key)}:\s*[^\n]*(?:\n|$)"
    replacement = f"{key}: {value}\n"
    if re.search(pattern, text):
        return re.sub(pattern, replacement, text, count=1)
    return text


def top_level_scalar_value(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*([^\n#]*?)\s*(?:#.*)?$", text)
    return match.group(1) if match else None


def insert_before(text: str, marker: str, addition: str) -> tuple[str, bool]:
    if marker not in text:
        return text, False
    return text.replace(marker, addition + marker, 1), True


def insert_after_line(text: str, anchor_pattern: str, line: str) -> tuple[str, bool]:
    if line in text:
        return text, True
    match = re.search(anchor_pattern, text, re.M)
    if not match:
        return text, False
    insertion = match.end()
    return text[:insertion] + "\n" + line + text[insertion:], True


# ------------------------------------------------------------ schema validation

class ValidationProblem(NamedTuple):
    line: int | None
    path: str
    message: str
    remedy: str
    advisory: bool = False   # true = worth surfacing but never fails a check
                             # (e.g. a key that is documented as ignored)

    def render(self) -> str:
        location = f"line {self.line}: " if self.line else ""
        return f"{location}{self.path}: {self.message} — {self.remedy}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_bool_or_null(value: Any) -> bool:
    return value is None or isinstance(value, bool)


def _is_str_or_null(value: Any) -> bool:
    return value is None or isinstance(value, str)


def _is_datetime_or_null(value: Any) -> bool:
    return value is None or parse_datetime(value) is not None


def _enum_or_null(*allowed: str) -> Callable[[Any], bool]:
    return lambda value: value is None or value in allowed


# Field specs: name -> (predicate, expectation shown in the remedy).
_STATE_TOP_FIELDS = {
    "schema_version": (_is_int, "an integer"),
    "last_updated": (_is_datetime_or_null, "null or an ISO 8601 timestamp"),
    "playbook_version": (
        lambda v: v is None or (isinstance(v, str) and re.fullmatch(r"V\d+\.\d+\.\d+", v)),
        'null or a version string such as "V0.5.0"',
    ),
    "last_upgraded": (_is_datetime_or_null, "null or an ISO 8601 date"),
    "prereqs_required": (_is_bool_or_null, "true or false"),
}
_STATUS_FIELDS = {
    "computed_at": (_is_datetime_or_null, "null or an ISO 8601 timestamp"),
    "headline": (_is_str_or_null, "null or a one-line string"),
    "pending_plan_routes": (_is_int, "an integer"),
    "pending_closeouts": (_is_int, "an integer"),
}
_DECISIONS_FIELDS = {
    "no_ui": (_is_bool_or_null, "null, true, or false"),
    "graduated_from_lite": (_is_datetime_or_null, "null or a YYYY-MM-DD date"),
    "capability_profile": (_enum_or_null("core", "accelerated", "extended"),
                           "null, core, accelerated, or extended"),
    "technical_decisions": (_enum_or_null("ask", "auto_recommend"),
                            "null, ask, or auto_recommend"),
    "verification_harness_path": (
        lambda value: value is None or is_canonical_relative_path(value),
        "null or one canonical, safe project-relative harness directory",
    ),
    "verification_harness_binding": (
        lambda value: value is None or is_canonical_relative_path(value),
        "null or one canonical, safe project-relative harness directory bound by the selection transition",
    ),
    "verification_map_maintenance": (lambda value: isinstance(value, bool), "true or false"),
}
# Keys upgrade-project.py adds when moving a project to schema 3; their absence
# means the migration has not run (or was hand-reverted).
_SCHEMA3_REQUIRED_KEYS = (
    "status", "playbook_version", "decisions", "counters", "last_run",
    "pending_closeouts", "pending_model_routes", "delivery_missions", "active_wayfinding_maps",
    "active_features", "prereqs_required",
)
_LIST_ENTRY_REQUIRED = {
    "active_features": ("slug", "status"),
    "pending_model_routes": ("route_id", "status"),
    "delivery_missions": ("mission_id", "locator", "authority_class", "status"),
    "pending_closeouts": ("feature_slug",),
    "active_wayfinding_maps": ("title", "locator"),
}
_CADENCE_TYPES = {"count", "time", "event"}
_SEVERITIES = {"nudge", "insist"}


def _top_level_blocks(text: str) -> dict[str, dict]:
    """{key: {"line": n, "inline": raw-inline-value, "lines": [(n, line), ...]}}"""
    blocks: dict[str, dict] = {}
    current: dict | None = None
    for number, line in enumerate(text.splitlines(), 1):
        if line and not line.startswith((" ", "#")):
            match = re.match(r"^([A-Za-z0-9_-]+):(.*)$", line)
            if match:
                current = {"line": number, "inline": match.group(2), "lines": []}
                blocks[match.group(1)] = current
            else:
                current = None
            continue
        if current is not None:
            current["lines"].append((number, line))
    return blocks


def _map_fields(block: dict, indent: str = "  ") -> list[tuple[int, str, Any]]:
    fields = []
    for number, line in block["lines"]:
        match = re.match(rf"^{indent}([A-Za-z0-9_-]+):\s*(.*)$", line)
        if match:
            fields.append((number, match.group(1), parse_scalar(match.group(2))))
    return fields


def _list_entries(block: dict) -> list[dict]:
    """[{"line": n, "fields": {name: (line, value)}}] for two-level list items."""
    entries: list[dict] = []
    current: dict | None = None
    for number, line in block["lines"]:
        item = re.match(r"^  - ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if item:
            current = {"line": number,
                       "fields": {item.group(1): (number, parse_scalar(item.group(2)))}}
            entries.append(current)
            continue
        field = re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if field and current is not None:
            current["fields"][field.group(1)] = (number, parse_scalar(field.group(2)))
    return entries


def _check_fields(blocks: dict, block_name: str, specs: dict,
                  problems: list[ValidationProblem]) -> None:
    block = blocks.get(block_name)
    if block is None:
        return
    for number, key, value in _map_fields(block):
        if key not in specs:
            continue  # customization is allowed; only known fields are typed
        predicate, expectation = specs[key]
        if not predicate(value):
            problems.append(ValidationProblem(
                number, f"{block_name}.{key}", f"got {value!r}", f"expected {expectation}"))


def is_canonical_relative_path(value: object) -> bool:
    """Return whether a managed path is portable, traversal-free, and YAML-safe.

    These paths are persisted as scalars in a hand-preserving YAML document.
    Keep their spelling deliberately narrower than what a filesystem accepts so
    that a caller cannot turn a scalar replacement into YAML structure.
    """
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or value != value.strip()
        or any(not char.isprintable() for char in value)
    ):
        return False
    # Colons are not portable Windows filename characters; the remaining
    # characters are YAML indicators that would need quoting or can change the
    # meaning of a scalar in the text-preserving editor.
    if any(char in "#:[]{}&,*!|>'\"%@`" for char in value):
        return False
    if value.startswith(("- ", "? ")):
        return False
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return False
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    return (
        not posix.is_absolute()
        and not windows.is_absolute()
        and not windows.drive
        and posix.as_posix() == value
    )


def validate_template_provenance(text: str) -> list[ValidationProblem]:
    """Validate the machine-owned, three-level provenance block.

    Unlike ordinary project state, unknown fields are errors here: bootstrap
    and upgrade rewrite this block wholesale, so accepting an unknown key would
    silently discard it on the next run.
    """
    provenance_headers = [
        number for number, line in enumerate(text.splitlines(), 1)
        if re.match(r"^template_provenance:", line)
    ]
    block = _top_level_blocks(text).get("template_provenance")
    if block is None:
        return []

    problems: list[ValidationProblem] = []
    if len(provenance_headers) > 1:
        problems.append(ValidationProblem(
            provenance_headers[1], "template_provenance",
            "duplicate machine-owned block",
            "keep exactly one validated template_provenance block"))
    if strip_inline_comment(block["inline"]):
        problems.append(ValidationProblem(
            block["line"], "template_provenance",
            f"got inline value {block['inline'].strip()!r}",
            "expected an indented machine-owned map"))
    allowed_headers = {"schema", "project_name", "files"}
    required_headers = {"schema", "files"}
    seen_headers: dict[str, int] = {}
    entries: dict[str, dict] = {}
    current_file: str | None = None
    skip_duplicate_file = False
    in_files = False

    for number, line in block["lines"]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        header = re.match(r"^  ([A-Za-z0-9_-]+):\s*(.*)$", line)
        if header:
            key, raw = header.groups()
            current_file = None
            skip_duplicate_file = False
            in_files = key == "files"
            if key in seen_headers:
                problems.append(ValidationProblem(
                    number, f"template_provenance.{key}",
                    "duplicate machine-owned field",
                    "keep exactly one occurrence of this field"))
            seen_headers[key] = number
            if key not in allowed_headers:
                problems.append(ValidationProblem(
                    number, f"template_provenance.{key}", "unknown machine-owned field",
                    "remove it or migrate the provenance schema explicitly"))
                continue
            value = parse_scalar(raw)
            if key == "schema" and value != 1:
                problems.append(ValidationProblem(
                    number, "template_provenance.schema", f"got {value!r}",
                    "expected integer 1"))
            elif key == "project_name":
                stripped = raw.strip()
                malformed_quote = False
                if stripped.startswith('"'):
                    try:
                        malformed_quote = not isinstance(json.loads(stripped), str)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        malformed_quote = True
                elif stripped.startswith("'"):
                    malformed_quote = len(stripped) < 2 or not stripped.endswith("'")
                elif stripped.endswith(('"', "'")):
                    malformed_quote = True
                if malformed_quote:
                    problems.append(ValidationProblem(
                        number, "template_provenance.project_name",
                        "malformed quoted string",
                        "restore a balanced YAML-safe quoted project name"))
                elif not isinstance(value, str) or not value:
                    problems.append(ValidationProblem(
                        number, "template_provenance.project_name", f"got {value!r}",
                        "expected a non-empty quoted string"))
                elif not raw.lstrip().startswith(("\"", "'")) and (
                    ": " in raw or "#" in raw
                ):
                    problems.append(ValidationProblem(
                        number, "template_provenance.project_name",
                        "YAML punctuation is not quoted",
                        "quote the project name so ':' and '#' remain data"))
            elif key == "files" and raw.strip():
                problems.append(ValidationProblem(
                    number, "template_provenance.files", f"got inline value {raw.strip()!r}",
                    "expected an indented managed-file map"))
            continue

        file_key = re.match(r"^    (\S+):\s*$", line)
        if file_key:
            if not in_files:
                problems.append(ValidationProblem(
                    number, "template_provenance.files",
                    "managed-file entry appears before template_provenance.files",
                    "place every managed-file entry under the files map"))
                current_file = None
                continue
            current_file = file_key.group(1)
            skip_duplicate_file = current_file in entries
            if skip_duplicate_file:
                problems.append(ValidationProblem(
                    number, f"template_provenance.files[{current_file}]",
                    "duplicate managed-file entry",
                    "keep exactly one provenance entry for this path"))
                current_file = None
                continue
            entries[current_file] = {"line": number, "fields": {}}
            continue

        field = re.match(r"^      ([a-z_0-9]+):\s*(.*)$", line)
        if field and skip_duplicate_file:
            continue
        if field and current_file is not None:
            key, raw = field.groups()
            if key in entries[current_file]["fields"]:
                problems.append(ValidationProblem(
                    number,
                    f"template_provenance.files[{current_file}].{key}",
                    "duplicate machine-owned field",
                    "keep exactly one occurrence of this field"))
                continue
            entries[current_file]["fields"][key] = (number, parse_scalar(raw))
            continue

        problems.append(ValidationProblem(
            number, "template_provenance", f"malformed line {line!r}",
            "restore the machine-owned block or re-run the approved upgrade"))

    for key in required_headers:
        if key not in seen_headers:
            problems.append(ValidationProblem(
                block["line"], f"template_provenance.{key}", "required field is missing",
                "restore it from the current provenance schema"))

    allowed_entry_fields = {"template", "version", "base_sha256"}
    for relative, entry in entries.items():
        fields = entry["fields"]
        if not is_canonical_relative_path(relative):
            problems.append(ValidationProblem(
                entry["line"], f"template_provenance.files[{relative}]",
                f"non-canonical or unsafe managed path {relative!r}",
                "use one canonical project-relative path with no absolute, empty, dot, "
                "dot-dot, backslash, drive, or traversal component"))
        for key in fields:
            if key not in allowed_entry_fields:
                problems.append(ValidationProblem(
                    fields[key][0], f"template_provenance.files[{relative}].{key}",
                    "unknown machine-owned field",
                    "remove it or migrate the provenance schema explicitly"))
        for key in allowed_entry_fields:
            if key not in fields:
                problems.append(ValidationProblem(
                    entry["line"], f"template_provenance.files[{relative}].{key}",
                    "required field is missing", "restore it from the recorded base"))
        template = fields.get("template", (None, None))[1]
        if "template" in fields and (not isinstance(template, str) or not template):
            problems.append(ValidationProblem(
                fields["template"][0], f"template_provenance.files[{relative}].template",
                f"got {template!r}", "expected a non-empty playbook-relative path"))
        elif "template" in fields and not is_canonical_relative_path(template):
            problems.append(ValidationProblem(
                fields["template"][0], f"template_provenance.files[{relative}].template",
                f"non-canonical or unsafe template path {template!r}",
                "use one canonical playbook-relative path with no absolute, empty, dot, "
                "dot-dot, backslash, drive, or traversal component"))
        version = fields.get("version", (None, None))[1]
        if "version" in fields and not (
            isinstance(version, str) and re.fullmatch(r"V\d+\.\d+\.\d+", version)
        ):
            problems.append(ValidationProblem(
                fields["version"][0], f"template_provenance.files[{relative}].version",
                f"got {version!r}", 'expected a version such as "V0.5.0"'))
        digest = fields.get("base_sha256", (None, None))[1]
        if "base_sha256" in fields and not (
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            problems.append(ValidationProblem(
                fields["base_sha256"][0],
                f"template_provenance.files[{relative}].base_sha256",
                f"got {digest!r}", "expected 64 lowercase hexadecimal characters"))
    return problems


def validate_state(text: str) -> list[ValidationProblem]:
    """Type/enum problems on known fields, plus schema-3 required keys.

    Unknown extra fields are never reported — preserving customized content is
    a bootstrap/upgrade invariant. Required-key checks apply only at
    schema_version 3, so pre-migration (v0.1/v0.2) states validate quietly.
    """
    problems: list[ValidationProblem] = []
    blocks = _top_level_blocks(text)
    problems.extend(validate_template_provenance(text))

    for key, (predicate, expectation) in _STATE_TOP_FIELDS.items():
        block = blocks.get(key)
        if block is None:
            continue
        value = parse_scalar(block["inline"])
        if not predicate(value):
            problems.append(ValidationProblem(
                block["line"], key, f"got {value!r}", f"expected {expectation}"))

    schema_version = parse_scalar(blocks["schema_version"]["inline"]) \
        if "schema_version" in blocks else None
    if schema_version == 3:
        for key in _SCHEMA3_REQUIRED_KEYS:
            if key not in blocks:
                problems.append(ValidationProblem(
                    None, key, "required top-level key is missing",
                    "run /ai-playbook-upgrade-project to restore it"))

    _check_fields(blocks, "status", _STATUS_FIELDS, problems)
    _check_fields(blocks, "decisions", _DECISIONS_FIELDS, problems)

    counters = blocks.get("counters")
    if counters is not None:
        for number, key, value in _map_fields(counters):
            if not _is_int(value):
                problems.append(ValidationProblem(
                    number, f"counters.{key}", f"got {value!r}",
                    "expected an integer (count cadences read this)"))

    last_run = blocks.get("last_run")
    if last_run is not None:
        for number, key, value in _map_fields(last_run):
            if not _is_datetime_or_null(value):
                problems.append(ValidationProblem(
                    number, f"last_run.{key}", f"got {value!r}",
                    "expected null or an ISO 8601 timestamp (time cadences diff this)"))

    for block_name, required in _LIST_ENTRY_REQUIRED.items():
        block = blocks.get(block_name)
        if block is None:
            continue
        for index, entry in enumerate(_list_entries(block)):
            for field in required:
                value = entry["fields"].get(field, (None, None))[1]
                if value in (None, ""):
                    problems.append(ValidationProblem(
                        entry["line"], f"{block_name}[{index}].{field}",
                        "required entry field is missing or empty",
                        "fill it in or remove the entry"))
        if block_name == "pending_closeouts":
            for index, entry in enumerate(_list_entries(block)):
                for field in ("doc_close", "retro"):
                    if field in entry["fields"]:
                        number, value = entry["fields"][field]
                        if value not in ("pending", "complete"):
                            problems.append(ValidationProblem(
                                number, f"{block_name}[{index}].{field}",
                                f"got {value!r}", "expected pending or complete"))
    return problems


def validate_cadences(text: str) -> list[ValidationProblem]:
    problems: list[ValidationProblem] = []
    blocks = _top_level_blocks(text)
    if "cadences" not in blocks:
        problems.append(ValidationProblem(
            None, "cadences", "required top-level key is missing",
            "restore the cadences list from the template"))
        return problems

    seen_ids: dict[str, int] = {}
    for index, entry in enumerate(_list_entries(blocks["cadences"])):
        fields = entry["fields"]
        cadence_id = fields.get("id", (None, None))[1]
        label = f"cadences[{index}]" + (f" ({cadence_id})" if cadence_id else "")
        if not cadence_id:
            problems.append(ValidationProblem(
                entry["line"], label + ".id", "cadence has no id", "add a unique id"))
        elif cadence_id in seen_ids:
            problems.append(ValidationProblem(
                entry["line"], label + ".id",
                f"duplicate of line {seen_ids[cadence_id]}", "ids must be unique"))
        else:
            seen_ids[cadence_id] = entry["line"]

        cadence_type = fields.get("type", (None, None))[1]
        if cadence_type not in _CADENCE_TYPES:
            problems.append(ValidationProblem(
                entry["line"], label + ".type", f"got {cadence_type!r}",
                "expected count, time, or event"))
            continue

        thresholds = {}
        for key in ("nudge_threshold", "insist_threshold"):
            if key in fields:
                number, value = fields[key]
                if not _is_int(value):
                    problems.append(ValidationProblem(
                        number, f"{label}.{key}", f"got {value!r}", "expected an integer"))
                else:
                    thresholds[key] = value
        if len(thresholds) == 2 and thresholds["nudge_threshold"] > thresholds["insist_threshold"]:
            problems.append(ValidationProblem(
                entry["line"], label,
                f"nudge_threshold {thresholds['nudge_threshold']} exceeds "
                f"insist_threshold {thresholds['insist_threshold']}",
                "nudge must fire at or before insist"))

        if cadence_type in {"count", "time"}:
            counter = fields.get("counter", (None, None))[1]
            if not isinstance(counter, str) or not counter:
                problems.append(ValidationProblem(
                    entry["line"], label + ".counter", f"got {counter!r}",
                    "count/time cadences need a counter name"))
            if "severity" in fields:
                # Documented-as-ignored (V0.3.35), so advisory: real in older
                # bootstraps and harmless, but worth surfacing because someone
                # setting it usually expects it to take effect.
                problems.append(ValidationProblem(
                    fields["severity"][0], label + ".severity",
                    "severity on a count/time cadence is ignored",
                    "remove it; severity derives from the thresholds", advisory=True))
        else:  # event
            severity = fields.get("severity", (None, None))[1]
            if severity not in _SEVERITIES:
                problems.append(ValidationProblem(
                    entry["line"], label + ".severity", f"got {severity!r}",
                    "event cadences need severity: nudge or insist"))
            if not fields.get("trigger", (None, None))[1]:
                problems.append(ValidationProblem(
                    entry["line"], label + ".trigger", "event cadence has no trigger",
                    "name the observable condition"))
    return problems

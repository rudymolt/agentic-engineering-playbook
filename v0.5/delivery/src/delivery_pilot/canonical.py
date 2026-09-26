"""Strict parsing and RFC 8785-compatible canonical JSON for pilot records."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import PurePosixPath
from typing import Any


class CanonicalError(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise CanonicalError(f"non-finite number: {value}")


def _validate(value: Any, key: str | None = None) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise CanonicalError("non-finite number")
    if isinstance(value, dict):
        for child_key, child in value.items():
            if not isinstance(child_key, str):
                raise CanonicalError("object keys must be strings")
            _validate(child, child_key)
    elif isinstance(value, list):
        for child in value:
            _validate(child, key)
    elif isinstance(value, str) and key and (key.endswith("_ref") or key.endswith("_path") or key in {"ref", "path", "control_path"}):
        if value.startswith(("tracker:", "registry:", "artifact:", "secret-ref:", "refs/")):
            return
        if key == "path" and value.startswith("/") and ".." not in value.split("/"):
            # JSON Pointer paths are absolute within their record, not host paths.
            return
        candidate = PurePosixPath(value)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise CanonicalError(f"path traversal in {key}")


def load_strict(raw: bytes | str) -> Any:
    """Parse the pilot's strict JSON subset of YAML.

    Persisted ``.yml`` files are emitted as JSON, which is valid YAML 1.2. This
    deliberately keeps one dependency-free parser and makes duplicate-key and
    canonicalization behavior identical for YAML- and JSON-named records.
    """

    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            value = json.loads(
                text,
                object_pairs_hook=_pairs,
                parse_constant=_reject_constant,
            )
        else:
            value = _load_yaml_subset(text)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise CanonicalError(str(exc)) from exc
    _validate(value)
    return value


def _commentless(line: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
        elif char in {"'", '"'}:
            quote = None if quote == char else (char if quote is None else quote)
        elif char == "#" and quote is None and (index == 0 or line[index - 1].isspace()):
            return line[:index]
    return line


def _split_flow(value: str, separator: str) -> list[str]:
    result: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote == '"':
            escaped = True
        elif char in {"'", '"'}:
            quote = None if quote == char else (char if quote is None else quote)
        elif quote is None:
            if char in "[{":
                depth += 1
            elif char in "]}":
                depth -= 1
            elif char == separator and depth == 0:
                result.append(value[start:index].strip())
                start = index + 1
    result.append(value[start:].strip())
    return result


def _flow_key(value: str) -> str:
    parsed = _scalar(value)
    if not isinstance(parsed, str) or not parsed:
        raise CanonicalError("YAML mapping keys must be non-empty strings")
    return parsed


def _scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        raise CanonicalError("missing YAML scalar")
    if value.startswith("&") or value.startswith("*") or value.startswith("!"):
        raise CanonicalError("YAML anchors, aliases, and tags are forbidden")
    if value.startswith("["):
        if not value.endswith("]"):
            raise CanonicalError("unterminated flow sequence")
        inner = value[1:-1].strip()
        return [] if not inner else [_scalar(item) for item in _split_flow(inner, ",")]
    if value.startswith("{"):
        if not value.endswith("}"):
            raise CanonicalError("unterminated flow mapping")
        inner = value[1:-1].strip()
        result: dict[str, Any] = {}
        if not inner:
            return result
        for item in _split_flow(inner, ","):
            pair = _split_flow(item, ":")
            if len(pair) != 2:
                raise CanonicalError("flow mapping entry must contain one colon")
            key = _flow_key(pair[0])
            if key in result:
                raise CanonicalError(f"duplicate key: {key}")
            result[key] = _scalar(pair[1])
        return result
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise CanonicalError(str(exc)) from exc
    if value.startswith("'"):
        if not value.endswith("'"):
            raise CanonicalError("unterminated single-quoted scalar")
        return value[1:-1].replace("''", "'")
    lowered = value.lower()
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        return int(value)
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)\.[0-9]+(?:[eE][+-]?[0-9]+)?|-?(?:0|[1-9][0-9]*)[eE][+-]?[0-9]+", value):
        number = float(value)
        if not math.isfinite(number):
            raise CanonicalError("non-finite number")
        return number
    return value


def _mapping_pair(content: str) -> tuple[str, str]:
    parts = _split_flow(content, ":")
    if len(parts) < 2:
        raise CanonicalError(f"YAML mapping entry lacks colon: {content}")
    key = _flow_key(parts[0])
    return key, ":".join(parts[1:]).strip()


def _load_yaml_subset(text: str) -> Any:
    lines: list[tuple[int, str, int]] = []
    for number, raw_line in enumerate(text.splitlines(), 1):
        clean = _commentless(raw_line).rstrip()
        if not clean.strip() or clean.lstrip().startswith("---") or clean.lstrip().startswith("..."):
            continue
        prefix = clean[: len(clean) - len(clean.lstrip(" "))]
        if "\t" in prefix:
            raise CanonicalError(f"tabs are forbidden in YAML indentation at line {number}")
        lines.append((len(prefix), clean.lstrip(" "), number))
    if not lines:
        raise CanonicalError("empty YAML document")

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        if lines[index][0] != indent:
            raise CanonicalError(f"unexpected YAML indentation at line {lines[index][2]}")
        sequence = lines[index][1].startswith("- ") or lines[index][1] == "-"
        container: Any = [] if sequence else {}
        while index < len(lines):
            current_indent, content, number = lines[index]
            if current_indent < indent:
                break
            if current_indent > indent:
                raise CanonicalError(f"unexpected YAML indentation at line {number}")
            is_item = content.startswith("- ") or content == "-"
            if is_item != sequence:
                raise CanonicalError(f"mixed mapping and sequence at line {number}")
            if sequence:
                rest = content[1:].strip()
                if not rest:
                    if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
                        raise CanonicalError(f"empty sequence item at line {number}")
                    value, index = parse_block(index + 1, lines[index + 1][0])
                    container.append(value)
                    continue
                if ":" in rest and not rest.startswith(("{", "[", "'", '"')):
                    key, raw_value = _mapping_pair(rest)
                    item: dict[str, Any] = {}
                    if raw_value:
                        item[key] = _scalar(raw_value)
                        index += 1
                    else:
                        if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
                            item[key] = None
                            index += 1
                        else:
                            item[key], index = parse_block(index + 1, lines[index + 1][0])
                    while index < len(lines) and lines[index][0] > indent:
                        child_indent, child_content, child_number = lines[index]
                        if child_content.startswith("- "):
                            raise CanonicalError(f"unexpected sequence continuation at line {child_number}")
                        child_key, child_raw = _mapping_pair(child_content)
                        if child_key in item:
                            raise CanonicalError(f"duplicate key: {child_key}")
                        if child_raw:
                            item[child_key] = _scalar(child_raw)
                            index += 1
                        else:
                            if index + 1 >= len(lines) or lines[index + 1][0] <= child_indent:
                                item[child_key] = None
                                index += 1
                            else:
                                item[child_key], index = parse_block(index + 1, lines[index + 1][0])
                    container.append(item)
                    continue
                container.append(_scalar(rest))
                index += 1
                continue
            key, raw_value = _mapping_pair(content)
            if key in container:
                raise CanonicalError(f"duplicate key: {key}")
            if raw_value:
                container[key] = _scalar(raw_value)
                index += 1
            else:
                if index + 1 >= len(lines) or lines[index + 1][0] <= indent:
                    container[key] = None
                    index += 1
                else:
                    container[key], index = parse_block(index + 1, lines[index + 1][0])
        return container, index

    value, final = parse_block(0, lines[0][0])
    if final != len(lines):
        raise CanonicalError("YAML document did not parse completely")
    return value


def canonical_bytes(value: Any) -> bytes:
    _validate(value)
    try:
        return _serialize(value).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise CanonicalError(str(exc)) from exc


def _utf16_key(value: str) -> bytes:
    return value.encode("utf-16-be", "surrogatepass")


def _number(value: float) -> str:
    if value == 0:
        return "0"
    negative = value < 0
    absolute = -value if negative else value
    raw = repr(absolute).lower()
    if "e" in raw:
        coefficient, exponent_raw = raw.split("e")
        exponent = int(exponent_raw)
    else:
        coefficient, exponent = raw, 0
    digits = coefficient.replace(".", "")
    decimal_index = coefficient.find(".")
    integer_digits = len(coefficient) if decimal_index < 0 else decimal_index
    decimal_position = integer_digits + exponent
    if 1e-6 <= absolute < 1e21:
        if decimal_position <= 0:
            rendered = "0." + "0" * (-decimal_position) + digits
        elif decimal_position >= len(digits):
            rendered = digits + "0" * (decimal_position - len(digits))
        else:
            rendered = digits[:decimal_position] + "." + digits[decimal_position:]
        rendered = rendered.rstrip("0").rstrip(".") if "." in rendered else rendered
    else:
        significant = digits.rstrip("0")
        mantissa = significant[0]
        if len(significant) > 1:
            mantissa += "." + significant[1:]
        scientific_exponent = decimal_position - 1
        sign = "+" if scientific_exponent >= 0 else ""
        rendered = f"{mantissa}e{sign}{scientific_exponent}"
    return ("-" if negative else "") + rendered


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_serialize(key)}:{_serialize(value[key])}" for key in sorted(value, key=_utf16_key)
        ) + "}"
    raise CanonicalError(f"unsupported canonical type: {type(value).__name__}")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_digest(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

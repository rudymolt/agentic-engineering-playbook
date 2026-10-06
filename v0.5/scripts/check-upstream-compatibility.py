#!/usr/bin/env python3
"""Fail closed when an embedded upstream skill is untested or incompatible."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "upstream-integrations.json"
REQUIRED_FIELDS = {
    "upstream",
    "tested_version",
    "tested_source_sha256",
    "embedded_compatible",
    "compatible_mode",
    "embedded_invocation",
    "adapter",
    "compatibility_evidence",
    "required_outputs",
    "permitted_side_effects",
    "prohibited_side_effects",
    "fallback",
    "last_verified",
}


class ManifestError(ValueError):
    """The integration manifest cannot enforce the declared contract."""


class Decision(NamedTuple):
    skill: str
    status: str
    may_invoke: bool
    reason: str
    embedded_invocation: str | None
    fallback: str
    tested_version: str | None
    expected_sha256: str | None
    actual_sha256: str | None


def load_manifest(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise ManifestError(f"missing integration manifest: {path}") from error
    except json.JSONDecodeError as error:
        raise ManifestError(f"invalid integration manifest JSON: {error}") from error
    if payload.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    integrations = payload.get("integrations")
    if not isinstance(integrations, dict):
        raise ManifestError("integrations must be an object")
    for name, entry in integrations.items():
        if not isinstance(entry, dict):
            raise ManifestError(f"{name}: integration entry must be an object")
        missing = sorted(REQUIRED_FIELDS - set(entry))
        if missing:
            raise ManifestError(f"{name}: missing required fields: {', '.join(missing)}")
        for field in (
            "upstream", "tested_version", "adapter", "compatibility_evidence",
            "fallback", "last_verified",
        ):
            if not isinstance(entry[field], str) or not entry[field].strip():
                raise ManifestError(f"{name}: {field} must be a non-empty string")
        if not isinstance(entry["embedded_compatible"], bool):
            raise ManifestError(f"{name}: embedded_compatible must be a boolean")
        if entry["embedded_compatible"] is True and entry["compatible_mode"] != "report-only":
            raise ManifestError(f"{name}: embedded-compatible verification must be report-only")
        if entry["embedded_compatible"] is False and entry["compatible_mode"] != "none":
            raise ManifestError(f"{name}: incompatible integration must declare compatible_mode none")
        invocation = entry["embedded_invocation"]
        if (
            entry["embedded_compatible"] is True
            and (not isinstance(invocation, str) or not invocation.strip())
        ):
            raise ManifestError(f"{name}: compatible integration requires embedded_invocation")
        if entry["embedded_compatible"] is False and invocation is not None:
            raise ManifestError(f"{name}: incompatible integration must not declare embedded_invocation")
        digest = entry["tested_source_sha256"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ManifestError(f"{name}: tested_source_sha256 must be a SHA-256 digest")
        try:
            dt.date.fromisoformat(entry["last_verified"])
        except ValueError as error:
            raise ManifestError(f"{name}: last_verified must use YYYY-MM-DD") from error
        for field in ("required_outputs", "permitted_side_effects", "prohibited_side_effects"):
            if not isinstance(entry[field], list) or not entry[field]:
                raise ManifestError(f"{name}: {field} must be a non-empty list")
    return payload


def evaluate(
    skill: str,
    source: Path,
    unknown_fallback: str,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> Decision:
    if not unknown_fallback.strip():
        raise ManifestError("unknown fallback must name a manual route")
    manifest = load_manifest(manifest_path)
    integrations = manifest["integrations"]
    assert isinstance(integrations, dict)
    entry = integrations.get(skill)
    if entry is None:
        return Decision(
            skill, "unknown", False, "integration is not declared", None, unknown_fallback,
            None, None, None,
        )
    assert isinstance(entry, dict)
    fallback = str(entry["fallback"])
    expected = str(entry["tested_source_sha256"])
    version = str(entry["tested_version"])
    try:
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as error:
        return Decision(
            skill, "missing", False,
            f"cannot read installed source ({type(error).__name__}); restore a readable regular SKILL.md for this exact source and retry",
            None, fallback,
            version, expected, None,
        )
    if actual != expected:
        return Decision(
            skill, "drifted", False, "installed skill is outside tested source", None, fallback,
            version, expected, actual,
        )
    if entry["embedded_compatible"] is not True:
        return Decision(
            skill, "incompatible", False,
            "tested source does not provide the required embedded report-only mode",
            None, fallback, version, expected, actual,
        )
    return Decision(
        skill, "compatible", True, "exact tested report-only source",
        str(entry["embedded_invocation"]), fallback,
        version, expected, actual,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", required=True, help="manifest integration key")
    parser.add_argument("--source", required=True, type=Path, help="installed SKILL.md path")
    parser.add_argument(
        "--fallback",
        required=True,
        help="named manual/adapter route used when the manifest key is unknown",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", action="store_true", help="emit a machine-readable decision")
    args = parser.parse_args(argv)
    try:
        decision = evaluate(args.skill, args.source, args.fallback, args.manifest)
    except ManifestError as error:
        print(f"ERROR: {error}")
        return 1
    if args.json:
        print(json.dumps(decision._asdict(), sort_keys=True))
    elif decision.may_invoke:
        print(
            f"COMPATIBLE {decision.skill}: {decision.reason}; "
            f"invoke {decision.embedded_invocation}"
        )
    else:
        print(f"FALLBACK {decision.skill}: {decision.reason}; {decision.fallback}")
    return 0 if decision.may_invoke else 2


if __name__ == "__main__":
    sys.exit(main())

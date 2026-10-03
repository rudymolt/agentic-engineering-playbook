#!/usr/bin/env python3
"""Apply deterministic V0.5 upgrades and the supported V0.4 transition.

The skill remains responsible for presenting the plan and obtaining approval.
This helper patches only known boilerplate. Anything ambiguous is returned as a
manual review and prevents the project from being stamped at the latest version.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import template_base  # noqa: E402
from playbook_state import (  # noqa: E402
    insert_after_line,
    insert_before,
    parse_top_level_list,
    parse_top_level_map,
    replace_top_level_scalar,
    top_level_scalar_value,
    validate_cadences,
    validate_state,
)

CURRENT_VERSION = template_base.CURRENT_VERSION
LAST_AUTOMATIC_VERSION = "V0.3.33"
DELIVERY_SKILL = Path(".agents/skills/ai-playbook-deliver")
AUTHORITATIVE_EVIDENCE_KINDS = {
    "provider_metadata",
    "session_metadata",
    "host_metadata",
}

MODEL_ROUTING_BLOCK = """model_routing:
  policy: gated
  defaults:
    planning: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }
    implementation: { model_id: gpt-6.1-sol, runner: codex, reasoning: medium }
    verification: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }
  allowed_runners: [codex, claude-code, cursor, opencode]

"""

PRE_V038_MODEL_DEFAULTS = """    planning: { model_id: gpt-5.6-sol, runner: codex, reasoning: high }
    implementation: { model_id: gpt-5.6-terra, runner: codex, reasoning: medium }
    verification: { model_id: gpt-5.6-sol, runner: codex, reasoning: high }"""

V038_MODEL_DEFAULTS = """    planning: { model_id: gpt-5.6-sol, runner: codex, reasoning: high }
    implementation: { model_id: gpt-5.6-terra, runner: codex, reasoning: high }
    verification: { model_id: gpt-5.6-sol, runner: codex, reasoning: medium }"""

PRE_V061_MODEL_DEFAULTS = """    planning: { model_id: gpt-5.6-sol, runner: codex, reasoning: high }
    implementation: { model_id: gpt-6-sol, runner: codex, reasoning: medium }
    verification: { model_id: gpt-6-sol, runner: codex, reasoning: high }"""

CURRENT_MODEL_DEFAULTS = """    planning: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }
    implementation: { model_id: gpt-6.1-sol, runner: codex, reasoning: medium }
    verification: { model_id: gpt-6.1-sol, runner: codex, reasoning: high }"""

OBSERVATIONAL_TEMPLATE_CONTRACTS = {
    "retro-template.md": "Time-to-merge (med/max)",
    "field-report.md": "## Observational eval baseline",
}

WAYFINDER_BLOCK = """# Pre-spec Wayfinder maps currently in discovery. The tracker is canonical.
active_wayfinding_maps: []

"""

DELIVERY_MISSIONS_BLOCK = """# Optional discovery pointers; Mission Control remains canonical.
delivery_missions: []

"""

PENDING_STATUS_SECTION = """## Pending Plan routes

*(none — add `- {request title} · {route status} · {model label} via {runner} · handoff {path|automatic}`, mirroring resumable `pending_model_routes` without increasing `active_features`)*

"""

WAYFINDER_STATUS_SECTION = """## Open Wayfinder maps

*(none — while pre-spec discovery is open, add `- [{map title}]({locator}) — {one-line destination}`, mirroring `active_wayfinding_maps` without increasing `active_features`)*
"""

AGENT_ROUTE_ROW = "| Choose a Plan, Build, or Verify model | `{playbook-path}/v0.5/93-model-routing-track.md`, then `/model-router` |"
AGENT_HANDOFF_RULE = "- Don't treat `.playbook-routing/` handoffs as durable feature docs; use them only to resume the named pending route."
CLAUDE_ROUTING_RULE = "- **Model routing:** gated — use `{path-to-playbook}/v0.5/93-model-routing-track.md` at Plan, Build, and Verify. The normal typed action accepts the resolved project/feature preference with origin; `models` shows verified alternatives; every route states current tab, sidecar, or Conductor new-tab behavior."
CLAUDE_PACE_RULE = "- **Codex pace:** standard by default. When the human is waiting, they may append `fast` to a Build action (for example `build all fast`); carry fast pace through returned fixes and the fresh Verify handoff for that run only. Fast changes generation pace and usage, never the selected model, reasoning, tests, permissions, or safety gates."
PRE_V040_CLOSEOUT_RULE = "- Any pending feature closeout — recommend its next missing action: production verification, doc-close, then feature retro. Never say “ready for new work” while one exists."
V040_CLOSEOUT_RULE = PRE_V040_CLOSEOUT_RULE + " When doc-close and the feature retro will run in the same session, recommend them as one closeout branch and PR (stage 10's closeout mechanics), not a docs PR per step."
V041_MANAGED_MERGE_SENTENCE = (
    " Managed prose files upgrade by three-way merge against the committed "
    "`.playbook-base/` snapshots (V0.3.41): `note:` lines are informational; "
    "a reported merge conflict is tier 3 — merge it by hand with the user, "
    "then re-run with `--adopt-current {file}` to reset that file's recorded base."
)
V041_SKILL_ANCHOR = (
    "Earlier versions continue through the listed file-by-file deltas. "
    "Completion criterion:"
)
V041_TAG_RULE = (
    "- **Tag every released version.** When one release train ships several changelog "
    "versions, create a tag per version on the release commit — template provenance and "
    "upgrade archaeology resolve versions to commits through these tags, so a skipped tag "
    "is a permanent hole."
)
V041_TAG_ANCHOR = "- Tag convention: lowercase version, e.g. `V0.3.31` becomes `v0.3.31`."
VERIFICATION_MAP_CADENCE = """  - id: verification-map-drift
    type: time
    counter: days_since_last_verification_map_maintenance
    nudge_threshold: 7
    insist_threshold: 21
    action: /ai-playbook-maintain-verification-harness
    stage: 09-qa
    rationale: An explicitly adopted verification map needs a complete accepted audit before its evidence becomes stale.

"""


def insert_cadence_at_list_end(text: str, cadence: str) -> tuple[str, bool]:
    """Append a cadence before the next top-level mapping, preserving custom YAML.

    Customized cadence files do not necessarily retain the template's section
    comments. Standalone comments never establish ownership: they may occur
    between an item's fields at any indentation. Bound the block by the next
    top-level data line, verify its list shape, then insert after its last data
    line. Leave trailing comments with the following section or footer.
    """
    header = re.search(r"(?m)^cadences:[ \t]*(?:#.*)?$", text)
    if header is None:
        return text, False
    start = header.end()
    if start < len(text) and text[start] == "\n":
        start += 1
    boundary = re.search(r"(?m)^(?=[^ \t\r\n#])", text[start:])
    end = start + boundary.start() if boundary else len(text)
    insertion = start
    offset = start
    has_item = False
    for line in text[start:end].splitlines(keepends=True):
        if line.strip() and not line.lstrip().startswith("#"):
            if re.match(r"^  - [A-Za-z0-9_-]+:", line):
                has_item = True
            elif not has_item or not line.startswith("    "):
                return text, False
            insertion = offset + len(line)
        offset += len(line)
    end = insertion
    prefix = "" if end == 0 or text[:end].endswith("\n") else "\n"
    return text[:end] + prefix + cadence + text[end:], True


def insert_after_map_field(
    text: str, block_name: str, field_name: str, line: str,
) -> tuple[str, bool]:
    """Insert LINE after FIELD_NAME in one named top-level mapping only.

    Project state files may have custom maps whose fields deliberately overlap
    with playbook names.  A document-wide anchor search can then place defaults
    in that unrelated map.  Keep the search inside the owning map and retain
    every surrounding comment and custom field verbatim.
    """
    header = re.search(rf"(?m)^{re.escape(block_name)}:\s*(?:#.*)?$", text)
    if header is None:
        return text, False
    boundary = re.search(r"(?m)^(?=[^ \t\r\n#])", text[header.end():])
    end = header.end() + boundary.start() if boundary else len(text)
    block = text[header.end():end]
    anchor = re.search(rf"(?m)^  {re.escape(field_name)}:[^\n]*$", block)
    if anchor is None:
        return text, False
    insertion = header.end() + anchor.end()
    return text[:insertion] + "\n" + line + text[insertion:], True


def insert_at_map_start(text: str, block_name: str, line: str) -> tuple[str, bool]:
    """Insert LINE immediately under one named top-level mapping header."""
    header = re.search(rf"(?m)^{re.escape(block_name)}:\s*(?:#.*)?$", text)
    if header is None:
        return text, False
    return text[:header.end()] + "\n" + line + text[header.end():], True


class UpgradeReport:
    def __init__(self) -> None:
        self.changed_files: list[str] = []
        self.manual_reviews: list[str] = []
        self.provenance_reviews: list[str] = []
        self.notes: list[str] = []   # informational; never blocks certification

    def add_provenance_review(self, message: str) -> None:
        """Record merge/provenance work while retaining its stamp semantics.

        A declined template item keeps the last satisfied project version; it
        must not trigger the legacy V0.3.32 stamp correction used for missing
        pre-provenance state/boilerplate evidence.
        """
        self.manual_reviews.append(message)
        self.provenance_reviews.append(message)


def unverified_identity_reviews(state: str) -> list[str]:
    reviews: list[str] = []
    lines = state.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s+identity:\s*$", line):
            continue
        indent = len(line) - len(line.lstrip())
        block: list[str] = []
        for candidate in lines[index + 1 :]:
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate.strip() and candidate_indent <= indent:
                break
            block.append(candidate)
        block_text = "\n".join(block)
        if not re.search(r"(?m)^\s+status:\s*verified\s*(?:#.*)?$", block_text):
            continue
        evidence = re.search(r"(?m)^\s+evidence_kind:\s*([^\s#]+)", block_text)
        requested = re.search(r"(?m)^\s+requested_model_id:\s*([^\s#]+)", block_text)
        reported = re.search(r"(?m)^\s+reported_model_id:\s*([^\s#]+)", block_text)
        verified_at = re.search(r"(?m)^\s+verified_at:\s*([^\s#]+)", block_text)
        complete_evidence = (
            evidence
            and evidence.group(1) in AUTHORITATIVE_EVIDENCE_KINDS
            and requested
            and reported
            and requested.group(1) == reported.group(1)
            and reported.group(1) not in {"null", "~"}
            and verified_at
            and verified_at.group(1) not in {"null", "~"}
        )
        if complete_evidence:
            continue
        owner = "saved model route"
        for previous in reversed(lines[:index]):
            owner_match = re.match(r"^\s+(?:-\s+)?(?:route_id|slug):\s*([^\s#]+)", previous)
            if owner_match:
                owner = owner_match.group(1)
                break
        reviews.append(
            f"{owner}: re-prove verified model identity from authoritative runtime metadata; "
            "otherwise mark it identity-unverifiable before stamping V0.3.34"
        )
    return reviews


def split_yaml_value_comment(value: str) -> tuple[str, str]:
    """Split a YAML scalar from its real inline comment without unescaping it."""
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
            return value[:index], value[index:]
        index += 1
    return value, ""


def inside_escaped_double_quotes(value: str, position: int) -> bool:
    """Whether POSITION is inside a \"...\" literal within a double-quoted scalar."""
    outer_double = False
    escaped_literal = False
    index = 0
    while index < position:
        character = value[index]
        if character == "\\" and index + 1 < position:
            if outer_double and value[index + 1] == '"':
                escaped_literal = not escaped_literal
            index += 2
            continue
        if character == '"':
            outer_double = not outer_double
            if not outer_double:
                escaped_literal = False
        index += 1
    return outer_double and escaped_literal


def command_token_at(value: str, start: int, end: int) -> bool:
    """Return whether VALUE[start:end] is an intended standalone slash command."""
    if start:
        left = value[start - 1]
        if not (left.isspace() or left in "'\"([{"):
            return False
        if left in "'\"" and start >= 2 and value[start - 2] == "\\":
            return False

    if end < len(value):
        right = value[end]
        if right.isalnum() or right in "_/-?#=:":
            return False
        if right == "." and end + 1 < len(value) and value[end + 1].isalnum():
            return False

    token_start = start
    while token_start and not value[token_start - 1].isspace():
        token_start -= 1
    token_prefix = value[token_start:start]
    if (
        re.search(r"[A-Za-z][A-Za-z0-9+.-]*://", token_prefix)
        or token_prefix.lstrip("'\"([{<").startswith(("//", "www."))
        or "?" in token_prefix
        or "#" in token_prefix
    ):
        return False
    if inside_escaped_double_quotes(value, start):
        return False
    return True


def rewrite_renamed_route_value(line: str, old: str, new: str) -> str:
    """Rewrite one command token in a capability-routes YAML mapping value.

    Comments are deliberately excluded: route migration is data migration, not
    free-text replacement. URL tokens, path/prefix/suffix forms, and escaped
    string literals are not command tokens and stay untouched.
    """
    mapping = re.match(r"^(\s+[^#:\n][^:\n]*:\s*)(.*?)(\r?\n)?$", line)
    if not mapping:
        return line

    route_value, comment = split_yaml_value_comment(mapping.group(2))
    command = re.compile(rf"/{re.escape(old)}")
    pieces: list[str] = []
    cursor = 0
    for match in command.finditer(route_value):
        if not command_token_at(route_value, match.start(), match.end()):
            continue
        pieces.extend((route_value[cursor:match.start()], f"/{new}"))
        cursor = match.end()
    if pieces:
        pieces.append(route_value[cursor:])
        route_value = "".join(pieces)
    return mapping.group(1) + route_value + comment + (mapping.group(3) or "")


def migrate_cadences(text: str, report: UpgradeReport) -> str:
    """Migrate exact rendered action scalars without touching tuned cadence data."""
    lines = text.splitlines(keepends=True)
    renamed: set[tuple[str, str]] = set()
    for index, line in enumerate(lines):
        mapping = re.match(r"^(\s+(?:-\s+)?action:\s*)(.*?)(\r?\n)?$", line)
        if not mapping:
            continue
        value, comment = split_yaml_value_comment(mapping.group(2))
        leading = value[:len(value) - len(value.lstrip())]
        trailing = value[len(value.rstrip()):]
        scalar = value.strip()
        for old, new in template_base.REGISTRY.previous_name_map().items():
            replacements = {
                f"/{old}": f"/{new}",
                f"'/{old}'": f"'/{new}'",
                f'"/{old}"': f'"/{new}"',
            }
            if scalar not in replacements:
                continue
            scalar = replacements[scalar]
            renamed.add((old, new))
            break
        lines[index] = (
            mapping.group(1) + leading + scalar + trailing + comment
            + (mapping.group(3) or "")
        )
    for old, new in sorted(renamed):
        report.notes.append(f"playbook-cadences.yml: renamed /{old} → /{new}")
    text = "".join(lines)
    if not any(
        cadence.get("id") == "verification-map-drift"
        for cadence in parse_top_level_list(text, "cadences")
    ):
        if re.search(r"(?m)^cadences:[ \t]*\[\][ \t]*$", text):
            text = re.sub(
                r"(?m)^cadences:[ \t]*\[\][ \t]*$",
                "cadences:\n\n" + VERIFICATION_MAP_CADENCE.rstrip(),
                text,
                count=1,
            ) + ("" if text.endswith("\n") else "\n")
        else:
            text, inserted = insert_cadence_at_list_end(text, VERIFICATION_MAP_CADENCE)
            if inserted:
                return text
            report.manual_reviews.append(
                "playbook-cadences.yml: add verification-map-drift to the customized cadence list"
            )
    return text


def migrate_state(text: str, report: UpgradeReport, starting_patch: int) -> str:
    if not re.search(r"(?m)^schema_version:", text):
        text = "schema_version: 3\n" + text
    elif top_level_scalar_value(text, "schema_version") != "3":
        text = replace_top_level_scalar(text, "schema_version", "3")

    if not re.search(r"(?m)^  pending_plan_routes:", text):
        text, found = insert_before(
            text,
            "playbook_version:",
            "  pending_plan_routes: 0   # resumable pending_model_routes; linked Wayfinder routes do not count\n\n",
        )
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add status.pending_plan_routes to the customized status block")

    if not re.search(r"(?m)^  pending_closeouts:", text):
        text, found = insert_after_line(text, r"^  pending_plan_routes:[^\n]*$", "  pending_closeouts: 0")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add status.pending_closeouts to the customized status block")

    decision_values = parse_top_level_map(text, "decisions")
    if "technical_decisions" not in decision_values:
        text, found = insert_after_map_field(
            text, "decisions", "capability_profile", "  technical_decisions: null  # ask | auto_recommend",
        )
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add decisions.technical_decisions to the customized decisions block")

    decision_values = parse_top_level_map(text, "decisions")
    if "verification_harness_path" not in decision_values:
        text, found = insert_after_map_field(
            text, "decisions", "technical_decisions",
            "  verification_harness_path: null   # canonical selected project-relative harness directory",
        )
        if not found:
            report.manual_reviews.append(
                ".playbook-state.yml: add decisions.verification_harness_path to the customized decisions block"
            )
    decision_values = parse_top_level_map(text, "decisions")
    if "verification_map_maintenance" not in decision_values:
        text, found = insert_after_map_field(
            text, "decisions", "verification_harness_path",
            "  verification_map_maintenance: false   # explicit opt-in only",
        )
        if not found:
            report.manual_reviews.append(
                ".playbook-state.yml: add decisions.verification_map_maintenance beside the selected harness path"
            )
    decision_values = parse_top_level_map(text, "decisions")
    if "verification_harness_binding" not in decision_values:
        text, found = insert_after_map_field(
            text, "decisions", "verification_map_maintenance",
            "  verification_harness_binding: null   # selected path bound by the explicit selection transition",
        )
        if not found:
            report.manual_reviews.append(
                ".playbook-state.yml: add decisions.verification_harness_binding beside verification-map selection"
            )

    last_run_values = parse_top_level_map(text, "last_run")
    if "feature_ship" not in last_run_values:
        text, found = insert_after_map_field(text, "last_run", "ship", "  feature_ship: null")
        if not found:
            text, found = insert_at_map_start(text, "last_run", "  feature_ship: null")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add last_run.feature_ship to the customized timestamp block")

    last_run_values = parse_top_level_map(text, "last_run")
    if "verification_map_enabled" not in last_run_values:
        text, found = insert_after_map_field(
            text, "last_run", "feature_ship",
            "  verification_map_enabled: null   # actual initial opt-in time",
        )
        if not found:
            text, found = insert_at_map_start(
                text, "last_run",
                "  verification_map_enabled: null",
            )
        if not found:
            report.manual_reviews.append(
                ".playbook-state.yml: add last_run.verification_map_enabled to the customized last_run block"
            )
    last_run_values = parse_top_level_map(text, "last_run")
    if "verification_map_maintenance" not in last_run_values:
        text, found = insert_after_map_field(
            text, "last_run", "verification_map_enabled",
            "  verification_map_maintenance: null   # accepted complete clean/changed audit only",
        )
        if not found:
            report.manual_reviews.append(
                ".playbook-state.yml: add last_run.verification_map_maintenance beside verification_map_enabled"
            )

    if not re.search(r"(?m)^pending_closeouts:", text):
        text, found = insert_before(text, "active_features:\n", "pending_closeouts: []\n\n")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add pending_closeouts before the customized active_features block")

    if not re.search(r"(?m)^  model_routing:", text):
        text, found = insert_after_line(text, r"^  state_lifecycle:[^\n]*$", "  model_routing: null")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add capability_routes.model_routing to the customized route map")

    if not re.search(r"(?m)^model_routing:", text):
        text, found = insert_before(text, "counters:\n", MODEL_ROUTING_BLOCK)
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add the model_routing policy before the customized counters block")
    else:
        routing = re.search(r"(?m)^model_routing:\n(?:[ \t]+.*\n|[ \t]*\n)*", text)
        previous_defaults = (V038_MODEL_DEFAULTS, PRE_V061_MODEL_DEFAULTS)
        if starting_patch < 38:
            previous_defaults = (PRE_V038_MODEL_DEFAULTS, *previous_defaults)
        if routing:
            for previous in previous_defaults:
                if previous in routing.group():
                    updated = routing.group().replace(previous, CURRENT_MODEL_DEFAULTS, 1)
                    text = text[:routing.start()] + updated + text[routing.end():]
                    break

    if not re.search(r"(?m)^pending_model_routes:", text):
        text, found = insert_before(text, "counters:\n", "pending_model_routes: []\n\n")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add pending_model_routes before the customized counters block")

    if not re.search(r"(?m)^active_wayfinding_maps:", text):
        text, found = insert_before(text, "active_features:\n", WAYFINDER_BLOCK)
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add active_wayfinding_maps before the customized active_features block")

    if not re.search(r"(?m)^delivery_missions:", text):
        text, found = insert_before(text, "counters:\n", DELIVERY_MISSIONS_BLOCK)
        if not found:
            report.manual_reviews.append(".playbook-state.yml: add delivery_missions before the customized counters block")

    identity_reviews = unverified_identity_reviews(text)
    report.manual_reviews.extend(identity_reviews)
    if not re.search(r"(?m)^prereqs_required:", text):
        text, found = insert_before(text, "decisions:\n", "prereqs_required: true\n")
        if not found:
            report.manual_reviews.append(".playbook-state.yml: place prereqs_required before the customized decisions block")

    lines = text.splitlines(keepends=True)
    renamed: set[tuple[str, str]] = set()
    in_capability_routes = False
    for index, line in enumerate(lines):
        if re.match(r"^capability_routes:\s*(?:#.*)?$", line):
            in_capability_routes = True
        elif in_capability_routes and re.match(r"^[^\s#]", line):
            in_capability_routes = False
        if not in_capability_routes:
            continue
        for old, new in template_base.REGISTRY.previous_name_map().items():
            updated = rewrite_renamed_route_value(line, old, new)
            if updated != line:
                renamed.add((old, new))
                line = updated
        lines[index] = line
    for old, new in sorted(renamed):
        report.notes.append(f"capability_routes: renamed /{old} → /{new}")
    text = "".join(lines)
    return text


def migrate_planning_status(text: str, state: str, report: UpgradeReport) -> str:
    if "## Pending Plan routes" not in text:
        text = text.rstrip() + "\n\n"
        text += PENDING_STATUS_SECTION
    if "## Open Wayfinder maps" not in text:
        text = text.rstrip() + "\n\n"
        text += WAYFINDER_STATUS_SECTION
    resumable = {"selected", "running", "waiting_manual", "blocked"}
    # The typed parser returns unquoted scalars (and None for null), so titles
    # arrive ready for the containment check — including fields that carry an
    # inline comment, which the old raw parser silently dropped.
    for route in parse_top_level_list(state, "pending_model_routes"):
        title = str(route.get("request_title") or "")
        if route.get("status") in resumable and title and title not in text:
            report.manual_reviews.append(
                f"planning/STATUS.md: mirror pending Plan route '{title}' before certification"
            )
    for map_entry in parse_top_level_list(state, "active_wayfinding_maps"):
        title = str(map_entry.get("title") or "")
        locator = str(map_entry.get("locator") or "")
        if title and (title not in text or (locator and locator not in text)):
            report.manual_reviews.append(
                f"planning/STATUS.md: mirror open Wayfinder map '{title}' before certification"
            )
    return text


def valid_routing_path(value: str) -> bool:
    return value in {
        "{playbook-path}/v0.5/93-model-routing-track.md",
        "{path-to-playbook}/v0.5/93-model-routing-track.md",
    } or (
        value.startswith("/") and value.endswith("/v0.5/93-model-routing-track.md")
    )


def migrate_agents(text: str, report: UpgradeReport) -> str:
    route_match = re.search(
        r"(?m)^\| Choose a Plan, Build, or Verify model \| `([^`]+)`, then `/model-router` \|$",
        text,
    )
    route_ok = bool(route_match and valid_routing_path(route_match.group(1)))
    route_present = "| Choose a Plan, Build, or Verify model |" in text
    if not route_ok and not route_present:
        text, route_ok = insert_after_line(text, r"^\| New feature \|[^\n]*$", AGENT_ROUTE_ROW)
    text, handoff_ok = insert_after_line(text, r"^- Don't read `archive/`\.$", AGENT_HANDOFF_RULE)
    if not route_ok:
        report.manual_reviews.append("AGENTS.md: place the Plan/Build/Verify model-routing row in the customized task table")
    if not handoff_ok:
        report.manual_reviews.append("AGENTS.md: place the .playbook-routing handoff rule in the customized guardrails")
    return text


def migrate_claude(text: str, report: UpgradeReport) -> str:
    policy_match = re.search(r"(?m)^- \*\*Model routing:\*\* ([^\n]+)$", text)
    policy = policy_match.group(1) if policy_match else ""
    path_match = re.search(r"`([^`]*93-model-routing-track\.md)`", policy)
    required_tokens = (
        "gated",
        "at Plan, Build, and Verify",
        "`models`",
        "current tab",
        "sidecar",
        "Conductor",
    )
    ok = bool(
        path_match
        and valid_routing_path(path_match.group(1))
        and all(token in policy for token in required_tokens)
    )
    if not ok and policy_match is None:
        text, ok = insert_after_line(text, r"^- \*\*State file:\*\*[^\n]*$", CLAUDE_ROUTING_RULE)
    if not ok:
        report.manual_reviews.append("CLAUDE.md: place the model-routing policy beside the customized state settings")
    if CLAUDE_PACE_RULE not in text:
        text, pace_ok = insert_after_line(text, r"^- \*\*Model routing:\*\*[^\n]*$", CLAUDE_PACE_RULE)
        if not pace_ok:
            report.manual_reviews.append("CLAUDE.md: place the Codex pace rule beside the customized model-routing policy")
    return text


def write_if_changed(path: Path, text: str, report: UpgradeReport) -> None:
    before = path.read_text() if path.exists() else ""
    if before == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if str(path) not in report.changed_files:
        report.changed_files.append(str(path))


def install_or_upgrade_delivery(project: Path, report: UpgradeReport) -> None:
    """Install the edition-owned runtime; modified installed files fail closed."""

    playbook_root = Path(__file__).resolve().parents[2]
    lifecycle = playbook_root / "v0.5" / "delivery" / "scripts" / "lifecycle.py"
    lock = project / DELIVERY_SKILL / "manifest-lock.yml"
    command = "upgrade" if lock.exists() else "install"
    before = lock.read_bytes() if lock.exists() else None
    completed = subprocess.run(
        [sys.executable, str(lifecycle), command, "--project", str(project)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        detail = completed.stdout.strip() or completed.stderr.strip()
        report.manual_reviews.append(
            f"{DELIVERY_SKILL}: manifest-owned delivery {command} blocked: {detail}"
        )
        return
    after = lock.read_bytes()
    if before != after:
        report.changed_files.append(str(lock))


def migrate_observational_templates(
    project: Path, report: UpgradeReport, tracked: set[str] | None = None
) -> None:
    tracked = tracked or set()
    template_root = Path(__file__).resolve().parents[1] / "templates"
    for name, contract in OBSERVATIONAL_TEMPLATE_CONTRACTS.items():
        if name in tracked:
            continue
        target = project / name
        if not target.exists():
            write_if_changed(target, (template_root / name).read_text(), report)
        else:
            try:
                text = target.read_text()
            except UnicodeDecodeError:
                continue  # the provenance merge reports one typed tier-3 review
            if contract in text:
                continue
            report.manual_reviews.append(
                f"{name}: merge the V0.3.39 observational eval contract into the customized template"
            )


def migrate_whats_next_skill(project: Path, report: UpgradeReport, starting_patch: int) -> None:
    """Patch the installed V0.3.39 closeout boilerplate when that local skill exists."""
    if starting_patch >= 40:
        return
    target = project / ".agents" / "skills" / "whats-next" / "SKILL.md"
    if not target.exists():
        return
    try:
        text = target.read_text()
    except UnicodeDecodeError:
        return  # the provenance merge reports one typed tier-3 review
    if V040_CLOSEOUT_RULE in text:
        return
    if PRE_V040_CLOSEOUT_RULE not in text:
        report.manual_reviews.append(
            ".agents/skills/whats-next/SKILL.md: merge the V0.3.40 one-closeout-PR rule into the customized skill"
        )
        return
    write_if_changed(target, text.replace(PRE_V040_CLOSEOUT_RULE, V040_CLOSEOUT_RULE, 1), report)


def recover_project_name(project: Path) -> str:
    """Backfill name source for pre-provenance projects. Bootstrap rendered
    `{project name}` into the CLAUDE.md heading, so that heading — not the
    directory name — is what the recorded bases must be rendered with;
    otherwise the wrong name reads as a customisation and can even be merged
    into project files by later template changes."""
    claude = project / "CLAUDE.md"
    if claude.exists():
        try:
            match = re.search(r"(?m)^# CLAUDE\.md — (.+?)\s*$", claude.read_text())
        except UnicodeDecodeError:
            match = None
        if match:
            return match.group(1)
    return project.name


def write_managed(path: Path, text: str, report: UpgradeReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    if str(path) not in report.changed_files:
        report.changed_files.append(str(path))


def migrate_v041_provenance_rollout(
    project: Path,
    state: str,
    report: UpgradeReport,
    starting_patch: int,
) -> set[str]:
    """Bridge managed-file changes made by the provenance release itself.

    Projects before V0.3.41 have no recorded base, so the new merge mechanism
    cannot distinguish the release's own template deltas from customisation.
    Apply the three known uncustomised V0.3.41 deltas once using narrow anchors.
    A customised surface remains tier 3 and is deliberately excluded from
    provenance backfill so it re-presents on the next run.
    """
    if starting_patch >= 41:
        return set()
    try:
        record = template_base.read_provenance(state)
    except ValueError:
        return set()  # migrate_templates reports the malformed block once
    tracked = set(record.get("files", {}))
    blocked: set[str] = set()

    def read_rollout_target(relative: str, target: Path) -> str | None:
        try:
            return target.read_text()
        except UnicodeDecodeError:
            report.add_provenance_review(
                f"{relative}: managed file is not UTF-8 text — repair its encoding "
                "before the V0.3.41 rollout can update it"
            )
            blocked.add(relative)
            return None

    relative = ".agents/skills/ai-playbook-upgrade-project/SKILL.md"
    target = project / relative
    if relative not in tracked and target.exists():
        text = read_rollout_target(relative, target)
        if text is None:
            text = ""
        if V041_MANAGED_MERGE_SENTENCE not in text:
            if relative in blocked:
                pass
            elif V041_SKILL_ANCHOR in text:
                write_if_changed(
                    target,
                    text.replace(
                        V041_SKILL_ANCHOR,
                        "Earlier versions continue through the listed file-by-file deltas."
                        + V041_MANAGED_MERGE_SENTENCE
                        + " Completion criterion:",
                        1,
                    ),
                    report,
                )
            else:
                report.add_provenance_review(
                    f"{relative}: merge the V0.3.41 provenance-upgrade instructions into "
                    "the customized skill"
                )
                blocked.add(relative)

    relative = ".agents/skills/ai-playbook-upgrade-project/MIGRATIONS.md"
    target = project / relative
    if relative not in tracked and target.exists():
        text = read_rollout_target(relative, target)
        if text is None:
            text = ""
        row = next(
            line for line in (
                Path(__file__).resolve().parents[1]
                / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md"
            ).read_text().splitlines()
            if line.startswith("| Template provenance (V0.3.41)")
        )
        if row not in text and relative not in blocked:
            anchor = next(
                (line for line in text.splitlines()
                 if line.startswith("| One closeout PR (V0.3.40)")),
                None,
            )
            if anchor:
                write_if_changed(target, text.replace(anchor, anchor + "\n" + row, 1), report)
            else:
                report.add_provenance_review(
                    f"{relative}: add the V0.3.41 template-provenance migration row to "
                    "the customized reference"
                )
                blocked.add(relative)

    relative = ".agents/skills/ship-release/PLAYBOOK-PROFILE.md"
    target = project / relative
    if relative not in tracked and target.exists():
        text = read_rollout_target(relative, target)
        if text is None:
            text = ""
        if V041_TAG_RULE not in text:
            if relative in blocked:
                pass
            elif V041_TAG_ANCHOR in text:
                write_if_changed(
                    target,
                    text.replace(V041_TAG_ANCHOR, V041_TAG_ANCHOR + "\n" + V041_TAG_RULE, 1),
                    report,
                )
            else:
                report.add_provenance_review(
                    f"{relative}: add the V0.3.41 every-version tag rule to the "
                    "customized release profile"
                )
                blocked.add(relative)
    return blocked


def recorded_playbook_root(project: Path, state: str, fallback: Path) -> Path:
    """Recover the project's rendered playbook root without requiring it to exist here."""
    state_match = re.search(
        r"(?m)^# Updated by stage files \(see (/.+?)/v0\.[345]/10-process/\*\)",
        state,
    )
    if state_match:
        return Path(state_match.group(1))

    claude_base = project / template_base.BASE_DIR / "CLAUDE.md"
    if claude_base.exists():
        try:
            base_text = claude_base.read_text()
        except (OSError, UnicodeDecodeError):
            base_text = ""
        base_match = re.search(
            r"The full playbook V0\.4 is at `(.+?)/v0\.4/`\.", base_text
        )
        if base_match:
            return Path(base_match.group(1))
    return fallback


def migrate_templates(
    project: Path,
    playbook_root: Path,
    state: str,
    report: UpgradeReport,
    adopt_current: set[str],
    starting_patch: int,
    blocked_backfills: set[str] | None = None,
    render_root_override: Path | None = None,
) -> str:
    """Recorded-base three-way merge for managed prose files (V0.3.41).

    Provenance-tracked files merge {recorded base, project file, newly rendered
    template}; conflicts degrade to tier-3 manual reviews and keep their old
    base so they re-present until resolved (or explicitly accepted via
    --adopt-current). Files without provenance are backfilled: the base becomes
    the current template render, so deltas older than the backfill stay with
    the legacy migration rows while every later release merges.
    """
    try:
        record = template_base.read_provenance(state)
    except ValueError as error:
        report.add_provenance_review(
            f".playbook-state.yml: {error} — repair the machine-owned template_provenance block"
        )
        return state
    if not record and starting_patch >= 41:
        report.add_provenance_review(
            ".playbook-state.yml: template_provenance is missing from a V0.3.41+ project "
            "— restore the block and .playbook-base/ from version control, or explicitly "
            "re-establish the last proven version before upgrading"
        )
        return state
    project_name = record.get("project_name") or recover_project_name(project)
    render_root = render_root_override or recorded_playbook_root(project, state, playbook_root)
    files = record.setdefault("files", {})
    record.setdefault("schema", template_base.PROVENANCE_SCHEMA)
    record["project_name"] = project_name

    managed = template_base.managed_files(playbook_root)
    known_skill_dirs = {
        Path(relative).parts[2]
        for relative in files
        if Path(relative).parts[:2] == (".agents", "skills")
        and len(Path(relative).parts) > 2
    }
    for relative in sorted(set(files) - set(managed)):
        report.add_provenance_review(
            f"{relative}: recorded provenance path is absent from the current managed-file "
            "registry — add an explicit rename/removal migration before changing membership"
        )

    for relative, template_relative in managed.items():
        template_path = playbook_root / template_relative
        target = project / relative
        base_path = project / template_base.BASE_DIR / relative
        rendered_new = template_base.render(template_path.read_text(), render_root, project_name)
        fresh_entry = template_base.provenance_entry(
            template_relative, CURRENT_VERSION, rendered_new
        )
        entry = files.get(relative)

        if entry is None:
            if relative in (blocked_backfills or set()):
                continue
            # Backfill: bases recorded at the current render; older deltas stay
            # with the legacy migration rows this one time.
            if not target.exists():
                parts = Path(relative).parts
                is_new_default_skill = (
                    starting_patch >= 41
                    and parts[:2] == (".agents", "skills")
                    and len(parts) > 2
                    and parts[2] not in known_skill_dirs
                    and bool(known_skill_dirs)
                )
                if not is_new_default_skill:
                    continue
                write_managed(target, rendered_new, report)
                files[relative] = fresh_entry
                write_managed(base_path, rendered_new, report)
                continue
            try:
                ours = target.read_text()
            except UnicodeDecodeError:
                report.add_provenance_review(
                    f"{relative}: managed file is not UTF-8 text — repair its encoding "
                    "before provenance can track it"
                )
                continue
            if ours != rendered_new:
                report.notes.append(
                    f"{relative}: provenance backfilled at {CURRENT_VERSION}; existing "
                    "customisations are preserved and pre-backfill deltas remain covered "
                    "by the legacy migration rows"
                )
            files[relative] = fresh_entry
            write_managed(base_path, rendered_new, report)
            continue

        if not target.exists():
            report.add_provenance_review(
                f"{relative}: managed file is missing — restore it or remove its "
                "template_provenance entry"
            )
            continue
        try:
            ours = target.read_text()
        except UnicodeDecodeError:
            report.add_provenance_review(
                f"{relative}: managed file is not UTF-8 text — repair its encoding, then "
                f"re-run (use --adopt-current {relative} if the content is intentional)"
            )
            continue

        if relative in adopt_current:
            files[relative] = fresh_entry
            write_managed(base_path, rendered_new, report)
            continue

        if not base_path.exists():
            report.add_provenance_review(
                f"{relative}: pristine base under {template_base.BASE_DIR}/ is missing or was "
                f"edited — verify the project file, then re-run with --adopt-current {relative}"
            )
            continue
        try:
            base_bytes = base_path.read_bytes()
        except OSError as error:
            report.add_provenance_review(
                f"{relative}: pristine base under {template_base.BASE_DIR}/ cannot be read "
                f"({error}) — restore it, then re-run with --adopt-current {relative}"
            )
            continue
        if template_base.sha256_bytes(base_bytes) != entry.get("base_sha256"):
            report.add_provenance_review(
                f"{relative}: pristine base under {template_base.BASE_DIR}/ is missing or was "
                f"edited — verify the project file, then re-run with --adopt-current {relative}"
            )
            continue
        try:
            base = base_bytes.decode("utf-8")
        except UnicodeDecodeError:
            report.add_provenance_review(
                f"{relative}: pristine base under {template_base.BASE_DIR}/ is not UTF-8 text "
                f"— restore it, then re-run with --adopt-current {relative}"
            )
            continue

        if ours == base:
            if rendered_new != ours:
                write_managed(target, rendered_new, report)
            files[relative] = fresh_entry
            if rendered_new != base:
                write_managed(base_path, rendered_new, report)
        elif rendered_new == base:
            entry["version"] = CURRENT_VERSION   # customised, but no template change to carry
        else:
            try:
                merged, conflicted = template_base.merge3(base, ours, rendered_new)
            except template_base.MergeUnavailableError as error:
                report.add_provenance_review(
                    f"{relative}: {error} — merge the template change manually"
                )
                continue
            if conflicted:
                report.add_provenance_review(
                    f"{relative}: template change conflicts with project customisations — merge "
                    f"manually, then re-run with --adopt-current {relative}; conflicting hunks: "
                    f"{template_base.conflict_evidence(merged)}"
                )
                continue
            write_managed(target, merged, report)
            files[relative] = fresh_entry
            write_managed(base_path, rendered_new, report)

    if files:
        readme_path = project / template_base.BASE_DIR / "README.md"
        if not readme_path.exists():
            write_managed(readme_path, template_base.BASE_README, report)
        state = template_base.upsert_provenance(state, record)
    return state


def upgrade_project(
    project: Path,
    today: date | None = None,
    adopt_current: set[str] | None = None,
) -> UpgradeReport:
    project = project.resolve()
    today = today or date.today()
    report = UpgradeReport()

    required = (".playbook-state.yml", "AGENTS.md", "CLAUDE.md")
    missing = [name for name in required if not (project / name).exists()]
    if missing:
        raise FileNotFoundError(f"not a bootstrapped playbook project; missing: {', '.join(missing)}")

    state_path = project / ".playbook-state.yml"
    original_state = state_path.read_text()
    starting_version_match = re.search(r"(?m)^playbook_version:\s*([^\s#]+)", original_state)
    starting_version = starting_version_match.group(1) if starting_version_match else "unknown"
    starting_upgrade_date = top_level_scalar_value(original_state, "last_upgraded")
    needs_upgrade_date_repair = starting_upgrade_date in {None, "", "null", "~"}
    previous_version = re.fullmatch(r"V0\.4\.(\d+)", starting_version)
    current_version = re.fullmatch(r"V0\.5\.(\d+)", starting_version)
    if current_version:
        current_patch_number = int(CURRENT_VERSION.rsplit(".", 1)[1])
        if int(current_version.group(1)) > current_patch_number:
            raise ValueError(
                f"{starting_version} is newer than this playbook ({CURRENT_VERSION}); refusing to downgrade it"
            )
        # Current-edition projects have already passed the legacy migration floor.
        starting_patch = 41
        cross_major = False
    elif previous_version:
        # A private V0.4 project needs the public-edition transition. The
        # provenance merge below must certify every managed file before stamp.
        starting_patch = 41
        cross_major = True
    else:
        raise ValueError(
            "the deterministic migrator supports V0.4 and V0.5 projects; "
            "use the explicit file-by-file migration plan for older editions"
        )
    current_patch = 41
    playbook_root = Path(__file__).resolve().parents[2]
    prior_root = recorded_playbook_root(project, original_state, playbook_root) if previous_version else None
    state_for_migration = original_state
    if previous_version and prior_root is not None:
        state_for_migration = state_for_migration.replace(
            f"{prior_root}/v0.4/", f"{playbook_root}/v0.5/"
        )
    migrated_state = migrate_state(state_for_migration, report, starting_patch)

    cadences_path = project / "playbook-cadences.yml"
    if cadences_path.exists():
        cadences = cadences_path.read_text()
        if previous_version and prior_root is not None:
            cadences = cadences.replace(f"{prior_root}/v0.4/", f"{playbook_root}/v0.5/")
        write_if_changed(cadences_path, migrate_cadences(cadences, report), report)

    planning_path = project / "planning" / "STATUS.md"
    planning_before = planning_path.read_text() if planning_path.exists() else "# Planning status\n\n## Active features\n\n*(none)*\n"
    write_if_changed(planning_path, migrate_planning_status(planning_before, migrated_state, report), report)

    # Once a file has provenance it is exclusively merge-owned, even when a
    # different unresolved rollout file keeps the project stamp below V0.3.41.
    # Malformed provenance blocks also forbid legacy edits until repaired.
    provenance_malformed = False
    try:
        existing_provenance = template_base.read_provenance(migrated_state)
    except ValueError:
        existing_provenance = {}
        provenance_malformed = True
    tracked_prose = set(existing_provenance.get("files", {}))

    if starting_patch < 41 and not provenance_malformed:
        agents_path = project / "AGENTS.md"
        if "AGENTS.md" not in tracked_prose:
            try:
                agents_text = agents_path.read_text()
            except UnicodeDecodeError:
                agents_text = None
            if agents_text is not None:
                write_if_changed(agents_path, migrate_agents(agents_text, report), report)

        claude_path = project / "CLAUDE.md"
        if "CLAUDE.md" not in tracked_prose:
            try:
                claude_text = claude_path.read_text()
            except UnicodeDecodeError:
                claude_text = None
            if claude_text is not None:
                write_if_changed(claude_path, migrate_claude(claude_text, report), report)

        migrate_observational_templates(project, report, tracked_prose)
        if ".agents/skills/whats-next/SKILL.md" not in tracked_prose:
            migrate_whats_next_skill(project, report, starting_patch)
    blocked_backfills = migrate_v041_provenance_rollout(
        project, migrated_state, report, starting_patch
    )
    migrated_state = migrate_templates(
        project,
        playbook_root,
        migrated_state,
        report,
        adopt_current or set(),
        starting_patch,
        blocked_backfills,
        playbook_root if previous_version else None,
    )
    install_or_upgrade_delivery(project, report)

    gitignore_path = project / ".gitignore"
    gitignore = gitignore_path.read_text() if gitignore_path.exists() else ""
    if not re.search(r"(?m)^\.playbook-routing/$", gitignore):
        gitignore = gitignore.rstrip() + ("\n" if gitignore.strip() else "") + ".playbook-routing/\n"
    write_if_changed(gitignore_path, gitignore, report)

    needs_cold_path = (
        cross_major
        or starting_patch < current_patch
        or migrated_state != original_state
        or bool(report.changed_files)
        or bool(report.manual_reviews)
    )
    if needs_cold_path:
        migrated_state = replace_top_level_scalar(
            migrated_state,
            "prereqs_required",
            "true",
        )

    # Recompute deterministic state before certification. A failure leaves the
    # starting version in place even though safe file patches remain visible.
    write_if_changed(state_path, migrated_state, report)
    if report.changed_files:
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("compute-status.py")), str(project)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(
                "status recompute failed after safe migration:\n"
                + completed.stdout
                + completed.stderr
            )
        migrated_state = state_path.read_text()

    # A state file with type/enum errors on known fields cannot be certified:
    # the very counters and timestamps the stages rely on would be silently
    # miscomputed. Reported as manual reviews so the human fixes and reruns.
    for problem in validate_state(migrated_state):
        if problem.advisory:
            continue
        message = f".playbook-state.yml: {problem.render()}"
        if problem.path.startswith("template_provenance"):
            if message not in report.manual_reviews:
                report.add_provenance_review(message)
        else:
            report.manual_reviews.append(message)

    if cadences_path.exists():
        for problem in validate_cadences(cadences_path.read_text()):
            if not problem.advisory:
                report.manual_reviews.append(
                    f"playbook-cadences.yml: {problem.render()}"
                )

    if previous_version:
        checked = set(template_base.managed_files(playbook_root)) | {
            ".playbook-state.yml", "playbook-cadences.yml"
        }
        stale_refs = ["/v0.4/"]
        if prior_root is not None and prior_root != playbook_root:
            stale_refs.append(f"{prior_root}/v0.5/")
        for relative in sorted(checked):
            path = project / relative
            if not path.is_file():
                continue
            try:
                content = path.read_text()
            except UnicodeDecodeError:
                continue
            if any(ref in content for ref in stale_refs):
                report.manual_reviews.append(
                    f"{relative}: old playbook checkout reference remains after the public transition"
                )

    non_provenance_reviews = [
        review for review in report.manual_reviews
        if review not in report.provenance_reviews
    ]
    identity_only = bool(non_provenance_reviews) and all(
        "re-prove verified model identity" in review
        for review in non_provenance_reviews
    )
    # V0.5 certification is atomic: any unresolved review retains the exact
    # starting version so the same edition transition re-presents on retry.
    # Safe file changes remain visible, but the project is never stamped V0.5
    # until every required manual review is resolved.
    target_version = CURRENT_VERSION if not report.manual_reviews else starting_version
    migrated_state = replace_top_level_scalar(migrated_state, "playbook_version", target_version)
    certification_changed = target_version != starting_version or needs_cold_path
    if (not report.manual_reviews or identity_only) and (
        certification_changed or needs_upgrade_date_repair
    ):
        if re.search(r"(?m)^last_upgraded:", migrated_state):
            migrated_state = replace_top_level_scalar(migrated_state, "last_upgraded", today.isoformat())
        else:
            migrated_state, found = insert_before(
                migrated_state,
                "prereqs_required:",
                f"last_upgraded: {today.isoformat()}\n",
            )
            if not found:
                raise RuntimeError("cannot place required last_upgraded stamp in customized state")
    write_if_changed(state_path, migrated_state, report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--apply-safe", action="store_true", help="apply deterministic V0.5 changes or a V0.4 transition")
    parser.add_argument(
        "--adopt-current",
        action="append",
        default=[],
        metavar="FILE",
        help="accept FILE's current content as the agreed state: reset its recorded template "
        "base to the current render (use after resolving a reported merge conflict by hand)",
    )
    args = parser.parse_args(argv)
    if not args.apply_safe:
        parser.error("no changes made; pass --apply-safe after the user approves tiers 1 and 2")

    try:
        report = upgrade_project(args.project, adopt_current=set(args.adopt_current))
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"upgrade failed: {error}", file=sys.stderr)
        print("No certification completed; safe file changes may remain, so inspect the diff before retrying.", file=sys.stderr)
        return 1
    for changed in report.changed_files:
        print(f"changed: {changed}")
    for note in report.notes:
        print(f"note: {note}")
    for review in report.manual_reviews:
        print(f"manual review: {review}")
    if report.manual_reviews:
        print("Safe migrations applied, but the project was not certified current.")
        return 2
    print("Safe migrations applied; run stage 00 cold path to certify the project.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

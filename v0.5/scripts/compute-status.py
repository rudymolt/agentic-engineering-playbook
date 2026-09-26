#!/usr/bin/env python3
"""Recompute the generated status block in a project's playbook state file."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from playbook_state import (  # noqa: E402
    parse_datetime,
    is_canonical_relative_path,
    parse_scalar,
    parse_top_level_list,
    parse_top_level_map,
    quote_yaml_string,
    strip_inline_comment,
    validate_cadences,
    validate_state,
)

STATUS_ORDER = ["aligning", "spec-written", "sliced", "in-flight", "ready-to-ship"]
LEGACY_STATUS_ALIASES = {"prd-written": "spec-written"}
SEVERITY_ORDER = {"insist": 0, "nudge": 1}
COUNT_LABELS = {
    "slices_since_last_architecture_review": "slices since last review",
}
RESUMABLE_PLAN_ROUTE_STATUSES = {"selected", "running", "waiting_manual", "blocked"}


def iso_now(now: datetime) -> str:
    return now.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_active_features(text: str) -> list[dict[str, Any]]:
    return parse_top_level_list(text, "active_features")


def parse_pending_model_routes(text: str) -> list[dict[str, Any]]:
    return parse_top_level_list(text, "pending_model_routes")


def parse_cadences(text: str) -> list[dict[str, Any]]:
    """Parse only entries owned by the top-level ``cadences`` YAML list.

    A cadence file may carry arbitrary top-level project metadata after that
    list.  Parsing each item through EOF lets identically named metadata fields
    overwrite a cadence's thresholds, so use the shared list parser's explicit
    top-level boundary before selecting the fields used by status calculation.
    """
    known_fields = {
        "id", "type", "counter", "nudge_threshold", "insist_threshold", "severity", "only_if",
    }
    return [
        {key: value for key, value in cadence.items() if key in known_fields}
        for cadence in parse_top_level_list(text, "cadences")
    ]


def allowed_statuses(state_text: str) -> list[str]:
    match = re.search(r"^# Allowed statuses:\s*(.+)$", state_text, re.M)
    if match:
        statuses = [status.strip() for status in match.group(1).split(",")]
        return list(dict.fromkeys(LEGACY_STATUS_ALIASES.get(status, status) for status in statuses))

    current = parse_status_block(state_text)
    keys = list(current.get("features_by_stage", {}).keys())
    if not keys:
        return STATUS_ORDER
    return list(dict.fromkeys(LEGACY_STATUS_ALIASES.get(status, status) for status in keys))


def days_since(value: Any, today: date) -> int | None:
    timestamp = parse_datetime(value)
    if timestamp is None:
        return None
    return max(0, (today - timestamp.date()).days)


def severity_for(value: int, nudge: int | None, insist: int | None) -> str | None:
    if insist is not None and value >= insist:
        return "insist"
    if nudge is not None and value >= nudge:
        return "nudge"
    return None


def threshold_detail(nudge: int | None, insist: int | None) -> str:
    if nudge is not None and insist is not None:
        return f"nudge at {nudge}, insist at {insist}"
    if nudge is not None:
        return f"nudge at {nudge}"
    if insist is not None:
        return f"insist at {insist}"
    return "no thresholds set"


def plural(value: int, singular: str, plural_form: str | None = None) -> str:
    return singular if value == 1 else (plural_form or f"{singular}s")


def verification_map_clock(
    decisions: dict[str, Any],
    last_run: dict[str, Any],
    today: date,
    nudge: int | None,
    insist: int | None,
    harness_available: bool | None,
) -> tuple[int | None, str, str | None]:
    """Evaluate the selected, explicitly opted-in verification-map clock."""
    if decisions.get("verification_map_maintenance") is not True:
        return None, "", None

    path = decisions.get("verification_harness_path")
    if not isinstance(path, str) or not is_canonical_relative_path(path):
        return 0, "configuration error: select one canonical project-relative verification harness directory", "insist"
    bound_path = decisions.get("verification_harness_binding")
    if not isinstance(bound_path, str) or not is_canonical_relative_path(bound_path):
        return 0, "configuration error: bind the selected verification harness through the stage-owned selection command", "insist"
    if bound_path != path:
        return 0, "configuration error: selected verification harness differs from its bound audit target; reselect it through the stage-owned selection command", "insist"

    enabled = parse_datetime(last_run.get("verification_map_enabled"))
    accepted = parse_datetime(last_run.get("verification_map_maintenance"))
    if enabled is None:
        return 0, "configuration error: record the actual initial verification-map opt-in timestamp", "insist"
    if last_run.get("verification_map_maintenance") is not None and accepted is None:
        return 0, "configuration error: verification-map maintenance must be null or an ISO 8601 timestamp", "insist"

    baseline = max(timestamp for timestamp in (enabled, accepted) if timestamp is not None)
    # Calendar-day thresholds are UTC boundaries, including for an explicit
    # offset timestamp whose local date differs from its UTC date.
    value = max(0, (today - baseline.astimezone(timezone.utc).date()).days)
    detail = (
        f"{value} {plural(value, 'day')} since verification-map enable or accepted complete audit "
        f"({threshold_detail(nudge, insist)})"
    )
    if harness_available is False:
        return value, f"selected verification harness is missing or unsafe: {path}; {detail}", "insist"
    return value, detail, None


def compute_status(
    state_text: str,
    cadences_text: str,
    now: datetime,
    has_ui: bool | None = None,
    harness_available: bool | None = None,
) -> dict[str, Any]:
    counters = parse_top_level_map(state_text, "counters")
    decisions = parse_top_level_map(state_text, "decisions")
    last_run = parse_top_level_map(state_text, "last_run")
    features = parse_active_features(state_text)
    pending_routes = parse_pending_model_routes(state_text)
    pending_plan_routes = sum(
        1 for route in pending_routes
        if route.get("status") in RESUMABLE_PLAN_ROUTE_STATUSES
    )
    pending_closeouts = len(parse_top_level_list(state_text, "pending_closeouts"))
    statuses = allowed_statuses(state_text)
    today = now.astimezone(timezone.utc).date()

    features_by_stage = {status: 0 for status in statuses}
    slices_open = 0
    for feature in features:
        status = str(feature.get("status") or "unknown")
        status = LEGACY_STATUS_ALIASES.get(status, status)
        features_by_stage.setdefault(status, 0)
        features_by_stage[status] += 1
        open_count = feature.get("slices_open")
        if isinstance(open_count, int):
            slices_open += open_count

    overdue: list[dict[str, Any]] = []
    for order, cadence in enumerate(parse_cadences(cadences_text)):
        cadence_type = cadence.get("type")
        if cadence_type == "event":
            continue
        # only_if guards (currently just project_has_ui) suppress a cadence when
        # the project observably lacks the surface it audits. Unknown (None)
        # keeps the cadence active, preserving text-only evaluation behaviour.
        if cadence.get("only_if") == "project_has_ui" and has_ui is False:
            continue

        cadence_id = str(cadence.get("id"))
        counter = cadence.get("counter")
        nudge = cadence.get("nudge_threshold")
        insist = cadence.get("insist_threshold")
        if not isinstance(nudge, int):
            nudge = None
        if not isinstance(insist, int):
            insist = None

        value: int | None = None
        detail_subject = ""
        if cadence_type == "count" and isinstance(counter, str):
            raw_value = counters.get(counter, 0)
            value = raw_value if isinstance(raw_value, int) else 0
            detail_subject = COUNT_LABELS.get(counter, counter.replace("_", " "))
        elif cadence_type == "time" and isinstance(counter, str):
            if cadence_id == "verification-map-drift":
                value, detail_subject, forced_severity = verification_map_clock(
                    decisions, last_run, today, nudge, insist, harness_available
                )
                if value is None:
                    continue
                severity = forced_severity or severity_for(value, nudge, insist)
                if severity is None:
                    continue
                overdue.append({
                    "cadence_id": cadence_id,
                    "severity": severity,
                    "detail": detail_subject,
                    "_order": order,
                })
                continue
            if cadence_id == "doc-close-after-ship":
                ship = parse_datetime(last_run.get("feature_ship"))
                doc_close = parse_datetime(last_run.get("doc_close"))
                if ship is None or (doc_close is not None and doc_close >= ship):
                    continue
                value = max(0, (today - ship.date()).days)
                detail_subject = f"{plural(value, 'day')} since feature ship without doc-close"
            elif counter.startswith("days_since_last_"):
                source = counter.removeprefix("days_since_last_")
                value = days_since(last_run.get(source), today)
                if value is None:
                    continue
                detail_subject = f"{plural(value, 'day')} since last {source.replace('_', ' ')}"

        if value is None:
            continue
        severity = severity_for(value, nudge, insist)
        if severity is None:
            continue
        overdue.append({
            "cadence_id": cadence_id,
            "severity": severity,
            "detail": f"{value} {detail_subject} ({threshold_detail(nudge, insist)})",
            "_order": order,
        })

    overdue.sort(key=lambda item: (SEVERITY_ORDER.get(str(item["severity"]), 99), item["_order"]))
    for item in overdue:
        item.pop("_order", None)

    feature_count = len(features)
    active_parts = []
    for status in statuses:
        count = features_by_stage.get(status, 0)
        if count:
            active_parts.append(status if count == 1 else f"{count} {status}")
    if slices_open:
        active_parts.append(f"{slices_open} {plural(slices_open, 'slice')} open")
    stage_summary = ", ".join(active_parts) if active_parts else "none"
    feature_phrase = f"{feature_count} {plural(feature_count, 'feature')} in flight ({stage_summary})"
    if overdue:
        cadence_word = plural(len(overdue), "cadence")
        headline = f"{len(overdue)} {cadence_word} overdue; {feature_phrase}"
    else:
        headline = f"nothing overdue; {feature_phrase}"
    if pending_closeouts:
        headline += f"; {pending_closeouts} feature {plural(pending_closeouts, 'closeout')} pending"
    if pending_plan_routes:
        headline += f"; {pending_plan_routes} pending Plan {plural(pending_plan_routes, 'route')}"

    return {
        "headline": headline,
        "overdue": overdue,
        "features_by_stage": features_by_stage,
        "pending_plan_routes": pending_plan_routes,
        "pending_closeouts": pending_closeouts,
    }


def render_status_block(status: dict[str, Any], timestamp: str) -> str:
    lines = [
        "status:",
        f"  computed_at: {timestamp}",
        f"  headline: {quote_yaml_string(status['headline'])}",
    ]
    overdue = status["overdue"]
    if overdue:
        lines.append("  overdue:")
        for item in overdue:
            lines.append(f"    - cadence_id: {item['cadence_id']}")
            lines.append(f"      severity: {item['severity']}")
            lines.append(f"      detail: {quote_yaml_string(item['detail'])}")
    else:
        lines.append("  overdue: []")
    lines.append("  features_by_stage:")
    for key, value in status["features_by_stage"].items():
        lines.append(f"    {key}: {value}")
    lines.append(f"  pending_plan_routes: {status['pending_plan_routes']}")
    lines.append(f"  pending_closeouts: {status['pending_closeouts']}")
    return "\n".join(lines)


def find_status_region(text: str) -> tuple[int, int]:
    match = re.search(r"(?m)^status:\n", text)
    if not match:
        raise ValueError(".playbook-state.yml has no status: block")
    start = match.start()
    pos = match.end()
    while pos < len(text):
        line_end = text.find("\n", pos)
        if line_end == -1:
            line_end = len(text)
            next_pos = len(text)
        else:
            next_pos = line_end + 1
        line = text[pos:line_end]
        if line == "" or not line.startswith(" "):
            return start, pos
        pos = next_pos
    return start, len(text)


def replace_last_updated(text: str, timestamp: str) -> str:
    pattern = re.compile(r"(?m)^(last_updated:\s*)([^#\n]*?)(\s+#.*)?$")

    def replacement(match: re.Match[str]) -> str:
        return f"{match.group(1)}{timestamp}{match.group(3) or ''}"

    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(".playbook-state.yml has no last_updated: line")
    return updated


def rewrite_state_text(
    state_text: str,
    cadences_text: str,
    now: datetime,
    has_ui: bool | None = None,
    harness_available: bool | None = None,
) -> str:
    timestamp = iso_now(now)
    status = compute_status(state_text, cadences_text, now, has_ui, harness_available)
    start, end = find_status_region(state_text)
    rewritten = state_text[:start] + render_status_block(status, timestamp) + "\n" + state_text[end:]
    return replace_last_updated(rewritten, timestamp)


def parse_status_block(state_text: str) -> dict[str, Any]:
    start, end = find_status_region(state_text)
    lines = state_text[start:end].splitlines()
    parsed: dict[str, Any] = {
        "overdue": [], "features_by_stage": {}, "pending_plan_routes": 0, "pending_closeouts": 0,
    }
    section: str | None = None
    current_overdue: dict[str, Any] | None = None
    for line in lines[1:]:
        if match := re.match(r"^  computed_at:\s*(.*)$", line):
            parsed["computed_at"] = parse_scalar(match.group(1))
        elif match := re.match(r"^  headline:\s*(.*)$", line):
            parsed["headline"] = parse_scalar(match.group(1))
        elif re.match(r"^  overdue:\s*\[\]\s*$", line):
            parsed["overdue"] = []
            section = None
        elif re.match(r"^  overdue:\s*$", line):
            parsed["overdue"] = []
            section = "overdue"
        elif re.match(r"^  features_by_stage:\s*", line):
            section = "features"
        elif match := re.match(r"^  pending_plan_routes:\s*(.*)$", line):
            parsed["pending_plan_routes"] = parse_scalar(match.group(1))
            section = None
        elif match := re.match(r"^  pending_closeouts:\s*(.*)$", line):
            parsed["pending_closeouts"] = parse_scalar(match.group(1))
            section = None
        elif section == "overdue" and (match := re.match(r"^    - cadence_id:\s*(.*)$", line)):
            current_overdue = {"cadence_id": parse_scalar(match.group(1))}
            parsed["overdue"].append(current_overdue)
        elif section == "overdue" and current_overdue is not None and (match := re.match(r"^      ([A-Za-z0-9_-]+):\s*(.*)$", line)):
            current_overdue[match.group(1)] = parse_scalar(match.group(2))
        elif section == "features" and (match := re.match(r"^    ([A-Za-z0-9_-]+):\s*(.*)$", line)):
            parsed["features_by_stage"][match.group(1)] = parse_scalar(match.group(2))
    return parsed


def status_is_current(
    state_text: str,
    cadences_text: str,
    now: datetime,
    has_ui: bool | None = None,
    harness_available: bool | None = None,
) -> tuple[bool, list[str]]:
    expected = compute_status(state_text, cadences_text, now, has_ui, harness_available)
    actual = parse_status_block(state_text)
    problems: list[str] = []
    for key in ("headline", "overdue", "features_by_stage", "pending_plan_routes", "pending_closeouts"):
        if actual.get(key) != expected.get(key):
            problems.append(f"status.{key} is stale or wrong")

    last_updated_match = re.search(r"(?m)^last_updated:\s*([^#\n]+)", state_text)
    computed_at = parse_datetime(actual.get("computed_at"))
    last_updated = parse_datetime(parse_scalar(last_updated_match.group(1)) if last_updated_match else None)
    if computed_at is None:
        problems.append("status.computed_at is missing or invalid")
    if last_updated is None:
        problems.append("last_updated is missing or invalid")
    if computed_at is not None and last_updated is not None and computed_at < last_updated:
        problems.append("status.computed_at predates last_updated")
    return not problems, problems


def project_has_ui(project_root: Path) -> bool:
    return (project_root / "DESIGN-GLOSSARY.md").exists() or (project_root / "design-glossary").is_dir()


def verification_harness_available(project_root: Path, state_text: str) -> bool | None:
    """Check an opted-in selection without allowing a missing harness to hide age."""
    decisions = parse_top_level_map(state_text, "decisions")
    if decisions.get("verification_map_maintenance") is not True:
        return None
    path = decisions.get("verification_harness_path")
    if not isinstance(path, str) or not is_canonical_relative_path(path):
        return None
    root = project_root.resolve()
    try:
        target = (project_root / path).resolve()
        return target.is_relative_to(root) and target.is_dir()
    except (OSError, RuntimeError):
        return False


def _top_level_block_bounds(text: str, block_name: str) -> tuple[int, int]:
    match = re.search(rf"(?m)^{re.escape(block_name)}:\s*(?:#.*)?$", text)
    if match is None:
        raise ValueError(f".playbook-state.yml has no {block_name}: block")
    start = match.end() + (1 if match.end() < len(text) and text[match.end()] == "\n" else 0)
    next_block = re.search(r"(?m)^[A-Za-z0-9_-]+:", text[start:])
    end = start + next_block.start() if next_block else len(text)
    return start, end


def _replace_map_value(text: str, block_name: str, key: str, value: str) -> str:
    """Replace one managed map scalar without disturbing adjacent custom text."""
    start, end = _top_level_block_bounds(text, block_name)
    block = text[start:end]
    # YAML permits an empty null after the colon. Whitespace here must stay
    # on this line, including before a comment, or the next field is consumed.
    pattern = re.compile(rf"(?m)^(  {re.escape(key)}:[ \t]*)[^#\r\n]*?([ \t]+#[^\r\n]*)?$")

    def replacement(match: re.Match[str]) -> str:
        prefix = match.group(1)
        if prefix.endswith(":"):
            prefix += " "
        return f"{prefix}{value}{match.group(2) or ''}"

    rewritten, count = pattern.subn(replacement, block, count=1)
    if count == 0:
        suffix = "" if not block or block.endswith("\n") else "\n"
        rewritten = block + suffix + f"  {key}: {value}\n"
    return text[:start] + rewritten + text[end:]


def select_verification_harness(
    project_root: Path,
    path: str,
    enabled_at: datetime | None = None,
    now: datetime | None = None,
) -> str:
    """Atomically record an explicit stage-owned verification-harness selection.

    The persisted binding makes a hand-edited target mismatch actionable.  A
    new target gets a new enable boundary and no audit credit; a previously
    bound target keeps its history, including across a quiet disable/re-enable.
    """
    if not is_canonical_relative_path(path):
        raise ValueError(
            "verification harness path must be one canonical, safe project-relative directory "
            "without controls, YAML-significant punctuation, or edge whitespace"
        )
    now = now or datetime.now(timezone.utc)
    enabled_at = enabled_at or now
    state_text, cadences_text = read_project_files(project_root)
    decisions = parse_top_level_map(state_text, "decisions")
    previous_last_run = parse_top_level_map(state_text, "last_run")
    same_target = decisions.get("verification_harness_binding") == path
    # Quote the validated scalar so ordinary safe names (including an internal
    # space) remain valid YAML in the position-preserving state editor.
    scalar_path = quote_yaml_string(path)
    selected = _replace_map_value(state_text, "decisions", "verification_harness_path", scalar_path)
    selected = _replace_map_value(selected, "decisions", "verification_map_maintenance", "true")
    selected = _replace_map_value(selected, "decisions", "verification_harness_binding", scalar_path)
    if not same_target:
        selected = _replace_map_value(selected, "last_run", "verification_map_enabled", iso_now(enabled_at))
        selected = _replace_map_value(selected, "last_run", "verification_map_maintenance", "null")
    rewritten = rewrite_state_text(
        selected, cadences_text, now, project_has_ui(project_root),
        verification_harness_available(project_root, selected),
    )
    validation_errors = [
        problem.render() for problem in validate_state(rewritten) if not problem.advisory
    ]
    effective_decisions = parse_top_level_map(rewritten, "decisions")
    if (
        effective_decisions.get("verification_harness_path") != path
        or effective_decisions.get("verification_map_maintenance") is not True
        or effective_decisions.get("verification_harness_binding") != path
    ):
        validation_errors.append(
            "selected verification harness was not preserved as its enabled, bound target"
        )
    effective_last_run = parse_top_level_map(rewritten, "last_run")
    if same_target:
        for key in ("verification_map_enabled", "verification_map_maintenance"):
            if effective_last_run.get(key) != previous_last_run.get(key):
                validation_errors.append(
                    f"same-target selection changed preserved {key} history"
                )
    elif (
        effective_last_run.get("verification_map_enabled") != iso_now(enabled_at)
        or effective_last_run.get("verification_map_maintenance") is not None
    ):
        validation_errors.append(
            "new selected verification harness did not receive a fresh enable boundary without audit credit"
        )
    if validation_errors:
        raise ValueError(
            "refusing to replace .playbook-state.yml with invalid selected-harness state: "
            + "; ".join(validation_errors)
        )
    (project_root / ".playbook-state.yml").write_text(rewritten)
    return rewritten


def read_project_files(project_root: Path) -> tuple[str, str]:
    for name in (".playbook-state.yml", "playbook-cadences.yml"):
        if not (project_root / name).exists():
            raise FileNotFoundError(
                f"{project_root / name} not found — this project is not bootstrapped. "
                "Run /ai-playbook-bootstrap-project (or the bootstrap sequence in the playbook README) first."
            )
    return (
        (project_root / ".playbook-state.yml").read_text(),
        (project_root / "playbook-cadences.yml").read_text(),
    )


def recompute_project(project_root: Path, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    state_text, cadences_text = read_project_files(project_root)
    rewritten = rewrite_state_text(
        state_text, cadences_text, now, project_has_ui(project_root),
        verification_harness_available(project_root, state_text),
    )
    (project_root / ".playbook-state.yml").write_text(rewritten)
    return rewritten


def schema_problems(state_text: str, cadences_text: str) -> list[str]:
    """Rendered non-advisory schema problems for both project files."""
    return [
        problem.render()
        for problem in validate_state(state_text) + validate_cadences(cadences_text)
        if not problem.advisory
    ]


def check_project(project_root: Path, now: datetime | None = None) -> tuple[bool, list[str]]:
    now = now or datetime.now(timezone.utc)
    state_text, cadences_text = read_project_files(project_root)
    ok, problems = status_is_current(
        state_text, cadences_text, now, project_has_ui(project_root),
        verification_harness_available(project_root, state_text),
    )
    invalid = schema_problems(state_text, cadences_text)
    return ok and not invalid, problems + invalid


def main(argv: list[str] | None = None, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute .playbook-state.yml status block.")
    parser.add_argument("project_root", type=Path)
    parser.add_argument("--check", action="store_true", help="verify the generated block without writing")
    parser.add_argument(
        "--select-verification-harness", metavar="PATH",
        help="explicit stage-owned selection; binds PATH, enables its clock, and clears credit only for a new target",
    )
    parser.add_argument(
        "--verification-map-enabled-at", metavar="ISO_TIMESTAMP",
        help="actual selection time for --select-verification-harness (default: current UTC time)",
    )
    args = parser.parse_args(argv)

    selection_requested = args.select_verification_harness is not None
    selection_time_requested = args.verification_map_enabled_at is not None
    if args.check and selection_requested:
        parser.error("--check cannot be combined with --select-verification-harness")
    if selection_time_requested and not selection_requested:
        parser.error("--verification-map-enabled-at requires --select-verification-harness")

    project_root = args.project_root.resolve()
    try:
        if selection_requested:
            current_time = now or datetime.now(timezone.utc)
            selection_time = current_time
            if selection_time_requested:
                selection_time = parse_datetime(args.verification_map_enabled_at)
                if selection_time is None:
                    raise ValueError("--verification-map-enabled-at must be an ISO 8601 timestamp")
            select_verification_harness(
                project_root, args.select_verification_harness, selection_time, current_time
            )
            print(f"Selected verification harness: {args.select_verification_harness}")
            return 0
        if args.check:
            ok, failures = check_project(project_root, now)
            if ok:
                print(".playbook-state.yml status block is current.")
                return 0
            print(".playbook-state.yml status block is stale or wrong:")
            for failure in failures:
                print(f"- {failure}")
            return 1

        recompute_project(project_root, now)
        # Non-blocking: a type error on a known field silently skews the very
        # numbers this script computes, so surface it at every recompute.
        state_text, cadences_text = read_project_files(project_root)
        for problem in schema_problems(state_text, cadences_text):
            print(f"warning: {problem}", file=sys.stderr)
    except (FileNotFoundError, ValueError) as error:
        print(f"compute-status failed: {error}", file=sys.stderr)
        return 1
    print(f"Recomputed {project_root / '.playbook-state.yml'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

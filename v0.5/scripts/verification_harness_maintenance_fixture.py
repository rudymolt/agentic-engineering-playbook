"""Execute a bounded maintenance audit against the controlled harness fixture.

The module is test-only evidence for the local maintenance skill.  It deliberately
uses the generated harness's real source and public CLI commands rather than a
mocked coverage result.  It is not installed in, or a substitute for, a project.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path


# These are the bounded recipes/effects implemented by the admitted fixture
# driver, not a Markdown interpreter for arbitrary project harnesses.
MAP_BEHAVIORS = {
    "create-note": ("create a note, then observe it through a separate list process",
                    {"notes": ["fixture note"]}),
    "list-notes": ("create two notes, then observe their order through list",
                   {"notes": ["fixture note", "second note"]}),
    "reject-broken": ("reject an empty note with exit 1 and observe unchanged state",
                      {"rejection": {"error": "note must not be empty"},
                       "remaining": {"notes": ["fixture note"]}}),
}


def _result(outcome: str, **values) -> dict:
    return {"outcome": outcome, "covered": [], "evidence": [], "map_drift": [],
            "harness_drift": [], "defects": [], **values}


def _index_ids(index: Path) -> list[tuple[str, str]]:
    pairs = []
    for line in index.read_text().splitlines():
        line = line.strip()
        if not re.match(r"(?:[-*+]|\d+[.)])\s", line):
            continue
        match = re.fullmatch(r"(?:[-*+]|\d+[.)])\s+\[([^]]+)\]\(([^)]+)\)", line)
        if not match:
            raise ValueError(f"malformed feature-map entry: {line}")
        pairs.append(match.groups())
    return pairs


def _owned(root: Path, locator: str) -> Path:
    path = Path(locator)
    if path.is_absolute() or ".." in path.parts or "\\" in locator:
        raise ValueError(f"unsafe path outside harness-owned scope: {locator}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError(f"path outside harness-owned scope: {locator}")
    return resolved


def _entry(root: Path, feature: str) -> Path:
    if not isinstance(feature, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", feature):
        raise ValueError(f"unsafe feature ID: {feature}")
    return _owned(root, f"features/{feature}.md")


def _preflight(root: Path) -> None:
    # Check every known write destination and mapped path before even a report.
    for locator in ("features", "features/README.md", "reports", "defects", "evidence",
                    ".runs", ".owned-run", "drive.py", "doctor.py", "target.json"):
        _owned(root, locator)
    index = root / "features/README.md"
    if index.is_file():
        for feature, locator in _index_ids(index):
            _entry(root, feature)
            _owned(root, f"features/{locator}")
            if Path(locator).is_absolute() or locator != f"{feature}.md":
                raise ValueError(f"unsafe map entry locator: {locator}")
    for path in (root / "features").glob("*.md"):
        _owned(root, str(path.relative_to(root)))


def _map_problems(root: Path) -> tuple[list[str], list[str]]:
    features = root / "features"
    index = features / "README.md"
    if not index.is_file():
        return ["missing feature-map index"], []
    pairs = _index_ids(index)
    ids = [name for name, _ in pairs]
    problems: list[str] = []
    if not ids:
        problems.append("empty declared map")
    duplicates = sorted({name for name in ids if ids.count(name) > 1})
    if duplicates:
        problems.append("duplicate feature IDs: " + ", ".join(duplicates))
    for name, locator in pairs:
        if locator != f"{name}.md" or not (features / locator).is_file():
            problems.append(f"inaccessible map entry: {name}")
    indexed = {f"{name}.md" for name in ids}
    actual = {path.name for path in features.glob("*.md") if path.name != "README.md"}
    orphaned = sorted(actual - indexed)
    if orphaned:
        problems.append("orphaned feature files: " + ", ".join(orphaned))
    return problems, ids


def _source_and_map_drift(root: Path, ids: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    app = root.parents[2] / "fixture-app" / "cli.py"
    if not app.is_file():
        return ["fixture application source is inaccessible"], [], [], []
    source = app.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ["fixture application source cannot be parsed"], [], [], []
    # Bounded to this fixture's argparse registrations; unknown/dynamic routing
    # is a coverage block, not a claim about arbitrary application frameworks.
    registrations = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser"]
    if not registrations or any(not node.args or not isinstance(node.args[0], ast.Constant)
                                or not isinstance(node.args[0].value, str)
                                or node.keywords and any(k.arg == "aliases" for k in node.keywords)
                                for node in registrations):
        return ["public CLI entry-point enumeration is incomplete"], [], [], []
    commands = sorted({node.args[0].value for node in registrations})
    gaps = sorted(set(commands) - {"create", "list", "status"})
    missing = sorted({"create", "list", "status"} - set(commands))
    problems = (["unmapped public CLI entry points: " + ", ".join(gaps)] if gaps else [])
    if missing:
        problems.append("missing public CLI entry points: " + ", ".join(missing))
    drift: list[str] = []
    for feature in ids:
        entry = root / "features" / f"{feature}.md"
        text = entry.read_text()
        if "fixture-app/cli.py public create/list commands." not in text:
            drift.append(feature)
    return problems, drift, commands, gaps


def _mapped_recipes(root: Path, ids: list[str]) -> tuple[list[str], list[str], dict]:
    """Admit exactly one complete supported Drive and expectation field per entry.

    Whitespace wrapping is harmless; additional instructions, malformed fields,
    unknown commands, or changed expectations require explicit fixture support.
    Never execute map text as shell code or silently replace it with an ID.
    """
    problems, gaps, recipes = [], [], {}
    for feature in ids:
        try:
            if feature not in MAP_BEHAVIORS:
                raise ValueError("unsupported mapped feature")
            text = _entry(root, feature).read_text()
            labels = ("Purpose", "Entry point", "Prerequisites", "Drive",
                      "Expected observation and effects", "Limitations", "Last verification")
            markers = list(re.finditer(r"^\*\*([^*\n]+):\*\*[ \t]*", text, flags=re.M))
            if tuple(marker[1] for marker in markers) != labels:
                raise ValueError("expected exactly one ordered field each: " + ", ".join(labels))
            if text[:markers[0].start()].strip() != f"# {feature}":
                raise ValueError("unsupported map heading or preamble")
            # A field extends to the next declared field, including every blank
            # line and continuation paragraph. Unknown/duplicate field markers
            # cannot shorten it because the complete schema is checked above.
            values = {label: text[marker.end():markers[i + 1].start()
                                  if i + 1 < len(markers) else len(text)]
                      for i, (label, marker) in enumerate(zip(labels, markers))}

            def field(label: str) -> str:
                return " ".join(values[label].split())

            drive = field("Drive")
            match = re.fullmatch(
                r"from the harness directory, `python3 (drive\.py) ([a-z][a-z0-9-]*)( --report-only)?`\.",
                drive,
            )
            if not match or match[2] != feature:
                raise ValueError("unsupported or malformed Drive recipe")
            expected, effect = MAP_BEHAVIORS[feature]
            if field("Expected observation and effects") != (
                expected + "; each run owns a fresh notes file, removes that file on exit, "
                "and retains command outputs."
            ):
                raise ValueError("unsupported or malformed Expected observation and effects")
            # The only adaptation is suppressing Last verification writes. Both
            # command arguments come from the validated declared recipe.
            recipes[feature] = ([match[1], match[2], "--report-only"], effect)
        except (ValueError, OSError, RuntimeError) as error:
            problems.append(f"{feature}: {error}")
            gaps.append(feature)
    return problems, gaps, recipes


def _proves_mapped_effect(record: dict, feature: str, effect: dict) -> bool:
    return (record.get("feature") == feature and record.get("observation") == "passed"
            and record.get("effect") == effect and record.get("owned_state_removed") is True)


def _write_report(root: Path, report: dict) -> str:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    path = reports / f"audit-{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return str(path.relative_to(root))


def _write_defect(root: Path, error: str) -> str:
    defects = root / "defects"
    defects.mkdir(exist_ok=True)
    path = defects / f"product-regression-{uuid.uuid4().hex}.md"
    path.write_text(
        "# Product regression\n\n"
        "The controlled fixture's Doctor reported healthy readiness, but its public "
        "Drive command did not produce the declared observation.\n\n"
        f"- Observed failure: `{error}`\n"
        "- Required owner: the product task workflow; do not redefine the map or edit "
        "product behavior from maintenance.\n"
    )
    return str(path.relative_to(root))


def _execution_snapshot(root: Path) -> dict[str, str]:
    """Bind only the controlled fixture's persistent execution inputs."""
    app = root.parents[2] / "fixture-app"
    paths = {name: _owned(root, name) for name in ("drive.py", "doctor.py", "target.json")}
    paths.update({f"fixture-app/{name}": app / name for name in ("cli.py", "instance.json")})
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def audit(root: Path, *, environment: dict[str, str] | None = None,
          inspect_source: bool = True, run_live: bool = True,
          evidence_destination: Path | None = None, reviewer: str = "report-only") -> dict:
    """Inspect every declared entry and exercise every real mapped command.

    The returned JSON-compatible result is a report-only inspection.  Its only
    writes are declared retained evidence from the existing harness and a report;
    it never corrects maps, helpers, or product files.
    """
    root = root.resolve()
    try:
        _preflight(root)
    except (ValueError, OSError, RuntimeError) as error:
        return _result("blocked", reason=str(error), reviewer=reviewer)
    map_problems, ids = _map_problems(root)
    if map_problems:
        report = _result("blocked", reason="; ".join(map_problems), reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    if not inspect_source:
        report = _result("blocked", reason="source coverage skipped", reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    source_problems, map_drift, commands, gaps = _source_and_map_drift(root, ids)
    recipe_problems, recipe_gaps, recipes = _mapped_recipes(root, ids)
    gaps = sorted(set(gaps + recipe_gaps))
    if source_problems or map_drift or recipe_problems:
        report = _result("blocked", reason="; ".join(source_problems + recipe_problems
                                                    or ["map drift requires authorization"]),
                         map_drift=map_drift, reviewer=reviewer,
                         public_entry_points=commands, coverage_gaps=gaps)
        report["report"] = _write_report(root, report)
        return report
    if not run_live:
        report = _result("blocked", reason="live coverage skipped", reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    # Evidence-only compatibility covers the whole controlled execution chain.
    # This is fixture admission, not a sandbox for arbitrary application code.
    templates = Path(__file__).with_name("fixtures") / "verification-harness"
    app = root.parents[2] / "fixture-app/cli.py"
    try:
        drift = [name for name in ("drive.py", "doctor.py")
                 if (root / name).read_bytes() != (templates / name).read_bytes()]
        target = json.loads((root / "target.json").read_text())
        if (root / target["cli"]).resolve() != app.resolve():
            drift.append("target.json")
        app_drift = app.read_bytes() != (templates / "cli.py").read_bytes()
        execution_snapshot = _execution_snapshot(root)
    except (OSError, ValueError, KeyError, TypeError):
        drift, app_drift = ["inaccessible fixture execution chain"], False
    if drift or app_drift:
        report = _result("blocked", reason="fixture execution chain report-only compatibility is unverified",
                         harness_drift=drift, source_gaps=["fixture-app/cli.py"] if app_drift else [],
                         reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    env = dict(os.environ if environment is None else environment)
    if evidence_destination is not None:
        env["VERIFY_EVIDENCE_DIR"] = str(evidence_destination)
    if not env.get("VERIFY_EVIDENCE_DIR"):
        report = _result("blocked", reason="evidence destination unavailable", reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    try:
        Path(env["VERIFY_EVIDENCE_DIR"]).resolve().relative_to(root)
    except ValueError:
        report = _result("blocked", reason="evidence destination is outside the owned harness", reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    artifacts: list[str] = []
    for feature in ids:
        arguments, effect = recipes[feature]
        completed = subprocess.run(
            [sys.executable, str(root / arguments[0]), *arguments[1:]], cwd=root, env=env,
            text=True, capture_output=True, check=False,
        )
        if completed.returncode != 0:
            try:
                payload = json.loads(completed.stdout)
                artifact = payload.get("artifact")
                if artifact:
                    artifacts.append(str(Path(artifact).relative_to(root)))
                error = payload.get("error", completed.stderr.strip())
            except (json.JSONDecodeError, ValueError):
                error = completed.stderr.strip() or completed.stdout.strip()
            defect = _write_defect(root, error or "live command failed") if "behavior mismatch" in (error or "") else None
            report = _result("blocked", reason="live coverage failed", evidence=artifacts,
                             defects=[defect] if defect else [], reviewer=reviewer)
            report["report"] = _write_report(root, report)
            return report
        try:
            artifact = json.loads(completed.stdout)["artifact"]
            artifact_path = Path(artifact)
        except (json.JSONDecodeError, KeyError):
            report = _result("blocked", reason="live command produced no evidence", reviewer=reviewer)
            report["report"] = _write_report(root, report)
            return report
        if not artifact_path.is_file():
            report = _result("blocked", reason="live evidence is inaccessible", reviewer=reviewer)
            report["report"] = _write_report(root, report)
            return report
        artifacts.append(str(artifact_path.relative_to(root)))
        try:
            record = json.loads(artifact_path.read_text())
            if not _proves_mapped_effect(record, feature, effect):
                raise ValueError("live evidence does not prove declared observation/effect and cleanup")
        except (OSError, ValueError, AttributeError) as error:
            report = _result("blocked", reason=f"{feature}: {error}", evidence=artifacts,
                             coverage_gaps=[feature], reviewer=reviewer)
            report["report"] = _write_report(root, report)
            return report
    try:
        if _execution_snapshot(root) != execution_snapshot:
            raise ValueError("execution inputs changed during verification; fresh proof required")
    except (ValueError, OSError, RuntimeError) as error:
        report = _result("blocked", reason=str(error), evidence=artifacts, reviewer=reviewer)
        report["report"] = _write_report(root, report)
        return report
    report = _result("clean", covered=ids, evidence=artifacts, reviewer=reviewer,
                     execution_sha256=execution_snapshot,
                     public_entry_points=commands, coverage_gaps=gaps,
                     map_sha256={feature: hashlib.sha256(_entry(root, feature).read_bytes()).hexdigest()
                                 for feature in ids})
    report["report"] = _write_report(root, report)
    return report


def correct(root: Path, report: dict, *, authorized: bool) -> dict:
    """Apply the sole fixture-authorized correction: proven map entry-point drift."""
    root = root.resolve()
    drift = report.get("map_drift", [])
    try:
        _preflight(root)
        for locator in report.get("harness_drift", []):
            _owned(root, locator)
        paths = [_entry(root, feature) for feature in drift]
        problems, ids = _map_problems(root)
        if problems or any(feature not in ids for feature in drift):
            raise ValueError("correction requires accessible indexed map entries")
        if any(not path.is_file() for path in paths):
            raise ValueError("correction path is inaccessible")
        source_problems, current_drift, _, _ = _source_and_map_drift(root, ids)
        if (report.get("outcome") != "blocked" or source_problems
                or not set(drift).issubset(current_drift)
                or any("fixture-app/legacy-cli.py public create/list commands."
                       not in path.read_text() for path in paths)):
            raise ValueError("correction requires current proven legacy entry-point drift")
    except (ValueError, OSError, RuntimeError) as error:
        return _result("blocked", reason=str(error))
    if not drift:
        return _result("blocked", reason="no proven harness-owned map drift to correct")
    if not authorized:
        return _result("blocked", reason="report-only inspection cannot correct without scoped authorization")
    corrected: list[str] = []
    for feature in drift:
        path = root / "features" / f"{feature}.md"
        if not path.is_file():
            return _result("blocked", reason=f"map path is inaccessible: {feature}")
        text = path.read_text()
        text = text.replace("fixture-app/legacy-cli.py", "fixture-app/cli.py")
        text = re.sub(r"^\*\*Last verification:\*\*.*$",
                      "**Last verification:** invalidated by corrected entry point; fresh proof required.",
                      text, flags=re.M)
        path.write_text(text)
        corrected.append(feature)
    return _result("pending", verification="reproof-required", corrected_paths=corrected,
                   initial_reviewer=report.get("reviewer"),
                   reason="map-only correction applied; all declared paths need fresh independent verification")


def verify_corrected(root: Path, correction: dict, *, environment: dict[str, str], reviewer: str) -> dict:
    """Re-drive complete declared coverage after a correction, with a fresh reviewer id."""
    root = root.resolve()
    if correction.get("outcome") != "pending" or not correction.get("corrected_paths"):
        return _result("blocked", reason="no corrected paths require verification")
    if not correction.get("initial_reviewer") or not reviewer or reviewer == correction.get("initial_reviewer"):
        return _result("blocked", reason="fresh independent reviewer is required")
    try:
        _preflight(root)
        problems, ids = _map_problems(root)
        for feature in correction["corrected_paths"]:
            _entry(root, feature)
        if problems or not set(correction["corrected_paths"]).issubset(ids):
            raise ValueError("corrected paths are no longer completely mapped")
    except (ValueError, OSError, RuntimeError) as error:
        return _result("blocked", reason=str(error))
    result = audit(root, environment=environment, reviewer=reviewer)
    if result["outcome"] != "clean":
        return result
    result["outcome"] = "changed"
    result["corrected_paths"] = correction["corrected_paths"]
    result["initial_reviewer"] = correction["initial_reviewer"]
    result["verification"] = "fresh-independent-pass"
    result["reason"] = "complete coverage re-driven after authorized correction"
    result["report"] = _write_report(root, {key: value for key, value in result.items() if key != "report"})
    return result


def accept_maintenance(root: Path, report: dict, *, authorized: bool) -> dict:
    """Stage-owned acceptance records proven evidence; inspection never calls this.

    This fixture updates map records only. It implements no S3 clock/state.
    """
    root = root.resolve()
    if not authorized:
        return _result("blocked", reason="maintenance record updates require scoped authorization")
    try:
        _preflight(root)
        problems, ids = _map_problems(root)
        if (problems or report.get("outcome") not in {"clean", "changed"}
                or set(report.get("covered", [])) != set(ids)):
            raise ValueError("only complete clean/changed evidence can be accepted")
        recipe_problems, gaps, recipes = _mapped_recipes(root, ids)
        if recipe_problems:
            return _result("blocked", reason="; ".join(recipe_problems), coverage_gaps=gaps)
        if report["outcome"] == "changed" and report.get("verification") != "fresh-independent-pass":
            raise ValueError("corrected paths require fresh independent verification")
        if report.get("execution_sha256") != _execution_snapshot(root):
            raise ValueError("execution inputs changed since verification; fresh proof required")
        records = {}
        for locator in report["evidence"]:
            artifact = _owned(root, locator)
            record = json.loads(artifact.read_text())
            if record["observation"] != "passed" or record["feature"] in records:
                raise ValueError("accepted evidence must uniquely prove each feature")
            records[record["feature"]] = (artifact, record)
        if set(records) != set(ids):
            raise ValueError("accepted evidence does not cover the current map")
        for feature in ids:
            if not _proves_mapped_effect(records[feature][1], feature, recipes[feature][1]):
                raise ValueError(f"{feature}: evidence does not prove declared observation/effect and cleanup")
        updates = {}
        for feature in ids:
            entry = _entry(root, feature)
            if hashlib.sha256(entry.read_bytes()).hexdigest() != report["map_sha256"][feature]:
                raise ValueError("map changed since verification; fresh proof required")
            artifact, record = records[feature]
            locator = os.path.relpath(artifact, entry.parent)
            updated, count = re.subn(
                r"^\*\*Last verification:\*\*.*$",
                lambda _: f"**Last verification:** revision={record['revision']}; instance={record['instance']}; "
                f"run={record['run_id']}; command=drive.py {feature}; observation=passed; "
                f"evidence=[run artifact]({locator}).",
                entry.read_text(), flags=re.M,
            )
            if count != 1:
                raise ValueError("expected exactly one Last verification field")
            updates[entry] = updated
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        return _result("blocked", reason=str(error))
    for entry, contents in updates.items():
        entry.write_text(contents)
    return {**report, "maintenance_records_updated": ids}

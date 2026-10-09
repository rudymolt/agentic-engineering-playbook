"""Template provenance and three-way merge primitives for managed project files.

Implements the recorded-base upgrade contract from
`analysis/template-upgrade-provenance-spec-2026-07-18.md`: bootstrap records the
pristine rendered copy of every managed file under `.playbook-base/` plus a
machine-owned `template_provenance` block in `.playbook-state.yml`; upgrades
three-way merge {recorded base, newly rendered template, project file} instead
of recognising boilerplate by remembered exact strings.

Ownership note: the `template_provenance` block is parsed, validated, and
rewritten wholesale here (it is machine-owned), unlike the position-preserving
edits in `playbook_state.py` that protect human-formatted state content.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

from playbook_state import parse_scalar, quote_yaml_string, validate_template_provenance
import upstream_registry as _registry  # noqa: E402  (same directory)

PROVENANCE_KEY = "template_provenance"
PROVENANCE_SCHEMA = 1
CURRENT_VERSION = "V0.5.0"
BASE_DIR = ".playbook-base"
BASE_README = """# .playbook-base/

Machine-owned pristine copies of playbook-managed files, recorded at bootstrap
and refreshed by `/ai-playbook-upgrade-project`. They are the merge base that
lets upgrades preserve project customisations. Agents do not read this folder;
humans do not edit it. Commit it — future upgrades need it intact.
"""

# Managed = eligible for provenance. `.playbook-state.yml` / `playbook-cadences.yml`
# (structured data with field-level migrations), the status mirrors (owned by
# compute-status.py), and the UI artefacts (near-total project content) are
# deliberately excluded — see the spec's managed-file set.
MANAGED_ROOT_FILES = {
    "CLAUDE.md": "v0.5/templates/CLAUDE.md",
    "AGENTS.md": "v0.5/templates/AGENTS.md",
    "GLOSSARY.md": "v0.5/templates/GLOSSARY.md",
    "retro-template.md": "v0.5/templates/retro-template.md",
    "field-report.md": "v0.5/templates/field-report.md",
    "ci-gates.md": "v0.5/templates/ci-gates.md",
    "planning/README.md": "v0.5/templates/planning-template/README.md",
    "archive/README.md": "v0.5/templates/archive/README.md",
}
REGISTRY = _registry.load()
MANAGED_SKILLS = tuple(REGISTRY.local_default_skills())


def _current_skill_name(name: str) -> str:
    """Resolve a current registry name, accepting recorded previous names."""
    if name in REGISTRY.current_names():
        return name
    try:
        return REGISTRY.previous_name_map()[name]
    except KeyError as error:
        raise ValueError(f"unknown skill placeholder {name!r}") from error


class MergeUnavailableError(RuntimeError):
    """git merge-file could not run; callers degrade to a manual review."""


def render(text: str, playbook_root: Path, project_name: str) -> str:
    """The one rendering seam shared by bootstrap and upgrade.

    The merge base and the upgrade's template side must both be rendered with
    the same project config, or path/name substitutions would show up as
    spurious template changes.
    """
    replacements = {
        "{path-to-playbook}": str(playbook_root),
        "{playbook-path}": str(playbook_root),
        "{project name}": project_name,
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"\{skill:([a-z0-9-]+)\}", lambda m: "/" + _current_skill_name(m.group(1)), text)
    return text


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def provenance_entry(template: str, version: str, rendered: str) -> dict[str, str]:
    """Build one schema-1 provenance entry from its pristine render."""
    return {
        "template": template,
        "version": version,
        "base_sha256": sha256_text(rendered),
    }


def managed_files(playbook_root: Path) -> dict[str, str]:
    """{project-relative path: playbook-relative template path} for every
    managed candidate the current playbook ships."""
    mapping = dict(MANAGED_ROOT_FILES)
    for skill in MANAGED_SKILLS:
        skill_root = playbook_root / "v0.5" / "skills" / skill
        if not skill_root.is_dir():
            continue
        for source in sorted(path for path in skill_root.rglob("*") if path.is_file()):
            if "__pycache__" in source.parts or source.suffix == ".pyc":
                continue
            try:
                source.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue  # provenance merging is a prose contract; skip binaries
            relative = source.relative_to(playbook_root)
            mapping[str(Path(".agents/skills") / source.relative_to(skill_root.parent))] = str(relative)
    return mapping


def merge3(base: str, ours: str, theirs: str) -> tuple[str, bool]:
    """Three-way merge via `git merge-file`. Returns (text, conflicted).

    On conflict the returned text contains markers and MUST NOT be written to
    the project; the caller reports a manual review instead.
    """
    with tempfile.TemporaryDirectory() as scratch:
        paths = {}
        for name, content in (("ours", ours), ("base", base), ("theirs", theirs)):
            path = Path(scratch) / name
            path.write_text(content)
            paths[name] = str(path)
        try:
            completed = subprocess.run(
                ["git", "merge-file", "-p", "-L", "project", "-L", "base", "-L", "template",
                 paths["ours"], paths["base"], paths["theirs"]],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as error:
            raise MergeUnavailableError("git is not available for merge-file") from error
    if completed.returncode < 0:
        raise MergeUnavailableError(f"git merge-file failed: {completed.stderr.strip()}")
    return completed.stdout, completed.returncode > 0


def conflict_evidence(merged: str) -> str:
    """Return compact project/template text for every merge conflict hunk."""
    hunks: list[str] = []
    pattern = re.compile(
        r"^<<<<<<< project\n(.*?)^=======\n(.*?)^>>>>>>> template$",
        re.MULTILINE | re.DOTALL,
    )
    for project_text, template_text in pattern.findall(merged):
        hunks.append(
            f"project={project_text.rstrip()!r}; template={template_text.rstrip()!r}"
        )
    return " | ".join(hunks) or "conflict markers returned without a parseable hunk"


# ------------------------------------------------------------ provenance block

def read_provenance(state_text: str) -> dict:
    """Parse the machine-owned block. Returns {} when absent.

    Raises ValueError on a malformed block — callers surface that as a manual
    review rather than silently re-backfilling over it.
    """
    lines = state_text.splitlines()
    starts = [
        index for index, line in enumerate(lines)
        if re.match(rf"^{re.escape(PROVENANCE_KEY)}:", line)
    ]
    if not starts:
        return {}
    if len(starts) > 1:
        raise ValueError(f"duplicate {PROVENANCE_KEY} blocks")
    problems = validate_template_provenance(state_text)
    if problems:
        raise ValueError(problems[0].render())
    start = starts[0]
    record: dict = {"files": {}}
    current_file: str | None = None
    for line in lines[start + 1:]:
        if line.strip() and not line.startswith(" "):
            break
        if not line.strip():
            continue
        header = re.match(r"^  (schema|project_name):\s*(.*)$", line)
        if header:
            value = header.group(2).strip()
            if header.group(1) == "schema":
                if value != str(PROVENANCE_SCHEMA):
                    raise ValueError(f"unsupported template_provenance schema: {value}")
                record["schema"] = int(value)
            else:
                record["project_name"] = parse_scalar(value)
            continue
        if line == "  files:":
            continue
        file_key = re.match(r"^    (\S+):\s*$", line)
        if file_key:
            current_file = file_key.group(1)
            record["files"][current_file] = {}
            continue
        field = re.match(r"^      ([a-z_0-9]+):\s*(.*)$", line)
        if field and current_file is not None:
            value = field.group(2).strip()
            record["files"][current_file][field.group(1)] = parse_scalar(value)
            continue
        raise ValueError(f"malformed template_provenance line: {line!r}")
    if "schema" not in record:
        raise ValueError("template_provenance block is missing its schema field")
    return record


def render_provenance(record: dict) -> str:
    lines = [f"{PROVENANCE_KEY}:", f"  schema: {PROVENANCE_SCHEMA}"]
    if record.get("project_name"):
        lines.append(f"  project_name: {quote_yaml_string(str(record['project_name']))}")
    lines.append("  files:")
    for path in sorted(record.get("files", {})):
        lines.append(f"    {path}:")
        entry = record["files"][path]
        for key in ("template", "version", "base_sha256"):
            if key in entry:
                lines.append(f"      {key}: {entry[key]}")
    return "\n".join(lines) + "\n"


def upsert_provenance(state_text: str, record: dict) -> str:
    """Replace or append the whole block; the block is machine-owned, so a
    wholesale rewrite (sorted keys) keeps it deterministic."""
    lines = state_text.splitlines(keepends=True)
    existing_starts = [
        index for index, line in enumerate(lines)
        if re.match(rf"^{re.escape(PROVENANCE_KEY)}:", line.rstrip("\n"))
    ]
    if existing_starts:
        # Never append or rewrite around a malformed/duplicate machine-owned
        # block: doing so could hide invalid state behind a later valid key.
        read_provenance(state_text)
    start = end = None
    for index, line in enumerate(lines):
        if re.match(rf"^{re.escape(PROVENANCE_KEY)}:", line.rstrip("\n")):
            start = index
            end = len(lines)
            for later in range(index + 1, len(lines)):
                candidate = lines[later].rstrip("\n")
                if candidate and not candidate.startswith(" "):
                    end = later
                    break
            break
    block = render_provenance(record)
    if start is None:
        base = state_text if state_text.endswith("\n") or not state_text else state_text + "\n"
        return base.rstrip("\n") + "\n\n" + block
    return "".join(lines[:start]) + block + "".join(lines[end:])

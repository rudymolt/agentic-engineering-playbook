#!/usr/bin/env python3
"""Validate local skill invocation metadata against skills/README.md."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import upstream_registry


ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = ROOT / "skills"
INDEX = SKILLS_ROOT / "README.md"
MAX_DESCRIPTION_WORDS = 45


def yaml_mapping_body(text: str, key: str) -> str:
    """Return the indented body of one top-level YAML mapping."""

    lines = text.splitlines()
    try:
        start = lines.index(f"{key}:") + 1
    except ValueError:
        return ""
    body: list[str] = []
    for line in lines[start:]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    metadata: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"\'')
    return metadata, text[end + 5:]


def invocation_contract(index_text: str) -> dict[str, str]:
    match = re.search(r"local_skills\[\d+\]\{name,invocation\}:\n((?:  .+\n?)+)", index_text)
    if not match:
        return {}
    contract: dict[str, str] = {}
    for line in match.group(1).splitlines():
        name, invocation = (part.strip() for part in line.split(",", 1))
        contract[name] = invocation
    return contract


def registry_contract() -> dict[str, str]:
    registry = upstream_registry.load()
    return {
        skill.name: skill.invocation
        for skill in registry.skills_for("playbook")
    }


def validate_skill_text(name: str, text: str, invocation: str) -> list[str]:
    problems: list[str] = []
    metadata, body = parse_frontmatter(text)
    if metadata.get("name") != name:
        problems.append(f"{name}: frontmatter name does not match directory")

    description = metadata.get("description", "")
    if not description:
        problems.append(f"{name}: description is required")
    elif len(re.findall(r"\b[\w/-]+\b", description)) > MAX_DESCRIPTION_WORDS:
        problems.append(f"{name}: description exceeds {MAX_DESCRIPTION_WORDS} words")

    disabled = metadata.get("disable-model-invocation")
    if invocation == "model" and disabled is not None:
        problems.append(f"{name}: model-invoked skill must omit disable-model-invocation")
    elif invocation == "user" and disabled != "true":
        problems.append(f"{name}: user-invoked skill must set disable-model-invocation: true")
    elif invocation not in {"model", "user"}:
        problems.append(f"{name}: unknown invocation type '{invocation}'")

    if "## Procedure" not in body:
        problems.append(f"{name}: ordered skill is missing a Procedure section")
    else:
        procedure = body.split("## Procedure", 1)[1]
        next_heading = re.search(r"^## ", procedure, re.M)
        if next_heading:
            procedure = procedure[:next_heading.start()]
        heading_steps = list(re.finditer(r"^### Step \d+\b", procedure, re.M))
        step_starts = heading_steps or list(re.finditer(r"^\d+\.", procedure, re.M))
        if not step_starts:
            problems.append(f"{name}: Procedure has no ordered steps")
        for index, start in enumerate(step_starts):
            end = step_starts[index + 1].start() if index + 1 < len(step_starts) else len(procedure)
            if "Completion criterion:" not in procedure[start.start():end]:
                label = start.group(0).rstrip(".")
                problems.append(f"{name}: {label} is missing a completion criterion")
    if re.search(r"^## (?:Things this skill must not do|What this skill must never do)$", body, re.M):
        problems.append(f"{name}: replace negative guardrail heading with a positive Guardrails contract")
    return problems


def validate_codex_metadata(name: str, skill_dir: Path, invocation: str) -> list[str]:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        return [f"{name}: missing agents/openai.yaml Codex discovery metadata"]

    text = path.read_text()
    interface = yaml_mapping_body(text, "interface")
    policy = yaml_mapping_body(text, "policy")
    problems: list[str] = []
    fields = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'^  (display_name|short_description|default_prompt): "([^"]+)"$', interface, re.M
        )
    }
    problems.extend(
        f"{name}: agents/openai.yaml missing quoted {field}"
        for field in ("display_name", "short_description", "default_prompt")
        if field not in fields
    )
    if "default_prompt" in fields and f"${name}" not in fields["default_prompt"]:
        problems.append(f"{name}: agents/openai.yaml default_prompt must mention ${name}")

    implicit_policy = re.search(
        r"(?m)^  allow_implicit_invocation:\s*(true|false)\s*(?:#.*)?$", policy
    )
    if invocation == "user" and (
        implicit_policy is None or implicit_policy.group(1) != "false"
    ):
        problems.append(
            f"{name}: user-invoked skill must set Codex policy.allow_implicit_invocation: false"
        )
    elif invocation == "model" and implicit_policy is not None:
        problems.append(
            f"{name}: model-invoked skill must omit Codex allow_implicit_invocation policy"
        )
    return problems


def check(skills_root: Path = SKILLS_ROOT, index: Path = INDEX) -> list[str]:
    contract = invocation_contract(index.read_text())
    if contract != registry_contract():
        problems = [
            "skills/README.md: local-skill table drifted from the registry "
            "(run generate-upstream-inventory.py)"
        ]
    else:
        problems = []
    directories = {
        path.parent.name: path
        for path in skills_root.glob("*/SKILL.md")
    }
    if set(contract) != set(directories):
        missing = sorted(set(directories) - set(contract))
        extra = sorted(set(contract) - set(directories))
        if missing:
            problems.append(f"skills/README.md: missing local skills {missing}")
        if extra:
            problems.append(f"skills/README.md: lists absent local skills {extra}")
    for name in sorted(set(contract) & set(directories)):
        problems.extend(validate_skill_text(name, directories[name].read_text(), contract[name]))
        problems.extend(validate_codex_metadata(name, directories[name].parent, contract[name]))
    return problems


def main() -> int:
    problems = check()
    if problems:
        print("Skill metadata checks failed:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print("Skill metadata checks passed: invocation contract exact, Claude/Codex ownership aligned, descriptions bounded, steps checkable, guardrails positive.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

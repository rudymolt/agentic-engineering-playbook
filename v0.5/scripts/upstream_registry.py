"""Load and validate the upstream skill registry (`v0.5/upstream-skills.json`).

The registry is the single machine-readable source of truth for every package
(upstream or local) and every skill the playbook names. Nothing else parses the
JSON: generators, checkers, the installed-state probe, and the rename/retire
helpers all go through this module. See ADR 0001 and
`analysis/upstream-skill-lifecycle-plan-2026-09-04.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "upstream-skills.json"

CAPABILITY_LANES = frozenset({
    "repository",
    "human_decisions",
    "spec_and_slices",
    "implementation_and_diagnosis",
    "independent_verification",
    "real_environment_qa",
    "security",
    "state_lifecycle",
    "model_routing",
})
PACKAGE_KINDS = frozenset({"upstream", "local"})
ADOPTION_LEVELS = frozenset({"source", "accelerator"})
INSTALL_METHODS = frozenset({"skills-cli", "git-checkout", "plugin", "none"})
PIN_KINDS = frozenset({"tag", "commit", "commit+version"})
SKILL_STATUSES = frozenset({"current", "removed"})
INVOCATIONS = frozenset({"user", "model"})
TIERS = frozenset({"core", "accelerated", "extended"})


class RegistryError(ValueError):
    """The registry cannot be trusted as a source of truth."""


@dataclass(frozen=True)
class Package:
    name: str
    kind: str
    source: str
    adoption_level: str | None
    pin: dict
    install: dict
    harness_name_pattern: dict
    watch: tuple[str, ...]


@dataclass(frozen=True)
class Skill:
    name: str
    package: str
    status: str
    invocation: str
    tier: str
    lanes: tuple[str, ...]
    stages: tuple[str, ...]
    previous_names: tuple[dict, ...]
    manifest_key: str | None
    upstream_path: str | None
    install_by_default: bool | None
    provenance: dict | None
    since: str | None
    removed_in: str | None


@dataclass
class Registry:
    packages: dict[str, Package]
    skills: dict[str, Skill]
    borrowed_ideas: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------ queries

    def skills_for(self, package: str, *, status: str | None = "current") -> list[Skill]:
        return [
            skill for skill in self.skills.values()
            if skill.package == package and (status is None or skill.status == status)
        ]

    def current_names(self) -> set[str]:
        return {name for name, skill in self.skills.items() if skill.status == "current"}

    def previous_name_map(self) -> dict[str, str]:
        """Old name → current name for every recorded rename."""
        mapping: dict[str, str] = {}
        for skill in self.skills.values():
            for entry in skill.previous_names:
                mapping[str(entry["name"])] = skill.name
        return mapping

    def removed_names(self) -> set[str]:
        return {name for name, skill in self.skills.items() if skill.status == "removed"}

    def manifest_keys(self) -> dict[str, str]:
        """Manifest key → skill name for every embedded (level 2) skill."""
        return {
            skill.manifest_key: skill.name
            for skill in self.skills.values()
            if skill.manifest_key is not None
        }

    def local_default_skills(self) -> list[str]:
        return sorted(
            skill.name for skill in self.skills.values()
            if self.packages[skill.package].kind == "local"
            and skill.status == "current"
            and skill.install_by_default is True
        )

    def check_a_paths(self, package: str, prefix: str = ".claude/skills/") -> list[str]:
        """Bucketed install paths in Check A order (registry order)."""
        return [
            f"{prefix}{skill.upstream_path}/SKILL.md"
            for skill in self.skills_for(package)
            if skill.upstream_path
        ]

    def check_b_commands(self, package: str) -> list[str]:
        return [f"/{skill.name}" for skill in self.skills_for(package)]

    def harness_name(self, skill: str, harness: str) -> str:
        package = self.packages[self.skills[skill].package]
        pattern = package.harness_name_pattern.get(harness, "/{name}")
        return pattern.replace("{name}", skill)


# ---------------------------------------------------------------- loading

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def _package(name: str, raw: dict) -> Package:
    _require(isinstance(raw, dict), f"package {name}: entry must be an object")
    kind = raw.get("kind", "upstream")
    _require(kind in PACKAGE_KINDS, f"package {name}: kind must be one of {sorted(PACKAGE_KINDS)}")
    source = raw.get("source")
    _require(isinstance(source, str) and source.strip(), f"package {name}: source is required")
    pin = raw.get("pin") or {}
    install = raw.get("install") or {}
    adoption_level = raw.get("adoption_level")
    if kind == "upstream":
        _require(
            adoption_level in ADOPTION_LEVELS,
            f"package {name}: adoption_level must be one of {sorted(ADOPTION_LEVELS)}",
        )
        _require(isinstance(pin, dict) and pin.get("kind") in PIN_KINDS,
                 f"package {name}: pin.kind must be one of {sorted(PIN_KINDS)}")
        _require(isinstance(pin.get("commit"), str) and len(pin["commit"]) >= 7,
                 f"package {name}: pin.commit must be a commit hash")
        if pin["kind"] != "commit":
            _require(isinstance(pin.get("value"), str) and pin["value"].strip(),
                     f"package {name}: pin.value is required for pin.kind {pin['kind']}")
        _require(isinstance(install, dict) and install.get("method") in INSTALL_METHODS,
                 f"package {name}: install.method must be one of {sorted(INSTALL_METHODS)}")
        if adoption_level == "accelerator":
            _require(install["method"] != "none",
                     f"package {name}: an accelerator package must declare an install method")
    else:
        _require(adoption_level is None, f"package {name}: local packages have no adoption_level")
    patterns = raw.get("harness_name_pattern") or {"claude": "/{name}"}
    _require(isinstance(patterns, dict) and all("{name}" in v for v in patterns.values()),
             f"package {name}: every harness_name_pattern must contain {{name}}")
    watch = raw.get("watch") or []
    _require(isinstance(watch, list), f"package {name}: watch must be a list")
    return Package(name, kind, source, adoption_level, pin, install, patterns, tuple(watch))


def _skill(name: str, raw: dict, packages: dict[str, Package]) -> Skill:
    _require(isinstance(raw, dict), f"skill {name}: entry must be an object")
    package = raw.get("package")
    _require(package in packages, f"skill {name}: unknown package {package!r}")
    status = raw.get("status", "current")
    _require(status in SKILL_STATUSES, f"skill {name}: status must be one of {sorted(SKILL_STATUSES)}")
    invocation = raw.get("invocation")
    _require(invocation in INVOCATIONS, f"skill {name}: invocation must be user or model")
    tier = raw.get("tier", "accelerated")
    _require(tier in TIERS, f"skill {name}: tier must be one of {sorted(TIERS)}")
    lanes = tuple(raw.get("lanes") or [])
    unknown = sorted(set(lanes) - CAPABILITY_LANES)
    _require(not unknown, f"skill {name}: unknown lanes {unknown}")
    stages = tuple(str(s) for s in (raw.get("stages") or []))
    previous = tuple(raw.get("previous_names") or [])
    for entry in previous:
        _require(isinstance(entry, dict) and isinstance(entry.get("name"), str)
                 and isinstance(entry.get("upstream_version"), str),
                 f"skill {name}: previous_names entries need name and upstream_version")
    manifest_key = raw.get("manifest_key")
    _require(manifest_key is None or (isinstance(manifest_key, str) and manifest_key.strip()),
             f"skill {name}: manifest_key must be a non-empty string when present")
    install_by_default = raw.get("install_by_default")
    if packages[package].kind == "local":
        _require(isinstance(install_by_default, bool),
                 f"skill {name}: local skills must declare install_by_default")
    else:
        _require(install_by_default is None,
                 f"skill {name}: install_by_default applies to local skills only")
    if status == "removed":
        _require(isinstance(raw.get("removed_in"), str),
                 f"skill {name}: removed skills must record removed_in")
    return Skill(
        name, package, status, invocation, tier, lanes, stages, previous,
        manifest_key, raw.get("upstream_path"), install_by_default,
        raw.get("provenance"), raw.get("since"), raw.get("removed_in"),
    )


def load(path: Path = DEFAULT_REGISTRY) -> Registry:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError as error:
        raise RegistryError(f"missing registry: {path}") from error
    except json.JSONDecodeError as error:
        raise RegistryError(f"invalid registry JSON: {error}") from error
    _require(payload.get("schema_version") == 1, "schema_version must be 1")
    raw_packages = payload.get("packages")
    raw_skills = payload.get("skills")
    _require(isinstance(raw_packages, dict) and raw_packages, "packages must be a non-empty object")
    _require(isinstance(raw_skills, dict) and raw_skills, "skills must be a non-empty object")
    packages = {name: _package(name, raw) for name, raw in raw_packages.items()}
    skills = {name: _skill(name, raw, packages) for name, raw in raw_skills.items()}
    seen_manifest: dict[str, str] = {}
    for skill in skills.values():
        if skill.manifest_key is not None:
            _require(skill.manifest_key not in seen_manifest,
                     f"manifest_key {skill.manifest_key!r} claimed by both "
                     f"{seen_manifest.get(skill.manifest_key)} and {skill.name}")
            seen_manifest[skill.manifest_key] = skill.name
    all_names = set(skills)
    for skill in skills.values():
        for entry in skill.previous_names:
            _require(entry["name"] not in all_names or skills[entry["name"]].status == "removed",
                     f"skill {skill.name}: previous name {entry['name']!r} is still a current skill")
    ideas = payload.get("borrowed_ideas") or []
    _require(isinstance(ideas, list), "borrowed_ideas must be a list")
    for idea in ideas:
        _require(isinstance(idea, dict) and idea.get("package") in packages
                 and isinstance(idea.get("id"), str),
                 "borrowed_ideas entries need a known package and an id")
    return Registry(packages, skills, list(ideas))


def manifest_problems(registry: Registry, manifest: dict) -> list[str]:
    """Cross-validate the registry against `upstream-integrations.json`."""
    problems: list[str] = []
    integrations = manifest.get("integrations", {})
    keys = registry.manifest_keys()
    for key in sorted(integrations):
        if key not in keys:
            problems.append(f"manifest entry {key!r} has no registry skill with manifest_key {key!r}")
    for key, skill in sorted(keys.items()):
        if key not in integrations:
            problems.append(f"registry skill {skill!r} names manifest_key {key!r} that the manifest lacks")
            continue
        upstream = str(integrations[key].get("upstream", ""))
        package = registry.packages[registry.skills[skill].package]
        if upstream and upstream not in package.source:
            problems.append(
                f"manifest entry {key!r} upstream {upstream!r} does not match package "
                f"{package.name!r} source {package.source!r}"
            )
    return problems

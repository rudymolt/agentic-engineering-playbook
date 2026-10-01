"""Read-only personal seed preview and the bootstrap-owned approved write."""

from copy import deepcopy
from pathlib import Path

from playbook_config import Configuration, ConfigError, DESTINATION, IDENTITY, digest, encoded, validate_config
from skill_bindings import JobBindings


def preview_seed(project, preferences_dir, discover, clock=None, preset=None, custom_dir=None):
    service = Configuration(project, discover, clock, preferences_dir=preferences_dir,
                            bindings=JobBindings(project, custom_dir=custom_dir))
    personal = service._personal_snapshot()
    preferences = personal["before"] or {}
    candidate = preferences.get("presets", {}).get(preset) if preset else preferences.get("defaults")
    if candidate is None:
        if preset:
            raise ConfigError("Named bootstrap preset is missing; reload personal settings and select an existing name.")
        return None
    validate_config(candidate)
    if (Path(project) / DESTINATION).exists() or (Path(project) / ".playbook-state.yml").exists():
        raise ConfigError("Personal defaults seed only new projects. Existing content is preserved; use Configure, Load defaults/preset, preview and explicit Apply instead.")
    service._guard_write()
    routes, evidence = service._available()
    for role, choice in candidate["models"].items():
        identity = {key: value for key, value in choice.items() if key in IDENTITY}
        if identity not in routes[role]:
            raise ConfigError("Bootstrap preset model is unavailable; restore the route or explicitly edit the personal seed. No substitution.")
    if "skills" in candidate:
        for job in candidate["skills"]["jobs"]:
            service._bindings().resolve(candidate["skills"], job)
    origin = "personal preset " + preset if preset else "personal defaults"
    preview = {"destination": DESTINATION, "before": None, "after": deepcopy(candidate),
               "origins": {"models": origin, "skills": origin if "skills" in candidate else "existing stage routes"},
               "personal_inputs": personal["inputs"], "discovery_revision": service._discovery_revision(evidence),
               "skill_options": {job: service._bindings().options(job) for job in candidate.get("skills", {}).get("jobs", {})}}
    preview["seed_revision"] = digest(encoded(preview))
    return preview


def apply_seed(project, preferences_dir, discover, preview, clock=None, custom_dir=None, project_identity=None):
    service = Configuration(project, discover, clock, preferences_dir=preferences_dir,
                            bindings=JobBindings(project, custom_dir=custom_dir))
    current_personal = service._personal_snapshot()["inputs"]
    planned_personal = preview["personal_inputs"]
    current_project = current_personal["directories"]["project"]
    planned_project = planned_personal["directories"]["project"]
    if (current_personal["preferences.json"] != planned_personal["preferences.json"]
            or current_personal["directories"]["personal"] != planned_personal["directories"]["personal"]
            or current_project["resolved"] != planned_project["resolved"]
            or project_identity is None
            or any(current_project[key] != project_identity[key] for key in ("resolved", "device", "inode"))
            or (planned_project["anchor"] == planned_project["resolved"] and current_project != planned_project)):
        raise ConfigError("Personal seed changed during bootstrap; preserve project content, reload and review before retrying.")
    _, _, inputs = service._snapshot()
    if inputs[DESTINATION] is not None:
        raise ConfigError("Configuration appeared during bootstrap; preserve it and review through Configure.")
    routes, evidence = service._available()
    if service._discovery_revision(evidence) != preview["discovery_revision"]:
        raise ConfigError("Seed discovery changed during bootstrap; review the new evidence, never substitute.")
    candidate = validate_config(deepcopy(preview["after"]))
    for role, choice in candidate["models"].items():
        if {key: value for key, value in choice.items() if key in IDENTITY} not in routes[role]:
            raise ConfigError("Seed route is no longer available; review without substitution.")
    for job in candidate.get("skills", {}).get("jobs", {}):
        service._bindings().resolve(candidate["skills"], job)
        if service._bindings().options(job) != preview["skill_options"][job]:
            raise ConfigError("Seed skill eligibility changed during bootstrap; review the retained source before Apply.")
    service.preferences._expected_directory = current_personal["directories"]
    try:
        service._save(candidate, inputs, evidence)
    finally:
        service.preferences._expected_directory = None

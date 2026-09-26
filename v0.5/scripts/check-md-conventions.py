#!/usr/bin/env python3
"""Check the V0.5 Markdown agent-ergonomics conventions.

Verifies the redundancy the V0.2 ergonomics rely on hasn't drifted:
  1. Every stage file has exactly one "This stage in one breath" opener.
  2. Every stage file has exactly one `## Next` block, and it is the last section.
  3. Every playbook path mentioned in AGENT-DIGEST.md resolves to a real file.
  4. The digest's stage map lists every stage file in 10-process/ (and no extras).
  5. Cadence counters have matching source keys in the state template.
  6. Allowed feature statuses are reachable from stage state updates.
  7. Backtick-wrapped skill commands are installed, local, or explicitly optional.
  8. Stale V0.2 labels and paths are kept out of live v0.5 docs.
  9. Stage 00 keeps a bounded warm path and points at the capability profile.
  10. Wayfinder stays optional, visible on the fast path, and separate from slicing.
  11. Model routing stays text-first, state-visible, and linked from every lane boundary.
  12. Every current-era release has reachable, executable project migration guidance.
  13. First-time bootstrap stays discoverable, plan-first, deterministic, and
      Conductor-aware when the host or user requests that lane.
  14. Terminal routing and routed worker evidence stay machine-readable.
  15. Observational eval fields stay aligned across stage 12 and project templates.
  16. Live V0.5 surfaces never route into retired pre-v1.0 process references.
  17. Architecture-review issues retain their source label through breakdown.
  18. Embedded upstream reviewers stay report-only, compatibility-gated, and
      safely replaceable by a manual route.
  19. Registry-pinned upstream names, evidence rules, and dual-harness invocation metadata stay aligned.
  20. Ordinary issue-build checkpoints stay distinct from selected and protected hard limits.

Run: python3 v0.5/scripts/check-md-conventions.py   (exit 0 = clean)
"""

import re
import sys
from pathlib import Path

from convention_checks import (
    architecture_issue_provenance_problems,
    embedded_upstream_contract_problems,
    legacy_command_has_context,
    live_tdd_drift_problems,
    model_router_skill_routing_contract_problems,
    model_routing_track_contract_problems,
    ordinary_build_policy_problems,
    stage_membership_problems,
    upstream_contract_problems,
    upstream_version_problems,
)
import upstream_registry

ROOT = Path(__file__).resolve().parents[1]          # v0.5/
STAGES = sorted((ROOT / "10-process").glob("[0-9][0-9]-*.md"))
DIGEST = ROOT / "AGENT-DIGEST.md"
PREREQS = ROOT / "10-process" / "00-prereqs.md"
STATE_TEMPLATE = ROOT / "templates" / ".playbook-state.yml"
CADENCES_TEMPLATE = ROOT / "templates" / "playbook-cadences.yml"
CAPABILITY_PROFILE = ROOT / "10-process" / "prereqs-capability-profiles.md"
MAINTENANCE = ROOT / "MAINTENANCE.md"
PROCESS_MAP = ROOT / "10-process" / "README.md"
ALIGN = ROOT / "10-process" / "01-align.md"
SPEC = ROOT / "10-process" / "03-spec.md"
BREAKDOWN = ROOT / "10-process" / "04-breakdown.md"
DELEGATION = ROOT / "91-delegation-track.md"
WAYFINDER = ROOT / "92-wayfinder-track.md"
MODEL_ROUTING = ROOT / "93-model-routing-track.md"
PLANNING_STATUS_TEMPLATE = ROOT / "templates" / "planning-template" / "STATUS.md"
WHATS_NEXT = ROOT / "skills" / "whats-next" / "SKILL.md"
MODEL_ROUTER = ROOT / "skills" / "model-router" / "SKILL.md"
MODEL_ROUTER_PROMPTS = ROOT / "skills" / "model-router" / "references" / "chat-prompts.md"
ARCHITECTURE_STAGE = ROOT / "10-process" / "06-architecture.md"
DEBUG_STAGE = ROOT / "10-process" / "11-debug.md"
REVIEW_STAGE = ROOT / "10-process" / "08-review.md"
FRONTEND_TRACK = ROOT / "20-frontend-track.md"
SKILLS_INDEX = ROOT / "skills" / "README.md"
SHIP_STAGE = ROOT / "10-process" / "10-ship-and-deploy.md"
RETRO_STAGE = ROOT / "10-process" / "12-retro-and-learn.md"
RETRO_TEMPLATE = ROOT / "templates" / "retro-template.md"
FIELD_REPORT_TEMPLATE = ROOT / "templates" / "field-report.md"
UPGRADE_SKILL = ROOT / "skills" / "ai-playbook-upgrade-project" / "SKILL.md"
MIGRATIONS = ROOT / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md"
UPGRADE_SCRIPT = ROOT / "scripts" / "upgrade-project.py"
BOOTSTRAP_SKILL = ROOT / "skills" / "ai-playbook-bootstrap-project" / "SKILL.md"
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "bootstrap-project.py"
CHANGELOG = ROOT / "CHANGELOG.md"
DOCUMENT_LIFECYCLE = ROOT / "30-document-lifecycle.md"
VERSION_README = ROOT / "README.md"
OPTIONAL_COMMANDS = {"pair-agent"}  # Referenced in 11-debug as optional; not verifiable upstream.
MANIFEST_OWNED_COMMANDS = {"ai-playbook-deliver"}
NON_SKILL_SLASH_REFERENCES = {"me"}  # Conductor API endpoint documented by delivery/README.md.
REGISTRY = upstream_registry.load()
LEGACY_COMMANDS = set(REGISTRY.previous_name_map()) | REGISTRY.removed_names()
V02_PATH_ALLOWED = {
    ROOT / "CHANGELOG.md",
    ROOT / "README.md",
    ROOT / "skills" / "ai-playbook-upgrade-project" / "SKILL.md",
    ROOT / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md",
}  # These intentionally mention the frozen v0.2 fork or migration path.

problems: list[str] = []


for line, command, expected in (
    ("Use `/to-spec` (formerly `/to-prd`).", "to-prd", True),
    ("`/to-prd` was renamed `/to-spec`.", "to-prd", True),
    ("`/to-plan` and `/to-issues` are **merged** into `/to-tickets`.", "to-plan", True),
    ("Run `/to-prd` before breakdown.", "to-prd", False),
    ("Use `/to-prd` with v1.1.", "to-prd", False),
):
    if legacy_command_has_context(line, command) != expected:
        problems.append(f"internal legacy-command context regression for: {line}")


def keys_under_top_level_block(text: str, block_name: str) -> set[str]:
    keys: set[str] = set()
    in_block = False
    for line in text.splitlines():
        if line == f"{block_name}:":
            in_block = True
            continue
        if not in_block:
            continue
        if line and not line.startswith(" "):
            break
        match = re.match(r"^\s{2}([A-Za-z0-9_-]+):", line)
        if match:
            keys.add(match.group(1))
    return keys

# 1 + 2 — stage file conventions
for stage in STAGES:
    text = stage.read_text()
    rel = stage.relative_to(ROOT)
    breaths = text.count("**This stage in one breath:**")
    if breaths != 1:
        problems.append(f"{rel}: expected exactly one 'in one breath' opener, found {breaths}")
    nexts = re.findall(r"^## Next$", text, re.M)
    if len(nexts) != 1:
        problems.append(f"{rel}: expected exactly one '## Next' block, found {len(nexts)}")
    else:
        last_heading = re.findall(r"^## .+$", text, re.M)[-1]
        if last_heading != "## Next":
            problems.append(f"{rel}: '## Next' must be the final section (found '{last_heading}' after it)")

# 3 — digest pointers resolve
digest_text = DIGEST.read_text()
refs = set(re.findall(
    r"\b((?:10-process/|skills/|templates/)[\w./-]+\.(?:md|yml|html)|"
    r"(?:README|00-foundations|20-frontend-track|30-document-lifecycle|"
    r"40-self-improvement|CHANGELOG|AGENT-DIGEST)\.md)\b", digest_text))
for ref in sorted(refs):
    if not (ROOT / ref).exists():
        problems.append(f"AGENT-DIGEST.md: pointer '{ref}' does not resolve")

# 4 — digest stage map is complete and exact
digest_stages = set(re.findall(r"10-process/\d\d-[\w-]+\.md", digest_text))
actual_stages = {f"10-process/{s.name}" for s in STAGES}
for missing in sorted(actual_stages - digest_stages):
    problems.append(f"AGENT-DIGEST.md: stage map missing {missing}")
for extra in sorted(digest_stages - actual_stages):
    problems.append(f"AGENT-DIGEST.md: stage map lists non-existent {extra}")

# 5 — cadence counters have state-template source keys
cadences_text = CADENCES_TEMPLATE.read_text()
state_text = STATE_TEMPLATE.read_text()
counter_keys = keys_under_top_level_block(state_text, "counters")
last_run_keys = keys_under_top_level_block(state_text, "last_run")
cadence_blocks = re.finditer(r"(?ms)^  - id:\s*([^\n#]+).*?(?=^  - id:|\Z)", cadences_text)
for cadence in cadence_blocks:
    cadence_id = cadence.group(1).strip()
    block = cadence.group(0)
    type_match = re.search(r"^\s+type:\s*([A-Za-z0-9_-]+)", block, re.M)
    counter_match = re.search(r"^\s+counter:\s*([A-Za-z0-9_]+)", block, re.M)
    cadence_type = type_match.group(1) if type_match else None
    if cadence_type == "event" or not counter_match:
        continue
    counter = counter_match.group(1)
    days_match = re.match(r"days_since_last_(.+)$", counter)
    if days_match:
        last_run_key = days_match.group(1)
        if last_run_key not in last_run_keys:
            problems.append(
                f"templates/playbook-cadences.yml: cadence '{cadence_id}' counter "
                f"'{counter}' has no last_run.{last_run_key} key in .playbook-state.yml"
            )
    elif cadence_type == "count" and counter not in counter_keys:
        problems.append(
            f"templates/playbook-cadences.yml: cadence '{cadence_id}' counter "
            f"'{counter}' has no counters.{counter} key in .playbook-state.yml"
        )
    elif cadence_type == "time":
        problems.append(
            f"templates/playbook-cadences.yml: cadence '{cadence_id}' type time counter "
            f"'{counter}' must use days_since_last_* naming convention"
        )

# 6 — allowed feature statuses are reachable and stage-set statuses are valid
allowed_match = re.search(r"^# Allowed statuses:\s*(.+)$", state_text, re.M)
allowed_statuses = set()
if not allowed_match:
    problems.append("templates/.playbook-state.yml: missing '# Allowed statuses:' line")
else:
    allowed_statuses = {status.strip() for status in allowed_match.group(1).split(",")}

seen_statuses: set[str] = set()
for stage in STAGES:
    text = stage.read_text()
    rel = stage.relative_to(ROOT)
    for match in re.finditer(r"^\s*status:\s*([a-z][a-z0-9-]+)\b", text, re.M):
        status = match.group(1)
        seen_statuses.add(status)
        if status not in allowed_statuses:
            problems.append(f"{rel}: status '{status}' is not in the state template allowed-status list")
    for match in re.finditer(r"status to `([a-z][a-z0-9-]+)`", text):
        seen_statuses.add(match.group(1))

for status in sorted(allowed_statuses - seen_statuses):
    problems.append(f"templates/.playbook-state.yml: allowed status '{status}' is not set by any stage file")

# 7 — backtick-wrapped skill command references resolve to known skills
prereqs_text = PREREQS.read_text()
check_a_match = re.search(r"The path list below.*?```(.*?)```", prereqs_text, re.S)
check_b_match = re.search(r"Check for any of these skill commands.*?```(.*?)```", prereqs_text, re.S)
allowed_commands: set[str] = set(OPTIONAL_COMMANDS)
allowed_commands.update(MANIFEST_OWNED_COMMANDS)
allowed_commands.update(NON_SKILL_SLASH_REFERENCES)
if check_a_match:
    allowed_commands.update(re.findall(r"/([^/\s]+)/SKILL\.md", check_a_match.group(1)))
else:
    problems.append("10-process/00-prereqs.md: could not find Check A skill path block")
if check_b_match:
    allowed_commands.update(re.findall(r"/([a-z][a-z0-9-]+)", check_b_match.group(1)))
else:
    problems.append("10-process/00-prereqs.md: could not find Check B command block")
allowed_commands.update(path.name for path in (ROOT / "skills").iterdir() if path.is_dir())
allowed_commands.add("upgrade-project")

for md_file in sorted(ROOT.rglob("*.md")):
    if md_file.name == "CHANGELOG.md":
        continue
    rel = md_file.relative_to(ROOT)
    text = md_file.read_text()
    for match in re.finditer(r"`/([a-z][a-z0-9-]+)`", text):
        command = match.group(1)
        if command in LEGACY_COMMANDS:
            line_start = text.rfind("\n", 0, match.start()) + 1
            line_end = text.find("\n", match.end())
            line = text[line_start:line_end if line_end != -1 else len(text)]
            if not legacy_command_has_context(line, command):
                problems.append(
                    f"{rel}: legacy skill command `/{command}` lacks explicit rename/compatibility context"
                )
            continue
        if command not in allowed_commands:
            problems.append(f"{rel}: unknown skill command `/{command}`")

# 8 — stale V0.2 labels and live v0.2 paths are not allowed in v0.5 docs
for md_file in sorted(ROOT.rglob("*.md")):
    text = md_file.read_text()
    rel = md_file.relative_to(ROOT)
    if "**V0.2:**" in text:
        problems.append(f"{rel}: stale '**V0.2:**' label")
    if md_file not in V02_PATH_ALLOWED and "v0.2/" in text:
        problems.append(f"{rel}: stale 'v0.2/' path reference")

# 9 — stage 00 warm/cold routing stays short and capability-based
warm_match = re.search(r"(?ms)^## Warm path — normal session\n(.*?)(?=^---$)", prereqs_text)
if not warm_match:
    problems.append("10-process/00-prereqs.md: missing bounded warm path")
else:
    warm_lines = [line for line in warm_match.group(1).splitlines() if line.strip()]
    if len(warm_lines) > 15:
        problems.append(
            f"10-process/00-prereqs.md: warm path exceeds 15 non-blank lines ({len(warm_lines)})"
        )
if "## Cold path — bootstrap, upgrade, or capability change" not in prereqs_text:
    problems.append("10-process/00-prereqs.md: missing cold-path trigger section")
if "prereqs-capability-profiles.md" not in prereqs_text or not CAPABILITY_PROFILE.exists():
    problems.append("10-process/00-prereqs.md: capability-profile pointer missing or unresolved")
if not MAINTENANCE.exists():
    problems.append("MAINTENANCE.md: maintainer upstream-drift policy missing")
process_map_text = PROCESS_MAP.read_text()
if "Invocation owner" not in process_map_text or "**Human intent** starts external mutation" not in process_map_text:
    problems.append("10-process/README.md: stage invocation ownership is missing")
for required_state_text in ("prereqs_required: true", "capability_routes:", "verified_at: null"):
    if required_state_text not in state_text:
        problems.append(f"templates/.playbook-state.yml: missing cold-path state '{required_state_text}'")

# 10 — Wayfinder stays optional, visible, and distinct from implementation slicing
align_text = ALIGN.read_text()
version_readme_text = VERSION_README.read_text()
wayfinder_surfaces = {
    "AGENT-DIGEST.md": digest_text,
    "10-process/README.md": process_map_text,
    "10-process/01-align.md": align_text,
    "10-process/03-spec.md": SPEC.read_text(),
    "10-process/04-breakdown.md": BREAKDOWN.read_text(),
    "30-document-lifecycle.md": DOCUMENT_LIFECYCLE.read_text(),
    "README.md": version_readme_text,
}
if not WAYFINDER.exists():
    problems.append("92-wayfinder-track.md: optional Wayfinder track missing")
else:
    wayfinder_text = WAYFINDER.read_text()
    for required_wayfinder_text in (
        "## Invocation ownership",
        "user-invoked",
        "active_wayfinding_maps",
        "## Graduation",
        "### Abandoned or deferred outcome",
        "set `last_updated`",
        "recompute the normal status block",
        "One session resolves at most one decision ticket",
        "ready-for-agent",
    ):
        if required_wayfinder_text not in wayfinder_text:
            problems.append(
                f"92-wayfinder-track.md: missing contract text '{required_wayfinder_text}'"
            )
for surface, text in wayfinder_surfaces.items():
    if "92-wayfinder-track.md" not in text:
        problems.append(f"{surface}: missing 92-wayfinder-track.md pointer")
if "active_wayfinding_maps: []" not in state_text:
    problems.append("templates/.playbook-state.yml: missing active_wayfinding_maps empty-state contract")
for state_field in ("# - title:", "#   locator:", "#   destination:", "#   opened:"):
    if state_field not in state_text:
        problems.append(
            f"templates/.playbook-state.yml: missing open-map schema field '{state_field}'"
        )
planning_status_text = PLANNING_STATUS_TEMPLATE.read_text()
if "## Open Wayfinder maps" not in planning_status_text:
    problems.append("templates/planning-template/STATUS.md: missing open Wayfinder map index")
if "- [{map title}]({locator}) — {one-line destination}" not in planning_status_text:
    problems.append("templates/planning-template/STATUS.md: missing open-map mirror format")
whats_next_text = WHATS_NEXT.read_text()
fast_path_match = re.search(
    r"\*\*Fast path \(fresh status\):\*\*(.*?)(?=\n\n\*\*Full path)",
    whats_next_text,
    re.S,
)
if not fast_path_match or "active_wayfinding_maps" not in fast_path_match.group(1):
    problems.append("skills/whats-next/SKILL.md: fast path does not read active_wayfinding_maps")
for routing_contract in (
    "user-invoked",
    "5. Then an open Wayfinder map, oldest listed first — only when no active feature is in flight.",
    "/wayfinder {locator}",
    "wait for the human to invoke it",
    "do not offer the cadence dismissal replies",
    "Stage 12's retro reviews any map open longer than 30 days",
):
    if routing_contract not in whats_next_text:
        problems.append(
            f"skills/whats-next/SKILL.md: missing open-map routing contract '{routing_contract}'"
        )
if "active_wayfinding_maps" not in digest_text:
    problems.append("AGENT-DIGEST.md: open Wayfinder map state is invisible at session start")
if "wait for the human to invoke it" not in digest_text:
    problems.append("AGENT-DIGEST.md: session start must offer /wayfinder and wait for the human, never continue a map itself")
retro_text = (ROOT / "10-process" / "12-retro-and-learn.md").read_text()
if "## When a Wayfinder map goes stale" not in retro_text or "more than 30 days old" not in retro_text:
    problems.append("10-process/12-retro-and-learn.md: missing stale open-map review (30-day tripwire)")
delegation_text = DELEGATION.read_text()
if "not yet integrated" in delegation_text.lower() or "92-wayfinder-track.md" not in delegation_text:
    problems.append("91-delegation-track.md: Wayfinder relationship is stale or missing")

# 11 — model routing stays text-first, state-visible, and connected to lane stages
model_routing_surfaces = {
    "AGENT-DIGEST.md": digest_text,
    "10-process/README.md": process_map_text,
    "10-process/00-prereqs.md": prereqs_text,
    "10-process/01-align.md": align_text,
    "10-process/07-implementation-tdd.md": (ROOT / "10-process" / "07-implementation-tdd.md").read_text(),
    "10-process/08-review.md": (ROOT / "10-process" / "08-review.md").read_text(),
    "10-process/09-qa.md": (ROOT / "10-process" / "09-qa.md").read_text(),
    "README.md": version_readme_text,
}
problems.extend(model_routing_track_contract_problems(ROOT))
problems.extend(model_router_skill_routing_contract_problems(ROOT))
for surface, text in model_routing_surfaces.items():
    if "93-model-routing-track.md" not in text:
        problems.append(f"{surface}: missing 93-model-routing-track.md pointer")
if not MODEL_ROUTER.exists():
    problems.append("skills/model-router/SKILL.md: local model-router skill missing")
else:
    model_router_text = MODEL_ROUTER.read_text()
    for identity_contract in (
        "authoritative runtime evidence",
        "Model-generated self-description is not authoritative identity evidence",
    ):
        if identity_contract not in model_router_text:
            problems.append(
                f"skills/model-router/SKILL.md: missing identity contract '{identity_contract}'"
            )
if not MODEL_ROUTER_PROMPTS.exists():
    problems.append("skills/model-router/references/chat-prompts.md: text prompt contract missing")
else:
    model_prompt_text = MODEL_ROUTER_PROMPTS.read_text()
    for prompt_contract in (
        "Plan “{feature title}”",
        "Build “{feature title}”",
        "Verify “{feature title}”",
        "`plan` — start planning",
        "`openai defaults` — use the OpenAI defaults for this feature and start Plan",
        "`build one` — build the next slice, then stop",
        "`build all fast`",
        "Pace: standard",
        "`models` — change the build model first",
        "`verify` — start independent review and QA",
        "Choosing a model returns to the Build menu; nothing starts yet.",
        "uses this tab",
        "opens a new tab",
    ):
        if prompt_contract not in model_prompt_text:
            problems.append(
                "skills/model-router/references/chat-prompts.md: "
                f"missing text prompt contract '{prompt_contract}'"
            )
for state_contract in (
    "schema_version: 3",
    "pending_plan_routes: 0",
    "model_routing:",
    "pending_model_routes: []",
    "model_routing: null",
):
    if state_contract not in state_text:
        problems.append(f"templates/.playbook-state.yml: missing model-routing state '{state_contract}'")
for pending_status_contract in (
    "## Pending Plan routes",
    "mirroring resumable `pending_model_routes`",
):
    if pending_status_contract not in planning_status_text:
        problems.append(
            f"templates/planning-template/STATUS.md: missing pending-route contract '{pending_status_contract}'"
        )
for resume_contract in (
    "pending_plan_routes",
    "pending_model_routes",
    "resumable pending Plan route",
    "exact resume action",
    "3. Then a resumable pending Plan route, oldest listed first.",
):
    if resume_contract not in whats_next_text:
        problems.append(f"skills/whats-next/SKILL.md: missing pending-route contract '{resume_contract}'")
for closeout_contract in (
    "pending_closeouts",
    "2. Then a pending feature closeout, oldest shipped first.",
    "Never say “ready for new work” while one exists.",
    "recommend them as one closeout branch and PR",
):
    if closeout_contract not in whats_next_text:
        problems.append(f"skills/whats-next/SKILL.md: missing closeout contract '{closeout_contract}'")

for path, text, contracts in (
    (
        DOCUMENT_LIFECYCLE,
        DOCUMENT_LIFECYCLE.read_text(),
        (
            "update **every current-release pointer**",
            "### One closeout branch, one PR",
        ),
    ),
    (
        SHIP_STAGE,
        SHIP_STAGE.read_text(),
        (
            "An insist-level overdue architecture review runs before the merge",
            "A nudge-level overdue is surfaced but does not block the ship.",
            "share **one fresh closeout branch and one PR**",
        ),
    ),
    (
        ARCHITECTURE_STAGE,
        ARCHITECTURE_STAGE.read_text(),
        (
            "### Timing against an open feature PR",
            "run the review **before the human merges**",
        ),
    ),
):
    for contract in contracts:
        if contract not in text:
            problems.append(f"{path.relative_to(ROOT)}: missing V0.3.40 contract '{contract}'")

# 12 — release guidance must remain reachable and executable for existing projects
upgrade_text = UPGRADE_SKILL.read_text()
migrations_text = MIGRATIONS.read_text()
if "Read [`MIGRATIONS.md`](MIGRATIONS.md) completely for every upgrade" not in upgrade_text:
    problems.append("upgrade skill: same-major V0.3 upgrades do not read the field-level migration contract")
if "upgrade-project.py {project-path} --apply-safe" not in upgrade_text or not UPGRADE_SCRIPT.exists():
    problems.append("upgrade skill: deterministic recent-V0.3 migration seam is missing or unresolved")
for migration_contract in (
    "private V0.4.2",
    "public V0.5",
    "preserve project-written content",
    "no-change second run",
):
    if migration_contract not in migrations_text:
        problems.append(f"upgrade migrations: missing recent project contract '{migration_contract}'")

release_versions = {
    match.group(1)
    for match in re.finditer(r"^## (V0\.3\.(\d+))\b", CHANGELOG.read_text(), re.M)
    if int(match.group(2)) >= 31
}
for version in sorted(release_versions):
    if version not in migrations_text:
        problems.append(
            f"upgrade migrations: {version} has no project-side row; add a delta or an explicit no-op row"
        )

# 13 — new projects enter through one plan-first deterministic bootstrap seam
if not BOOTSTRAP_SKILL.exists() or not BOOTSTRAP_SCRIPT.exists():
    problems.append("bootstrap: skill or deterministic script is missing")
else:
    bootstrap_skill_text = BOOTSTRAP_SKILL.read_text()
    bootstrap_script_text = BOOTSTRAP_SCRIPT.read_text()
    for contract in (
        "Present the dry-run",
        "the user has seen and approved the complete plan",
        "Run stage 00's cold path",
        ".agents/skills/",
        "CONDUCTOR_WORKSPACE_PATH",
        "bundled `conductor` skill",
        ".conductor/settings.toml",
        ".conductor/settings.local.toml",
        "CONDUCTOR_PORT",
        "does not run retroactively",
        "merged to the remote default branch",
    ):
        if contract not in bootstrap_skill_text:
            problems.append(f"bootstrap skill: missing contract '{contract}'")
    for script_contract in (
        "ROOT_TEMPLATE_FILES",
        "DIRECTORY_TEMPLATES",
        "--apply",
        '".agents" / "skills"',
        "compute-status.py",
    ):
        if script_contract not in bootstrap_script_text:
            problems.append(f"bootstrap script: missing deterministic surface '{script_contract}'")
for surface, text in {
    "AGENT-DIGEST.md": digest_text,
    "README.md": version_readme_text,
}.items():
    if "/ai-playbook-bootstrap-project" not in text:
        problems.append(f"{surface}: missing first-time bootstrap skill route")
    if "Conductor setup lane" not in text:
        problems.append(f"{surface}: missing Conductor setup lane")

# 14 — terminal routing and routed worker evidence remain machine-readable end to end
process_map_text = PROCESS_MAP.read_text()
ship_stage_text = SHIP_STAGE.read_text()
retro_stage_text = RETRO_STAGE.read_text()
model_routing_text = MODEL_ROUTING.read_text()
model_router_text = MODEL_ROUTER.read_text()
for contract in ("playbook_result:", "outcome:", "next_stage:", "required_actions:"):
    if contract not in process_map_text:
        problems.append(f"process map: missing terminal result field '{contract}'")
for surface, text in {
    "ship stage": ship_stage_text,
    "retro stage": retro_stage_text,
    "whats-next": whats_next_text,
}.items():
    if "playbook_result" not in text:
        problems.append(f"{surface}: does not consume or return the terminal result contract")
for field in (
    "model_id", "reasoning_effort", "thinking", "thread_id", "runner", "permission_mode",
    "tool_calls_used", "tool_calls_remaining", "wall_time_used_seconds", "wall_time_remaining_seconds",
):
    if field not in model_routing_text:
        problems.append(f"model routing: worker-result envelope missing '{field}'")
for contract in ("authoritative worker-result envelope", "Reject any route mismatch automatically", "validated runtime envelope"):
    if contract not in model_router_text:
        problems.append(f"model-router skill: missing worker-result enforcement '{contract}'")

# 15 — the observational baseline is one contract across stage and copied templates
eval_contracts = (
    "Rework rate",
    "Time-to-merge (med/max)",
    "Verifier passes",
    "Catches",
    "unavailable — {reason}",
    "three-period baseline",
)
for surface, path in {
    "retro stage": RETRO_STAGE,
    "retro template": RETRO_TEMPLATE,
    "field-report template": FIELD_REPORT_TEMPLATE,
}.items():
    text = path.read_text()
    for contract in eval_contracts:
        if contract not in text:
            problems.append(f"{surface}: observational eval contract missing '{contract}'")

# 16 — legacy routes and the pre-v1.1 TDD loop stay out of live V0.3 surfaces
problems.extend(live_tdd_drift_problems(ROOT, CHANGELOG))

# 17 — architecture findings retain their source through tracker publication
problems.extend(architecture_issue_provenance_problems(ROOT))

# 18 — upstream reviewers do not take ownership of the enclosing transaction
problems.extend(embedded_upstream_contract_problems(ROOT))

# 19 — upstream behavior, names, versions, and stage memberships stay registry-driven
problems.extend(upstream_contract_problems(ROOT, CHANGELOG, REGISTRY))
problems.extend(upstream_version_problems(ROOT, REGISTRY))
problems.extend(stage_membership_problems(ROOT, REGISTRY))

# 20 — ordinary build authority must not regress into inherited time stops
problems.extend(ordinary_build_policy_problems(ROOT))

if problems:
    print("Markdown convention checks failed:")
    for p in problems:
        print(f"- {p}")
    sys.exit(1)

print(f"Markdown convention checks passed: {len(STAGES)} stage files, "
      f"{len(refs)} digest pointers, stage map exact, drift guards exact.")

"""Focused helpers shared by the V0.3 convention checker and its tests."""

import re
from pathlib import Path

import upstream_registry


ORDINARY_POLICY_SECTIONS = {
    "00-foundations.md": ("## 11. The budget floor", "## 12. Delivery authority"),
    "10-process/07-implementation-tdd.md": ("### The back-to-back loop's contract", "### Classifying failures outside the diff"),
    "AGENT-DIGEST.md": ("## Hard rules", "## Escape hatches"),
    "templates/CLAUDE.md": ("- **Budget floor", "## Constraints"),
    "../CLAUDE.md": ("- **Budget floor", "## Constraints"),
}
ORDINARY_POLICY_CLAUSES = {
    "00-foundations.md": {
        "checkpoint continuation": "Inherited time checkpoints and effort estimates in an ordinary issue build report progress, remaining work and a revised estimate; they do not require extension approval while the work makes demonstrable progress.",
        "returned fix and fresh Verify": "A concrete verifier finding re-enters Build and fresh Verify without a time-extension prompt.",
        "selected hard limit": "Stop for an explicitly selected hard time, cost or dispatch limit, an actual host/provider quota, Stop, a scope/authority/safety decision, or the cumulative retry and no-progress guards.",
        "cumulative guards": "A handoff does not reset those guards.",
        "protected ceilings": "Their approved limits are not converted to checkpoints by ordinary-build authority.",
        "build-one scope": "Build one remains build one; this rule grants no merge, activation, new service or spending authority.",
    },
    "10-process/07-implementation-tdd.md": {
        "checkpoint continuation": "An inherited time checkpoint reports evidence, remaining work and a revised estimate while progress continues; it is not an extension-approval boundary.",
        "returned fix and fresh Verify": "Frame it as a fresh fix task carrying the finding and evidence, then send it to fresh independent verification.",
        "selected hard limit": "an explicitly selected hard limit, an actual host/provider quota, or completion.",
        "cumulative guards": "Count the same failure signature across fix tasks and handoffs.",
        "protected ceilings": "Protected delivery and live qualification retain their own mandatory approved ceilings.",
        "build-one scope": "This authority lasts through the selected build-one, build-all or build-to endpoint.",
    },
    "AGENT-DIGEST.md": {
        "checkpoint continuation": "Ordinary issue builds use inherited time checkpoints and effort estimates for progress reporting, not extension-approval boundaries.",
        "returned fix and fresh Verify": "Necessary reversible in-scope returned fixes and fresh independent verification continue through the selected endpoint without a new prompt while progress is demonstrable.",
        "selected hard limit": "selected limits and actual host/provider quotas stop.",
        "cumulative guards": "Do not reset cumulative failure history across handoffs.",
        "protected ceilings": "Protected/autonomous delivery and live qualification retain mandatory approved ceilings",
        "build-one scope": "Back-to-back builds are opt-in via the typed build choice (build one / build all / build to <slice>)",
    },
    "templates/CLAUDE.md": {
        "checkpoint continuation": "Inherited time checkpoints, effort estimates and verification reserves report progress and plan capacity; they do not require extension approval while progress continues.",
        "returned fix and fresh Verify": "Ordinary issue builds include necessary reversible in-scope returned fixes and fresh independent verification through the selected endpoint.",
        "selected hard limit": "Explicitly selected hard limits, actual host/provider quotas, Stop, scope/authority/safety decisions and cumulative failure/no-progress guards still bind.",
        "protected ceilings": "Protected/autonomous delivery and live qualification retain mandatory approved limits.",
        "build-one scope": "this rule grants no merge, activation, new service or spending authority.",
    },
}
ORDINARY_POLICY_CLAUSES["../CLAUDE.md"] = ORDINARY_POLICY_CLAUSES["templates/CLAUDE.md"]
KNOWN_ORDINARY_POLICY_REVERSALS = (
    re.compile(r"(?:30-minute(?: time)?|inherited time) checkpoint[^.!?\n]{0,160}(?:pause|stop|wait)[^.!?\n]{0,160}(?:extension approval|more time)", re.I),
    re.compile(r"\bstop at the declared wall[- ]time\b", re.I),
    re.compile(r"\bignore the explicitly selected hard limit\b", re.I),
    re.compile(r"\bprotected delivery approval limits are optional\b", re.I),
)


def ordinary_build_policy_problems(root: Path | dict[str, str]) -> list[str]:
    """Guard named canonical clauses and known reversals, not arbitrary prose semantics."""

    if isinstance(root, dict):
        texts = root
    else:
        texts = {path: (root / path).read_text() for path in ORDINARY_POLICY_SECTIONS if path != "../CLAUDE.md"}
        sibling = root.parent / "CLAUDE.md"
        if sibling.is_file() and sibling.read_text().startswith("# CLAUDE.md — AI Engineering Playbook"):
            texts["../CLAUDE.md"] = sibling.read_text()
    problems = []
    for path, content in texts.items():
        if path not in ORDINARY_POLICY_SECTIONS:
            continue
        start, end = ORDINARY_POLICY_SECTIONS[path]
        if start not in content or end not in content:
            problems.append(f"{path}: ordinary build policy section is missing")
            continue
        section = content.split(start, 1)[1].split(end, 1)[0]
        normalized = " ".join(section.lower().split())
        for label, clause in ORDINARY_POLICY_CLAUSES[path].items():
            if " ".join(clause.lower().split()) not in normalized:
                problems.append(f"{path}: canonical ordinary build clause missing: {label}")
        for reversal in KNOWN_ORDINARY_POLICY_REVERSALS:
            if reversal.search(content):
                problems.append(f"{path}: known ordinary build policy reversal: {reversal.pattern}")
    for path in ORDINARY_POLICY_CLAUSES:
        if path != "../CLAUDE.md" and path not in texts:
            problems.append(f"{path}: ordinary build policy source is missing")
    return problems


LEGACY_PROCESS_FRAGMENT = "../processes/matt-pocock-inspired/"
STALE_TDD_PATTERNS = (
    re.compile(
        r"\bred\s*(?:,\s*(?:then\s+)?|→\s*|[-=]+>\s*)green\s*"
        r"(?:,\s*(?:then\s+)?|→\s*|[-=]+>\s*)(?:refactor|tidy[- ]?up)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfailing test\s*(?:→|[-=]+>)\s*code\s*(?:→|[-=]+>)\s*green\s*"
        r"(?:→|[-=]+>)\s*refactor\b",
        re.IGNORECASE,
    ),
)
LITE_SEAM_QUESTION = "How will we know it works, and at which public seam will we test it?"
ARCHITECTURE_ORIGIN_LABEL = "source:improve-codebase-architecture"
ARCHITECTURE_ORIGIN_SOURCE = "Source skill: /improve-codebase-architecture"
ARCHITECTURE_PROVENANCE_CONTRACTS = {
    Path("10-process/06-architecture.md"): (
        f"Add `{ARCHITECTURE_ORIGIN_SOURCE}` to the issue body.",
        f"Create or reuse the tracker label `{ARCHITECTURE_ORIGIN_LABEL}`",
        "apply it to every umbrella issue, slice, or follow-up directly produced from this review.",
        "Carry both markers into stage 04 or any later ticket split.",
        "Do not apply the label merely because an independently created issue is architecture-related.",
        "If the tracker has no labels, the source line is the required fallback.",
        "Before closing the review, query the created issues and verify that each direct descendant carries the available marker.",
    ),
    Path("10-process/04-breakdown.md"): (
        "every published umbrella, slice, and direct follow-up preserves both markers:",
        f"`{ARCHITECTURE_ORIGIN_SOURCE}` in the issue body.",
        f"Tracker label `{ARCHITECTURE_ORIGIN_LABEL}` when labels are supported.",
        "Propagate the markers through later re-slicing.",
        "Do not infer them for merely related architecture work created from another review or request.",
    ),
}
EMBEDDED_UPSTREAM_CONTRACTS = {
    Path("00-foundations.md"): (
        "report-only stage-09 browser/device pass",
        "compatibility-gated or manual stage-08 security pass",
    ),
    Path("40-self-improvement.md"): (
        "compatibility-gated or manual security pass",
    ),
    Path("80-quickstart.md"): (
        "stage-08 stage-owned standards/spec pass",
    ),
    Path("skills/README.md"): (
        "## Embedded upstream skill contract",
        "`commit_owner`: the playbook stage.",
        "`mutation_mode`: `report-only`.",
        "Structured question controls are optional transport",
        "Unknown, missing, or source-drifted integrations take the manifest's fallback",
        "Embedded skills do not self-upgrade",
    ),
    Path("skills/ai-playbook-design-review/SKILL.md"): (
        "name: ai-playbook-design-review",
        "Report-only UI verification",
        "desktop, tablet, and mobile",
        "horizontal body overflow",
        "44 px tap targets",
        "table wrapper readability",
        "heading hierarchy",
        "compact-control exceptions",
        "drawer, filter, tab, link, hash, query, and row expansions",
        "native form submission",
        "scroll position and focus",
        "severity, confidence, action tag, and evidence",
        "separate generator task",
    ),
    Path("10-process/00-prereqs.md"): (
        "check-upstream-compatibility.py",
        "Exit 2 means use the named fallback",
    ),
    Path("10-process/07-implementation-tdd.md"): (
        "`/implement` is not an embedded stage-07 route.",
    ),
    Path("10-process/08-review.md"): (
        "`/ai-playbook-design-review`",
        "direct upstream reviewer only after",
        "report-only compatibility",
        "separate generator task",
    ),
    Path("10-process/09-qa.md"): (
        "Report-only verification is the default.",
        "check-upstream-compatibility.py",
        "separate generator task",
        "row expansions",
        "native form submission",
    ),
    Path("20-frontend-track.md"): ("`/ai-playbook-design-review`",),
    Path("templates/playbook-cadences.yml"): ("action: /ai-playbook-design-review",),
    Path("MAINTENANCE.md"): (
        "upstream-integrations.json",
        "check-upstream-compatibility.py",
    ),
}
MODEL_ROUTING_TRACK_CONTRACTS = (
    "plain text",
    "`openai defaults`",
    "`models`",
    "| Plan | 01–06 | `gpt-6.1-sol` | high |",
    "| Build | 07 and returned fixes | `gpt-6.1-sol` | medium |",
    "| Verify | 08–09 | `gpt-6.1-sol` | high |",
    "pending_model_routes",
    "status.pending_plan_routes",
    "uses this tab",
    "opens a new tab",
    "Never substitute",
    "generated content and is never authoritative identity evidence",
    "## Codex pace overlay",
    "1.5× generation speed with increased usage",
    "never as the next session's default",
    "## Verify runner preference",
    "Verify prefers a runner other than the Build runner that actually ran",
    "relative to the Build runner that actually ran, never to the default lane table",
    "The Build lane's coverage of stage 07 and returned fixes carries the preference",
    "A project with one available runner reads this same rule and is not interrupted",
    "Worked example: Build actually ran on `claude-code`",
    "prefers a runner other than `claude-code` — for example `codex` — ahead of offering `claude-code` itself",
    "When no different runner is reachable, Verify proceeds on an available runner and records the fallback",
    "the preference never stops the run by itself",
    "it never substitutes a runner silently",
    "Worked fallback example: a project configures only `claude-code`",
    "records `cross_runner: false` with `cross_runner_reason: single_runner_project`",
    "for Verify selections only: `cross_runner` (`true` or `false`)",
    "`cross_runner_reason` from a closed set — `single_runner_project`, `preferred_runner_unavailable`,",
    "`null` when `cross_runner` is `true`",
    "single_runner_project",
    "preferred_runner_unavailable",
    "human_override",
)

MODEL_ROUTER_SKILL_ROUTING_CONTRACTS = (
    "worker-result envelope's `runner` field is authoritative",
    "read the persisted lane record only when no envelope is available",
    "discovery to prefer a runner other than that one, per `93-model-routing-track.md`'s Verify runner preference",
    "A project with one available runner has no alternate to prefer, so discovery proceeds unchanged",
    "For Verify, also persist `cross_runner`",
    "`cross_runner_reason` from `93-model-routing-track.md`'s closed set",
)
FORBIDDEN_ADAPTER_COMMANDS = ("git commit", "git stash", "git push")
UPSTREAM_BEHAVIOUR_CONTRACTS = (
    (
        "stage 00",
        Path("10-process/00-prereqs.md"),
        (
            "/writing-for-agents",
            "policy.allow_implicit_invocation: false",
            "~/.agents/skills/",
        ),
    ),
    (
        "debug stage",
        Path("10-process/11-debug.md"),
        ("<REDACTED>", "redacted output", "environment variables", "`capture` prompt"),
    ),
    (
        "architecture stage",
        Path("10-process/06-architecture.md"),
        ("Scope before scanning", "/codebase-design", "available subagent mechanism"),
    ),
    (
        "review stage",
        Path("10-process/08-review.md"),
        ("harness-neutral", "available parallel-agent mechanism"),
    ),
    (
        "Wayfinder track",
        Path("92-wayfinder-track.md"),
        ("decision ticket", "research/<name>", "/research` subagent", "prototype/<name>"),
    ),
    (
        "frontend track",
        Path("20-frontend-track.md"),
        ("### Prototype evidence", "self-contained HTML file", "prototype/<name>"),
    ),
    (
        "local skill index",
        Path("skills/README.md"),
        ("/writing-for-agents", "agents/openai.yaml", "policy.allow_implicit_invocation: false"),
    ),
    (
        "delegation track",
        Path("91-delegation-track.md"),
        ("merge base", "both sides' intent", "phase's verification commands"),
    ),
)


def architecture_issue_provenance_problems(root: Path) -> list[str]:
    """Keep architecture-review provenance present at both tracker handoffs."""

    problems: list[str] = []
    for relative, contracts in ARCHITECTURE_PROVENANCE_CONTRACTS.items():
        path = root / relative
        text = path.read_text() if path.is_file() else ""
        missing = [contract for contract in contracts if contract not in text]
        if missing:
            problems.append(
                f"{relative}: architecture issue provenance contract missing "
                + ", ".join(repr(contract) for contract in missing)
            )
    return problems


def embedded_upstream_contract_problems(root: Path) -> list[str]:
    """Keep embedded reviewers report-only and their live routes contract-gated."""

    problems: list[str] = []
    for relative, contracts in EMBEDDED_UPSTREAM_CONTRACTS.items():
        path = root / relative
        text = path.read_text() if path.is_file() else ""
        missing = [contract for contract in contracts if contract not in text]
        if missing:
            problems.append(
                f"{relative}: embedded upstream contract missing "
                + ", ".join(repr(contract) for contract in missing)
            )
    adapter = root / "skills" / "ai-playbook-design-review" / "SKILL.md"
    adapter_text = adapter.read_text() if adapter.is_file() else ""
    for command in FORBIDDEN_ADAPTER_COMMANDS:
        if command in adapter_text:
            problems.append(
                f"skills/ai-playbook-design-review/SKILL.md: forbidden transaction command {command!r}"
            )
    return problems


def model_routing_track_contract_problems(root: Path) -> list[str]:
    """Keep the Verify runner preference stated, worked, and connected to lane defaults."""

    path = root / "93-model-routing-track.md"
    if not path.is_file():
        return ["93-model-routing-track.md: optional model-routing track missing"]
    text = path.read_text()
    return [
        f"93-model-routing-track.md: missing routing contract '{contract}'"
        for contract in MODEL_ROUTING_TRACK_CONTRACTS
        if contract not in text
    ]


def model_router_skill_routing_contract_problems(root: Path) -> list[str]:
    """Keep the model-router skill's Verify runner-preference discovery and persistence text gated."""

    path = root / "skills" / "model-router" / "SKILL.md"
    if not path.is_file():
        return ["skills/model-router/SKILL.md: local model-router skill missing"]
    text = path.read_text()
    return [
        f"skills/model-router/SKILL.md: missing routing contract '{contract}'"
        for contract in MODEL_ROUTER_SKILL_ROUTING_CONTRACTS
        if contract not in text
    ]


def legacy_command_has_context(line: str, command: str) -> bool:
    """Return whether a legacy command reference has explicit historical context."""

    token = re.escape(command)
    ref = rf"(?:`/{token}`|/{token}|\b{token}\b)"
    patterns = (
        rf"\b(?:formerly|legacy|old)\s+{ref}",
        rf"\bnamed\s+{ref}\s+before\b",
        rf"{ref}.{{0,30}}\bis\s+now\b",
        rf"{ref}.{{0,80}}\b(?:is|are|was|were)\s+[*_]*(?:now\s+)?[*_]*(?:merged|renamed|replaced)\b",
    )
    return any(re.search(pattern, line, re.I) for pattern in patterns)


def upstream_contract_problems(
    root: Path, changelog: Path, registry: upstream_registry.Registry
) -> list[str]:
    """Keep registry-recorded legacy names and behavior contracts on live surfaces."""

    problems: list[str] = []
    old_names = sorted(registry.previous_name_map()) + sorted(registry.removed_names())
    for md_file in sorted(root.rglob("*.md")):
        if md_file == changelog or "analysis" in md_file.relative_to(root).parts:
            continue
        for line in md_file.read_text().splitlines():
            for old_name in old_names:
                pattern = rf"(?:/{re.escape(old_name)}\b|\b{re.escape(old_name)}\b)"
                if not re.search(pattern, line):
                    continue
                if not (
                    re.search(
                        r"\b(?:renamed|replaced|removed|historical|pre-v\d|upgrade (?:history|compatibility))\b",
                        line,
                        re.I,
                    )
                    or legacy_command_has_context(line, old_name)
                ):
                    problems.append(
                        f"{md_file.relative_to(root)}: {old_name} is live "
                        "without explicit history/compatibility context"
                    )

    for surface, relative, contracts in UPSTREAM_BEHAVIOUR_CONTRACTS:
        path = root / relative
        text = path.read_text() if path.is_file() else ""
        for contract in contracts:
            if contract not in text:
                problems.append(f"{surface}: missing upstream behaviour contract '{contract}'")
    return problems


def _live_markdown_files(root: Path) -> list[Path]:
    """Return live Markdown surfaces, excluding history-only files."""

    return [
        path for path in sorted(root.rglob("*.md"))
        if "analysis" not in path.relative_to(root).parts
        and path.name not in {"CHANGELOG.md", "MIGRATIONS.md"}
    ]


def upstream_version_problems(root: Path, registry: upstream_registry.Registry) -> list[str]:
    """Ensure live Matt references and manifest tested versions derive from the registry."""

    problems: list[str] = []
    matt_pin = registry.packages["mattpocock-skills"].pin["value"]
    version_pattern = re.compile(r"mattpocock/skills[`\s]+(v\d+\.\d+\.\d+)")
    for path in _live_markdown_files(root):
        for match in version_pattern.finditer(path.read_text()):
            if match.group(1) != matt_pin:
                problems.append(
                    f"{path.relative_to(root)}: Matt version {match.group(1)} does not match registry {matt_pin}"
                )

    manifest_path = root / "upstream-integrations.json"
    if manifest_path.is_file():
        import json

        manifest = json.loads(manifest_path.read_text())
        gstack_pin = registry.packages["gstack"].pin
        expected = f"{gstack_pin['value']} ({gstack_pin['commit']})"
        for key, entry in manifest.get("integrations", {}).items():
            if entry.get("upstream") == "garrytan/gstack" and entry.get("tested_version") != expected:
                problems.append(
                    f"upstream-integrations.json: {key} tested_version {entry.get('tested_version')!r} "
                    f"does not match registry {expected!r}"
                )
    return problems


def stage_membership_problems(root: Path, registry: upstream_registry.Registry) -> list[str]:
    """Ensure declared stage membership mirrors live stage-route references."""

    problems: list[str] = []
    stage_files = {
        path.name[:2]: path
        for path in (root / "10-process").glob("[0-9][0-9]-*.md")
        if path.name != "00-prereqs.md"
    }
    for skill in registry.skills.values():
        if skill.status != "current":
            continue
        declared = {stage for stage in skill.stages if re.fullmatch(r"\d{2}", stage)} - {"00"}
        pattern = re.compile(rf"/{re.escape(skill.name)}\b")
        actual = {
            code for code, path in stage_files.items()
            if pattern.search(path.read_text())
        }
        for code in sorted(declared - actual):
            problems.append(f"{skill.name}: missing from declared stage {code}")
        for code in sorted(actual - declared):
            problems.append(f"{skill.name}: present in undeclared stage {code}")
    return problems


def live_tdd_drift_problems(root: Path, changelog: Path) -> list[str]:
    """Return stale-route/TDD guidance found on live V0.3 surfaces."""

    problems: list[str] = []
    history_paths = {
        changelog,
        root / "skills" / "ai-playbook-upgrade-project" / "MIGRATIONS.md",
    }
    live_files = sorted((*root.rglob("*.md"), *root.rglob("*.html"), *root.rglob("*.js")))
    for live_file in live_files:
        if live_file in history_paths:
            continue
        live_text = live_file.read_text()
        if LEGACY_PROCESS_FRAGMENT in live_text:
            problems.append(
                f"{live_file.relative_to(root)}: live V0.3 surface links to the legacy "
                "pre-v1.0 Matt Pocock process"
            )
        for pattern in STALE_TDD_PATTERNS:
            match = pattern.search(live_text)
            if match:
                problems.append(
                    f"{live_file.relative_to(root)}: stale pre-v1.1 TDD loop phrase "
                    f"'{match.group(0)}'"
                )

    lite_mode = root / "70-lite-mode.md"
    lite_text = lite_mode.read_text() if lite_mode.is_file() else ""
    if LITE_SEAM_QUESTION not in lite_text:
        problems.append(
            "70-lite-mode.md: lite alignment does not explicitly confirm the public test seam"
        )
    return problems

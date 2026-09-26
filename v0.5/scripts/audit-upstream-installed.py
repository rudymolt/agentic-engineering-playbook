#!/usr/bin/env python3
"""Maintainer-only probe: compare the host's installed upstream skills with the
registry pins and the integration manifest, and draft the monthly sync report.

Reads the maintainer's home directory (the skills CLI lock file, the gstack
checkout), so it is deliberately NOT part of verify-playbook.py. It reports and
never fails: exit 0 always. `--json` emits the report object; the default is
Markdown suitable for the monthly analysis note.

Slice 1 of the upstream-skill-lifecycle feature: read-only. Pin writing
(`--write-pins`) arrives with slice 2.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upstream_registry as ur  # noqa: E402

COMPATIBILITY_PATH = Path(__file__).with_name("check-upstream-compatibility.py")
_SPEC = importlib.util.spec_from_file_location("upstream_compatibility_for_probe", COMPATIBILITY_PATH)
assert _SPEC and _SPEC.loader
COMPATIBILITY = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(COMPATIBILITY)

DEFAULT_MANIFEST = ur.ROOT / "upstream-integrations.json"
SKILL_ROOTS = (".agents/skills", ".claude/skills", ".codex/skills")


# ------------------------------------------------------------------ readers

def read_skill_lock(home: Path, lock_file: str) -> dict[str, dict] | None:
    path = Path(lock_file.replace("~", str(home), 1)) if lock_file.startswith("~") else home / lock_file
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    skills = payload.get("skills")
    return skills if isinstance(skills, dict) else None


def read_checkout(path: Path, version_file: str | None) -> dict:
    info: dict = {"path": str(path), "exists": path.is_dir(), "version": None, "head": None}
    if not info["exists"]:
        return info
    if version_file and (path / version_file).is_file():
        info["version"] = (path / version_file).read_text().strip()
    completed = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
    )
    if completed.returncode == 0:
        info["head"] = completed.stdout.strip()
    return info


def resolve_checkout(package: ur.Package, home: Path, overrides: dict[str, Path]) -> Path | None:
    if package.name in overrides:
        return overrides[package.name]
    raw = package.install.get("checkout")
    if not raw:
        return None
    return Path(str(raw).replace("~", str(home), 1)) if str(raw).startswith("~") else Path(raw)


def installed_source(skill: ur.Skill, package: ur.Package, home: Path, checkout: Path | None) -> Path | None:
    if package.install.get("method") == "git-checkout" and checkout is not None:
        candidate = checkout / skill.name / "SKILL.md"
        return candidate if candidate.is_file() else None
    for root in SKILL_ROOTS:
        candidate = home / root / skill.name / "SKILL.md"
        if candidate.is_file():
            return candidate
    return None


# -------------------------------------------------------------------- probe

def package_status(package: ur.Package, lock: dict | None, checkout_info: dict | None) -> str:
    if package.kind == "local":
        return "not applicable (playbook-owned)"
    method = package.install.get("method")
    if method == "skills-cli":
        if lock is None:
            return "lock file not found: package not installed through the skills CLI"
        stamps = sorted(entry.get("updatedAt", "") for entry in lock.values() if entry.get("source") in package.source)
        newest = stamps[-1][:10] if stamps else "unknown"
        return f"installed via skills CLI; newest skill update {newest}; pin {package.pin.get('value') or package.pin['commit']} (installed revision is not recorded by the CLI)"
    if method == "git-checkout":
        if not checkout_info or not checkout_info["exists"]:
            return "checkout not found"
        head = checkout_info["head"] or "unknown"
        pin_commit = package.pin["commit"]
        version = checkout_info["version"] or "unknown"
        if head != "unknown" and head.startswith(pin_commit):
            return f"matches pin {pin_commit} (VERSION {version})"
        return f"installed VERSION {version} at {head[:7]} differs from pin {package.pin.get('value') or ''} ({pin_commit})".replace("pin  (", "pin (")
    if method == "none":
        return "not installed by design (level 0 source package)"
    return f"install method {method!r} not probed"


def probe(
    registry: ur.Registry,
    manifest_path: Path,
    home: Path,
    checkout_overrides: dict[str, Path] | None = None,
) -> dict:
    overrides = checkout_overrides or {}
    report: dict = {"home": str(home), "packages": [], "skills": {}, "unregistered": {},
                    "stale_renamed": {}, "manifest": [], "borrowed_ideas": [], "manifest_problems": []}
    try:
        manifest = COMPATIBILITY.load_manifest(manifest_path)
    except COMPATIBILITY.ManifestError as error:
        manifest = {"integrations": {}}
        report["manifest_problems"].append(str(error))
    report["manifest_problems"].extend(ur.manifest_problems(registry, manifest))

    locks: dict[str, dict | None] = {}
    checkouts: dict[str, Path | None] = {}
    for package in registry.packages.values():
        lock = None
        checkout_info = None
        if package.install.get("method") == "skills-cli":
            lock = read_skill_lock(home, str(package.install.get("lock_file", "~/.agents/.skill-lock.json")))
        checkout = resolve_checkout(package, home, overrides)
        checkouts[package.name] = checkout
        if package.install.get("method") == "git-checkout" and checkout is not None:
            checkout_info = read_checkout(checkout, package.install.get("version_file"))
        locks[package.name] = lock
        report["packages"].append({
            "name": package.name, "kind": package.kind, "adoption_level": package.adoption_level,
            "pin": package.pin, "checkout": checkout_info,
            "status": package_status(package, lock, checkout_info),
        })
        if package.kind == "local":
            continue
        rows = []
        registered = set()
        for skill in registry.skills_for(package.name, status=None):
            registered.add(skill.name)
            source = installed_source(skill, package, home, checkout)
            entry = (lock or {}).get(skill.name)
            rows.append({
                "name": skill.name, "status": skill.status, "installed": source is not None,
                "source": str(source) if source else None,
                "lock_updated": (entry or {}).get("updatedAt"),
                "lock_hash": (entry or {}).get("skillFolderHash"),
                "note": ("removed upstream but still installed" if skill.status == "removed" and source
                         else "not installed" if skill.status == "current" and source is None else ""),
            })
        report["skills"][package.name] = rows
        present: set[str] = set()
        if lock:
            present |= {name for name, entry in lock.items() if entry.get("source") in package.source}
        if checkout is not None and checkout.is_dir():
            present |= {p.parent.name for p in checkout.glob("*/SKILL.md")}
        renames = registry.previous_name_map()
        leftovers = present - registered
        report["stale_renamed"][package.name] = sorted(
            f"{name} → {renames[name]}" for name in leftovers if name in renames
        )
        report["unregistered"][package.name] = sorted(name for name in leftovers if name not in renames)

    for key, entry in sorted(manifest.get("integrations", {}).items()):
        skill_name = registry.manifest_keys().get(key)
        skill = registry.skills.get(skill_name) if skill_name else None
        package = registry.packages[skill.package] if skill else None
        source = installed_source(skill, package, home, checkouts.get(package.name)) if skill and package else None
        if source is None:
            decision = {"status": "missing", "reason": "installed source not found", "actual": None}
        else:
            result = COMPATIBILITY.evaluate(key, source, "manual", manifest_path)
            decision = {"status": result.status, "reason": result.reason, "actual": result.actual_sha256}
        report["manifest"].append({
            "key": key, "skill": skill_name, "upstream": entry.get("upstream"),
            "tested_version": entry.get("tested_version"), "expected": entry.get("tested_source_sha256"),
            "installed_source": str(source) if source else None, "fallback": entry.get("fallback"),
            **decision,
        })

    for idea in registry.borrowed_ideas:
        report["borrowed_ideas"].append({**idea, "upstream_change": "not fetched (slice 2 adds the watch fetch)"})
    return report


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ render

def render_markdown(report: dict) -> str:
    lines = ["# Upstream installed-state report", "", f"Host home: `{report['home']}`", ""]
    lines += ["## Packages", "", "| Package | Level | Pin | Installed |", "|---|---|---|---|"]
    for pkg in report["packages"]:
        pin = pkg["pin"].get("value") or pkg["pin"].get("commit") or "—"
        lines.append(f"| {pkg['name']} | {pkg['adoption_level'] or pkg['kind']} | `{pin}` | {pkg['status']} |")
    lines.append("")
    lines += ["## Embedded reviewer manifest", "",
              "| Key | Tested version | Installed digest | Verdict | Reason |", "|---|---|---|---|---|"]
    for row in report["manifest"]:
        digest = "matches" if row["actual"] == row["expected"] else (row["actual"] or "—")[:12]
        lines.append(f"| {row['key']} | {row['tested_version']} | {digest} | **{row['status']}** | {row['reason']} |")
    lines.append("")
    if report["manifest_problems"]:
        lines += ["Manifest cross-validation problems:", ""] + [f"- {p}" for p in report["manifest_problems"]] + [""]
    for package, rows in report["skills"].items():
        missing = [r["name"] for r in rows if r["status"] == "current" and not r["installed"]]
        stale = [r["name"] for r in rows if r["status"] == "removed" and r["installed"]]
        extra = report["unregistered"].get(package, [])
        lines += [f"## {package}", "",
                  f"- Registered current skills: {sum(1 for r in rows if r['status'] == 'current')}; installed: "
                  f"{sum(1 for r in rows if r['status'] == 'current' and r['installed'])}"]
        lines.append(f"- Registered but not installed: {', '.join(missing) if missing else 'none'}")
        lines.append(f"- Removed upstream but still installed: {', '.join(stale) if stale else 'none'}")
        stale_renamed = report["stale_renamed"].get(package, [])
        lines.append(f"- Stale copies of renamed skills still installed: "
                     f"{', '.join(stale_renamed) if stale_renamed else 'none'}")
        lines.append(f"- Installed but not in the registry (adoption candidates or private skills): "
                     f"{', '.join(extra) if extra else 'none'}")
        lines.append("")
    if report["borrowed_ideas"]:
        lines += ["## Borrowed ideas", ""]
        for idea in report["borrowed_ideas"]:
            lines.append(f"- {idea['package']} · {idea['id']}: {idea['upstream_change']}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=ur.DEFAULT_REGISTRY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--gstack-checkout", type=Path, default=None,
                        help="override the registry's gstack checkout path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        registry = ur.load(args.registry)
    except ur.RegistryError as error:
        print(f"registry invalid: {error}", file=sys.stderr)
        return 1
    overrides = {"gstack": args.gstack_checkout} if args.gstack_checkout else {}
    report = probe(registry, args.manifest, args.home, overrides)
    print(json.dumps(report, indent=2, default=str) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

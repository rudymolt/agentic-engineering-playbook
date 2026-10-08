#!/usr/bin/env python3
"""JSON helper for the typed Configure skill and existing model-router reader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import subprocess

from playbook_config import Configuration, ConfigError, RecoveryRequired, public_error_message, strict_json
from model_recommendations import OfficialSources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--preferences-dir", type=Path, help="Explicit user-local directory outside the project for presentation, billing, reusable defaults and named presets.")
    parser.add_argument("--custom-bindings-dir", type=Path, help="Read-only machine-local custom bindings and stage-retained audits; never saved in project configuration.")
    parser.add_argument("--discovery", type=Path)
    parser.add_argument("--discovery-command", help="JSON argv for the current-availability adapter; request JSON is sent on stdin.")
    parser.add_argument("--now", help="Fixture clock only; live use omits this option.")
    parser.add_argument("--evidence-fixture", type=Path, help="Controlled official evidence fixture; requires --now, never live proof.")
    parser.add_argument('--evidence-dir', type=Path, help='External private advisory cache directory; never launch authority.')
    parser.add_argument("action", choices=("read", "reply", "resolve", "advise", "job-route"))
    args = parser.parse_args()

    def binding_catalog():
        if args.custom_bindings_dir is None:
            return None
        from skill_bindings import JobBindings
        return JobBindings(args.project, custom_dir=args.custom_bindings_dir)

    def discover(request):
        if args.discovery_command is None:
            raise ConfigError("Supply --discovery-command for a fresh authoritative recheck; a saved --discovery file cannot prove current availability.")
        command = strict_json(args.discovery_command)
        if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
            raise ConfigError("Discovery command must be a nonempty JSON argv list.")
        result = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True)
        if result.returncode:
            raise ConfigError("Current-availability adapter failed; rediscover without saving.")
        return strict_json(result.stdout)

    clock = (lambda: args.now) if args.now else None
    request = None
    sources = None
    service = None
    try:
        request = strict_json(sys.stdin.read() or "{}")
        if not isinstance(request, dict):
            raise ConfigError("Request must be a JSON object; use the documented helper contract.")
        if args.evidence_fixture and not args.now:
            raise ConfigError("Evidence fixtures require the controlled fixture clock; never present them as live current facts.")
        sources = ((lambda: strict_json(args.evidence_fixture.read_text())) if args.evidence_fixture else
                   (None if args.now else OfficialSources().retrieve))
        try:
            service = Configuration(args.project, discover, clock, preferences_dir=args.preferences_dir,
                                    context=request.get("context"),
                                    recommendation_sources=sources,
                                    evidence_dir=args.evidence_dir or (None if args.now else Path.home() / '.cache' / 'ai-playbook-evidence'),
                                    bindings=binding_catalog())
        except ConfigError:
            reply = request.get("reply", "")
            if args.action != "reply" or not isinstance(reply, str):
                raise
            reply = reply.strip().lower()
            if reply not in {"back", "edit", "not now"} and not reply.startswith("edit "):
                raise
            service = Configuration(args.project, discover, clock, context=request.get("context"),
                                    recommendation_sources=sources,
                                    evidence_dir=args.evidence_dir or (None if args.now else Path.home() / '.cache' / 'ai-playbook-evidence'),
                                    bindings=binding_catalog())
        if args.action == "read":
            result = service.read()
        elif args.action == "reply":
            result = service.reply(request["proposal"], request["reply"])
        elif args.action == "resolve":
            result = service.resolve(request["role"], request.get("feature_choice"))
        elif args.action == "advise":
            result = service.advise(request["role"], request.get("feature_choice"))
        else:
            result = service.dispatch_job(request["job"], request["owner"], approved_binding=request.get("approved_binding"))
    except (ConfigError, OSError, KeyError, TypeError, AttributeError, UnicodeError) as error:
        result = {"state": "recovery_required" if isinstance(error, RecoveryRequired) else "blocked", "message": public_error_message(error), "launched": False}
        if isinstance(request, dict):
            adapter = getattr(sources, '__self__', None)
            result = Configuration.retain_proposal(result, request.get("proposal"), now=args.now,
                                                  reviewed=service._official_reviewed_guidance() if service is not None else
                                                  ([] if isinstance(adapter, OfficialSources) else None))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if result.get("state") in {"blocked", "recovery_required"} else 0


if __name__ == "__main__":
    raise SystemExit(main())

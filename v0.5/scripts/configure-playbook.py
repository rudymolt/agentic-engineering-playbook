#!/usr/bin/env python3
"""JSON helper for the typed Configure skill and existing model-router reader."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from playbook_config import Configuration, ConfigError, strict_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--discovery", type=Path)
    parser.add_argument("--now", help="Fixture clock only; live use omits this option.")
    parser.add_argument("action", choices=("read", "reply", "resolve"))
    args = parser.parse_args()

    def discover():
        if args.discovery is None:
            raise ConfigError("Supply fresh authoritative discovery through --discovery; no saved catalogue authorises launch.")
        return strict_json(args.discovery.read_text())

    clock = (lambda: args.now) if args.now else None
    service = Configuration(args.project, discover, clock)
    try:
        request = strict_json(sys.stdin.read() or "{}")
        if not isinstance(request, dict):
            raise ConfigError("Request must be a JSON object; use the documented helper contract.")
        if args.action == "read":
            result = service.read()
        elif args.action == "reply":
            result = service.reply(request["proposal"], request["reply"])
        else:
            result = service.resolve(request["role"], request.get("feature_choice"))
    except (ConfigError, OSError, KeyError, TypeError, AttributeError, UnicodeError) as error:
        result = {"state": "blocked", "message": str(error), "launched": False}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 2 if result.get("state") in {"blocked", "recovery_required"} else 0


if __name__ == "__main__":
    raise SystemExit(main())

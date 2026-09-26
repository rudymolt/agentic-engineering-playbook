#!/usr/bin/env python3
"""Controlled notes application: real JSON persistence, no network or secrets."""

import argparse
import json
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, help="isolated notes file owned by the caller")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="observe instance, revision, auth and readiness")
    commands.add_parser("list", help="read persisted notes")
    commands.add_parser("create", help="persist a nonempty note").add_argument("text")
    args = parser.parse_args()
    try:
        instance = json.loads(Path(__file__).with_name("instance.json").read_text())
        # This is a public fixture authorization marker, never a credential.
        authorized = os.environ.get("VERIFY_HARNESS_AUTH") == "fixture-test-authorized"
        if args.command == "status":
            print(json.dumps({**instance, "authorized": authorized}))
            return 0
        if not authorized or not instance["ready"]:
            print("blocked: authorize the fixture and restore its readiness", file=sys.stderr)
            return 2
        if args.state is None:
            print("error: provide --state for an isolated notes file", file=sys.stderr)
            return 1
        notes = json.loads(args.state.read_text()) if args.state.exists() else []
        if args.command == "list":
            print(json.dumps({"notes": notes}))
        elif not args.text.strip():
            print(json.dumps({"error": "note must not be empty"}))
            return 1
        else:
            notes.append(args.text)
            # Deliberately broken application persistence. The harness must
            # discover the lost write by invoking list in another process.
            if os.environ.get("FIXTURE_BEHAVIOR_BROKEN") != "1":
                args.state.write_text(json.dumps(notes) + "\n")
            print(json.dumps({"created": args.text}))
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"error: inspect fixture configuration/state: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

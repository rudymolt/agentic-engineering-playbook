#!/usr/bin/env python3
"""Drive public notes CLI commands and retain each run: 0 passed, 1 failed."""
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    if sys.argv[1:] == ["--help"]:
        print(__doc__ + " Usage: drive.py {create-note|list-notes|reject-broken} [--report-only]")
        return 0
    args = sys.argv[1:]
    report_only = len(args) == 2 and args[1] == "--report-only"
    feature = args[0] if len(args) == 1 or report_only else ""
    if feature not in {"create-note", "list-notes", "reject-broken"}:
        print("error: choose a mapped feature; use --help", file=sys.stderr)
        return 1
    if not os.environ.get("VERIFY_EVIDENCE_DIR"):
        print("error: set VERIFY_EVIDENCE_DIR before driving", file=sys.stderr)
        return 1
    root = Path(__file__).resolve().parent
    evidence = Path(os.environ["VERIFY_EVIDENCE_DIR"]).resolve()
    run_id = uuid.uuid4().hex
    artifact = evidence / f"{feature}-{run_id}.json"
    marker = root / ".owned-run"
    owned = root / ".runs" / run_id
    owns_marker = owns_state = False
    record = {"feature": feature, "run_id": run_id, "started_at": now(),
              "observation": "failed", "commands": [], "fixture_only": True}
    try:
        evidence.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents evidence replacement even if IDs collide.
        with artifact.open("x") as handle:
            json.dump(record, handle)
    except OSError as error:
        print(f"error: cannot retain evidence; choose a writable destination: {error}", file=sys.stderr)
        return 1
    try:
        doctor = subprocess.run(
            [sys.executable, str(root / "doctor.py")], cwd=root,
            text=True, capture_output=True, timeout=15,
        )
        record["doctor"] = {"exit": doctor.returncode, "stdout": doctor.stdout, "stderr": doctor.stderr}
        if doctor.returncode:
            raise RuntimeError("Doctor did not establish readiness; follow its correction")
        observed = json.loads(doctor.stdout)
        record.update({"instance": observed["observed"]["instance"],
                       "revision": observed["observed"]["revision"],
                       "cli_sha256": observed["cli_sha256"]})
        target = json.loads((root / "target.json").read_text())
        with marker.open("x") as handle:
            owns_marker = True
            handle.write(run_id)
        owned.mkdir(parents=True)
        owns_state = True
        state = owned / "notes.json"

        def invoke(*args):
            command = [sys.executable, target["cli"], "--state",
                       str(state.relative_to(root)), *args]
            result = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=10)
            record["commands"].append({"command": ["python3", *command[1:]],
                                      "exit": result.returncode, "stdout": result.stdout,
                                      "stderr": result.stderr})
            return result.returncode, json.loads(result.stdout) if result.stdout else {}

        def expect(args, code, output):
            actual = invoke(*args)
            if actual != (code, output):
                raise RuntimeError(f"application behavior mismatch for {args!r}: expected {(code, output)!r}, observed {actual!r}")
            return actual[1]

        expect(("list",), 0, {"notes": []})
        expect(("create", "fixture note"), 0, {"created": "fixture note"})
        created = expect(("list",), 0, {"notes": ["fixture note"]})
        if feature == "create-note":
            record["effect"] = created
        elif feature == "list-notes":
            expect(("create", "second note"), 0, {"created": "second note"})
            record["effect"] = expect(("list",), 0, {"notes": ["fixture note", "second note"]})
        else:
            rejected = expect(("create", ""), 1, {"error": "note must not be empty"})
            record["effect"] = {"rejection": rejected,
                                "remaining": expect(("list",), 0, {"notes": ["fixture note"]})}
        record["observation"] = "passed"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        record["error"] = str(error)
    finally:
        try:
            if owns_state:
                shutil.rmtree(owned)
            if owns_marker:
                marker.unlink()
            record["owned_state_removed"] = owns_state and not owned.exists()
        except OSError as error:
            record["error"] = f"owned cleanup failed; inspect before continuation: {error}"
            record["observation"] = "failed"
        if "error" in record:
            record["observation"] = "failed"
        record["finished_at"] = now()
    try:
        artifact.write_text(json.dumps(record, indent=2) + "\n")
        if record["observation"] == "passed" and not report_only:
            entry = root / "features" / f"{feature}.md"
            locator = os.path.relpath(artifact, entry.parent)
            updated, count = re.subn(
                r"^\*\*Last verification:\*\*.*$",
                lambda _: f"**Last verification:** revision={record['revision']}; instance={record['instance']}; "
                f"run={run_id}; command=drive.py {feature}; observation=passed; evidence=[run artifact]({locator}).",
                entry.read_text(), flags=re.MULTILINE,
            )
            if count != 1:
                raise ValueError("restore exactly one Last verification field in the feature entry")
            entry.write_text(updated)
    except (OSError, ValueError) as error:
        record.update({"observation": "failed", "error": f"evidence/map update failed: {error}"})
        try:
            artifact.write_text(json.dumps(record, indent=2) + "\n")
        except OSError:
            pass
    print(json.dumps({"observation": record["observation"], "artifact": str(artifact),
                      "run_id": run_id, "error": record.get("error")}))
    return 0 if record["observation"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

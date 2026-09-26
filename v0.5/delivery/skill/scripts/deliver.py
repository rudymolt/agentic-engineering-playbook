#!/usr/bin/env python3
"""Installed entrypoint for digest-owned V0.5 process-attested delivery."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.dont_write_bytecode = True
SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "runtime"))

from delivery_pilot.workflow import main as workflow_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(workflow_main(sys.argv[1:]))

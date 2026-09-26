#!/usr/bin/env python3
"""Run checker-side Python with bytecode writes disabled."""

from __future__ import annotations

import os
import sys


if __name__ == "__main__":
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ["AI_PLAYBOOK_CHECKER_PYTHON_WRAPPER"] = "1"
    os.execve(sys.executable, [sys.executable, "-B", *sys.argv[1:]], os.environ)

"""Offline synthetic-only TDD verification with explicit negative control."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(target: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SYNTHETIC_TDD_TARGET"] = target
    return subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "agent_tdd/tests", "-v"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=90,
    )


def main() -> int:
    red = run("unsafe_baseline")
    negative = re.search(r"FAILED \(failures=(\d+)\)", red.stderr)
    if red.returncode == 0 or negative is None or int(negative.group(1)) < 1:
        print("TDD_NEGATIVE_CONTROL=FAIL")
        print(red.stderr[-2500:])
        return 1
    print(f"TDD_NEGATIVE_CONTROL=PASS expected_failures={negative.group(1)}")

    green = run("plan_guard")
    if green.returncode != 0 or "OK" not in green.stderr:
        print("TDD_GREEN=FAIL")
        print(green.stderr[-4000:])
        return 1
    matched = re.search(r"Ran (\d+) tests?", green.stderr)
    print(f"TDD_GREEN=PASS tests={matched.group(1) if matched else 'unknown'}")
    print("DATA_CLASS=PUBLIC_SYNTHETIC")
    print("LIVE_AGENT_EXECUTION=NO")
    print("PRODUCTION_ACCESS=NO")
    return 0


if __name__ == "__main__":
    sys.exit(main())

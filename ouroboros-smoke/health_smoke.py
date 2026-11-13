#!/usr/bin/env python3
"""Public-only bounded local Ouroboros HTTP smoke; no model calls or secrets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = 8765
VERSION = "7.10.0"
LIMIT_SECONDS = 90
MAX_BYTES = 16_384


def observe() -> dict | None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/health",
        headers={"Accept": "application/json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=2.0) as resp:
            if resp.status != 200:
                return None
            raw = resp.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise RuntimeError("health response oversized")
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise RuntimeError("invalid response shape")
        boot = doc.get("boot")
        if doc.get("status") != "ok" or doc.get("runtime_version") != VERSION:
            raise RuntimeError("wrong runtime version or non-ok status")
        if not isinstance(boot, dict) or boot.get("phase") not in {"starting", "serving", "ready"}:
            raise RuntimeError("no acceptable boot phase")
        return {
            "version": VERSION,
            "boot_phase": boot["phase"],
            "dialogue_ready": boot.get("dialogue_ready") is True,
            "tasks_ready": boot.get("tasks_ready") is True,
            "result": "HTTP_LIVENESS_CONFIRMED_ONLY",
            "note": "No model, task, memory or restart qualification performed",
        }
    except (OSError, urllib.error.URLError):
        return None


def main() -> int:
    if os.geteuid() == 0:
        print("SMOKE=REFUSED_ROOT")
        return 2
    root = Path(os.environ["OUROBOROS_PUBLIC_SOURCE"])
    venv_python = root / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        print("SMOKE=MISSING_INSTALLED_VENV")
        return 2
    cmd = [str(venv_python), "-m", "ouroboros.cli", "server", "--host",
           "127.0.0.1", "--port", str(PORT)]
    env = os.environ.copy()
    env.update({
        "OUROBOROS_DATA_DIR": str(Path(os.environ["RUNNER_TEMP"]) / "ouroboros-data"),
        "OUROBOROS_SERVER_HOST": "127.0.0.1",
        "OUROBOROS_SERVER_PORT": str(PORT),
        "OUROBOROS_LAUNCH_INTENT": "automatic",
        "OUROBOROS_NETWORK_PASSWORD": "isolated-loopback-smoke-not-remote",
        "HOME": str(Path(os.environ["RUNNER_TEMP"]) / "ouroboros-home"),
        "XDG_CONFIG_HOME": str(Path(os.environ["RUNNER_TEMP"]) / "ouroboros-config"),
    })
    for name in ("OUROBOROS_DATA_DIR", "HOME", "XDG_CONFIG_HOME"):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    log_path = Path(os.environ["RUNNER_TEMP"]) / "ouroboros-smoke.log"
    observed = None
    ready = False
    last_report = None
    started = time.monotonic()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while time.monotonic() - started < LIMIT_SECONDS:
                if proc.poll() is not None:
                    print(f"SMOKE=EARLY_EXIT,code={proc.returncode}")
                    break
                try:
                    observed = observe()
                    if observed is not None:
                        if observed != last_report:
                            print("SMOKE="+json.dumps(observed, sort_keys=True), flush=True)
                            last_report = observed
                        if (observed["boot_phase"] == "ready" and observed["tasks_ready"]
                                and observed["dialogue_ready"]):
                            ready = True
                            break
                except (ValueError, RuntimeError) as exc:
                    print(f"SMOKE=INVALID_HEALTH,{type(exc).__name__}")
                    break
                time.sleep(3)
        finally:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=5)
    if observed is None:
        print("SMOKE=NOT_CONFIRMED")
        # No full log dump: transient logs may contain implementation details.
        return 2
    if not ready:
        print("SMOKE=HTTP_ALIVE_BUT_NOT_FULLY_READY")
        return 2
    print("SMOKE=PASS_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import urllib.request

WITR_VERSION = "v0.3.3"
WITR_RELEASE_COMMIT = "86831e80c59c54e19c74cdbd126ed7ff6bcad756"
WITR_LINUX_AMD64_SHA256 = "08fc46e3f80a374476f71d0d6e6579477cd98c6df5cc59d98224adf948f5ebf5"
WITR_LINUX_AMD64_URL = (
    "https://github.com/pranshuparmar/witr/releases/download/"
    f"{WITR_VERSION}/witr-linux-amd64"
)
SYNTHETIC_MARKER = "public_dummy_marker_witr_w1_7d4d3c"
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_TREE_KEYS = {"Ancestry", "Children", "PID", "Command"}


def download_exact_binary(destination: Path) -> None:
    request = urllib.request.Request(
        WITR_LINUX_AMD64_URL,
        headers={"User-Agent": "panam-ci-lab-public-witr-w1"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise AssertionError("download exceeded public W1 byte limit")

    digest = hashlib.sha256(payload).hexdigest()
    if digest != WITR_LINUX_AMD64_SHA256:
        raise AssertionError(
            f"witr digest mismatch: expected {WITR_LINUX_AMD64_SHA256}, got {digest}"
        )

    destination.write_bytes(payload)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR)


def collect_dict_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(collect_dict_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(collect_dict_keys(child))
    return keys


def collect_pids(value: object) -> set[int]:
    pids: set[int] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "PID" and isinstance(child, int):
                pids.add(child)
            else:
                pids.update(collect_pids(child))
    elif isinstance(value, list):
        for child in value:
            pids.update(collect_pids(child))
    return pids


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="witr-w1-public-") as td:
        binary = Path(td) / "witr"
        download_exact_binary(binary)

        version = subprocess.run(
            [str(binary), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if version.returncode != 0:
            raise AssertionError("pinned witr binary did not return a version cleanly")
        if "0.3.3" not in (version.stdout + version.stderr):
            raise AssertionError("pinned binary version output did not contain 0.3.3")

        child_env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "WITR_W1_SYNTHETIC_MARKER": SYNTHETIC_MARKER,
        }
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            result = subprocess.run(
                [str(binary), "--pid", str(child.pid), "--tree", "--json"],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C.UTF-8",
                    "LC_ALL": "C.UTF-8",
                },
            )

            # witr documents 0 as clean and 1 as a warning-bearing successful lookup.
            if result.returncode not in {0, 1}:
                raise AssertionError(
                    f"tree lookup failed closed with exit code {result.returncode}"
                )

            combined = result.stdout + result.stderr
            if SYNTHETIC_MARKER in combined:
                raise AssertionError("reduced tree output leaked the synthetic environment marker")

            payload = json.loads(result.stdout)
            observed_keys = collect_dict_keys(payload)
            unexpected = sorted(observed_keys - ALLOWED_TREE_KEYS)
            if unexpected:
                raise AssertionError(f"unexpected tree JSON keys: {unexpected}")

            if child.pid not in collect_pids(payload):
                raise AssertionError("tree JSON did not contain the synthetic target PID")

            forbidden_names = {
                "Env",
                "Cmdline",
                "WorkingDir",
                "GitRepo",
                "GitBranch",
                "Sockets",
                "FileDescs",
                "Capabilities",
            }
            leaked_names = sorted(observed_keys & forbidden_names)
            if leaked_names:
                raise AssertionError(f"privacy-sensitive fields appeared: {leaked_names}")
        finally:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)

    print("WITR_W1_PUBLIC_SYNTHETIC=PASS")
    print(f"WITR_VERSION={WITR_VERSION}")
    print(f"WITR_RELEASE_COMMIT={WITR_RELEASE_COMMIT}")
    print(f"WITR_BINARY_SHA256={WITR_LINUX_AMD64_SHA256}")
    print("OUTPUT_CONTRACT=tree-json-allowlist-only")


if __name__ == "__main__":
    main()

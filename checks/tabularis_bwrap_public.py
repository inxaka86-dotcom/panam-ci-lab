#!/usr/bin/env python3
"""Public-only Tabularis MCP Linux Bubblewrap isolation proof.

This probe fails closed if unprivileged namespaces are unavailable; it never
falls back to host execution, sudo, or a more permissive sandbox.
Only a single public test program, the native binary, /usr libraries and an
empty work directory are mounted. No PANAM data, credentials or servers.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SMOKE = HERE / "tabularis_mcp_public_smoke.py"


def base_args(work: Path, *, binary: Path | None = None) -> list[str]:
    command = [
        "bwrap", "--unshare-all", "--unshare-net",
        "--die-with-parent", "--new-session",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--dir", "/etc",
        "--dir", "/run",
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--dir", "/app",
        "--dir", "/work",
        "--bind", str(work), "/work",
        "--ro-bind", str(Path(__file__).resolve()), "/app/probe.py",
        "--ro-bind", str(SMOKE), "/app/acceptance.py",
        "--chdir", "/work",
        "--clearenv", "--setenv", "HOME", "/work",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "TMPDIR", "/tmp",
        "--setenv", "RUST_LOG", "off",
    ]
    if binary is not None:
        command += ["--ro-bind", str(binary.resolve()), "/app/tabularis"]
    return command + ["--"]


def child_probe(port: int, hidden_path: Path) -> dict:
    # The listening TCP socket exists on the runner's host loopback.
    # An unshared network namespace MUST NOT reach the socket.
    network_reached = False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            network_reached = True
    except OSError:
        pass
    canary_visible = hidden_path.exists()
    home_visible = Path("/home/runner").exists()
    wrote_inside = False
    try:
        inside = Path("/work/public-sandbox-written.txt")
        inside.write_text("FAKE_SANDBOX_OK", encoding="utf-8")
        wrote_inside = inside.read_text(encoding="utf-8") == "FAKE_SANDBOX_OK"
    except OSError:
        pass
    checks = {
        "network_namespace_excludes_host_listener": not network_reached,
        "synthetic_host_file_hidden": not canary_visible,
        "runner_home_hidden": not home_visible,
        "sandbox_workdir_writable": wrote_inside,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "production_permission": "NONE"}


def execute(args: list[str], timeout: int) -> dict:
    if os.geteuid() == 0:
        return {"status": "BLOCKED", "reason": "root caller forbidden"}
    if not shutil.which("bwrap"):
        return {"status": "BLOCKED", "reason": "bubblewrap unavailable"}
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "BLOCKED", "reason": "bounded sandbox execution timeout"}
    # If the child executed, retain only its explicit structured canary flags.
    # Never print raw stdout/stderr or runner paths.
    try:
        data = json.loads(p.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict) and data.get("status") in ("PASS", "FAIL"):
        if p.returncode != 0 and data.get("status") == "PASS":
            return {"status": "BLOCKED", "reason": "inconsistent exit code"}
        return data
    if p.returncode != 0:
        err = p.stderr.lower()
        category = (
            "USER_NAMESPACE_PERMISSION" if (
                "operation not permitted" in err
                or "permission denied" in err
                or "user namespace" in err
            ) else
            "MOUNT_OR_FILESYSTEM_SETUP" if (
                "mount" in err or "file exists" in err
                or "no such file or directory" in err
            ) else
            "UNCLASSIFIED_SANDBOX_ERROR"
        )
        return {"status": "BLOCKED", "reason": category,
                "exit_code": p.returncode}
    return {"status": "BLOCKED", "reason": "no valid structured child result"}


def preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix="public-sandbox-test-") as tmp:
        root = Path(tmp)
        hidden = root / "host-secret-synthetic.txt"
        hidden.write_text("FICTIONAL_HIDDEN_HOST_CANARY", encoding="utf-8")
        work = root / "sandbox-work"
        work.mkdir()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            server.listen(3)
            port = server.getsockname()[1]
            # Host-positive-control: the same listener is reachable here.
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass
            cmd = base_args(work) + [
                "/usr/bin/python3", "/app/probe.py", "--child-probe",
                "--port", str(port), "--hidden-path", str(hidden)
            ]
            outcome = execute(cmd, timeout=20)
            outcome["host_positive_control"] = True
            return outcome


def native(binary: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="public-sandbox-native-") as tmp:
        work = Path(tmp) / "work"
        work.mkdir()
        cmd = base_args(work, binary=binary) + [
            "/usr/bin/python3", "/app/acceptance.py",
            "--binary", "/app/tabularis", "--timeout", "40",
        ]
        result = execute(cmd, timeout=65)
        return {
            "status": "PASS" if (result.get("status") == "PASS"
                                and result.get("production_permission") == "NONE"
                                and result.get("functional_pass")
                                and result.get("privacy_pass")) else "FAIL",
            "native_synthetic_status": result.get("status"),
            "native_functional_pass": result.get("functional_pass", False),
            "native_stderr_privacy_pass": result.get("privacy_pass", False),
            "runner_bubblewrap_exit": result.get("exit_code", 0),
            "production_permission": "NONE",
        }


class SelfTest(unittest.TestCase):
    def test_denies_network_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = base_args(Path(tmp))
            self.assertIn("--unshare-net", cmd)
            self.assertIn("--tmpfs", cmd)
            self.assertNotIn("--bind", cmd[:cmd.index("--ro-bind")])
            self.assertNotIn("sudo", cmd)
            self.assertIn("--clearenv", cmd)

    def test_ro_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd = base_args(Path(tmp), binary=Path("/usr/bin/python3"))
            idx = cmd.index("/app/tabularis")
            self.assertEqual(cmd[idx - 2], "--ro-bind")

    def test_bounded_host_canary(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = child_probe(65530, Path(tmp) / "absent")
            self.assertTrue(result["checks"]["synthetic_host_file_hidden"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--child-probe", action="store_true")
    parser.add_argument("--port", type=int)
    parser.add_argument("--hidden-path", type=Path)
    args = parser.parse_args()
    if args.selftest:
        tests = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest))
        return 0 if tests.wasSuccessful() else 1
    if args.child_probe:
        if args.port is None or args.hidden_path is None:
            parser.error("--child-probe requires --port and --hidden-path")
        data = child_probe(args.port, args.hidden_path)
    elif args.preflight:
        data = preflight()
    elif args.binary:
        data = native(args.binary)
    else:
        parser.error("--preflight, --binary or --selftest required")
    print(json.dumps(data, sort_keys=True))
    return 0 if data["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

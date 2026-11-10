#!/usr/bin/env python3
"""Public synthetic-only Tabularis Docker isolation acceptance.

A privileged Docker daemon may assemble the sandbox, but actual MCP always
runs as UID/GID 65532:65532 with no network, capabilities, host home, or
writable image root. Uses no PANAM source, data, or credentials.
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

IMAGE = "panam-public-tabularis-sandbox:v1"
HERE = Path(__file__).resolve()
SMOKE = HERE.with_name("tabularis_mcp_public_smoke.py")


def docker(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker"] + args, capture_output=True,
                          text=True, check=False, timeout=timeout)


def secure_options() -> list[str]:
    return [
        "--network", "none", "--ipc", "none",
        "--read-only", "--user", "65532:65532",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=64m",
        "--tmpfs", "/work:rw,nosuid,nodev,mode=1777,size=16m",
        "--env", "HOME=/work", "--env", "TMPDIR=/tmp",
        "--env", "RUST_LOG=off", "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--mount", "type=bind,source=" + str(HERE) + ",target=/app/probe.py,readonly",
        "--mount", "type=bind,source=" + str(SMOKE) + ",target=/app/smoke.py,readonly",
    ]


def inspect_flags(obj: dict, binary: bool) -> dict:
    host = obj.get("HostConfig", {})
    cfg = obj.get("Config", {})
    mounts = obj.get("Mounts", [])
    expected = {"/app/probe.py", "/app/smoke.py"}
    if binary:
        expected.add("/app/tabularis")
    current = {m.get("Destination") for m in mounts if m.get("Type") == "bind"}
    flags = {
        "network_none": host.get("NetworkMode") == "none",
        "ipc_none": host.get("IpcMode") == "none",
        "read_only_root": host.get("ReadonlyRootfs") is True,
        "nonroot_uid_gid": cfg.get("User") == "65532:65532",
        "all_capabilities_dropped": "ALL" in [
            x.upper() for x in host.get("CapDrop", [])],
        "no_new_privileges": any(
            "no-new-privileges" in x for x in host.get("SecurityOpt", [])),
        "pid_limit": host.get("PidsLimit") == 64,
        "memory_limit": host.get("Memory") == 536870912,
        "cpu_limit": host.get("NanoCpus") == 1000000000,
        "private_tmpfs": all(
            x in host.get("Tmpfs", {}) for x in ("/tmp", "/work")),
        "only_expected_bind_mounts": current == expected and all(
            m.get("RW") is False for m in mounts if m.get("Type") == "bind"),
    }
    return flags


def create_and_run(test_args: list[str], *, binary: Path | None = None) -> dict:
    if not shutil.which("docker"):
        return {"status": "BLOCKED", "reason": "docker unavailable"}
    opts = secure_options()
    if binary is not None:
        opts += ["--mount", "type=bind,source=" + str(binary.resolve()) +
                 ",target=/app/tabularis,readonly"]
    # Never run privileged, host networking, mounted /var/run/docker.sock or sudo.
    cmd = ["create"] + opts + [
        "--entrypoint", "/usr/bin/python3", IMAGE] + test_args
    try:
        created = docker(cmd, 40)
        if created.returncode != 0:
            return {"status": "BLOCKED", "reason": "docker create failed"}
        ident = created.stdout.strip()
        try:
            inspected = docker(["inspect", ident], 15)
            if inspected.returncode != 0:
                return {"status": "BLOCKED", "reason": "docker inspect failed"}
            obj = json.loads(inspected.stdout)[0]
            flags = inspect_flags(obj, binary is not None)
            if not all(flags.values()):
                return {"status": "FAIL", "reason": "runtime isolation config mismatch",
                        "isolation_checks": flags}
            started = docker(["start", ident], 15)
            if started.returncode != 0:
                return {"status": "BLOCKED", "reason": "docker start failed"}
            ended = docker(["wait", ident], 75)
            if ended.returncode != 0:
                return {"status": "BLOCKED", "reason": "docker wait failed"}
            exited = int(ended.stdout.strip())
            logs = docker(["logs", ident], 15)
            if logs.returncode != 0:
                return {"status": "BLOCKED", "reason": "docker logs unavailable"}
            try:
                result = json.loads(logs.stdout.strip().splitlines()[-1])
            except (IndexError, ValueError):
                return {"status": "BLOCKED", "reason": "no structured child result"}
            if result.get("status") == "PASS" and exited == 0:
                result["isolation_checks"] = flags
                return result
            return {"status": "FAIL", "reason": "child test rejected",
                    "child_status": result.get("status"),
                    "isolation_checks": flags}
        finally:
            docker(["rm", "-f", ident], 15)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        return {"status": "BLOCKED", "reason": type(error).__name__}


def child_check(port: int, outside: Path) -> dict:
    host_network_reached = False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            host_network_reached = True
    except OSError:
        pass
    wrote_workdir = False
    try:
        dest = Path("/work/inside_canary.txt")
        dest.write_text("SYNTHETIC_CONTAINER_OK", encoding="utf-8")
        wrote_workdir = dest.read_text(encoding="utf-8") == "SYNTHETIC_CONTAINER_OK"
    except OSError:
        pass
    effective_caps = None
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("CapEff:"):
            effective_caps = int(line.partition(":")[2].strip(), 16)
            break
    fs_read_only = bool(os.statvfs("/").f_flag & os.ST_RDONLY)
    flags = {
        "cannot_reach_host_test_listener": not host_network_reached,
        "outside_host_canary_hidden": not outside.exists(),
        "host_home_hidden": not Path("/home/runner").exists(),
        "inside_uid_unprivileged": os.geteuid() == 65532,
        "effective_caps_empty": effective_caps == 0,
        "root_mount_readonly": fs_read_only,
        "private_workdir_usable": wrote_workdir,
    }
    return {"status": "PASS" if all(flags.values()) else "FAIL",
            "checks": flags, "production_permission": "NONE"}


def preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix="public-docker-boundary-") as td:
        outside = Path(td) / "host_synthetic_canary.txt"
        outside.write_text("PUBLIC_SYNTHETIC_OUTSIDE_CANARY", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as host:
            host.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            host.bind(("127.0.0.1", 0))
            host.listen(2)
            port = host.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass
            result = create_and_run([
                "/app/probe.py", "--child-check", "--port", str(port),
                "--outside", str(outside),
            ])
            result["host_socket_positive_control"] = True
            return result


def native(binary: Path) -> dict:
    result = create_and_run([
        "/app/smoke.py", "--binary", "/app/tabularis", "--timeout", "40",
    ], binary=binary)
    checks = result.get("isolation_checks", {})
    return {
        "status": "PASS" if (
            result.get("status") == "PASS" and
            result.get("functional_pass") and
            result.get("privacy_pass") and
            result.get("production_permission") == "NONE" and
            all(checks.values())
        ) else "FAIL",
        "synthetic_mcp_functional": result.get("functional_pass", False),
        "stderr_canaries_clear": result.get("privacy_pass", False),
        "isolation_checks": checks,
        "production_permission": "NONE",
    }


class SelfTest(unittest.TestCase):
    def test_hardened_flags(self):
        options = secure_options()
        self.assertIn("none", options)
        self.assertIn("--cap-drop", options)
        self.assertIn("--read-only", options)
        self.assertIn("65532:65532", options)
        self.assertNotIn("--privileged", options)
        self.assertNotIn("host", options)

    def test_fail_closed_inspect(self):
        self.assertFalse(all(inspect_flags({}, False).values()))

    def test_expected_mounts(self):
        base = {
            "HostConfig": {"NetworkMode": "none", "IpcMode": "none",
                "ReadonlyRootfs": True, "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges:true"],
                "PidsLimit": 64, "Memory": 536870912,
                "NanoCpus": 1000000000,
                "Tmpfs": {"/tmp": "rw", "/work": "rw"}},
            "Config": {"User": "65532:65532"},
            "Mounts": [{"Type": "bind", "Destination": p, "RW": False}
                       for p in ("/app/probe.py", "/app/smoke.py")],
        }
        self.assertTrue(all(inspect_flags(base, False).values()))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--binary", type=Path)
    p.add_argument("--child-check", action="store_true")
    p.add_argument("--port", type=int)
    p.add_argument("--outside", type=Path)
    args = p.parse_args()
    if args.selftest:
        test = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest))
        return 0 if test.wasSuccessful() else 1
    if args.child_check:
        if args.port is None or args.outside is None:
            p.error("--child-check requires --port/--outside")
        result = child_check(args.port, args.outside)
    elif args.preflight:
        result = preflight()
    elif args.binary:
        result = native(args.binary)
    else:
        p.error("--preflight, --binary or --selftest required")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

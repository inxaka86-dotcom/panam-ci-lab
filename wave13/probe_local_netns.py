#!/usr/bin/env python3
"""No-model Linux network-namespace capability probe, not an agent executor.

Only a fixed local Python child runs using unshare --user --map-root-user --net.
It attempts TCP to a temporary LOOPBACK-ONLY parent listener, NEVER internet.
No API key, AI provider, Codex process, private/production material or spend.
A local CI result is not proof on the actual executor host, and gives no authority.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import re
import socket
import subprocess
import tempfile

SCHEMA = "panam.leanrea.loopback-netns-child.v1"
NET_NS = re.compile(r"^net:\[[0-9]+\]$")
USER_NS = re.compile(r"^user:\[[0-9]+\]$")
CHILD = r'''
import json, os, socket, sys
try:
    port = int(sys.argv[1])
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    connected = s.connect_ex(("127.0.0.1", port)) == 0
    s.close()
    payload = {
        "schema": "panam.leanrea.loopback-netns-child.v1",
        "net_ns": os.readlink("/proc/self/ns/net"),
        "user_ns": os.readlink("/proc/self/ns/user"),
        "interfaces": sorted(os.listdir("/sys/class/net")),
        "loopback_reachable": connected,
        "child_uid": os.getuid(),
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
except Exception:
    sys.exit(19)
'''


def report(status: str, proof: bool = False) -> dict:
    return {
        "schema": "panam.leanrea.local-netns-capability.v1",
        "status": status,
        "local_ephemeral_netns_observed": proof,
        "actual_target_host_isolation_proven": False,
        "filesystem_isolation_proven": False,
        "worker_isolation_proven": False,
        "external_internet_egress_probed": False,
        "model_request_executed": False,
        "provider_credentials_accessed": False,
        "production_changed": False,
        "agent_execution_allowed": False,
        "real_usd_hard_cap_enforced": False,
    }


def classify(parent_net: str, parent_user: str, code: int, output: str) -> dict:
    """Strict parser: never promote failed, partial or untrusted child output."""
    if type(code) is not int or code != 0:
        return report("BLOCKED_UNSHARE_UNAVAILABLE")
    if not isinstance(output, str) or len(output) > 512:
        return report("BLOCKED_UNTRUSTED_CHILD_OUTPUT")
    try:
        result = json.loads(output)
    except (ValueError, TypeError):
        return report("BLOCKED_UNTRUSTED_CHILD_OUTPUT")
    keys = {"schema", "net_ns", "user_ns", "interfaces",
            "loopback_reachable", "child_uid"}
    if not isinstance(result, dict) or set(result) != keys:
        return report("BLOCKED_UNTRUSTED_CHILD_OUTPUT")
    if result["schema"] != SCHEMA:
        return report("BLOCKED_UNTRUSTED_CHILD_OUTPUT")
    if (not isinstance(parent_net, str) or not NET_NS.fullmatch(parent_net)
            or not isinstance(parent_user, str) or not USER_NS.fullmatch(parent_user)
            or not isinstance(result["net_ns"], str)
            or not NET_NS.fullmatch(result["net_ns"])
            or not isinstance(result["user_ns"], str)
            or not USER_NS.fullmatch(result["user_ns"])
            or type(result["child_uid"]) is not int):
        return report("BLOCKED_UNTRUSTED_CHILD_OUTPUT")
    if (parent_net == result["net_ns"] or parent_user == result["user_ns"]):
        return report("BLOCKED_NAMESPACE_NOT_SEPARATE")
    # UID 0 is an isolated child user-namespace mapping, NOT host root.
    if (result["child_uid"] != 0 or result["interfaces"] != ["lo"]
            or type(result["loopback_reachable"]) is not bool):
        return report("BLOCKED_UNSAFE_NETWORK_OBSERVATION")
    if result["loopback_reachable"]:
        return report("BLOCKED_PARENT_LOOPBACK_REACHABLE")
    return report("PASS_LOCAL_EPHEMERAL_NETNS_ONLY", proof=True)


def probe() -> dict:
    if platform.system() != "Linux":
        return report("BLOCKED_NON_LINUX")
    if os.geteuid() == 0:
        return report("BLOCKED_HOST_ROOT_NOT_ALLOWED")
    if not (Path("/usr/bin/unshare").is_file()
            and Path("/usr/bin/python3").is_file()):
        return report("BLOCKED_REQUIRED_TOOLS_MISSING")
    try:
        parent_net = os.readlink("/proc/self/ns/net")
        parent_user = os.readlink("/proc/self/ns/user")
        if not (NET_NS.fullmatch(parent_net) and USER_NS.fullmatch(parent_user)):
            return report("BLOCKED_PARENT_NAMESPACE_UNAVAILABLE")
        with tempfile.TemporaryDirectory(prefix="leanrea-netns-") as tmp:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                port = listener.getsockname()[1]
                argv = [
                    "/usr/bin/unshare", "--user", "--map-root-user", "--net",
                    "--", "/usr/bin/python3", "-I", "-c", CHILD, str(port),
                ]
                cp = subprocess.run(
                    argv, cwd=tmp, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, timeout=8, check=False,
                    close_fds=True, start_new_session=True,
                    env={
                        "PATH": "/usr/bin:/bin", "HOME": tmp,
                        "PYTHONNOUSERSITE": "1",
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                )
                return classify(parent_net, parent_user, cp.returncode,
                                cp.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return report("BLOCKED_PROBE_UNAVAILABLE")


def main() -> None:
    result = probe()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    print("PANAM_LEANREA_LOCAL_NETNS=" + result["status"])
    print("PANAM_LEANREA_REAL_AGENT_EXECUTION=DENIED")


if __name__ == "__main__":
    main()

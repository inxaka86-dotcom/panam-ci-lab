#!/usr/bin/env python3
"""Public-only Tabularis MCP isolated internal PostgreSQL Docker network test.

Docker daemon is a test-host trusted component. The MCP process itself is
nonroot, restricted, and sees only an ephemeral synthetic PostgreSQL container.
No external provider, PANAM account, data or production network is accessed.
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
import time
import uuid

def base_secure_options() -> list[str]:
    # Standalone so the exact public probe can run inside a minimal container
    # without importing any code from the host repository.
    return [
        "--network", "none", "--ipc", "none",
        "--read-only", "--user", "65532:65532",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "64", "--memory", "512m", "--cpus", "1",
        "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=64m",
        "--tmpfs", "/work:rw,nosuid,nodev,mode=1777,size=16m",
        "--env", "HOME=/work", "--env", "TMPDIR=/tmp",
        "--env", "RUST_LOG=off", "--env", "PYTHONDONTWRITEBYTECODE=1",
    ]

SOURCE = Path(__file__).resolve()
DB = "public_mcp_test"
READER = "public_mcp_reader"
WRITER = "public_mcp_writer"
MARKER = "FICTIONAL_INTERNAL_PG_ITEM_A011"
PRIVATE = "FICTIONAL_PRIVATE_INTERNAL_DENIED_P093"
ADMIN_PASS = "synthetic-admin-public-only"
READER_PASS = "synthetic-reader-public-only"
WRITER_PASS = "synthetic-writer-public-only"
READ_ID = "synthetic-private-network-reader"
WRITE_ID = "synthetic-private-network-writer"

SCHEMA_SQL = f"""
REVOKE ALL ON DATABASE {DB} FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE ROLE {READER} LOGIN PASSWORD '{READER_PASS}';
CREATE ROLE {WRITER} LOGIN PASSWORD '{WRITER_PASS}';
GRANT CONNECT ON DATABASE {DB} TO {READER}, {WRITER};
GRANT USAGE ON SCHEMA public TO {READER}, {WRITER};
CREATE TABLE public.public_items(id text PRIMARY KEY,title text NOT NULL,amount integer NOT NULL);
INSERT INTO public.public_items VALUES ('p1','{MARKER}',17);
CREATE TABLE public.private_items(secret_marker text NOT NULL);
INSERT INTO public.private_items VALUES ('{PRIVATE}');
CREATE SEQUENCE public.public_counter START WITH 42;
GRANT SELECT ON public.public_items TO {READER};
GRANT SELECT, INSERT, UPDATE, DELETE ON public.public_items TO {WRITER};
GRANT ALL PRIVILEGES ON SEQUENCE public.public_counter TO {WRITER};
GRANT CREATE ON SCHEMA public TO {WRITER};
"""


def docker(args: list[str], timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker"] + args, capture_output=True,
                          text=True, check=False, timeout=timeout)


def must(args: list[str], timeout: int = 25) -> str:
    result = docker(args, timeout)
    if result.returncode != 0:
        raise RuntimeError("Synthetic Docker administration operation failed")
    return result.stdout.strip()


def sql_admin(pg: str, sql: str) -> str:
    return must(["exec", "-e", "PGPASSWORD=" + ADMIN_PASS,
                 pg, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-At",
                 "-U", "postgres", "-d", DB, "-c", sql], 15)


def state(pg: str) -> dict:
    return {
        "row": sql_admin(pg, "SELECT title || ':' || amount FROM public.public_items"),
        "seq": sql_admin(pg, "SELECT last_value FROM public.public_counter"),
        "private": sql_admin(pg, "SELECT secret_marker FROM public.private_items"),
        "new_table": sql_admin(pg, "SELECT count(*) FROM information_schema.tables "
                           "WHERE table_schema='public' AND table_name='created_by_mcp'"),
    }


def network_options(net: str, binary: Path | None) -> list[str]:
    opts = base_secure_options()
    idx = opts.index("--network")
    opts[idx + 1] = net
    # Remove prior SQLite-specific read-only source mounts, retaining its other gates.
    updated: list[str] = []
    pos = 0
    while pos < len(opts):
        if (opts[pos] == "--mount" and pos + 1 < len(opts)
            and "/app/" in opts[pos + 1]):
            pos += 2
            continue
        updated.append(opts[pos])
        pos += 1
    updated.extend([
        "--mount", "type=bind,source=" + str(SOURCE) +
                   ",target=/app/probe.py,readonly",
    ])
    if binary is not None:
        updated += ["--mount", "type=bind,source=" + str(binary.resolve()) +
                    ",target=/app/tabularis,readonly"]
    return updated


def runtime_checks(obj: dict, net: str, binary: bool) -> dict:
    host = obj.get("HostConfig", {})
    cfg = obj.get("Config", {})
    envnets = (obj.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
    mounts = obj.get("Mounts", [])
    expect = {"/app/probe.py"} | ({"/app/tabularis"} if binary else set())
    actual = {m.get("Destination") for m in mounts if m.get("Type") == "bind"}
    return {
        "only_internal_network_attached": host.get("NetworkMode") == net and set(envnets) == {net},
        "no_published_ports": not host.get("PortBindings"),
        "read_only_root": host.get("ReadonlyRootfs") is True,
        "nonroot_user": cfg.get("User") == "65532:65532",
        "capabilities_all_dropped": "ALL" in [str(x).upper() for x in host.get("CapDrop", [])],
        "no_new_privileges": any("no-new-privileges" in x for x in host.get("SecurityOpt", [])),
        "pid_cpu_memory_limits": (host.get("PidsLimit") == 64
                                 and host.get("Memory") == 536870912
                                 and host.get("NanoCpus") == 1000000000),
        "read_only_explicit_mounts_only": actual == expect and all(
            m.get("RW") is False for m in mounts if m.get("Type") == "bind"),
        "private_tmpfs": "/tmp" in host.get("Tmpfs", {}) and "/work" in host.get("Tmpfs", {}),
    }


def run_container(net: str, binary: Path | None, child: str) -> dict:
    options = network_options(net, binary)
    args = ["create"] + options + [
        "--entrypoint", "/usr/bin/python3",
        "panam-public-tabularis-sandbox:v1", "/app/probe.py", child,
    ]
    if child == "--child-native":
        args += ["--binary", "/app/tabularis"]
    created = must(args, 30)
    try:
        checked = json.loads(must(["inspect", created], 15))[0]
        guards = runtime_checks(checked, net, binary is not None)
        if not all(guards.values()):
            return {"status": "FAIL", "reason": "runtime configuration mismatch", "guards": guards}
        must(["start", created], 15)
        exit_code = int(must(["wait", created], 75))
        log = must(["logs", created], 15)
        try:
            result = json.loads(log.splitlines()[-1])
        except (ValueError, IndexError):
            return {"status": "BLOCKED", "reason": "missing structured child report"}
        if result.get("status") != "PASS" or exit_code != 0:
            return {"status": "FAIL", "reason": "child acceptance failed",
                    "guards": guards, "child": result.get("status")}
        return {"status": "PASS", "guards": guards, "child_checks": result.get("checks"),
                "synthetic_native": child == "--child-native",
                "production_permission": "NONE"}
    finally:
        docker(["rm", "-f", created], 15)


def setup(pg: str) -> None:
    for _ in range(40):
        status = docker(["exec", pg, "pg_isready", "-U", "postgres", "-d", DB], 8)
        if status.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Synthetic PostgreSQL service not ready")
    sql_admin(pg, SCHEMA_SQL)


def environment_test(binary: Path | None) -> dict:
    if not shutil.which("docker"):
        return {"status": "BLOCKED", "reason": "docker unavailable"}
    suffix = uuid.uuid4().hex[:9]
    net = "tabularis_public_internal_" + suffix
    pg = "tabularis_public_pg_" + suffix
    try:
        must(["network", "create", "--internal", "--driver", "bridge", net], 20)
        inspection = json.loads(must(["network", "inspect", net]))[0]
        if not (inspection.get("Internal") is True and inspection.get("Driver") == "bridge"):
            return {"status": "FAIL", "reason": "Docker network not internal"}
        must(["run", "-d", "--name", pg, "--network", net,
              "--network-alias", "pg",
              "-e", "POSTGRES_USER=postgres",
              "-e", "POSTGRES_DB=" + DB,
              "-e", "POSTGRES_PASSWORD=" + ADMIN_PASS,
              "postgres:16"], 55)
        setup(pg)
        before = state(pg)
        if before != {"row": MARKER + ":17", "seq": "42",
                      "private": PRIVATE, "new_table": "0"}:
            return {"status": "FAIL", "reason": "unexpected disposable fixture"}
        result = run_container(net, binary, "--child-native" if binary else "--child-connectivity")
        after = state(pg)
        result["pg_fixture_unchanged"] = before == after
        result["docker_network_internal"] = True
        if before != after:
            result["status"] = "FAIL"
        return result
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError):
        return {"status": "BLOCKED", "reason": "synthetic Docker network/DB setup failed"}
    finally:
        docker(["rm", "-f", pg], 15)
        docker(["network", "rm", net], 15)


def child_connectivity() -> dict:
    connected = False
    try:
        with socket.create_connection(("pg", 5432), timeout=3):
            connected = True
    except OSError:
        pass
    route = Path("/proc/net/route").read_text().splitlines()
    default_route = any(
        len(fields := line.split()) > 7 and fields[1] == "00000000"
        and fields[7] == "00000000" for line in route[1:]
    )
    checks = {
        "internal_postgres_reachable": connected,
        "no_default_ipv4_route": not default_route,
        "nonroot_process": os.geteuid() == 65532,
        "root_readonly": bool(os.statvfs("/").f_flag & os.ST_RDONLY),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL",
            "checks": checks, "production_permission": "NONE"}


def rpc(n: int, method: str, params: dict | None = None) -> dict:
    v = {"jsonrpc": "2.0", "id": n, "method": method}
    if params is not None:
        v["params"] = params
    return v


def call(n: int, conn: str, query: str) -> dict:
    return rpc(n, "tools/call", {"name": "run_query", "arguments": {
        "connection_id": conn, "query": query,
    }})


def native_requests() -> list[dict]:
    return [
        rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "public-pg-isolated-client", "version": "1"}}),
        rpc(2, "tools/list"),
        rpc(3, "tools/call", {"name": "list_connections", "arguments": {}}),
        rpc(4, "tools/call", {"name": "list_tables", "arguments": {"connection_id": READ_ID}}),
        rpc(5, "tools/call", {"name": "describe_table", "arguments": {
            "connection_id": READ_ID, "table_name": "public_items",
        }}),
        call(6, READ_ID, "SELECT title, amount FROM public.public_items"),
        call(7, WRITE_ID, "SELECT title, amount FROM public.public_items"),
        call(8, WRITE_ID, "INSERT INTO public.public_items VALUES ('x','BAD',1)"),
        call(9, WRITE_ID, "UPDATE public.public_items SET amount=0"),
        call(10, WRITE_ID, "DELETE FROM public.public_items"),
        call(11, WRITE_ID, "SELECT nextval('public.public_counter')"),
        call(12, READ_ID, "SELECT secret_marker FROM public.private_items"),
        call(13, WRITE_ID, "SELECT secret_marker FROM public.private_items"),
        call(14, WRITE_ID, "SELECT current_user"),
        call(15, WRITE_ID, "WITH c AS (SELECT amount FROM public.public_items) SELECT max(amount) FROM c"),
        call(16, "nonexistent", "SELECT 1"),
    ]


def native(binary: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="synthetic-internal-pg-mcp-") as td:
        root = Path(td)
        app = root / "config"
        app.mkdir(mode=0o700)
        config = {"mcpReadonlyDefault": True, "mcpReadonlyConnections": [],
                  "mcpApprovalMode": "off", "mcpOutputFormat": "json",
                  "aiAuditEnabled": False, "activeExternalDrivers": []}
        def conn(cid: str, username: str, password: str) -> dict:
            return {"id": cid, "name": cid, "params": {
                "driver": "postgres", "host": "pg", "port": 5432,
                "username": username, "password": password,
                "database": DB, "ssl_mode": "disable"}}
        connections = {"groups": [], "tags": [], "connections": [
            conn(READ_ID, READER, READER_PASS),
            conn(WRITE_ID, WRITER, WRITER_PASS),
        ]}
        for name, val in (("config.json", config), ("connections.json", connections)):
            dest = app / name
            dest.write_text(json.dumps(val), encoding="utf-8")
            dest.chmod(0o600)
        payload = "".join(json.dumps(x) + "\n" for x in native_requests())
        env = {"PATH": "/usr/bin:/bin", "HOME": str(root),
               "XDG_CONFIG_HOME": str(root / "xdg"),
               "TABULARIS_DATA_DIR": str(app), "RUST_LOG": "off"}
        run = subprocess.run(
            [str(binary), "--mcp"], input=payload, capture_output=True,
            text=True, cwd=root, env=env, timeout=45, check=False)
        raw = []
        for line in run.stdout.splitlines():
            try:
                raw.append(json.loads(line))
            except ValueError:
                pass
        answers = {x["id"]: x for x in raw if isinstance(x, dict)
                   and isinstance(x.get("id"), int)}
        def is_err(n: int) -> bool:
            item = answers.get(n, {})
            return bool(item.get("error")) or (
                isinstance(item.get("result"), dict) and
                item["result"].get("isError") is True)
        def value(n: int) -> str:
            return json.dumps(answers.get(n, {}).get("result"), ensure_ascii=False)
        flags = {
            "process_exit": run.returncode == 0,
            "sixteen_valid_jsonrpc": len(raw) == 16 and set(answers) == set(range(1, 17))
               and all(x.get("jsonrpc") == "2.0" for x in raw),
            "reader_select": not is_err(6) and MARKER in value(6),
            "writer_select": not is_err(7) and MARKER in value(7),
            "writes_denied_even_to_writer": all(is_err(n) for n in (8, 9, 10, 11)),
            "private_table_denied": is_err(12) and is_err(13)
                and PRIVATE not in run.stdout,
            "cte_read": not is_err(15) and "17" in value(15),
            "current_user": not is_err(14) and WRITER in value(14),
            "unknown_connection_denied": is_err(16),
            "no_sql_or_secret_in_stderr": not any(marker in run.stderr for marker in (
                MARKER, PRIVATE, READER_PASS, WRITER_PASS,
                "DELETE FROM public.public_items",
                "SELECT nextval('public.public_counter')")),
            "no_default_ipv4_route": child_connectivity()["checks"]["no_default_ipv4_route"],
        }
        return {"status": "PASS" if all(flags.values()) else "FAIL",
                "checks": flags, "production_permission": "NONE"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--preflight", action="store_true")
    p.add_argument("--binary", type=Path)
    p.add_argument("--child-connectivity", action="store_true")
    p.add_argument("--child-native", action="store_true")
    args = p.parse_args()
    if args.child_connectivity:
        result = child_connectivity()
    elif args.child_native:
        if not args.binary:
            p.error("--child-native requires --binary")
        result = native(args.binary)
    elif args.preflight:
        result = environment_test(None)
    elif args.binary:
        result = environment_test(args.binary)
    else:
        p.error("--preflight or --binary")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

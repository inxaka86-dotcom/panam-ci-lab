#!/usr/bin/env python3
"""Tabularis MCP x ephemeral PostgreSQL 16: public synthetic-only acceptance.

This probe is intentionally bound to localhost:55432 and database
public_mcp_test. The supplied roles/passwords are disposable test constants.
Never run against a PANAM server or a database with real data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HOST, PORT, DATABASE = "127.0.0.1", 55432, "public_mcp_test"
READER, WRITER = "public_mcp_reader", "public_mcp_writer"
READER_PASS, WRITER_PASS = "public-reader-fixture-only", "public-writer-fixture-only"
ADMIN, ADMIN_PASS = "postgres", "public-admin-fixture-only"
READER_ID, WRITER_ID = "public-postgres-reader", "public-postgres-writer"
MARKER = "FICTIONAL_POSTGRES_ITEM_A007"
PRIVATE_MARKER = "FICTIONAL_PRIVATE_DENIED_S078"
DELETE_SQL = "DELETE FROM public.public_items"


def sql_client(query: str, admin: bool = True) -> str:
    env = {"PATH": "/usr/bin:/bin",
           "PGPASSWORD": ADMIN_PASS if admin else READER_PASS,
           "PGCONNECT_TIMEOUT": "5"}
    user = ADMIN if admin else READER
    result = subprocess.run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At",
         "-h", HOST, "-p", str(PORT), "-U", user, "-d", DATABASE,
         "-c", query],
        text=True, capture_output=True, env=env, timeout=10, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("Cannot independently verify the disposable database")
    return result.stdout.strip()


def database_state() -> dict:
    # Hard guard: this is not a generic DB utility or remote access tool.
    assert (HOST, PORT, DATABASE) == ("127.0.0.1", 55432, "public_mcp_test")
    if sql_client("SELECT current_database()") != DATABASE:
        raise RuntimeError("Unexpected target database, refusing probe")
    state = {
        "row": sql_client("SELECT id || ':' || title || ':' || amount FROM public.public_items"),
        "sequence": sql_client("SELECT last_value FROM public.public_counter"),
        "private": sql_client("SELECT secret_marker FROM public.private_items"),
        "extra_table": sql_client("SELECT count(*) FROM information_schema.tables "
                                  "WHERE table_schema='public' AND table_name='created_by_mcp'"),
    }
    return state


def fixture_config(folder: Path) -> Path:
    app = folder / "tabularis-config"
    app.mkdir(mode=0o700)
    config = {
        "mcpReadonlyDefault": True, "mcpReadonlyConnections": [],
        "mcpApprovalMode": "off", "mcpOutputFormat": "json",
        "aiAuditEnabled": False, "activeExternalDrivers": [],
    }

    def conn(identifier: str, user: str, password: str) -> dict:
        return {
            "id": identifier, "name": identifier,
            "params": {
                "driver": "postgres", "host": HOST, "port": PORT,
                "username": user, "password": password,
                "database": DATABASE, "ssl_mode": "disable",
            },
        }

    connections = {
        "groups": [], "tags": [],
        "connections": [conn(READER_ID, READER, READER_PASS),
                        conn(WRITER_ID, WRITER, WRITER_PASS)],
    }
    for name, value in [("config.json", config), ("connections.json", connections)]:
        path = app / name
        path.write_text(json.dumps(value), encoding="utf-8")
        path.chmod(0o600)
    return app


def rpc(number: int, method: str, params: dict | None = None) -> dict:
    data = {"jsonrpc": "2.0", "id": number, "method": method}
    if params is not None:
        data["params"] = params
    return data


def call(number: int, name: str, *, conn: str = WRITER_ID,
         query: str | None = None, table: str | None = None) -> dict:
    args: dict = {"connection_id": conn}
    if query is not None:
        args["query"] = query
    if table is not None:
        args["table_name"] = table
    return rpc(number, "tools/call", {"name": name, "arguments": args})


def requests() -> list[dict]:
    return [
        rpc(1, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "public-postgres-acceptance", "version": "1"}}),
        rpc(2, "tools/list"),
        rpc(3, "tools/call", {"name": "list_connections", "arguments": {}}),
        call(4, "list_tables", conn=READER_ID),
        call(5, "describe_table", conn=READER_ID, table="public_items"),
        call(6, "run_query", conn=READER_ID,
             query="SELECT title, amount FROM public.public_items"),
        call(7, "run_query", query="SELECT title, amount FROM public.public_items"),
        call(8, "run_query", query="WITH c AS (SELECT amount FROM public.public_items) SELECT MAX(amount) FROM c"),
        call(9, "run_query", query="INSERT INTO public.public_items VALUES('x','BAD',9)"),
        call(10, "run_query", query="UPDATE public.public_items SET amount=0"),
        call(11, "run_query", query=DELETE_SQL),
        call(12, "run_query", query="DROP TABLE public.public_items"),
        call(13, "run_query", query="CREATE TABLE public.created_by_mcp (id int)"),
        call(14, "run_query", query="TRUNCATE TABLE public.public_items"),
        call(15, "run_query", query="SELECT nextval('public.public_counter')"),
        call(16, "run_query", query="SELECT setval('public.public_counter', 999)"),
        call(17, "run_query", query="SELECT title INTO public.created_by_mcp FROM public.public_items"),
        call(18, "run_query", conn=READER_ID,
             query="SELECT secret_marker FROM public.private_items"),
        call(19, "run_query", query="SELECT secret_marker FROM public.private_items"),
        call(20, "run_query", query="SELECT current_user"),
        call(21, "run_query", conn="unknown-public-connection", query="SELECT 1"),
    ]


def error(r: dict) -> bool:
    return bool(r.get("error")) or (
        isinstance(r.get("result"), dict) and r["result"].get("isError") is True
    )


def parse(stdout: str) -> tuple[dict, int, bool]:
    responses = []
    bad = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1
    valid = (
        bad == 0 and len(responses) == 21
        and all(isinstance(r, dict) and r.get("jsonrpc") == "2.0"
                and type(r.get("id")) is int for r in responses)
    )
    index = {r["id"]: r for r in responses if isinstance(r, dict)
             and type(r.get("id")) is int}
    valid = valid and len(index) == 21 and set(index) == set(range(1, 22))
    return index, bad, valid


def evaluate(stdout: str, stderr: str, exit_code: int,
             before: dict, after: dict) -> dict:
    responses, malformed, valid = parse(stdout)

    def content(number: int) -> str:
        return json.dumps(responses.get(number, {}).get("result"),
                          ensure_ascii=False)

    tools_result = responses.get(2, {}).get("result") or {}
    names = {v.get("name") for v in tools_result.get("tools", [])
             if isinstance(v, dict)}
    sql_expected = ("SELECT title, amount FROM public.public_items",
                    "SELECT nextval('public.public_counter')")
    privacy_flags = {
        "sql_query_in_stderr": any(q in stderr for q in sql_expected),
        "denied_sql_in_stderr": DELETE_SQL in stderr,
        "data_marker_in_stderr": MARKER in stderr,
        "private_marker_in_stderr": PRIVATE_MARKER in stderr,
        "reader_password_in_stderr": READER_PASS in stderr,
        "writer_password_in_stderr": WRITER_PASS in stderr,
    }
    checks = {
        "process_exit": exit_code == 0,
        "jsonrpc_envelopes": valid,
        "server_identity": (responses.get(1, {}).get("result") or {})
                           .get("serverInfo", {}).get("name") == "tabularis-mcp",
        "tools": {"list_connections", "list_tables", "describe_table",
                  "run_query"}.issubset(names),
        "listed_both_connections": (READER_ID in content(3)
                                    and WRITER_ID in content(3)
                                    and not error(responses.get(3, {}))),
        "reader_lists_tables": ("public_items" in content(4)
                               and not error(responses.get(4, {}))),
        "reader_describes_schema": ("public_items" in content(5)
                                   and not error(responses.get(5, {}))),
        "reader_select": (MARKER in content(6)
                          and not error(responses.get(6, {}))),
        "writer_select": (MARKER in content(7)
                          and not error(responses.get(7, {}))),
        "writer_cte_select": ("17" in content(8)
                             and not error(responses.get(8, {}))),
        "nine_mutating_attempts_denied": all(
            error(responses.get(i, {})) for i in range(9, 18)
        ),
        "reader_private_select_denied": error(responses.get(18, {})),
        "writer_private_select_denied": error(responses.get(19, {})),
        "writer_current_user": (WRITER in content(20)
                                and not error(responses.get(20, {}))),
        "unknown_connection_denied": error(responses.get(21, {})),
        "no_private_marker_in_responses": PRIVATE_MARKER not in stdout,
        "db_data_unchanged": before == after,
    }
    functional = all(checks.values())
    privacy = not any(privacy_flags.values())
    return {
        "suite": "public-tabularis-postgres-mcp-v1",
        "status": ("PASS" if functional and privacy else
                   "PRIVACY_FAIL" if functional else "FUNCTIONAL_FAIL"),
        "functional_pass": functional,
        "privacy_pass": privacy,
        "checks": checks,
        "stderr_canaries": privacy_flags,
        "malformed_stdout_lines": malformed,
        "expected_responses": 21,
        "production_permission": "NONE",
        "scope": "ephemeral local PostgreSQL 16 only",
    }


def native(binary: Path, timeout: int) -> dict:
    binary = binary.resolve(strict=True)
    if timeout < 1 or timeout > 120:
        raise ValueError("Timeout must be 1..120 seconds")
    before = database_state()
    # Refuse unexpected fixture state before any MCP request.
    if (before["row"] != "p-1:" + MARKER + ":17"
        or before["private"] != PRIVATE_MARKER
        or before["sequence"] != "42"
        or before["extra_table"] != "0"):
        raise RuntimeError("Unexpected disposable PostgreSQL fixture")
    with tempfile.TemporaryDirectory(prefix="public-tabularis-pg-") as folder:
        root = Path(folder)
        app = fixture_config(root)
        env = {
            "PATH": "/usr/bin:/bin", "HOME": str(root), "TMPDIR": str(root),
            "TABULARIS_DATA_DIR": str(app), "XDG_CONFIG_HOME": str(root / "xdg"),
            "RUST_LOG": "off", "PGCONNECT_TIMEOUT": "5",
        }
        stdin = "".join(json.dumps(req, separators=(",", ":")) + "\n"
                        for req in requests())
        process = subprocess.run(
            [str(binary), "--mcp"], input=stdin, capture_output=True,
            text=True, check=False, cwd=root, env=env, timeout=timeout,
        )
        after = database_state()
        report = evaluate(process.stdout, process.stderr,
                          process.returncode, before, after)
        report["exit_code"] = process.returncode
        return report


class SelfTest(unittest.TestCase):
    def test_ids(self):
        self.assertEqual([r["id"] for r in requests()], list(range(1, 22)))

    def test_config_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            app = fixture_config(Path(td))
            cfg = json.loads((app / "config.json").read_text())
            self.assertTrue(cfg["mcpReadonlyDefault"])
            self.assertEqual(cfg["mcpReadonlyConnections"], [])
            conn = json.loads((app / "connections.json").read_text())["connections"]
            self.assertEqual([x["params"]["driver"] for x in conn],
                             ["postgres", "postgres"])

    def test_missing_mcp_fails(self):
        r = evaluate("", "", 0, {"row": "synthetic"}, {"row": "synthetic"})
        self.assertEqual(r["status"], "FUNCTIONAL_FAIL")

    def test_privacy_flags(self):
        r = evaluate("", DELETE_SQL + READER_PASS + MARKER, 0, {}, {})
        self.assertTrue(r["stderr_canaries"]["denied_sql_in_stderr"])
        self.assertTrue(r["stderr_canaries"]["reader_password_in_stderr"])
        self.assertTrue(r["stderr_canaries"]["data_marker_in_stderr"])

    def test_duplicate_response_fails(self):
        rows = [json.dumps({"jsonrpc": "2.0", "id": n, "result": {}})
                for n in range(1, 22)]
        rows.append(rows[-1])
        _, _, valid = parse("\n".join(rows))
        self.assertFalse(valid)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.selftest:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest))
        return 0 if result.wasSuccessful() else 1
    if args.binary is None:
        parser.error("--binary or --selftest required")
    try:
        report = native(args.binary, args.timeout)
    except (OSError, subprocess.TimeoutExpired, RuntimeError,
            ValueError, AssertionError) as exc:
        report = {"status": "BLOCKED", "error_type": type(exc).__name__,
                  "production_permission": "NONE"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

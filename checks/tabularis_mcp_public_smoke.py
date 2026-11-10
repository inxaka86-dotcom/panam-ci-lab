#!/usr/bin/env python3
"""Public upstream MCP smoke test: invented SQLite fixture only, no private data."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

CONNECTION = "public-test-sqlite-001"
MARKER = "FICTIONAL_ITEM_ALPHA_0198"
DELETE_SQL = "DELETE FROM public_items"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fixture(root: Path):
    db = root / "synthetic.sqlite3"
    with sqlite3.connect(db) as cx:
        cx.executescript("""
        CREATE TABLE public_items(id TEXT PRIMARY KEY, title TEXT, amount INTEGER);
        INSERT INTO public_items VALUES('p-1','FICTIONAL_ITEM_ALPHA_0198',17);
        """)
    folder = root / "config"
    folder.mkdir(mode=0o700)
    settings = {
        "mcpReadonlyDefault": True,
        "mcpReadonlyConnections": [],
        "mcpApprovalMode": "off",
        "mcpOutputFormat": "json",
        "aiAuditEnabled": False,
        "activeExternalDrivers": [],
    }
    connections = {
        "groups": [], "tags": [], "connections": [{
            "id": CONNECTION, "name": "Public test database",
            "params": {"driver": "sqlite", "database": str(db)},
        }],
    }
    for name, obj in (("config.json", settings), ("connections.json", connections)):
        dest = folder / name
        dest.write_text(json.dumps(obj), encoding="utf-8")
        dest.chmod(0o600)
    return folder, db

def requests():
    def rpc(n, method, params=None):
        x = {"jsonrpc": "2.0", "id": n, "method": method}
        if params is not None:
            x["params"] = params
        return x
    def call(n, name, **kw):
        return rpc(n, "tools/call", {"name": name, "arguments": kw})
    return [
        rpc(1,"initialize",{"protocolVersion":"2024-11-05","capabilities":{},
            "clientInfo":{"name":"public-mcp-smoke","version":"1"}}),
        rpc(2,"tools/list"),
        call(3,"list_connections"),
        call(4,"list_tables",connection_id=CONNECTION),
        call(5,"describe_table",connection_id=CONNECTION,table_name="public_items"),
        call(6,"run_query",connection_id=CONNECTION,query="SELECT title, amount FROM public_items"),
        call(7,"run_query",connection_id=CONNECTION,query="INSERT INTO public_items VALUES ('p-2','ignored',1)"),
        call(8,"run_query",connection_id=CONNECTION,query="UPDATE public_items SET amount=0"),
        call(9,"run_query",connection_id=CONNECTION,query=DELETE_SQL),
        call(10,"run_query",connection_id=CONNECTION,query="DROP TABLE public_items"),
        call(11,"run_query",connection_id=CONNECTION,query="ATTACH DATABASE ':memory:' AS extra"),
        call(12,"run_query",connection_id=CONNECTION,query="SELECT title FROM public_items; DELETE FROM public_items"),
        call(13,"run_query",connection_id=CONNECTION,
            query="WITH c AS (SELECT amount FROM public_items) SELECT MAX(amount) FROM c"),
    ]

def is_error(r):
    return bool(r.get("error")) or (
        isinstance(r.get("result"), dict) and r["result"].get("isError") is True
    )

def assess(stdout, stderr, db, before, returncode):
    responses = []
    malformed = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            responses.append(json.loads(line))
        except ValueError:
            malformed += 1
    by_id = {r["id"]:r for r in responses
             if isinstance(r,dict) and type(r.get("id")) is int}
    def content(n):
        return json.dumps(by_id.get(n,{}).get("result"),ensure_ascii=False)
    initialization = by_id.get(1,{}).get("result") or {}
    tools = by_id.get(2,{}).get("result") or {}
    names = {x.get("name") for x in tools.get("tools",[]) if isinstance(x,dict)}
    checks = {
        "process_exit": returncode==0,
        "jsonrpc_envelopes": (malformed==0 and len(responses)==13
            and len(by_id)==13 and set(by_id)==set(range(1,14))
            and all(r.get("jsonrpc")=="2.0" for r in responses)),
        "server_identity": initialization.get("serverInfo",{}).get("name")=="tabularis-mcp",
        "tools": {"list_connections","list_tables","describe_table","run_query"}.issubset(names),
        "connections": not is_error(by_id.get(3,{})) and CONNECTION in content(3),
        "tables": not is_error(by_id.get(4,{})) and "public_items" in content(4),
        "schema": not is_error(by_id.get(5,{})) and "public_items" in content(5),
        "synthetic_select": not is_error(by_id.get(6,{})) and MARKER in content(6),
        "unsafe_sql_denied": all(is_error(by_id.get(i,{})) for i in range(7,13)),
        "cte_read": not is_error(by_id.get(13,{})) and "17" in content(13),
        "file_unchanged": sha(db)==before,
    }
    with sqlite3.connect("file:"+db.as_posix()+"?mode=ro",uri=True) as cx:
        checks["row_unchanged"]=cx.execute(
            "SELECT title, amount FROM public_items"
        ).fetchone()==(MARKER,17)
    # No raw output or sensitive file path is printed; these are only booleans.
    disclosures = {
        "sql_request_logged": DELETE_SQL in stderr,
        "select_logged": "SELECT title, amount FROM public_items" in stderr,
        "result_logged": MARKER in stderr,
        "file_path_logged": str(db) in stderr,
    }
    functional=all(checks.values())
    privacy=not any(disclosures.values())
    return {
        "suite":"public-synthetic-tabularis-mcp-v1",
        "status":"PASS" if functional and privacy else (
            "PRIVACY_FAIL" if functional else "FUNCTIONAL_FAIL"),
        "functional_pass":functional,
        "privacy_pass":privacy,
        "checks":checks,
        "disclosure_flags":disclosures,
        "response_count":len(responses),
        "malformed_stdout_lines":malformed,
        "production_permission":"NONE",
    }

def run(binary, timeout):
    binary=binary.resolve(strict=True)
    if timeout<1 or timeout>90:
        raise ValueError("timeout outside 1..90 seconds")
    with tempfile.TemporaryDirectory(prefix="public-tabularis-") as folder:
        root=Path(folder)
        config,db=fixture(root)
        original=sha(db)
        env={"PATH":"/usr/bin:/bin","HOME":str(root),
             "XDG_CONFIG_HOME":str(root/"xdg"),
             "TABULARIS_DATA_DIR":str(config),"RUST_LOG":"off"}
        payload="".join(json.dumps(r,separators=(",",":"))+"\n" for r in requests())
        p=subprocess.run([str(binary),"--mcp"],input=payload,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,
            cwd=root,env=env,check=False)
        result=assess(p.stdout,p.stderr,db,original,p.returncode)
        result["binary_sha256"]=sha(binary)
        return result

class SelfTest(unittest.TestCase):
    def test_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            _,db=fixture(Path(folder))
            self.assertEqual(sqlite3.connect(db).execute(
                "SELECT count(*) FROM public_items").fetchone()[0],1)
    def test_request_ids(self):
        self.assertEqual([x["id"] for x in requests()],list(range(1,14)))
    def test_missing_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            _,db=fixture(Path(folder))
            self.assertEqual(assess("","",db,sha(db),0)["status"],"FUNCTIONAL_FAIL")
    def test_logged_public_canary_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _,db=fixture(Path(folder))
            rows=[]
            for n in range(1,14):
                r={"jsonrpc":"2.0","id":n,"result":{"content":[]}}
                if n==1:r["result"]={"serverInfo":{"name":"tabularis-mcp"}}
                if n==2:r["result"]={"tools":[{"name":k} for k in (
                    "list_connections","list_tables","describe_table","run_query")]}
                if n==3:r["result"]={"content":[{"text":CONNECTION}]}
                if n in (4,5):r["result"]={"content":[{"text":"public_items"}]}
                if n==6:r["result"]={"content":[{"text":MARKER}]}
                if n==13:r["result"]={"content":[{"text":"17"}]}
                if 7<=n<=12:r.pop("result");r["error"]={"code":-32000}
                rows.append(json.dumps(r))
            text="\n".join(rows)+"\n"
            self.assertEqual(assess(text,"",db,sha(db),0)["status"],"PASS")
            self.assertEqual(assess(text,DELETE_SQL,db,sha(db),0)["status"],"PRIVACY_FAIL")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--selftest",action="store_true")
    p.add_argument("--binary",type=Path)
    p.add_argument("--timeout",type=int,default=35)
    a=p.parse_args()
    if a.selftest:
        r=unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest))
        return 0 if r.wasSuccessful() else 1
    if a.binary is None:
        p.error("provide --binary or --selftest")
    try:
        result=run(a.binary,a.timeout)
    except (OSError,ValueError,subprocess.TimeoutExpired) as err:
        result={"status":"BLOCKED","error_type":type(err).__name__,
                "production_permission":"NONE"}
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":
    sys.exit(main())

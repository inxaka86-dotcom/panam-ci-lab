#!/usr/bin/env python3
"""Public-only native Tabularis MCP session metadata tests.

Runs the exact public synthetic SQLite MCP fixture under umask 022.
Records only booleans and permission bits; never emits raw session contents.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from tabularis_mcp_public_smoke import (
    fixture, requests, assess, sha
)

FILE = ".mcp_session_state.json"
SENTINEL = "EXTERNAL_PUBLIC_TEST_CANARY_DO_NOT_REPLACE"


def run_probe(binary: Path, audit: str, symlink: bool = False) -> dict:
    if audit not in ("unset", "off", "on"):
        raise ValueError("Unexpected audit mode")
    with tempfile.TemporaryDirectory(prefix="public-tabularis-session-") as tmp:
        root = Path(tmp)
        config_dir, db = fixture(root)
        cfg_file = config_dir / "config.json"
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        if audit == "unset":
            cfg.pop("aiAuditEnabled", None)
        else:
            cfg["aiAuditEnabled"] = audit == "on"
        cfg_file.write_text(json.dumps(cfg), encoding="utf-8")
        cfg_file.chmod(0o600)
        state = config_dir / FILE
        external = root / "external-public-canary.txt"
        if symlink:
            external.write_text(SENTINEL, encoding="utf-8")
            external.chmod(0o644)
            state.symlink_to(external)
        before_db = sha(db)
        payload = "".join(json.dumps(x, separators=(",", ":")) + "\n"
                          for x in requests())
        env = {
            "HOME": str(root), "PATH": "/usr/bin:/bin",
            "TABULARIS_DATA_DIR": str(config_dir),
            "XDG_CONFIG_HOME": str(root / "xdg"),
            "RUST_LOG": "off",
        }
        result = subprocess.run(
            [str(binary), "--mcp"], input=payload, text=True,
            capture_output=True, cwd=root, env=env, check=False, timeout=45,
        )
        smoke = assess(result.stdout, result.stderr, db, before_db,
                       result.returncode)
        state_exists = state.is_file()
        mode = stat.S_IMODE(state.stat().st_mode) if state_exists else None
        state_json_valid = False
        state_contains_query_canary = False
        if state_exists:
            value = state.read_text(encoding="utf-8")
            try:
                obj = json.loads(value)
                state_json_valid = (
                    isinstance(obj, dict) and bool(obj.get("sessionId"))
                    and bool(obj.get("lastActivityAt"))
                )
            except (ValueError, TypeError):
                pass
            state_contains_query_canary = "DELETE FROM public_items" in value
        outside_changed = (external.read_text(encoding="utf-8") != SENTINEL
                           if symlink else None)
        return {
            "audit": audit,
            "mcp_pass": smoke["status"] == "PASS",
            "session_file_exists": state_exists,
            "session_mode": format(mode, "04o") if mode is not None else None,
            "session_owner_only": mode == 0o600,
            "session_json_valid": state_json_valid,
            "session_contains_sql": state_contains_query_canary,
            "session_final_path_is_symlink": state.is_symlink(),
            "external_canary_changed": outside_changed,
        }


def evaluate(ordinary: dict, linked: dict, variant: str) -> dict:
    if variant not in ("baseline", "hardened"):
        raise ValueError("Invalid experiment variant")
    modes = ("unset", "off", "on")
    checks = {
        "mcp_all_modes": all(ordinary[m]["mcp_pass"] for m in modes),
        "session_created_all_modes": all(
            ordinary[m]["session_file_exists"] for m in modes),
        "valid_session_metadata_all_modes": all(
            ordinary[m]["session_json_valid"] for m in modes),
        "no_sql_in_session_all_modes": all(
            not ordinary[m]["session_contains_sql"] for m in modes),
        "symlink_trial_mcp_pass": linked["mcp_pass"],
    }
    if variant == "baseline":
        checks["permissive_session_reproduced"] = all(
            ordinary[m]["session_mode"] == "0644" for m in modes)
        checks["symlink_follow_reproduced"] = (
            linked["session_final_path_is_symlink"]
            and linked["external_canary_changed"] is True)
    else:
        checks["session_owner_only_all_modes"] = all(
            ordinary[m]["session_owner_only"] for m in modes)
        checks["symlink_target_not_overwritten"] = (
            linked["external_canary_changed"] is False
            and not linked["session_final_path_is_symlink"]
            and linked["session_owner_only"]
            and linked["session_json_valid"])
    return {
        "suite": "public-tabularis-mcp-session-state-v1",
        "variant": variant,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "observations": {"regular": ordinary, "symlink": linked},
        "production_permission": "NONE",
    }


class SelfTest(unittest.TestCase):
    def test_fail_closed(self):
        empty = {"mcp_pass": False, "session_file_exists": False,
                 "session_json_valid": False, "session_contains_sql": False,
                 "session_owner_only": False, "session_mode": None}
        normal = {m: dict(empty) for m in ("unset", "off", "on")}
        linked = dict(empty, external_canary_changed=True,
                      session_final_path_is_symlink=True)
        self.assertEqual(evaluate(normal, linked, "hardened")["status"], "FAIL")

    def test_three_modes(self):
        self.assertEqual(("unset", "off", "on"), tuple(("unset", "off", "on")))

    def test_positive_hardened_contract(self):
        good = {"mcp_pass": True, "session_file_exists": True,
                "session_json_valid": True, "session_contains_sql": False,
                "session_owner_only": True, "session_mode": "0600"}
        normal = {m: dict(good) for m in ("unset", "off", "on")}
        linked = dict(good, external_canary_changed=False,
                      session_final_path_is_symlink=False)
        self.assertEqual(evaluate(normal, linked, "hardened")["status"], "PASS")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path)
    p.add_argument("--variant", choices=("baseline", "hardened"))
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        test = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest))
        return 0 if test.wasSuccessful() else 1
    if not args.binary or not args.variant:
        p.error("--binary and --variant required")
    try:
        binary = args.binary.resolve(strict=True)
        prior_umask = os.umask(0o022)
        try:
            normal = {m: run_probe(binary, m) for m in ("unset", "off", "on")}
            symlink = run_probe(binary, "off", symlink=True)
        finally:
            os.umask(prior_umask)
        report = evaluate(normal, symlink, args.variant)
    except (OSError, subprocess.TimeoutExpired, ValueError, RuntimeError) as e:
        report = {"status": "BLOCKED", "error_type": type(e).__name__,
                  "production_permission": "NONE"}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Public synthetic Tabularis MCP audit persistence acceptance, no real data.

Uses only invented SQLite and short-lived TABULARIS_DATA_DIR. Compares
the pinned two-line stderr patch baseline with an audit-minimization patch.
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
    fixture, requests, assess, sha, DELETE_SQL
)

MODES = ("unset", "off", "on")
AUDIT = "ai_activity.jsonl"


def trial(binary: Path, mode: str, timeout: int = 40) -> dict:
    if mode not in MODES:
        raise ValueError("Unknown trial")
    with tempfile.TemporaryDirectory(prefix="public-tabularis-audit-") as td:
        root = Path(td)
        app, db = fixture(root)
        configfile = app / "config.json"
        config = json.loads(configfile.read_text(encoding="utf-8"))
        if mode == "unset":
            config.pop("aiAuditEnabled", None)
        else:
            config["aiAuditEnabled"] = mode == "on"
        configfile.write_text(json.dumps(config), encoding="utf-8")
        configfile.chmod(0o600)

        before = sha(db)
        env = {
            "HOME": str(root),
            "PATH": "/usr/bin:/bin",
            "TABULARIS_DATA_DIR": str(app),
            "XDG_CONFIG_HOME": str(root / "xdg"),
            "RUST_LOG": "off",
        }
        transcript = "".join(json.dumps(msg, separators=(",", ":")) + "\n"
                             for msg in requests())
        process = subprocess.run(
            [str(binary), "--mcp"], input=transcript, text=True,
            capture_output=True, cwd=root, env=env,
            check=False, timeout=timeout,
        )
        smoke = assess(process.stdout, process.stderr, db, before,
                       process.returncode)
        auditfile = app / AUDIT
        exists = auditfile.is_file()
        audit_data = auditfile.read_text(encoding="utf-8") if exists else ""
        disk_files = list(root.rglob("*.jsonl"))
        any_sql_persisted = any(
            DELETE_SQL in f.read_text(encoding="utf-8")
            for f in disk_files if f.is_file()
        )
        mode_bits = stat.S_IMODE(auditfile.stat().st_mode) if exists else None
        return {
            "mode": mode,
            "mcp_pass": smoke["status"] == "PASS",
            "mcp_functional_pass": smoke["functional_pass"],
            "mcp_stderr_privacy_pass": smoke["privacy_pass"],
            "audit_file_present": exists,
            "audit_sql_stored": DELETE_SQL in audit_data,
            "any_jsonl_sql_stored": any_sql_persisted,
            "audit_owner_only": (
                mode_bits is not None and (mode_bits & 0o077) == 0
            ),
            "audit_mode_octal": (
                format(mode_bits, "04o") if mode_bits is not None else None
            ),
            "session_state_file_present": (app / ".mcp_session_state.json").exists(),
        }


def evaluate(results: dict[str, dict], experiment: str) -> dict:
    if experiment not in ("baseline", "hardened"):
        raise ValueError("Unknown experiment")
    checks = {
        "all_three_trial_mcp_pass": all(results[n]["mcp_pass"] for n in MODES),
        "disabled_has_no_audit": (
            not results["off"]["audit_file_present"]
            and not results["off"]["any_jsonl_sql_stored"]
        ),
        "explicit_opt_in_audits": (
            results["on"]["audit_file_present"]
            and results["on"]["audit_sql_stored"]
        ),
    }
    if experiment == "baseline":
        checks["default_audit_reproduced"] = (
            results["unset"]["audit_file_present"]
            and results["unset"]["audit_sql_stored"]
        )
    else:
        checks["default_has_no_audit"] = (
            not results["unset"]["audit_file_present"]
            and not results["unset"]["any_jsonl_sql_stored"]
        )
        checks["explicit_optin_file_owner_only"] = (
            results["on"]["audit_owner_only"]
        )
    return {
        "suite": "public-tabularis-mcp-audit-persistence-v1",
        "experiment": experiment,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "observations": results,
        "production_permission": "NONE",
    }


class SelfTest(unittest.TestCase):
    def test_synthetic_fixture_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            config, db = fixture(Path(td))
            self.assertTrue(config.joinpath("config.json").exists())
            self.assertTrue(db.exists())

    def test_three_modes(self):
        self.assertEqual(MODES, ("unset", "off", "on"))

    def test_evaluation_hardened_fail_closed(self):
        no = {"mcp_pass": True, "audit_file_present": False,
              "audit_sql_stored": False, "any_jsonl_sql_stored": False,
              "audit_owner_only": False}
        r = {mode: dict(no) for mode in MODES}
        self.assertEqual(evaluate(r, "hardened")["status"], "FAIL")

    def test_evaluation_hardened_positive(self):
        no = {"mcp_pass": True, "audit_file_present": False,
              "audit_sql_stored": False, "any_jsonl_sql_stored": False,
              "audit_owner_only": False}
        r = {mode: dict(no) for mode in MODES}
        r["on"]["audit_file_present"] = True
        r["on"]["audit_sql_stored"] = True
        r["on"]["audit_owner_only"] = True
        self.assertEqual(evaluate(r, "hardened")["status"], "PASS")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path)
    p.add_argument("--experiment", choices=("baseline", "hardened"))
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        results = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest)
        )
        return 0 if results.wasSuccessful() else 1
    if args.binary is None or args.experiment is None:
        p.error("--binary and --experiment required")
    try:
        if not args.binary.is_file():
            raise OSError("binary not found")
        observations = {
            m: trial(args.binary.resolve(), m) for m in MODES
        }
        result = evaluate(observations, args.experiment)
    except (OSError, subprocess.TimeoutExpired, RuntimeError,
            ValueError, UnicodeError) as error:
        result = {
            "status": "BLOCKED",
            "error_type": type(error).__name__,
            "production_permission": "NONE",
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

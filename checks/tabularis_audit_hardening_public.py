#!/usr/bin/env python3
"""Exact-match public upstream Tabularis v0.32 audit hardening.

After applying the separately tested MCP stderr redaction, adjust MCP's
unconfigured audit default to opt-in and make AI activity files owner-only
on Unix, including existing files opened for appending.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import unittest

MCP_IMPORT = "    self, AppConfig, DEFAULT_AI_AUDIT_ENABLED, DEFAULT_AI_AUDIT_MAX_ENTRIES,"
MCP_IMPORT_SAFE = "    self, AppConfig, DEFAULT_AI_AUDIT_MAX_ENTRIES,"
MCP_DEFAULT = """    let audit_enabled = app_config
        .ai_audit_enabled
        .unwrap_or(DEFAULT_AI_AUDIT_ENABLED);"""
MCP_DEFAULT_SAFE = """    // MCP queries can contain sensitive SQL and connection details.
    // Persist audit entries only after an explicit opt-in.
    let audit_enabled = app_config
        .ai_audit_enabled
        .unwrap_or(false);"""

OPEN_AUDIT = """    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|e| e.to_string())?;
    writeln!(file, "{}", line).map_err(|e| e.to_string())"""

OPEN_AUDIT_SAFE = """    let mut options = OpenOptions::new();
    options.create(true).append(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&path).map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        file.set_permissions(fs::Permissions::from_mode(0o600))
            .map_err(|e| e.to_string())?;
    }
    writeln!(file, "{}", line).map_err(|e| e.to_string())"""


def exact_replace(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("Unrecognized upstream file or patch already applied")
    return source.replace(old, new)


def patch_mcp(source: str) -> str:
    return exact_replace(
        exact_replace(source, MCP_IMPORT, MCP_IMPORT_SAFE),
        MCP_DEFAULT, MCP_DEFAULT_SAFE,
    )


def patch_activity(source: str) -> str:
    return exact_replace(source, OPEN_AUDIT, OPEN_AUDIT_SAFE)


class SelfTest(unittest.TestCase):
    def test_mcp_patch_minimal(self):
        src = MCP_IMPORT + "\n" + MCP_DEFAULT
        updated = patch_mcp(src)
        self.assertNotIn("DEFAULT_AI_AUDIT_ENABLED", updated)
        self.assertIn("unwrap_or(false)", updated)

    def test_activity_patch_minimal(self):
        result = patch_activity(OPEN_AUDIT)
        self.assertIn("options.mode(0o600)", result)
        self.assertIn("file.set_permissions(", result)

    def test_mcp_reapplication_refused(self):
        source = patch_mcp(MCP_IMPORT + "\n" + MCP_DEFAULT)
        with self.assertRaises(ValueError):
            patch_mcp(source)

    def test_activity_reapplication_refused(self):
        with self.assertRaises(ValueError):
            patch_activity(patch_activity(OPEN_AUDIT))

    def test_mismatched_source_refused(self):
        with self.assertRaises(ValueError):
            patch_mcp("not upstream MCP source")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mcp", type=Path)
    p.add_argument("--activity", type=Path)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()
    if args.selftest:
        run = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest)
        )
        return 0 if run.wasSuccessful() else 1
    if not args.mcp or not args.activity:
        p.error("--mcp and --activity are required")
    # All-or-nothing validation: do not partially edit one file on mismatch.
    mcp = patch_mcp(args.mcp.read_text(encoding="utf-8"))
    activity = patch_activity(args.activity.read_text(encoding="utf-8"))
    args.mcp.write_text(mcp, encoding="utf-8")
    args.activity.write_text(activity, encoding="utf-8")
    print("MCP_AUDIT_OPT_IN_AND_OWNER_ONLY_PATCH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

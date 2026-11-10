#!/usr/bin/env python3
"""Public-safe, exact-source patch: stop Tabularis v0.32.0 MCP payload logging.

Do not silently rewrite other versions: each expected source line must appear once.
The patch changes only upstream src-tauri/src/mcp/mod.rs, not a PANAM source file.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
import unittest

RAW_INPUT = '                eprintln!("[MCP] Received: {}", line);'
RAW_OUTPUT = '                            eprintln!("[MCP] Sending: {}", json);'
SAFE_INPUT = '                // Never log raw MCP requests: SQL, credentials, and data may be present.'
SAFE_OUTPUT = '                            // Never log raw MCP responses: result sets may contain data.'


def patch(source: str) -> str:
    for phrase in (RAW_INPUT, RAW_OUTPUT):
        if source.count(phrase) != 1:
            raise ValueError("Refusing unknown or previously patched upstream MCP source")
    new = source.replace(RAW_INPUT, SAFE_INPUT).replace(RAW_OUTPUT, SAFE_OUTPUT)
    if RAW_INPUT in new or RAW_OUTPUT in new:
        raise ValueError("MCP logging removal incomplete")
    return new


class PatchTests(unittest.TestCase):
    def test_exact_lines_removed(self) -> None:
        before = "\n".join(["fn demo() {", RAW_INPUT, RAW_OUTPUT, "}"])
        after = patch(before)
        self.assertNotIn('Received: {}', after)
        self.assertNotIn('Sending: {}', after)
        self.assertIn("Never log raw MCP requests", after)
        self.assertIn("Never log raw MCP responses", after)

    def test_duplicate_rejected(self) -> None:
        with self.assertRaises(ValueError):
            patch("\n".join([RAW_INPUT, RAW_INPUT, RAW_OUTPUT]))

    def test_missing_rejected(self) -> None:
        with self.assertRaises(ValueError):
            patch(RAW_INPUT)

    def test_second_patch_refused(self) -> None:
        src = "\n".join([RAW_INPUT, RAW_OUTPUT])
        with self.assertRaises(ValueError):
            patch(patch(src))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--source", type=Path)
    args = ap.parse_args()
    if args.selftest:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(PatchTests))
        return 0 if result.wasSuccessful() else 1
    if args.source is None:
        ap.error("--source is required unless --selftest")
    old = args.source.read_text(encoding="utf-8")
    new = patch(old)
    args.source.write_text(new, encoding="utf-8")
    print("TABULARIS_MCP_RAW_PAYLOAD_LOGGING_PATCHED=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

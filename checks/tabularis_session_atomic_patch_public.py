#!/usr/bin/env python3
"""Fail-closed patch for Tabularis v0.32 MCP session state writes.

Replaces fs::write to the session-state path with a private, atomic
write-and-replace operation using the upstream's existing tempfile crate.
This avoids writable 0644 session metadata and following a final-path symlink.
It does NOT prevent reading through a pre-existing malicious symlink; host
filesystem isolation is separately required.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import unittest

ORIGINAL = """    fs::write(&path, content).map_err(|e| e.to_string())
}"""
REPLACEMENT = """    // Session metadata can contain client hints; never write it world-readable.
    // Create a separate private file, then replace the name atomically rather
    // than truncating a pre-existing symlink target.
    let mut temporary = tempfile::NamedTempFile::new_in(dir)
        .map_err(|e| e.to_string())?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        temporary.as_file()
            .set_permissions(fs::Permissions::from_mode(0o600))
            .map_err(|e| e.to_string())?;
    }
    temporary.write_all(content.as_bytes()).map_err(|e| e.to_string())?;
    temporary.as_file().sync_all().map_err(|e| e.to_string())?;
    temporary.persist(&path).map_err(|e| e.error.to_string())?;
    Ok(())
}"""
FUNCTION_ANCHOR = "pub fn save_session_state_in(dir: &Path, state: &SessionState) -> Result<(), String> {"


def patch(src: str) -> str:
    if src.count(FUNCTION_ANCHOR) != 1:
        raise ValueError("Unknown session-state function source")
    if src.count(ORIGINAL) != 1:
        raise ValueError("Expected exact upstream session write not present exactly once")
    start = src.index(FUNCTION_ANCHOR)
    end = src.find("\n}\n", start)
    if end < start or ORIGINAL not in src[start:end+3]:
        raise ValueError("Original write not inside expected function")
    return src.replace(ORIGINAL, REPLACEMENT)


class SelfTest(unittest.TestCase):
    def test_exact_patch(self):
        body = FUNCTION_ANCHOR + "\n" + ORIGINAL
        out = patch(body)
        self.assertIn("NamedTempFile::new_in", out)
        self.assertIn("temporary.persist(&path)", out)
        self.assertIn("Permissions::from_mode(0o600)", out)

    def test_refuse_unknown(self):
        with self.assertRaises(ValueError):
            patch("fn unrelated() {}")

    def test_refuse_repeat(self):
        sample = FUNCTION_ANCHOR + "\n" + ORIGINAL
        with self.assertRaises(ValueError):
            patch(patch(sample))

    def test_refuse_duplicate_write(self):
        with self.assertRaises(ValueError):
            patch(FUNCTION_ANCHOR + "\n" + ORIGINAL + "\n" + ORIGINAL)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    if args.selftest:
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(SelfTest)
        )
        return 0 if result.wasSuccessful() else 1
    if args.source is None:
        parser.error("provide --source or --selftest")
    old = args.source.read_text(encoding="utf-8")
    revised = patch(old)
    args.source.write_text(revised, encoding="utf-8")
    print("SESSION_STATE_ATOMIC_PRIVATE_WRITE_PATCH=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

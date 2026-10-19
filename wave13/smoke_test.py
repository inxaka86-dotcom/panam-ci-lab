#!/usr/bin/env python3
"""Offline synthetic smoke for selected Leanrea command patterns.

No HTTP, npm, model, private source or untrusted executable execution.
Test output is not an agent-performance measurement.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent

def command(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        list(args), check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=45, env=env
    )
    return result.stdout

class OfflineSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        required = ("rg", "jq", "file", "readelf", "go")
        missing = [tool for tool in required if shutil.which(tool) is None]
        if missing:
            raise RuntimeError("Missing required offline tools: " + ", ".join(missing))

    def test_security_constraints(self):
        skill = (HERE / "SKILL.md").read_text()
        for marker in ("NO_PRODUCTION_AUTHORITY", "No network access",
                       "Never rm -rf", "untrusted data", "UNKNOWN", "BLOCKED",
                       "No model-benefit claim"):
            with self.subTest(marker=marker):
                self.assertIn(marker, skill)

    def test_hidden_bundle_search(self):
        with tempfile.TemporaryDirectory(prefix="leanrea-safe-") as d:
            folder = Path(d) / ".webpack"
            folder.mkdir()
            (folder / "main.js").write_text('const token = "ipcMain.handle";\n')
            output = command("rg", "-uu", "-n", "-m", "20", "ipcMain", d)
            self.assertIn("main.js:1:", output)
            self.assertIn("ipcMain.handle", output)

    def test_har_jq(self):
        with tempfile.TemporaryDirectory(prefix="leanrea-safe-") as d:
            p = Path(d) / "fixture.har"
            p.write_text(json.dumps({"log": {"entries": [
                {"request": {"method": "GET",
                             "url": "https://example.invalid/synthetic"}}]}}))
            output = command("jq", "-r",
                             '.log.entries[].request | .method+" "+.url', str(p))
            self.assertEqual("GET https://example.invalid/synthetic",
                             output.strip())

    def test_regex_alternation(self):
        with tempfile.TemporaryDirectory(prefix="leanrea-safe-") as d:
            p = Path(d) / "fixture.asm"
            p.write_text("call f\nmov eax,1\ncmp eax,0\n")
            output = command("rg", "-n", "bl|call|literal|cmp", str(p))
            self.assertEqual(2, len(output.strip().splitlines()))

    def test_scratch_with_spaces_and_neighbor(self):
        with tempfile.TemporaryDirectory(prefix="leanrea-safe-") as d:
            root = Path(d)
            unrelated = root / "unrelated"
            unrelated.mkdir()
            marker = unrelated / "KEEP"
            marker.write_text("unchanged")
            spaced = root / "scratch dir"
            spaced.mkdir()
            with tempfile.TemporaryDirectory(prefix="leanrea.", dir=spaced) as work:
                (Path(work) / "observation").write_text("synthetic")
                self.assertTrue((Path(work) / "observation").is_file())
            self.assertEqual("unchanged", marker.read_text())

    def test_elf_header_read_only(self):
        target = Path("/bin/ls")
        if not target.is_file():
            self.fail("Required Linux /bin/ls ELF fixture is unavailable")
        if "ELF" not in command("file", "--", str(target)):
            self.fail("Required Linux /bin/ls fixture is not ELF")
        header = command("readelf", "-h", "--", str(target))
        self.assertIn("ELF Header", header)
        self.assertIn("Machine:", header)

    def test_go_build_metadata_without_execution(self):
        with tempfile.TemporaryDirectory(prefix="leanrea-safe-") as d:
            folder = Path(d)
            source = folder / "synthetic.go"
            source.write_text("package main\nfunc main() {}\n")
            target = folder / "synthetic"
            # Compiles controlled synthetic source; never invokes target.
            go_env = dict(os.environ, GOPROXY="off", GOSUMDB="off",
                          GOTOOLCHAIN="local", GO111MODULE="off",
                          GOWORK="off", GOTELEMETRY="off")
            command("go", "build", "-o", str(target), str(source), env=go_env)
            info = command("go", "version", "-m", str(target), env=go_env)
            self.assertIn("go1.", info)
            self.assertIn("synthetic", info)

if __name__ == "__main__":
    checks = unittest.defaultTestLoader.loadTestsFromTestCase(OfflineSmoke)
    result = unittest.TextTestRunner(verbosity=2).run(checks)
    complete = result.wasSuccessful() and result.testsRun == 7 and not result.skipped
    print(f"PANAM_LEANREA_OFFLINE_SMOKE={'PASS' if complete else 'FAIL'}"
          f"; executed={result.testsRun - len(result.skipped)}"
          f"; skipped={len(result.skipped)}")
    raise SystemExit(0 if complete else 1)

#!/usr/bin/env python3
"""Run only compilers and static inspection on isolated synthetic artifacts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from build_synthetic_targets import CASES, build, run, sha256


class SyntheticReverseEngineering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="leanrea-target-test-")
        cls.root = Path(cls.temp.name) / "pack"
        cls.manifest = build(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_only_four_predeclared_public_cases(self):
        tasks = json.loads((self.root / "tasks.json").read_text())
        self.assertEqual(tasks["data_class"], "public-synthetic")
        self.assertEqual({x["case_id"] for x in tasks["cases"]}, set(CASES))
        self.assertEqual(len(tasks["cases"]), 4)
        self.assertTrue(all("answer" not in x and "gold" not in x
                            for x in tasks["cases"]))

    def test_electron_hidden_folder_recon(self):
        result = run(["rg", "-uu", "-n", "records:begin-v2",
                      str(self.root / "targets" / "electron-app")])
        self.assertIn(".webpack/main.js", result)
        self.assertIn(".vite/preload.js", result)

    def test_electron_changed_channel(self):
        result = run(["rg", "-uu", "-n", "records:changed-v2",
                      str(self.root / "targets" / "electron-app")])
        self.assertIn(".webpack/main.js", result)
        self.assertIn(".vite/preload.js", result)

    def test_native_export_static(self):
        target = self.root / "targets/libcapture_probe.so"
        exports = run(["nm", "-D", "--defined-only", str(target)])
        self.assertIn("capture_access_check", exports)
        self.assertIn("capture_result", exports)
        header = run(["readelf", "-h", str(target)])
        self.assertIn("ELF Header", header)

    def test_native_disassembly_static(self):
        target = self.root / "targets/libcapture_probe.so"
        dis = run(["objdump", "-d", str(target)])
        self.assertIn("<capture_access_check>:", dis)
        self.assertIn("geteuid", dis)

    def test_go_binary_metadata_not_executed(self):
        target = self.root / "targets/go_probe"
        output = run(["go", "version", "-m", str(target)])
        self.assertIn("example.invalid/leanrea-fixture/tool", output)
        self.assertIn("go1.", output)

    def test_deep_native_strings_and_calls(self):
        target = self.root / "targets/libwire_probe.so"
        strings = run(["strings", "-a", str(target)])
        self.assertIn("/tmp/leanrea-synthetic-v2.sock", strings)
        self.assertIn("HELLO:2", strings)
        symbols = run(["nm", "-D", "--defined-only", str(target)])
        self.assertIn("wire_peer_matches", symbols)
        self.assertIn("wire_handshake", symbols)
        dis = run(["objdump", "-d", str(target)])
        self.assertIn("<wire_handshake>:", dis)
        self.assertIn("wire_peer_matches", dis)

    def test_manifest_hashes_correspond_to_bytes(self):
        for relative, declared in self.manifest["artifacts"].items():
            with self.subTest(file=relative):
                self.assertEqual(declared, sha256(self.root / relative))
                self.assertEqual(len(declared), 64)
        self.assertEqual(self.manifest["status"], "SYNTHETIC_NOT_A_MODEL_BENCHMARK")

    def test_never_overwrites_existing_output(self):
        with self.assertRaises(ValueError):
            build(self.root)
        self.assertTrue((self.root / "tasks.json").is_file())

    def test_refuses_dangling_output_symlink(self):
        dangling = Path(self.temp.name) / "shortcut"
        destination = Path(self.temp.name) / "outside" / "pack"
        dangling.symlink_to(destination)
        with self.assertRaises(ValueError):
            build(dangling)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

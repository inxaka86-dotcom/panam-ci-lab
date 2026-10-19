#!/usr/bin/env python3
"""Synthetic workspace export tests; no model calls and no executable target runs."""
from __future__ import annotations

import json
from pathlib import Path
import stat
import tempfile
import unittest

from export_equal_workspaces import ARMS, BANNED, FILES, file_inventory, prepare


class EqualWorkspaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.holder = tempfile.TemporaryDirectory(prefix="leanrea-export-test-")
        cls.root = Path(cls.holder.name)
        cls.dest = cls.root / "prepared"
        cls.report = prepare(cls.dest)

    @classmethod
    def tearDownClass(cls):
        cls.holder.cleanup()

    def test_same_seven_file_hashes(self):
        x = file_inventory(self.dest / "base")
        y = file_inventory(self.dest / "leanrea")
        self.assertEqual(x, y)
        self.assertEqual(set(x), set(FILES))
        self.assertEqual(x, self.report["source_hashes"])

    def test_agent_workspaces_no_gold_or_skill(self):
        for arm in ARMS:
            paths = list((self.dest / arm).rglob("*"))
            self.assertFalse(any(path.name in BANNED for path in paths))
            self.assertFalse(any(path.suffix == ".py" for path in paths))
            self.assertFalse(any(path.name == ".git" for path in paths))
        self.assertFalse(self.report["gold_in_workspaces"])
        self.assertFalse(self.report["skill_in_workspaces"])

    def test_same_task_bytes_and_public_safe(self):
        packs = [(self.dest / a / "tasks.json").read_bytes() for a in ARMS]
        self.assertEqual(*packs)
        tasks = json.loads(packs[0])
        self.assertEqual(tasks["data_class"], "public-synthetic")
        self.assertEqual(len(tasks["cases"]), 4)
        self.assertTrue(all(set(c) == {"case_id", "task"} for c in tasks["cases"]))

    def test_files_not_executable(self):
        for arm in ARMS:
            root = self.dest / arm
            for path in root.rglob("*"):
                if path.is_file():
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                    self.assertFalse(path.is_symlink())

    def test_no_executor_or_network_claim(self):
        self.assertFalse(self.report["agent_execution"])
        self.assertFalse(self.report["network_sandbox_verified"])
        self.assertEqual(self.report["mode"], "OFFLINE_SYNTHETIC_NO_AGENT")

    def test_manifest_outside_agents(self):
        self.assertTrue((self.dest / "WORKSPACE_MANIFEST.json").is_file())
        self.assertFalse((self.dest / "base/WORKSPACE_MANIFEST.json").exists())
        self.assertFalse((self.dest / "leanrea/WORKSPACE_MANIFEST.json").exists())

    def test_existing_destination_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.dest)
        self.assertEqual(file_inventory(self.dest / "base"),
                         file_inventory(self.dest / "leanrea"))

    def test_dangling_destination_symlink_rejected(self):
        symlink = self.root / "dangling"
        target = self.root / "different" / "unexpected"
        symlink.symlink_to(target)
        with self.assertRaises(ValueError):
            prepare(symlink)
        self.assertFalse(target.exists())

    def test_missing_parent_rejected(self):
        with self.assertRaises(ValueError):
            prepare(self.root / "unknown" / "pack")
        self.assertFalse((self.root / "unknown").exists())

    def test_existing_leaf_file_rejected(self):
        leaf = self.root / "existing.txt"
        leaf.write_text("do-not-modify")
        with self.assertRaises(ValueError):
            prepare(leaf)
        self.assertEqual(leaf.read_text(), "do-not-modify")

    def test_unexpected_agent_file_rejected(self):
        copy = self.root / "unexpected"
        copy.mkdir()
        (copy / "tasks.json").write_bytes((self.dest / "base/tasks.json").read_bytes())
        (copy / "score_synthetic.py").write_text("sensitive grader here")
        with self.assertRaises(ValueError):
            file_inventory(copy)

    def test_world_readable_agent_file_rejected(self):
        copy = self.root / "bad-permission"
        copy.mkdir()
        (copy / "tasks.json").write_text("{}")
        (copy / "tasks.json").chmod(0o644)
        with self.assertRaises(ValueError):
            file_inventory(copy)


if __name__ == "__main__":
    unittest.main(verbosity=2)

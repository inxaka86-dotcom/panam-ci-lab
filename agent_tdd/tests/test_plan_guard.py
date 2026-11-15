"""Identical synthetic RED/GREEN tests for baseline and corrected implementation."""

from __future__ import annotations

import copy
import importlib
import os
import unittest

TARGET = os.environ.get("SYNTHETIC_TDD_TARGET", "plan_guard")
if TARGET not in {"plan_guard", "unsafe_baseline"}:
    raise RuntimeError("unsupported synthetic TDD target")
validate_change_plan = importlib.import_module(
    f"agent_tdd.{TARGET}"
).validate_change_plan

EXAMPLE = {
    "schema": "synthetic.agent-change.v1",
    "data_class": "PUBLIC_SYNTHETIC",
    "changes": [{"path": "synthetic/example.py", "action": "modify"}],
}


class ChangePlanTests(unittest.TestCase):
    def test_accepts_safe_synthetic_plan(self) -> None:
        self.assertEqual(validate_change_plan(copy.deepcopy(EXAMPLE)), ("synthetic/example.py",))

    def test_sorts_multiple_safe_paths_deterministically(self) -> None:
        candidate = copy.deepcopy(EXAMPLE)
        candidate["changes"] = [
            {"path": "synthetic/z/report.json", "action": "create"},
            {"path": "synthetic/a/readme.md", "action": "modify"},
        ]
        self.assertEqual(validate_change_plan(candidate), (
            "synthetic/a/readme.md", "synthetic/z/report.json"))

    def test_rejects_invalid_envelopes(self) -> None:
        cases = [None, [], {}, {**EXAMPLE, "extra": "ignored"}]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_change_plan(case)

    def test_rejects_wrong_schema_or_data_class(self) -> None:
        for key, bad_value in (("schema", "other"), ("data_class", "PRIVATE")):
            candidate = copy.deepcopy(EXAMPLE)
            candidate[key] = bad_value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_change_plan(candidate)

    def test_rejects_empty_and_excessive_changes(self) -> None:
        for changes in ([], EXAMPLE["changes"] * 9, "not a list"):
            candidate = copy.deepcopy(EXAMPLE)
            candidate["changes"] = changes
            with self.subTest(changes=str(changes)[:32]), self.assertRaises(ValueError):
                validate_change_plan(candidate)

    def test_rejects_bad_paths(self) -> None:
        paths = (
            "../synthetic/escape.py", "/synthetic/abs.py",
            "synthetic/../escape.py", "synthetic//gap.py",
            "synthetic/./dot.py", "synthetic/.hidden.py",
            "synthetic\\windows.py", "other/example.py",
            "synthetic/secret.env", "synthetic/x.py\nmore",
            "synthetic/noext", "synthetic/" + "a" * 130 + ".py",
            123, "synthetic/é.py",
        )
        for path in paths:
            candidate = copy.deepcopy(EXAMPLE)
            candidate["changes"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_change_plan(candidate)

    def test_rejects_destructive_or_unknown_actions(self) -> None:
        for action in ("delete", "execute", "deploy", None, "CREATE", [], {}):
            candidate = copy.deepcopy(EXAMPLE)
            candidate["changes"][0]["action"] = action
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate_change_plan(candidate)

    def test_rejects_duplicate_path(self) -> None:
        candidate = copy.deepcopy(EXAMPLE)
        candidate["changes"].append(dict(candidate["changes"][0], action="create"))
        with self.assertRaises(ValueError):
            validate_change_plan(candidate)

    def test_rejects_extra_or_missing_entry_fields(self) -> None:
        for item in ({"path": "synthetic/x.py"},
                     {"path": "synthetic/x.py", "action": "create", "command": "echo hi"},
                     "synthetic/x.py"):
            candidate = copy.deepcopy(EXAMPLE)
            candidate["changes"][0] = item
            with self.subTest(item=item), self.assertRaises(ValueError):
                validate_change_plan(candidate)


if __name__ == "__main__":
    unittest.main()

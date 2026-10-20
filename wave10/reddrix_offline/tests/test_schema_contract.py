"""Stdlib-only structural checks for the proposed JSON Schema (not a full validator)."""
import json
import re
import unittest
from pathlib import Path
from offline_signal import process_fixture

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "panam.signal.v1.schema.json").read_text(encoding="utf-8"))
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
CAPTURED = "2026-10-20T13:14:00Z"


class ProposedSchemaTests(unittest.TestCase):
    def test_schema_is_restrictive(self):
        self.assertEqual(SCHEMA["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(SCHEMA["additionalProperties"])
        self.assertEqual(SCHEMA["properties"]["schema"]["const"], "panam.signal.v1")
        self.assertEqual(SCHEMA["properties"]["provenance"]["kind"] if "kind" in SCHEMA["properties"]["provenance"] else SCHEMA["properties"]["provenance"]["properties"]["kind"]["const"], "synthetic_fixture")

    def test_events_match_declared_fields(self):
        events, report = process_fixture(ROOT / "fixtures" / "synthetic.jsonl", ROOT / "fixtures", POLICY, CAPTURED)
        self.assertEqual((report["accepted"], report["duplicates"]), (3, 1))
        fields = set(SCHEMA["properties"])
        required = set(SCHEMA["required"])
        for item in events:
            self.assertEqual(set(item), fields)
            self.assertTrue(required.issubset(item))
            self.assertRegex(item["record_key"], SCHEMA["properties"]["record_key"]["pattern"])
            self.assertRegex(item["source_url"], SCHEMA["properties"]["source_url"]["pattern"])
            self.assertEqual(item["schema"], SCHEMA["properties"]["schema"]["const"])
            self.assertTrue(set(item["topics"]) <= set(SCHEMA["properties"]["topics"]["items"]["enum"]))


if __name__ == "__main__":
    unittest.main()

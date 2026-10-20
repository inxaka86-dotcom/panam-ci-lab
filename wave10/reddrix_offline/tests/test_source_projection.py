"""Synthetic-only comparison with panam-infrastructure/database/migrations/0001_core.sql."""
import copy
import json
import unittest
from pathlib import Path

from offline_signal import Rejected, process_fixture
from source_projection import project_synthetic_source, SOURCE_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
CAPTURED = "2026-10-20T13:14:00Z"


class SourceProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, cls.report = process_fixture(
            ROOT / "fixtures" / "synthetic.jsonl", ROOT / "fixtures", POLICY, CAPTURED
        )

    def test_three_synthetic_events_no_effects(self):
        self.assertEqual(len(self.events), 3)
        projected = [project_synthetic_source(e) for e in self.events]
        self.assertEqual(len({p["row"]["external_id"] for p in projected}), 3)
        self.assertTrue(all(p["write_authorized"] is False for p in projected))
        self.assertTrue(all(p["runtime_compatibility_verified"] is False for p in projected))

    def test_repository_source_column_shape(self):
        for event in self.events:
            row = project_synthetic_source(event)["row"]
            self.assertEqual(set(row), SOURCE_COLUMNS)
            self.assertEqual(row["source_type"], "web")
            self.assertEqual(row["authority"], "unknown")
            self.assertIs(row["contains_personal_data"], True)
            self.assertIs(row["metadata"]["retention_enforced"], False)

    def test_no_plaintext_or_author_fields(self):
        event = self.events[0]
        projected = project_synthetic_source(event)
        serialized = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn(event["body"], serialized)
        self.assertNotIn(event["title"], serialized)
        self.assertNotIn('"author"', serialized)
        self.assertIsNone(projected["row"]["title"])

    def test_rejects_wrong_provenance_and_identity(self):
        for field, value in (
            ("schema", "panam.signal.v2"),
            ("source_id", "reddit"),
            ("type", "custom"),
            ("record_key", "../bad"),
            ("provenance", {"kind": "reddit", "document_ref": "test"}),
        ):
            with self.subTest(field=field), self.assertRaises(Rejected):
                project_synthetic_source({**self.events[0], field: value})

    def test_rejects_malicious_and_uncanonical_urls(self):
        for url in (
            "https://forum.example.org.evil.invalid/discussions/abc",
            "https://forum.example.org/discussions/abc?token=123",
            "http://forum.example.org/discussions/abc",
        ):
            with self.subTest(url=url), self.assertRaises(Rejected):
                project_synthetic_source({**self.events[0], "source_url": url})

    def test_rejects_invalid_lifecycle(self):
        for field, value in (
            ("published_at", "2026-10-29T00:00:00Z"),
            ("delete_after", "2027-11-01T00:00:00Z"),
            ("delete_after", "2026-10-19T00:00:00Z"),
        ):
            with self.subTest(field=field), self.assertRaises(Rejected):
                project_synthetic_source({**self.events[0], field: value})

    def test_rejects_author_fields_and_unapproved_topics(self):
        extra = copy.deepcopy(self.events[0])
        extra["author"] = "user_name"
        with self.assertRaises(Rejected):
            project_synthetic_source(extra)
        bad_topic = copy.deepcopy(self.events[0])
        bad_topic["topics"] = ["unknown"]
        with self.assertRaises(Rejected):
            project_synthetic_source(bad_topic)


if __name__ == "__main__":
    unittest.main()

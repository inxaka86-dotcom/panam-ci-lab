import json
import tempfile
import unittest
from pathlib import Path

from offline_signal import Rejected, normalize, process_fixture, safe_url, validate_policy

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
FIXTURE = ROOT / "fixtures" / "synthetic.jsonl"
CAPTURED = "2026-10-20T13:14:00Z"
BASE = {
    "synthetic_fixture": True, "source_id": "synthetic_legal_discussions",
    "record_id": "abc", "kind": "discussion",
    "url": "https://forum.example.org/discussions/abc?ref=fake",
    "published_at": "2026-10-19T10:00:00+03:00", "title": "Договор",
    "body": "demo@example.org +7 999 123 45 67", "author": "excluded",
}

class OfflineSignalTests(unittest.TestCase):
    def test_positive_contract(self):
        item = normalize(BASE, POLICY, CAPTURED)
        self.assertEqual(item["schema"], "panam.signal.v1")
        self.assertEqual(item["published_at"], "2026-10-19T07:00:00Z")
        self.assertEqual(item["delete_after"], "2026-10-27T13:14:00Z")
        self.assertEqual(item["topics"], ["contracts"])
        self.assertNotIn("author", item)
        self.assertIn("[EMAIL]", item["body"])
        self.assertIn("[PHONE]", item["body"])
        self.assertNotIn("?", item["source_url"])

    def test_exact_hosts(self):
        for raw in ("http://forum.example.org/discussions/abc",
                    "https://forum.example.org.evil.invalid/discussions/abc",
                    "https://evilforum.example.org/discussions/abc",
                    "https://user:pass@forum.example.org/discussions/abc",
                    "https://forum.example.org:443/discussions/abc",
                    "https://forum.example.org/discussions/../admin",
                    "https://forum.example.org/discussions/%2e%2e/admin",
                    "https://forum.example.org/discussions/abc#fragment"):
            with self.subTest(raw=raw), self.assertRaises(Rejected):
                safe_url(raw, POLICY["allowed_host"])

    def test_real_mode_rejected(self):
        for name, val in (("mode", "live"), ("data_status", "real"),
                          ("authorization", "unverified"), ("allowed_host", "reddit.com"),
                          ("max_records", 99999), ("retention_days", 500)):
            p = {**POLICY, name: val}
            with self.subTest(name=name), self.assertRaises(Rejected):
                validate_policy(p)

    def test_non_synthetic_item_rejected(self):
        for name, val in (("synthetic_fixture", False), ("source_id", "other"),
                          ("kind", "unknown"), ("record_id", "../escape")):
            with self.subTest(name=name), self.assertRaises(Rejected):
                normalize({**BASE, name: val}, POLICY, CAPTURED)

    def test_timestamp_requires_timezone(self):
        with self.assertRaises(Rejected):
            normalize({**BASE, "published_at": "2026-10-20T13:00:00"}, POLICY, CAPTURED)
        with self.assertRaises(Rejected):
            normalize(BASE, POLICY, "2026-10-20T13:00:00")

    def test_empty_content_rejected(self):
        with self.assertRaises(Rejected):
            normalize({**BASE, "title": None, "body": None}, POLICY, CAPTURED)

    def test_fixture_report(self):
        items, report = process_fixture(FIXTURE, ROOT / "fixtures", POLICY, CAPTURED)
        self.assertEqual((report["consumed"], report["accepted"], report["duplicates"]), (4, 3, 1))
        self.assertEqual(report["topics"], {"consumer": 1, "contracts": 1, "procurement": 1})
        self.assertEqual(len(items), 3)

    def test_reject_outside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "test.jsonl"
            other.write_text(json.dumps(BASE), encoding="utf-8")
            with self.assertRaises(Rejected):
                process_fixture(other, ROOT / "fixtures", POLICY, CAPTURED)

    def test_fixture_limit(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "fixtures") as tmp:
            path = Path(tmp) / "sample.jsonl"
            path.write_text((json.dumps(BASE) + "\n") * (POLICY["max_records"] + 1), encoding="utf-8")
            with self.assertRaises(Rejected):
                process_fixture(path, ROOT / "fixtures", POLICY, CAPTURED)

    def test_malformed_json(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "fixtures") as tmp:
            path = Path(tmp) / "sample.jsonl"
            path.write_text("{bad json}", encoding="utf-8")
            with self.assertRaises(Rejected):
                process_fixture(path, ROOT / "fixtures", POLICY, CAPTURED)

if __name__ == "__main__":
    unittest.main()

"""Fail-closed synthetic ingress, replay, memory retention and no-production tests."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from offline_signal import Rejected, process_fixture
from synthetic_ingress import (
    EXACT_FIXTURE_CONTEXT, MAX_BATCH, SyntheticInbox, check_fixture_context,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads((ROOT / "policy.json").read_text(encoding="utf-8"))
CAPTURED = "2026-10-20T13:14:00Z"
NOW = "2026-10-20T14:00:00Z"
AFTER_RETENTION = "2026-10-27T13:14:00Z"


class SyntheticIngressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, _ = process_fixture(
            ROOT / "fixtures" / "synthetic.jsonl", ROOT / "fixtures", POLICY, CAPTURED
        )

    def setUp(self):
        self.inbox = SyntheticInbox()

    def test_accept_three_and_no_effect_claim(self):
        receipt = self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        self.assertEqual((receipt["accepted"], receipt["duplicates"], receipt["stored"]), (3, 0, 3))
        self.assertIs(receipt["production_write_authorized"], False)
        self.assertIs(receipt["runtime_authorization_verified"], False)
        self.assertIs(receipt["persistent_retention_enforced"], False)

    def test_repeat_is_idempotent_in_memory(self):
        self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        receipt = self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        self.assertEqual((receipt["accepted"], receipt["duplicates"], receipt["stored"]), (0, 3, 3))

    def test_duplicate_within_one_batch(self):
        r = self.inbox.accept([self.events[0], self.events[0]], context=EXACT_FIXTURE_CONTEXT, now=NOW)
        self.assertEqual((r["accepted"], r["duplicates"], r["stored"]), (1, 1, 1))

    def test_not_storing_body_title_author(self):
        self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        dump = json.dumps(self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT), ensure_ascii=False)
        for e in self.events:
            self.assertNotIn(e["body"], dump)
            if e["title"]:
                self.assertNotIn(e["title"], dump)
        self.assertNotIn('"author"', dump)

    def test_reject_bypass_attempts(self):
        for field, value in (
            ("actor", "untrusted-worker"),
            ("mode", "live"),
            ("purpose", "marketing_bulk_export"),
            ("transport", "https"),
            ("source_id", "reddit"),
            ("data_status", "real"),
            ("network_allowed", True),
        ):
            with self.subTest(field=field), self.assertRaises(Rejected):
                self.inbox.accept(self.events, context={**EXACT_FIXTURE_CONTEXT, field: value}, now=NOW)
            self.assertEqual(self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT), [])

    def test_context_extra_field_denied(self):
        with self.assertRaises(Rejected):
            check_fixture_context({**EXACT_FIXTURE_CONTEXT, "write_authorized": True})

    def test_no_real_reddit_source(self):
        item = {**self.events[0], "source_url": "https://www.reddit.com/r/example/comments/abc"}
        with self.assertRaises(Rejected):
            self.inbox.accept([item], context=EXACT_FIXTURE_CONTEXT, now=NOW)

    def test_atomic_failure_does_not_partially_accept(self):
        bad = {**self.events[1], "schema": "panam.signal.v2"}
        with self.assertRaises(Rejected):
            self.inbox.accept([self.events[0], bad], context=EXACT_FIXTURE_CONTEXT, now=NOW)
        self.assertEqual(self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT), [])

    def test_rejects_future_and_expired(self):
        with self.assertRaises(Rejected):
            self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now="2026-10-19T00:00:00Z")
        with self.assertRaises(Rejected):
            self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=AFTER_RETENTION)
        self.assertEqual(self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT), [])

    def test_expire_at_inclusive_deadline(self):
        self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        before = self.inbox.expire(context=EXACT_FIXTURE_CONTEXT, now="2026-10-27T13:13:59Z")
        self.assertEqual((before["expired_in_memory"], before["stored"]), (0, 3))
        after = self.inbox.expire(context=EXACT_FIXTURE_CONTEXT, now=AFTER_RETENTION)
        self.assertEqual((after["expired_in_memory"], after["stored"]), (3, 0))
        self.assertIs(after["persistent_deletion_verified"], False)

    def test_expire_requires_fixture_context(self):
        self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        with self.assertRaises(Rejected):
            self.inbox.expire(context={**EXACT_FIXTURE_CONTEXT, "transport": "network"}, now=AFTER_RETENTION)
        self.assertEqual(len(self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT)), 3)

    def test_snapshot_cannot_mutate_store(self):
        self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=NOW)
        snapshot = self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT)
        snapshot[0]["metadata"]["topics"].append("injected")
        fresh = self.inbox.metadata_snapshot(context=EXACT_FIXTURE_CONTEXT)
        self.assertNotIn("injected", fresh[0]["metadata"]["topics"])

    def test_invalid_batch_fail_closed(self):
        for batch in ([], "not-an-array", [{}] * (MAX_BATCH + 1)):
            with self.subTest(batch_type=type(batch).__name__), self.assertRaises(Rejected):
                self.inbox.accept(batch, context=EXACT_FIXTURE_CONTEXT, now=NOW)

    def test_invalid_timestamp_fail_closed(self):
        for now in ("2026-10-20T13:14:00", "junk", "2010-01-01T00:00:00Z"):
            with self.subTest(now=now), self.assertRaises(Rejected):
                self.inbox.accept(self.events, context=EXACT_FIXTURE_CONTEXT, now=now)


if __name__ == "__main__":
    unittest.main()

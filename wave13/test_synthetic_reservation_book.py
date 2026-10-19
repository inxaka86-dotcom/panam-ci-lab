#!/usr/bin/env python3
"""No-network adversarial tests for a SYNTHETIC in-memory reservation model."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import unittest

from synthetic_reservation_book import SyntheticReservations, Invalid
from test_synthetic_usd_envelope import packet


def slot_ids():
    return [(case, arm) for case in ("LR-E01", "LR-N01", "LR-G01", "LR-D01")
            for arm in ("base", "leanrea")]


class InMemoryReservationTests(unittest.TestCase):
    def book(self):
        return SyntheticReservations(packet())

    def reserve(self, b, case="LR-E01", arm="base", nonce="synthetic001"):
        return b.reserve(case, arm, nonce)

    def test_all_eight_slots_reserve_once(self):
        b = self.book()
        for i, (case, arm) in enumerate(slot_ids()):
            r = self.reserve(b, case, arm, "synthetic-%03d" % i)
            self.assertFalse(r["real_upstream_request_allowed"])
            self.assertFalse(r["provider_call_performed"])
        s = b.snapshot()
        self.assertEqual((s["slots_reserved"], s["remaining_synthetic_slot_count"]), (8, 0))
        self.assertEqual(s["synthetic_held_micro_usd"], 16000)

    def test_same_slot_64_simultaneous_only_one_wins(self):
        b = self.book()
        def try_one(i):
            try:
                self.reserve(b, nonce="parallel-%03d" % i)
                return True
            except Invalid:
                return False
        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(try_one, range(64)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(b.snapshot()["synthetic_held_micro_usd"], 2000)

    def test_64_simultaneous_all_eight_and_replays(self):
        b = self.book()
        ids = slot_ids()
        def try_one(i):
            case, arm = ids[i % 8]
            try:
                self.reserve(b, case, arm, "parallel-%03d" % i)
                return True
            except Invalid:
                return False
        with ThreadPoolExecutor(max_workers=24) as pool:
            results = list(pool.map(try_one, range(64)))
        self.assertEqual(sum(results), 8)
        self.assertEqual(b.snapshot()["synthetic_held_micro_usd"], 16000)

    def test_duplicate_slot_different_nonce_rejected(self):
        b = self.book()
        self.reserve(b)
        with self.assertRaises(Invalid):
            self.reserve(b, nonce="synthetic002")

    def test_nonce_replay_across_cases_rejected(self):
        b = self.book()
        self.reserve(b)
        with self.assertRaises(Invalid):
            self.reserve(b, case="LR-N01", nonce="synthetic001")

    def test_nonce_length_rejected(self):
        b = self.book()
        with self.assertRaises(Invalid):
            self.reserve(b, nonce="a")

    def test_nonce_control_or_slash_rejected(self):
        b = self.book()
        with self.assertRaises(Invalid):
            self.reserve(b, nonce="../../test")

    def test_empty_case_rejected(self):
        with self.assertRaises(Invalid):
            self.reserve(self.book(), case="")

    def test_unknown_arm_rejected(self):
        with self.assertRaises(Invalid):
            self.reserve(self.book(), arm="fallback")

    def test_unhashable_arm_rejected(self):
        with self.assertRaises(Invalid):
            self.reserve(self.book(), arm=[])

    def test_unhashable_case_rejected(self):
        with self.assertRaises(Invalid):
            self.reserve(self.book(), case={})

    def test_none_nonce_rejected(self):
        with self.assertRaises(Invalid):
            self.reserve(self.book(), nonce=None)

    def test_stop_blocks_new_slots(self):
        b = self.book()
        b.stop()
        with self.assertRaises(Invalid):
            self.reserve(b)
        self.assertTrue(b.snapshot()["stopped"])

    def test_uncertain_outcome_never_releases_hold(self):
        b = self.book()
        self.reserve(b)
        b.mark_uncertain("LR-E01", "base")
        self.assertEqual(b.snapshot()["synthetic_held_micro_usd"], 2000)
        self.assertEqual(b.snapshot()["states"][0]["state"], "UNKNOWN_NO_REFUND")
        with self.assertRaises(Invalid):
            self.reserve(b, nonce="next-nonce-100")

    def test_unknown_uncertain_slot_rejected(self):
        with self.assertRaises(Invalid):
            self.book().mark_uncertain("LR-E01", "base")

    def test_double_mark_uncertain_rejected(self):
        b = self.book()
        self.reserve(b)
        b.mark_uncertain("LR-E01", "base")
        with self.assertRaises(Invalid):
            b.mark_uncertain("LR-E01", "base")

    def test_small_claim_does_not_release_reservation(self):
        b = self.book()
        self.reserve(b)
        b.record_claim("LR-E01", "base", 1)
        self.assertEqual(b.snapshot()["synthetic_held_micro_usd"], 2000)
        self.assertEqual(b.snapshot()["states"][0]["state"], "CLAIM_ONLY_NO_REFUND")

    def test_exact_claim_accepted_as_unverified(self):
        b = self.book()
        self.reserve(b)
        b.record_claim("LR-E01", "base", 2000)
        self.assertFalse(b.snapshot()["provider_charges_verified"])

    def test_claim_over_reserved_stops_book(self):
        b = self.book()
        self.reserve(b)
        with self.assertRaises(Invalid):
            b.record_claim("LR-E01", "base", 2001)
        self.assertTrue(b.snapshot()["stopped"])
        with self.assertRaises(Invalid):
            self.reserve(b, case="LR-N01", nonce="different-001")

    def test_claim_boolean_rejected(self):
        b = self.book()
        self.reserve(b)
        with self.assertRaises(Invalid):
            b.record_claim("LR-E01", "base", True)

    def test_negative_claim_rejected(self):
        b = self.book()
        self.reserve(b)
        with self.assertRaises(Invalid):
            b.record_claim("LR-E01", "base", -1)

    def test_double_claim_rejected(self):
        b = self.book()
        self.reserve(b)
        b.record_claim("LR-E01", "base", 20)
        with self.assertRaises(Invalid):
            b.record_claim("LR-E01", "base", 21)

    def test_claim_without_reservation_rejected(self):
        with self.assertRaises(Invalid):
            self.book().record_claim("LR-E01", "base", 20)

    def test_over_budget_envelope_rejected_before_use(self):
        p = packet()
        p["tariff"]["micro_usd_per_million_input"] = 10_000_000
        p["tariff"]["micro_usd_per_million_output"] = 10_000_000
        with self.assertRaises(Invalid):
            SyntheticReservations(p)

    def test_invalid_real_tariff_data_class_rejected(self):
        p = packet()
        p["tariff"]["data_class"] = "provider_verified"
        with self.assertRaises(Invalid):
            SyntheticReservations(p)

    def test_snapshot_no_execution_authority_or_real_billing(self):
        r = self.book().snapshot()
        for field in ("currency_contract_verified", "provider_charges_verified",
                      "persistent_atomic_ledger", "crash_recovery_verified",
                      "kernel_egress_isolation_verified", "model_generation_verified",
                      "real_upstream_request_allowed", "real_usd_hard_cap_enforced",
                      "specific_owner_spend_approval"):
            self.assertFalse(r[field])
        self.assertEqual(r["status"], "IN_MEMORY_SYNTHETIC_ONLY_NOT_A_BROKER")


if __name__ == "__main__":
    unittest.main(verbosity=2)

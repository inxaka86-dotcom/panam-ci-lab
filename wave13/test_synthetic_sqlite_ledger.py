#!/usr/bin/env python3
"""Public-safe filesystem and multi-process tests for the SQLite demo ONLY."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from synthetic_sqlite_ledger import SyntheticSQLiteLedger, Invalid
from test_synthetic_usd_envelope import packet


def worker_reserve(db_string, case, arm, nonce, queue):
    try:
        ledger = SyntheticSQLiteLedger(packet(), Path(db_string), create=False)
        ledger.reserve(case, arm, nonce)
        queue.put(True)
    except Exception:
        queue.put(False)


def worker_crash_uncommitted(db_string):
    # SYNTHETIC test fixture simulates a process killed after an uncommitted
    # local SQLite insert, before SQLite commits a write. No API/model activity.
    conn = sqlite3.connect(db_string, isolation_level=None, timeout=3)
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("""
        INSERT INTO reservations
        (case_id,arm,nonce,reserved_micro_usd,state,claim_micro_usd)
        VALUES(?,?,?,?,?,NULL)
    """, ("LR-E01", "base", "crash-before-commit", 2000, "HELD"))
    os._exit(19)


def worker_crash_after_commit(db_string):
    ledger = SyntheticSQLiteLedger(packet(), Path(db_string), create=False)
    ledger.reserve("LR-E01", "base", "crash-after-commit")
    os._exit(20)


class SyntheticSQLiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="leanrea-sqlite-")
        self.root = Path(self.tmp.name)
        self.db = self.root / "ledger.sqlite"

    def tearDown(self):
        self.tmp.cleanup()

    def new(self):
        return SyntheticSQLiteLedger(packet(), self.db, create=True)

    def reopen(self):
        return SyntheticSQLiteLedger(packet(), self.db, create=False)

    def test_new_empty_database_is_private(self):
        x = self.new().snapshot()
        self.assertEqual(x["slots_reserved"], 0)
        self.assertEqual(stat.S_IMODE(self.db.stat().st_mode), 0o600)

    def test_reopen_empty_database(self):
        self.new()
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 0)

    def test_reopen_retains_reservation(self):
        self.new().reserve("LR-E01", "base", "restart-test-001")
        x = self.reopen().snapshot()
        self.assertEqual(x["slots_reserved"], 1)
        self.assertEqual(x["synthetic_held_micro_usd"], 2000)

    def test_replay_after_restart_denied(self):
        self.new().reserve("LR-E01", "base", "restart-test-002")
        with self.assertRaises(Invalid):
            self.reopen().reserve("LR-E01", "base", "restart-test-003")

    def test_nonce_replay_after_restart_denied(self):
        self.new().reserve("LR-E01", "base", "restart-test-004")
        with self.assertRaises(Invalid):
            self.reopen().reserve("LR-N01", "base", "restart-test-004")

    def test_eight_slots_count_and_bound(self):
        l = self.new()
        for j, case in enumerate(("LR-E01", "LR-N01", "LR-G01", "LR-D01")):
            for k, arm in enumerate(("base", "leanrea")):
                l.reserve(case, arm, "allslots-%02d-%02d" % (j, k))
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 8)
        self.assertEqual(self.reopen().snapshot()["synthetic_held_micro_usd"], 16000)

    def test_threadlike_two_independent_connections(self):
        first = self.new()
        second = self.reopen()
        first.reserve("LR-E01", "base", "independent-001")
        with self.assertRaises(Invalid):
            second.reserve("LR-E01", "base", "independent-002")

    def test_multi_process_16_same_slot_one_wins(self):
        self.new()
        q = multiprocessing.Queue()
        procs = [
            multiprocessing.Process(
                target=worker_reserve,
                args=(str(self.db), "LR-E01", "base", "parallel-%03d" % i, q))
            for i in range(16)
        ]
        for p in procs:
            p.start()
        results = [q.get(timeout=15) for _ in procs]
        for p in procs:
            p.join(timeout=15)
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(sum(results), 1)
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 1)

    def test_multi_process_16_across_eight_slots_eight_wins(self):
        self.new()
        q = multiprocessing.Queue()
        cases = ("LR-E01", "LR-N01", "LR-G01", "LR-D01")
        procs = [
            multiprocessing.Process(target=worker_reserve, args=(
                str(self.db), cases[(i % 8)//2], ("base", "leanrea")[i % 2],
                "multi-case-%03d" % i, q))
            for i in range(16)
        ]
        for p in procs:
            p.start()
        results = [q.get(timeout=15) for _ in procs]
        for p in procs:
            p.join(timeout=15)
            self.assertEqual(p.exitcode, 0)
        self.assertEqual(sum(results), 8)
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 8)
        self.assertEqual(self.reopen().snapshot()["synthetic_held_micro_usd"], 16000)

    def test_uncertain_after_restart_keeps_amount(self):
        l = self.new()
        l.reserve("LR-E01", "base", "uncertain-001")
        l.uncertain("LR-E01", "base")
        x = self.reopen().snapshot()
        self.assertEqual(x["states"][0]["state"], "UNKNOWN_NO_REFUND")
        self.assertEqual(x["synthetic_held_micro_usd"], 2000)

    def test_unknown_reservation_cannot_be_uncertain(self):
        self.new()
        with self.assertRaises(Invalid):
            self.reopen().uncertain("LR-E01", "base")

    def test_small_claim_never_refunds_across_restart(self):
        l = self.new()
        l.reserve("LR-E01", "base", "small-claim-001")
        l.claim("LR-E01", "base", 1)
        x = self.reopen().snapshot()
        self.assertEqual(x["states"][0]["state"], "CLAIM_NO_REFUND")
        self.assertEqual(x["synthetic_held_micro_usd"], 2000)

    def test_overclaim_persists_stop(self):
        l = self.new()
        l.reserve("LR-E01", "base", "overclaim-001")
        with self.assertRaises(Invalid):
            l.claim("LR-E01", "base", 2001)
        r = self.reopen()
        self.assertTrue(r.snapshot()["stopped"])
        self.assertEqual(r.snapshot()["states"][0]["state"], "OVERCLAIM_STOP")
        with self.assertRaises(Invalid):
            r.reserve("LR-N01", "base", "after-stop-001")

    def test_stop_persists_after_restart(self):
        l = self.new()
        l.stop()
        with self.assertRaises(Invalid):
            self.reopen().reserve("LR-E01", "base", "after-stop-002")

    def test_claim_without_reservation_denied(self):
        self.new()
        with self.assertRaises(Invalid):
            self.reopen().claim("LR-E01", "base", 1)

    def test_boolean_claim_denied(self):
        l = self.new()
        l.reserve("LR-E01", "base", "bool-claim-001")
        with self.assertRaises(Invalid):
            l.claim("LR-E01", "base", True)

    def test_refuse_preexisting_db_on_create(self):
        self.new()
        with self.assertRaises(Invalid):
            self.new()

    def test_refuse_missing_db_on_reopen(self):
        with self.assertRaises(Invalid):
            self.reopen()

    def test_refuse_symlinked_db_on_reopen(self):
        actual = self.root / "real.sqlite"
        self.new()
        self.db.rename(actual)
        self.db.symlink_to(actual)
        with self.assertRaises(Invalid):
            self.reopen()

    def test_refuse_unsafe_parent_permissions(self):
        self.root.chmod(0o755)
        with self.assertRaises(Invalid):
            self.new()

    def test_refuse_world_readable_db(self):
        self.new()
        self.db.chmod(0o644)
        with self.assertRaises(Invalid):
            self.reopen()

    def test_refuse_hardlinked_db(self):
        self.new()
        os.link(self.db, self.root / "another-hardlink.sqlite")
        with self.assertRaises(Invalid):
            self.reopen()

    def test_envelope_hash_mismatch_refused(self):
        self.new()
        altered = packet()
        altered["slots"][0]["max_output_tokens"] = 500
        altered["slots"][1]["max_output_tokens"] = 500
        with self.assertRaises(Invalid):
            SyntheticSQLiteLedger(altered, self.db, create=False)

    def test_database_metadata_tampering_refused(self):
        self.new()
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE metadata SET v='fake' WHERE k='envelope_sha256'")
        with self.assertRaises(Invalid):
            self.reopen()

    def test_crash_precommit_rolls_back(self):
        self.new()
        p = multiprocessing.Process(target=worker_crash_uncommitted, args=(str(self.db),))
        p.start()
        p.join(timeout=15)
        self.assertEqual(p.exitcode, 19)
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 0)

    def test_crash_after_commit_retains(self):
        self.new()
        p = multiprocessing.Process(target=worker_crash_after_commit, args=(str(self.db),))
        p.start()
        p.join(timeout=15)
        self.assertEqual(p.exitcode, 20)
        self.assertEqual(self.reopen().snapshot()["slots_reserved"], 1)

    def test_no_model_provider_or_cap_proven(self):
        x = self.new().snapshot()
        for field in ("provider_billable_request_executed", "real_upstream_request_allowed",
                      "real_usd_hard_cap_enforced", "currency_contract_verified",
                      "provider_charges_verified", "crash_consistency_on_target_host_verified",
                      "kernel_network_isolation_verified",
                      "authenticated_model_response_verified", "owner_spend_approval"):
            self.assertFalse(x[field])
        self.assertEqual(x["status"], "LOCAL_SQLITE_SYNTHETIC_ONLY_NOT_A_BROKER")


if __name__ == "__main__":
    unittest.main(verbosity=2)

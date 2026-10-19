#!/usr/bin/env python3
"""Thread-safe IN-MEMORY synthetic request reservation model for Leanrea.

This is NOT a network/API broker, daemon, spend limiter, trusted ledger or
execution permission. There is deliberately no send/forward/connect callback,
no API key handling, no file journal, no subprocess and no approval parser.
All prices are fabricated; no real USD billing or crash recovery is possible.
"""
from __future__ import annotations

from threading import Lock
import re

from synthetic_usd_envelope import Invalid, project, DEMO_CAP_MICRO_USD

NONCE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{7,63}\Z")


class SyntheticReservations:
    """Fail-closed demo: lock serializes reservation of predetermined A/B slots.

    Conservatively retains the maximum amount after claim/abort. It never
    refunds a reservation because no provider billing proof is available.
    """

    def __init__(self, example_envelope: dict):
        projection = project(example_envelope)
        if not projection["synthetic_arithmetic_under_demo_cap"]:
            raise Invalid("Synthetic maximum exceeds toy ceiling")
        # Snapshot immutable values; never retain caller-controlled envelope.
        slots = projection["per_slot"]
        self._costs = {
            (x["case_id"], x["arm"]): x["synthetic_worst_case_micro_usd"]
            for x in slots
        }
        if len(self._costs) != 8:
            raise Invalid("Missing synthetic slots")
        self._lock = Lock()
        self._used = {}
        self._nonces = set()
        self._held_micro_usd = 0
        self._stopped = False

    def reserve(self, case_id: str, arm: str, nonce: str) -> dict:
        if (not isinstance(case_id, str) or not isinstance(arm, str)
                or not isinstance(nonce, str) or not NONCE.fullmatch(nonce)):
            raise Invalid("Malformed slot identity or nonce")
        with self._lock:
            if self._stopped:
                raise Invalid("Synthetic reservation book stopped")
            key = (case_id, arm)
            if key not in self._costs:
                raise Invalid("Unknown A/B slot")
            if key in self._used or nonce in self._nonces:
                raise Invalid("Duplicate/replayed reservation attempt")
            amount = self._costs[key]
            if self._held_micro_usd + amount > DEMO_CAP_MICRO_USD:
                raise Invalid("Toy ceiling exceeded")
            self._held_micro_usd += amount
            self._nonces.add(nonce)
            self._used[key] = {"nonce": nonce, "state": "SYNTHETIC_HELD"}
            return {
                "case_id": case_id,
                "arm": arm,
                "synthetic_reserved_micro_usd": amount,
                "synthetic_reservation_recorded": True,
                "real_upstream_request_allowed": False,
                "provider_call_performed": False,
                "specific_owner_approval": False,
            }

    def mark_uncertain(self, case_id: str, arm: str) -> None:
        """Mark unknown synthetic outcome; hold remains consumed forever."""
        with self._lock:
            key = (case_id, arm)
            if key not in self._used or self._used[key]["state"] != "SYNTHETIC_HELD":
                raise Invalid("Unknown or previously finalized reservation")
            self._used[key]["state"] = "UNKNOWN_NO_REFUND"

    def record_claim(self, case_id: str, arm: str, amount_micro_usd: int) -> None:
        """Record unverified fabricated charge; does NOT authenticate receipts."""
        if type(amount_micro_usd) is not int or amount_micro_usd < 0:
            raise Invalid("Noninteger or negative fabricated cost")
        with self._lock:
            key = (case_id, arm)
            if key not in self._used or self._used[key]["state"] != "SYNTHETIC_HELD":
                raise Invalid("Unknown or finalized synthetic reservation")
            if amount_micro_usd > self._costs[key]:
                self._used[key]["state"] = "OVER_CLAIM_STOPPED"
                self._stopped = True
                raise Invalid("Unverified claimed charge exceeds held amount; stop")
            self._used[key]["state"] = "CLAIM_ONLY_NO_REFUND"
            # Never free unconsumed reservation: delayed charges are unknown.

    def stop(self) -> None:
        with self._lock:
            self._stopped = True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "schema": "panam.leanrea.synthetic-reservations-snapshot.v1",
                "slots_reserved": len(self._used),
                "synthetic_held_micro_usd": self._held_micro_usd,
                "demo_cap_micro_usd": DEMO_CAP_MICRO_USD,
                "remaining_synthetic_slot_count": 8 - len(self._used),
                "stopped": self._stopped,
                "states": [
                    {"case_id": case, "arm": arm, "state": item["state"]}
                    for (case, arm), item in sorted(self._used.items())
                ],
                "currency_contract_verified": False,
                "provider_charges_verified": False,
                "persistent_atomic_ledger": False,
                "crash_recovery_verified": False,
                "kernel_egress_isolation_verified": False,
                "model_generation_verified": False,
                "real_upstream_request_allowed": False,
                "real_usd_hard_cap_enforced": False,
                "specific_owner_spend_approval": False,
                "status": "IN_MEMORY_SYNTHETIC_ONLY_NOT_A_BROKER",
            }

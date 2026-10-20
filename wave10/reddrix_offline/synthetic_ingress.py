"""Synthetic-only in-process ingestion boundary and ephemeral retention selftest.

Does not expose a network API, authenticate a real user, access Reddit or a DB,
issue capabilities, or confer permission to use third-party source data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from offline_signal import Rejected, timestamp
from source_projection import project_synthetic_source

# A fixture assertion, NOT an authorization token or production IAM role.
EXACT_FIXTURE_CONTEXT = {
    "mode": "synthetic_offline_only",
    "actor": "synthetic-ci-harness",
    "purpose": "projection_contract_test",
    "source_id": "synthetic_legal_discussions",
    "transport": "in_process",
    "data_status": "invented",
    "network_allowed": False,
}
MAX_BATCH = 20
MAX_IN_MEMORY = 100


def check_fixture_context(context: dict[str, Any]) -> None:
    """Deny every unrecognised actor/source/purpose/mode, even if seemingly similar."""
    if type(context) is not dict or context != EXACT_FIXTURE_CONTEXT:
        raise Rejected("synthetic-only fixture context required")


def check_now(raw: str) -> datetime:
    value = timestamp(raw)
    if value.year < 2020 or value.year > 2100:
        raise Rejected("timestamp outside synthetic test range")
    return value


class SyntheticInbox:
    """Bounded ephemeral memory store, not a production ingestion or retention engine."""

    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def accept(self, events: list[dict], *, context: dict, now: str) -> dict:
        """All-or-nothing validation; store only metadata projections, never input texts."""
        check_fixture_context(context)
        observed = check_now(now)
        if type(events) is not list or not 1 <= len(events) <= MAX_BATCH:
            raise Rejected("invalid synthetic batch size")

        # Validate entire batch *before* any state modification.
        staged: dict[str, dict] = {}
        duplicates = 0
        for event in events:
            proposal = project_synthetic_source(event)
            if (proposal["write_authorized"] is not False
                    or proposal["runtime_compatibility_verified"] is not False):
                raise Rejected("projection must not claim runtime authority")
            if timestamp(event["captured_at"]) > observed:
                raise Rejected("event not yet captured")
            if timestamp(event["delete_after"]) <= observed:
                raise Rejected("expired fixture cannot be ingested")
            row = proposal["row"]
            key = row["external_id"]
            if key in staged or key in self._rows:
                duplicates += 1
            else:
                staged[key] = deepcopy(row)

        if len(self._rows) + len(staged) > MAX_IN_MEMORY:
            raise Rejected("synthetic in-memory storage cap exceeded")
        self._rows.update(staged)
        return {
            "schema": "panam.signal.synthetic-ingress-receipt.v1",
            "accepted": len(staged),
            "duplicates": duplicates,
            "stored": len(self._rows),
            "runtime_authorization_verified": False,
            "production_write_authorized": False,
            "persistent_retention_enforced": False,
            "data_mode": "synthetic_ephemeral_only",
        }

    def expire(self, *, context: dict, now: str) -> dict:
        """Explicit in-memory pruning only; no timer, persistent erasure or backup cleanup."""
        check_fixture_context(context)
        observed = check_now(now)
        keys = [
            key for key, row in self._rows.items()
            if timestamp(row["retention_until"]) <= observed
        ]
        for key in keys:
            del self._rows[key]
        return {
            "schema": "panam.signal.synthetic-retention-receipt.v1",
            "expired_in_memory": len(keys),
            "stored": len(self._rows),
            "persistent_deletion_verified": False,
            "production_effect": False,
        }

    def metadata_snapshot(self, *, context: dict) -> list[dict]:
        """Deep copies only: callers cannot modify internal state via the response."""
        check_fixture_context(context)
        return [deepcopy(self._rows[key]) for key in sorted(self._rows)]

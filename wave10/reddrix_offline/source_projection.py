"""Inert offline projection against repository-defined panam.sources column names.

Not a DB client, insert instruction, consent, or production schema approval.
Requires synthetic fixtures. Never writes, reads, or connects to any service.
"""
from __future__ import annotations

import re
from datetime import timedelta
from offline_signal import Rejected, safe_url, timestamp, isotime

ALLOWED_EVENT_FIELDS = frozenset({
    "schema", "record_key", "source_id", "source_url", "type", "published_at",
    "captured_at", "delete_after", "title", "body", "topics", "provenance",
})
ALLOWED_TOPICS = frozenset({"consumer", "contracts", "procurement", "employment", "housing"})
SOURCE_COLUMNS = frozenset({
    "source_type", "external_id", "title", "source_url", "authority", "occurred_at",
    "contains_personal_data", "retention_until", "metadata",
})


def project_synthetic_source(event: dict) -> dict:
    """Produce a comparison envelope with *no* plaintext or write authority."""
    if not isinstance(event, dict) or set(event) != ALLOWED_EVENT_FIELDS:
        raise Rejected("event shape mismatch")
    if event["schema"] != "panam.signal.v1" or event["source_id"] != "synthetic_legal_discussions":
        raise Rejected("unexpected event identity")
    if event["type"] not in ("post", "comment", "discussion"):
        raise Rejected("unexpected event type")
    key = event["record_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{24}", key):
        raise Rejected("invalid record key")
    if event["source_url"] != safe_url(event["source_url"], "forum.example.org"):
        raise Rejected("noncanonical URL")
    if not isinstance(event["title"], str) or not isinstance(event["body"], str):
        raise Rejected("invalid content fields")
    if len(event["title"]) > 250 or len(event["body"]) > 3000:
        raise Rejected("content over length limit")
    topics = event["topics"]
    if (not isinstance(topics, list) or any(not isinstance(t, str) for t in topics)
            or len(topics) != len(set(topics)) or set(topics) - ALLOWED_TOPICS):
        raise Rejected("unexpected topic tags")
    if event["provenance"] != {"kind": "synthetic_fixture", "document_ref": "PANAM-OFFLINE-2026-10-20"}:
        raise Rejected("non-synthetic provenance")
    published = timestamp(event["published_at"])
    captured = timestamp(event["captured_at"])
    expiry = timestamp(event["delete_after"])
    if not (published <= captured < expiry <= captured + timedelta(days=30)):
        raise Rejected("invalid synthetic lifecycle")

    row = {
        "source_type": "web",
        "external_id": "panam-synthetic-signal-v1:" + key,
        "title": None,  # deliberately excludes content
        "source_url": event["source_url"],
        "authority": "unknown",  # topic detection is not truth verification
        "occurred_at": isotime(published),
        "contains_personal_data": True,  # regex redaction is not anonymization
        "retention_until": isotime(expiry),  # metadata only; no expiry executor
        "metadata": {
            "projection_kind": "synthetic_schema_comparison_only",
            "signal_schema": "panam.signal.v1",
            "topics": sorted(topics),
            "event_type": event["type"],
            "origin": "synthetic_fixture",
            "retention_enforced": False,
        },
    }
    if set(row) != SOURCE_COLUMNS:
        raise AssertionError("unexpected projected columns")
    return {
        "projection_schema": "panam.sources.synthetic_projection.v1",
        "authoritative": False,
        "source_of_truth": False,
        "write_authorized": False,
        "runtime_compatibility_verified": False,
        "requires_separate_permission": True,
        "row": row,
    }

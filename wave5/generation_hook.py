from __future__ import annotations

import hashlib
import json
from copy import deepcopy

from wave4.storage_lineage import ALREADY_REGISTERED, REGISTERED, register_draft

SAVE_STATUS_STORED = "STORED"
DOCUMENT_TYPE = "meeting_record"
STORAGE_PROVIDER = "synthetic_store"
APPROVED_WORKFLOW_TRIGGER = "approved_workflow"

HOOK_REGISTERED = "LINEAGE_REGISTERED"
HOOK_ALREADY_PROCESSED = "ALREADY_PROCESSED"
HOOK_DRAFT_ALREADY_REGISTERED = "LINEAGE_ALREADY_REGISTERED"
HOOK_NOT_STORED = "NOT_REGISTERED_SAVE_INCOMPLETE"

IMMUTABLE_EVENT_FIELDS = (
    "event_id",
    "save_status",
    "document_type",
    "storage_provider",
    "draft_id",
    "artifact_id",
    "store_id",
    "storage_revision",
    "source_id",
    "correlation_id",
    "text_sha256",
    "stored_at",
)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not _nonempty(value):
        raise ValueError(f"{field} must be non-empty when supplied")
    return str(value)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_event_sha256(event: dict) -> str:
    material = {field: event.get(field) for field in IMMUTABLE_EVENT_FIELDS}
    payload = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def new_hook_registry() -> dict:
    return {
        "schema_version": 1,
        "policy": {
            "metadata_only": True,
            "meeting_record_only_v1": True,
            "successful_save_only": True,
            "approved_workflow_only": True,
            "raw_text_forbidden": True,
        },
        "processed_events": [],
    }


def validate_hook_registry(registry: dict) -> dict:
    if not isinstance(registry, dict):
        raise ValueError("hook registry must be an object")
    if registry.get("schema_version") != 1:
        raise ValueError("unsupported hook registry schema")
    events = registry.get("processed_events")
    if not isinstance(events, list):
        raise ValueError("processed_events must be an array")

    seen = set()
    for item in events:
        if not isinstance(item, dict):
            raise ValueError("processed event must be an object")
        event_id = item.get("event_id")
        if not _nonempty(event_id):
            raise ValueError("processed event missing event_id")
        if event_id in seen:
            raise ValueError("duplicate event_id")
        seen.add(event_id)
        if "text" in item or "content" in item or "raw_text" in item:
            raise ValueError("hook registry must not persist raw text")
        digest = item.get("event_sha256")
        if not _nonempty(digest) or len(digest) != 64:
            raise ValueError("processed event missing event_sha256")
        if digest != _canonical_event_sha256(item):
            raise ValueError("processed event metadata does not match event_sha256")
    return registry


def validate_save_receipt(receipt: dict) -> dict:
    if not isinstance(receipt, dict):
        raise ValueError("save receipt must be an object")
    for field in (
        "event_id",
        "save_status",
        "document_type",
        "storage_provider",
        "draft_id",
        "artifact_id",
    ):
        if not _nonempty(receipt.get(field)):
            raise ValueError(f"save receipt missing {field}")

    if receipt["document_type"] != DOCUMENT_TYPE:
        raise ValueError("Wave 5 accepts meeting_record receipts only")
    if receipt["storage_provider"] != STORAGE_PROVIDER:
        raise ValueError("Wave 5 accepts synthetic_store receipts only")

    if receipt["save_status"] == SAVE_STATUS_STORED:
        for field in ("store_id", "storage_revision", "text_sha256"):
            if not _nonempty(receipt.get(field)):
                raise ValueError(f"stored receipt missing {field}")
        digest = receipt["text_sha256"]
        if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
            raise ValueError("text_sha256 must be SHA-256 hex")
        source_id = _optional(receipt.get("source_id"), "source_id")
        correlation_id = _optional(receipt.get("correlation_id"), "correlation_id")
        if source_id is None and correlation_id is None:
            raise ValueError("stored receipt requires source_id or correlation_id")

    _optional(receipt.get("display_name"), "display_name")
    _optional(receipt.get("stored_at"), "stored_at")
    return receipt


def _event_entry(receipt: dict, *, hook_status: str, lineage_status: str | None) -> dict:
    return {
        "event_id": receipt["event_id"],
        "event_sha256": _canonical_event_sha256(receipt),
        "save_status": receipt["save_status"],
        "document_type": receipt["document_type"],
        "storage_provider": receipt["storage_provider"],
        "draft_id": receipt["draft_id"],
        "artifact_id": receipt["artifact_id"],
        "store_id": receipt.get("store_id"),
        "storage_revision": receipt.get("storage_revision"),
        "source_id": receipt.get("source_id"),
        "correlation_id": receipt.get("correlation_id"),
        "text_sha256": receipt.get("text_sha256"),
        "stored_at": receipt.get("stored_at"),
        "hook_status": hook_status,
        "lineage_status": lineage_status,
        "registration_trigger": APPROVED_WORKFLOW_TRIGGER,
    }


def _existing_event(registry: dict, receipt: dict) -> dict | None:
    matches = [
        item for item in registry["processed_events"]
        if item.get("event_id") == receipt["event_id"]
    ]
    if len(matches) > 1:
        raise ValueError("duplicate event_id")
    if not matches:
        return None
    existing = matches[0]
    if existing.get("event_sha256") != _canonical_event_sha256(receipt):
        raise ValueError("event_id already bound to different metadata")
    return existing


def process_save_event(
    receipt: dict,
    *,
    text: str | None,
    draft_registry: dict,
    hook_registry: dict,
) -> dict:
    validate_save_receipt(receipt)
    validate_hook_registry(hook_registry)

    existing = _existing_event(hook_registry, receipt)
    if existing is not None:
        return {
            "status": HOOK_ALREADY_PROCESSED,
            "event": deepcopy(existing),
            "draft_registry": deepcopy(draft_registry),
            "hook_registry": deepcopy(hook_registry),
        }

    if receipt["save_status"] != SAVE_STATUS_STORED:
        return {
            "status": HOOK_NOT_STORED,
            "reason": "SAVE_STATUS_IS_NOT_STORED",
            "draft_registry": deepcopy(draft_registry),
            "hook_registry": deepcopy(hook_registry),
        }

    if not isinstance(text, str) or not text.strip():
        raise ValueError("stored event requires non-empty text")
    if _sha256_text(text).lower() != receipt["text_sha256"].lower():
        raise ValueError("receipt text_sha256 does not match text")

    lineage = register_draft(
        draft_registry,
        draft_id=receipt["draft_id"],
        artifact_id=receipt["artifact_id"],
        store_id=receipt["store_id"],
        draft_text=text,
        source_id=receipt.get("source_id"),
        correlation_id=receipt.get("correlation_id"),
        display_name=receipt.get("display_name"),
        storage_revision=receipt.get("storage_revision"),
        document_type=DOCUMENT_TYPE,
        trigger_mode=APPROVED_WORKFLOW_TRIGGER,
    )

    if lineage["status"] == REGISTERED:
        hook_status = HOOK_REGISTERED
    elif lineage["status"] == ALREADY_REGISTERED:
        hook_status = HOOK_DRAFT_ALREADY_REGISTERED
    else:
        raise ValueError(f"unexpected Wave 4 status: {lineage['status']}")

    updated_hook = deepcopy(hook_registry)
    event = _event_entry(
        receipt,
        hook_status=hook_status,
        lineage_status=lineage["status"],
    )
    updated_hook["processed_events"].append(event)
    validate_hook_registry(updated_hook)

    return {
        "status": hook_status,
        "event": deepcopy(event),
        "draft_entry": deepcopy(lineage["entry"]),
        "draft_registry": lineage["registry"],
        "hook_registry": updated_hook,
    }

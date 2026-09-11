from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Callable

from wave5.generation_hook import (
    DOCUMENT_TYPE,
    HOOK_ALREADY_PROCESSED,
    HOOK_DRAFT_ALREADY_REGISTERED,
    HOOK_REGISTERED,
    SAVE_STATUS_STORED,
    STORAGE_PROVIDER,
    process_save_event,
    validate_save_receipt,
)

COMMITTED = "COMMITTED"
ALREADY_COMMITTED = "ALREADY_COMMITTED"
SAVE_NOT_STORED = "SAVE_NOT_STORED"
STORED_AWAITING_LINEAGE = "STORED_AWAITING_LINEAGE"
RECEIPT_CONFLICT_REQUIRES_REVIEW = "RECEIPT_CONFLICT_REQUIRES_REVIEW"

FINAL_HOOK_STATUSES = {
    HOOK_REGISTERED,
    HOOK_DRAFT_ALREADY_REGISTERED,
    HOOK_ALREADY_PROCESSED,
}

REQUEST_IDENTITY_FIELDS = (
    "operation_id", "event_id", "document_type", "storage_provider",
    "draft_id", "artifact_id", "source_id", "correlation_id", "text_sha256",
)
RECEIPT_MATCH_FIELDS = (
    "event_id", "document_type", "storage_provider", "draft_id",
    "artifact_id", "source_id", "correlation_id", "text_sha256",
)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_sha256(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def new_commit_registry() -> dict:
    return {
        "schema_version": 1,
        "policy": {
            "metadata_only": True,
            "stored_artifact_resume_without_reupload": True,
            "raw_text_forbidden": True,
        },
        "operations": [],
    }


def validate_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    for field in (
        "operation_id", "event_id", "document_type", "storage_provider",
        "draft_id", "artifact_id", "text_sha256",
    ):
        if not _nonempty(request.get(field)):
            raise ValueError(f"request missing {field}")
    if request["document_type"] != DOCUMENT_TYPE:
        raise ValueError("unsupported document_type")
    if request["storage_provider"] != STORAGE_PROVIDER:
        raise ValueError("unsupported storage_provider")
    digest = request["text_sha256"]
    if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
        raise ValueError("text_sha256 must be SHA-256 hex")
    if not (_nonempty(request.get("source_id")) or _nonempty(request.get("correlation_id"))):
        raise ValueError("request requires source_id or correlation_id")
    return request


def _request_sha(request: dict) -> str:
    return _canonical_sha256({f: request.get(f) for f in REQUEST_IDENTITY_FIELDS})


def _safe_receipt(receipt: dict) -> dict:
    fields = (
        "event_id", "save_status", "document_type", "storage_provider",
        "draft_id", "artifact_id", "store_id", "storage_revision", "source_id",
        "correlation_id", "text_sha256", "display_name", "stored_at",
    )
    return {field: receipt.get(field) for field in fields}


def _operation_sha(item: dict) -> str:
    return _canonical_sha256({
        "operation_id": item.get("operation_id"),
        "request_sha256": item.get("request_sha256"),
        "state": item.get("state"),
        "storage_receipt": item.get("storage_receipt"),
        "lineage_status": item.get("lineage_status"),
    })


def validate_commit_registry(registry: dict) -> dict:
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("invalid commit registry")
    operations = registry.get("operations")
    if not isinstance(operations, list):
        raise ValueError("operations must be an array")
    seen = set()
    for item in operations:
        op = item.get("operation_id") if isinstance(item, dict) else None
        if not _nonempty(op) or op in seen:
            raise ValueError("invalid or duplicate operation_id")
        seen.add(op)
        if any(key in item for key in ("text", "raw_text", "content")):
            raise ValueError("raw text forbidden")
        if item.get("operation_sha256") != _operation_sha(item):
            raise ValueError("operation metadata digest mismatch")
    return registry


def _find(registry: dict, operation_id: str):
    matches = [x for x in registry["operations"] if x.get("operation_id") == operation_id]
    if len(matches) > 1:
        raise ValueError("duplicate operation_id")
    return matches[0] if matches else None


def _put(registry: dict, item: dict, *, replace: bool = False) -> dict:
    updated = deepcopy(registry)
    item = deepcopy(item)
    item["operation_sha256"] = _operation_sha(item)
    if replace:
        matches = [i for i, x in enumerate(updated["operations"]) if x.get("operation_id") == item["operation_id"]]
        if len(matches) != 1:
            raise ValueError("operation replacement target missing")
        updated["operations"][matches[0]] = item
    else:
        updated["operations"].append(item)
    validate_commit_registry(updated)
    return updated


def _attempt(request: dict, state: str, receipt: dict | None = None, lineage_status: str | None = None) -> dict:
    return {
        "operation_id": request["operation_id"],
        "request_sha256": _request_sha(request),
        "state": state,
        "storage_receipt": deepcopy(receipt),
        "lineage_status": lineage_status,
    }


def _validate_receipt(receipt: dict, request: dict) -> None:
    validate_save_receipt(receipt)
    conflicts = [f for f in RECEIPT_MATCH_FIELDS if receipt.get(f) != request.get(f)]
    if conflicts:
        raise ValueError("receipt/request mismatch: " + ", ".join(conflicts))


def _finish(request: dict, text: str, receipt: dict, draft_registry: dict, hook_registry: dict, commit_registry: dict) -> dict:
    try:
        hook = process_save_event(
            receipt,
            text=text,
            draft_registry=draft_registry,
            hook_registry=hook_registry,
        )
    except Exception:
        return {
            "status": STORED_AWAITING_LINEAGE,
            "reason": "LINEAGE_FAILED_RETRY_WITHOUT_REUPLOAD",
            "draft_registry": deepcopy(draft_registry),
            "hook_registry": deepcopy(hook_registry),
            "commit_registry": deepcopy(commit_registry),
        }
    if hook.get("status") not in FINAL_HOOK_STATUSES:
        return {
            "status": STORED_AWAITING_LINEAGE,
            "reason": "LINEAGE_NOT_FINAL",
            "draft_registry": hook.get("draft_registry", deepcopy(draft_registry)),
            "hook_registry": hook.get("hook_registry", deepcopy(hook_registry)),
            "commit_registry": deepcopy(commit_registry),
        }
    current = _find(commit_registry, request["operation_id"])
    completed = dict(current)
    completed["state"] = COMMITTED
    completed["lineage_status"] = hook["status"]
    return {
        "status": COMMITTED,
        "lineage_status": hook["status"],
        "draft_registry": hook["draft_registry"],
        "hook_registry": hook["hook_registry"],
        "commit_registry": _put(commit_registry, completed, replace=True),
    }


def commit_artifact(
    request: dict,
    *,
    text: str,
    storage_writer: Callable[[dict, str], dict],
    draft_registry: dict,
    hook_registry: dict,
    commit_registry: dict,
) -> dict:
    validate_request(request)
    validate_commit_registry(commit_registry)
    if not callable(storage_writer):
        raise ValueError("storage_writer must be callable")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be non-empty")
    if _sha256_text(text).lower() != request["text_sha256"].lower():
        raise ValueError("request text_sha256 does not match text")

    existing = _find(commit_registry, request["operation_id"])
    if existing is not None:
        if existing["request_sha256"] != _request_sha(request):
            raise ValueError("operation_id rebound to different request")
        if existing["state"] == COMMITTED:
            return {
                "status": ALREADY_COMMITTED,
                "draft_registry": deepcopy(draft_registry),
                "hook_registry": deepcopy(hook_registry),
                "commit_registry": deepcopy(commit_registry),
            }
        if existing["state"] == STORED_AWAITING_LINEAGE:
            return _finish(
                request, text, existing["storage_receipt"],
                draft_registry, hook_registry, commit_registry,
            )
        if existing["state"] in {SAVE_NOT_STORED, RECEIPT_CONFLICT_REQUIRES_REVIEW}:
            return {
                "status": existing["state"],
                "draft_registry": deepcopy(draft_registry),
                "hook_registry": deepcopy(hook_registry),
                "commit_registry": deepcopy(commit_registry),
            }
        raise ValueError("unsupported existing state")

    receipt = storage_writer(deepcopy(request), text)
    if not isinstance(receipt, dict):
        raise ValueError("storage_writer must return object")
    try:
        _validate_receipt(receipt, request)
    except ValueError:
        safe = _safe_receipt(receipt)
        updated = _put(commit_registry, _attempt(request, RECEIPT_CONFLICT_REQUIRES_REVIEW, safe))
        return {
            "status": RECEIPT_CONFLICT_REQUIRES_REVIEW,
            "draft_registry": deepcopy(draft_registry),
            "hook_registry": deepcopy(hook_registry),
            "commit_registry": updated,
        }

    safe = _safe_receipt(receipt)
    if receipt["save_status"] != SAVE_STATUS_STORED:
        updated = _put(commit_registry, _attempt(request, SAVE_NOT_STORED, safe))
        return {
            "status": SAVE_NOT_STORED,
            "draft_registry": deepcopy(draft_registry),
            "hook_registry": deepcopy(hook_registry),
            "commit_registry": updated,
        }

    checkpoint = _put(commit_registry, _attempt(request, STORED_AWAITING_LINEAGE, safe))
    return _finish(request, text, safe, draft_registry, hook_registry, checkpoint)

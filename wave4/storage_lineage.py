from __future__ import annotations

from copy import deepcopy

from wave3.intake import (
    INTEGRITY_CONFLICT,
    MATCHED,
    process_intake,
    resolve_draft,
    sha256_text,
    validate_registry,
)

REGISTERED = "REGISTERED"
ALREADY_REGISTERED = "ALREADY_REGISTERED"

ALLOWED_TRIGGER_MODES = {
    "owner_explicit",
    "approved_workflow",
    "manual_operator",
}

IDENTITY_FIELDS = (
    "status",
    "draft_id",
    "document_type",
    "artifact_id",
    "store_id",
    "source_id",
    "correlation_id",
    "text_sha256",
    "storage_revision",
)


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _optional(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not _nonempty(value):
        raise ValueError(f"{field} must be non-empty when supplied")
    return str(value)


def validate_trigger_mode(trigger_mode: str) -> str:
    if trigger_mode not in ALLOWED_TRIGGER_MODES:
        raise ValueError(f"trigger mode is not authorized: {trigger_mode}")
    return trigger_mode


def register_draft(
    registry: dict,
    *,
    draft_id: str,
    artifact_id: str,
    store_id: str,
    draft_text: str,
    source_id: str | None = None,
    correlation_id: str | None = None,
    display_name: str | None = None,
    storage_revision: str | None = None,
    document_type: str = "meeting_record",
    trigger_mode: str = "owner_explicit",
) -> dict:
    validate_trigger_mode(trigger_mode)
    validate_registry(registry)
    for field, value in (
        ("draft_id", draft_id),
        ("artifact_id", artifact_id),
        ("store_id", store_id),
        ("document_type", document_type),
    ):
        if not _nonempty(value):
            raise ValueError(f"{field} is required")
    if not isinstance(draft_text, str) or not draft_text.strip():
        raise ValueError("draft_text must be non-empty")

    entry = {
        "status": "SYNTHETIC_DRAFT",
        "draft_id": draft_id,
        "document_type": document_type,
        "artifact_id": artifact_id,
        "store_id": store_id,
        "source_id": _optional(source_id, "source_id"),
        "correlation_id": _optional(correlation_id, "correlation_id"),
        "text_sha256": sha256_text(draft_text),
        "display_name": _optional(display_name, "display_name"),
        "storage_revision": _optional(storage_revision, "storage_revision"),
        "registration_trigger": trigger_mode,
    }

    drafts = registry["drafts"]
    same = [d for d in drafts if d.get("draft_id") == draft_id]
    if len(same) > 1:
        raise ValueError("duplicate draft_id already exists")
    if same:
        existing = same[0]
        conflicts = [f for f in IDENTITY_FIELDS if existing.get(f) != entry.get(f)]
        if conflicts:
            raise ValueError("draft_id immutable metadata conflict: " + ", ".join(conflicts))
        return {
            "status": ALREADY_REGISTERED,
            "entry": deepcopy(existing),
            "registry": deepcopy(registry),
        }

    for existing in drafts:
        if existing.get("store_id") == store_id:
            raise ValueError("store_id is already bound to another draft")
        if existing.get("artifact_id") == artifact_id:
            raise ValueError("artifact_id is already bound to another draft")

    updated = deepcopy(registry)
    updated["drafts"].append(entry)
    validate_registry(updated)
    return {"status": REGISTERED, "entry": deepcopy(entry), "registry": updated}


def normalize_snapshot(
    *,
    provider: str,
    store_id: str,
    text: str,
    expected_store_id: str | None = None,
    storage_revision: str | None = None,
) -> dict:
    if not _nonempty(provider):
        raise ValueError("provider is required")
    if not _nonempty(store_id):
        raise ValueError("store_id is required")
    if expected_store_id is not None and store_id != expected_store_id:
        raise ValueError("store_id does not match expected_store_id")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be non-empty")
    return {
        "schema_version": 1,
        "provider": provider,
        "store_id": store_id,
        "storage_revision": _optional(storage_revision, "storage_revision"),
        "text_sha256": sha256_text(text),
        "text": text,
        "persistence": "EPHEMERAL_DO_NOT_PERSIST_IN_METADATA_REGISTRY",
    }


def prepare_intake_from_storage(
    request: dict,
    draft_registry: dict,
    reference_registry: dict,
    *,
    draft_snapshot: dict | None,
    final_snapshot: dict | None,
    trigger_mode: str = "owner_explicit",
) -> dict:
    validate_trigger_mode(trigger_mode)
    validate_registry(draft_registry)

    match = resolve_draft(request, draft_registry)
    if match.get("status") != MATCHED:
        return process_intake(request, draft_registry, reference_registry)

    if draft_snapshot is None or final_snapshot is None:
        return process_intake(request, draft_registry, reference_registry)

    draft = match["draft"]
    expected_draft_store = draft.get("store_id")
    if not _nonempty(expected_draft_store):
        return {
            "schema_version": 1,
            "intake_id": request.get("intake_id"),
            "intake_state": INTEGRITY_CONFLICT,
            "reason": "DRAFT_STORAGE_IDENTITY_MISSING",
        }
    if draft_snapshot.get("store_id") != expected_draft_store:
        return {
            "schema_version": 1,
            "intake_id": request.get("intake_id"),
            "intake_state": INTEGRITY_CONFLICT,
            "reason": "DRAFT_STORAGE_ID_MISMATCH",
        }
    if draft_snapshot.get("text_sha256") != draft.get("text_sha256"):
        return {
            "schema_version": 1,
            "intake_id": request.get("intake_id"),
            "intake_state": INTEGRITY_CONFLICT,
            "reason": "DRAFT_STORAGE_TEXT_SHA256_MISMATCH",
        }
    if final_snapshot.get("store_id") != request.get("reference_store_id"):
        return {
            "schema_version": 1,
            "intake_id": request.get("intake_id"),
            "intake_state": INTEGRITY_CONFLICT,
            "reason": "FINAL_STORAGE_ID_MISMATCH",
        }

    draft_text = draft_snapshot.get("text")
    final_text = final_snapshot.get("text")
    if not isinstance(draft_text, str) or not draft_text.strip():
        raise ValueError("draft snapshot missing ephemeral text")
    if not isinstance(final_text, str) or not final_text.strip():
        raise ValueError("final snapshot missing ephemeral text")

    return process_intake(
        request,
        draft_registry,
        reference_registry,
        draft_text=draft_text,
        final_text=final_text,
    )

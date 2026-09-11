from __future__ import annotations

import hashlib
from copy import deepcopy

from wave2.document_learning import build_revision_pair, validate_reference

DRAFT_STATUS = "SYNTHETIC_DRAFT"
FINAL_STATUS = "APPROVED_FINAL"

MATCHED = "MATCHED"
UNPAIRED = "UNPAIRED"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
AWAITING_REFERENCE = "AWAITING_REFERENCE"
AWAITING_TEXT = "AWAITING_TEXT"
INTEGRITY_CONFLICT = "INTEGRITY_CONFLICT"
READY_FOR_CHANGE_REVIEW = "READY_FOR_CHANGE_REVIEW"

MATCH_KEYS = ("draft_id_hint", "correlation_id", "source_id")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_draft(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("draft must be an object")
    if entry.get("status") != DRAFT_STATUS:
        raise ValueError("draft status must be SYNTHETIC_DRAFT")
    for field in ("draft_id", "document_type", "artifact_id", "text_sha256"):
        if not _nonempty(entry.get(field)):
            raise ValueError(f"draft missing {field}")
    for field in ("source_id", "correlation_id"):
        if entry.get(field) is not None and not _nonempty(entry[field]):
            raise ValueError(f"{field} must be non-empty when supplied")
    return entry


def validate_registry(registry: dict) -> dict:
    drafts = registry.get("drafts")
    if not isinstance(drafts, list):
        raise ValueError("drafts must be an array")
    ids = set()
    for draft in drafts:
        validate_draft(draft)
        if draft["draft_id"] in ids:
            raise ValueError("duplicate draft_id")
        ids.add(draft["draft_id"])
    return registry


def validate_request(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("request must be an object")
    for field in ("intake_id", "document_type", "reference_id", "reference_store_id"):
        if not _nonempty(request.get(field)):
            raise ValueError(f"request missing {field}")
    if request.get("final_status") != FINAL_STATUS:
        raise ValueError("final_status must be APPROVED_FINAL")
    if not any(_nonempty(request.get(key)) for key in MATCH_KEYS):
        raise ValueError("at least one exact linkage key is required")
    return request


def _result(request: dict, status: str, reason: str, *, draft=None, candidates=None, basis=None):
    out = {
        "schema_version": 1,
        "intake_id": request["intake_id"],
        "status": status,
        "reason": reason,
        "match_basis": basis or [],
    }
    if draft is not None:
        out["draft"] = deepcopy(draft)
    if candidates is not None:
        out["candidate_draft_ids"] = [item["draft_id"] for item in candidates]
    return out


def resolve_draft(request: dict, registry: dict) -> dict:
    validate_request(request)
    validate_registry(registry)
    drafts = registry["drafts"]
    same_type = [d for d in drafts if d["document_type"] == request["document_type"]]

    selectors = []
    if _nonempty(request.get("draft_id_hint")):
        selectors.append(("draft_id_hint", "draft_id", request["draft_id_hint"]))
    if _nonempty(request.get("correlation_id")):
        selectors.append(("correlation_id", "correlation_id", request["correlation_id"]))
    if _nonempty(request.get("source_id")):
        selectors.append(("source_id", "source_id", request["source_id"]))

    if _nonempty(request.get("draft_id_hint")):
        hinted = [d for d in drafts if d["draft_id"] == request["draft_id_hint"]]
        if len(hinted) == 1 and hinted[0]["document_type"] != request["document_type"]:
            return _result(request, REVIEW_REQUIRED, "DOCUMENT_TYPE_CONFLICT", candidates=hinted, basis=["draft_id_hint"])

    matched = same_type
    individual = []
    for _, field, value in selectors:
        individual.append({d["draft_id"] for d in same_type if d.get(field) == value})
        matched = [d for d in matched if d.get(field) == value]

    basis = [x[0] for x in selectors]
    if len(matched) == 1:
        return _result(request, MATCHED, "EXACT_UNIQUE_MATCH", draft=matched[0], basis=basis)
    if len(matched) > 1:
        return _result(request, REVIEW_REQUIRED, "AMBIGUOUS_EXACT_MATCH", candidates=matched, basis=basis)

    hits = [s for s in individual if s]
    if len(hits) >= 2 and not set.intersection(*hits):
        ids = set().union(*hits)
        candidates = [d for d in same_type if d["draft_id"] in ids]
        return _result(request, REVIEW_REQUIRED, "LINKAGE_CONFLICT", candidates=candidates, basis=basis)

    if _nonempty(request.get("draft_id_hint")):
        hinted = [d for d in same_type if d["draft_id"] == request["draft_id_hint"]]
        if hinted:
            return _result(request, REVIEW_REQUIRED, "LINKAGE_CONFLICT", candidates=hinted, basis=basis)

    return _result(request, UNPAIRED, "NO_EXACT_MATCH", candidates=[], basis=basis)


def _lookup_reference(reference_registry: dict, reference_id: str):
    refs = reference_registry.get("references")
    if not isinstance(refs, list):
        return "REGISTRY_INVALID", None
    matches = [r for r in refs if r.get("reference_id") == reference_id]
    if not matches:
        return "NOT_REGISTERED", None
    if len(matches) > 1:
        return "REGISTRY_CONFLICT", None
    ref = matches[0]
    if ref.get("status") != "APPROVED_REFERENCE":
        return str(ref.get("status") or "NOT_APPROVED"), ref
    try:
        validate_reference(ref)
    except ValueError:
        return "REGISTRY_CONFLICT", ref
    if not _nonempty(ref.get("store_id")):
        return "REGISTRY_CONFLICT", ref
    return "APPROVED_REFERENCE", ref


def process_intake(request: dict, draft_registry: dict, reference_registry: dict, *, draft_text=None, final_text=None) -> dict:
    match = resolve_draft(request, draft_registry)
    if match["status"] != MATCHED:
        return {**match, "intake_state": match["status"]}

    out = {
        "schema_version": 1,
        "intake_id": request["intake_id"],
        "match": match,
    }
    state, reference = _lookup_reference(reference_registry, request["reference_id"])
    if state != "APPROVED_REFERENCE":
        out.update({"intake_state": AWAITING_REFERENCE, "reference_state": state})
        return out

    assert reference is not None
    if reference["store_id"] != request["reference_store_id"]:
        out.update({"intake_state": INTEGRITY_CONFLICT, "reason": "REFERENCE_STORE_ID_MISMATCH"})
        return out
    if draft_text is None or final_text is None:
        out.update({"intake_state": AWAITING_TEXT, "reason": "CONTENT_NOT_SUPPLIED"})
        return out

    draft = match["draft"]
    if sha256_text(draft_text) != draft["text_sha256"]:
        out.update({"intake_state": INTEGRITY_CONFLICT, "reason": "DRAFT_TEXT_SHA256_MISMATCH"})
        return out

    pair = build_revision_pair(
        draft_text,
        final_text,
        pair_id=request.get("pair_id") or f"PAIR-{request['intake_id']}",
        draft_id=draft["draft_id"],
        final_reference=reference,
        document_type=request["document_type"],
    )
    out.update({
        "intake_state": READY_FOR_CHANGE_REVIEW,
        "revision_pair": pair,
        "review_queue": [
            {
                "change_index": i,
                "kind": change["kind"],
                "classification": change["classification"],
            }
            for i, change in enumerate(pair["changes"])
        ],
    })
    return out


def new_metrics() -> dict:
    states = [UNPAIRED, REVIEW_REQUIRED, AWAITING_REFERENCE, AWAITING_TEXT, INTEGRITY_CONFLICT, READY_FOR_CHANGE_REVIEW]
    return {
        "schema_version": 1,
        "total": 0,
        "state_counts": {state: 0 for state in states},
        "prepared_pairs": 0,
        "processed_intake_ids": [],
    }


def update_metrics(metrics: dict, outcome: dict) -> dict:
    if metrics.get("schema_version") != 1:
        raise ValueError("unsupported metrics schema")
    intake_id = outcome.get("intake_id")
    if not _nonempty(intake_id):
        raise ValueError("missing intake_id")
    if intake_id in metrics.get("processed_intake_ids", []):
        raise ValueError("intake already counted")
    state = outcome.get("intake_state") or outcome.get("status")
    if state not in metrics.get("state_counts", {}):
        raise ValueError("unknown intake state")
    result = deepcopy(metrics)
    result["processed_intake_ids"].append(intake_id)
    result["total"] += 1
    result["state_counts"][state] += 1
    if isinstance(outcome.get("revision_pair"), dict):
        result["prepared_pairs"] += 1
    return result

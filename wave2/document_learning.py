from __future__ import annotations

import hashlib
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Iterable

LEARNABLE_CATEGORIES = {
    "structure",
    "wording",
    "compression_detail",
    "decision_phrasing",
    "responsible_deadline_formatting",
    "exclusion",
    "style_grammar",
}

BLOCKED_CATEGORIES = {"factual_legal_substantive"}
ALL_REVIEW_CATEGORIES = LEARNABLE_CATEGORIES | BLOCKED_CATEGORIES
MIN_DISTINCT_REFERENCE_EVIDENCE = 3


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def validate_reference(record: dict) -> dict:
    """Validate an exact, reviewed synthetic reference record.

    The public lab deliberately models only generic metadata. It has no access to
    private repositories, document stores, users, services or production systems.
    """
    if not isinstance(record, dict):
        raise ValueError("reference record must be an object")
    if record.get("status") != "APPROVED_REFERENCE":
        raise ValueError("final document is not an approved reference")
    for field in ("reference_id", "content_sha256", "review_receipt_sha256"):
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"reference record is missing required field: {field}")
    if not _is_sha256(record["content_sha256"]):
        raise ValueError("content_sha256 must be a SHA-256 hex digest")
    if not _is_sha256(record["review_receipt_sha256"]):
        raise ValueError("review_receipt_sha256 must be a SHA-256 hex digest")
    return record


def _split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def build_revision_pair(
    draft_text: str,
    final_text: str,
    *,
    pair_id: str,
    draft_id: str,
    final_reference: dict,
    document_type: str,
) -> dict:
    """Build a deterministic draft-to-approved-final diff.

    Every edit is unclassified by default. Textual difference is evidence that a
    change happened, not evidence of why it happened or whether it is reusable.
    """
    if not pair_id or not draft_id or not document_type:
        raise ValueError("pair_id, draft_id and document_type are required")
    reference = validate_reference(final_reference)
    if sha256_text(final_text) != reference["content_sha256"]:
        raise ValueError("final text does not match the approved reference digest")

    draft_lines = _split_lines(draft_text)
    final_lines = _split_lines(final_text)
    matcher = SequenceMatcher(a=draft_lines, b=final_lines, autojunk=False)

    changes: list[dict] = []
    counts = {"replace": 0, "delete": 0, "insert": 0}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        counts[tag] += 1
        changes.append(
            {
                "kind": tag,
                "draft_range": [i1, i2],
                "final_range": [j1, j2],
                "before": draft_lines[i1:i2],
                "after": final_lines[j1:j2],
                "classification": "UNCLASSIFIED_REQUIRES_REVIEW",
            }
        )

    return {
        "schema_version": 1,
        "pair_id": pair_id,
        "document_type": document_type,
        "draft": {"draft_id": draft_id, "content_sha256": sha256_text(draft_text)},
        "final": {
            "reference_id": reference["reference_id"],
            "content_sha256": reference["content_sha256"],
            "review_receipt_sha256": reference["review_receipt_sha256"],
            "status": reference["status"],
        },
        "metrics": {
            "line_similarity_ratio": round(matcher.ratio(), 6),
            "changed_blocks": len(changes),
            "replace_blocks": counts["replace"],
            "delete_blocks": counts["delete"],
            "insert_blocks": counts["insert"],
        },
        "changes": changes,
        "learning_state": "REVIEW_REQUIRED",
    }


def classify_change(pair: dict, change_index: int, *, category: str, manual_verified: bool) -> dict:
    """Return a reviewed copy of a revision pair with one change classified."""
    if category not in ALL_REVIEW_CATEGORIES:
        raise ValueError("unknown change category")
    if manual_verified is not True:
        raise ValueError("manual verification is required")
    changes = pair.get("changes")
    if not isinstance(changes, list) or not (0 <= change_index < len(changes)):
        raise ValueError("change_index does not identify a change")

    result = deepcopy(pair)
    result["changes"][change_index]["classification"] = category
    result["changes"][change_index]["manual_verified"] = True
    if result["changes"] and all(
        change.get("classification") in ALL_REVIEW_CATEGORIES
        and change.get("manual_verified") is True
        for change in result["changes"]
    ):
        result["learning_state"] = "REVIEWED"
    return result


def qualify_revision_pair(pair: dict, approved_references: dict[str, dict]) -> dict:
    """Validate a reviewed pair against the exact approved synthetic reference."""
    if not isinstance(pair, dict):
        raise ValueError("revision pair must be an object")
    pair_id = pair.get("pair_id")
    if not isinstance(pair_id, str) or not pair_id.strip():
        raise ValueError("revision pair is missing pair_id")
    if pair.get("learning_state") != "REVIEWED":
        raise ValueError("revision pair is not fully reviewed")

    final = pair.get("final")
    if not isinstance(final, dict):
        raise ValueError("revision pair final metadata is missing")
    reference_id = final.get("reference_id")
    reference = approved_references.get(reference_id)
    if reference is None:
        raise ValueError("revision pair reference is not in the approved reference set")
    reference = validate_reference(reference)

    expected = {
        "content_sha256": reference["content_sha256"],
        "review_receipt_sha256": reference["review_receipt_sha256"],
        "status": reference["status"],
    }
    for field, value in expected.items():
        if final.get(field) != value:
            raise ValueError(f"revision pair reference provenance mismatch: {field}")

    draft = pair.get("draft")
    if not isinstance(draft, dict) or not _is_sha256(draft.get("content_sha256")):
        raise ValueError("revision pair draft content_sha256 is invalid")

    changes = pair.get("changes")
    if not isinstance(changes, list) or not changes:
        raise ValueError("revision pair has no reviewed changes")
    for change in changes:
        if change.get("classification") not in ALL_REVIEW_CATEGORIES:
            raise ValueError("revision pair contains an unclassified change")
        if change.get("manual_verified") is not True:
            raise ValueError("revision pair contains an unverified change")
    return pair


def qualified_pair_ids(pairs: Iterable[dict], approved_references: dict[str, dict]) -> set[str]:
    """Return IDs only after every pair passes reviewed-reference qualification."""
    ids: set[str] = set()
    for pair in pairs:
        qualified = qualify_revision_pair(pair, approved_references)
        pair_id = qualified["pair_id"]
        if pair_id in ids:
            raise ValueError(f"duplicate revision pair id: {pair_id}")
        ids.add(pair_id)
    return ids


def can_accept_rule(candidate: dict, qualified_pair_ids: Iterable[str]) -> tuple[bool, list[str]]:
    """Fail closed unless a reusable rule satisfies the public Wave 2 contract."""
    reasons: list[str] = []
    category = candidate.get("category")

    for field in ("rule_id", "before_pattern", "after_pattern"):
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            reasons.append(f"{field} must be a non-empty string")

    before = candidate.get("before_pattern")
    after = candidate.get("after_pattern")
    if isinstance(before, str) and isinstance(after, str) and before.strip() == after.strip():
        reasons.append("before_pattern and after_pattern must differ")

    if candidate.get("status") != "CANDIDATE":
        reasons.append("status must be CANDIDATE")
    if category in BLOCKED_CATEGORIES:
        reasons.append("factual/legal/substantive corrections are not reusable style rules")
    elif category not in LEARNABLE_CATEGORIES:
        reasons.append("category is not a recognized learnable category")
    if candidate.get("manual_verified") is not True:
        reasons.append("manual verification is required")

    evidence = candidate.get("evidence_pair_ids")
    if not isinstance(evidence, list):
        reasons.append("evidence_pair_ids must be an array")
        evidence_ids: set[str] = set()
    else:
        evidence_ids = {value for value in evidence if isinstance(value, str) and value}
        if len(evidence_ids) < MIN_DISTINCT_REFERENCE_EVIDENCE:
            reasons.append(
                f"at least {MIN_DISTINCT_REFERENCE_EVIDENCE} distinct approved revision pairs are required"
            )

    qualified = set(qualified_pair_ids)
    if evidence_ids - qualified:
        reasons.append("all evidence pairs must be qualified approved-reference pairs")

    contradictions = candidate.get("contradiction_count")
    if not isinstance(contradictions, int) or isinstance(contradictions, bool) or contradictions != 0:
        reasons.append("contradiction_count must be integer zero")

    return not reasons, reasons


def accept_rule(candidate: dict, qualified_pair_ids: Iterable[str]) -> dict:
    allowed, reasons = can_accept_rule(candidate, qualified_pair_ids)
    if not allowed:
        raise ValueError("rule acceptance refused: " + "; ".join(reasons))
    result = deepcopy(candidate)
    result["status"] = "ACCEPTED"
    result["acceptance_policy"] = {
        "version": 1,
        "minimum_distinct_reference_evidence": MIN_DISTINCT_REFERENCE_EVIDENCE,
        "manual_verification_required": True,
        "zero_contradictions_required": True,
        "blocked_categories": sorted(BLOCKED_CATEGORIES),
        "reviewed_pair_qualification_required": True,
    }
    return result


def accept_rule_from_pairs(
    candidate: dict,
    revision_pairs: Iterable[dict],
    approved_references: dict[str, dict],
) -> dict:
    """Preferred fail-closed path from reviewed pair objects."""
    return accept_rule(candidate, qualified_pair_ids(revision_pairs, approved_references))

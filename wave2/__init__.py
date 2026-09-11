"""Public synthetic Document Learning contract."""

from .document_learning import (
    BLOCKED_CATEGORIES,
    LEARNABLE_CATEGORIES,
    MIN_DISTINCT_REFERENCE_EVIDENCE,
    accept_rule,
    accept_rule_from_pairs,
    build_revision_pair,
    can_accept_rule,
    classify_change,
    qualified_pair_ids,
    qualify_revision_pair,
    sha256_text,
    validate_reference,
)

__all__ = [
    "BLOCKED_CATEGORIES",
    "LEARNABLE_CATEGORIES",
    "MIN_DISTINCT_REFERENCE_EVIDENCE",
    "accept_rule",
    "accept_rule_from_pairs",
    "build_revision_pair",
    "can_accept_rule",
    "classify_change",
    "qualified_pair_ids",
    "qualify_revision_pair",
    "sha256_text",
    "validate_reference",
]

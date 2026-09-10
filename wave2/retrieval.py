from __future__ import annotations


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for index, item_id in enumerate(ranked_ids, start=1):
        if item_id in relevant_ids:
            return 1.0 / index
    return 0.0


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be >= 1")
    if not relevant_ids:
        return 1.0
    hits = len(set(ranked_ids[:k]) & relevant_ids)
    return hits / len(relevant_ids)


def mean_reciprocal_rank(cases: list[tuple[list[str], set[str]]]) -> float:
    if not cases:
        raise ValueError("at least one case is required")
    return sum(reciprocal_rank(ranked, relevant) for ranked, relevant in cases) / len(cases)

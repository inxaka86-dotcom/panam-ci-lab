from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Observation:
    candidate: str
    exact_match: bool
    freshness: float
    confidence: float
    retry_count: int = 0


def attribution_score(item: Observation) -> float:
    """Deterministic synthetic attribution score in [0, 1]."""
    freshness = min(max(float(item.freshness), 0.0), 1.0)
    confidence = min(max(float(item.confidence), 0.0), 1.0)
    exact = 1.0 if item.exact_match else 0.0
    retry_penalty = min(max(int(item.retry_count), 0), 5) * 0.03
    score = (0.50 * exact) + (0.30 * confidence) + (0.20 * freshness) - retry_penalty
    return round(min(max(score, 0.0), 1.0), 6)


def choose_candidate(items: list[Observation]) -> Observation | None:
    if not items:
        return None
    return max(items, key=lambda x: (attribution_score(x), x.candidate))

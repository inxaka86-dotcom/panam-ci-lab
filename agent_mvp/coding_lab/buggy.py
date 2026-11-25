"""Tiny isolated coding challenge for autonomous PANAM Agent verification."""


def priority_bucket(score: int) -> str:
    """Return low for <5, medium for 5..9, and high for >=10."""
    if score < 5:
        return "low"
    if score < 10:
        return "medium"
    return "high"

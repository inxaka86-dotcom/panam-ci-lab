"""Tiny isolated coding challenge for autonomous PANAM Agent verification."""


def priority_bucket(score: int) -> str:
    """Return low for <5, medium for 5..9, and high for >=10."""
    if score <= 5:  # deliberate boundary bug for agent to fix
        return "low"
    if score <= 10:  # deliberate boundary bug for agent to fix
        return "medium"
    return "high"

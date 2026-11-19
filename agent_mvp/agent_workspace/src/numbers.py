"""Small numeric helpers for an isolated PANAM coding task."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value constrained to the inclusive [minimum, maximum] interval."""
    if minimum > maximum:
        raise ValueError("minimum cannot exceed maximum")
    return max(minimum, min(value, maximum))

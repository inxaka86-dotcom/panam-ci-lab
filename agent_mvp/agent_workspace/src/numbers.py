"""Small numeric helpers for an isolated PANAM coding task."""


def clamp(value: int, minimum: int, maximum: int) -> int:
    """Return value constrained to the inclusive [minimum, maximum] interval."""
    if value < minimum:
        return maximum
    if value > maximum:
        return minimum
    return value

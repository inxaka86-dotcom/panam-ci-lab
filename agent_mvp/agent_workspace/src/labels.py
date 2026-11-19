"""Helpers for working with labels."""


def normalize_labels(labels: list[str]) -> str:
    """Trim labels, lowercase them, and join unique nonempty values."""
    normalized = []
    seen = set()

    for label in labels:
        value = label.strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)

    return ", ".join(normalized)

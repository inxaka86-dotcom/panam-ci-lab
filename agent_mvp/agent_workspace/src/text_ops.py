"""Small text helpers for an isolated PANAM coding task."""


def slugify(text: str) -> str:
    """Convert text into a lowercase ASCII hyphenated slug."""
    return text.lower().replace(" ", "-")

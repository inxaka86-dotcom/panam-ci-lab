"""Small text helpers for an isolated PANAM coding task."""

import re
import unicodedata


def slugify(text: str) -> str:
    """Convert text into a lowercase ASCII hyphenated slug."""
    # Normalize accents into base characters, then discard remaining non-ASCII
    # marks while converting punctuation and whitespace runs to one separator.
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower())
    return slug.strip("-")

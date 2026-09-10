from __future__ import annotations

import re


_DOUBLE_SPACE = re.compile(r" {2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
_DUPLICATE_WORD = re.compile(r"\b([A-Za-zА-Яа-яЁё]+)\s+\1\b", re.IGNORECASE)


def normalize_spacing(text: str) -> str:
    text = _DOUBLE_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return text.strip()


def diagnostics(text: str) -> tuple[str, ...]:
    issues: list[str] = []
    if _DOUBLE_SPACE.search(text):
        issues.append("DOUBLE_SPACE")
    if _SPACE_BEFORE_PUNCT.search(text):
        issues.append("SPACE_BEFORE_PUNCTUATION")
    if _DUPLICATE_WORD.search(text):
        issues.append("DUPLICATE_WORD")
    return tuple(issues)


def exact_correction_score(source: str, expected: str) -> float:
    return 1.0 if normalize_spacing(source) == expected else 0.0

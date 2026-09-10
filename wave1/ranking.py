from __future__ import annotations

import math
import re
from collections import Counter


def tokens(text: str) -> list[str]:
    return [x for x in re.findall(r"[^\W_]+", str(text).lower(), flags=re.UNICODE) if len(x) >= 2]


def score_documents(query: str, documents: list[str]) -> list[float]:
    q = sorted(set(tokens(query)))
    docs = [tokens(text) for text in documents]
    n = max(1, len(docs))
    df = {term: sum(term in set(doc) for doc in docs) for term in q}
    out = []
    for doc in docs:
        counts = Counter(doc)
        score = 0.0
        for term in q:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1.0 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf
        out.append(score)
    return out


def promote_one(original: list[str], preferred_order: list[str], *, protected: int = 3) -> list[str]:
    if protected < 0:
        raise ValueError("protected must be non-negative")
    if len(original) <= protected:
        return list(original)
    prefix = list(original[:protected])
    protected_set = set(prefix)
    pick = next((item for item in preferred_order if item in original and item not in protected_set), None)
    if pick is None:
        return list(original)
    out = prefix + [pick]
    seen = set(out)
    out.extend(item for item in original if item not in seen)
    return out


def query_only_rank(query: str, ids: list[str], documents: list[str]) -> list[str]:
    if len(ids) != len(documents) or len(set(ids)) != len(ids):
        raise ValueError("ids/documents mismatch")
    scores = score_documents(query, documents)
    ranked = sorted(zip(ids, scores, range(len(ids))), key=lambda x: (-x[1], x[2]))
    return [item_id for item_id, _, _ in ranked]

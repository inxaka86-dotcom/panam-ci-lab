from __future__ import annotations

from typing import Iterable


def normalize(text: str) -> str:
    return " ".join(str(text).split())


def _distance(a: Iterable[str], b: Iterable[str]) -> int:
    left = list(a)
    right = list(b)
    previous = list(range(len(right) + 1))
    for i, x in enumerate(left, 1):
        current = [i]
        for j, y in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (x != y)))
        previous = current
    return previous[-1]


def cer(reference: str, observed: str) -> float:
    ref = normalize(reference)
    obs = normalize(observed)
    return _distance(ref, obs) / max(1, len(ref))


def wer(reference: str, observed: str) -> float:
    ref = normalize(reference).split()
    obs = normalize(observed).split()
    return _distance(ref, obs) / max(1, len(ref))


def evaluate(case: dict) -> dict:
    reference = case["reference"]
    observed = case["observed"]
    result = {"id": case["id"], "exact": normalize(reference) == normalize(observed), "cer": cer(reference, observed), "wer": wer(reference, observed)}
    kind = case["kind"]
    if kind == "text":
        result["pass"] = result["exact"]
    elif kind == "scan":
        result["pass"] = result["cer"] <= float(case["cer_max"]) and result["wer"] <= float(case["wer_max"])
    elif kind == "mixed":
        result["missing_pages"] = int(case["page_count"]) - int(case["observed_page_count"])
        result["pass"] = result["missing_pages"] == 0
    else:
        raise ValueError("unsupported fixture kind")
    return result

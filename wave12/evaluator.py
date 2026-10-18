"""Offline evidence-grounding evaluator for public synthetic PANAM experiments.

No model executor, network client, provider credentials, or PANAM state.
Use 'export' to produce a prompt-only task pack. Use 'compare' *after*
obtaining independently produced baseline and candidate predictions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

DECISIONS = frozenset(("REQUIRED", "NOT_REQUIRED", "UNKNOWN", "CONFLICT"))
DOMAINS = frozenset(("legal", "tender"))
SCHEMA_VERSION = 1


class InvalidSubmission(ValueError):
    pass


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise InvalidSubmission("Duplicate JSON object key: " + key)
        obj[key] = value
    return obj


def reject_constant(value: str) -> None:
    raise InvalidSubmission("Nonfinite JSON value: " + value)


def read_json(path: Path) -> Any:
    if not path.is_file():
        raise InvalidSubmission("Missing input file: " + str(path))
    if path.stat().st_size > 5_000_000:
        raise InvalidSubmission("Input exceeds 5 MB limit: " + str(path))
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidSubmission("Invalid JSON: " + str(exc)) from exc


def exact_keys(value: Any, keys: set[str], where: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise InvalidSubmission(where + ": unexpected or missing fields")


def distinct_strings(values: Any, where: str) -> list[str]:
    if not isinstance(values, list) or not all(isinstance(x, str) and x for x in values):
        raise InvalidSubmission(where + ": expected an array of nonempty strings")
    if len(values) != len(set(values)):
        raise InvalidSubmission(where + ": repeated value")
    return values


def load_cases(path: Path) -> tuple[list[dict], str]:
    raw = read_json(path)
    exact_keys(raw, {"schema_version", "notice", "cases"}, "cases root")
    if raw["schema_version"] != SCHEMA_VERSION or not isinstance(raw["notice"], str):
        raise InvalidSubmission("Unsupported cases schema or missing notice")
    cases = raw["cases"]
    if not isinstance(cases, list) or not cases:
        raise InvalidSubmission("Case collection must be nonempty")
    ids: set[str] = set()
    for entry in cases:
        exact_keys(entry, {"id", "domain", "question", "sources", "gold"}, "case")
        cid = entry["id"]
        if not isinstance(cid, str) or not cid or cid in ids:
            raise InvalidSubmission("Missing or duplicate case ID")
        ids.add(cid)
        if entry["domain"] not in DOMAINS:
            raise InvalidSubmission(cid + ": unknown domain")
        if not isinstance(entry["question"], str) or not entry["question"].strip():
            raise InvalidSubmission(cid + ": empty question")
        sources = entry["sources"]
        if not isinstance(sources, list) or not sources:
            raise InvalidSubmission(cid + ": missing sources")
        source_ids: set[str] = set()
        for src in sources:
            exact_keys(src, {"id", "text"}, cid + ": source")
            if (
                not isinstance(src["id"], str)
                or not src["id"]
                or src["id"] in source_ids
                or not isinstance(src["text"], str)
                or not src["text"].strip()
            ):
                raise InvalidSubmission(cid + ": invalid source")
            source_ids.add(src["id"])
        gold = entry["gold"]
        exact_keys(gold, {"decision", "citations"}, cid + ": gold")
        if gold["decision"] not in DECISIONS:
            raise InvalidSubmission(cid + ": invalid gold decision")
        evidence = distinct_strings(gold["citations"], cid + ": gold citations")
        if not set(evidence).issubset(source_ids):
            raise InvalidSubmission(cid + ": gold cites a non-existent source")
        if gold["decision"] == "UNKNOWN" and evidence:
            raise InvalidSubmission(cid + ": UNKNOWN should cite no sources")
        if gold["decision"] in ("REQUIRED", "NOT_REQUIRED") and not evidence:
            raise InvalidSubmission(cid + ": missing affirmative evidence")
        if gold["decision"] == "CONFLICT" and len(evidence) < 2:
            raise InvalidSubmission(cid + ": conflict requires two sources")
    return cases, hashlib.sha256(path.read_bytes()).hexdigest()


def pack_tasks(cases: list[dict], source_sha: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "case_file_sha256": source_sha,
        "tasks": [
            {
                "case_id": c["id"],
                "domain": c["domain"],
                "question": c["question"],
                "sources": c["sources"],
            }
            for c in cases
        ],
    }


def encode(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def save(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = encode(value)
    path.write_bytes(body)
    return hashlib.sha256(body).hexdigest()


def load_predictions(path: Path, cases: list[dict]) -> dict[str, dict]:
    data = read_json(path)
    exact_keys(data, {"schema_version", "predictions"}, "predictions root")
    if data["schema_version"] != SCHEMA_VERSION:
        raise InvalidSubmission("Unsupported predictions schema")
    rows = data["predictions"]
    if not isinstance(rows, list):
        raise InvalidSubmission("Predictions must be a list")
    expected = {c["id"] for c in cases}
    responses: dict[str, dict] = {}
    for item in rows:
        exact_keys(item, {"case_id", "decision", "citations"}, "prediction")
        cid = item["case_id"]
        if not isinstance(cid, str) or cid not in expected or cid in responses:
            raise InvalidSubmission("Unknown or duplicate prediction case ID: " + str(cid))
        if item["decision"] not in DECISIONS:
            raise InvalidSubmission(cid + ": invalid prediction label")
        distinct_strings(item["citations"], cid + ": prediction citations")
        if len(item["citations"]) > 20:
            raise InvalidSubmission(cid + ": too many citations")
        responses[cid] = item
    if set(responses) != expected:
        raise InvalidSubmission("Missing case predictions: " + repr(sorted(expected - set(responses))))
    return responses


def evaluate(cases: list[dict], responses: dict[str, dict]) -> tuple[dict, dict]:
    details: dict[str, dict] = {}
    for c in cases:
        cid = c["id"]
        p = responses[cid]
        permitted = {s["id"] for s in c["sources"]}
        unsupported = sorted(set(p["citations"]) - permitted)
        dc = p["decision"] == c["gold"]["decision"]
        ec = (
            set(p["citations"]) == set(c["gold"]["citations"])
            and not unsupported
        )
        details[cid] = {
            "domain": c["domain"],
            "decision_correct": dc,
            "evidence_exact": ec,
            "fully_correct": dc and ec,
            "unsupported_citations": unsupported,
            "unknown_case": c["gold"]["decision"] == "UNKNOWN",
        }

    def totals(rows: list[dict]) -> dict:
        return {
            "cases": len(rows),
            "decision_correct": sum(x["decision_correct"] for x in rows),
            "evidence_exact": sum(x["evidence_exact"] for x in rows),
            "fully_correct": sum(x["fully_correct"] for x in rows),
            "unsupported_citations": sum(len(x["unsupported_citations"]) for x in rows),
            "unknown_cases": sum(x["unknown_case"] for x in rows),
            "unknown_correct": sum(x["unknown_case"] and x["fully_correct"] for x in rows),
        }

    overall = totals(list(details.values()))
    per_domain = {
        domain: totals([row for row in details.values() if row["domain"] == domain])
        for domain in sorted({c["domain"] for c in cases})
    }
    return details, {"overall": overall, "by_domain": per_domain}


def compare(cases: list[dict], baseline: dict[str, dict], candidate: dict[str, dict],
            source_sha: str) -> dict:
    bd, bs = evaluate(cases, baseline)
    cd, cs = evaluate(cases, candidate)
    regressions = [cid for cid in bd if bd[cid]["fully_correct"] and not cd[cid]["fully_correct"]]
    improvements = [cid for cid in bd if not bd[cid]["fully_correct"] and cd[cid]["fully_correct"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "offline_prediction_comparison_no_model_execution",
        "case_file_sha256": source_sha,
        "baseline": bs,
        "candidate": cs,
        "delta_fully_correct": cs["overall"]["fully_correct"] - bs["overall"]["fully_correct"],
        "regressions": regressions,
        "improvements": improvements,
        "by_case": {
            cid: {"baseline": bd[cid], "candidate": cd[cid]}
            for cid in bd
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    exp = sub.add_parser("export", help="Write a task pack with gold answers omitted")
    exp.add_argument("--cases", required=True, type=Path)
    exp.add_argument("--out", required=True, type=Path)
    cmp = sub.add_parser("compare", help="Offline score of two completed predictions")
    cmp.add_argument("--cases", required=True, type=Path)
    cmp.add_argument("--baseline", required=True, type=Path)
    cmp.add_argument("--candidate", required=True, type=Path)
    cmp.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        cases, source_sha = load_cases(args.cases)
        paths = [args.cases.resolve()]
        if args.action == "compare":
            paths.extend([args.baseline.resolve(), args.candidate.resolve()])
        if args.out.resolve() in paths:
            raise InvalidSubmission("Output path must not overwrite an input")
        if args.action == "export":
            digest = save(args.out, pack_tasks(cases, source_sha))
            print("PANAM_EVAL_EXPORTED_TASKS=" + str(len(cases)))
            print("PANAM_EVAL_TASK_PACK_SHA256=" + digest)
        else:
            baseline = load_predictions(args.baseline, cases)
            candidate = load_predictions(args.candidate, cases)
            report = compare(cases, baseline, candidate, source_sha)
            digest = save(args.out, report)
            print("PANAM_EVAL_COMPARISON=" + json.dumps({
                "baseline": report["baseline"]["overall"],
                "candidate": report["candidate"]["overall"],
                "delta_fully_correct": report["delta_fully_correct"],
                "regressions": report["regressions"],
            }, ensure_ascii=False, sort_keys=True))
            print("PANAM_EVAL_REPORT_SHA256=" + digest)
        return 0
    except InvalidSubmission as exc:
        parser.exit(2, "PANAM_EVAL_INVALID=" + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())

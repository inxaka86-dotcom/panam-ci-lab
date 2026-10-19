#!/usr/bin/env python3
"""Public synthetic answer-key scorer — NOT blind, no agent/provider calls.

Verifies answer values, NOT cited evidence or authenticity of model traces.
The labels live in this public repository. This can test scorer sensitivity,
but cannot prove real-world agent accuracy or generalisation.
"""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path

CASES = ("LR-E01", "LR-N01", "LR-G01", "LR-D01")
FIELDS = {
    "LR-E01": ("start_channel", "changed_channel"),
    "LR-N01": ("permission_symbol", "allowed_euid"),
    "LR-G01": ("module_path", "toolchain"),
    "LR-D01": ("socket_path", "accepted_message", "peer_check_symbol"),
}
FIXED = {
    "LR-E01": {"start_channel": "records:begin-v2",
               "changed_channel": "records:changed-v2"},
    "LR-N01": {"permission_symbol": "capture_access_check",
               "allowed_euid": "1234"},
    "LR-D01": {"socket_path": "/tmp/leanrea-synthetic-v2.sock",
               "accepted_message": "HELLO:2",
               "peer_check_symbol": "wire_peer_matches"},
}


class Invalid(ValueError):
    pass


def expected_from_target(target_root: Path) -> dict:
    # Only static inspection of the locally built synthetic Go binary.
    target = target_root / "targets" / "go_probe"
    if not target.is_file() or target.is_symlink():
        raise Invalid("Go target missing or symlinked")
    try:
        result = subprocess.run(
            ["go", "version", "-m", str(target)], check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Invalid("Cannot inspect Go build metadata") from exc
    path = re.search(r"(?m)^\s*path\s+(\S+)\s*$", result)
    toolchain = re.search(r"\b(go1\.\d+(?:\.\d+)?)\b", result)
    if not path or not toolchain:
        raise Invalid("Go metadata incomplete")
    if path.group(1) != "example.invalid/leanrea-fixture/tool":
        raise Invalid("Unexpected Go source identity")
    return {
        **FIXED, "LR-G01": {
            "module_path": path.group(1),
            "toolchain": toolchain.group(1),
        },
    }


def score(packet: dict, target_root: Path) -> dict:
    if not isinstance(packet, dict) or set(packet) != {"schema", "responses"}:
        raise Invalid("Unknown prediction packet keys")
    if packet["schema"] != "panam.leanrea.synthetic-predictions.v1":
        raise Invalid("Unknown prediction schema")
    responses = packet["responses"]
    if not isinstance(responses, list) or len(responses) != 4:
        raise Invalid("Exactly four responses are required")
    gold = expected_from_target(target_root)
    seen = set()
    details = []
    for item in responses:
        if not isinstance(item, dict) or set(item) != {"case_id", "answers"}:
            raise Invalid("Malformed response")
        case = item["case_id"]
        if not isinstance(case, str) or case not in CASES or case in seen:
            raise Invalid("Unknown or duplicate case")
        seen.add(case)
        answers = item["answers"]
        if not isinstance(answers, dict) or set(answers) != set(FIELDS[case]):
            raise Invalid("Missing or extra answer fields")
        correctness = {}
        for field in FIELDS[case]:
            value = answers[field]
            if not isinstance(value, str) or len(value) > 256 or "\x00" in value:
                raise Invalid("Answer must be a bounded string")
            correctness[field] = value == gold[case][field]
        details.append({"case_id": case, "field_correct": correctness,
                        "fields_correct": sum(correctness.values()),
                        "fields_total": len(FIELDS[case])})
    if seen != set(CASES):
        raise Invalid("Case mismatch")
    details.sort(key=lambda d: d["case_id"])
    correct = sum(d["fields_correct"] for d in details)
    total = sum(d["fields_total"] for d in details)
    return {
        "schema": "panam.leanrea.synthetic-scorer-report.v1",
        "source_class": "PUBLIC_SYNTHETIC_NOT_BLIND",
        "fields_correct": correct, "fields_total": total,
        "all_fields_correct": correct == total,
        "evidence_citations_verified": False,
        "tool_traces_verified": False,
        "real_agent_benefit_proven": False,
        "authorization": "NONE",
        "cases": details,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = args.predictions.read_bytes()
        if len(raw) > 32768:
            raise Invalid("Input over 32 KiB")
        p = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(
            Invalid("Non-finite value")))
        report = score(p, args.targets)
    except (Invalid, OSError, ValueError, TypeError):
        print("PANAM_LEANREA_SYNTHETIC_SCORE=FAIL")
        raise SystemExit(2)
    print(json.dumps(report, sort_keys=True))
    print("PANAM_LEANREA_SYNTHETIC_SCORE=SHAPE_AND_PUBLIC_GOLD_ONLY")


if __name__ == "__main__":
    main()

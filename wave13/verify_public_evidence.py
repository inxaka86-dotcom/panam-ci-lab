#!/usr/bin/env python3
"""Check answer-value evidence anchors in approved PUBLIC SYNTHETIC artifacts.

Not a semantic correctness judge, model trace verifier, blind benchmark or
sandbox. Never executes analyzed binaries; runs only fixed local read-only
inspection commands. Inputs must be synthetic, built by this research pack.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from score_synthetic import CASES, FIELDS, Invalid

SCHEMA = "panam.leanrea.public-evidence-submission.v1"
FIELD_RULES = {
    "LR-E01": {
        "start_channel": ("source-line", (
            "targets/electron-app/.webpack/main.js",
            "targets/electron-app/.vite/preload.js")),
        "changed_channel": ("source-line", (
            "targets/electron-app/.webpack/main.js",
            "targets/electron-app/.vite/preload.js")),
    },
    "LR-N01": {
        "permission_symbol": ("nm-export", ("targets/libcapture_probe.so",)),
        "allowed_euid": ("objdump-immediate", ("targets/libcapture_probe.so",)),
    },
    "LR-G01": {
        "module_path": ("go-build", ("targets/go_probe",)),
        "toolchain": ("go-build", ("targets/go_probe",)),
    },
    "LR-D01": {
        "socket_path": ("strings-line", ("targets/libwire_probe.so",)),
        "accepted_message": ("strings-line", ("targets/libwire_probe.so",)),
        "peer_check_symbol": ("nm-export", ("targets/libwire_probe.so",)),
    },
}


def approved_target(root: Path, relative: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise Invalid("Target root not a real directory")
    path = root
    for part in Path(relative).parts:
        if part in ("..", ".", ""):
            raise Invalid("Invalid relative artifact")
        path = path / part
        if path.is_symlink():
            raise Invalid("Symlink in cited artifact chain")
    if not path.is_file():
        raise Invalid("Missing cited artifact")
    return path


def inspect(tool: str, path: Path) -> str:
    if tool == "nm-export":
        argv = ["nm", "-D", "--defined-only", str(path)]
    elif tool == "objdump-immediate":
        argv = ["objdump", "-d", "--disassemble=capture_access_check", str(path)]
    elif tool == "go-build":
        argv = ["go", "version", "-m", str(path)]
    elif tool == "strings-line":
        argv = ["strings", "-a", str(path)]
    else:
        raise Invalid("Unapproved inspector")
    try:
        output = subprocess.run(argv, check=True, capture_output=True,
                                text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise Invalid("Static inspection unavailable") from exc
    if len(output) > 262144:
        raise Invalid("Oversized static inspector output")
    return output


def evidence_matches(path: Path, method: str, answer: str, line: int | None) -> bool:
    if method == "source-line":
        if type(line) is not int or not (1 <= line <= 10000):
            raise Invalid("source-line requires bounded integer position")
        data = path.read_bytes()
        if len(data) > 65536:
            raise Invalid("Source text exceeds fixture bound")
        try:
            lines = data.decode("utf-8").splitlines()
        except UnicodeError as exc:
            raise Invalid("Non-UTF8 synthetic source") from exc
        # Match an entire quoted JavaScript string literal, not a substring.
        return (line <= len(lines)
                and re.search(r"(['\"])" + re.escape(answer) + r"\1",
                              lines[line - 1]) is not None)
    if line is not None:
        raise Invalid("Static inspector does not accept source line position")
    text = inspect(method, path)
    if method == "nm-export":
        return any(re.search(r"(?:^|\s)" + re.escape(answer) + r"\s*$", s)
                   for s in text.splitlines())
    if method == "strings-line":
        return answer in text.splitlines()
    if method == "go-build":
        if answer.startswith("go1."):
            return re.search(r"\b" + re.escape(answer) + r"(?:\s|$)", text) is not None
        return re.search(r"(?m)^\s*path\s+" + re.escape(answer) + r"\s*$", text) is not None
    if method == "objdump-immediate":
        if not answer.isdecimal() or not (0 <= int(answer) <= 65535):
            return False
        # A random immediate is not permission-rule evidence. Demand the
        # synthetic fixture's actual geteuid call and the immediate in CMP.
        if re.search(r"\bcall(?:q)?\s+[^\n]*<geteuid@plt>", text) is None:
            return False
        compare = (r"(?m)^\s*[0-9a-f]+:\s+(?:[0-9a-f]{2}\s+)+"
                   r"cmp(?:[bwlq])?\s+\$0x"
                   + format(int(answer), "x") + r"\s*,\s*%[a-z0-9]+\b")
        return re.search(compare, text) is not None
    raise Invalid("Unapproved method")


def verify(packet: dict, target_root: Path) -> dict:
    if not isinstance(packet, dict) or set(packet) != {"schema", "responses"}:
        raise Invalid("Evidence packet has unknown fields")
    if packet["schema"] != SCHEMA:
        raise Invalid("Invalid evidence schema")
    cases = packet["responses"]
    if not isinstance(cases, list) or len(cases) != 4:
        raise Invalid("Exactly four public synthetic cases required")
    seen = set()
    details = []
    for item in cases:
        if not isinstance(item, dict) or set(item) != {"case_id", "answers", "evidence"}:
            raise Invalid("Malformed response with evidence")
        case_id = item["case_id"]
        if not isinstance(case_id, str) or case_id not in CASES or case_id in seen:
            raise Invalid("Unknown or repeated case")
        seen.add(case_id)
        answers, evidence = item["answers"], item["evidence"]
        required = set(FIELDS[case_id])
        if (not isinstance(answers, dict) or not isinstance(evidence, dict)
                or set(answers) != required or set(evidence) != required):
            raise Invalid("Missing/extra answer or evidence field")
        matched = {}
        for field in FIELDS[case_id]:
            answer = answers[field]
            if (not isinstance(answer, str) or not (1 <= len(answer) <= 256)
                    or any(ord(c) < 32 or ord(c) == 127 for c in answer)):
                raise Invalid("Invalid answer value")
            item_evidence = evidence[field]
            if (not isinstance(item_evidence, dict)
                    or set(item_evidence) != {"path", "method", "line"}):
                raise Invalid("Unexpected evidence shape")
            method, paths = FIELD_RULES[case_id][field]
            if (item_evidence["method"] != method or
                    not isinstance(item_evidence["path"], str) or
                    item_evidence["path"] not in paths):
                raise Invalid("Cross-case, cross-field or unapproved artifact/method")
            path = approved_target(target_root, item_evidence["path"])
            matched[field] = evidence_matches(path, method, answer, item_evidence["line"])
        details.append({"case_id": case_id, "anchor_present": matched})
    if seen != set(CASES):
        raise Invalid("Incomplete set of cases")
    details.sort(key=lambda e: e["case_id"])
    hits = sum(sum(c["anchor_present"].values()) for c in details)
    return {
        "schema": "panam.leanrea.public-evidence-check.v1",
        "source_class": "PUBLIC_SYNTHETIC_NOT_BLIND",
        "fields_with_matching_anchors": hits,
        "fields_total": 9,
        "all_anchors_found": hits == 9,
        "semantic_correctness_verified": False,
        "agent_trace_verified": False,
        "independent_blind_gold_verified": False,
        "real_agent_benefit_proven": False,
        "authority": "NONE",
        "cases": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = args.submission.read_bytes()
        if len(raw) > 32768:
            raise Invalid("Evidence JSON exceeds 32 KiB")
        packet = json.loads(raw, parse_constant=lambda _:
                            (_ for _ in ()).throw(Invalid("nonfinite JSON")))
        result = verify(packet, args.targets)
    except (OSError, Invalid, TypeError, ValueError):
        print("PANAM_LEANREA_PUBLIC_EVIDENCE=FAIL")
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True))
    print("PANAM_LEANREA_PUBLIC_EVIDENCE=ANCHORS_ONLY")


if __name__ == "__main__":
    main()

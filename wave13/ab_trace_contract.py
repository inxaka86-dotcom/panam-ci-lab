#!/usr/bin/env python3
"""Shape-only paired trace projection for a future Leanrea/Codex experiment.

No agent invocation, network, authentication, cost conversion, scoring or approval.
Receipt SHA fields are declarations; this module does not verify underlying files.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path

SCHEMA = "panam.leanrea.paired-trace.v1"
CASES = frozenset(("LR-E01", "LR-N01", "LR-G01", "LR-D01"))
ARMS = ("base", "leanrea")
HASH = re.compile(r"[0-9a-f]{64}\Z")
MAIN = re.compile(r"[0-9a-f]{40}\Z")
RUN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
ARM_KEYS = frozenset((
    "run_id", "route_sha256", "profile_sha256", "environment_sha256",
    "trace_sha256", "receipt_sha256", "latency_ms", "input_tokens",
    "cached_input_tokens", "output_tokens",
))


class Invalid(ValueError):
    pass


def obj(value, keys, where):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid(f"{where}: missing, extra or non-object fields")
    return value


def digest(value, where, sha40=False):
    if not isinstance(value, str) or not (MAIN if sha40 else HASH).fullmatch(value):
        raise Invalid(f"{where}: invalid digest")
    return value


def integer(value, where, positive=False):
    if type(value) is not int or value < (1 if positive else 0):
        raise Invalid(f"{where}: invalid integer")
    return value


def project(packet):
    p = obj(packet, (
        "schema", "data_class", "lab_head_sha", "skill_sha256",
        "tasks_sha256", "route_sha256", "environment_sha256",
        "profiles", "cases",
    ), "packet")
    if p["schema"] != SCHEMA or p["data_class"] not in ("synthetic", "observed"):
        raise Invalid("schema or data_class invalid")
    digest(p["lab_head_sha"], "lab_head_sha", sha40=True)
    for field in ("skill_sha256", "tasks_sha256", "route_sha256", "environment_sha256"):
        digest(p[field], field)
    profiles = obj(p["profiles"], ARMS, "profiles")
    for arm in ARMS:
        digest(profiles[arm], "profile " + arm)
    if profiles["base"] == profiles["leanrea"]:
        raise Invalid("profiles: the base and candidate cannot be identical")
    cases = p["cases"]
    if not isinstance(cases, list) or len(cases) != 4:
        raise Invalid("expected exactly four fixed cases")
    seen_cases, seen_runs = set(), set()
    totals = {arm: {"latency_ms": 0, "total_tokens": 0, "cached_input_tokens": 0}
              for arm in ARMS}
    for case in cases:
        c = obj(case, ("case_id", "task_sha256", "base", "leanrea"), "case")
        case_id = c["case_id"]
        if not isinstance(case_id, str) or case_id not in CASES or case_id in seen_cases:
            raise Invalid("unexpected or duplicate case")
        seen_cases.add(case_id)
        digest(c["task_sha256"], f"{case_id}.task_sha256")
        for arm in ARMS:
            a = obj(c[arm], ARM_KEYS, f"{case_id}.{arm}")
            rid = a["run_id"]
            if not isinstance(rid, str) or not RUN.fullmatch(rid) or rid in seen_runs:
                raise Invalid("invalid or duplicate run_id")
            seen_runs.add(rid)
            for name in ("route_sha256", "profile_sha256", "environment_sha256",
                         "trace_sha256", "receipt_sha256"):
                digest(a[name], f"{case_id}.{arm}.{name}")
            for name, expected in (
                ("route_sha256", p["route_sha256"]),
                ("profile_sha256", profiles[arm]),
                ("environment_sha256", p["environment_sha256"]),
            ):
                if a[name] != expected:
                    raise Invalid(f"{case_id}.{arm}: mismatch for {name}")
            latency = integer(a["latency_ms"], "latency_ms", positive=True)
            input_tok = integer(a["input_tokens"], "input_tokens")
            cache_tok = integer(a["cached_input_tokens"], "cached_input_tokens")
            output_tok = integer(a["output_tokens"], "output_tokens")
            if cache_tok > input_tok:
                raise Invalid("cached input exceeds input tokens")
            totals[arm]["latency_ms"] += latency
            totals[arm]["total_tokens"] += input_tok + output_tok
            totals[arm]["cached_input_tokens"] += cache_tok
    if seen_cases != CASES:
        raise Invalid("case set mismatch")
    # Arithmetic over declared observations ONLY: not source receipt validation.
    return {
        "schema": "panam.leanrea.paired-trace-projection.v1",
        "source_class": p["data_class"],
        "shape_valid": True,
        "underlying_receipts_verified": False,
        "external_judgement_verified": False,
        "real_model_benefit_proven": False,
        "usd_cost_comparison": "NOT_AVAILABLE",
        "verification": "SHAPE_ONLY_NEVER_EXECUTION_AUTHORITY",
        "pair_count": 4,
        "totals_unverified": totals,
        "delta_unverified": {
            key: totals["leanrea"][key] - totals["base"][key]
            for key in ("latency_ms", "total_tokens", "cached_input_tokens")
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        if len(raw) > 65536:
            raise Invalid("input exceeds 64 KiB")
        packet = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(
            Invalid("non-finite JSON value")))
        result = project(packet)
    except (OSError, ValueError, TypeError) as exc:
        print("PANAM_LEANREA_AB_TRACE=FAIL (" + type(exc).__name__ + ")")
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    print("PANAM_LEANREA_AB_TRACE=SHAPE_ONLY")


if __name__ == "__main__":
    main()

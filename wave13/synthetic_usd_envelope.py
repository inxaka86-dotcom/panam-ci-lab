#!/usr/bin/env python3
"""Pure PUBLIC SYNTHETIC USD envelope projection for a future Leanrea A/B.

This module neither brokers nor authorizes requests; even a feasible arithmetic
projection is NOT a real USD hard cap or evidence of network isolation.
AiDostup billing is in provider tokens, not proven USD. No provider client,
network, credentials, agent runner, host access, subprocess or persistent state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCHEMA = "panam.leanrea.synthetic-usd-envelope.v1"
CASES = frozenset(("LR-E01", "LR-N01", "LR-G01", "LR-D01"))
ARMS = ("base", "leanrea")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
DEMO_CAP_MICRO_USD = 100_000  # $0.10 toy threshold, NOT Leanrea spending permission.
TOKEN_BOUND = 1_000_000
MAX_RATE = 1_000_000_000  # micro-USD per 1M tokens; demo sanity ceiling only.
SLOT_FIELDS = ("case_id", "arm", "task_sha256", "route_sha256",
               "environment_sha256", "max_input_tokens", "max_output_tokens",
               "max_retries", "max_extra_billable_calls")
TARIFF_FIELDS = ("data_class", "currency", "micro_usd_per_million_input",
                 "micro_usd_per_million_output")


class Invalid(ValueError):
    pass


def exact_obj(value: object, required: tuple[str, ...], context: str) -> dict:
    if not isinstance(value, dict) or set(value) != set(required):
        raise Invalid(context + ": incorrect/missing/extra fields")
    return value


def integer(value: object, name: str, *, minimum: int = 0,
            maximum: int = TOKEN_BOUND) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid(name + ": invalid integer limit")
    return value


def digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise Invalid(name + ": invalid SHA-256")
    return value


def ceil_div(n: int, d: int) -> int:
    return (n + d - 1) // d


def project(packet: dict) -> dict:
    p = exact_obj(packet, (
        "schema", "experiment_class", "provider", "model",
        "wire_api", "demo_cap_micro_usd", "tariff", "slots",
    ), "envelope")
    if p["schema"] != SCHEMA or p["experiment_class"] != "public_synthetic":
        raise Invalid("This projection accepts synthetic-only data")
    if (p["provider"], p["model"], p["wire_api"]) != (
        "aidostup", "gpt-6-luna", "responses",
    ):
        raise Invalid("Unexpected route")
    if integer(p["demo_cap_micro_usd"], "demo cap", minimum=1,
               maximum=DEMO_CAP_MICRO_USD) != DEMO_CAP_MICRO_USD:
        raise Invalid("Demo cap must remain fixed to $0.10 (not permission)")
    tariff = exact_obj(p["tariff"], TARIFF_FIELDS, "tariff")
    if tariff["data_class"] != "fabricated_example" or tariff["currency"] != "USD":
        raise Invalid("Observed/claimed vendor tariffs are not authenticated here")
    inp_rate = integer(tariff["micro_usd_per_million_input"], "input rate",
                       minimum=1, maximum=MAX_RATE)
    out_rate = integer(tariff["micro_usd_per_million_output"], "output rate",
                       minimum=1, maximum=MAX_RATE)

    slots = p["slots"]
    if not isinstance(slots, list) or len(slots) != 8:
        raise Invalid("Exactly eight slot reservations (4 paired cases) required")
    seen, task_bindings, caps = set(), {}, {}
    route = environment = None
    total = 0
    details = []
    for slot in slots:
        x = exact_obj(slot, SLOT_FIELDS, "slot")
        case, arm = x["case_id"], x["arm"]
        if (not isinstance(case, str) or case not in CASES
                or not isinstance(arm, str) or arm not in ARMS
                or (case, arm) in seen):
            raise Invalid("Unknown, duplicate or unsupported A/B slot")
        seen.add((case, arm))
        task_sha = digest(x["task_sha256"], "task")
        route_sha = digest(x["route_sha256"], "route")
        env_sha = digest(x["environment_sha256"], "environment")
        if case in task_bindings and task_bindings[case] != task_sha:
            raise Invalid("Unequal task identity across arms")
        task_bindings[case] = task_sha
        if route is None:
            route, environment = route_sha, env_sha
        if route_sha != route or env_sha != environment:
            raise Invalid("A/B route/environment changed")
        input_tokens = integer(x["max_input_tokens"], "reserved input", minimum=1)
        output_tokens = integer(x["max_output_tokens"], "reserved output", minimum=1)
        integer(x["max_retries"], "retries", maximum=0)
        integer(x["max_extra_billable_calls"], "extra calls", maximum=0)
        token_caps = (input_tokens, output_tokens)
        if case in caps and caps[case] != token_caps:
            raise Invalid("Unequal reservation for comparable arms")
        caps[case] = token_caps
        # Ceil EACH call before aggregating: never round fractional charge down.
        unit_micro_usd = ceil_div(
            input_tokens * inp_rate + output_tokens * out_rate, 1_000_000)
        total += unit_micro_usd
        details.append({"case_id": case, "arm": arm,
                        "synthetic_worst_case_micro_usd": unit_micro_usd})
    if seen != {(case, arm) for case in CASES for arm in ARMS}:
        raise Invalid("Missing paired cases")
    details.sort(key=lambda x: (x["case_id"], x["arm"]))
    return {
        "schema": "panam.leanrea.synthetic-envelope-report.v1",
        "route_shape_valid": True,
        "eight_request_slots": 8,
        "requested_retries": 0,
        "requested_extra_calls": 0,
        "demo_cap_micro_usd": DEMO_CAP_MICRO_USD,
        "synthetic_bound_micro_usd": total,
        "synthetic_arithmetic_under_demo_cap": total <= DEMO_CAP_MICRO_USD,
        "tariff_verified_against_provider": False,
        "actual_provider_usd_billing_verified": False,
        "usd_hard_cap_enforced": False,
        "hidden_provider_subcalls_verified": False,
        "network_egress_isolation_verified": False,
        "blind_independent_gold_verified": False,
        "specific_owner_spend_approval": False,
        "execution_allowed": False,
        "status": "PROJECTION_ONLY_NO_EXECUTION_AUTHORITY",
        "per_slot": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        raw = args.input.read_bytes()
        if len(raw) > 65536:
            raise Invalid("Envelope exceeds 64 KiB")
        packet = json.loads(raw, parse_constant=lambda c: (_ for _ in ()).throw(
            Invalid("nonfinite JSON: " + c)))
        report = project(packet)
    except (OSError, ValueError, TypeError) as exc:
        print("PANAM_LEANREA_USD_ENVELOPE=FAIL (" + type(exc).__name__ + ")")
        raise SystemExit(2)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    print("PANAM_LEANREA_USD_ENVELOPE=SYNTHETIC_ONLY")


if __name__ == "__main__":
    main()

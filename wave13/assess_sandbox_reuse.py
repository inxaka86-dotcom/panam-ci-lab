#!/usr/bin/env python3
"""Public-safe OFFLINE compatibility assessment for a proven fixed-smoke sandbox.

Existing PANAM disposable JIT sandbox has live evidence for a *fixed* smoke
script, not a cross-repository, credentialed or model-backed Leanrea executor.
The assessment is descriptive and always denies dispatch/execution. Input
claims are NOT authenticated attestations and cannot confer permissions.
No requests, cloud/production calls, secrets, host operations or shell.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "panam.leanrea.sandbox-reuse-assessment.v1"
SCOPE = frozenset(("same_repository", "different_repository"))
OPERATIONS = frozenset(("source-admission", "fixed-exec-smoke",
                        "leanrea-synthetic-ab"))
WORKLOADS = frozenset(("fixed-smoke", "leanrea-synthetic-ab"))
PROOF_KINDS = frozenset(("historical-fixed-smoke", "current-target-independent"))
INPUT_FIELDS = frozenset(("schema", "data_class", "source_repository_relation",
                          "requested_operation", "requested_workload",
                          "existing_route_operation", "proof_kind",
                          "network_policy", "credential_delivery",
                          "trusted_source_binding", "cleanup_verified",
                          "private_sealed_gold", "usd_cap_proven"))


class Invalid(ValueError):
    pass


def describe(packet: dict) -> dict:
    if not isinstance(packet, dict) or set(packet) != INPUT_FIELDS:
        raise Invalid("Missing, extra or nonobject properties")
    if packet["schema"] != SCHEMA or packet["data_class"] != "synthetic_claim":
        raise Invalid("Only public synthetic declarations accepted")
    if packet["source_repository_relation"] not in SCOPE:
        raise Invalid("Unrecognized repository scope")
    if (packet["requested_operation"] not in OPERATIONS
            or packet["existing_route_operation"] not in OPERATIONS
            or packet["requested_workload"] not in WORKLOADS
            or packet["proof_kind"] not in PROOF_KINDS):
        raise Invalid("Unrecognized operation or proof class")
    if packet["network_policy"] not in ("none", "unknown", "allowlisted"):
        raise Invalid("Network policy unrecognized")
    if packet["credential_delivery"] not in ("none", "external-broker", "agent-env"):
        raise Invalid("Credential delivery unrecognized")
    for key in ("trusted_source_binding", "cleanup_verified",
                "private_sealed_gold", "usd_cap_proven"):
        if type(packet[key]) is not bool:
            raise Invalid("Untrusted/nonboolean declared evidence")
    reasons = []
    if packet["source_repository_relation"] != "same_repository":
        reasons.append("CROSS_REPOSITORY_ROUTE_NOT_ADMITTED")
    if packet["requested_operation"] != packet["existing_route_operation"]:
        reasons.append("ROUTE_DOES_NOT_SUPPORT_REQUESTED_OPERATION")
    if packet["requested_workload"] != "fixed-smoke":
        reasons.append("ONLY_FIXED_SMOKE_LIVE_PROVEN")
    if (packet["requested_workload"] == "fixed-smoke"
            and packet["requested_operation"] != "fixed-exec-smoke"):
        reasons.append("FIXED_SMOKE_REQUIRES_FIXED_OPERATION")
    if packet["proof_kind"] == "historical-fixed-smoke":
        reasons.append("HISTORICAL_SMOKE_NOT_CURRENT_WORKLOAD_PROOF")
    if packet["network_policy"] != "none":
        reasons.append("NETWORK_NONE_NOT_CONFIRMED")
    if packet["credential_delivery"] == "agent-env":
        reasons.append("AGENT_CREDENTIALS_FORBIDDEN")
    if not packet["trusted_source_binding"]:
        reasons.append("IMMUTABLE_SOURCE_BINDING_MISSING")
    if not packet["cleanup_verified"]:
        reasons.append("DISPOSABLE_TEARDOWN_NOT_EVIDENCED")
    if not packet["private_sealed_gold"]:
        reasons.append("INDEPENDENT_BLIND_GOLD_MISSING")
    if not packet["usd_cap_proven"]:
        reasons.append("REAL_USD_LIMIT_NOT_VERIFIED")
    # Observed/claimed evidence here is supplied by test fixtures only.
    # Even an all-green claim packet cannot be elevated to a sandbox grant:
    # no signed receipt, authority, trusted route binding or real agent exists.
    if not reasons:
        reasons.append("DECLARATIONS_NOT_AUTHENTICATED_NO_EXECUTION")
    return {
        "schema": "panam.leanrea.sandbox-reuse-report.v1",
        "data_class": "PUBLIC_SYNTHETIC_DECLARATIONS_ONLY",
        "compatibility_reasons": sorted(set(reasons)),
        "route_compatible_for_requested_real_agent": False,
        "provider_model_route_verified": False,
        "sandbox_evidence_authenticated": False,
        "cross_repo_source_admitted": False,
        "real_network_isolation_verified_for_leanrea": False,
        "real_usd_hard_cap_verified": False,
        "live_leanrea_model_executed": False,
        "execution_allowed": False,
        "production_change_allowed": False,
        "status": "OFFLINE_REUSE_ANALYSIS_NOT_EXECUTION_AUTHORITY",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = args.input.read_bytes()
        if len(data) > 8192:
            raise Invalid("Oversized assessment")
        packet = json.loads(data, parse_constant=lambda _:
                            (_ for _ in ()).throw(Invalid("Nonfinite JSON")))
        result = describe(packet)
    except (OSError, Invalid, TypeError, ValueError):
        print("PANAM_LEANREA_SANDBOX_REUSE=BLOCKED_BAD_INPUT")
        raise SystemExit(2)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    print("PANAM_LEANREA_SANDBOX_REUSE=ASSESSMENT_ONLY")
    print("PANAM_LEANREA_REAL_AGENT_EXECUTION=DENIED")


if __name__ == "__main__":
    main()

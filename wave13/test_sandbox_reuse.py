#!/usr/bin/env python3
"""Review of fixed-smoke sandbox reuse claims; no execution capability."""
from __future__ import annotations

from copy import deepcopy
import unittest

from assess_sandbox_reuse import Invalid, SCHEMA, describe


def claimed():
    # Hypothetical best-case synthetic claims: NONE is authenticated.
    return {
        "schema": SCHEMA,
        "data_class": "synthetic_claim",
        "source_repository_relation": "same_repository",
        "requested_operation": "fixed-exec-smoke",
        "requested_workload": "fixed-smoke",
        "existing_route_operation": "fixed-exec-smoke",
        "proof_kind": "current-target-independent",
        "network_policy": "none",
        "credential_delivery": "none",
        "trusted_source_binding": True,
        "cleanup_verified": True,
        "private_sealed_gold": True,
        "usd_cap_proven": True,
    }


def actual_leanrea_shape():
    p = claimed()
    p.update({
        "source_repository_relation": "different_repository",
        "requested_operation": "leanrea-synthetic-ab",
        "requested_workload": "leanrea-synthetic-ab",
        "existing_route_operation": "fixed-exec-smoke",
        "proof_kind": "historical-fixed-smoke",
        "private_sealed_gold": False,
        "usd_cap_proven": False,
    })
    return p


class SandboxReuseTests(unittest.TestCase):
    def test_actual_cross_repo_ab_scenario_blocked(self):
        out = describe(actual_leanrea_shape())
        self.assertIn("CROSS_REPOSITORY_ROUTE_NOT_ADMITTED", out["compatibility_reasons"])
        self.assertIn("ROUTE_DOES_NOT_SUPPORT_REQUESTED_OPERATION", out["compatibility_reasons"])
        self.assertIn("ONLY_FIXED_SMOKE_LIVE_PROVEN", out["compatibility_reasons"])
        self.assertFalse(out["execution_allowed"])

    def test_even_best_case_self_reports_never_authorize(self):
        r = describe(claimed())
        self.assertEqual(r["compatibility_reasons"],
                         ["DECLARATIONS_NOT_AUTHENTICATED_NO_EXECUTION"])
        self.assertFalse(r["sandbox_evidence_authenticated"])
        self.assertFalse(r["execution_allowed"])

    def test_historical_fixed_smoke_not_agent_proof(self):
        p = claimed()
        p["proof_kind"] = "historical-fixed-smoke"
        self.assertIn("HISTORICAL_SMOKE_NOT_CURRENT_WORKLOAD_PROOF",
                      describe(p)["compatibility_reasons"])

    def test_cross_repo_even_with_fixed_smoke_rejected(self):
        p = claimed()
        p["source_repository_relation"] = "different_repository"
        self.assertIn("CROSS_REPOSITORY_ROUTE_NOT_ADMITTED",
                      describe(p)["compatibility_reasons"])

    def test_arbitrary_operation_within_same_repo_rejected(self):
        p = claimed()
        p["requested_operation"] = "leanrea-synthetic-ab"
        self.assertIn("ROUTE_DOES_NOT_SUPPORT_REQUESTED_OPERATION",
                      describe(p)["compatibility_reasons"])

    def test_workload_upgrade_without_route_rejected(self):
        p = claimed()
        p["requested_workload"] = "leanrea-synthetic-ab"
        self.assertIn("ONLY_FIXED_SMOKE_LIVE_PROVEN",
                      describe(p)["compatibility_reasons"])

    def test_network_allowlist_not_equivalent_none(self):
        p = claimed()
        p["network_policy"] = "allowlisted"
        self.assertIn("NETWORK_NONE_NOT_CONFIRMED", describe(p)["compatibility_reasons"])

    def test_unknown_network_not_equivalent_none(self):
        p = claimed()
        p["network_policy"] = "unknown"
        self.assertIn("NETWORK_NONE_NOT_CONFIRMED", describe(p)["compatibility_reasons"])

    def test_credentials_in_agent_env_forbidden(self):
        p = claimed()
        p["credential_delivery"] = "agent-env"
        self.assertIn("AGENT_CREDENTIALS_FORBIDDEN", describe(p)["compatibility_reasons"])

    def test_external_broker_claim_still_not_authorized(self):
        p = claimed()
        p["credential_delivery"] = "external-broker"
        self.assertFalse(describe(p)["execution_allowed"])

    def test_no_source_binding(self):
        p = claimed()
        p["trusted_source_binding"] = False
        self.assertIn("IMMUTABLE_SOURCE_BINDING_MISSING",
                      describe(p)["compatibility_reasons"])

    def test_no_teardown(self):
        p = claimed()
        p["cleanup_verified"] = False
        self.assertIn("DISPOSABLE_TEARDOWN_NOT_EVIDENCED",
                      describe(p)["compatibility_reasons"])

    def test_public_gold_not_blind(self):
        p = claimed()
        p["private_sealed_gold"] = False
        self.assertIn("INDEPENDENT_BLIND_GOLD_MISSING",
                      describe(p)["compatibility_reasons"])

    def test_unknown_usd_cap(self):
        p = claimed()
        p["usd_cap_proven"] = False
        self.assertIn("REAL_USD_LIMIT_NOT_VERIFIED",
                      describe(p)["compatibility_reasons"])

    def test_extra_fake_admin_approval_rejected(self):
        p = claimed()
        p["owner_approved"] = True
        with self.assertRaises(Invalid):
            describe(p)

    def test_missing_field_rejected(self):
        p = claimed()
        p.pop("network_policy")
        with self.assertRaises(Invalid):
            describe(p)

    def test_false_boolean_claim_rejected(self):
        p = claimed()
        p["trusted_source_binding"] = 1
        with self.assertRaises(Invalid):
            describe(p)

    def test_claim_real_execution_schema_rejected(self):
        p = claimed()
        p["data_class"] = "observed"
        with self.assertRaises(Invalid):
            describe(p)

    def test_unknown_route_rejected(self):
        p = claimed()
        p["existing_route_operation"] = "arbitrary-command"
        with self.assertRaises(Invalid):
            describe(p)

    def test_all_proof_booleans_remain_false_on_claims(self):
        for p in (claimed(), actual_leanrea_shape()):
            out = describe(p)
            for f in ("route_compatible_for_requested_real_agent",
                      "provider_model_route_verified",
                      "sandbox_evidence_authenticated",
                      "cross_repo_source_admitted",
                      "real_network_isolation_verified_for_leanrea",
                      "real_usd_hard_cap_verified",
                      "live_leanrea_model_executed", "execution_allowed",
                      "production_change_allowed"):
                self.assertFalse(out[f])


if __name__ == "__main__":
    unittest.main(verbosity=2)

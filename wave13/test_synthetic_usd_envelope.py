#!/usr/bin/env python3
"""Adversarial tests for nonauthoritative public-synthetic cost arithmetic."""
from __future__ import annotations
import copy
import unittest

from synthetic_usd_envelope import Invalid, project, SCHEMA, CASES


def packet():
    return {
        "schema": SCHEMA,
        "experiment_class": "public_synthetic",
        "provider": "aidostup",
        "model": "gpt-6-luna",
        "wire_api": "responses",
        "demo_cap_micro_usd": 100000,
        "tariff": {
            "data_class": "fabricated_example",
            "currency": "USD",
            "micro_usd_per_million_input": 1000000,
            "micro_usd_per_million_output": 1000000,
        },
        "slots": [
            {
                "case_id": case, "arm": arm,
                "task_sha256": chr(ord("a")+j) * 64,
                "route_sha256": "e"*64,
                "environment_sha256": "f"*64,
                "max_input_tokens": 1000,
                "max_output_tokens": 1000,
                "max_retries": 0,
                "max_extra_billable_calls": 0,
            }
            for j,case in enumerate(("LR-E01","LR-N01","LR-G01","LR-D01"))
            for arm in ("base", "leanrea")
        ],
    }


class SyntheticUsdEnvelopeTests(unittest.TestCase):
    def denied(self, mutation):
        data = packet()
        mutation(data)
        with self.assertRaises((Invalid, TypeError)):
            project(data)

    def test_8_slots_valid_arithmetic_but_never_allowed(self):
        out = project(packet())
        self.assertTrue(out["synthetic_arithmetic_under_demo_cap"])
        self.assertEqual(out["synthetic_bound_micro_usd"], 16000)
        self.assertEqual(out["eight_request_slots"], 8)
        for label in ("execution_allowed", "usd_hard_cap_enforced",
                      "tariff_verified_against_provider",
                      "network_egress_isolation_verified",
                      "blind_independent_gold_verified",
                      "specific_owner_spend_approval",
                      "hidden_provider_subcalls_verified"):
            self.assertFalse(out[label])
        self.assertEqual(out["status"], "PROJECTION_ONLY_NO_EXECUTION_AUTHORITY")

    def test_cap_exceedance_is_explicit_not_silent(self):
        data = packet()
        data["tariff"]["micro_usd_per_million_input"] = 10000000
        data["tariff"]["micro_usd_per_million_output"] = 10000000
        r = project(data)
        self.assertEqual(r["synthetic_bound_micro_usd"], 160000)
        self.assertFalse(r["synthetic_arithmetic_under_demo_cap"])
        self.assertFalse(r["execution_allowed"])

    def test_per_request_rounding_up(self):
        data = packet()
        data["tariff"]["micro_usd_per_million_input"] = 1
        data["tariff"]["micro_usd_per_million_output"] = 1
        for s in data["slots"]:
            s["max_input_tokens"] = s["max_output_tokens"] = 1
        self.assertEqual(project(data)["synthetic_bound_micro_usd"], 8)

    def test_shuffled_slot_order_stable(self):
        data = packet()
        data["slots"].reverse()
        self.assertEqual(project(data), project(packet()))

    def test_unknown_route_denied(self):
        self.denied(lambda p: p.__setitem__("provider", "other"))

    def test_unverified_real_tariff_denied(self):
        self.denied(lambda p: p["tariff"].__setitem__("data_class", "observed"))

    def test_vendor_tokens_are_not_usd_denied(self):
        self.denied(lambda p: p["tariff"].__setitem__("currency", "PROVIDER_TOKENS"))

    def test_synthetic_model_generation_claim_denied(self):
        self.denied(lambda p: p.__setitem__("actual_generation_pass", True))

    def test_budget_spend_approval_injection_denied(self):
        self.denied(lambda p: p.__setitem__("owner_confirmed", True))

    def test_larger_budget_denied(self):
        self.denied(lambda p: p.__setitem__("demo_cap_micro_usd", 200000))

    def test_smaller_budget_changed_without_review_denied(self):
        self.denied(lambda p: p.__setitem__("demo_cap_micro_usd", 50000))

    def test_bool_cap_denied(self):
        self.denied(lambda p: p.__setitem__("demo_cap_micro_usd", True))

    def test_missing_slot_denied(self):
        self.denied(lambda p: p["slots"].pop())

    def test_duplicate_slot_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("arm", "base"))

    def test_extra_tool_calls_denied(self):
        self.denied(lambda p: p["slots"][2].__setitem__("max_extra_billable_calls", 1))

    def test_retries_denied(self):
        self.denied(lambda p: p["slots"][2].__setitem__("max_retries", 1))

    def test_changed_task_in_pair_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("task_sha256", "c" * 64))

    def test_changed_route_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("route_sha256", "0" * 64))

    def test_changed_environment_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("environment_sha256", "0" * 64))

    def test_changed_token_caps_between_pair_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("max_output_tokens", 1001))

    def test_zero_input_reservation_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("max_input_tokens", 0))

    def test_unknown_fields_in_slot_denied(self):
        self.denied(lambda p: p["slots"][1].__setitem__("fallback_provider", "other"))

    def test_zero_tariff_rate_denied(self):
        self.denied(lambda p: p["tariff"].__setitem__("micro_usd_per_million_input", 0))

    def test_bool_tariff_rate_denied(self):
        self.denied(lambda p: p["tariff"].__setitem__("micro_usd_per_million_output", True))

    def test_excessively_large_rate_denied(self):
        self.denied(lambda p: p["tariff"].__setitem__(
            "micro_usd_per_million_output", 1000000001))

    def test_unbounded_token_count_denied(self):
        self.denied(lambda p: p["slots"][2].__setitem__("max_output_tokens", 1000001))


if __name__ == "__main__":
    unittest.main(verbosity=2)

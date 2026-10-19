#!/usr/bin/env python3
"""Pure synthetic/adversarial tests; never call a model or use credentials."""
import copy
import unittest

from ab_trace_contract import Invalid, project, SCHEMA, CASES, ARMS


def fixture():
    profiles = {"base": "a" * 64, "leanrea": "b" * 64}
    p = {
        "schema": SCHEMA,
        "data_class": "synthetic",
        "lab_head_sha": "a" * 40,
        "skill_sha256": "c" * 64,
        "tasks_sha256": "d" * 64,
        "route_sha256": "e" * 64,
        "environment_sha256": "f" * 64,
        "profiles": profiles,
        "cases": [],
    }
    for i, cid in enumerate(sorted(CASES)):
        arms = {}
        for j, arm in enumerate(ARMS):
            arms[arm] = {
                "run_id": f"fixture{i}-{arm}",
                "route_sha256": p["route_sha256"],
                "profile_sha256": profiles[arm],
                "environment_sha256": p["environment_sha256"],
                "trace_sha256": f"{i+j+1:064x}",
                "receipt_sha256": f"{i+j+10:064x}",
                "latency_ms": 100 + 10 * j,
                "input_tokens": 70 + 5 * j,
                "cached_input_tokens": 20,
                "output_tokens": 30,
            }
        p["cases"].append({
            "case_id": cid, "task_sha256": f"{i+20:064x}", **arms
        })
    return p


class ContractSelftest(unittest.TestCase):
    def test_synthetic_fixture_unverified(self):
        result = project(fixture())
        self.assertEqual(result["pair_count"], 4)
        self.assertEqual(result["totals_unverified"]["base"]["latency_ms"], 400)
        self.assertEqual(result["totals_unverified"]["leanrea"]["latency_ms"], 440)
        self.assertFalse(result["underlying_receipts_verified"])
        self.assertFalse(result["real_model_benefit_proven"])
        self.assertEqual(result["usd_cost_comparison"], "NOT_AVAILABLE")

    def test_claimed_observed_does_not_verify_receipts(self):
        p = fixture()
        p["data_class"] = "observed"
        r = project(p)
        self.assertFalse(r["underlying_receipts_verified"])
        self.assertFalse(r["external_judgement_verified"])

    def reject(self, fn):
        p = fixture()
        fn(p)
        with self.assertRaises(Invalid):
            project(p)

    def test_missing_case(self):
        self.reject(lambda p: p["cases"].pop())

    def test_duplicate_case(self):
        self.reject(lambda p: p["cases"].__setitem__(
            1, copy.deepcopy(p["cases"][0])))

    def test_duplicate_run_id(self):
        self.reject(lambda p: p["cases"][1]["base"].__setitem__(
            "run_id", p["cases"][0]["base"]["run_id"]))

    def test_wrong_profile(self):
        self.reject(lambda p: p["cases"][0]["leanrea"].__setitem__(
            "profile_sha256", p["profiles"]["base"]))

    def test_wrong_route(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "route_sha256", "0" * 64))

    def test_wrong_environment(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "environment_sha256", "0" * 64))

    def test_negative_latency(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "latency_ms", -1))

    def test_boolean_usage_not_int(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "output_tokens", True))

    def test_cache_larger_than_input(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "cached_input_tokens", 999))

    def test_unverified_cost_field_rejected(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "cost_usd", 0.01))

    def test_self_reported_success_field_rejected(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "accuracy", 1.0))

    def test_missing_receipt(self):
        self.reject(lambda p: p["cases"][0]["base"].pop("receipt_sha256"))

    def test_bad_digest(self):
        self.reject(lambda p: p.__setitem__("skill_sha256", "unsigned"))

    def test_identical_profiles(self):
        self.reject(lambda p: p["profiles"].__setitem__(
            "leanrea", p["profiles"]["base"]))

    def test_unknown_arm(self):
        self.reject(lambda p: p["cases"][0].__setitem__(
            "third_arm", {}))

    def test_nonnumeric_string_usage(self):
        self.reject(lambda p: p["cases"][0]["base"].__setitem__(
            "input_tokens", "70"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

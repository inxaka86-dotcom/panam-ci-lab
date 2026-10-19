#!/usr/bin/env python3
"""Self-test the public synthetic scorer. Hand-crafted, NOT agent predictions."""
from __future__ import annotations
import copy
from pathlib import Path
import tempfile
import unittest

from build_synthetic_targets import build
from score_synthetic import Invalid, score, expected_from_target, CASES


class PublicSyntheticScorerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="leanrea-score-test-")
        cls.root = Path(cls.temp.name) / "pack"
        build(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def packet(self):
        key = expected_from_target(self.root)
        return {"schema": "panam.leanrea.synthetic-predictions.v1",
                "responses": [{"case_id": case, "answers": copy.deepcopy(key[case])}
                              for case in CASES]}

    def rejected(self, change):
        p = self.packet()
        change(p)
        with self.assertRaises(Invalid):
            score(p, self.root)

    def test_positive_scorer_control(self):
        r = score(self.packet(), self.root)
        self.assertEqual((r["fields_correct"], r["fields_total"]), (9, 9))
        self.assertFalse(r["real_agent_benefit_proven"])
        self.assertFalse(r["evidence_citations_verified"])
        self.assertEqual(r["source_class"], "PUBLIC_SYNTHETIC_NOT_BLIND")

    def test_negative_wrong_answer_decreases_score(self):
        p = self.packet()
        p["responses"][0]["answers"]["start_channel"] = "old:begin"
        r = score(p, self.root)
        self.assertEqual((r["fields_correct"], r["fields_total"]), (8, 9))
        self.assertFalse(r["all_fields_correct"])

    def test_wrong_go_toolchain_decreases_score(self):
        p = self.packet()
        p["responses"][2]["answers"]["toolchain"] = "go1.0.0"
        self.assertEqual(score(p, self.root)["fields_correct"], 8)

    def test_duplicate_case_rejected(self):
        self.rejected(lambda p: p["responses"][1].__setitem__(
            "case_id", p["responses"][0]["case_id"]))

    def test_missing_case_rejected(self):
        self.rejected(lambda p: p["responses"].pop())

    def test_extra_case_rejected(self):
        self.rejected(lambda p: p["responses"].append(copy.deepcopy(p["responses"][0])))

    def test_unknown_field_rejected(self):
        self.rejected(lambda p: p["responses"][0]["answers"].__setitem__("model_cost", 0.01))

    def test_missing_claim_rejected(self):
        self.rejected(lambda p: p["responses"][0]["answers"].pop("start_channel"))

    def test_numeric_field_rejected(self):
        self.rejected(lambda p: p["responses"][1]["answers"].__setitem__("allowed_euid", 1234))

    def test_malformed_packet_rejected(self):
        self.rejected(lambda p: p.__setitem__("fabricated_evidence_verified", True))

    def test_wrong_schema_rejected(self):
        self.rejected(lambda p: p.__setitem__("schema", "unknown"))

    def test_untrusted_gold_file_not_required(self):
        # A separate gold-label file is not accepted from the prediction payload.
        self.rejected(lambda p: p.__setitem__("expected_answers", self.packet()))


if __name__ == "__main__":
    unittest.main(verbosity=2)

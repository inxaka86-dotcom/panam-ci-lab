"""Self-contained negative controls for the offline PANAM Harness² evaluator."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import evaluator as ev


ROOT = Path(__file__).resolve().parent
CASES = ROOT / "synthetic_cases.json"


def prediction_rows(cases: list[dict], *, perfect: bool) -> dict:
    return {
        "schema_version": 1,
        "predictions": [
            {
                "case_id": case["id"],
                "decision": case["gold"]["decision"] if perfect else "UNKNOWN",
                "citations": list(case["gold"]["citations"]) if perfect else [],
            }
            for case in cases
        ],
    }


class EvaluatorContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.sha = ev.load_cases(CASES)

    def test_dataset_balanced_and_fictional(self):
        self.assertEqual(len(self.cases), 16)
        self.assertEqual(sum(c["domain"] == "legal" for c in self.cases), 8)
        self.assertEqual(sum(c["domain"] == "tender" for c in self.cases), 8)
        self.assertTrue(all("gold" in case for case in self.cases))

    def test_task_pack_omits_gold(self):
        pack = ev.pack_tasks(self.cases, self.sha)
        self.assertEqual(pack["case_file_sha256"], self.sha)
        self.assertEqual(len(pack["tasks"]), 16)
        self.assertTrue(all(set(x) == {"case_id", "domain", "question", "sources"} for x in pack["tasks"]))
        self.assertNotIn('"gold"', json.dumps(pack))
        self.assertNotIn('"citations"', json.dumps(pack))

    def test_scoring_positive_control_not_model_evidence(self):
        base = {r["case_id"]: r for r in prediction_rows(self.cases, perfect=False)["predictions"]}
        good = {r["case_id"]: r for r in prediction_rows(self.cases, perfect=True)["predictions"]}
        result = ev.compare(self.cases, base, good, self.sha)
        self.assertEqual(result["candidate"]["overall"]["fully_correct"], 16)
        self.assertEqual(result["baseline"]["overall"]["fully_correct"], 3)
        self.assertEqual(result["delta_fully_correct"], 13)
        self.assertEqual(len(result["improvements"]), 13)
        self.assertEqual(result["regressions"], [])
        self.assertEqual(result["candidate"]["overall"]["unknown_correct"], 3)
        self.assertEqual(result["candidate"]["by_domain"]["legal"]["fully_correct"], 8)
        self.assertEqual(result["candidate"]["by_domain"]["tender"]["fully_correct"], 8)

    def test_negative_regression_is_not_discarded(self):
        perfect = {r["case_id"]: r for r in prediction_rows(self.cases, perfect=True)["predictions"]}
        worse = json.loads(json.dumps(perfect))
        worse["L01"]["decision"] = "UNKNOWN"
        worse["L01"]["citations"] = []
        result = ev.compare(self.cases, perfect, worse, self.sha)
        self.assertIn("L01", result["regressions"])
        self.assertEqual(result["delta_fully_correct"], -1)

    def test_unsupported_citation_is_reported(self):
        perfect = {r["case_id"]: r for r in prediction_rows(self.cases, perfect=True)["predictions"]}
        perfect["L01"]["citations"] = ["INVENTED-SOURCE"]
        _, score = ev.evaluate(self.cases, perfect)
        self.assertEqual(score["overall"]["unsupported_citations"], 1)
        self.assertEqual(score["overall"]["fully_correct"], 15)

    def test_wrong_case_reference_is_not_valid_evidence(self):
        perfect = {r["case_id"]: r for r in prediction_rows(self.cases, perfect=True)["predictions"]}
        perfect["L01"]["citations"] = ["T01-A"]
        details, score = ev.evaluate(self.cases, perfect)
        self.assertEqual(details["L01"]["unsupported_citations"], ["T01-A"])
        self.assertFalse(details["L01"]["evidence_exact"])
        self.assertEqual(score["overall"]["unsupported_citations"], 1)

    def test_malformed_submissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer.json"
            submission = prediction_rows(self.cases, perfect=True)
            def try_invalid(value):
                path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
                with self.assertRaises(ev.InvalidSubmission):
                    ev.load_predictions(path, self.cases)
            try_invalid({"schema_version": 1, "predictions": []})
            try_invalid({"schema_version": 1, "predictions": submission["predictions"] + [submission["predictions"][0]]})
            extra = json.loads(json.dumps(submission))
            extra["predictions"][0]["citation_note"] = "injected"
            try_invalid(extra)
            bad = json.loads(json.dumps(submission))
            bad["predictions"][0]["decision"] = "MAYBE"
            try_invalid(bad)
            duplicate_cite = json.loads(json.dumps(submission))
            duplicate_cite["predictions"][0]["citations"] *= 2
            try_invalid(duplicate_cite)
            path.write_text('{"schema_version":1,"schema_version":1,"predictions":[]}', encoding="utf-8")
            with self.assertRaises(ev.InvalidSubmission):
                ev.load_predictions(path, self.cases)

    def test_export_and_compare_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            tasks = tmp / "tasks.json"
            b = tmp / "baseline.json"
            c = tmp / "candidate.json"
            report = tmp / "result.json"
            ev.save(b, prediction_rows(self.cases, perfect=False))
            ev.save(c, prediction_rows(self.cases, perfect=True))
            self.assertEqual(ev.main(["export", "--cases", str(CASES), "--out", str(tasks)]), 0)
            self.assertNotIn('"gold"', tasks.read_text(encoding="utf-8"))
            self.assertEqual(ev.main([
                "compare", "--cases", str(CASES), "--baseline", str(b),
                "--candidate", str(c), "--out", str(report)
            ]), 0)
            result = ev.read_json(report)
            self.assertEqual(result["delta_fully_correct"], 13)
            self.assertEqual(result["kind"], "offline_prediction_comparison_no_model_execution")

    def test_unsafe_output_input_collision_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            ev.main(["export", "--cases", str(CASES), "--out", str(CASES)])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()

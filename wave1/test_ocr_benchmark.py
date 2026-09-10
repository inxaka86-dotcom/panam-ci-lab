import json
import unittest
from pathlib import Path

from wave1.ocr_benchmark import evaluate


class OcrBenchmarkTests(unittest.TestCase):
    def test_all_synthetic_cases_meet_contract(self):
        cases = json.loads(Path("wave1/fixtures/ocr_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(len(cases), 6)
        ids = {case["id"] for case in cases}
        self.assertEqual(ids, {"text-ru", "text-en", "scan-clean-ru", "scan-degraded-ru", "scan-rotated-ru", "mixed-ru"})
        results = [evaluate(case) for case in cases]
        failed = [result for result in results if not result["pass"]]
        self.assertEqual(failed, [])

    def test_fixture_text_is_explicitly_synthetic(self):
        raw = Path("wave1/fixtures/ocr_cases.json").read_text(encoding="utf-8").lower()
        self.assertNotIn("example.com", raw)
        self.assertNotIn("@", raw)


if __name__ == "__main__":
    unittest.main()

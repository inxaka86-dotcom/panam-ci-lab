import unittest

from wave2.attribution import Observation, attribution_score, choose_candidate


class AttributionTests(unittest.TestCase):
    def test_score_is_bounded(self):
        item = Observation("alpha", True, 2.0, 4.0, 0)
        self.assertEqual(attribution_score(item), 1.0)

    def test_retry_penalty_is_deterministic(self):
        base = Observation("alpha", True, 0.8, 0.9, 0)
        retried = Observation("alpha", True, 0.8, 0.9, 2)
        self.assertGreater(attribution_score(base), attribution_score(retried))

    def test_best_candidate_wins(self):
        items = [
            Observation("alpha", False, 1.0, 0.9, 0),
            Observation("beta", True, 0.7, 0.8, 1),
        ]
        self.assertEqual(choose_candidate(items).candidate, "beta")

    def test_empty_is_none(self):
        self.assertIsNone(choose_candidate([]))


if __name__ == "__main__":
    unittest.main()

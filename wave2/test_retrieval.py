import unittest

from wave2.retrieval import mean_reciprocal_rank, recall_at_k, reciprocal_rank


class RetrievalTests(unittest.TestCase):
    def test_reciprocal_rank(self):
        self.assertEqual(reciprocal_rank(["d1", "d2", "d3"], {"d2"}), 0.5)

    def test_recall_at_k(self):
        self.assertEqual(recall_at_k(["d1", "d2", "d3"], {"d2", "d3"}, 2), 0.5)

    def test_empty_relevant_set(self):
        self.assertEqual(recall_at_k(["d1"], set(), 1), 1.0)

    def test_mrr(self):
        cases = [
            (["d1", "d2"], {"d1"}),
            (["d3", "d4"], {"d4"}),
        ]
        self.assertEqual(mean_reciprocal_rank(cases), 0.75)

    def test_invalid_k(self):
        with self.assertRaises(ValueError):
            recall_at_k(["d1"], {"d1"}, 0)


if __name__ == "__main__":
    unittest.main()

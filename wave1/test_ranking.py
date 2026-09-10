import unittest

from wave1.ranking import promote_one, query_only_rank


class RankingContractTests(unittest.TestCase):
    def test_query_only_scoring_is_deterministic(self):
        ids = ["a", "b", "c", "d", "e"]
        docs = ["orchid archive memo", "violet schedule note", "cedar neutral record", "orchid protocol archive archive", "general placeholder"]
        first = query_only_rank("orchid archive", ids, docs)
        second = query_only_rank("orchid archive", ids, docs)
        self.assertEqual(first, second)
        self.assertEqual(first[0], "d")

    def test_only_one_item_may_cross_protected_boundary(self):
        original = ["a", "b", "c", "d", "e", "f"]
        preferred = ["f", "e", "d", "a", "b", "c"]
        result = promote_one(original, preferred, protected=3)
        self.assertEqual(result[:3], ["a", "b", "c"])
        self.assertEqual(result[3], "f")
        self.assertEqual(set(result), set(original))
        self.assertEqual(len(result), len(original))


if __name__ == "__main__":
    unittest.main()

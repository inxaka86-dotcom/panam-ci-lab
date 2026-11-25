"""Deterministic unit tests. These must fail before the agent repairs buggy.py."""
import unittest
from buggy import priority_bucket


class PriorityBucketTests(unittest.TestCase):
    def test_low(self):
        self.assertEqual(priority_bucket(0), "low")
        self.assertEqual(priority_bucket(4), "low")

    def test_exact_medium_boundary(self):
        self.assertEqual(priority_bucket(5), "medium")

    def test_medium(self):
        self.assertEqual(priority_bucket(9), "medium")

    def test_exact_high_boundary(self):
        self.assertEqual(priority_bucket(10), "high")

    def test_high(self):
        self.assertEqual(priority_bucket(11), "high")
        self.assertEqual(priority_bucket(100), "high")


if __name__ == "__main__":
    unittest.main()

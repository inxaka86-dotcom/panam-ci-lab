"""Read-only acceptance tests for the numeric helper."""
import unittest
from src.numbers import clamp


class NumberTests(unittest.TestCase):
    def test_below_minimum(self):
        self.assertEqual(clamp(-3, 0, 10), 0)

    def test_above_maximum(self):
        self.assertEqual(clamp(13, 0, 10), 10)

    def test_inside(self):
        self.assertEqual(clamp(7, 0, 10), 7)

    def test_boundaries(self):
        self.assertEqual(clamp(0, 0, 10), 0)
        self.assertEqual(clamp(10, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()

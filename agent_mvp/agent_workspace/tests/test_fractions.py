"""Read-only tests for new-module creation by the autonomous coding agent."""
import unittest
from src.fractions import safe_divide


class FractionTests(unittest.TestCase):
    def test_regular_division(self):
        self.assertEqual(safe_divide(9, 2), 4.5)

    def test_negative_division(self):
        self.assertEqual(safe_divide(-8, 4), -2)

    def test_division_by_zero(self):
        self.assertIsNone(safe_divide(5, 0))


if __name__ == "__main__":
    unittest.main()

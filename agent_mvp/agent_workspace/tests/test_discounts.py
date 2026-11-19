"""Read-only acceptance tests for the Sol 6.2 coding agent smoke test."""
import unittest
from src.discounts import discounted_total


class DiscountTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(discounted_total(200, 10), 180)

    def test_decimal(self):
        self.assertEqual(discounted_total(75, 20), 60)

    def test_zero_percent(self):
        self.assertEqual(discounted_total(100, 0), 100)

    def test_full_discount(self):
        self.assertEqual(discounted_total(75, 100), 0)

    def test_invalid_percent(self):
        with self.assertRaises(ValueError):
            discounted_total(100, 110)

    def test_invalid_price(self):
        with self.assertRaises(ValueError):
            discounted_total(-1, 10)


if __name__ == "__main__":
    unittest.main()

"""Read-only acceptance tests for the text helper."""
import unittest
from src.text_ops import slugify


class TextOpsTests(unittest.TestCase):
    def test_punctuation(self):
        self.assertEqual(slugify("Hello, World!"), "hello-world")

    def test_whitespace(self):
        self.assertEqual(slugify("  A   B "), "a-b")

    def test_existing_hyphen(self):
        self.assertEqual(slugify("Already-Clean"), "already-clean")


if __name__ == "__main__":
    unittest.main()

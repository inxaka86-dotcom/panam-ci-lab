"""Read-only acceptance test for a real GitHub Issue -> AutoCoder task.

The module intentionally does not exist before the first trusted Issue run.
"""
import unittest
from src.labels import normalize_labels


class LabelsTests(unittest.TestCase):
    def test_trim_lowercase_and_deduplicate(self):
        self.assertEqual(
            normalize_labels([" Work ", "urgent", "work", "URGENT", "new"]),
            "work, urgent, new",
        )

    def test_empty_labels_ignored(self):
        self.assertEqual(normalize_labels(["", "  ", "A", ""]), "a")

    def test_empty_input(self):
        self.assertEqual(normalize_labels([]), "")

    def test_first_occurrence_order(self):
        self.assertEqual(normalize_labels(["B", "A", "b", "a", "C"]), "b, a, c")

    def test_single_word(self):
        self.assertEqual(normalize_labels([" Pending "]), "pending")


if __name__ == "__main__":
    unittest.main()

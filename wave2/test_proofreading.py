import unittest

from wave2.proofreading import diagnostics, exact_correction_score, normalize_spacing


class ProofreadingTests(unittest.TestCase):
    def test_spacing_normalization(self):
        self.assertEqual(normalize_spacing("Draft  text ."), "Draft text.")

    def test_diagnostics(self):
        issues = diagnostics("word  word , next")
        self.assertIn("DOUBLE_SPACE", issues)
        self.assertIn("SPACE_BEFORE_PUNCTUATION", issues)
        self.assertIn("DUPLICATE_WORD", issues)

    def test_exact_score(self):
        self.assertEqual(exact_correction_score("Alpha  beta .", "Alpha beta."), 1.0)
        self.assertEqual(exact_correction_score("Alpha beta", "Alpha gamma"), 0.0)


if __name__ == "__main__":
    unittest.main()

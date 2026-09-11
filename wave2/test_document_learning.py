import unittest

from wave2.document_learning import (
    MIN_DISTINCT_REFERENCE_EVIDENCE,
    accept_rule,
    accept_rule_from_pairs,
    build_revision_pair,
    can_accept_rule,
    classify_change,
    qualified_pair_ids,
    qualify_revision_pair,
    sha256_text,
    validate_reference,
)


class DocumentLearningSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.final_text = "Agenda item 1\nSubmit a concise written recommendation by Friday.\n"
        self.reference = {
            "reference_id": "REF-SYN-001",
            "status": "APPROVED_REFERENCE",
            "content_sha256": sha256_text(self.final_text),
            "review_receipt_sha256": "b" * 64,
        }
        self.references = {self.reference["reference_id"]: self.reference}

    def _pair(self, pair_id="P1"):
        pair = build_revision_pair(
            "Agenda item 1\nPrepare a detailed note next week.\n",
            self.final_text,
            pair_id=pair_id,
            draft_id=f"DRAFT-{pair_id}",
            final_reference=self.reference,
            document_type="meeting_record",
        )
        return classify_change(pair, 0, category="decision_phrasing", manual_verified=True)

    def _rule(self, **overrides):
        candidate = {
            "rule_id": "RULE-SYN-6",
            "status": "CANDIDATE",
            "category": "decision_phrasing",
            "manual_verified": True,
            "evidence_pair_ids": ["P1", "P2", "P3"],
            "contradiction_count": 0,
            "before_pattern": "look into the issue",
            "after_pattern": "review the issue and submit recommendations",
        }
        candidate.update(overrides)
        return candidate

    def test_reference_requires_exact_approved_status(self):
        self.assertEqual(validate_reference(self.reference), self.reference)
        with self.assertRaisesRegex(ValueError, "not an approved reference"):
            validate_reference({**self.reference, "status": "DRAFT"})

    def test_reference_rejects_invalid_digest(self):
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            validate_reference({**self.reference, "content_sha256": "not-a-digest"})

    def test_revision_pair_requires_final_text_digest_match(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_revision_pair(
                "Agenda item 1\nWrite something.\n",
                self.final_text + "extra",
                pair_id="PAIR-1",
                draft_id="DRAFT-1",
                final_reference=self.reference,
                document_type="meeting_record",
            )

    def test_revision_pair_is_deterministic_and_review_required(self):
        pair = build_revision_pair(
            "Agenda item 1\nPrepare a detailed note next week.\n",
            self.final_text,
            pair_id="PAIR-1",
            draft_id="DRAFT-1",
            final_reference=self.reference,
            document_type="meeting_record",
        )
        self.assertEqual(pair["learning_state"], "REVIEW_REQUIRED")
        self.assertEqual(pair["metrics"]["changed_blocks"], 1)
        self.assertEqual(pair["changes"][0]["classification"], "UNCLASSIFIED_REQUIRES_REVIEW")
        self.assertEqual(pair["final"]["content_sha256"], self.reference["content_sha256"])

    def test_change_classification_requires_manual_verification(self):
        pair = build_revision_pair(
            "Agenda item 1\nPrepare a detailed note next week.\n",
            self.final_text,
            pair_id="PAIR-1",
            draft_id="DRAFT-1",
            final_reference=self.reference,
            document_type="meeting_record",
        )
        with self.assertRaisesRegex(ValueError, "manual verification"):
            classify_change(pair, 0, category="wording", manual_verified=False)

    def test_reviewed_pair_moves_to_reviewed_state(self):
        pair = self._pair("P1")
        self.assertEqual(pair["learning_state"], "REVIEWED")
        self.assertEqual(pair["changes"][0]["classification"], "decision_phrasing")

    def test_qualify_pair_rejects_unreviewed_pair(self):
        pair = build_revision_pair(
            "Agenda item 1\nPrepare a detailed note next week.\n",
            self.final_text,
            pair_id="P1",
            draft_id="DRAFT-P1",
            final_reference=self.reference,
            document_type="meeting_record",
        )
        with self.assertRaisesRegex(ValueError, "not fully reviewed"):
            qualify_revision_pair(pair, self.references)

    def test_qualify_pair_rejects_reference_provenance_tampering(self):
        pair = self._pair("P1")
        pair["final"]["review_receipt_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            qualify_revision_pair(pair, self.references)

    def test_qualified_pair_ids_reject_duplicate_ids(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            qualified_pair_ids([self._pair("P1"), self._pair("P1")], self.references)

    def test_substantive_change_is_never_reusable_rule(self):
        candidate = self._rule(
            rule_id="RULE-SYN-1",
            category="factual_legal_substantive",
            before_pattern="old fact",
            after_pattern="corrected fact",
        )
        allowed, reasons = can_accept_rule(candidate, {"P1", "P2", "P3"})
        self.assertFalse(allowed)
        self.assertTrue(any("not reusable" in reason for reason in reasons))

    def test_style_rule_requires_three_distinct_qualified_pairs(self):
        candidate = self._rule(evidence_pair_ids=["P1", "P2"])
        allowed, reasons = can_accept_rule(candidate, {"P1", "P2"})
        self.assertFalse(allowed)
        self.assertTrue(any(str(MIN_DISTINCT_REFERENCE_EVIDENCE) in reason for reason in reasons))

    def test_style_rule_requires_nonempty_distinct_patterns(self):
        candidate = self._rule(
            rule_id="RULE-SYN-3",
            category="style_grammar",
            before_pattern="same",
            after_pattern="same",
        )
        allowed, reasons = can_accept_rule(candidate, {"P1", "P2", "P3"})
        self.assertFalse(allowed)
        self.assertTrue(any("must differ" in reason for reason in reasons))

    def test_style_rule_rejects_unqualified_evidence(self):
        candidate = self._rule(rule_id="RULE-SYN-4", category="exclusion")
        allowed, reasons = can_accept_rule(candidate, {"P1", "P2"})
        self.assertFalse(allowed)
        self.assertTrue(any("qualified" in reason for reason in reasons))

    def test_style_rule_rejects_nonzero_or_boolean_contradictions(self):
        for bad in (1, True, None):
            candidate = self._rule(contradiction_count=bad)
            allowed, _ = can_accept_rule(candidate, {"P1", "P2", "P3"})
            self.assertFalse(allowed)

    def test_verified_style_rule_can_be_accepted_without_mutating_candidate(self):
        candidate = self._rule()
        accepted = accept_rule(candidate, {"P1", "P2", "P3"})
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertEqual(candidate["status"], "CANDIDATE")
        self.assertEqual(
            accepted["acceptance_policy"]["minimum_distinct_reference_evidence"],
            MIN_DISTINCT_REFERENCE_EVIDENCE,
        )

    def test_preferred_acceptance_validates_pair_objects(self):
        candidate = self._rule()
        pairs = [self._pair("P1"), self._pair("P2"), self._pair("P3")]
        accepted = accept_rule_from_pairs(candidate, pairs, self.references)
        self.assertEqual(accepted["status"], "ACCEPTED")
        self.assertTrue(accepted["acceptance_policy"]["reviewed_pair_qualification_required"])

    def test_preferred_acceptance_rejects_unreviewed_evidence(self):
        pairs = [self._pair("P1"), self._pair("P2")]
        unreviewed = build_revision_pair(
            "Agenda item 1\nPrepare a detailed note next week.\n",
            self.final_text,
            pair_id="P3",
            draft_id="DRAFT-P3",
            final_reference=self.reference,
            document_type="meeting_record",
        )
        with self.assertRaisesRegex(ValueError, "not fully reviewed"):
            accept_rule_from_pairs(self._rule(), pairs + [unreviewed], self.references)


if __name__ == "__main__":
    unittest.main()

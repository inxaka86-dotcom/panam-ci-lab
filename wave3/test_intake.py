import unittest

from wave2.document_learning import sha256_text
from wave3.intake import (
    AWAITING_REFERENCE,
    AWAITING_TEXT,
    FINAL_STATUS,
    INTEGRITY_CONFLICT,
    MATCHED,
    READY_FOR_CHANGE_REVIEW,
    REVIEW_REQUIRED,
    UNPAIRED,
    new_metrics,
    process_intake,
    resolve_draft,
    update_metrics,
)


class SyntheticIntakeTests(unittest.TestCase):
    def setUp(self):
        self.draft_text = "Agenda item 1\nPrepare a detailed note next week.\n"
        self.final_text = "Agenda item 1\nSubmit a concise written recommendation by Friday.\n"
        self.draft = {
            "draft_id": "DRAFT-SYN-1",
            "status": "SYNTHETIC_DRAFT",
            "document_type": "meeting_record",
            "artifact_id": "ART-SYN-1",
            "source_id": "SRC-SYN-1",
            "correlation_id": "CORR-SYN-1",
            "text_sha256": sha256_text(self.draft_text),
        }
        self.drafts = {"drafts": [self.draft]}
        self.reference = {
            "reference_id": "REF-SYN-1",
            "status": "APPROVED_REFERENCE",
            "store_id": "STORE-SYN-1",
            "content_sha256": sha256_text(self.final_text),
            "review_receipt_sha256": "b" * 64,
        }
        self.references = {"references": [self.reference]}
        self.request = {
            "intake_id": "INTAKE-SYN-1",
            "final_status": FINAL_STATUS,
            "document_type": "meeting_record",
            "reference_id": "REF-SYN-1",
            "reference_store_id": "STORE-SYN-1",
            "source_id": "SRC-SYN-1",
        }

    def test_unique_exact_source_match(self):
        out = resolve_draft(self.request, self.drafts)
        self.assertEqual(out["status"], MATCHED)
        self.assertEqual(out["draft"]["draft_id"], "DRAFT-SYN-1")

    def test_no_match_is_unpaired(self):
        out = resolve_draft({**self.request, "source_id": "OTHER"}, self.drafts)
        self.assertEqual(out["status"], UNPAIRED)

    def test_ambiguous_match_requires_review(self):
        other = {**self.draft, "draft_id": "DRAFT-SYN-2", "artifact_id": "ART-SYN-2", "correlation_id": "CORR-SYN-2"}
        out = resolve_draft(self.request, {"drafts": [self.draft, other]})
        self.assertEqual(out["status"], REVIEW_REQUIRED)
        self.assertEqual(out["reason"], "AMBIGUOUS_EXACT_MATCH")

    def test_conflicting_exact_keys_require_review(self):
        other = {**self.draft, "draft_id": "DRAFT-SYN-2", "artifact_id": "ART-SYN-2", "source_id": "SRC-SYN-2", "correlation_id": "CORR-SYN-2"}
        request = {**self.request, "correlation_id": "CORR-SYN-2"}
        out = resolve_draft(request, {"drafts": [self.draft, other]})
        self.assertEqual(out["status"], REVIEW_REQUIRED)
        self.assertEqual(out["reason"], "LINKAGE_CONFLICT")

    def test_document_type_conflict_requires_review(self):
        request = {**self.request, "draft_id_hint": "DRAFT-SYN-1", "document_type": "briefing"}
        out = resolve_draft(request, self.drafts)
        self.assertEqual(out["status"], REVIEW_REQUIRED)
        self.assertEqual(out["reason"], "DOCUMENT_TYPE_CONFLICT")

    def test_unapproved_reference_waits(self):
        refs = {"references": [{**self.reference, "status": "PENDING"}]}
        out = process_intake(self.request, self.drafts, refs, draft_text=self.draft_text, final_text=self.final_text)
        self.assertEqual(out["intake_state"], AWAITING_REFERENCE)
        self.assertNotIn("revision_pair", out)

    def test_missing_text_waits(self):
        out = process_intake(self.request, self.drafts, self.references)
        self.assertEqual(out["intake_state"], AWAITING_TEXT)

    def test_reference_store_mismatch_stops(self):
        request = {**self.request, "reference_store_id": "OTHER"}
        out = process_intake(request, self.drafts, self.references, draft_text=self.draft_text, final_text=self.final_text)
        self.assertEqual(out["intake_state"], INTEGRITY_CONFLICT)
        self.assertEqual(out["reason"], "REFERENCE_STORE_ID_MISMATCH")

    def test_draft_hash_mismatch_stops(self):
        out = process_intake(self.request, self.drafts, self.references, draft_text="tampered", final_text=self.final_text)
        self.assertEqual(out["intake_state"], INTEGRITY_CONFLICT)
        self.assertEqual(out["reason"], "DRAFT_TEXT_SHA256_MISMATCH")

    def test_final_text_digest_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            process_intake(
                self.request,
                self.drafts,
                self.references,
                draft_text=self.draft_text,
                final_text=self.final_text + "tampered",
            )

    def test_success_prepares_unclassified_review_queue(self):
        out = process_intake(self.request, self.drafts, self.references, draft_text=self.draft_text, final_text=self.final_text)
        self.assertEqual(out["intake_state"], READY_FOR_CHANGE_REVIEW)
        self.assertEqual(out["revision_pair"]["learning_state"], "REVIEW_REQUIRED")
        self.assertEqual(out["review_queue"][0]["classification"], "UNCLASSIFIED_REQUIRES_REVIEW")

    def test_explicit_pair_id_is_preserved(self):
        out = process_intake(
            {**self.request, "pair_id": "PAIR-CUSTOM"},
            self.drafts,
            self.references,
            draft_text=self.draft_text,
            final_text=self.final_text,
        )
        self.assertEqual(out["revision_pair"]["pair_id"], "PAIR-CUSTOM")

    def test_metrics_reject_double_counting(self):
        out = process_intake(self.request, self.drafts, self.references, draft_text=self.draft_text, final_text=self.final_text)
        metrics = update_metrics(new_metrics(), out)
        self.assertEqual(metrics["total"], 1)
        self.assertEqual(metrics["prepared_pairs"], 1)
        with self.assertRaisesRegex(ValueError, "already counted"):
            update_metrics(metrics, out)

    def test_nonmatched_case_never_builds_pair(self):
        out = process_intake({**self.request, "source_id": "OTHER"}, self.drafts, self.references)
        self.assertEqual(out["intake_state"], UNPAIRED)
        self.assertNotIn("revision_pair", out)


if __name__ == "__main__":
    unittest.main()

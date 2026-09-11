import unittest

from wave2.document_learning import sha256_text
from wave4.storage_lineage import (
    ALREADY_REGISTERED,
    REGISTERED,
    normalize_snapshot,
    prepare_intake_from_storage,
    register_draft,
    validate_trigger_mode,
)


class StorageLineageSyntheticTests(unittest.TestCase):
    def setUp(self):
        self.registry = {"drafts": []}
        self.draft_text = "Agenda item 1\nPrepare a detailed note next week.\n"
        self.final_text = "Agenda item 1\nSubmit a concise written recommendation by Friday.\n"
        self.kw = dict(
            draft_id="DRAFT-SYN-1",
            artifact_id="ART-SYN-1",
            store_id="STORE-DRAFT-1",
            draft_text=self.draft_text,
            source_id="SOURCE-SYN-1",
            correlation_id="CORR-SYN-1",
            display_name="draft-one.txt",
            storage_revision="rev-1",
        )
        self.reference = {
            "reference_id": "REF-SYN-1",
            "status": "APPROVED_REFERENCE",
            "content_sha256": sha256_text(self.final_text),
            "review_receipt_sha256": "b" * 64,
            "store_id": "STORE-FINAL-1",
        }
        self.references = {"references": [self.reference]}

    def _registered(self):
        return register_draft(self.registry, **self.kw)

    def _request(self):
        return {
            "intake_id": "INTAKE-SYN-1",
            "document_type": "meeting_record",
            "final_status": "APPROVED_FINAL",
            "reference_id": "REF-SYN-1",
            "reference_store_id": "STORE-FINAL-1",
            "draft_id_hint": "DRAFT-SYN-1",
        }

    def _snapshots(self):
        return (
            normalize_snapshot(
                provider="synthetic_store",
                store_id="STORE-DRAFT-1",
                text=self.draft_text,
            ),
            normalize_snapshot(
                provider="synthetic_store",
                store_id="STORE-FINAL-1",
                text=self.final_text,
            ),
        )

    def test_registry_never_persists_raw_text(self):
        result = self._registered()
        self.assertEqual(result["status"], REGISTERED)
        self.assertNotIn("draft_text", result["entry"])
        self.assertNotIn(self.draft_text, str(result["registry"]))

    def test_exact_reregistration_is_idempotent(self):
        first = self._registered()
        second = register_draft(first["registry"], **self.kw)
        self.assertEqual(second["status"], ALREADY_REGISTERED)
        self.assertEqual(len(second["registry"]["drafts"]), 1)

    def test_display_name_is_not_identity_authority(self):
        first = self._registered()
        second = register_draft(
            first["registry"], **dict(self.kw, display_name="renamed.txt")
        )
        self.assertEqual(second["status"], ALREADY_REGISTERED)

    def test_changed_text_for_same_draft_fails_closed(self):
        first = self._registered()
        with self.assertRaisesRegex(ValueError, "immutable metadata"):
            register_draft(first["registry"], **dict(self.kw, draft_text="different"))

    def test_changed_revision_for_same_draft_fails_closed(self):
        first = self._registered()
        with self.assertRaisesRegex(ValueError, "storage_revision"):
            register_draft(first["registry"], **dict(self.kw, storage_revision="rev-2"))

    def test_storage_id_cannot_back_two_draft_ids(self):
        first = self._registered()
        with self.assertRaisesRegex(ValueError, "store_id"):
            register_draft(
                first["registry"],
                **dict(self.kw, draft_id="DRAFT-SYN-2", artifact_id="ART-SYN-2"),
            )

    def test_same_source_can_have_multiple_drafts(self):
        first = self._registered()
        second = register_draft(
            first["registry"],
            **dict(
                self.kw,
                draft_id="DRAFT-SYN-2",
                artifact_id="ART-SYN-2",
                store_id="STORE-DRAFT-2",
                correlation_id="CORR-SYN-2",
            ),
        )
        self.assertEqual(len(second["registry"]["drafts"]), 2)

    def test_background_trigger_modes_are_rejected(self):
        for mode in ("background_watcher", "autonomous_scan", "scheduled_poll"):
            with self.assertRaisesRegex(ValueError, "not authorized"):
                validate_trigger_mode(mode)

    def test_explicit_trigger_modes_are_allowed(self):
        for mode in ("owner_explicit", "approved_workflow", "manual_operator"):
            self.assertEqual(validate_trigger_mode(mode), mode)

    def test_snapshot_expected_id_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, "expected_store_id"):
            normalize_snapshot(
                provider="synthetic_store",
                store_id="A",
                expected_store_id="B",
                text="text",
            )

    def test_success_delegates_to_wave3_and_keeps_edits_unclassified(self):
        reg = self._registered()["registry"]
        draft, final = self._snapshots()
        outcome = prepare_intake_from_storage(
            self._request(), reg, self.references,
            draft_snapshot=draft, final_snapshot=final,
        )
        self.assertEqual(outcome["intake_state"], "READY_FOR_CHANGE_REVIEW")
        self.assertTrue(outcome["review_queue"])
        self.assertTrue(all(
            item["classification"] == "UNCLASSIFIED_REQUIRES_REVIEW"
            for item in outcome["review_queue"]
        ))

    def test_draft_storage_id_mismatch_fails_closed(self):
        reg = self._registered()["registry"]
        draft, final = self._snapshots()
        draft["store_id"] = "WRONG"
        outcome = prepare_intake_from_storage(
            self._request(), reg, self.references,
            draft_snapshot=draft, final_snapshot=final,
        )
        self.assertEqual(outcome["reason"], "DRAFT_STORAGE_ID_MISMATCH")

    def test_draft_hash_mismatch_fails_closed(self):
        reg = self._registered()["registry"]
        draft, final = self._snapshots()
        draft["text_sha256"] = "0" * 64
        outcome = prepare_intake_from_storage(
            self._request(), reg, self.references,
            draft_snapshot=draft, final_snapshot=final,
        )
        self.assertEqual(outcome["reason"], "DRAFT_STORAGE_TEXT_SHA256_MISMATCH")

    def test_final_storage_id_mismatch_fails_closed(self):
        reg = self._registered()["registry"]
        draft, final = self._snapshots()
        final["store_id"] = "WRONG"
        outcome = prepare_intake_from_storage(
            self._request(), reg, self.references,
            draft_snapshot=draft, final_snapshot=final,
        )
        self.assertEqual(outcome["reason"], "FINAL_STORAGE_ID_MISMATCH")

    def test_missing_snapshots_preserve_wave3_wait_state(self):
        reg = self._registered()["registry"]
        outcome = prepare_intake_from_storage(
            self._request(), reg, self.references,
            draft_snapshot=None, final_snapshot=None,
        )
        self.assertEqual(outcome["intake_state"], "AWAITING_TEXT")


if __name__ == "__main__":
    unittest.main()

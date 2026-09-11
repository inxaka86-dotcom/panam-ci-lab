import hashlib
import json
import unittest

from wave2.document_learning import sha256_text
from wave4.storage_lineage import normalize_snapshot, prepare_intake_from_storage
from wave5.generation_hook import (
    APPROVED_WORKFLOW_TRIGGER,
    HOOK_ALREADY_PROCESSED,
    HOOK_DRAFT_ALREADY_REGISTERED,
    HOOK_NOT_STORED,
    HOOK_REGISTERED,
    new_hook_registry,
    process_save_event,
    validate_hook_registry,
    validate_save_receipt,
)

TEXT = "Agenda item 1\nPrepare a detailed note next week.\n"
DIGEST = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def draft_registry():
    return {"drafts": []}


def receipt(**overrides):
    value = {
        "event_id": "SAVE-SYN-001",
        "save_status": "STORED",
        "document_type": "meeting_record",
        "storage_provider": "synthetic_store",
        "draft_id": "DRAFT-SYN-1",
        "artifact_id": "ART-SYN-1",
        "store_id": "STORE-DRAFT-1",
        "storage_revision": "rev-1",
        "source_id": "SOURCE-SYN-1",
        "correlation_id": "CORR-SYN-1",
        "text_sha256": DIGEST,
        "display_name": "draft-one.txt",
        "stored_at": "2026-09-11T08:00:00Z",
    }
    value.update(overrides)
    return value


class GenerationHookSyntheticTests(unittest.TestCase):
    def test_success_registers_lineage_and_event(self):
        result = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        self.assertEqual(HOOK_REGISTERED, result["status"])
        self.assertEqual(1, len(result["draft_registry"]["drafts"]))
        self.assertEqual(1, len(result["hook_registry"]["processed_events"]))
        self.assertEqual(
            APPROVED_WORKFLOW_TRIGGER,
            result["draft_entry"]["registration_trigger"],
        )

    def test_full_chain_reaches_wave3_review_queue(self):
        result = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        final_text = "Agenda item 1\nSubmit a concise written recommendation by Friday.\n"
        references = {
            "references": [{
                "reference_id": "REF-SYN-1",
                "status": "APPROVED_REFERENCE",
                "content_sha256": sha256_text(final_text),
                "review_receipt_sha256": "b" * 64,
                "store_id": "STORE-FINAL-1",
            }]
        }
        request = {
            "intake_id": "INTAKE-SYN-1",
            "document_type": "meeting_record",
            "final_status": "APPROVED_FINAL",
            "reference_id": "REF-SYN-1",
            "reference_store_id": "STORE-FINAL-1",
            "draft_id_hint": "DRAFT-SYN-1",
        }
        outcome = prepare_intake_from_storage(
            request,
            result["draft_registry"],
            references,
            draft_snapshot=normalize_snapshot(
                provider="synthetic_store",
                store_id="STORE-DRAFT-1",
                text=TEXT,
            ),
            final_snapshot=normalize_snapshot(
                provider="synthetic_store",
                store_id="STORE-FINAL-1",
                text=final_text,
            ),
            trigger_mode="approved_workflow",
        )
        self.assertEqual("READY_FOR_CHANGE_REVIEW", outcome["intake_state"])
        self.assertTrue(outcome["review_queue"])
        self.assertTrue(all(
            item["classification"] == "UNCLASSIFIED_REQUIRES_REVIEW"
            for item in outcome["review_queue"]
        ))

    def test_raw_text_never_persisted_in_hook_ledger(self):
        result = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        serialized = json.dumps(result["hook_registry"])
        self.assertNotIn(TEXT, serialized)

    def test_failed_save_never_registers(self):
        result = process_save_event(
            receipt(
                save_status="FAILED",
                store_id=None,
                storage_revision=None,
                text_sha256=None,
                source_id=None,
                correlation_id=None,
            ),
            text=None,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        self.assertEqual(HOOK_NOT_STORED, result["status"])
        self.assertEqual([], result["draft_registry"]["drafts"])
        self.assertEqual([], result["hook_registry"]["processed_events"])

    def test_hash_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            process_save_event(
                receipt(text_sha256="0" * 64),
                text=TEXT,
                draft_registry=draft_registry(),
                hook_registry=new_hook_registry(),
            )

    def test_stored_event_requires_storage_identity(self):
        for field in ("store_id", "storage_revision", "text_sha256"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validate_save_receipt(receipt(**{field: None}))

    def test_stored_event_requires_exact_linkage_key(self):
        with self.assertRaises(ValueError):
            validate_save_receipt(receipt(source_id=None, correlation_id=None))

    def test_document_type_is_bounded(self):
        with self.assertRaises(ValueError):
            validate_save_receipt(receipt(document_type="other"))

    def test_storage_provider_is_bounded(self):
        with self.assertRaises(ValueError):
            validate_save_receipt(receipt(storage_provider="other"))

    def test_exact_event_replay_is_idempotent(self):
        first = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        second = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=first["draft_registry"],
            hook_registry=first["hook_registry"],
        )
        self.assertEqual(HOOK_ALREADY_PROCESSED, second["status"])
        self.assertEqual(1, len(second["draft_registry"]["drafts"]))
        self.assertEqual(1, len(second["hook_registry"]["processed_events"]))

    def test_same_event_id_different_identity_fails_closed(self):
        first = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        with self.assertRaises(ValueError):
            process_save_event(
                receipt(store_id="STORE-OTHER"),
                text=TEXT,
                draft_registry=first["draft_registry"],
                hook_registry=first["hook_registry"],
            )

    def test_new_event_for_same_exact_draft_does_not_duplicate_draft(self):
        first = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        second = process_save_event(
            receipt(event_id="SAVE-SYN-002"),
            text=TEXT,
            draft_registry=first["draft_registry"],
            hook_registry=first["hook_registry"],
        )
        self.assertEqual(HOOK_DRAFT_ALREADY_REGISTERED, second["status"])
        self.assertEqual(1, len(second["draft_registry"]["drafts"]))
        self.assertEqual(2, len(second["hook_registry"]["processed_events"]))

    def test_new_event_cannot_rebind_same_draft(self):
        first = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        with self.assertRaises(ValueError):
            process_save_event(
                receipt(event_id="SAVE-SYN-002", store_id="STORE-OTHER"),
                text=TEXT,
                draft_registry=first["draft_registry"],
                hook_registry=first["hook_registry"],
            )

    def test_display_name_is_not_event_identity(self):
        first = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )
        second = process_save_event(
            receipt(display_name="renamed.txt"),
            text=TEXT,
            draft_registry=first["draft_registry"],
            hook_registry=first["hook_registry"],
        )
        self.assertEqual(HOOK_ALREADY_PROCESSED, second["status"])

    def test_stored_event_requires_nonempty_text(self):
        with self.assertRaises(ValueError):
            process_save_event(
                receipt(),
                text="",
                draft_registry=draft_registry(),
                hook_registry=new_hook_registry(),
            )

    def test_invalid_digest_rejected(self):
        with self.assertRaises(ValueError):
            validate_save_receipt(receipt(text_sha256="not-a-sha"))

    def test_duplicate_event_registry_rejected(self):
        good = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )["event"]
        registry = new_hook_registry()
        registry["processed_events"] = [good, dict(good)]
        with self.assertRaises(ValueError):
            validate_hook_registry(registry)

    def test_tampered_event_registry_rejected(self):
        good = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )["event"]
        good["store_id"] = "STORE-TAMPERED"
        registry = new_hook_registry()
        registry["processed_events"] = [good]
        with self.assertRaises(ValueError):
            validate_hook_registry(registry)

    def test_raw_text_field_in_registry_rejected(self):
        good = process_save_event(
            receipt(),
            text=TEXT,
            draft_registry=draft_registry(),
            hook_registry=new_hook_registry(),
        )["event"]
        good["raw_text"] = TEXT
        registry = new_hook_registry()
        registry["processed_events"] = [good]
        with self.assertRaises(ValueError):
            validate_hook_registry(registry)


if __name__ == "__main__":
    unittest.main()

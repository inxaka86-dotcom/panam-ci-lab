import hashlib
import unittest
from unittest.mock import patch

from wave2.document_learning import sha256_text
from wave4.storage_lineage import normalize_snapshot, prepare_intake_from_storage
from wave6.protocol_commit import (
    ALREADY_COMMITTED,
    COMMITTED,
    RECEIPT_CONFLICT_REQUIRES_REVIEW,
    SAVE_NOT_STORED,
    STORED_AWAITING_LINEAGE,
    commit_artifact,
    new_commit_registry,
    validate_commit_registry,
)

TEXT = "Agenda item 1\nPrepare a detailed note next week.\n"
DIGEST = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


def req(**overrides):
    value = {
        "operation_id": "OP-SYN-1",
        "event_id": "SAVE-SYN-1",
        "document_type": "meeting_record",
        "storage_provider": "synthetic_store",
        "draft_id": "DRAFT-SYN-1",
        "artifact_id": "ART-SYN-1",
        "source_id": "SOURCE-SYN-1",
        "correlation_id": "CORR-SYN-1",
        "text_sha256": DIGEST,
        "display_name": "draft-one.txt",
    }
    value.update(overrides)
    return value


def stored(request=None, **overrides):
    request = request or req()
    value = {
        "event_id": request["event_id"],
        "save_status": "STORED",
        "document_type": request["document_type"],
        "storage_provider": request["storage_provider"],
        "draft_id": request["draft_id"],
        "artifact_id": request["artifact_id"],
        "store_id": "STORE-DRAFT-1",
        "storage_revision": "rev-1",
        "source_id": request.get("source_id"),
        "correlation_id": request.get("correlation_id"),
        "text_sha256": request["text_sha256"],
        "display_name": request.get("display_name"),
        "stored_at": "2026-09-11T08:01:00Z",
    }
    value.update(overrides)
    return value


def drafts(): return {"drafts": []}
def hooks(): return {"schema_version": 1, "processed_events": []}


class ProtocolCommitSyntheticTests(unittest.TestCase):
    def test_success_commits_once(self):
        calls = []
        def writer(request, text): calls.append(1); return stored(request)
        result = commit_artifact(
            req(), text=TEXT, storage_writer=writer,
            draft_registry=drafts(), hook_registry=hooks(),
            commit_registry=new_commit_registry(),
        )
        self.assertEqual(COMMITTED, result["status"])
        self.assertEqual(1, len(calls))

    def test_full_chain_reaches_wave3_review_queue(self):
        def writer(request, text): return stored(request)
        committed = commit_artifact(
            req(), text=TEXT, storage_writer=writer,
            draft_registry=drafts(), hook_registry=hooks(),
            commit_registry=new_commit_registry(),
        )
        final_text = "Agenda item 1\nSubmit a concise written recommendation by Friday.\n"
        references = {"references": [{
            "reference_id": "REF-SYN-1",
            "status": "APPROVED_REFERENCE",
            "content_sha256": sha256_text(final_text),
            "review_receipt_sha256": "b" * 64,
            "store_id": "STORE-FINAL-1",
        }]}
        request = {
            "intake_id": "INTAKE-SYN-1",
            "document_type": "meeting_record",
            "final_status": "APPROVED_FINAL",
            "reference_id": "REF-SYN-1",
            "reference_store_id": "STORE-FINAL-1",
            "draft_id_hint": "DRAFT-SYN-1",
        }
        outcome = prepare_intake_from_storage(
            request, committed["draft_registry"], references,
            draft_snapshot=normalize_snapshot(
                provider="synthetic_store", store_id="STORE-DRAFT-1", text=TEXT,
            ),
            final_snapshot=normalize_snapshot(
                provider="synthetic_store", store_id="STORE-FINAL-1", text=final_text,
            ),
            trigger_mode="approved_workflow",
        )
        self.assertEqual("READY_FOR_CHANGE_REVIEW", outcome["intake_state"])
        self.assertTrue(all(
            item["classification"] == "UNCLASSIFIED_REQUIRES_REVIEW"
            for item in outcome["review_queue"]
        ))

    def test_committed_replay_never_calls_writer(self):
        first = commit_artifact(
            req(), text=TEXT, storage_writer=lambda r, t: stored(r),
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        def forbidden(*args): raise AssertionError("writer called")
        second = commit_artifact(
            req(), text=TEXT, storage_writer=forbidden,
            draft_registry=first["draft_registry"], hook_registry=first["hook_registry"],
            commit_registry=first["commit_registry"],
        )
        self.assertEqual(ALREADY_COMMITTED, second["status"])

    def test_digest_mismatch_fails_before_writer(self):
        calls = []
        def writer(*args): calls.append(1)
        with self.assertRaises(ValueError):
            commit_artifact(
                req(text_sha256="0" * 64), text=TEXT, storage_writer=writer,
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )
        self.assertEqual([], calls)

    def test_save_failure_is_terminal_without_reupload(self):
        def writer(r, t): return stored(r, save_status="FAILED", store_id=None, storage_revision=None)
        first = commit_artifact(
            req(), text=TEXT, storage_writer=writer,
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        self.assertEqual(SAVE_NOT_STORED, first["status"])
        def forbidden(*args): raise AssertionError("writer called")
        second = commit_artifact(
            req(), text=TEXT, storage_writer=forbidden,
            draft_registry=first["draft_registry"], hook_registry=first["hook_registry"],
            commit_registry=first["commit_registry"],
        )
        self.assertEqual(SAVE_NOT_STORED, second["status"])

    def test_receipt_conflict_blocks_automatic_continuation(self):
        first = commit_artifact(
            req(), text=TEXT, storage_writer=lambda r, t: stored(r, event_id="OTHER"),
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        self.assertEqual(RECEIPT_CONFLICT_REQUIRES_REVIEW, first["status"])
        def forbidden(*args): raise AssertionError("writer called")
        second = commit_artifact(
            req(), text=TEXT, storage_writer=forbidden,
            draft_registry=first["draft_registry"], hook_registry=first["hook_registry"],
            commit_registry=first["commit_registry"],
        )
        self.assertEqual(RECEIPT_CONFLICT_REQUIRES_REVIEW, second["status"])

    def test_lineage_failure_recovers_without_reupload(self):
        calls = []
        def writer(r, t): calls.append(1); return stored(r)
        with patch("wave6.protocol_commit.process_save_event", side_effect=ValueError("fail")):
            first = commit_artifact(
                req(), text=TEXT, storage_writer=writer,
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )
        self.assertEqual(STORED_AWAITING_LINEAGE, first["status"])
        def forbidden(*args): raise AssertionError("writer called during recovery")
        second = commit_artifact(
            req(), text=TEXT, storage_writer=forbidden,
            draft_registry=first["draft_registry"], hook_registry=first["hook_registry"],
            commit_registry=first["commit_registry"],
        )
        self.assertEqual(COMMITTED, second["status"])
        self.assertEqual(1, len(calls))

    def test_raw_text_not_persisted(self):
        result = commit_artifact(
            req(), text=TEXT, storage_writer=lambda r, t: stored(r),
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        self.assertNotIn(TEXT, str(result["commit_registry"]))

    def test_operation_rebind_rejected(self):
        first = commit_artifact(
            req(), text=TEXT, storage_writer=lambda r, t: stored(r),
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        with self.assertRaises(ValueError):
            commit_artifact(
                req(artifact_id="OTHER"), text=TEXT, storage_writer=lambda r, t: stored(r),
                draft_registry=first["draft_registry"], hook_registry=first["hook_registry"],
                commit_registry=first["commit_registry"],
            )

    def test_exact_linkage_required(self):
        with self.assertRaises(ValueError):
            commit_artifact(
                req(source_id=None, correlation_id=None), text=TEXT,
                storage_writer=lambda r, t: {}, draft_registry=drafts(), hook_registry=hooks(),
                commit_registry=new_commit_registry(),
            )

    def test_document_type_bounded(self):
        with self.assertRaises(ValueError):
            commit_artifact(
                req(document_type="other"), text=TEXT, storage_writer=lambda r, t: {},
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )

    def test_storage_provider_bounded(self):
        with self.assertRaises(ValueError):
            commit_artifact(
                req(storage_provider="other"), text=TEXT, storage_writer=lambda r, t: {},
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )

    def test_non_callable_writer_rejected(self):
        with self.assertRaises(ValueError):
            commit_artifact(
                req(), text=TEXT, storage_writer=None,
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )

    def test_tampered_registry_rejected(self):
        result = commit_artifact(
            req(), text=TEXT, storage_writer=lambda r, t: stored(r),
            draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
        )
        registry = result["commit_registry"]
        registry["operations"][0]["state"] = "TAMPERED"
        with self.assertRaises(ValueError): validate_commit_registry(registry)

    def test_writer_must_return_object(self):
        with self.assertRaises(ValueError):
            commit_artifact(
                req(), text=TEXT, storage_writer=lambda r, t: None,
                draft_registry=drafts(), hook_registry=hooks(), commit_registry=new_commit_registry(),
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from wave9.runtime_ipc import RuntimeClient
from wave11.protocol_pipeline import (
    ALREADY_PIPELINE_COMMITTED,
    GENERATED_AWAITING_COMMIT,
    GENERATION_CONFLICT_REQUIRES_REVIEW,
    PIPELINE_COMMITTED,
    StateStore,
    run_pipeline,
)

RULE_REGISTRY = {"schema_version": 1, "rules": []}
FIXTURE = Path(__file__).with_name("runtime_fixture.js")


class Wave11ProtocolPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.state_path = root / "pipeline-state.json"
        self.external_store_path = root / "external-store.json"
        self.state_store = StateStore(self.state_path)
        self.base = {
            "transcript_text": "Synthetic meeting transcript with one explicit decision.",
            "rule_registry": RULE_REGISTRY,
            "state_store": self.state_store,
            "pipeline_id": "pipeline-1",
            "generation_id": "generation-1",
            "operation_id": "operation-1",
            "event_id": "event-1",
            "draft_id": "draft-1",
            "artifact_id": "artifact-1",
            "source_id": "source-1",
            "correlation_id": "correlation-1",
            "display_name": "synthetic-protocol.txt",
            "requested_model": "synthetic-model",
            "trigger_mode": "approved_workflow",
        }

    def tearDown(self):
        self.temp.cleanup()

    def client(self, variant="A", mode="ok", fixture=FIXTURE):
        return RuntimeClient([
            "node",
            str(fixture),
            str(self.external_store_path),
            variant,
            mode,
        ])

    def execute_pipeline(self, client, **overrides):
        args = dict(self.base)
        args.update(overrides)
        transcript = args.pop("transcript_text")
        return run_pipeline(
            transcript,
            runtime_client=client,
            **args,
        )

    def test_full_cross_language_pipeline_commits_through_wave4_lineage(self):
        result = self.execute_pipeline(self.client("A", "ok"))
        self.assertEqual(result["status"], PIPELINE_COMMITTED)
        self.assertEqual(result["commit_result"]["status"], "COMMITTED")
        self.assertEqual(len(result["state"]["draft_registry"]["drafts"]), 1)
        draft = result["state"]["draft_registry"]["drafts"][0]
        self.assertEqual(draft["draft_id"], "draft-1")
        self.assertEqual(draft["source_id"], "source-1")

        external = json.loads(self.external_store_path.read_text(encoding="utf-8"))
        self.assertEqual(len(external["records"]), 1)

        state_raw = self.state_path.read_text(encoding="utf-8")
        external_raw = self.external_store_path.read_text(encoding="utf-8")
        self.assertNotIn(self.base["transcript_text"], state_raw)
        self.assertNotIn("Synthetic protocol draft A", state_raw)
        self.assertNotIn("Synthetic protocol draft A", external_raw)

    def test_background_watcher_rejected_before_any_subprocess(self):
        nonexistent = Path(self.temp.name) / "does-not-exist.js"
        with self.assertRaisesRegex(ValueError, "trigger mode is not authorized"):
            self.execute_pipeline(
                self.client(fixture=nonexistent),
                trigger_mode="background_watcher",
            )
        self.assertFalse(self.state_path.exists())
        self.assertFalse(self.external_store_path.exists())

    def test_storage_failure_leaves_durable_generation_checkpoint(self):
        with self.assertRaisesRegex(RuntimeError, "exit code 1"):
            self.execute_pipeline(self.client("A", "fail"))

        state = self.state_store.load()
        entry = state["pipeline_registry"]["operations"][0]
        self.assertEqual(entry["state"], GENERATED_AWAITING_COMMIT)
        self.assertFalse(self.external_store_path.exists())
        self.assertNotIn(
            "Synthetic protocol draft A",
            self.state_path.read_text(encoding="utf-8"),
        )

    def test_retry_same_draft_after_storage_failure_commits(self):
        with self.assertRaises(RuntimeError):
            self.execute_pipeline(self.client("A", "fail"))

        result = self.execute_pipeline(self.client("A", "ok"))
        self.assertEqual(result["status"], PIPELINE_COMMITTED)
        external = json.loads(self.external_store_path.read_text(encoding="utf-8"))
        self.assertEqual(len(external["records"]), 1)

    def test_retry_changed_draft_requires_review_and_never_stores(self):
        with self.assertRaises(RuntimeError):
            self.execute_pipeline(self.client("A", "fail"))

        result = self.execute_pipeline(self.client("B", "ok"))
        self.assertEqual(result["status"], GENERATION_CONFLICT_REQUIRES_REVIEW)
        self.assertFalse(self.external_store_path.exists())
        entry = result["state"]["pipeline_registry"]["operations"][0]
        self.assertNotEqual(entry["text_sha256"], entry["replayed_text_sha256"])

    def test_already_committed_replay_does_not_launch_runtime(self):
        first = self.execute_pipeline(self.client("A", "ok"))
        self.assertEqual(first["status"], PIPELINE_COMMITTED)

        nonexistent = Path(self.temp.name) / "does-not-exist.js"
        replay = self.execute_pipeline(self.client(fixture=nonexistent))
        self.assertEqual(replay["status"], ALREADY_PIPELINE_COMMITTED)
        external = json.loads(self.external_store_path.read_text(encoding="utf-8"))
        self.assertEqual(len(external["records"]), 1)

    def test_pipeline_identity_change_is_rejected_before_runtime(self):
        with self.assertRaises(RuntimeError):
            self.execute_pipeline(self.client("A", "fail"))

        nonexistent = Path(self.temp.name) / "does-not-exist.js"
        with self.assertRaisesRegex(ValueError, "different request"):
            self.execute_pipeline(
                self.client(fixture=nonexistent),
                transcript_text="Changed transcript identity",
            )
        self.assertFalse(self.external_store_path.exists())


if __name__ == "__main__":
    unittest.main()

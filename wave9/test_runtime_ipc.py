import json
import unittest
from pathlib import Path

from wave9.runtime_ipc import RuntimeClient

FIXTURE = Path(__file__).with_name("runtime_fixture.js")


class RuntimeIPCSyntheticTests(unittest.TestCase):
    def client(self, **kwargs):
        return RuntimeClient(["node", str(FIXTURE)], **kwargs)

    def test_generate_uses_real_wave8_adapter_across_process(self):
        out = self.client().generate("hello world", "m1", "synthetic_protocol_generation")
        self.assertTrue(out["text"].startswith("DRAFT:"))
        self.assertEqual(out["model"], "m1")
        self.assertEqual(out["provider"], "synthetic-provider")

    def test_store_uses_real_wave8_writer_across_process(self):
        text = "draft record"
        request = {
            "event_id": "EVENT-1",
            "document_type": "meeting_record",
            "storage_provider": "synthetic_store",
            "draft_id": "DRAFT-1",
            "artifact_id": "ART-1",
            "source_id": "SOURCE-1",
            "correlation_id": "CORR-1",
            "text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
            "display_name": "record.txt",
        }
        out = self.client().store(request, text)
        self.assertEqual(out["save_status"], "STORED")
        self.assertEqual(out["store_id"], "STORE-1")
        self.assertEqual(out["text_sha256"], request["text_sha256"])

    def test_wrong_generation_operation_is_structured_failure(self):
        with self.assertRaisesRegex(RuntimeError, "exit code 1"):
            self.client().generate("x", None, "wrong")

    def test_string_command_rejected(self):
        with self.assertRaisesRegex(ValueError, "argv sequence"):
            RuntimeClient("node worker.js")

    def test_empty_argv_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-empty"):
            RuntimeClient([])

    def test_timeout_is_bounded(self):
        client = RuntimeClient(["node", "-e", "setTimeout(()=>{}, 5000)"], timeout_seconds=1)
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            client.generate("x", None, "synthetic_protocol_generation")

    def test_invalid_json_rejected(self):
        client = RuntimeClient([
            "node", "-e",
            'process.stdin.resume();process.stdin.on("end",()=>process.stdout.write("nope\\n"))'
        ])
        with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
            client.generate("x", None, "synthetic_protocol_generation")

    def test_multiple_json_lines_rejected(self):
        script = 'process.stdin.resume();process.stdin.on("end",()=>process.stdout.write("{}\\n{}\\n"))'
        client = RuntimeClient(["node", "-e", script])
        with self.assertRaisesRegex(RuntimeError, "exactly one JSON line"):
            client.generate("x", None, "synthetic_protocol_generation")

    def test_response_size_limit(self):
        payload = json.dumps({"schema_version": 1, "ok": True, "result": {"text": "x" * 200}}) + "\n"
        script = (
            'process.stdin.resume();process.stdin.on("end",()=>process.stdout.write('
            + json.dumps(payload) + '))'
        )
        client = RuntimeClient(["node", "-e", script], max_response_bytes=100)
        with self.assertRaisesRegex(RuntimeError, "size limit"):
            client.generate("x", None, "synthetic_protocol_generation")

    def test_nonzero_success_looking_response_is_rejected(self):
        payload = json.dumps({"schema_version": 1, "ok": True, "result": {"text": "ok"}}) + "\n"
        script = (
            'process.stdin.resume();process.stdin.on("end",()=>{process.stdout.write('
            + json.dumps(payload) + ');process.exitCode=2;})'
        )
        client = RuntimeClient(["node", "-e", script])
        with self.assertRaisesRegex(RuntimeError, "exit code 2"):
            client.generate("x", None, "synthetic_protocol_generation")


if __name__ == "__main__":
    unittest.main()

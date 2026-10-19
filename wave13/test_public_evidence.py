#!/usr/bin/env python3
"""Hand-authored public fixture evidence probes; no model or agent involved."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from build_synthetic_targets import build
from score_synthetic import expected_from_target
from verify_public_evidence import Invalid, approved_target, verify, evidence_matches, SCHEMA, CASES


def packet_for(root: Path) -> dict:
    answers = expected_from_target(root)
    cited = {
        "LR-E01": {
            "start_channel": ("targets/electron-app/.webpack/main.js", "source-line", 2),
            "changed_channel": ("targets/electron-app/.webpack/main.js", "source-line", 3),
        },
        "LR-N01": {
            "permission_symbol": ("targets/libcapture_probe.so", "nm-export", None),
            "allowed_euid": ("targets/libcapture_probe.so", "objdump-immediate", None),
        },
        "LR-G01": {
            "module_path": ("targets/go_probe", "go-build", None),
            "toolchain": ("targets/go_probe", "go-build", None),
        },
        "LR-D01": {
            "socket_path": ("targets/libwire_probe.so", "strings-line", None),
            "accepted_message": ("targets/libwire_probe.so", "strings-line", None),
            "peer_check_symbol": ("targets/libwire_probe.so", "nm-export", None),
        },
    }
    return {
        "schema": SCHEMA,
        "responses": [
            {"case_id": case, "answers": dict(answers[case]),
             "evidence": {
                 field: {"path": v[0], "method": v[1], "line": v[2]}
                 for field, v in cited[case].items()
             }}
            for case in CASES
        ]
    }


class PublicEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="leanrea-evidence-test-")
        cls.root = Path(cls.tmp.name) / "fixtures"
        build(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutate(self, func):
        x = packet_for(self.root)
        func(x)
        return x

    def reject(self, func):
        with self.assertRaises(Invalid):
            verify(self.mutate(func), self.root)

    def test_all_nine_synthetic_evidence_anchors(self):
        r = verify(packet_for(self.root), self.root)
        self.assertEqual((r["fields_with_matching_anchors"], r["fields_total"]), (9, 9))
        self.assertTrue(r["all_anchors_found"])

    def test_no_semantic_or_agent_or_blind_claim(self):
        r = verify(packet_for(self.root), self.root)
        self.assertFalse(r["semantic_correctness_verified"])
        self.assertFalse(r["agent_trace_verified"])
        self.assertFalse(r["independent_blind_gold_verified"])
        self.assertFalse(r["real_agent_benefit_proven"])

    def test_false_channel_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][0]["answers"].__setitem__(
            "start_channel", "fake:channel")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_wrong_source_line_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][0]["evidence"]["start_channel"].__setitem__(
            "line", 4)), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_wrong_native_immediate_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][1]["answers"].__setitem__(
            "allowed_euid", "7777")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_wrong_go_version_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][2]["answers"].__setitem__(
            "toolchain", "go1.0")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_wrong_socket_path_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][3]["answers"].__setitem__(
            "socket_path", "/tmp/false.sock")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_wrong_export_symbol_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][1]["answers"].__setitem__(
            "permission_symbol", "not_an_export")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_js_prefix_substring_not_grounded(self):
        # A channel fragment must not be passed off as the quoted full channel.
        r = verify(self.mutate(lambda p: p["responses"][0]["answers"].__setitem__(
            "start_channel", "records:begin")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_js_suffix_substring_not_grounded(self):
        r = verify(self.mutate(lambda p: p["responses"][0]["answers"].__setitem__(
            "changed_channel", "changed-v2")), self.root)
        self.assertEqual(r["fields_with_matching_anchors"], 8)

    def test_unrelated_mov_immediate_not_grounded(self):
        # A call to geteuid plus an unrelated MOV immediate is insufficient.
        fake = ("  1010:\te8 00 00 00 00\tcall 1020 <geteuid@plt>\n"
                "  1015:\tb8 d2 04 00 00\tmov $0x4d2,%eax\n")
        with patch("verify_public_evidence.inspect", return_value=fake):
            self.assertFalse(evidence_matches(Path("unused"), "objdump-immediate", "1234", None))

    def test_unrelated_cmp_without_geteuid_not_grounded(self):
        fake = "  1015:\t3d d2 04 00 00\tcmp $0x4d2,%eax\n"
        with patch("verify_public_evidence.inspect", return_value=fake):
            self.assertFalse(evidence_matches(Path("unused"), "objdump-immediate", "1234", None))

    def test_quoted_literal_js_still_grounded(self):
        r = verify(packet_for(self.root), self.root)
        self.assertTrue(r["cases"][0]["anchor_present"]["start_channel"])
        self.assertTrue(r["cases"][0]["anchor_present"]["changed_channel"])

    def test_reject_path_traversal(self):
        self.reject(lambda p: p["responses"][0]["evidence"]["start_channel"].__setitem__(
            "path", "targets/electron-app/../../../private"))

    def test_reject_wrong_case_artifact(self):
        self.reject(lambda p: p["responses"][1]["evidence"]["allowed_euid"].__setitem__(
            "path", "targets/libwire_probe.so"))

    def test_reject_wrong_method(self):
        self.reject(lambda p: p["responses"][1]["evidence"]["allowed_euid"].__setitem__(
            "method", "shell"))

    def test_reject_boolean_line(self):
        self.reject(lambda p: p["responses"][0]["evidence"]["start_channel"].__setitem__(
            "line", True))

    def test_reject_huge_source_line(self):
        self.reject(lambda p: p["responses"][0]["evidence"]["start_channel"].__setitem__(
            "line", 1000000))

    def test_reject_cli_method_with_line(self):
        self.reject(lambda p: p["responses"][1]["evidence"]["permission_symbol"].__setitem__(
            "line", 1))

    def test_reject_missing_evidence(self):
        self.reject(lambda p: p["responses"][0]["evidence"].pop("changed_channel"))

    def test_reject_duplicate_case(self):
        self.reject(lambda p: p["responses"][1].__setitem__(
            "case_id", p["responses"][0]["case_id"]))

    def test_reject_missing_case(self):
        self.reject(lambda p: p["responses"].pop())

    def test_reject_fabricated_verified_claim(self):
        self.reject(lambda p: p.__setitem__("agent_trace_verified", True))

    def test_reject_extra_evidence_property(self):
        self.reject(lambda p: p["responses"][0]["evidence"]["start_channel"].__setitem__(
            "run_python", True))

    def test_reject_ansi_control_payload(self):
        self.reject(lambda p: p["responses"][0]["answers"].__setitem__(
            "start_channel", "\x1b[31mfake"))

    def test_reject_bool_value_payload(self):
        self.reject(lambda p: p["responses"][0]["answers"].__setitem__(
            "start_channel", True))

    def test_reject_symlinked_fixture_root(self):
        alias = Path(self.tmp.name) / "symlinked-fixture"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Invalid):
            approved_target(alias, "targets/go_probe")

    def test_reject_missing_artifact(self):
        with self.assertRaises(Invalid):
            approved_target(self.root, "targets/absent.bin")


if __name__ == "__main__":
    unittest.main(verbosity=2)

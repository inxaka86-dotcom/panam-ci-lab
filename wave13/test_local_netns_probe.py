#!/usr/bin/env python3
"""Fail-closed fake child transcripts for a no-internet local namespace probe."""
from __future__ import annotations

import json
from unittest import TestCase, main
from unittest.mock import patch

from probe_local_netns import classify, probe, report, SCHEMA

PARENT_NET = "net:[4026532000]"
PARENT_USER = "user:[4026531837]"


def child(**kwargs):
    doc = {
        "schema": SCHEMA,
        "net_ns": "net:[4026532999]",
        "user_ns": "user:[4026532998]",
        "interfaces": ["lo"],
        "loopback_reachable": False,
        "child_uid": 0,
    }
    doc.update(kwargs)
    return json.dumps(doc, sort_keys=True)


class NetNamespaceProbeTests(TestCase):
    def status(self, **changes):
        return classify(PARENT_NET, PARENT_USER, 0, child(**changes))

    def test_valid_but_only_local_ephemeral(self):
        result = self.status()
        self.assertEqual(result["status"], "PASS_LOCAL_EPHEMERAL_NETNS_ONLY")
        self.assertTrue(result["local_ephemeral_netns_observed"])
        self.assertFalse(result["actual_target_host_isolation_proven"])

    def test_same_network_namespace_blocks(self):
        self.assertEqual(self.status(net_ns=PARENT_NET)["status"],
                         "BLOCKED_NAMESPACE_NOT_SEPARATE")

    def test_same_user_namespace_blocks(self):
        self.assertEqual(self.status(user_ns=PARENT_USER)["status"],
                         "BLOCKED_NAMESPACE_NOT_SEPARATE")

    def test_parent_listener_reachable_blocks(self):
        self.assertEqual(self.status(loopback_reachable=True)["status"],
                         "BLOCKED_PARENT_LOOPBACK_REACHABLE")

    def test_added_ethernet_interface_blocks(self):
        self.assertEqual(self.status(interfaces=["eth0", "lo"])["status"],
                         "BLOCKED_UNSAFE_NETWORK_OBSERVATION")

    def test_no_loopback_interface_blocks(self):
        self.assertEqual(self.status(interfaces=[])["status"],
                         "BLOCKED_UNSAFE_NETWORK_OBSERVATION")

    def test_nonmapped_child_uid_blocks(self):
        self.assertEqual(self.status(child_uid=1000)["status"],
                         "BLOCKED_UNSAFE_NETWORK_OBSERVATION")

    def test_boolean_uid_blocks(self):
        self.assertEqual(self.status(child_uid=False)["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_nonboolean_connected_blocks(self):
        self.assertEqual(self.status(loopback_reachable=0)["status"],
                         "BLOCKED_UNSAFE_NETWORK_OBSERVATION")

    def test_wrong_child_schema_blocks(self):
        self.assertEqual(self.status(schema="test.malicious")["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_wrong_parent_ns_type_blocks(self):
        out = classify("user:[4026531]", PARENT_USER, 0, child())
        self.assertEqual(out["status"], "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_wrong_child_ns_format_blocks(self):
        self.assertEqual(self.status(net_ns="fake")["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_bogus_result_field_blocks(self):
        raw = json.loads(child())
        raw["billing_proven"] = True
        self.assertEqual(classify(PARENT_NET, PARENT_USER, 0, json.dumps(raw))["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_nonzero_unshare_exit_is_blocked(self):
        self.assertEqual(classify(PARENT_NET, PARENT_USER, 1, child())["status"],
                         "BLOCKED_UNSHARE_UNAVAILABLE")

    def test_invalid_json_blocks(self):
        self.assertEqual(classify(PARENT_NET, PARENT_USER, 0, "{bad}")["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_oversized_output_blocks(self):
        self.assertEqual(classify(PARENT_NET, PARENT_USER, 0, "z"*513)["status"],
                         "BLOCKED_UNTRUSTED_CHILD_OUTPUT")

    def test_boolean_returncode_blocks(self):
        self.assertEqual(classify(PARENT_NET, PARENT_USER, True, child())["status"],
                         "BLOCKED_UNSHARE_UNAVAILABLE")

    def test_no_actual_authority_even_on_pass(self):
        r = self.status()
        for k in (
            "actual_target_host_isolation_proven", "filesystem_isolation_proven",
            "worker_isolation_proven", "external_internet_egress_probed",
            "model_request_executed", "provider_credentials_accessed",
            "production_changed", "agent_execution_allowed",
            "real_usd_hard_cap_enforced",
        ):
            self.assertFalse(r[k])

    def test_non_linux_no_subprocess(self):
        with patch("probe_local_netns.platform.system", return_value="Windows"):
            with patch("probe_local_netns.subprocess.run") as run:
                self.assertEqual(probe()["status"], "BLOCKED_NON_LINUX")
                run.assert_not_called()

    def test_host_root_no_subprocess(self):
        with patch("probe_local_netns.platform.system", return_value="Linux"):
            with patch("probe_local_netns.os.geteuid", return_value=0):
                with patch("probe_local_netns.subprocess.run") as run:
                    self.assertEqual(probe()["status"], "BLOCKED_HOST_ROOT_NOT_ALLOWED")
                    run.assert_not_called()


if __name__ == "__main__":
    main(verbosity=2)

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from witr_w2.safe_adapter import (
    SafeAdapterError,
    Target,
    build_argv,
    run_safe,
)

WITR_VERSION = "v0.3.3"
WITR_RELEASE_COMMIT = "86831e80c59c54e19c74cdbd126ed7ff6bcad756"
WITR_LINUX_AMD64_SHA256 = "08fc46e3f80a374476f71d0d6e6579477cd98c6df5cc59d98224adf948f5ebf5"
WITR_LINUX_AMD64_URL = (
    "https://github.com/pranshuparmar/witr/releases/download/"
    f"{WITR_VERSION}/witr-linux-amd64"
)
MAX_DOWNLOAD_BYTES = 12 * 1024 * 1024
SYNTHETIC_MARKER = "public_dummy_marker_witr_w2_2a9e71"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_executable(path: Path, body: str) -> str:
    path.write_text("#!/usr/bin/python3\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return sha256(path)


def download_exact_binary(destination: Path) -> None:
    request = urllib.request.Request(
        WITR_LINUX_AMD64_URL,
        headers={"User-Agent": "panam-ci-lab-public-witr-w2"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise AssertionError("download exceeded public W2 byte limit")
    digest = hashlib.sha256(payload).hexdigest()
    if digest != WITR_LINUX_AMD64_SHA256:
        raise AssertionError("exact upstream binary digest mismatch")
    destination.write_bytes(payload)
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR)


class ContractTests(unittest.TestCase):
    def test_argv_is_structured_and_tree_json_only(self) -> None:
        argv = build_argv(Path("/opt/panam/bin/witr"), Target("pid", 123))
        self.assertEqual(
            argv,
            ["/opt/panam/bin/witr", "--pid", "123", "--tree", "--json"],
        )
        self.assertNotIn("--env", argv)
        self.assertNotIn("--interactive", argv)

    def test_rejects_shellish_name_target(self) -> None:
        with self.assertRaises(SafeAdapterError):
            build_argv(Path("/opt/panam/bin/witr"), Target("name", "svc;id"))

    def test_file_target_is_argv_data_not_shell(self) -> None:
        argv = build_argv(
            Path("/opt/panam/bin/witr"),
            Target("file", "/tmp/a file;still-data"),
        )
        self.assertEqual(argv[1:3], ["--file", "/tmp/a file;still-data"])

    def test_rejects_relative_binary_and_relative_file(self) -> None:
        with self.assertRaises(SafeAdapterError):
            build_argv(Path("witr"), Target("pid", 1))
        with self.assertRaises(SafeAdapterError):
            build_argv(Path("/x/witr"), Target("file", "relative.txt"))

    def test_rejects_invalid_ports_and_pids(self) -> None:
        for target in (
            Target("pid", 0),
            Target("pid", "abc"),
            Target("port", 0),
            Target("port", 70000),
        ):
            with self.assertRaises(SafeAdapterError):
                build_argv(Path("/x/witr"), target)

    def test_fails_closed_on_unknown_json_field(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(
                binary,
                'import json\nprint(json.dumps({"PID": 7, "Command": "safe", "Env": ["SECRET=x"]}))\n',
            )
            with self.assertRaisesRegex(SafeAdapterError, "unexpected fields"):
                run_safe(binary, digest, Target("pid", 7))

    def test_command_arguments_are_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(
                binary,
                'import json\nprint(json.dumps({"PID": 7, "Command": "/usr/bin/python3 --flag harmless"}))\n',
            )
            result = run_safe(binary, digest, Target("pid", 7))
            self.assertEqual(
                result["provenance"]["command"],
                "python3 [args-omitted]",
            )
            self.assertNotIn("--flag", json.dumps(result))

    def test_secretish_command_is_fully_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(
                binary,
                'import json\nprint(json.dumps({"PID": 7, "Command": "worker --token=secretvalue"}))\n',
            )
            result = run_safe(binary, digest, Target("pid", 7))
            self.assertEqual(result["provenance"]["command"], "[redacted-command]")
            self.assertNotIn("secretvalue", json.dumps(result))

    def test_parent_environment_is_not_inherited(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(
                binary,
                'import json, os, sys\n'
                'if os.environ.get("PANAM_PRIVATE_TEST_MARKER"):\n'
                '    sys.exit(9)\n'
                'print(json.dumps({"PID": 7, "Command": "safe"}))\n',
            )
            old = os.environ.get("PANAM_PRIVATE_TEST_MARKER")
            os.environ["PANAM_PRIVATE_TEST_MARKER"] = "must-not-cross-boundary"
            try:
                result = run_safe(binary, digest, Target("pid", 7))
            finally:
                if old is None:
                    os.environ.pop("PANAM_PRIVATE_TEST_MARKER", None)
                else:
                    os.environ["PANAM_PRIVATE_TEST_MARKER"] = old
            self.assertEqual(result["provenance"]["pid"], 7)

    def test_raw_stderr_is_never_exposed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(
                binary,
                'import sys\nsys.stderr.write("SUPER_SECRET_STDERR_VALUE\\n")\nsys.exit(5)\n',
            )
            with self.assertRaises(SafeAdapterError) as ctx:
                run_safe(binary, digest, Target("pid", 7))
            self.assertNotIn("SUPER_SECRET_STDERR_VALUE", str(ctx.exception))

    def test_stdout_limit_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(binary, 'print("X" * 20000)\n')
            with self.assertRaisesRegex(SafeAdapterError, "byte limit"):
                run_safe(
                    binary,
                    digest,
                    Target("pid", 7),
                    stdout_limit=1024,
                )

    def test_timeout_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            binary = Path(td) / "fake-witr"
            digest = make_executable(binary, 'import time\ntime.sleep(3)\n')
            started = time.monotonic()
            with self.assertRaisesRegex(SafeAdapterError, "timed out"):
                run_safe(
                    binary,
                    digest,
                    Target("pid", 7),
                    timeout=0.15,
                )
            self.assertLess(time.monotonic() - started, 2.5)

    def test_digest_mismatch_blocks_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "executed"
            binary = Path(td) / "fake-witr"
            make_executable(
                binary,
                f'from pathlib import Path\nPath({str(marker)!r}).write_text("bad")\n',
            )
            with self.assertRaisesRegex(SafeAdapterError, "digest mismatch"):
                run_safe(binary, "0" * 64, Target("pid", 7))
            self.assertFalse(marker.exists())


class ExactUpstreamIntegrationTest(unittest.TestCase):
    def test_exact_witr_reduced_pid_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="witr-w2-public-") as td:
            binary = Path(td) / "witr"
            download_exact_binary(binary)

            child_env = {
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "WITR_W2_SYNTHETIC_MARKER": SYNTHETIC_MARKER,
            }
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                env=child_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                result = run_safe(
                    binary,
                    WITR_LINUX_AMD64_SHA256,
                    Target("pid", child.pid),
                    timeout=15,
                )
            finally:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)

            encoded = json.dumps(result, sort_keys=True)
            self.assertEqual(result["schema"], "panam.runtime_provenance.safe.v1")
            self.assertEqual(result["target"]["type"], "pid")
            self.assertEqual(len(result["target"]["ref_sha256"]), 64)
            self.assertEqual(
                result["upstream"]["binary_sha256"],
                WITR_LINUX_AMD64_SHA256,
            )
            self.assertNotIn(SYNTHETIC_MARKER, encoded)
            self.assertNotIn("Env", encoded)
            self.assertNotIn("Cmdline", encoded)
            self.assertNotIn("WorkingDir", encoded)


if __name__ == "__main__":
    unittest.main(verbosity=2)

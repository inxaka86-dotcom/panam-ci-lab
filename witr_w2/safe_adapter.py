from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import threading
import time
from typing import Any

SCHEMA = "panam.runtime_provenance.safe.v1"
ALLOWED_TREE_KEYS = {"Ancestry", "Children", "PID", "Command"}
MINIMAL_ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_STDOUT_LIMIT = 128 * 1024
DEFAULT_STDERR_LIMIT = 32 * 1024

_TARGET_TYPES = {"pid", "port", "file", "container", "name"}
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,128}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_SECRETISH_RE = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|"
    r"(?i:(?:token|secret|password|passwd|api[_-]?key|authorization|cookie))\s*[:=]\s*\S+|"
    r"(?i:bearer)\s+\S+)"
)


class SafeAdapterError(RuntimeError):
    """Fail-closed adapter error without raw upstream output."""


@dataclass(frozen=True)
class Target:
    type: str
    value: str | int


def _validate_target(target: Target) -> tuple[str, str]:
    target_type = str(target.type)
    if target_type not in _TARGET_TYPES:
        raise SafeAdapterError("unsupported target type")

    if target_type == "pid":
        try:
            value = int(target.value)
        except (TypeError, ValueError) as exc:
            raise SafeAdapterError("pid must be an integer") from exc
        if value <= 0:
            raise SafeAdapterError("pid must be positive")
        return "--pid", str(value)

    if target_type == "port":
        try:
            value = int(target.value)
        except (TypeError, ValueError) as exc:
            raise SafeAdapterError("port must be an integer") from exc
        if not 1 <= value <= 65535:
            raise SafeAdapterError("port out of range")
        return "--port", str(value)

    value = str(target.value)
    if "\x00" in value or "\n" in value or "\r" in value:
        raise SafeAdapterError("target contains control characters")

    if target_type == "file":
        if len(value) > 4096:
            raise SafeAdapterError("file target is too long")
        path = Path(value)
        if not path.is_absolute():
            raise SafeAdapterError("file target must be absolute")
        return "--file", str(path)

    if not _SAFE_NAME_RE.fullmatch(value):
        raise SafeAdapterError(f"{target_type} target contains unsupported characters")
    if target_type == "container":
        return "--container", value
    return "", value


def build_argv(binary_path: Path, target: Target) -> list[str]:
    binary = Path(binary_path)
    if not binary.is_absolute():
        raise SafeAdapterError("witr binary path must be absolute")
    flag, value = _validate_target(target)
    target_args = [value] if not flag else [flag, value]
    return [str(binary), *target_args, "--tree", "--json"]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _target_ref(target: Target) -> str:
    _flag, normalized = _validate_target(target)
    return hashlib.sha256(f"{target.type}:{normalized}".encode("utf-8")).hexdigest()


def _sanitize_command(value: Any) -> str:
    if not isinstance(value, str):
        raise SafeAdapterError("Command must be a string")
    if _SECRETISH_RE.search(value):
        return "[redacted-command]"
    try:
        parts = shlex.split(value, posix=True)
    except ValueError:
        parts = value.split()
    if not parts:
        return ""
    executable = Path(parts[0]).name[:128]
    if _SECRETISH_RE.search(executable):
        executable = "[redacted-executable]"
    return executable if len(parts) == 1 else f"{executable} [args-omitted]"


def _sanitize_node(node: Any) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise SafeAdapterError("tree node must be an object")
    unknown = set(node) - ALLOWED_TREE_KEYS
    if unknown:
        raise SafeAdapterError("upstream tree output contained unexpected fields")

    out: dict[str, Any] = {}
    if "PID" in node:
        pid = node["PID"]
        if not isinstance(pid, int) or pid <= 0:
            raise SafeAdapterError("PID must be a positive integer")
        out["pid"] = pid
    if "Command" in node:
        out["command"] = _sanitize_command(node["Command"])
    if "Ancestry" in node:
        ancestry = node["Ancestry"]
        if not isinstance(ancestry, list):
            raise SafeAdapterError("Ancestry must be a list")
        out["ancestry"] = [_sanitize_node(child) for child in ancestry]
    if "Children" in node:
        children = node["Children"]
        if not isinstance(children, list):
            raise SafeAdapterError("Children must be a list")
        out["children"] = [_sanitize_node(child) for child in children]
    return out


def _read_limited(stream: Any, limit: int, sink: bytearray, overflow: threading.Event) -> None:
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            remaining = limit - len(sink)
            if remaining <= 0:
                overflow.set()
                return
            sink.extend(chunk[:remaining])
            if len(chunk) > remaining:
                overflow.set()
                return
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_bounded(
    argv: list[str],
    *,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[int, bytes]:
    if timeout <= 0 or stdout_limit <= 0 or stderr_limit <= 0:
        raise SafeAdapterError("execution bounds must be positive")

    proc = subprocess.Popen(
        argv,
        shell=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/",
        env=MINIMAL_ENV.copy(),
        close_fds=True,
        start_new_session=True,
    )
    assert proc.stdout is not None and proc.stderr is not None

    out = bytearray()
    err = bytearray()
    overflow = threading.Event()
    threads = [
        threading.Thread(
            target=_read_limited,
            args=(proc.stdout, stdout_limit, out, overflow),
            daemon=True,
        ),
        threading.Thread(
            target=_read_limited,
            args=(proc.stderr, stderr_limit, err, overflow),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    timed_out = False
    while proc.poll() is None:
        if overflow.is_set():
            _kill_group(proc)
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _kill_group(proc)
            break
        time.sleep(0.01)

    try:
        returncode = proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_group(proc)
        returncode = proc.wait(timeout=2)

    for thread in threads:
        thread.join(timeout=1)

    if overflow.is_set():
        raise SafeAdapterError("upstream output exceeded byte limit")
    if timed_out:
        raise SafeAdapterError("upstream execution timed out")
    return returncode, bytes(out)


def run_safe(
    binary_path: Path,
    expected_sha256: str,
    target: Target,
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    stdout_limit: int = DEFAULT_STDOUT_LIMIT,
    stderr_limit: int = DEFAULT_STDERR_LIMIT,
) -> dict[str, Any]:
    binary = Path(binary_path)
    if not binary.is_absolute():
        raise SafeAdapterError("witr binary path must be absolute")
    if not _SHA256_RE.fullmatch(expected_sha256):
        raise SafeAdapterError("expected sha256 must be lowercase hex")
    if not binary.is_file():
        raise SafeAdapterError("witr binary does not exist")
    if not os.access(binary, os.X_OK):
        raise SafeAdapterError("witr binary is not executable")

    actual_digest = _sha256(binary)
    if actual_digest != expected_sha256:
        raise SafeAdapterError("witr binary digest mismatch")

    argv = build_argv(binary, target)
    returncode, stdout = _run_bounded(
        argv,
        timeout=timeout,
        stdout_limit=stdout_limit,
        stderr_limit=stderr_limit,
    )
    if returncode not in {0, 1}:
        raise SafeAdapterError(f"witr lookup failed with exit class {returncode}")

    if _sha256(binary) != actual_digest:
        raise SafeAdapterError("witr binary changed during execution")

    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SafeAdapterError("witr returned invalid reduced JSON") from exc

    reduced = _sanitize_node(payload)
    return {
        "schema": SCHEMA,
        "target": {
            "type": target.type,
            "ref_sha256": _target_ref(target),
        },
        "upstream": {
            "binary_sha256": actual_digest,
            "mode": "tree-json-reduced",
            "exit_class": returncode,
        },
        "provenance": reduced,
    }

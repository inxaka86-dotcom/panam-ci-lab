from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from typing import Sequence

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_command(command: Sequence[str]) -> list[str]:
    if isinstance(command, (str, bytes)) or not isinstance(command, Sequence):
        raise ValueError("runtime command must be argv sequence")
    argv = list(command)
    if not argv or not all(_nonempty(item) for item in argv):
        raise ValueError("runtime argv must contain non-empty strings")
    return argv


def _parse_response(stdout: str, max_response_bytes: int) -> dict:
    if len(stdout.encode("utf-8")) > max_response_bytes:
        raise RuntimeError("runtime response exceeds size limit")
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("runtime worker must return exactly one JSON line")
    try:
        response = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("runtime worker returned invalid JSON") from exc
    if not isinstance(response, dict) or response.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError("runtime response schema mismatch")
    if response.get("ok") is not True:
        error = response.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        raise RuntimeError(f"runtime worker refused request: {message or 'unspecified error'}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise RuntimeError("runtime response missing result")
    return result


class RuntimeClient:
    def __init__(self, command: Sequence[str], *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES):
        self.command = _validate_command(command)
        if not isinstance(timeout_seconds, int) or isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive integer")
        if not isinstance(max_response_bytes, int) or isinstance(max_response_bytes, bool) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive integer")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def _call(self, operation: str, payload: dict) -> dict:
        envelope = {"schema_version": 1, "operation": operation, "payload": deepcopy(payload)}
        try:
            completed = subprocess.run(
                self.command,
                input=json.dumps(envelope) + "\n",
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("runtime worker timed out") from exc
        try:
            result = _parse_response(completed.stdout, self.max_response_bytes)
        except RuntimeError:
            if completed.returncode != 0:
                raise RuntimeError(f"runtime worker failed with exit code {completed.returncode}") from None
            raise
        if completed.returncode != 0:
            raise RuntimeError(f"runtime worker failed with exit code {completed.returncode}")
        return result

    def generate(self, prompt: str, model: str | None, operation: str) -> dict:
        if not _nonempty(prompt) or not _nonempty(operation):
            raise ValueError("prompt and operation are required")
        return self._call("generate", {"prompt": prompt, "model": model, "generation_operation": operation})

    def store(self, request: dict, text: str) -> dict:
        if not isinstance(request, dict) or not _nonempty(text):
            raise ValueError("store request/text invalid")
        return self._call("store", {"request": deepcopy(request), "text": text})

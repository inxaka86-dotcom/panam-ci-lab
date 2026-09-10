from __future__ import annotations

import re
import subprocess
from pathlib import Path

WORKFLOW_SUFFIXES = {".yml", ".yaml"}
TOKEN_PATTERNS = (
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"])
    return [Path(item.decode("utf-8")) for item in raw.split(b"\0") if item]


def scan() -> list[str]:
    errors: list[str] = []
    for path in tracked_files():
        if not path.is_file() or path == Path("checks/publication_gate.py"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"{path}: non-UTF-8 tracked file requires explicit review")
            continue
        for pattern in TOKEN_PATTERNS:
            if pattern.search(text):
                errors.append(f"{path}: credential-like material detected")
        if path.parent == Path(".github/workflows") and path.suffix in WORKFLOW_SUFFIXES:
            lowered = text.lower()
            if "self-hosted" in lowered:
                errors.append(f"{path}: self-hosted runner is forbidden")
            if "pull_request_target" in lowered:
                errors.append(f"{path}: pull_request_target is forbidden")
            if re.search(r"\$\{\{\s*secrets\.", text, flags=re.IGNORECASE):
                errors.append(f"{path}: secret context is forbidden")
            if re.search(r"permissions:\s*\n(?:[ \t]+.+\n)*?[ \t]+contents:\s*write\b", text, flags=re.IGNORECASE):
                errors.append(f"{path}: contents: write is forbidden")
    return errors


if __name__ == "__main__":
    findings = scan()
    if findings:
        for finding in findings:
            print(f"PUBLICATION_GATE_ERROR={finding}")
        raise SystemExit(1)
    print("PUBLICATION_GATE=PASS")

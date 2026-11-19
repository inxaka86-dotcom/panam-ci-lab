"""Validate a trusted GitHub Issue before exposing an AI-provider key to the job.

All input comes from GITHUB_EVENT_PATH; no issue data is interpolated into shell.
Only an exact owner GitHub user ID/login may submit paid AI instructions.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

REPOSITORY = "inxaka86-dotcom/panam-ci-lab"
OWNER_LOGIN = "inxaka86-dotcom"
OWNER_ID = 317440435
TITLE_PREFIX = "[PANAM-AUTOCODER] "
BODY_PREFIX = "PANAM_AUTOCODER_V1\n"
MAX_TASK_BYTES = 2500


def validate(payload: dict[str, Any], repository: str) -> tuple[int, str]:
    if repository != REPOSITORY:
        raise ValueError("Untrusted repository")
    if payload.get("action") != "opened":
        raise ValueError("Unexpected issue action")
    issue = payload.get("issue")
    if not isinstance(issue, dict) or issue.get("pull_request"):
        raise ValueError("An ordinary issue is required")
    author = issue.get("user")
    if not isinstance(author, dict):
        raise ValueError("Issue author is missing")
    if author.get("login") != OWNER_LOGIN or author.get("id") != OWNER_ID:
        raise ValueError("Issue author is not the authorized repository owner")
    if issue.get("state") != "open":
        raise ValueError("Issue is not open")
    title = issue.get("title")
    if not isinstance(title, str) or not title.startswith(TITLE_PREFIX):
        raise ValueError("Unrecognized issue title prefix")
    if len(title) > 180 or not title[len(TITLE_PREFIX):].strip():
        raise ValueError("Invalid issue title")
    body = issue.get("body")
    if not isinstance(body, str):
        raise ValueError("Issue body is missing")
    # A single documented marker separates the command from arbitrary prose.
    normalized = body.replace("\r\n", "\n")
    if not normalized.startswith(BODY_PREFIX):
        raise ValueError("Unrecognized issue body marker")
    task = normalized[len(BODY_PREFIX):].strip()
    if not task or len(task.encode("utf-8")) > MAX_TASK_BYTES:
        raise ValueError("Task is empty or too long")
    if any(ord(char) < 32 and char not in ("\n", "\t") for char in task):
        raise ValueError("Control characters in task")
    number = issue.get("number")
    if type(number) is not int or number <= 0:
        raise ValueError("Invalid issue number")
    return number, task


def main() -> int:
    try:
        event_path = Path(os.environ["GITHUB_EVENT_PATH"])
        data = json.loads(event_path.read_text(encoding="utf-8"))
        number, task = validate(data, os.environ.get("GITHUB_REPOSITORY", ""))
        encoded = base64.b64encode(task.encode("utf-8")).decode("ascii")
        task_hash = hashlib.sha256(task.encode("utf-8")).hexdigest()[:16]
        env_path = Path(os.environ["GITHUB_ENV"])
        with env_path.open("a", encoding="utf-8") as env:
            env.write(f"AGENT_TASK_B64={encoded}\n")
            env.write(f"AGENT_ISSUE_NUMBER={number}\n")
            env.write(f"AGENT_TASK_HASH={task_hash}\n")
        print(f"PANAM_ISSUE_AUTHORIZED issue={number} task_sha256_prefix={task_hash}")
        return 0
    except (ValueError, KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"PANAM_ISSUE_REJECTED {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

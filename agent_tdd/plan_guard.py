"""Minimal synthetic change-plan validation for a public TDD experiment.

This DOES NOT authorize filesystem writes, run agents, or implement a private
system's approval/security boundary.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

SCHEMA = "synthetic.agent-change.v1"
DATA_CLASS = "PUBLIC_SYNTHETIC"
MAX_CHANGES = 8
ALLOWED_ACTIONS = frozenset({"create", "modify"})
ALLOWED_EXTENSIONS = frozenset({".json", ".md", ".py"})
SAFE_PATH = re.compile(r"^[a-z0-9][a-z0-9._/-]*$", re.ASCII)


def validate_change_plan(plan: object) -> tuple[str, ...]:
    """Validate metadata only; return deterministically ordered virtual paths.

    The caller must separately enforce filesystem containment, symlink policy
    and process permissions if this idea is ever adapted to real operations.
    """
    if not isinstance(plan, dict) or set(plan) != {"schema", "data_class", "changes"}:
        raise ValueError("invalid change-plan envelope")
    if plan["schema"] != SCHEMA or plan["data_class"] != DATA_CLASS:
        raise ValueError("unsupported change-plan schema or data class")
    changes = plan["changes"]
    if not isinstance(changes, list) or not (1 <= len(changes) <= MAX_CHANGES):
        raise ValueError("change count outside permitted range")

    approved: set[str] = set()
    for item in changes:
        if not isinstance(item, dict) or set(item) != {"path", "action"}:
            raise ValueError("invalid change entry")
        path = item["path"]
        action = item["action"]
        if not isinstance(path, str) or len(path) > 128 or not SAFE_PATH.fullmatch(path):
            raise ValueError("invalid path syntax")
        parts = path.split("/")
        if (len(parts) < 2 or parts[0] != "synthetic"
                or any(part in {"", ".", ".."} or part.startswith(".") for part in parts)):
            raise ValueError("path outside synthetic root")
        if PurePosixPath(path).suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("disallowed synthetic file extension")
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            raise ValueError("disallowed change action")
        if path in approved:
            raise ValueError("duplicate change path")
        approved.add(path)
    return tuple(sorted(approved))

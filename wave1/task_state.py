from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

SCHEMA = "public.task-state.v1"
STATUSES = {"queued", "running", "waiting", "succeeded", "failed", "cancelled"}
TERMINAL = {"succeeded", "failed", "cancelled"}
ALLOWED_TRANSITIONS = {
    "queued": {"running", "waiting", "cancelled"},
    "running": {"waiting", "succeeded", "failed", "cancelled"},
    "waiting": {"running", "cancelled"},
    "succeeded": set(),
    "failed": set(),
    "cancelled": set(),
}


class TaskStateError(ValueError):
    pass


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise TaskStateError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TaskStateError("timestamp missing")
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise TaskStateError("invalid timestamp") from exc
    if dt.tzinfo is None:
        raise TaskStateError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _plain(state: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    out.pop("integrity_sha256", None)
    return out


def _digest(state: dict[str, Any]) -> str:
    payload = json.dumps(_plain(state), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(payload).hexdigest()


def seal(state: dict[str, Any]) -> dict[str, Any]:
    out = _plain(state)
    out["integrity_sha256"] = _digest(out)
    return out


def validate(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("schema") != SCHEMA:
        raise TaskStateError("schema mismatch")
    if state.get("status") not in STATUSES:
        raise TaskStateError("status invalid")
    if not isinstance(state.get("task_id"), str) or not (4 <= len(state["task_id"]) <= 80):
        raise TaskStateError("task_id invalid")
    _parse(state.get("created_at"))
    _parse(state.get("updated_at"))
    wake = state.get("next_wake_at")
    if wake is not None:
        _parse(wake)
    if state.get("integrity_sha256") != _digest(state):
        raise TaskStateError("integrity mismatch")
    return state


def new_task(task_id: str, *, now: datetime) -> dict[str, Any]:
    stamp = _iso(now)
    return seal({
        "schema": SCHEMA,
        "task_id": task_id,
        "status": "queued",
        "created_at": stamp,
        "updated_at": stamp,
        "next_wake_at": stamp,
    })


def transition(
    state: dict[str, Any],
    target: str,
    *,
    now: datetime,
    next_wake_at: datetime | None = None,
) -> dict[str, Any]:
    validate(state)
    current = state["status"]
    if target not in ALLOWED_TRANSITIONS[current]:
        raise TaskStateError(f"transition {current}->{target} not allowed")
    out = _plain(state)
    out["status"] = target
    out["updated_at"] = _iso(now)
    if target == "waiting":
        if next_wake_at is None or next_wake_at <= now:
            raise TaskStateError("future wake required")
        out["next_wake_at"] = _iso(next_wake_at)
    elif target in TERMINAL or target == "running":
        out["next_wake_at"] = None
    return seal(out)


def is_due(state: dict[str, Any], *, now: datetime) -> bool:
    validate(state)
    if state["status"] not in {"queued", "waiting"}:
        return False
    wake = state.get("next_wake_at")
    return wake is None or _parse(wake) <= now.astimezone(timezone.utc)

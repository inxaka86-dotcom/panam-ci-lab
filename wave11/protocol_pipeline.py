from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

from wave3.intake import validate_registry
from wave5.generation_hook import new_hook_registry, validate_hook_registry
from wave6.protocol_commit import (
    ALREADY_COMMITTED,
    COMMITTED,
    commit_artifact,
    new_commit_registry,
    validate_commit_registry,
)
from wave7.protocol_generation import (
    build_generation_context,
    build_prompt,
    generate_draft,
)

SCHEMA_VERSION = 1
ALLOWED_TRIGGER_MODES = {"owner_explicit", "approved_workflow"}

GENERATED_AWAITING_COMMIT = "GENERATED_AWAITING_COMMIT"
PIPELINE_COMMITTED = "PIPELINE_COMMITTED"
ALREADY_PIPELINE_COMMITTED = "ALREADY_PIPELINE_COMMITTED"
COMMIT_REQUIRES_RECOVERY = "COMMIT_REQUIRES_RECOVERY"
GENERATION_CONFLICT_REQUIRES_REVIEW = "GENERATION_CONFLICT_REQUIRES_REVIEW"


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _sha(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def new_pipeline_registry():
    return {
        "schema_version": 1,
        "policy": {
            "metadata_only": True,
            "raw_text_forbidden": True,
            "generation_checkpoint_before_storage": True,
            "generation_replay_hash_guard": True,
            "background_watcher_forbidden": True,
            "allowed_trigger_modes": sorted(ALLOWED_TRIGGER_MODES),
        },
        "operations": [],
    }


def _entry_sha(item):
    return _sha({k: v for k, v in item.items() if k != "entry_sha256"})


def validate_pipeline_registry(registry):
    if not isinstance(registry, dict) or registry.get("schema_version") != 1:
        raise ValueError("invalid pipeline registry")
    operations = registry.get("operations")
    if not isinstance(operations, list):
        raise ValueError("pipeline operations must be array")
    seen = set()
    for item in operations:
        if not isinstance(item, dict) or not _nonempty(item.get("pipeline_id")):
            raise ValueError("invalid pipeline operation")
        if item["pipeline_id"] in seen:
            raise ValueError("duplicate pipeline_id")
        seen.add(item["pipeline_id"])
        if any(key in item for key in ("transcript_text", "text", "draft_text", "raw_text", "content")):
            raise ValueError("raw text forbidden in pipeline registry")
        if item.get("entry_sha256") != _entry_sha(item):
            raise ValueError("pipeline operation digest mismatch")
    return registry


def _state_sha(state):
    return _sha({
        "schema_version": state.get("schema_version"),
        "pipeline_registry": state.get("pipeline_registry"),
        "draft_registry": state.get("draft_registry"),
        "hook_registry": state.get("hook_registry"),
        "commit_registry": state.get("commit_registry"),
    })


def _with_state_sha(state):
    value = deepcopy(state)
    value["state_sha256"] = _state_sha(value)
    return value


def new_state():
    return _with_state_sha({
        "schema_version": 1,
        "pipeline_registry": new_pipeline_registry(),
        "draft_registry": {"drafts": []},
        "hook_registry": new_hook_registry(),
        "commit_registry": new_commit_registry(),
    })


def validate_state(state):
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        raise ValueError("invalid pipeline state")
    validate_pipeline_registry(state.get("pipeline_registry"))
    validate_registry(state.get("draft_registry"))
    validate_hook_registry(state.get("hook_registry"))
    validate_commit_registry(state.get("commit_registry"))
    if state.get("state_sha256") != _state_sha(state):
        raise ValueError("pipeline state digest mismatch")
    return state


class StateStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return new_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("pipeline state invalid JSON") from exc
        return validate_state(value)

    def save(self, state):
        value = _with_state_sha(state)
        validate_state(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.tmp-{os.getpid()}")
        temp.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, self.path)
        return value


def _find(registry, pipeline_id):
    matches = [x for x in registry["operations"] if x.get("pipeline_id") == pipeline_id]
    if len(matches) > 1:
        raise ValueError("duplicate pipeline_id")
    return matches[0] if matches else None


def _put(registry, item, *, replace=False):
    updated = deepcopy(registry)
    value = deepcopy(item)
    value["entry_sha256"] = _entry_sha(value)
    if replace:
        indexes = [i for i, x in enumerate(updated["operations"]) if x.get("pipeline_id") == value["pipeline_id"]]
        if len(indexes) != 1:
            raise ValueError("pipeline replacement target missing")
        updated["operations"][indexes[0]] = value
    else:
        updated["operations"].append(value)
    validate_pipeline_registry(updated)
    return updated


def _preflight(transcript_text, *, rule_registry, pipeline_id, generation_id, operation_id, event_id, draft_id, artifact_id, source_id, correlation_id, display_name, requested_model, trigger_mode):
    if trigger_mode not in ALLOWED_TRIGGER_MODES:
        raise ValueError("trigger mode is not authorized")
    for name, value in (("pipeline_id", pipeline_id), ("generation_id", generation_id), ("operation_id", operation_id), ("event_id", event_id), ("draft_id", draft_id), ("artifact_id", artifact_id)):
        if not _nonempty(value):
            raise ValueError(f"{name} is required")
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        raise ValueError("transcript_text is required")
    if not (_nonempty(source_id) or _nonempty(correlation_id)):
        raise ValueError("source_id or correlation_id required")
    context = build_generation_context(rule_registry)
    prompt = build_prompt(transcript_text, context)
    return {
        "pipeline_id": pipeline_id,
        "generation_id": generation_id,
        "operation_id": operation_id,
        "event_id": event_id,
        "draft_id": draft_id,
        "artifact_id": artifact_id,
        "source_id": source_id,
        "correlation_id": correlation_id,
        "display_name": display_name,
        "requested_model": requested_model,
        "trigger_mode": trigger_mode,
        "transcript_sha256": hashlib.sha256(transcript_text.encode()).hexdigest(),
        "generation_context_sha256": context["context_sha256"],
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
    }


def run_pipeline(transcript_text, *, rule_registry, state_store, runtime_client, pipeline_id, generation_id, operation_id, event_id, draft_id, artifact_id, source_id=None, correlation_id=None, display_name=None, requested_model=None, trigger_mode="owner_explicit"):
    identity = _preflight(
        transcript_text,
        rule_registry=rule_registry,
        pipeline_id=pipeline_id,
        generation_id=generation_id,
        operation_id=operation_id,
        event_id=event_id,
        draft_id=draft_id,
        artifact_id=artifact_id,
        source_id=source_id,
        correlation_id=correlation_id,
        display_name=display_name,
        requested_model=requested_model,
        trigger_mode=trigger_mode,
    )
    identity_sha = _sha(identity)
    state = state_store.load()
    existing = _find(state["pipeline_registry"], pipeline_id)
    if existing:
        if existing.get("pipeline_identity_sha256") != identity_sha:
            raise ValueError("pipeline_id rebound to different request")
        if existing.get("state") == PIPELINE_COMMITTED:
            return {"status": ALREADY_PIPELINE_COMMITTED, "state": deepcopy(state)}
        if existing.get("state") == GENERATION_CONFLICT_REQUIRES_REVIEW:
            return {"status": GENERATION_CONFLICT_REQUIRES_REVIEW, "state": deepcopy(state)}

    generated = generate_draft(
        transcript_text,
        rule_registry=rule_registry,
        generator=runtime_client.generate,
        generation_id=generation_id,
        source_id=source_id,
        correlation_id=correlation_id,
        requested_model=requested_model,
    )
    receipt = generated["generation_receipt"]
    for field, expected in (
        ("generation_id", generation_id),
        ("source_id", source_id),
        ("correlation_id", correlation_id),
        ("transcript_sha256", identity["transcript_sha256"]),
        ("generation_context_sha256", identity["generation_context_sha256"]),
        ("prompt_sha256", identity["prompt_sha256"]),
    ):
        if receipt.get(field) != expected:
            raise RuntimeError(f"generation receipt mismatch: {field}")

    if existing is None:
        checkpoint = {
            **identity,
            "pipeline_identity_sha256": identity_sha,
            "text_sha256": receipt["text_sha256"],
            "applied_rule_ids": deepcopy(receipt.get("applied_rule_ids", [])),
            "model": receipt.get("model"),
            "provider": receipt.get("provider"),
            "state": GENERATED_AWAITING_COMMIT,
            "commit_status": None,
        }
        state["pipeline_registry"] = _put(state["pipeline_registry"], checkpoint)
        state = state_store.save(state)
        existing = _find(state["pipeline_registry"], pipeline_id)
    elif receipt["text_sha256"] != existing.get("text_sha256"):
        conflict = dict(existing)
        conflict["state"] = GENERATION_CONFLICT_REQUIRES_REVIEW
        conflict["replayed_text_sha256"] = receipt["text_sha256"]
        state["pipeline_registry"] = _put(state["pipeline_registry"], conflict, replace=True)
        state = state_store.save(state)
        return {"status": GENERATION_CONFLICT_REQUIRES_REVIEW, "state": deepcopy(state), "generation_receipt": receipt}

    request = {
        "operation_id": operation_id,
        "event_id": event_id,
        "document_type": "meeting_record",
        "storage_provider": "synthetic_store",
        "draft_id": draft_id,
        "artifact_id": artifact_id,
        "source_id": source_id,
        "correlation_id": correlation_id,
        "text_sha256": receipt["text_sha256"],
        "display_name": display_name,
    }
    committed = commit_artifact(
        request,
        text=generated["text"],
        storage_writer=runtime_client.store,
        draft_registry=state["draft_registry"],
        hook_registry=state["hook_registry"],
        commit_registry=state["commit_registry"],
    )
    state["draft_registry"] = committed["draft_registry"]
    state["hook_registry"] = committed["hook_registry"]
    state["commit_registry"] = committed["commit_registry"]
    current = dict(_find(state["pipeline_registry"], pipeline_id))
    current["commit_status"] = committed.get("status")
    current["state"] = PIPELINE_COMMITTED if committed.get("status") in {COMMITTED, ALREADY_COMMITTED} else COMMIT_REQUIRES_RECOVERY
    state["pipeline_registry"] = _put(state["pipeline_registry"], current, replace=True)
    state = state_store.save(state)
    return {
        "status": current["state"],
        "generation_receipt": deepcopy(receipt),
        "commit_result": committed,
        "text": generated["text"],
        "state": deepcopy(state),
    }

#!/usr/bin/env python3
"""Pure read-only OpenResearch export -> PANAM developer projection V1.

No network, subprocess, SQLite, OpenResearch CLI, PANAM Task/Job State, Memory,
Control Plane or provider operation is performed here. The adapter validates a
small JSON export and emits a deterministic, explicitly non-authoritative
projection suitable for later inspection or graph mapping.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

INPUT_SCHEMA = "openresearch.panam-export.v1"
OUTPUT_SCHEMA = "panam.openresearch.research-projection.v1"
SUPPORTED_UPSTREAM_REPOSITORY = "alphaXiv/OpenResearch"
SUPPORTED_UPSTREAM_SHA = "69768ff1b0537a4656e69f550fc444ac35b945d2"
SUPPORTED_UPSTREAM_VERSION = "0.2.5"

MAX_EXPERIMENTS = 256
MAX_EVIDENCE_REFS = 16
MAX_TEXT = 800
MAX_REF = 512

TOP_KEYS = {"schema", "upstream", "project", "experiments"}
UPSTREAM_KEYS = {"repository", "commit_sha", "version"}
PROJECT_KEYS = {"project_id", "name"}
EXPERIMENT_KEYS = {
    "experiment_id",
    "parent_experiment_id",
    "title",
    "branch",
    "commit_sha",
    "source_status",
    "run",
}
RUN_KEYS = {"run_id", "status", "result_claim", "evidence_refs"}

EXPERIMENT_STATUS = {"provisional", "answered", "unknown"}
RUN_STATUS = {"starting", "running", "done", "failed", "cancelled", "unknown"}
TERMINAL_RUN_STATUS = {"done", "failed", "cancelled"}

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(token|secret|password|passwd|credential|api[_-]?key|authorization|cookie)(?:$|[_-])",
    re.IGNORECASE,
)
SECRET_VALUE_RES = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?:ghp_|github_pat_)[A-Za-z0-9_]{16,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{12,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
)


class ProjectionError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def scan_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text):
                raise ProjectionError(f"secret_like_key:{path}.{key_text}")
            scan_for_secrets(item, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            scan_for_secrets(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in SECRET_VALUE_RES:
            if pattern.search(value):
                raise ProjectionError(f"secret_like_value:{path}")


def require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectionError(f"object_required:{field}")
    return value


def require_keys(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ProjectionError(f"unknown_keys:{field}:{','.join(sorted(unknown))}")


def require_text(
    value: Any,
    field: str,
    *,
    max_len: int = MAX_TEXT,
    allow_none: bool = False,
) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise ProjectionError(f"text_required:{field}")
    text = value.strip()
    if not text:
        raise ProjectionError(f"empty_text:{field}")
    if len(text) > max_len:
        raise ProjectionError(f"text_too_long:{field}")
    if any(ord(ch) < 32 and ch not in "\t" for ch in text):
        raise ProjectionError(f"control_character:{field}")
    return text


def require_id(value: Any, field: str) -> str:
    text = require_text(value, field, max_len=128)
    assert text is not None
    if not ID_RE.fullmatch(text):
        raise ProjectionError(f"invalid_id:{field}")
    return text


def require_sha(value: Any, field: str) -> str:
    text = require_text(value, field, max_len=40)
    assert text is not None
    if not SHA_RE.fullmatch(text):
        raise ProjectionError(f"invalid_sha:{field}")
    return text


def require_branch(value: Any, field: str) -> str:
    text = require_text(value, field, max_len=256)
    assert text is not None
    if (
        not BRANCH_RE.fullmatch(text)
        or ".." in text
        or "//" in text
        or text.endswith("/")
    ):
        raise ProjectionError(f"invalid_branch:{field}")
    return text


def normalize_evidence_refs(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProjectionError(f"list_required:{field}")
    if len(value) > MAX_EVIDENCE_REFS:
        raise ProjectionError(f"too_many_evidence_refs:{field}")
    refs: set[str] = set()
    for index, item in enumerate(value):
        ref = require_text(item, f"{field}[{index}]", max_len=MAX_REF)
        assert ref is not None
        refs.add(ref)
    return sorted(refs)


def normalize_run(value: Any, exp_id: str) -> dict[str, Any] | None:
    if value is None:
        return None
    run = require_object(value, f"experiments[{exp_id}].run")
    require_keys(run, RUN_KEYS, f"experiments[{exp_id}].run")

    run_id = require_id(run.get("run_id"), f"experiments[{exp_id}].run.run_id")
    status = require_text(run.get("status"), f"experiments[{exp_id}].run.status")
    assert status is not None
    if status not in RUN_STATUS:
        raise ProjectionError(f"invalid_run_status:{exp_id}")

    result_claim = require_text(
        run.get("result_claim"),
        f"experiments[{exp_id}].run.result_claim",
        allow_none=True,
    )
    evidence_refs = normalize_evidence_refs(
        run.get("evidence_refs"), f"experiments[{exp_id}].run.evidence_refs"
    )
    if result_claim is not None and not evidence_refs:
        raise ProjectionError(f"result_claim_without_evidence_ref:{exp_id}")

    return {
        "run_id": run_id,
        "status": status,
        "result_claim": result_claim,
        "evidence_refs": evidence_refs,
    }


def normalize_source(source: Any) -> dict[str, Any]:
    source = require_object(source, "$")
    scan_for_secrets(source)
    require_keys(source, TOP_KEYS, "$")

    if source.get("schema") != INPUT_SCHEMA:
        raise ProjectionError("input_schema_mismatch")

    upstream = require_object(source.get("upstream"), "upstream")
    require_keys(upstream, UPSTREAM_KEYS, "upstream")
    repository = require_text(upstream.get("repository"), "upstream.repository")
    upstream_sha = require_sha(upstream.get("commit_sha"), "upstream.commit_sha")
    version = require_text(upstream.get("version"), "upstream.version")
    if repository != SUPPORTED_UPSTREAM_REPOSITORY:
        raise ProjectionError("unsupported_upstream_repository")
    if upstream_sha != SUPPORTED_UPSTREAM_SHA:
        raise ProjectionError("unsupported_upstream_sha")
    if version != SUPPORTED_UPSTREAM_VERSION:
        raise ProjectionError("unsupported_upstream_version")

    project = require_object(source.get("project"), "project")
    require_keys(project, PROJECT_KEYS, "project")
    project_id = require_id(project.get("project_id"), "project.project_id")
    project_name = require_text(project.get("name"), "project.name")

    experiments_raw = source.get("experiments")
    if not isinstance(experiments_raw, list) or not experiments_raw:
        raise ProjectionError("experiments_nonempty_list_required")
    if len(experiments_raw) > MAX_EXPERIMENTS:
        raise ProjectionError("too_many_experiments")

    experiments: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(experiments_raw):
        exp = require_object(raw, f"experiments[{index}]")
        require_keys(exp, EXPERIMENT_KEYS, f"experiments[{index}]")
        exp_id = require_id(exp.get("experiment_id"), f"experiments[{index}].experiment_id")
        if exp_id in ids:
            raise ProjectionError(f"duplicate_experiment_id:{exp_id}")
        ids.add(exp_id)

        parent_raw = exp.get("parent_experiment_id")
        parent_id = (
            None
            if parent_raw is None
            else require_id(parent_raw, f"experiments[{exp_id}].parent_experiment_id")
        )
        if parent_id == exp_id:
            raise ProjectionError(f"self_parent:{exp_id}")

        title = require_text(exp.get("title"), f"experiments[{exp_id}].title")
        branch = require_branch(exp.get("branch"), f"experiments[{exp_id}].branch")
        commit_sha = require_sha(exp.get("commit_sha"), f"experiments[{exp_id}].commit_sha")
        source_status = require_text(
            exp.get("source_status"), f"experiments[{exp_id}].source_status"
        )
        assert source_status is not None
        if source_status not in EXPERIMENT_STATUS:
            raise ProjectionError(f"invalid_experiment_status:{exp_id}")

        run = normalize_run(exp.get("run"), exp_id)
        if source_status == "answered":
            if run is None or run["status"] not in TERMINAL_RUN_STATUS:
                raise ProjectionError(f"answered_without_terminal_run:{exp_id}")

        experiments.append(
            {
                "experiment_id": exp_id,
                "parent_experiment_id": parent_id,
                "title": title,
                "branch": branch,
                "commit_sha": commit_sha,
                "source_status": source_status,
                "run": run,
            }
        )

    by_id = {exp["experiment_id"]: exp for exp in experiments}
    for exp in experiments:
        parent = exp["parent_experiment_id"]
        if parent is not None and parent not in by_id:
            raise ProjectionError(
                f"missing_parent:{exp['experiment_id']}:{parent}"
            )

    # Cycle check. Parent links form a forest when valid.
    for exp_id in sorted(by_id):
        seen: set[str] = set()
        cursor: str | None = exp_id
        while cursor is not None:
            if cursor in seen:
                raise ProjectionError(f"parent_cycle:{exp_id}")
            seen.add(cursor)
            cursor = by_id[cursor]["parent_experiment_id"]

    experiments.sort(key=lambda item: item["experiment_id"])

    return {
        "schema": INPUT_SCHEMA,
        "upstream": {
            "repository": repository,
            "commit_sha": upstream_sha,
            "version": version,
        },
        "project": {"project_id": project_id, "name": project_name},
        "experiments": experiments,
    }


def build_projection(source: Any) -> dict[str, Any]:
    normalized = normalize_source(source)
    warnings: list[str] = []
    projected_experiments: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    for exp in normalized["experiments"]:
        run = exp["run"]
        projected_run = None
        evidence_refs: list[str] = []
        if run is not None:
            evidence_refs = list(run["evidence_refs"])
            claim_state = (
                "UNVERIFIED_EXTERNAL"
                if run["result_claim"] is not None
                else "NO_RESULT_CLAIM"
            )
            projected_run = {
                "run_id": run["run_id"],
                "source_status": run["status"],
                "result_claim": run["result_claim"],
                "claim_verification": claim_state,
                "evidence_refs": evidence_refs,
            }
            if run["result_claim"] is not None:
                warnings.append(
                    f"RESULT_CLAIM_REQUIRES_WORK_VERIFICATION:{exp['experiment_id']}:{run['run_id']}"
                )
            elif run["status"] in TERMINAL_RUN_STATUS:
                warnings.append(
                    f"TERMINAL_RUN_STATUS_IS_NOT_RESULT:{exp['experiment_id']}:{run['run_id']}"
                )

        if exp["source_status"] == "answered":
            warnings.append(
                f"ANSWERED_IS_EXTERNAL_SOURCE_STATE:{exp['experiment_id']}"
            )

        projected_experiments.append(
            {
                "experiment_id": exp["experiment_id"],
                "parent_experiment_id": exp["parent_experiment_id"],
                "title": exp["title"],
                "branch": exp["branch"],
                "commit_sha": exp["commit_sha"],
                "source_status": exp["source_status"],
                "authority": "NONE",
                "evidence_refs": evidence_refs,
                "run": projected_run,
            }
        )
        if exp["parent_experiment_id"] is not None:
            edges.append(
                {
                    "edge_id": f"{exp['parent_experiment_id']}->{exp['experiment_id']}",
                    "from": exp["parent_experiment_id"],
                    "to": exp["experiment_id"],
                    "edge_type": "parent_child",
                }
            )

    edges.sort(key=lambda item: item["edge_id"])
    warnings.sort()

    return {
        "schema": OUTPUT_SCHEMA,
        "authority": {
            "source_of_truth": False,
            "projection_only": True,
            "execution_authorized": False,
            "owner_approval_satisfied": False,
            "private_data_eligible": False,
        },
        "job_binding": {
            "bound": False,
            "authoritative_job_id": None,
            "reason": "OpenResearch developer export is external metadata, not PANAM Task/Job State.",
        },
        "upstream": normalized["upstream"],
        "project": normalized["project"],
        "source_manifest_sha256": hashlib.sha256(
            canonical_bytes(normalized)
        ).hexdigest(),
        "experiments": projected_experiments,
        "edges": edges,
        "warnings": warnings,
    }


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    projection = build_projection(source)
    print(json.dumps(projection, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

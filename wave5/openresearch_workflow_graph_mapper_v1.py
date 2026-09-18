#!/usr/bin/env python3
"""Pure PANAM OpenResearch projection -> Workflow Graph mapper V1.

The mapper is presentation/projection only. It never reads OpenResearch runtime
state directly, never binds PANAM Task/Job State, never infers live activity and
never promotes external result claims into verified PANAM evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

INPUT_SCHEMA = "panam.openresearch.research-projection.v1"
OUTPUT_SCHEMA = "panam.workflow.graph.v1"
GRAPH_VERSION = "openresearch-workflow-graph-v1"

TOP_KEYS = {
    "schema",
    "authority",
    "job_binding",
    "upstream",
    "project",
    "source_manifest_sha256",
    "experiments",
    "edges",
    "warnings",
}
AUTHORITY_KEYS = {
    "source_of_truth",
    "projection_only",
    "execution_authorized",
    "owner_approval_satisfied",
    "private_data_eligible",
}
JOB_KEYS = {"bound", "authoritative_job_id", "reason"}
UPSTREAM_KEYS = {"repository", "commit_sha", "version"}
PROJECT_KEYS = {"project_id", "name"}
EXPERIMENT_KEYS = {
    "experiment_id",
    "parent_experiment_id",
    "title",
    "branch",
    "commit_sha",
    "source_status",
    "authority",
    "evidence_refs",
    "run",
}
RUN_KEYS = {
    "run_id",
    "source_status",
    "result_claim",
    "claim_verification",
    "evidence_refs",
}
EDGE_KEYS = {"edge_id", "from", "to", "edge_type"}

SUPPORTED_UPSTREAM_REPOSITORY = "alphaXiv/OpenResearch"
SUPPORTED_UPSTREAM_SHA = "69768ff1b0537a4656e69f550fc444ac35b945d2"
SUPPORTED_UPSTREAM_VERSION = "0.2.5"

EXPERIMENT_STATUS = {"provisional", "answered", "unknown"}
CLAIM_STATES = {"UNVERIFIED_EXTERNAL", "NO_RESULT_CLAIM"}
GRAPH_STATES = {"planned", "completed", "unknown"}
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
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


class MapperError(ValueError):
    pass


def _scan_for_secrets(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text):
                raise MapperError(f"secret_like_key:{path}.{key_text}")
            _scan_for_secrets(item, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _scan_for_secrets(item, f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in SECRET_VALUE_RES:
            if pattern.search(value):
                raise MapperError(f"secret_like_value:{path}")


def _obj(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MapperError(f"object_required:{field}")
    return value


def _keys(value: dict[str, Any], allowed: set[str], field: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise MapperError(f"unknown_keys:{field}:{','.join(sorted(unknown))}")


def _text(value: Any, field: str, *, max_len: int = 512, allow_none: bool = False) -> str | None:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise MapperError(f"text_required:{field}")
    value = value.strip()
    if not value:
        raise MapperError(f"empty_text:{field}")
    if len(value) > max_len:
        raise MapperError(f"text_too_long:{field}")
    if any(ord(ch) < 32 for ch in value):
        raise MapperError(f"control_character:{field}")
    return value


def _string_list(value: Any, field: str, *, max_items: int = 32) -> list[str]:
    if not isinstance(value, list):
        raise MapperError(f"list_required:{field}")
    if len(value) > max_items:
        raise MapperError(f"too_many_items:{field}")
    out: set[str] = set()
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]", max_len=512)
        assert text is not None
        out.add(text)
    return sorted(out)


def _node_id(experiment_id: str) -> str:
    digest = hashlib.sha256(experiment_id.encode("utf-8")).hexdigest()[:20]
    return f"orx-exp-{digest}"


def _state(source_status: str) -> str:
    if source_status == "answered":
        return "completed"
    if source_status == "provisional":
        return "planned"
    return "unknown"


def validate_projection(source: Any) -> dict[str, Any]:
    source = _obj(source, "$")
    _scan_for_secrets(source)
    _keys(source, TOP_KEYS, "$")
    if source.get("schema") != INPUT_SCHEMA:
        raise MapperError("input_schema_mismatch")

    authority = _obj(source.get("authority"), "authority")
    _keys(authority, AUTHORITY_KEYS, "authority")
    expected_authority = {
        "source_of_truth": False,
        "projection_only": True,
        "execution_authorized": False,
        "owner_approval_satisfied": False,
        "private_data_eligible": False,
    }
    if authority != expected_authority:
        raise MapperError("input_authority_not_fail_closed")

    job = _obj(source.get("job_binding"), "job_binding")
    _keys(job, JOB_KEYS, "job_binding")
    if job.get("bound") is not False or job.get("authoritative_job_id") is not None:
        raise MapperError("input_authoritative_job_binding_forbidden")
    _text(job.get("reason"), "job_binding.reason", max_len=512)

    upstream = _obj(source.get("upstream"), "upstream")
    _keys(upstream, UPSTREAM_KEYS, "upstream")
    if upstream != {
        "repository": SUPPORTED_UPSTREAM_REPOSITORY,
        "commit_sha": SUPPORTED_UPSTREAM_SHA,
        "version": SUPPORTED_UPSTREAM_VERSION,
    }:
        raise MapperError("unsupported_upstream_identity")

    project = _obj(source.get("project"), "project")
    _keys(project, PROJECT_KEYS, "project")
    project_id = _text(project.get("project_id"), "project.project_id", max_len=128)
    project_name = _text(project.get("name"), "project.name", max_len=800)
    assert project_id is not None and project_name is not None

    manifest = _text(source.get("source_manifest_sha256"), "source_manifest_sha256", max_len=64)
    assert manifest is not None
    if not SHA64_RE.fullmatch(manifest):
        raise MapperError("invalid_source_manifest_sha256")

    experiments_raw = source.get("experiments")
    if not isinstance(experiments_raw, list) or not experiments_raw:
        raise MapperError("experiments_nonempty_list_required")
    if len(experiments_raw) > 256:
        raise MapperError("too_many_experiments")

    experiments: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, raw in enumerate(experiments_raw):
        exp = _obj(raw, f"experiments[{index}]")
        _keys(exp, EXPERIMENT_KEYS, f"experiments[{index}]")
        exp_id = _text(exp.get("experiment_id"), f"experiments[{index}].experiment_id", max_len=128)
        assert exp_id is not None
        if exp_id in ids:
            raise MapperError(f"duplicate_experiment_id:{exp_id}")
        ids.add(exp_id)

        parent = _text(
            exp.get("parent_experiment_id"),
            f"experiments[{exp_id}].parent_experiment_id",
            max_len=128,
            allow_none=True,
        )
        title = _text(exp.get("title"), f"experiments[{exp_id}].title", max_len=200)
        branch = _text(exp.get("branch"), f"experiments[{exp_id}].branch", max_len=256)
        commit_sha = _text(exp.get("commit_sha"), f"experiments[{exp_id}].commit_sha", max_len=40)
        status = _text(exp.get("source_status"), f"experiments[{exp_id}].source_status", max_len=32)
        assert title is not None and branch is not None and commit_sha is not None and status is not None
        if not SHA40_RE.fullmatch(commit_sha):
            raise MapperError(f"invalid_commit_sha:{exp_id}")
        if status not in EXPERIMENT_STATUS:
            raise MapperError(f"invalid_source_status:{exp_id}")
        if exp.get("authority") != "NONE":
            raise MapperError(f"experiment_authority_forbidden:{exp_id}")
        evidence_refs = _string_list(
            exp.get("evidence_refs"), f"experiments[{exp_id}].evidence_refs", max_items=16
        )

        run = exp.get("run")
        normalized_run = None
        if run is not None:
            run = _obj(run, f"experiments[{exp_id}].run")
            _keys(run, RUN_KEYS, f"experiments[{exp_id}].run")
            run_id = _text(run.get("run_id"), f"experiments[{exp_id}].run.run_id", max_len=128)
            run_status = _text(
                run.get("source_status"), f"experiments[{exp_id}].run.source_status", max_len=32
            )
            result_claim = _text(
                run.get("result_claim"),
                f"experiments[{exp_id}].run.result_claim",
                max_len=800,
                allow_none=True,
            )
            claim_state = _text(
                run.get("claim_verification"),
                f"experiments[{exp_id}].run.claim_verification",
                max_len=32,
            )
            assert run_id is not None and run_status is not None and claim_state is not None
            if claim_state not in CLAIM_STATES:
                raise MapperError(f"invalid_claim_state:{exp_id}")
            if result_claim is not None and claim_state != "UNVERIFIED_EXTERNAL":
                raise MapperError(f"external_claim_not_marked_unverified:{exp_id}")
            run_evidence = _string_list(
                run.get("evidence_refs"),
                f"experiments[{exp_id}].run.evidence_refs",
                max_items=16,
            )
            normalized_run = {
                "run_id": run_id,
                "source_status": run_status,
                "result_claim": result_claim,
                "claim_verification": claim_state,
                "evidence_refs": run_evidence,
            }

        experiments.append(
            {
                "experiment_id": exp_id,
                "parent_experiment_id": parent,
                "title": title,
                "branch": branch,
                "commit_sha": commit_sha,
                "source_status": status,
                "evidence_refs": evidence_refs,
                "run": normalized_run,
            }
        )

    by_id = {exp["experiment_id"]: exp for exp in experiments}
    for exp in experiments:
        parent = exp["parent_experiment_id"]
        if parent is not None and parent not in by_id:
            raise MapperError(f"missing_parent:{exp['experiment_id']}:{parent}")

    expected_edges = {
        (exp["parent_experiment_id"], exp["experiment_id"])
        for exp in experiments
        if exp["parent_experiment_id"] is not None
    }
    edges_raw = source.get("edges")
    if not isinstance(edges_raw, list):
        raise MapperError("edges_list_required")
    actual_edges: set[tuple[str, str]] = set()
    for index, raw in enumerate(edges_raw):
        edge = _obj(raw, f"edges[{index}]")
        _keys(edge, EDGE_KEYS, f"edges[{index}]")
        if edge.get("edge_type") != "parent_child":
            raise MapperError("input_edge_type_invalid")
        left = _text(edge.get("from"), f"edges[{index}].from", max_len=128)
        right = _text(edge.get("to"), f"edges[{index}].to", max_len=128)
        edge_id = _text(edge.get("edge_id"), f"edges[{index}].edge_id", max_len=300)
        assert left is not None and right is not None and edge_id is not None
        if edge_id != f"{left}->{right}":
            raise MapperError("input_edge_id_mismatch")
        actual_edges.add((left, right))
    if actual_edges != expected_edges or len(actual_edges) != len(edges_raw):
        raise MapperError("input_edges_do_not_match_parent_links")

    warnings = _string_list(source.get("warnings"), "warnings", max_items=1024)

    experiments.sort(key=lambda item: item["experiment_id"])
    return {
        "upstream": upstream,
        "project": {"project_id": project_id, "name": project_name},
        "source_manifest_sha256": manifest,
        "experiments": experiments,
        "warnings": warnings,
    }


def map_to_workflow_graph(source: Any) -> dict[str, Any]:
    projection = validate_projection(source)
    experiments = projection["experiments"]
    children: dict[str, int] = {exp["experiment_id"]: 0 for exp in experiments}
    for exp in experiments:
        parent = exp["parent_experiment_id"]
        if parent is not None:
            children[parent] += 1

    node_id_by_exp = {exp["experiment_id"]: _node_id(exp["experiment_id"]) for exp in experiments}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for exp in experiments:
        evidence_refs = [
            f"openresearch-experiment:{exp['experiment_id']}",
            f"openresearch-source-status:{exp['source_status']}",
            *exp["evidence_refs"],
        ]
        run = exp["run"]
        if run is not None:
            evidence_refs.extend(run["evidence_refs"])
            evidence_refs.extend(
                [
                    f"openresearch-run:{run['run_id']}",
                    f"openresearch-run-status:{run['source_status']}",
                    f"openresearch-claim-verification:{run['claim_verification']}",
                ]
            )
        evidence_refs = sorted(set(evidence_refs))

        input_refs = []
        if exp["parent_experiment_id"] is not None:
            input_refs.append(f"openresearch-parent:{exp['parent_experiment_id']}")

        nodes.append(
            {
                "node_id": node_id_by_exp[exp["experiment_id"]],
                "title": exp["title"],
                "node_type": "subworkflow",
                "authority": "NONE",
                "state": _state(exp["source_status"]),
                "input_refs": input_refs,
                "output_refs": [
                    f"git-branch:{exp['branch']}",
                    f"git-commit:{exp['commit_sha']}",
                ],
                "evidence_refs": evidence_refs,
            }
        )

        parent = exp["parent_experiment_id"]
        if parent is not None:
            edges.append(
                {
                    "edge_id": f"{node_id_by_exp[parent]}--{node_id_by_exp[exp['experiment_id']]}",
                    "from": node_id_by_exp[parent],
                    "to": node_id_by_exp[exp["experiment_id"]],
                    "edge_type": "fanout" if children[parent] > 1 else "sequential",
                    "condition": None,
                }
            )

    nodes.sort(key=lambda item: item["node_id"])
    edges.sort(key=lambda item: item["edge_id"])
    workflow_digest = projection["source_manifest_sha256"][:16]

    graph = {
        "schema": OUTPUT_SCHEMA,
        "workflow_id": f"openresearch:{projection['project']['project_id']}:{workflow_digest}",
        "workflow_type": "openresearch_research_projection",
        "graph_version": GRAPH_VERSION,
        "source_of_truth": False,
        "projection_only": True,
        "job_binding": {
            "bound": False,
            "authoritative_job_id": None,
            "reason": "OpenResearch research projection has no PANAM Task/Job authority.",
        },
        "source_refs": [
            {
                "kind": "openresearch_projection",
                "ref": f"sha256:{projection['source_manifest_sha256']}",
            }
        ],
        "nodes": nodes,
        "edges": edges,
        "runtime_observation": {
            "authoritative_runtime_bound": False,
            "active_nodes": [],
            "freshness": "unknown",
            "node_mapping_state": "mapped",
            "note": "External lifecycle is projected; live execution activity and result verification are not inferred.",
        },
    }
    validate_graph(graph)
    return graph


def validate_graph(graph: Any) -> None:
    graph = _obj(graph, "graph")
    if graph.get("schema") != OUTPUT_SCHEMA:
        raise MapperError("graph_schema_mismatch")
    if graph.get("source_of_truth") is not False:
        raise MapperError("graph_source_of_truth_forbidden")
    if graph.get("projection_only") is not True:
        raise MapperError("graph_projection_only_required")

    job = _obj(graph.get("job_binding"), "graph.job_binding")
    if job.get("bound") is not False or job.get("authoritative_job_id") is not None:
        raise MapperError("graph_authoritative_job_binding_forbidden")

    runtime = _obj(graph.get("runtime_observation"), "graph.runtime_observation")
    if runtime.get("authoritative_runtime_bound") is not False:
        raise MapperError("graph_runtime_binding_forbidden")
    if runtime.get("active_nodes") != []:
        raise MapperError("graph_active_nodes_must_be_empty")

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise MapperError("graph_nodes_nonempty_required")
    if not isinstance(edges, list):
        raise MapperError("graph_edges_list_required")

    node_ids: set[str] = set()
    for raw in nodes:
        node = _obj(raw, "graph.nodes[]")
        node_id = _text(node.get("node_id"), "graph.node.node_id", max_len=128)
        assert node_id is not None
        if node_id in node_ids:
            raise MapperError("graph_duplicate_node")
        node_ids.add(node_id)
        if node.get("node_type") != "subworkflow":
            raise MapperError("graph_node_type_invalid")
        if node.get("authority") != "NONE":
            raise MapperError("graph_node_authority_forbidden")
        if node.get("state") not in GRAPH_STATES:
            raise MapperError("graph_node_state_invalid")

    edge_ids: set[str] = set()
    for raw in edges:
        edge = _obj(raw, "graph.edges[]")
        edge_id = _text(edge.get("edge_id"), "graph.edge.edge_id", max_len=300)
        assert edge_id is not None
        if edge_id in edge_ids:
            raise MapperError("graph_duplicate_edge")
        edge_ids.add(edge_id)
        if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
            raise MapperError("graph_dangling_edge")
        if edge.get("edge_type") not in {"fanout", "sequential"}:
            raise MapperError("graph_edge_type_invalid")
        if edge.get("condition") is not None:
            raise MapperError("graph_edge_condition_must_be_null")


def main() -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    graph = map_to_workflow_graph(source)
    print(json.dumps(graph, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
